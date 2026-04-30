"""Shared pytest fixtures: realistic VM/VMI/DV/Migration payloads."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def running_vm() -> dict[str, Any]:
    """Healthy running VM (Linux, instanceType-based)."""
    return {
        "metadata": {
            "name": "centos-stream9-test",
            "namespace": "default",
            "creationTimestamp": "2026-04-20T10:00:00Z",
        },
        "spec": {
            "runStrategy": "Always",
            "instancetype": {"name": "u1.medium"},
            "preference": {"name": "centos.stream9"},
            "template": {
                "spec": {
                    "domain": {
                        "cpu": {"cores": 2, "sockets": 1, "threads": 1},
                        "memory": {"guest": "2Gi"},
                        "resources": {"requests": {"memory": "2Gi"}},
                    }
                }
            },
        },
        "status": {
            "printableStatus": "Running",
            "ready": True,
            "conditions": [
                {"type": "Ready", "status": "True", "lastTransitionTime": "2026-04-20T10:01:00Z"},
                {"type": "DataVolumesReady", "status": "True", "reason": "AllDVsReady"},
                {"type": "LiveMigratable", "status": "True"},
                {"type": "AgentConnected", "status": "True"},
            ],
        },
    }


@pytest.fixture
def stopped_vm() -> dict[str, Any]:
    """VM intentionally stopped via runStrategy=Halted."""
    return {
        "metadata": {
            "name": "fedora-stopped",
            "namespace": "default",
            "creationTimestamp": "2026-04-20T10:00:00Z",
        },
        "spec": {
            "runStrategy": "Halted",
            "running": False,
            "template": {"spec": {"domain": {}}},
        },
        "status": {
            "printableStatus": "Stopped",
            "ready": False,
            "conditions": [],
        },
    }


@pytest.fixture
def broken_vm() -> dict[str, Any]:
    """VM that should be running but Ready=False."""
    return {
        "metadata": {
            "name": "broken-vm",
            "namespace": "default",
            "creationTimestamp": "2026-04-20T10:00:00Z",
        },
        "spec": {
            "runStrategy": "Always",
            "template": {"spec": {"domain": {}}},
        },
        "status": {
            "printableStatus": "ErrorUnschedulable",
            "ready": False,
            "conditions": [
                {
                    "type": "Ready",
                    "status": "False",
                    "reason": "PodNotExists",
                    "message": "virt-launcher pod has not yet been scheduled",
                },
            ],
        },
    }


@pytest.fixture
def running_vmi() -> dict[str, Any]:
    return {
        "metadata": {"name": "centos-stream9-test", "namespace": "default"},
        "status": {
            "phase": "Running",
            "nodeName": "worker-01",
            "interfaces": [
                {"name": "default", "ipAddress": "10.0.0.42", "mac": "52:54:00:00:00:01"},
            ],
            "guestOSInfo": {"name": "CentOS Stream", "version": "9"},
        },
    }


@pytest.fixture
def succeeded_dv() -> dict[str, Any]:
    return {
        "metadata": {"name": "centos-stream9-test", "namespace": "default"},
        "spec": {"source": {"pvc": {"name": "boot-source"}}},
        "status": {"phase": "Succeeded", "progress": "100.0%"},
    }


@pytest.fixture
def failing_dv() -> dict[str, Any]:
    return {
        "metadata": {"name": "broken-vm-disk0", "namespace": "default"},
        "spec": {"source": {"http": {"url": "https://example.com/iso"}}},
        "status": {"phase": "ImportInProgress", "progress": "12.5%"},
    }


@pytest.fixture
def failed_migration() -> dict[str, Any]:
    return {
        "metadata": {
            "name": "centos-stream9-test-mig-abc",
            "namespace": "default",
            "creationTimestamp": "2026-04-29T15:00:00Z",
        },
        "spec": {"vmiName": "centos-stream9-test"},
        "status": {
            "phase": "Failed",
            "migrationState": {
                "sourceNode": "worker-01",
                "targetNode": "worker-02",
                "failed": True,
                "failureReason": "Cannot recv data: Connection reset by peer",
                "completed": True,
            },
        },
    }


@pytest.fixture
def succeeded_migration() -> dict[str, Any]:
    return {
        "metadata": {
            "name": "centos-stream9-test-mig-ok",
            "namespace": "default",
            "creationTimestamp": "2026-04-28T15:00:00Z",
        },
        "spec": {"vmiName": "centos-stream9-test"},
        "status": {
            "phase": "Succeeded",
            "migrationState": {
                "sourceNode": "worker-01",
                "targetNode": "worker-02",
                "completed": True,
                "failed": False,
            },
        },
    }


@pytest.fixture
def warning_event() -> dict[str, Any]:
    return {
        "type": "Warning",
        "reason": "FailedScheduling",
        "message": "0/3 nodes are available: insufficient memory",
        "firstTimestamp": "2026-04-30T10:00:00Z",
        "lastTimestamp": "2026-04-30T10:05:00Z",
        "involvedObject": {"kind": "VirtualMachine", "name": "broken-vm"},
    }


@pytest.fixture
def snapshot_ready() -> dict[str, Any]:
    return {
        "metadata": {"name": "snap-1", "namespace": "default"},
        "spec": {"source": {"name": "centos-stream9-test"}},
        "status": {
            "phase": "Succeeded",
            "readyToUse": True,
            "indications": [],
            "error": None,
        },
    }
