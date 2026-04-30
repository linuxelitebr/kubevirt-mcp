"""Composite diagnostics tool.

`diagnose_vm` is the one tool you actually want when somebody pings
you saying "the VM is broken". It pulls the spec, the status, the
conditions, the last events, the related DataVolumes, the recent
migrations, all in one round trip, and bolts on a few heuristic
hypotheses so the agent doesn't have to do its own forensic work.

Heuristics are not magic. They're a glorified series of if statements
that have seen enough broken VMs to know where to point. Treat them
as hints, not verdicts.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client


def _vm_overall_state(vm: dict[str, Any], vmi: dict[str, Any] | None) -> str:
    """Derive a human-readable overall state from VM + VMI."""
    status = vm.get("status", {}) or {}
    printable = status.get("printableStatus")
    if printable:
        return printable
    if vmi and vmi.get("status", {}).get("phase"):
        return vmi["status"]["phase"]
    return "Stopped" if not status.get("ready") else "Running"


def _extract_conditions(obj: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": c.get("type"),
            "status": c.get("status"),
            "reason": c.get("reason"),
            "message": c.get("message"),
            "lastTransitionTime": c.get("lastTransitionTime"),
        }
        for c in (obj.get("status", {}).get("conditions") or [])
    ]


def _generate_hypotheses(
    vm: dict[str, Any],
    vmi: dict[str, Any] | None,
    events: list[dict[str, Any]],
    related_dvs: list[dict[str, Any]],
    related_migrations: list[dict[str, Any]],
) -> list[str]:
    """Heuristic guesses about what might be wrong with the VM.

    Hints, not verdicts. The agent gets the raw data alongside, and
    is expected to reason from there. We just point at the obvious
    smoke signals so it doesn't have to.
    """
    hints: list[str] = []
    state = _vm_overall_state(vm, vmi)

    # 1. VM stopped intentionally
    spec = vm.get("spec", {})
    run_strategy = spec.get("runStrategy")
    running = spec.get("running")
    if state in {"Stopped", "Halted"} and (run_strategy in {"Halted", "Manual"} or running is False):
        hints.append(
            f"VM is intentionally stopped (runStrategy={run_strategy}, running={running}). "
            "Use 'oc patch vm ... --type merge -p {\"spec\":{\"running\":true}}' to start it."
        )

    # 2. VMI absent but VM should be running
    if vmi is None and state not in {"Stopped", "Halted"}:
        hints.append(
            "VM has no active VirtualMachineInstance even though it's not stopped. "
            "Check recent events for scheduling failures or template issues."
        )

    # 3. DataVolume not Succeeded
    failed_dvs = [
        dv for dv in related_dvs if dv.get("phase") not in {"Succeeded", None}
    ]
    if failed_dvs:
        names = ", ".join(f"{dv['namespace']}/{dv['name']}({dv['phase']})" for dv in failed_dvs)
        hints.append(
            f"One or more DataVolumes for this VM have not finished importing: {names}. "
            "VM cannot start cleanly until disks are ready."
        )

    # 4. Recent failed migrations
    failed_migrations = [
        m for m in related_migrations if m.get("phase") == "Failed"
    ]
    if failed_migrations:
        latest = failed_migrations[0]
        hints.append(
            f"Latest live migration ({latest['name']}) failed. "
            f"Reason: {latest.get('failureReason') or 'unknown'}. "
            "Check node taints, drain budgets, and source/target compatibility."
        )

    # 5. Warning events
    warning_events = [e for e in events if e.get("type") == "Warning"]
    if warning_events:
        recent = warning_events[0]
        hints.append(
            f"Most recent Warning event: {recent['reason']}: {recent['message']}"
        )

    # 6. Conditions with status=False
    bad_conditions = [
        c
        for c in _extract_conditions(vm)
        if c["status"] == "False" and c["type"] in {"Ready", "LiveMigratable"}
    ]
    if bad_conditions:
        for c in bad_conditions:
            hints.append(
                f"Condition {c['type']}=False, reason={c.get('reason')}: {c.get('message')}"
            )

    if not hints:
        hints.append(
            "No obvious red flags detected. VM appears healthy or the issue is "
            "outside the scope of automated diagnostics."
        )

    return hints


def register(mcp: FastMCP) -> None:
    """Register the composite diagnostic tool."""

    @mcp.tool()
    def diagnose_vm(name: str, namespace: str) -> dict[str, Any]:
        """Aggregate diagnostic data and hypotheses for a specific VM.

        Use this when somebody asks "why is this VM not working?".
        It pulls everything potentially relevant in one round trip:

          - VM spec and status (with conditions)
          - VMI status (if there is one)
          - Recent Kubernetes Events for the VM
          - Related DataVolumes (matched by name prefix)
          - Recent VirtualMachineInstanceMigrations (matched by vmiName)

        Plus a list of heuristic hints. The hints are opinions, not
        diagnoses. The agent gets the raw data alongside and is
        expected to read it.

        Args:
            name: VM name.
            namespace: VM namespace.
        """
        client = get_client()
        vm = client.get_vm(name=name, namespace=namespace)
        vmi = client.get_vmi(name=name, namespace=namespace)
        events = client.list_events_for_vm(name=name, namespace=namespace)[:15]

        # DataVolumes whose name starts with the VM name (common convention)
        all_dvs = client.list_data_volumes(namespace=namespace)
        related_dvs = []
        for dv in all_dvs:
            dv_name = dv.get("metadata", {}).get("name", "")
            if dv_name == name or dv_name.startswith(f"{name}-"):
                related_dvs.append(
                    {
                        "name": dv_name,
                        "namespace": namespace,
                        "phase": dv.get("status", {}).get("phase"),
                        "progress": dv.get("status", {}).get("progress"),
                    }
                )

        # Migrations referencing this VMI
        all_migrations = client.list_migrations(namespace=namespace)
        related_migrations = []
        for m in all_migrations:
            if m.get("spec", {}).get("vmiName") == name:
                ms = m.get("status", {})
                related_migrations.append(
                    {
                        "name": m["metadata"]["name"],
                        "phase": ms.get("phase"),
                        "failureReason": (ms.get("migrationState") or {}).get("failureReason"),
                        "creationTime": m["metadata"].get("creationTimestamp"),
                    }
                )
        # newest first
        related_migrations.sort(key=lambda m: m.get("creationTime") or "", reverse=True)

        overall = _vm_overall_state(vm, vmi)
        hints = _generate_hypotheses(vm, vmi, events, related_dvs, related_migrations)

        return {
            "name": name,
            "namespace": namespace,
            "overallState": overall,
            "hints": hints,
            "vmConditions": _extract_conditions(vm),
            "vmiConditions": _extract_conditions(vmi or {}) if vmi else [],
            "recentEvents": events,
            "relatedDataVolumes": related_dvs,
            "recentMigrations": related_migrations[:5],
        }
