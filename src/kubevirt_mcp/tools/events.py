"""Event-related MCP tools.

Kubernetes Events are where things go to die quietly, then surface
just in time to ruin your day. Surface them on demand instead.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client


def register(mcp: FastMCP) -> None:
    """Register event tools."""

    @mcp.tool()
    def get_vm_events(
        name: str,
        namespace: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return recent Kubernetes Events for a specific VM.

        Pulls events with involvedObject.kind=VirtualMachine and
        =VirtualMachineInstance for the given name. Useful when you
        want to know why a VM didn't start, why a migration gave up,
        or what the controller is grumbling about.

        Args:
            name: VM name.
            namespace: VM namespace.
            limit: How many events to return (default 20, newest
                first). Bumping this past 50 rarely tells you more
                than the first 20 already did.
        """
        client = get_client()
        events = client.list_events_for_vm(name=name, namespace=namespace)
        return events[:limit]
