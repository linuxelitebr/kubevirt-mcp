# Sample prompts for kubevirt-mcp

Drop these into Claude Desktop, Cursor, or whichever MCP client you have
wired up, once your kubeconfig is pointing at a cluster that actually has
KubeVirt or OpenShift Virtualization installed.

## Health check

> What's the overall health of my virtualization cluster? How many VMs
> are running, how many are stopped, are any in error state?

Triggers: `virt_cluster_health`

## Inventory

> List every VM in the `clusters-mycluster` namespace and summarize
> their state.

Triggers: `list_vms(namespace="clusters-mycluster")`

## Why is this VM broken

> The VM `centos-stream9-teal-warbler-26` in namespace
> `clusters-mycluster` won't start. Tell me what's wrong.

Triggers: `diagnose_vm`. Returns spec, status, conditions, recent events,
related DataVolumes, recent migrations and a few heuristic hints in one
shot. The agent should reason over those signals, not chain individual
tool calls one at a time like it's billing by the API request.

## Storage import problems

> Are there DataVolumes stuck importing? Which ones, and where were
> they pulling from?

Triggers: `list_data_volumes`

## Live migration audit

> Show me every live migration in the last day. Did any fail? If so,
> tell me why.

Triggers: `list_live_migrations`. The agent will probably follow up
with `diagnose_vm` for any VMI whose migrations look bad.

## Snapshot audit

> Are there VirtualMachineSnapshots that errored out or are still
> pending?

Triggers: `list_vm_snapshots`

## Lifecycle (Tier 2)

> Migrate `fedora-black-butterfly-48` to another node.

Triggers: `migrate_vm`. Your MCP client should ask for confirmation
before sending this one. If it doesn't, file a bug against the client.

> Stop the win2k22 VM, gracefully.

Triggers: `stop_vm` with the default grace period.

> The centos VM is wedged, force a power-off.

Triggers: `stop_vm(force=True)`. Filesystems hate this trick. Only do
it when the guest has stopped responding.
