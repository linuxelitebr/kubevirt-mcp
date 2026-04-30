"""Unit tests for the per-resource summarizer helpers.

These don't touch the cluster. They verify our compaction logic against
realistic-shaped payloads.
"""

from __future__ import annotations

from kubevirt_mcp.tools.migrations import _summarize_migration
from kubevirt_mcp.tools.snapshots import _summarize_snapshot
from kubevirt_mcp.tools.storage import _summarize_dv
from kubevirt_mcp.tools.vms import _summarize_vm, _summarize_vmi


class TestSummarizeVM:
    def test_extracts_basics(self, running_vm):
        s = _summarize_vm(running_vm)
        assert s["name"] == "centos-stream9-test"
        assert s["namespace"] == "default"
        assert s["status"] == "Running"
        assert s["ready"] is True
        assert s["runStrategy"] == "Always"
        assert s["instanceType"] == "u1.medium"
        assert s["preference"] == "centos.stream9"

    def test_cpu_topology(self, running_vm):
        s = _summarize_vm(running_vm)
        assert s["cpu"]["cores"] == 2
        assert s["cpu"]["sockets"] == 1
        assert s["cpu"]["threads"] == 1

    def test_memory_from_resources_or_guest(self, running_vm):
        s = _summarize_vm(running_vm)
        assert s["memory"] == "2Gi"

    def test_falls_back_when_no_printable_status(self):
        vm = {
            "metadata": {"name": "x", "namespace": "y"},
            "spec": {"template": {"spec": {"domain": {}}}},
            "status": {"ready": False},
        }
        s = _summarize_vm(vm)
        assert s["status"] == "Stopped"


class TestSummarizeVMI:
    def test_extracts_running_state(self, running_vmi):
        s = _summarize_vmi(running_vmi)
        assert s["phase"] == "Running"
        assert s["nodeName"] == "worker-01"
        assert s["ip"] == "10.0.0.42"
        assert s["guestOSInfo"]["name"] == "CentOS Stream"

    def test_no_interfaces_means_no_ip(self):
        vmi = {"metadata": {"name": "x", "namespace": "y"}, "status": {"phase": "Pending"}}
        s = _summarize_vmi(vmi)
        assert s["ip"] is None
        assert s["interfaces"] == []


class TestSummarizeDV:
    def test_succeeded(self, succeeded_dv):
        s = _summarize_dv(succeeded_dv)
        assert s["phase"] == "Succeeded"
        assert s["progress"] == "100.0%"
        assert s["source"] == "pvc"

    def test_in_progress(self, failing_dv):
        s = _summarize_dv(failing_dv)
        assert s["phase"] == "ImportInProgress"
        assert s["progress"] == "12.5%"
        assert s["source"] == "http"


class TestSummarizeMigration:
    def test_failed(self, failed_migration):
        s = _summarize_migration(failed_migration)
        assert s["phase"] == "Failed"
        assert s["failed"] is True
        assert "Connection reset" in s["failureReason"]
        assert s["sourceNode"] == "worker-01"
        assert s["targetNode"] == "worker-02"

    def test_succeeded(self, succeeded_migration):
        s = _summarize_migration(succeeded_migration)
        assert s["phase"] == "Succeeded"
        assert s["failed"] is False
        assert s["failureReason"] is None


class TestSummarizeSnapshot:
    def test_ready(self, snapshot_ready):
        s = _summarize_snapshot(snapshot_ready)
        assert s["phase"] == "Succeeded"
        assert s["readyToUse"] is True
        assert s["sourceVM"] == "centos-stream9-test"
        assert s["error"] is None
