"""kubevirt-mcp server entry point.

Registers tools that let an AI agent (Claude Desktop, Cursor, whichever
client you have today) inspect and operate a KubeVirt or OpenShift
Virtualization cluster.

Two tiers:

  Tier 1 (read-only): list/get VMs, VMIs, snapshots, migrations, DVs,
                      events, plus a composite diagnose_vm. Boring and
                      safe.
  Tier 2 (lifecycle): start, stop, restart, migrate. The MCP client is
                      expected to ask the user before calling these.
                      The server doesn't second-guess the kubeconfig.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import diagnose, events, lifecycle, migrations, snapshots, storage, vms

mcp = FastMCP("kubevirt-mcp")

# Tier 1 tools (read-only).
vms.register(mcp)
events.register(mcp)
snapshots.register(mcp)
migrations.register(mcp)
storage.register(mcp)
diagnose.register(mcp)

# Tier 2 tools (mutating). Your client picks up the approval prompt.
lifecycle.register(mcp)


def main() -> None:
    """Run the MCP server over stdio. That's it. That's the function."""
    mcp.run()


if __name__ == "__main__":
    main()
