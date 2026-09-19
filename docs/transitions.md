# Minimum baselines and transitions

A profile expresses minimum security requirements. Intermediary includes the
selected Minimal recommendations. Moving back to Minimal does not undo settings
already applied by Intermediary. Controls above the selected level become
NOT_APPLICABLE to that run, and their files and runtime state remain untouched.

For enumerated sysctls, `accepted_values` is ordered from the requested baseline
to explicitly supported stronger states. Planning compares both the live value
and the owned persistent value and retains the strongest accepted one. Unknown
values are not guessed to be secure just because they are numerically larger.
Permission changes remove excessive bits and do not add bits to already stricter
shadow files. These decisions are unit-tested.

The catalogue records `reversible`, `reboot_required` and `transition`. The
transition vocabulary supports `reversible`, `reboot_reversible`, `structural`,
`manual`, `destructive` and `non_reversible_runtime`. Metadata describes a property,
not an implemented rollback operation. Yama ptrace_scope=3 is an example of a
strong state that cannot be relaxed during the current boot and must be preserved.

For automated sysctls, the owned configuration is
`/etc/sysctl.d/90-hardenops-<control-id>.conf`. This gives each decision traceability
and allows a future transition planner to identify the previous desired state.
v0.1 does not delete these files on a profile downgrade or normalize unmanaged
configuration. A later boot loader, service, or sysctl configuration can override
them. Verification detects live mismatches but a complete boot-precedence analysis
and VM reboot cycle are future work.

There is no broad "reset" command. Any deliberate relaxation should be reviewed,
performed through a separate approved change and verified afterwards.
