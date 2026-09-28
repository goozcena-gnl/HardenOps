# Validation record — 0.1.0

## 2026-09-27–28 — real-VM validation milestone

**Verdict: NOT READY FOR PUBLICATION.** The mandatory real-VM paths are
**BLOCKED (ENVIRONMENT)**. This run revalidated the existing implementation and
container tests; it did not establish guest-kernel or reboot correctness.

### Repository baseline

The initial checkout was clean on `main` at
`5fac298b385052676126ba8b87c0ba91b97d093d`, with version 0.1.0, 62 tracked files and
no configured remote. There was no discrepancy from the historical Git baseline.
Work continued locally on `validation/v0.1-real-vm`; no reset, tag, release,
publication or push was performed. The catalogue remains 28 entries: 7 Minimal,
21 Intermediary; 19 AUTOMATED, 4 AUDIT_ONLY, 4 MANUAL and 1 external-reference
requirement. No implementation or control was added.

### Environment and VM blocker

| Item | Observed state |
| --- | --- |
| Host | Windows 11 Home, 10.0.26200, x86_64; PowerShell 7.6.5 |
| Existing controller | Ubuntu 24.04.5 under WSL2; Linux 6.18.33.2-microsoft-standard-WSL2 |
| Python / Ansible | Python 3.12.3 / ansible-core 2.21.4 in the existing isolated Linux environment |
| Make / Docker | GNU Make 4.3 / existing Linux Docker engine 29.1.3 |
| Vagrant | Absent from Windows and WSL; no installed Windows Vagrant package found |
| Windows provider | VirtualBox 7.2.20r175154 installed; no functioning Vagrant/WSL provider path configured |
| Linux provider | No `virsh`, QEMU executable or libvirt socket; `/dev/kvm` exists but the current account cannot read or write it |
| Capacity | About 190 GiB free on the Windows volume before testing; no VM box was downloaded |
| Virtualization | Windows hypervisor already present; VirtualBox reports hardware virtualization support. These observations do not prove a guest can boot. |

The intended Linux/libvirt workflow cannot run in the discovered environment.
The existing Windows VirtualBox installation does not supply the missing Vagrant
controller or configured WSL integration. The
[Vagrant WSL documentation](https://developer.hashicorp.com/vagrant/docs/other/wsl)
requires a Linux Vagrant installation and explicit Windows-provider access; it
does not support substituting the Windows `vagrant.exe` inside WSL. No provider
change or host-wide installation was attempted. Host networking, Hyper-V,
VirtualBox, drivers, Windows security settings and KVM permissions were preserved.
Restoring a supported Vagrant/provider path requires user/admin environment setup.

Before any lifecycle action, the repository path and local state were checked:
neither `.lab/` nor `.vagrant/` existed, and no registered HardenOps VirtualBox VM
was found. No existing VM was reused, modified or destroyed. No VM was created by
this run, so no VM cleanup command was issued. The fixed-name Molecule container
was also absent before testing; only containers created by these test runs were
removed by their scenario cleanup.

### Fast regression baseline

`make test validate lint` completed successfully: 93 unit cases, 28 catalogue
entries, four profile definitions, YAML validation, production-profile
ansible-lint and syntax checks for all four playbooks. `ruby -c Vagrantfile`
also passed, executed in a disposable `ruby:3.3-slim` container with a read-only
project mount. This proves Ruby syntax only, not Vagrant/provider operation.
No local syntax or catalogue defect was found before evaluating the VM paths.

### Existing Minimal profile review: CONFIRMED

| Existing control | Requirement represented | Classification and intentional safe behavior |
| --- | --- | --- |
| `bp028_r30_unused_accounts` (R30) | Identify accounts no longer needed | AUDIT_ONLY: local account inventory cannot establish business need; no deletion or locking. |
| `bp028_r53_unknown_owners` (R53) | Investigate unknown file/directory owners or groups | AUDIT_ONLY: bounded candidates absent from local identity databases; no guessed ownership repair; external NSS requires review. |
| `bp028_r54_world_writable_dirs` (R54) | Sticky bit and root ownership for world-writable directories | AUDIT_ONLY: report sampled properties without recursive permission or ownership changes. |
| `bp028_r56_setid_inventory` (R56) | Reserve setuid/setgid for trusted software designed for it | AUDIT_ONLY: inventory does not prove trust; no blind privilege removal. |
| `bp028_r59_repository_review` (R59) | Official/editor or authorised internal repositories | MANUAL: provenance and authorisation need review; repository configuration is not automatically inspected or rewritten. |
| `bp028_r61_update_procedure` (R61) | Responsive ongoing security-update procedure | MANUAL: a timer or single upgrade cannot prove the procedure; no package upgrade is performed. |
| `bp028_r68_password_storage` (R68) | Password-storage requirements delegated to reference [9], section 4.6 | OUT_OF_SCOPE_REFERENCE_REQUIRED: preserve the missing-reference limitation; do not invent cryptographic requirements or alter PAM. |

The inspector excludes the 21 higher-level controls and sets `needs_change=false`
for non-AUTOMATED entries. Every role requires an applicable AUTOMATED entry
needing change. The filesystem audits cover only listed directories and their
direct children, with limits and exclusions disclosed. The default Minimal
expectation remains 4 AUDIT_ONLY, 2 MANUAL, 1 external-reference requirement,
21 NOT_APPLICABLE, zero automatic changes and zero applicable reboot-required
controls. This confirms the design; it is not a PASS for unexecuted real-guest
hardening or reboot gates.

### Mandatory real-VM gates

The two paths were assessed separately, Ubuntu first. The same missing prerequisite
blocks provisioning of each; no Ubuntu success was inferred for Rocky.

| Gate | Ubuntu Server 24.04 | Rocky Linux 9 | Explanation |
| --- | --- | --- | --- |
| Fresh provisioning | BLOCKED | BLOCKED | ENVIRONMENT: no usable Vagrant/provider execution path. |
| SSH / Ansible / sudo | NOT RUN | NOT RUN | No guest provisioned. |
| Minimal plan | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Minimal hardening | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Minimal verification | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Minimal target idempotence | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Minimal genuine reboot / persistence | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Intermediary plan | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Intermediary hardening | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Intermediary verification | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Intermediary target idempotence | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Intermediary genuine reboot / persistence | NOT RUN | NOT RUN | Depends on the blocked guest. |
| Guest reports | NOT RUN | NOT RUN | No real-guest evidence exists. |
| Cleanup | NOT RUN | NOT RUN | No VM was created; nothing was destroyed. |

The configured, unexecuted boxes remain `bento/ubuntu-24.04` version
`202508.03.0` and `rockylinux/9` version `6.0.0`. No guest distribution, version,
architecture or kernel is claimed for either VM. Live-VM Testinfra is downstream
of these blocked gates and was not executed against a guest.

### Local regression scope and evidence

Molecule uses the **default/delegated driver**, explicit unprivileged Docker
creation and `community.docker.docker` connections. It is not a VM driver.
The existing scenario exercises real filesystem fixtures, second convergence,
the Intermediary read-only planner and Minimal JSON/Markdown reporting. It does
not apply host sysctls or validate guest boot, sudo, SELinux or AppArmor semantics.

Commands used from the existing Linux controller:

```sh
make test validate lint
make hygiene
make molecule IMAGE=ubuntu:24.04
make molecule IMAGE=rockylinux:9
make test validate lint hygiene
```

The final local regression results are:

| Gate | Result | Executed evidence |
| --- | --- | --- |
| Unit and report tests | PASS | 93 cases, including four report-rendering cases; no tests removed. |
| Catalogue / profiles | PASS | 28 controls and all four profile definitions. |
| YAML | PASS | `yamllint .` |
| Ansible lint | PASS | Production profile, 47 files processed, zero failures or warnings. |
| Ansible syntax | PASS | Baseline, plan, harden and verify playbooks. Empty-inventory warnings are expected for syntax-only checks. |
| Vagrantfile syntax | PASS | Ruby syntax only, checked before the VM paths; unchanged since that check. |
| Tracked-file secret scan | PASS | Existing `detect-secrets-hook` gate. |
| Dependency audit | PASS | Existing `pip-audit` gate reported no known vulnerabilities at execution time. |
| Molecule / Ubuntu | PASS | All seven lifecycle actions completed; first convergence changed one fixture, second convergence changed zero. |
| Molecule / Rocky | PASS | All seven lifecycle actions completed independently; first convergence changed one fixture, second convergence changed zero. |
| Container report review | PASS | Parsed both JSON files; checked structure, metadata, counts and Markdown agreement against the catalogue and fresh scenario observations. |
| Live-VM integration | NOT RUN | Depends on blocked real-guest provisioning. |

The two Molecule runs reported Ubuntu 24.04 and Rocky 9.3 userspace respectively,
both x86_64, sharing the Linux Docker host kernel
`6.18.33.2-microsoft-standard-WSL2`. These are container facts, not independently
booted guest kernels. Both verification plays completed with zero target changes.
The scenario removed its test container; a final read-only check confirmed its
absence and that neither `.lab/` nor `.vagrant/` had been created.

Both JSON reports satisfy the renderer's version-1 contract; the repository has
no separate JSON report schema. All 28 control IDs, source references, levels
and enforcement classifications match the unchanged catalogue. The independently
recomputed Minimal counts are 4 AUDIT_ONLY, 2 MANUAL, 1
OUT_OF_SCOPE_REFERENCE_REQUIRED and 21 NOT_APPLICABLE, with no PASS, FAIL or
required automatic changes. Each Markdown report exactly matches rendering of
its JSON, and its material table values were also checked directly.

Scanning the four fresh report files produced two potential-secret alerts: the
`catalogue.sha256` value in each JSON report. Independent hashing of the tracked
catalogue confirmed that both values are its public content digest. These are
reviewed false positives, not credentials. No other secret findings were found;
no report was rewritten and no scanner rule or allowlist was changed. Generated
reports remain ignored and uncommitted.

Current-run logs and container reports are retained locally under the ignored
`artifacts/validation-2026-09-27/` directory. They are not publication artifacts.
Remote GitHub Actions is NOT RUN because it is explicitly outside this milestone.

### Scope of changes

No reproducible project or test defect was exposed by the executed gates. The
VM blocker is an environment prerequisite, not a HardenOps implementation failure.
Only this validation record is updated. The README, implementation, catalogue,
profiles, dependencies and tests retain their existing scope and behavior.

## Historical validation — 2026-09-19

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
