# Safety and operational boundaries

Use disposable VMs first. Take a provider snapshot or retain console access
before applying to a host with valuable state. This release has no rollback
engine. Read the plan and the applicability reasons before enforcement.

Preflight requires Ubuntu 24.04 or Rocky 9, an operational profile, successful
privilege escalation, a working connection, a readable package database and at
least 128 MiB free on the filesystem containing `/etc`. It refuses shared-kernel
containers. It records kernel, architecture, AppArmor/SELinux facts and the Ubuntu
reboot marker. Rocky pending-reboot state is explicitly unassessed; no package
update is performed, so HardenOps does not introduce a package reboot requirement.

`network.routing: false` is the generic-server default. Active IPv4 forwarding
contradicting that declaration stops enforcement. Declare routing as true for a
router; the six selected IPv4 server controls then become NOT_APPLICABLE.
`network.ipv6_required: true` is the default. R13 becomes a manual boot and runtime
change only when IPv6 is explicitly unused; v0.1 never disables it automatically.

No accounts or packages are deleted, no setuid bits are removed, and no arbitrary
world-writable tree is remediated. The filesystem audits require a human to assess
ownership and workload intent. Repository names do not establish trust. Update
cadence and local session locking also need operational decisions.

No SSH, sudo, firewall, SELinux or AppArmor policy is changed. Sysctl and sensitive
file changes are narrow and feature-tested. Yama can restrict debugging;
performance and kernel pointer restrictions can affect diagnostic tools. These
tradeoffs appear in the source catalogue and plan. Unknown or missing interfaces
are UNSUPPORTED, not PASS. Missing or symlinked sensitive files are not created
or followed. Owned sysctl symlinks are refused.

Owned sysctl storage is handled by a streamed standard-library Python guard.
It traverses root-owned, non-writable directories using no-follow directory
descriptors, checks metadata and content on the same file descriptor, and refuses
unsafe current files as well as unsafe legacy files. Missing or changed inspection
preconditions require a new plan; unsafe parents are never repaired automatically.
The guard publishes exactly one approved assignment atomically, with restrictive
metadata already set, then activates only the explicit key/value. It never passes
guest-supplied file content to an immediate `sysctl -p` reload.

This is not an atomic multi-resource transaction. Snapshot comparisons detect
stale observations but cannot serialize hostile root or other privileged
configuration writers. Run one configuration writer at a time. A later failure
can leave safe persistence installed or a key activated; review fresh evidence
and replan rather than automatically rolling back or weakening state.

When the vendor Apport service is
present, the privileged core-dump control installs a validated, narrowly scoped
drop-in through the same guarded storage and reloads systemd metadata through its handler. It does not restart or
disable Apport; the drop-in reapplies only the owned sysctl file when Apport starts.
That startup reload relies on the root-owned canonical file and trusted parents
remaining protected; changes by root and full boot precedence remain outside this
guarantee. The Python helper is streamed, not persistently installed on the guest.
Permission changes intersect existing bits with the maximum allowed mode,
preserving a stricter mode.

Explicit exceptions can be supplied in `hardenops_config.disabled_controls`.
They produce NOT_APPLICABLE with an operator-disabled reason, never PASS. Keep
the complete configuration mapping in a reviewed variables file and pass it
with Ansible `-e @path/to/lab-policy.yml`. The default policy lives in
`ansible/group_vars/all.yml`; that file is loaded explicitly by each playbook.

Reports include host and account metadata and filesystem paths. Keep the ignored
`artifacts/` directory private. Evidence files are written with restrictive
permissions on the controller. They contain no shadow contents or credentials.
