"""Unit tests for the diagnose_vm heuristics.

These verify that `_generate_hypotheses` produces the right hints for each
class of failure scenario, given mock VM/VMI/event/DV/migration payloads.
"""

from __future__ import annotations

from kubevirt_mcp.tools.diagnose import (
    _extract_conditions,
    _generate_hypotheses,
    _vm_overall_state,
)


class TestVMOverallState:
    def test_uses_printable_status_when_present(self, running_vm, running_vmi):
        assert _vm_overall_state(running_vm, running_vmi) == "Running"

    def test_falls_back_to_vmi_phase(self):
        vm = {"status": {}}
        vmi = {"status": {"phase": "Scheduling"}}
        assert _vm_overall_state(vm, vmi) == "Scheduling"

    def test_stopped_when_no_signals(self):
        vm = {"status": {}}
        assert _vm_overall_state(vm, None) == "Stopped"


class TestExtractConditions:
    def test_keeps_relevant_fields(self, running_vm):
        conds = _extract_conditions(running_vm)
        assert len(conds) == 4
        ready = next(c for c in conds if c["type"] == "Ready")
        assert ready["status"] == "True"

    def test_handles_no_conditions(self):
        assert _extract_conditions({}) == []


class TestGenerateHypothesesHealthy:
    def test_running_vm_has_no_red_flags(self, running_vm, running_vmi):
        hints = _generate_hypotheses(running_vm, running_vmi, [], [], [])
        assert len(hints) == 1
        assert "No obvious red flags" in hints[0]


class TestGenerateHypothesesStopped:
    def test_intentionally_stopped_vm_emits_hint(self, stopped_vm):
        hints = _generate_hypotheses(stopped_vm, None, [], [], [])
        assert any("intentionally stopped" in h for h in hints)
        assert any("runStrategy=Halted" in h for h in hints)


class TestGenerateHypothesesMissingVMI:
    def test_no_vmi_when_should_be_running(self, broken_vm):
        hints = _generate_hypotheses(broken_vm, None, [], [], [])
        # broken_vm has printableStatus=ErrorUnschedulable, so VMI-missing
        # hint should fire (it's not in {Stopped, Halted}).
        assert any("no active VirtualMachineInstance" in h for h in hints)


class TestGenerateHypothesesDataVolumes:
    def test_unfinished_dv_is_flagged(self, running_vm, running_vmi):
        related_dvs = [
            {"name": "boot", "namespace": "default", "phase": "ImportInProgress", "progress": "30%"},
        ]
        hints = _generate_hypotheses(running_vm, running_vmi, [], related_dvs, [])
        assert any("DataVolumes" in h and "ImportInProgress" in h for h in hints)

    def test_succeeded_dv_is_silent(self, running_vm, running_vmi):
        related_dvs = [
            {"name": "boot", "namespace": "default", "phase": "Succeeded", "progress": "100%"},
        ]
        hints = _generate_hypotheses(running_vm, running_vmi, [], related_dvs, [])
        assert not any("not finished importing" in h for h in hints)


class TestGenerateHypothesesMigrations:
    def test_failed_migration_surfaces_reason(self, running_vm, running_vmi, failed_migration):
        related_m = [
            {
                "name": failed_migration["metadata"]["name"],
                "phase": "Failed",
                "failureReason": "Connection reset by peer",
                "creationTime": "2026-04-29T15:00:00Z",
            }
        ]
        hints = _generate_hypotheses(running_vm, running_vmi, [], [], related_m)
        joined = " ".join(hints)
        assert "live migration" in joined
        assert "Connection reset by peer" in joined

    def test_only_succeeded_migrations_silent(self, running_vm, running_vmi, succeeded_migration):
        related_m = [
            {
                "name": succeeded_migration["metadata"]["name"],
                "phase": "Succeeded",
                "failureReason": None,
                "creationTime": "2026-04-28T15:00:00Z",
            }
        ]
        hints = _generate_hypotheses(running_vm, running_vmi, [], [], related_m)
        assert not any("live migration" in h and "failed" in h for h in hints)


class TestGenerateHypothesesEvents:
    def test_warning_event_surfaces(self, running_vm, running_vmi, warning_event):
        hints = _generate_hypotheses(running_vm, running_vmi, [warning_event], [], [])
        joined = " ".join(hints)
        assert "FailedScheduling" in joined
        assert "insufficient memory" in joined


class TestGenerateHypothesesBadConditions:
    def test_ready_false_emits_condition_hint(self, broken_vm):
        hints = _generate_hypotheses(broken_vm, None, [], [], [])
        assert any("Condition Ready=False" in h for h in hints)
        assert any("PodNotExists" in h for h in hints)


class TestHypothesesCombined:
    def test_multiple_signals_all_fire(self, broken_vm, warning_event):
        related_dvs = [
            {"name": "broken-vm-disk0", "namespace": "default", "phase": "ImportInProgress", "progress": "12.5%"},
        ]
        related_m = [
            {
                "name": "broken-vm-mig",
                "phase": "Failed",
                "failureReason": "node not ready",
                "creationTime": "2026-04-30T09:00:00Z",
            },
        ]
        hints = _generate_hypotheses(broken_vm, None, [warning_event], related_dvs, related_m)
        joined = " ".join(hints)
        # We should see hints for each signal class
        assert "no active VirtualMachineInstance" in joined
        assert "DataVolumes" in joined
        assert "live migration" in joined
        assert "Warning event" in joined
        assert "Ready=False" in joined
