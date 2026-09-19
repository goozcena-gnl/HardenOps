# Validation record — 0.1.0

Local validation date: 2026-09-19. Controller: Ubuntu 24.04 under WSL2,
Python 3.12.3, the pinned development requirements and Ansible collections.
These are local results, not GitHub Actions run results or certification evidence.

| Check | Result | Scope |
| --- | --- | --- |
| `make help` and lab helper help | PASS | Documented entry points execute |
| Catalogue and all four profile definitions | PASS | 28 controls; source-level, schema, safety-gate and inheritance checks |
| `pytest` | PASS | 93 unit cases across inspector, catalogue, reports and lab helper |
| `yamllint .` | PASS | Repository YAML |
| `ansible-lint` | PASS | Production lint profile |
| Ansible syntax checks | PASS | All four required playbooks |
| `ruby -c Vagrantfile` | PASS | Ruby syntax using a disposable Ruby 3.3 container |
| Secret scan | PASS | Tracked files; one reviewed annotation for a public package-version pin |
| `pip-audit -r requirements-dev.txt` | PASS | No known vulnerabilities reported at validation time |
| Molecule / Ubuntu 24.04 | PASS | Seven lifecycle actions; real file enforcement and second-pass idempotence |
| Molecule / Rocky Linux 9 | PASS | Seven lifecycle actions; image userspace reports Rocky 9.3 |
| Read-only planning and reports | PASS | Actual Intermediary plan and Minimal JSON/Markdown report on both containers |
| Vagrant boot / provider validation | NOT RUN | Vagrant, QEMU and libvirt provider were not installed/configured |
| Full VM hardening and reboot lifecycle | NOT RUN | No VMs were provisioned |
| Live VM Testinfra controls | NOT RUN | Suite supplied and guarded; no hardened VM was available |
| Live-test opt-in guard and Python compilation | PASS | 20 live checks explicitly skipped by default; helpers and tests compile |
| Remote GitHub Actions | NOT RUN | Workflows created and locally linted; repository not published |

The WSL kernel exposes `/dev/kvm`, but it was not accessible to the current Linux
account, which also lacked passwordless sudo. No changes were made to host
virtualization permissions or infrastructure. The container tests ran against an
available Docker engine using unprivileged containers without host bind mounts.
The Ruby syntax check mounted only the project, read-only.

## What was actually exercised

Each Molecule run created disposable distribution userspace, installed Python if
absent and prepared two ordinary test files. The production inspector read their
real metadata, and the production filesystem role restricted a 0666 file to 0640.
A separate 0400 file remained 0400. The first convergence reported one target
change; the second reported `changed=0`. Independent Ansible stat assertions
verified ownership and permissions afterwards.

The scenario then executed the real Intermediary planner using all 28 catalogue
entries and the real Minimal verifier/reporting playbook. The Minimal reports
correctly contained **4 AUDIT_ONLY, 2 MANUAL, 1 external-reference requirement and
21 NOT_APPLICABLE entries**, with **0 PASS**. This is evidence that reporting does
not manufacture passes from review-only coverage. Reports recorded the catalogue
digest, detected distribution and the shared WSL kernel; these are explicitly
container observations, not hardened VM reports.

Kernel sysctl enforcement, complete-host idempotence, reboot persistence, package
preflight on a VM, provider networking, SELinux and AppArmor enforcement were not
validated by these container runs. The two permission fixtures are test fixtures,
not claims that all sensitive-file or filesystem recommendations were implemented.

Unit tests cover cumulative profiles, unknown or unsupported systems, network
gates, explicit exceptions, missing interfaces, stronger runtime/persistent values,
unsafe or malformed persistence, Yama's irreversible state, restrictive file modes,
symlink refusal, bounded audits, non-disclosure of password fields, catalogue
validation and SSH inventory handling.

Initial failures were corrected before final validation: YAML formatting, Molecule
collection discovery, profile-variable precedence in imported smoke tests, and
stale tests after adding fail-closed handling of unknown sysctl values. The secret
scanner identified `detect-secrets==1.5.0` in the workflow as a keyword match; the
specific public dependency-install line is annotated as a reviewed false positive.
No broad scanner exclusion was introduced.

Local ignored evidence is retained in `artifacts/`: Molecule logs for each distro,
the static-validation log and separate `ubuntu-container/` and `rocky-container/`
JSON/Markdown reports. Generated reports and local runtime caches are not committed.

## Running the live Testinfra suite

After a successful real VM hardening run, use the same declared profile and
network assumptions as Ansible:

```bash
HARDENOPS_LIVE_TESTS=1 HARDENOPS_LEVEL=intermediary \
  pytest tests/integration --hosts=ansible://lab \
  --ansible-inventory=.lab/inventory.yml --sudo -rs
```

`HARDENOPS_ROUTING` defaults to `false`; `HARDENOPS_IPV6_REQUIRED` defaults to
`true`. `HARDENOPS_DISABLED_CONTROLS` is an optional comma-separated list matching
the operator exceptions used by Ansible. The 19 deterministic controls each have
an independent test case. Missing features and declared exclusions produce
explicit skips with reasons rather than being silently counted as passes.

## Next acceptance milestone

Run the full Vagrant cycle on a configured Linux virtualization host for both
distributions: deploy, plan, converge, second-run idempotence, reboot, verify and
Testinfra. Also verify that a downgrade to Minimal preserves the prior Intermediary
state. Keep both pre- and post-reboot evidence. The procedure is described in
[distributions.md](distributions.md).
