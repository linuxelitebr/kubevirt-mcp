"""Kubernetes / KubeVirt API client wrapper.

Loads the kubeconfig (in-cluster service account, ~/.kube/config, or
KUBECONFIG, in that order) and gives the rest of the codebase a
narrow set of methods over the KubeVirt CRDs.

Both the read helpers (Tier 1) and the lifecycle helpers (Tier 2)
inherit whatever RBAC the kubeconfig has. We do not pretend to be an
authorization layer. If the cluster says no, you get an exception.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

# KubeVirt API groups
KUBEVIRT_GROUP = "kubevirt.io"
KUBEVIRT_VERSION = "v1"
SNAPSHOT_GROUP = "snapshot.kubevirt.io"
SNAPSHOT_VERSION = "v1beta1"
MIGRATION_GROUP = "kubevirt.io"
CDI_GROUP = "cdi.kubevirt.io"
CDI_VERSION = "v1beta1"


class KubeVirtClient:
    """Thin wrapper around CustomObjectsApi for KubeVirt-related CRDs.

    "Thin" means: no caching, no retries, no fancy error normalization.
    Whatever the Kubernetes API said is what the caller gets.
    """

    def __init__(self) -> None:
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self.custom = client.CustomObjectsApi()
        self.core = client.CoreV1Api()

    # VirtualMachine

    def list_vms(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """List VirtualMachine resources. If namespace is None, lists across all namespaces."""
        try:
            if namespace:
                resp = self.custom.list_namespaced_custom_object(
                    group=KUBEVIRT_GROUP,
                    version=KUBEVIRT_VERSION,
                    namespace=namespace,
                    plural="virtualmachines",
                )
            else:
                resp = self.custom.list_cluster_custom_object(
                    group=KUBEVIRT_GROUP,
                    version=KUBEVIRT_VERSION,
                    plural="virtualmachines",
                )
            return resp.get("items", [])
        except ApiException as e:
            raise RuntimeError(f"Failed to list VMs: {e.reason}") from e

    def get_vm(self, name: str, namespace: str) -> dict[str, Any]:
        """Get a specific VirtualMachine by name."""
        try:
            return self.custom.get_namespaced_custom_object(
                group=KUBEVIRT_GROUP,
                version=KUBEVIRT_VERSION,
                namespace=namespace,
                plural="virtualmachines",
                name=name,
            )
        except ApiException as e:
            raise RuntimeError(f"Failed to get VM {namespace}/{name}: {e.reason}") from e

    # VirtualMachineInstance (running VM)

    def list_vmis(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """List VirtualMachineInstances (currently running VMs)."""
        try:
            if namespace:
                resp = self.custom.list_namespaced_custom_object(
                    group=KUBEVIRT_GROUP,
                    version=KUBEVIRT_VERSION,
                    namespace=namespace,
                    plural="virtualmachineinstances",
                )
            else:
                resp = self.custom.list_cluster_custom_object(
                    group=KUBEVIRT_GROUP,
                    version=KUBEVIRT_VERSION,
                    plural="virtualmachineinstances",
                )
            return resp.get("items", [])
        except ApiException as e:
            raise RuntimeError(f"Failed to list VMIs: {e.reason}") from e

    def get_vmi(self, name: str, namespace: str) -> dict[str, Any] | None:
        """Return the VMI for a VM, or None if it isn't running.

        We swallow 404 here on purpose. A stopped VM having no VMI is
        the boring case, not an error.
        """
        try:
            return self.custom.get_namespaced_custom_object(
                group=KUBEVIRT_GROUP,
                version=KUBEVIRT_VERSION,
                namespace=namespace,
                plural="virtualmachineinstances",
                name=name,
            )
        except ApiException as e:
            if e.status == 404:
                return None
            raise RuntimeError(f"Failed to get VMI {namespace}/{name}: {e.reason}") from e

    # Snapshots

    def list_vm_snapshots(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """List VirtualMachineSnapshot resources."""
        try:
            if namespace:
                resp = self.custom.list_namespaced_custom_object(
                    group=SNAPSHOT_GROUP,
                    version=SNAPSHOT_VERSION,
                    namespace=namespace,
                    plural="virtualmachinesnapshots",
                )
            else:
                resp = self.custom.list_cluster_custom_object(
                    group=SNAPSHOT_GROUP,
                    version=SNAPSHOT_VERSION,
                    plural="virtualmachinesnapshots",
                )
            return resp.get("items", [])
        except ApiException as e:
            raise RuntimeError(f"Failed to list VM snapshots: {e.reason}") from e

    # Live Migrations

    def list_migrations(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """List VirtualMachineInstanceMigration resources."""
        try:
            if namespace:
                resp = self.custom.list_namespaced_custom_object(
                    group=KUBEVIRT_GROUP,
                    version=KUBEVIRT_VERSION,
                    namespace=namespace,
                    plural="virtualmachineinstancemigrations",
                )
            else:
                resp = self.custom.list_cluster_custom_object(
                    group=KUBEVIRT_GROUP,
                    version=KUBEVIRT_VERSION,
                    plural="virtualmachineinstancemigrations",
                )
            return resp.get("items", [])
        except ApiException as e:
            raise RuntimeError(f"Failed to list migrations: {e.reason}") from e

    # DataVolumes

    def list_data_volumes(self, namespace: str | None = None) -> list[dict[str, Any]]:
        """List DataVolume resources (CDI)."""
        try:
            if namespace:
                resp = self.custom.list_namespaced_custom_object(
                    group=CDI_GROUP,
                    version=CDI_VERSION,
                    namespace=namespace,
                    plural="datavolumes",
                )
            else:
                resp = self.custom.list_cluster_custom_object(
                    group=CDI_GROUP,
                    version=CDI_VERSION,
                    plural="datavolumes",
                )
            return resp.get("items", [])
        except ApiException as e:
            raise RuntimeError(f"Failed to list DataVolumes: {e.reason}") from e

    # Lifecycle (Tier 2: mutating)

    def _vm_subresource(
        self,
        name: str,
        namespace: str,
        action: str,
        body: dict[str, Any] | None = None,
    ) -> None:
        """Hit a VM subresource (start/stop/restart) on the KubeVirt subresources API.

        These endpoints live under /apis/subresources.kubevirt.io/v1
        and answer with HTTP 202 + empty body, so we don't bother
        decoding a response. If it didn't blow up, it worked. Probably.
        """
        path = (
            f"/apis/subresources.kubevirt.io/{KUBEVIRT_VERSION}"
            f"/namespaces/{namespace}/virtualmachines/{name}/{action}"
        )
        try:
            self.custom.api_client.call_api(
                path,
                "PUT",
                path_params={},
                query_params=[],
                # Accept must be */*. The subresource returns 202 with no
                # body, so it has no representation to give back. Asking for
                # application/json gets a 406 Not Acceptable, which is
                # surprising and not documented anywhere obvious.
                header_params={
                    "Accept": "*/*",
                    "Content-Type": "application/json",
                },
                body=body if body is not None else {},
                post_params=[],
                files={},
                # kubernetes>=33 renamed `response_types_map` to `response_type`.
                # The subresource returns 202 with no body, so None is fine.
                response_type=None,
                auth_settings=["BearerToken"],
                _return_http_data_only=True,
                _preload_content=False,
            )
        except ApiException as e:
            raise RuntimeError(
                f"Subresource '{action}' failed for {namespace}/{name}: "
                f"{e.reason} (HTTP {e.status})"
            ) from e

    def start_vm(self, name: str, namespace: str) -> None:
        """Start a stopped VirtualMachine."""
        self._vm_subresource(name, namespace, "start")

    def stop_vm(
        self,
        name: str,
        namespace: str,
        force: bool = False,
        grace_period_seconds: int | None = None,
    ) -> None:
        """Stop a running VirtualMachine.

        Default: orderly ACPI shutdown. The guest gets to flush its
        buffers and call it a day.

        force=True: gracePeriod=0. Equivalent to yanking the power
        cable on a physical box. Use when the guest is unresponsive
        and you accept the consequences.
        """
        body: dict[str, Any] | None = None
        if force:
            body = {"gracePeriod": 0}
        elif grace_period_seconds is not None:
            body = {"gracePeriod": grace_period_seconds}
        self._vm_subresource(name, namespace, "stop", body)

    def restart_vm(self, name: str, namespace: str) -> None:
        """Restart a running VirtualMachine (graceful shutdown then start)."""
        self._vm_subresource(name, namespace, "restart")

    def migrate_vmi(self, name: str, namespace: str) -> dict[str, Any]:
        """Trigger a live migration by creating a VirtualMachineInstanceMigration.

        Returns the created migration object. The actual migration
        runs asynchronously, on the controller's schedule, not yours.
        Poll list_migrations() if you care about the outcome.
        """
        body = {
            "apiVersion": f"{KUBEVIRT_GROUP}/{KUBEVIRT_VERSION}",
            "kind": "VirtualMachineInstanceMigration",
            "metadata": {"generateName": f"{name}-migration-"},
            "spec": {"vmiName": name},
        }
        try:
            return self.custom.create_namespaced_custom_object(
                group=KUBEVIRT_GROUP,
                version=KUBEVIRT_VERSION,
                namespace=namespace,
                plural="virtualmachineinstancemigrations",
                body=body,
            )
        except ApiException as e:
            raise RuntimeError(
                f"Failed to start migration for {namespace}/{name}: {e.reason}"
            ) from e

    # Events

    def list_events_for_vm(self, name: str, namespace: str) -> list[dict[str, Any]]:
        """List Events for a VM, covering both VirtualMachine and VirtualMachineInstance kinds.

        The Kubernetes Events API doesn't let us OR field selectors, so
        we run two queries and merge. Sorted newest first, because
        that's the only ordering anyone actually wants.
        """
        try:
            field_selector = (
                f"involvedObject.name={name},"
                f"involvedObject.kind=VirtualMachine"
            )
            vm_events = self.core.list_namespaced_event(
                namespace=namespace, field_selector=field_selector
            ).items
            field_selector_vmi = (
                f"involvedObject.name={name},"
                f"involvedObject.kind=VirtualMachineInstance"
            )
            vmi_events = self.core.list_namespaced_event(
                namespace=namespace, field_selector=field_selector_vmi
            ).items
            all_events = list(vm_events) + list(vmi_events)
            # sort newest first
            all_events.sort(
                key=lambda e: e.last_timestamp or e.event_time or "",
                reverse=True,
            )
            return [_event_to_dict(e) for e in all_events]
        except ApiException as e:
            raise RuntimeError(
                f"Failed to list events for {namespace}/{name}: {e.reason}"
            ) from e


def _event_to_dict(event: Any) -> dict[str, Any]:
    """Convert a Kubernetes Event object to a plain dict."""
    return {
        "type": event.type,
        "reason": event.reason,
        "message": event.message,
        "count": event.count,
        "firstTimestamp": str(event.first_timestamp) if event.first_timestamp else None,
        "lastTimestamp": str(event.last_timestamp) if event.last_timestamp else None,
        "involvedObject": {
            "kind": event.involved_object.kind,
            "name": event.involved_object.name,
            "namespace": event.involved_object.namespace,
        },
    }


@lru_cache(maxsize=1)
def get_client() -> KubeVirtClient:
    """Return the singleton KubeVirtClient.

    One per process. Loading kubeconfig is not free and we'd rather
    not do it on every tool call.
    """
    return KubeVirtClient()
