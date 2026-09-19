# Control catalogue and profile scope

The machine-readable policy is `controls/anssi_bp_028.yml`. It contains **28 atomic
controls from 14 BP-028 recommendations**, selected from the supplied version 2.0
guide. The catalogue is deliberately smaller than the guide and is the complete
declared coverage for HardenOps v0.1.

| Profile contribution | AUTOMATED | AUDIT_ONLY | MANUAL | OUT_OF_SCOPE_REFERENCE_REQUIRED | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Minimal recommendations | 0 | 4 | 2 | 1 | 7 |
| Intermediary recommendations | 19 | 0 | 2 | 0 | 21 |
| Cumulative Intermediary target | 19 | 4 | 4 | 1 | 28 |

There are **0 VERIFIED-only entries**. The automated entries have independent
verification, but their catalogue classification does not count as a successful
host observation. Enhanced and High have metadata-only profile files with
`implemented: false`; applying either must fail clearly.

Minimal is a useful account/filesystem evidence and operational-review baseline;
it makes no automatic configuration changes in this selected v0.1 subset. The
Intermediary target includes those seven entries and the twenty-one Intermediary
entries. All nineteen currently automated controls genuinely belong to
Intermediary recommendations; moving them into Minimal would misrepresent the
source.

## Reading a catalogue entry

Each entry carries:

- An immutable internal ID and a source document, recommendation and printed page.
- A source-verified level, technical domain, description and scope qualifications.
- Applicability predicates for OS family and, where needed, declared network use.
- An enforcement status, plus an implementation path for automated controls.
- A verification definition describing independent host-state observations.
- Reversibility, transition category, reboot implications and change risk.

For sysctls, `expected` is the baseline, while `accepted_values` lists that baseline
followed by explicitly recognised stronger states. `remediable_values` lists
recognised weaker states. A value outside both lists is not ranked using a generic
numeric comparison: it requires review. The sole range exception is the documented
SysRq mask, `remediable_range: [1, 511]`; its baseline is absolute keyboard disablement
with value 0.

Examples of safe preservation include keeping `ptrace_scope=2` or `3`, keeping
`perf_event_paranoid=4`, and leaving an existing 0600 shadow file stricter than the
0640 maximum. Ownership and group checks still apply. Values inferred from missing
or unreadable state are never treated as an observed pass.

File `max_mode` is a permission ceiling, not a request to add every listed bit.
The implementation removes excess bits by intersection and preserves a recognised
group. It refuses symlink targets and does not create missing authentication
databases. See [transitions.md](transitions.md) for profile changes.

## Capability, applicability and result are different

| Term | Meaning |
| --- | --- |
| AUTOMATED | A selected implementation can enforce an applicable, supported control. This is not a pass result. |
| VERIFIED | A control can be independently inspected without automated enforcement. The vocabulary is supported; none is assigned this capability in v0.1. |
| AUDIT_ONLY | Evidence supports a review; a human must interpret it. No automatic remediation or pass is implied. |
| MANUAL | The requirement needs operational judgement or a lifecycle action beyond current automation. |
| NOT_APPLICABLE | The selected control does not apply to the declared environment, or is explicitly excluded with a reason. It is not a failure. |
| UNSUPPORTED | The relevant state or feature cannot be safely handled by the implementation. It needs attention and is not a pass. |
| FUTURE | Reserved for a future implementation; not secretly active in lower profiles. |
| OUT_OF_SCOPE_REFERENCE_REQUIRED | A source delegates essential requirements to an unavailable publication. |
| PASS / FAIL | Results of a concrete independent state check. Only deterministic applicable checks produce them. |

The reports distinguish the catalogue capability from the observed result and
explain applicability. They do not publish an overall ANSSI compliance score.
Any count of passing checks must state its denominator, including skipped,
unsupported and review-only entries separately.

## Network and feature gates

The default workload is `generic_server` with `network.routing: false` and
`network.ipv6_required: true`. The six R12 controls are excluded when routing is
required. Each is one all/default parameter; the implementation does not claim
per-interface or full R12 coverage. Host networking must match the declared use.

R13 is NOT_APPLICABLE with the default IPv6-required declaration. Setting
`ipv6_required: false` makes it a MANUAL change requiring review of kernel boot
arguments, runtime settings, connectivity and reboot behaviour. It does not turn on
automatic IPv6 disablement. Missing sysctl interfaces, unsupported OS releases
and unknown policy values are reported explicitly rather than silently accepted.

## Scope exclusions

The project does not delete user accounts, guess service owners, remove arbitrary
packages, alter repository trust, strip setuid/setgid bits, rewrite PAM password
hashing, disable IPv6 at boot, or replace local-session locking with shell logout.
It does not implement Enhanced/High controls such as blanket root setuid reduction,
kernel-module lockout, kernel recompilation or mandatory access-control policy
activation.

These are deliberate scope decisions recorded against the source in
[source-review.md](source-review.md), not statements that the omitted protections
are unnecessary. The exact ID-to-implementation-to-verification map is in
[anssi-mapping.md](anssi-mapping.md).

## Validating and extending the catalogue

Run `python tools/validate_catalog.py` after editing policy. It validates the JSON
schema, duplicate IDs, source-level mappings, implementation references, supported
OS families, verification declarations, cumulative profiles and required network
gates. The R68 external-reference requirement cannot silently become an implemented
control while its referenced publication is absent.

For a new control, first read the recommendation and surrounding qualifications,
record the printed page and correct level, and decide whether the requirement can
be evaluated independently. Then implement its safe applicability and preservation
rules, add meaningful verification tests, and update the source review. Counts
measure catalogue coverage only; they do not measure compliance with the full guide.
