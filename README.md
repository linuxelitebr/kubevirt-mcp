# kubevirt-mcp

An MCP server that lets your AI assistant poke around a KubeVirt or
OpenShift Virtualization cluster and do the boring parts for you. List
VMs, figure out why one refuses to boot, start, stop, restart,
live-migrate. From inside Claude Desktop, Cursor, or whichever MCP
client you happen to be running this week.

You know the routine: a VM misbehaves, and three minutes later you're
five `oc` commands deep, copy-pasting YAML into a chat window like
it's 2008. This skips that part. The agent calls one tool, gets back a
coherent payload (spec + status + events + DataVolumes + recent
migrations + a few heuristic hints), and can actually answer your
question instead of asking for more output.

## Status

Alpha, but it works. Tested against:

- **OpenShift 4.20.19** with **OpenShift Virtualization 4.20.11** (HCO)
- **Kubernetes v1.33.9** (whatever the OCP server reports)
- **kubernetes Python client 35.0.0** on Python 3.13
- Should work on upstream KubeVirt on plain Kubernetes 1.29 or newer.
  The KubeVirt API surface we depend on is stable across these.

If it doesn't work on your cluster, congratulations: you have a bug
report to file.

## What it ships

### Tier 1: read-only

The boring, safe ones.

| Tool | What it does |
| --- | --- |
| `list_vms` | List VirtualMachines with a compact status. |
| `get_vm` | Full spec/status of one VM. Plus its VMI if it's running. |
| `list_vmis` | Live VMIs with node, IP, guest OS info. |
| `virt_cluster_health` | Counts of VMs by state, failed migrations, unfinished DataVolumes. The dashboard you wish the console gave you. |
| `get_vm_events` | Recent Kubernetes Events for a specific VM. |
| `list_vm_snapshots` | VirtualMachineSnapshots with phase and readyToUse. |
| `list_live_migrations` | VirtualMachineInstanceMigrations. Optionally only the active ones, in case you have a long history of failures (we believe you). |
| `list_data_volumes` | CDI DataVolumes with import phase and progress. |
| `diagnose_vm` | The one to call when a VM is on fire. Grabs spec + status + events + DVs + migrations in one shot and bolts on heuristic hints so the agent doesn't have to make 17 tool calls. |

### Tier 2: lifecycle (mutating)

The fun ones. These actually change cluster state. Your MCP client is
supposed to ask the user before invoking them. If yours doesn't, that's
a feature gap on the client side, not here. We don't add extra
confirmation theater on top of Kubernetes. Whatever your kubeconfig can
do, these tools can do.

| Tool | What it does |
| --- | --- |
| `start_vm` | Starts a stopped VM. Ground-breaking. |
| `stop_vm` | Graceful shutdown. `force=true` for hard power-off (gracePeriod=0), the digital equivalent of yanking the power cable. Filesystems hate this trick. |
| `restart_vm` | Reboot a running VM. |
| `migrate_vm` | Triggers a live migration. Useful for planned maintenance, or for finding out the hard way that your storage doesn't actually support it. |

All four call the standard KubeVirt subresource endpoints
(`/apis/subresources.kubevirt.io/v1/.../start|stop|restart`) or create
a `VirtualMachineInstanceMigration`, exactly the way `virtctl` does.

## Install

Needs Python 3.11+. We don't test on 3.10. We don't plan to.

```bash
pip install git+https://github.com/linuxelitebr/kubevirt-mcp.git
```

For local hacking:

```bash
git clone git@github.com:linuxelitebr/kubevirt-mcp.git
cd kubevirt-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The server reads your kubeconfig the same way `oc` and `kubectl` do
(`KUBECONFIG` env var, or `~/.kube/config`). Whatever cluster you are
logged into is the cluster the agent will see. Logging into the wrong
cluster and then asking the AI to "fix things" is a creative way to
have a bad day.

## Wire it into Claude Desktop

Edit your config file
(`~/Library/Application Support/Claude/claude_desktop_config.json` on
macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows) and
add:

```json
{
  "mcpServers": {
    "kubevirt": {
      "command": "kubevirt-mcp",
      "env": {
        "KUBECONFIG": "/Users/you/.kube/config"
      }
    }
  }
}
```

Restart Claude Desktop. The `kubevirt` tools will show up in the tool
picker. There are working examples in [`examples/`](./examples/),
including a variant that points at a project-local virtualenv for when
you don't want yet another global pip install in your $PATH.

## Things to ask the agent

After it's wired up, try these:

- "What is the overall health of my virtualization cluster?"
- "List all VMs in namespace `clusters-mycluster`."
- "The VM `centos-stream9-foo` in namespace `default` is not booting. Why?"
  (this is what `diagnose_vm` exists for)
- "Are there any failed live migrations in the last day? If so, why?"
- "Show me DataVolumes that haven't finished importing."
- "Migrate `fedora-bar` to another node." (Tier 2: client should ask
  for confirmation before calling `migrate_vm`. If yours just does
  it, that's a separate problem.)

## Troubleshooting

A few real-world gotchas that bit us during setup:

### macOS sandbox blocks `~/Documents/`

Claude Desktop is a sandboxed app. macOS TCC will silently deny it access to
files under `~/Documents/`, `~/Desktop/` and `~/Downloads/`. If you install
the package into a venv at `~/Documents/git/kubevirt-mcp/.venv/`, the server
will fail at startup with:

```
PermissionError: [Errno 1] Operation not permitted: '.../pyvenv.cfg'
```

The fix is to put the venv outside the protected directories. We use
`~/.local/share/kubevirt-mcp/venv/`. `pipx` does the same thing automatically
in `~/.local/pipx/venvs/`. Either works.

This trips up everyone the first time. It also doesn't reproduce when you
run the binary by hand from the terminal, because your `Terminal.app`
already has Full Disk Access, but the sandboxed Claude Desktop process does
not.

### Claude Desktop refuses to actually quit

Editing `claude_desktop_config.json` requires a full Quit, not a window
close. Sometimes `Cmd+Q` plays dead and the daemon keeps running:

```bash
pgrep -i claude
# 38200    <-- still alive
kill -9 38200
pgrep -i claude
# (silence)
```

After that, relaunch the app and the new config takes effect. If you skip
this step you'll spend twenty minutes wondering why the config you just
edited isn't being read. Ask us how we know.

### Where to find the logs

The MCP server logs end up under:

```
~/Library/Logs/Claude/mcp-server-kubevirt.log
~/Library/Logs/Claude/mcp.log
```

`tail -50` on the first one tells you exactly why the server crashed at
startup, including stack traces from Python. Look here before opening a
GitHub issue. Probably saves both of us time.

## Safety notes

- Tier 1 calls only `list` and `get`. It cannot break anything. The
  worst it can do is be slow.
- Tier 2 mutates. The MCP client is in charge of asking for approval.
  Pointing this at a production cluster from an unattended agent is
  allowed, but you'll be doing it without our blessing.
- Auth is your kubeconfig's RBAC. We don't bring our own. Use a
  least-privilege ServiceAccount if the agent runs unsupervised.
- No secrets, tokens, or pod environment variables are read or
  returned. Pod and Secret data are out of scope, on purpose.

## License

Apache-2.0. See [LICENSE](./LICENSE).

---

This README is the short version. The long version, with screenshots,
real-cluster demos, and the two bugs caught the day it shipped, lives
over at [linuxelite.com.br/blog/kubevirt-mcp-claude-desktop](https://linuxelite.com.br/blog/kubevirt-mcp-claude-desktop/).
