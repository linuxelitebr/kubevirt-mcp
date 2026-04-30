"""Unit tests for the Tier 2 lifecycle helpers on KubeVirtClient.

These don't hit the cluster. They verify the right HTTP path / body is
constructed for each subresource call, and that migrate_vmi creates a
correctly-shaped VirtualMachineInstanceMigration.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException

from kubevirt_mcp.client import KubeVirtClient


@pytest.fixture
def fake_client() -> KubeVirtClient:
    """Build a KubeVirtClient with patched-out kubeconfig loading + mocked APIs."""
    with patch(
        "kubevirt_mcp.client.config.load_incluster_config",
        side_effect=ConfigException("not in cluster"),
    ):
        with patch("kubevirt_mcp.client.config.load_kube_config"):
            with patch("kubevirt_mcp.client.client.CustomObjectsApi") as custom_cls:
                with patch("kubevirt_mcp.client.client.CoreV1Api"):
                    c = KubeVirtClient()
                    c.custom = custom_cls.return_value
                    c.custom.api_client = MagicMock()
                    return c


class TestStartVM:
    def test_calls_subresource_with_correct_path(self, fake_client):
        fake_client.start_vm("my-vm", "default")

        fake_client.custom.api_client.call_api.assert_called_once()
        call_args = fake_client.custom.api_client.call_api.call_args
        path = call_args.args[0]
        method = call_args.args[1]
        assert path == "/apis/subresources.kubevirt.io/v1/namespaces/default/virtualmachines/my-vm/start"
        assert method == "PUT"


class TestStopVM:
    def test_default_stop_has_no_body(self, fake_client):
        fake_client.stop_vm("my-vm", "default")
        kwargs = fake_client.custom.api_client.call_api.call_args.kwargs
        assert kwargs["body"] == {}

    def test_force_stop_sets_grace_period_zero(self, fake_client):
        fake_client.stop_vm("my-vm", "default", force=True)
        kwargs = fake_client.custom.api_client.call_api.call_args.kwargs
        assert kwargs["body"] == {"gracePeriod": 0}

    def test_custom_grace_period(self, fake_client):
        fake_client.stop_vm("my-vm", "default", grace_period_seconds=120)
        kwargs = fake_client.custom.api_client.call_api.call_args.kwargs
        assert kwargs["body"] == {"gracePeriod": 120}

    def test_force_overrides_custom_grace(self, fake_client):
        fake_client.stop_vm("my-vm", "default", force=True, grace_period_seconds=120)
        kwargs = fake_client.custom.api_client.call_api.call_args.kwargs
        # force=True wins
        assert kwargs["body"] == {"gracePeriod": 0}


class TestRestartVM:
    def test_calls_restart_subresource(self, fake_client):
        fake_client.restart_vm("my-vm", "ns1")
        path = fake_client.custom.api_client.call_api.call_args.args[0]
        assert path.endswith("/virtualmachines/my-vm/restart")


class TestMigrateVMI:
    def test_creates_migration_with_correct_shape(self, fake_client):
        fake_client.custom.create_namespaced_custom_object.return_value = {
            "metadata": {"name": "my-vm-migration-abc", "creationTimestamp": "2026-04-30T20:00:00Z"},
        }

        result = fake_client.migrate_vmi("my-vm", "default")

        fake_client.custom.create_namespaced_custom_object.assert_called_once()
        kwargs = fake_client.custom.create_namespaced_custom_object.call_args.kwargs
        assert kwargs["group"] == "kubevirt.io"
        assert kwargs["version"] == "v1"
        assert kwargs["namespace"] == "default"
        assert kwargs["plural"] == "virtualmachineinstancemigrations"

        body = kwargs["body"]
        assert body["kind"] == "VirtualMachineInstanceMigration"
        assert body["spec"]["vmiName"] == "my-vm"
        assert body["metadata"]["generateName"].startswith("my-vm-migration-")

        assert result["metadata"]["name"] == "my-vm-migration-abc"

    def test_migration_failure_wraps_api_exception(self, fake_client):
        fake_client.custom.create_namespaced_custom_object.side_effect = ApiException(
            status=409, reason="Conflict"
        )
        with pytest.raises(RuntimeError, match="Failed to start migration"):
            fake_client.migrate_vmi("my-vm", "default")


class TestSubresourceErrorHandling:
    def test_api_exception_wrapped(self, fake_client):
        fake_client.custom.api_client.call_api.side_effect = ApiException(
            status=404, reason="Not Found"
        )
        with pytest.raises(RuntimeError, match="Subresource 'start' failed"):
            fake_client.start_vm("ghost-vm", "default")


class TestSubresourceCallApiSignature:
    """Regression: kubernetes>=33 renamed `response_types_map` to `response_type`.

    If somebody reintroduces the old kwarg name, every Tier 2 subresource
    call breaks at runtime with `TypeError: call_api() got an unexpected
    keyword argument 'response_types_map'`. These tests guard the wire.
    """

    def test_uses_response_type_not_response_types_map(self, fake_client):
        fake_client.start_vm("any-vm", "default")
        kwargs = fake_client.custom.api_client.call_api.call_args.kwargs
        assert "response_type" in kwargs, "must use modern kwarg name"
        assert "response_types_map" not in kwargs, "old kwarg removed in kubernetes>=33"

    def test_response_type_is_none_for_subresource_with_empty_body(self, fake_client):
        fake_client.restart_vm("any-vm", "default")
        kwargs = fake_client.custom.api_client.call_api.call_args.kwargs
        # Subresource returns 202 with empty body. None is the right hint.
        assert kwargs["response_type"] is None

    def test_accept_header_is_wildcard(self, fake_client):
        """Regression: KubeVirt subresources reply 202 with empty body and have
        no JSON representation, so Accept: application/json gets 406.
        Must be Accept: */*."""
        fake_client.start_vm("any-vm", "default")
        kwargs = fake_client.custom.api_client.call_api.call_args.kwargs
        assert kwargs["header_params"]["Accept"] == "*/*"
