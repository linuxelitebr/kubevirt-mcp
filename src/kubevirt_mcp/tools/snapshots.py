"""VM Snapshot MCP tools.

Snapshots: the safety net you remember to set up the day after you
needed it.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client


def _summarize_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    metadata = snap.get("metadata", {})
    spec = snap.get("spec", {})
    status = snap.get("status", {})
    source = spec.get("source", {})

    return {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "sourceVM": source.get("name"),
        "phase": status.get("phase"),
        "readyToUse": status.get("readyToUse"),
        "creationTime": metadata.get("creationTimestamp"),
        "indications": status.get("indications", []),
        "error": status.get("error"),
    }


def register(mcp: FastMCP) -> None:
    """Register snapshot tools."""

    @mcp.tool()
    def list_vm_snapshots(namespace: str | None = None) -> list[dict[str, Any]]:
        """List VirtualMachineSnapshots on the cluster.

        Args:
            namespace: Optional namespace filter. Leave it out to see
                every snapshot you have access to.

        Each entry has the source VM, phase, readyToUse flag, and
        whatever the snapshot controller decided to complain about
        in the error field. If readyToUse is False and there's no
        error, give it another minute. If there's an error, well.
        """
        client = get_client()
        snaps = client.list_vm_snapshots(namespace=namespace)
        return [_summarize_snapshot(s) for s in snaps]
