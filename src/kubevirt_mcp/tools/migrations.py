"""Live Migration MCP tools.

Live migration is one of those features that is amazing when it works
and a special kind of disaster when it doesn't. Inspect history here.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client


def _summarize_migration(m: dict[str, Any]) -> dict[str, Any]:
    metadata = m.get("metadata", {})
    spec = m.get("spec", {})
    status = m.get("status", {})
    migration_state = status.get("migrationState", {}) or {}

    return {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "vmiName": spec.get("vmiName"),
        "phase": status.get("phase"),
        "sourceNode": migration_state.get("sourceNode"),
        "targetNode": migration_state.get("targetNode"),
        "startTimestamp": migration_state.get("startTimestamp"),
        "endTimestamp": migration_state.get("endTimestamp"),
        "completed": migration_state.get("completed"),
        "failed": migration_state.get("failed"),
        "failureReason": migration_state.get("failureReason"),
        "creationTime": metadata.get("creationTimestamp"),
    }


def register(mcp: FastMCP) -> None:
    """Register migration tools."""

    @mcp.tool()
    def list_live_migrations(
        namespace: str | None = None,
        only_active: bool = False,
    ) -> list[dict[str, Any]]:
        """List VirtualMachineInstanceMigration resources.

        Pending, running, or recently finished, with whatever phase
        they ended up in. Source and target node included if the
        migration controller got that far.

        Args:
            namespace: Optional namespace filter.
            only_active: If True, only migrations still in flight
                (Pending, Scheduling, Scheduled, PreparingTarget,
                TargetReady, Running). Handy when you want to know
                whether a node drain is actually making progress
                instead of staring at the controller.
        """
        client = get_client()
        migrations = client.list_migrations(namespace=namespace)

        active_phases = {
            "Pending",
            "Scheduling",
            "Scheduled",
            "PreparingTarget",
            "TargetReady",
            "Running",
        }
        if only_active:
            migrations = [
                m for m in migrations if m.get("status", {}).get("phase") in active_phases
            ]
        return [_summarize_migration(m) for m in migrations]
