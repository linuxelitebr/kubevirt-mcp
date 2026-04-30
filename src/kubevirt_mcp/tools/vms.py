"""VM-related MCP tools: list, get, virt_cluster_health.

The bread and butter. If your agent isn't calling at least one of
these per session, it's not really helping.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client


def _summarize_vm(vm: dict[str, Any]) -> dict[str, Any]:
    """Return a compact summary of a VM (for list results)."""
    metadata = vm.get("metadata", {})
    spec = vm.get("spec", {})
    status = vm.get("status", {})
    template = spec.get("template", {}).get("spec", {})
    domain = template.get("domain", {})
    cpu = domain.get("cpu", {})
    memory = domain.get("resources", {}).get("requests", {}).get("memory") or domain.get(
        "memory", {}
    ).get("guest")

    return {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "status": status.get("printableStatus") or ("Running" if status.get("ready") else "Stopped"),
        "ready": status.get("ready", False),
        "runStrategy": spec.get("runStrategy"),
        "running": spec.get("running"),
        "cpu": {
            "cores": cpu.get("cores"),
            "sockets": cpu.get("sockets"),
            "threads": cpu.get("threads"),
            "model": cpu.get("model"),
        },
        "memory": memory,
        "instanceType": (spec.get("instancetype") or {}).get("name"),
        "preference": (spec.get("preference") or {}).get("name"),
        "creationTimestamp": metadata.get("creationTimestamp"),
    }


def _summarize_vmi(vmi: dict[str, Any]) -> dict[str, Any]:
    """Return a compact summary of a VMI (running instance)."""
    metadata = vmi.get("metadata", {})
    status = vmi.get("status", {})
    interfaces = status.get("interfaces", []) or []

    return {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "phase": status.get("phase"),
        "nodeName": status.get("nodeName"),
        "ip": (interfaces[0].get("ipAddress") if interfaces else None),
        "interfaces": [
            {"name": i.get("name"), "ip": i.get("ipAddress"), "mac": i.get("mac")}
            for i in interfaces
        ],
        "guestOSInfo": status.get("guestOSInfo", {}),
        "migrationState": status.get("migrationState"),
        "qosClass": status.get("qosClass"),
    }


def register(mcp: FastMCP) -> None:
    """Register all VM-related tools with the MCP server."""

    @mcp.tool()
    def list_vms(namespace: str | None = None) -> list[dict[str, Any]]:
        """List VirtualMachines on the cluster.

        Args:
            namespace: Filter to one namespace. Leave it out to see
                every VM the kubeconfig is allowed to see, which on a
                large cluster can be a lot.

        Returns one compact dict per VM (name, namespace, status,
        ready, cpu/memory, instanceType, creationTimestamp). The full
        spec is intentionally not in here: that's what get_vm is for.
        """
        client = get_client()
        vms = client.list_vms(namespace=namespace)
        return [_summarize_vm(vm) for vm in vms]

    @mcp.tool()
    def get_vm(name: str, namespace: str) -> dict[str, Any]:
        """Return the full VirtualMachine, plus its VMI if it has one.

        Args:
            name: VM name.
            namespace: VM namespace.

        The whole spec and status. Conditions, resource requests,
        network interfaces, disks, the lot. If you only need the
        compact view, list_vms is cheaper.
        """
        client = get_client()
        vm = client.get_vm(name=name, namespace=namespace)
        vmi = client.get_vmi(name=name, namespace=namespace)
        return {
            "vm": vm,
            "vmi": vmi,  # may be None if VM is stopped
        }

    @mcp.tool()
    def list_vmis(namespace: str | None = None) -> list[dict[str, Any]]:
        """List currently running VirtualMachineInstances (VMIs).

        A VMI is what a VM actually becomes when it boots. Use this
        when you want to know which VMs are really running, on which
        node, and with what IP, as opposed to which VMs the controller
        thinks are running.

        Args:
            namespace: Optional namespace filter.
        """
        client = get_client()
        vmis = client.list_vmis(namespace=namespace)
        return [_summarize_vmi(v) for v in vmis]

    @mcp.tool()
    def virt_cluster_health() -> dict[str, Any]:
        """Aggregate health snapshot of the virtualization stack.

        Counts of VMs by state, total VMIs running, any failed
        migrations, and any DataVolume that hasn't finished importing.
        Roughly the dashboard you wish the OpenShift web console
        actually had.
        """
        client = get_client()

        vms = client.list_vms()
        vmis = client.list_vmis()
        migrations = client.list_migrations()
        data_volumes = client.list_data_volumes()

        # VM state breakdown
        states: dict[str, int] = {}
        for vm in vms:
            state = (
                vm.get("status", {}).get("printableStatus")
                or ("Running" if vm.get("status", {}).get("ready") else "Stopped")
            )
            states[state] = states.get(state, 0) + 1

        # Migration breakdown
        migration_phases: dict[str, int] = {}
        for m in migrations:
            phase = m.get("status", {}).get("phase", "Unknown")
            migration_phases[phase] = migration_phases.get(phase, 0) + 1

        failed_migrations = [
            {
                "name": m["metadata"]["name"],
                "namespace": m["metadata"]["namespace"],
                "vmiName": m.get("spec", {}).get("vmiName"),
                "phase": m.get("status", {}).get("phase"),
                "reason": (m.get("status", {}).get("conditions") or [{}])[0].get("message"),
            }
            for m in migrations
            if m.get("status", {}).get("phase") == "Failed"
        ]

        # DataVolumes not Succeeded
        unfinished_dvs = [
            {
                "name": dv["metadata"]["name"],
                "namespace": dv["metadata"]["namespace"],
                "phase": dv.get("status", {}).get("phase"),
                "progress": dv.get("status", {}).get("progress"),
            }
            for dv in data_volumes
            if dv.get("status", {}).get("phase") not in {"Succeeded", None}
        ]

        return {
            "totalVMs": len(vms),
            "vmStates": states,
            "totalVMIs": len(vmis),
            "totalMigrations": len(migrations),
            "migrationPhases": migration_phases,
            "failedMigrations": failed_migrations,
            "totalDataVolumes": len(data_volumes),
            "unfinishedDataVolumes": unfinished_dvs,
        }
