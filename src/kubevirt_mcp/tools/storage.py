"""Storage-related MCP tools (DataVolumes / CDI).

DataVolumes wrap PVCs with import/clone/upload semantics for VM disks.
When a VM mysteriously refuses to start, the answer is often "the disk
hasn't finished importing yet" and nobody told you.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..client import get_client


def _summarize_dv(dv: dict[str, Any]) -> dict[str, Any]:
    metadata = dv.get("metadata", {})
    spec = dv.get("spec", {})
    status = dv.get("status", {})
    pvc = (spec.get("pvc") or {}).get("resources", {}).get("requests", {})
    storage = (spec.get("storage") or {}).get("resources", {}).get("requests", {})

    return {
        "name": metadata.get("name"),
        "namespace": metadata.get("namespace"),
        "phase": status.get("phase"),
        "progress": status.get("progress"),
        "size": pvc.get("storage") or storage.get("storage"),
        "source": next(iter((spec.get("source") or {}).keys()), None),
        "creationTime": metadata.get("creationTimestamp"),
        "restartCount": status.get("restartCount", 0),
    }


def register(mcp: FastMCP) -> None:
    """Register storage tools."""

    @mcp.tool()
    def list_data_volumes(namespace: str | None = None) -> list[dict[str, Any]]:
        """List DataVolumes (CDI) on the cluster.

        Shows phase, progress, and the source kind (HTTP, registry,
        PVC, blank, upload, etc.). The two states you usually care
        about: Succeeded (good) and anything else (talk to the user).

        Args:
            namespace: Optional namespace filter.
        """
        client = get_client()
        dvs = client.list_data_volumes(namespace=namespace)
        return [_summarize_dv(dv) for dv in dvs]
