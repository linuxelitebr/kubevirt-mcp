"""Lifecycle MCP tools (Tier 2): start, stop, restart, migrate.

These mutate the cluster. The MCP client is supposed to ask the user
before calling them. The server itself adds no extra confirmation
theater. Whatever the kubeconfig is allowed to do, these tools will
do, cheerfully and without follow-up questions.

If you point this at production from an unattended agent, that's a
choice and we respect it.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client


def register(mcp: FastMCP) -> None:
    """Register lifecycle tools."""

    @mcp.tool()
    def start_vm(name: str, namespace: str) -> dict[str, Any]:
        """Start a stopped VirtualMachine.

        PUT against /apis/subresources.kubevirt.io/v1/.../start, which
        is what `virtctl start` does under the hood. The controller
        builds a VMI and the kubelet schedules the virt-launcher pod.
        None of that happens before this call returns.

        Args:
            name: VM name.
            namespace: VM namespace.

        Returns an acknowledgment dict. Actual reaching-Running is
        async. Poll list_vmis or get_vm if you care, or trust the
        process and move on.
        """
        client = get_client()
        client.start_vm(name=name, namespace=namespace)
        return {
            "action": "start",
            "name": name,
            "namespace": namespace,
            "result": "accepted",
            "note": "VM start is asynchronous. Poll list_vmis or get_vm to see when it reaches Running.",
        }

    @mcp.tool()
    def stop_vm(
        name: str,
        namespace: str,
        force: bool = False,
        grace_period_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Stop a running VirtualMachine.

        Default: ACPI shutdown. The guest gets a chance to flush its
        buffers and close down properly.

        force=True: gracePeriod=0, the digital equivalent of yanking
        the power cable. Convenient when the guest is wedged. Less
        convenient if the next thing it does is fsck on boot.

        Args:
            name: VM name.
            namespace: VM namespace.
            force: If True, hard power-off (gracePeriod=0).
            grace_period_seconds: Custom grace period in seconds.
                Ignored if force=True, since force already won.
        """
        client = get_client()
        client.stop_vm(
            name=name,
            namespace=namespace,
            force=force,
            grace_period_seconds=grace_period_seconds,
        )
        return {
            "action": "stop",
            "name": name,
            "namespace": namespace,
            "force": force,
            "gracePeriodSeconds": 0 if force else grace_period_seconds,
            "result": "accepted",
        }

    @mcp.tool()
    def restart_vm(name: str, namespace: str) -> dict[str, Any]:
        """Restart a VirtualMachine (graceful shutdown then start).

        Same idea as `virtctl restart`. The VM resource keeps its
        name; the VMI underneath is replaced. There will be downtime,
        no matter how nicely you ask.
        """
        client = get_client()
        client.restart_vm(name=name, namespace=namespace)
        return {
            "action": "restart",
            "name": name,
            "namespace": namespace,
            "result": "accepted",
            "note": "Restart is asynchronous. The VMI will be recreated; expect a brief downtime.",
        }

    @mcp.tool()
    def migrate_vm(name: str, namespace: str) -> dict[str, Any]:
        """Trigger a live migration of a running VM to another node.

        Creates a VirtualMachineInstanceMigration pointing at the VMI
        with the given name. The migration controller picks a target,
        does its thing, and the VMI ends up somewhere else. No
        downtime, in theory. In practice, it depends on whether your
        storage actually cooperates.

        Good uses: node maintenance, balancing, or proving to yourself
        that live migration works in your environment before you bet
        anything important on it.

        Args:
            name: VMI name (same as the VM name, in practice).
            namespace: Namespace of the VMI.

        Returns the created VirtualMachineInstanceMigration's metadata.
        Cross-reference with list_live_migrations to track progress.
        """
        client = get_client()
        result = client.migrate_vmi(name=name, namespace=namespace)
        meta = result.get("metadata", {})
        return {
            "action": "migrate",
            "name": name,
            "namespace": namespace,
            "migrationName": meta.get("name"),
            "creationTimestamp": meta.get("creationTimestamp"),
            "result": "accepted",
            "note": "Migration runs asynchronously. Poll list_live_migrations to track phase.",
        }
