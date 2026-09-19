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

Configuration is replaced through Ansible modules. The sysctl module activates
each owned file immediately; delaying these changes in a handler would separate
the runtime state from the persisted decision. No reload service handler is
needed because this release edits no daemon configuration. Permission changes
intersect existing bits with the maximum allowed mode, preserving a stricter mode.

Explicit exceptions can be supplied in `hardenops_config.disabled_controls`.
They produce NOT_APPLICABLE with an operator-disabled reason, never PASS. Keep
the complete configuration mapping in a reviewed variables file and pass it
with Ansible `-e @path/to/lab-policy.yml`. The default policy lives in
`ansible/group_vars/all.yml`; that file is loaded explicitly by each playbook.

Reports include host and account metadata and filesystem paths. Keep the ignored
`artifacts/` directory private. Evidence files are written with restrictive
permissions on the controller. They contain no shadow contents or credentials.
