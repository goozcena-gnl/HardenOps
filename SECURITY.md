# Security policy

## Project and release scope

HardenOps is an Ansible-based Linux hardening lab for disposable environments.
Reports concerning published HardenOps releases or current main are welcome.
There is no promised long-term (LTS) support period, backport policy, or
guaranteed response or fix deadline.

The documented v0.1.0 targets are Ubuntu Server 24.04 LTS and Rocky Linux 9.
In v0.1.0, the selected subset of controls has these boundaries: Minimal performs no
automatic remediation, Intermediary implements the selected automated controls,
and Enhanced/High are not implemented and must fail explicitly. HardenOps is
not ANSSI certification, a compliance guarantee, or a production security audit.
See [README](README.md) and [validation record](docs/validation.md) for the
actual scope and separate static, container, and real-VM evidence. Do not point
the lab workflow at production infrastructure.

## Report a vulnerability privately

Use [GitHub private vulnerability reporting](https://github.com/goozcena-gnl/HardenOps/security/advisories):
open the repository Security tab, choose Advisories, then
**Report a vulnerability**. GitHub sign-in is required to submit a report.

Do not put vulnerability details, exploit instructions, or sensitive evidence
in public issues, discussions, or pull requests. Ordinary bugs without security
impact may be reported through public issues; if the impact is uncertain,
use the private channel.

Include:

- The affected release or full commit ID and relevant dependency versions.
- Controller OS/Python, target distribution/version, provider, profile, and
  relevant configuration, with identifying and sensitive values removed.
- A minimal reproduction in a disposable environment you control.
- Expected behavior, observed behavior, security impact, and attack prerequisites.
- Minimal redacted output or a proof of concept sufficient to assess the report.

Never submit passwords, tokens, private SSH keys, password hashes, complete VM
images, or unredacted logs, host inventories and evidence archives. Reports
contain operational metadata: keep local evidence private and share only the
minimum redacted excerpts. See [safety guidance](docs/safety.md).

## Security boundaries and reportable behavior

Examples of concerns worth reporting include unauthorized execution or writes
on the controller or target, symlink or path handling that escapes intended
owned files, disclosure of credentials or sensitive account data, silent
weakening of stricter supported settings, bypass of unsupported-target or
profile refusal, and misleading verification that reports an unobserved PASS.

Administrator-reviewed catalogues, profiles, playbooks, and target selection
are trusted configuration. Guest state, paths, and inspection results still
need safe handling. Privileged enforcement makes the distinction consequential.
Dependencies and CI actions are part of the assessment when a vulnerability
affects HardenOps; an upstream advisory alone does not establish reachability.

Documented manual controls and bounded audits are limitations, not automatic
claims of host security. Please report security consequences or misleading
behavior involving those limitations rather than assuming they exclude a report.

## Coordination

Keep reproduction and patch discussion in the private report while the impact
is assessed. Propose coordinated disclosure there with the maintainer.
This policy does not promise a bounty, a fixed disclosure schedule, or a
guaranteed remediation.
