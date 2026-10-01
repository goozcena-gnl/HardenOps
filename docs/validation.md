# Validation record — 0.1.0

## 2026-10-01 — Ubuntu single-CPU candidate gate

**SINGLE_CPU_CANDIDATE_PASS.** Two completely fresh Ubuntu VirtualBox guests
passed the provisioning and connectivity gate with
`cloud-image/ubuntu-24.04@20260926.0.0`, amd64, **1 configured vCPU**, 2048 MiB
RAM and the box's default I/O APIC off. No I/O APIC override was introduced.
The alternative was selected after controlled local stability validation;
these observations do not establish that Bento is defective.

### CPU requirement audit and scope

A read-only review of all 62 tracked files covered the Vagrant and Make workflow,
README/docs, tools, catalogue/profiles, Ansible tasks/roles/playbooks and
unit/live/Molecule tests. The two historical `cpus = 2` settings were resource
choices. Historical VM descriptions are observations, not acceptance conditions.
There is no functional CPU-count/topology assertion, scheduler/load test,
parallel-execution requirement or security control requiring SMP. The catalogue's
performance-monitoring restriction is an access policy, not a performance test.
Classification: **SINGLE_CPU_SUFFICIENT** for the existing v0.1 validation scope.
This does not claim that one CPU represents every production deployment.

Only the Ubuntu VirtualBox box name, exact version and CPU allocation changed.
Rocky, Ubuntu libvirt, controls, profiles, roles, Ansible behavior, networking and
host/provider installation settings were preserved. Existing lab unit tests cover
SSH inventory and state, without suitable Vagrant/provider configuration coverage;
the candidate was checked by `vagrant validate` and actual fresh-guest resource
observations rather than a new string-matching unit test.

### Exact controller and fresh evidence

Both attempts used `/home/goozcena/.cache/hardenops-v01-venv`: Python 3.12.3,
ansible-core 2.21.4, ansible-lint 26.8.0 and Molecule 26.8.0, with project collections
ansible.posix 2.2.2 and community.docker 5.3.0. All eleven direct dependency pins
and both collection pins were verified again; `python --version`,
`ansible --version` and `pip check` passed. WSL networking remained mirrored and
the actual `/mnt/c` mount retained DrvFS metadata. The existing provider was
VirtualBox 7.2.20r175154, controlled by Linux Vagrant 2.4.9.

| Check | VM 1 | VM 2 |
| --- | --- | --- |
| Fresh UUID | `f7396b51-152b-4543-bb63-77ea476092c7` | `1f97dc25-3a98-4901-a75d-10693cbf5951` |
| One fresh boot, no lifecycle intervention | PASS | PASS |
| Guest Ubuntu 24.04 / x86_64 | PASS | PASS |
| nproc / getconf / lscpu / Ansible CPU count | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1 |
| Guest kernel | `6.8.0-142-generic` | `6.8.0-142-generic` |
| WSL TCP / SSH / vagrant ssh | PASS | PASS |
| Inventory generation / validation | PASS | PASS |
| Ansible ping / full facts | PASS | PASS |
| Harmless `id -u` as vagrant | PASS, 1000 | Not required |
| sudo/become `id -u` | PASS, 0 | PASS, 0 |
| Read-only baseline prerequisite recap | changed=0, failed=0 | changed=0, failed=0 |
| Destruction after evidence | PASS | PASS |

The first guest was destroyed before the second import. There were no retries,
reboots, pause/resume operations or saved-state recovery. An independent evidence
review passed 36 checks. Both boots were slow, and Vagrant reported a Guest
Additions version mismatch; no workaround was applied and no cause was inferred.
The four unrelated VMs retained their UUIDs, powered-off states and configuration
hashes. Logs, console captures, guest/fact results and cleanup records are retained
locally outside the tracked repository in `../ubuntu-single-cpu-2026-10-01/`.

### Limits and next gate

The image is third-party, with **MEDIUM** provenance confidence and no independent
registry `.box` digest; see [the provider contract](distributions.md). The sample
is two fresh guests on this host, not a general reliability guarantee. Unresolved
multi-vCPU VirtualBox/NEM/WHP behavior is outside the intentional one-vCPU local
contract; no new SMP diagnostic was run because HardenOps does not require it.

Minimal and Intermediary hardening, real-guest control verification/idempotence,
genuine reboot persistence, live Testinfra and Rocky real-VM validation are
**NOT RUN** in this gate. The full Real VM Validation Gate remains the next
milestone, using the adopted Ubuntu VirtualBox contract and exact controller.

## 2026-09-30 — fresh real-VM validation attempt

**Verdict: NOT READY FOR PUBLICATION.** The earlier environment smoke chain
passed on 2026-09-29, but the mandatory fresh Ubuntu VM now stalls before SSH
and before any HardenOps baseline or hardening playbook executes. Rocky real-VM
validation is **NOT RUN**: the sequential workflow stops at this Ubuntu blocker.
Successful unit and container tests do not establish guest boot, kernel,
idempotence or reboot correctness.

### Repository gate and inventory correction

The starting branch was `validation/v0.1-real-vm`, HEAD
`80c03eff3e44d4645d89291c811bb914aa07fe2d`, with exactly two modified tracked
files: `tools/lab.py` and `tests/unit/test_lab.py`. Review confirmed that the
correction preserves the ordered identities for one host, keeps host-key
checking, quotes additional identity paths as separate arguments, and rejects
ambiguous host/match scopes and duplicate connection fields. Single-key and
multiple-key regression cases both pass.

Before creating a VM, `make test validate lint` passed: 101 unit cases, all
28 catalogue entries and four profiles, YAML and production Ansible lint, and
syntax checks for baseline, plan, harden and verify. `git diff --check` passed.
The dedicated local commit is `3d1862b728eec89689f1861583fe166e5f998a68`,
`fix: support multiple Vagrant SSH identities`. The VM gate started from a clean
tracked worktree. No push, tag, history rewrite or publication was performed.

### Observed host topology and short preflight

| Item | Actual observation |
| --- | --- |
| Windows | Windows 11, build `10.0.26300.9457`; last boot 2026-09-30 at 12:56 Europe/Paris |
| WSL / controller | WSL 2.7.14.0; Ubuntu 24.04.5 userspace; kernel `6.18.33.2-microsoft-standard-WSL2` |
| Networking / filesystem | `wslinfo` returns `mirrored`; actual `/mnt/c` mount includes DrvFS `metadata` |
| Vagrant / provider | Linux Vagrant 2.4.9; existing Windows VirtualBox 7.2.20r175154 |
| Python / Ansible | Python 3.12.3; ansible-core 2.21.4, using the existing isolated controller environment and project configuration |
| Molecule / Docker | Molecule 26.8.0; Docker engine 29.1.3 |
| Initial capacity | 12708 MiB available, 46% committed; no project VM or lab state existed |
| Later memory observations | 11808, 11624 and 11478 MiB available; 50% committed; no memory collapse observed |

No host, Hyper-V, WSL, DrvFS, BIOS, networking, security-feature or VirtualBox
installation setting was modified during this run. The provider log records
the NEM/Windows hypervisor execution path; that observation does not establish
the cause of the guest hang.

### Fresh Ubuntu attempt and bounded diagnosis

`make deploy DISTRO=ubuntu2404 PROVIDER=virtualbox` imported the pinned
`bento/ubuntu-24.04@202508.03.0` amd64 box and created only
`hardenops_default_1790769406826_74619`, UUID
`e5c1ec0f-d7d1-4871-8acb-461f95df993d`, with 2048 MiB and two CPUs.
VirtualBox reports it running, with NAT `127.0.0.1:2222` to guest port 22.
Repeated console observations remained at initramfs `Loading essential drivers`.
Both Windows and WSL TCP connections succeeded but received no SSH banner.

After preserving console and provider evidence, only this task's Vagrant SSH
wait was interrupted. `make deploy` returned 2 because Vagrant was interrupted,
not because a completed HardenOps task failed. The baseline playbook was never
reached. A single reversible pause/resume exposed a kernel stack during module
loading without restoring SSH. After preserving that evidence, one cold restart
of this same VM also remained in driver loading, with a RAID6 benchmark line and
no SSH banner during bounded observation. No additional VM was created, and no
provider settings were changed. The captured logs contain no recurrence of the
previous `0xc0000005` VBoxVMM crash signature.

Cause class: **ENVIRONMENT**. The demonstrated failure is guest cold-boot/module
loading before SSH. The evidence does not distinguish an image/kernel problem
from a VirtualBox/host-integration problem. No speculative project or host fix
was applied. The prior recovered smoke VM is not proof of this fresh boot path.

| Mandatory gate | Ubuntu Server 24.04 | Rocky Linux 9 |
| --- | --- | --- |
| Fresh provisioning | BLOCKED | NOT RUN |
| Guest version / kernel / architecture verified inside guest | NOT RUN | NOT RUN |
| SSH / Vagrant / inventory / Ansible / become | NOT RUN | NOT RUN |
| Minimal plan / harden / verify | NOT RUN | NOT RUN |
| Minimal target idempotence | NOT RUN | NOT RUN |
| Minimal genuine guest reboot / post-reboot verification | NOT RUN | NOT RUN |
| Intermediary plan / harden / verify | NOT RUN | NOT RUN |
| Intermediary target idempotence | NOT RUN | NOT RUN |
| Intermediary genuine guest reboot / post-reboot persistence | NOT RUN | NOT RUN |
| Real-guest JSON / Markdown reports and Testinfra | NOT RUN | NOT RUN |
| Successful-cycle cleanup | NOT RUN | NOT RUN |

The failed Ubuntu test VM is preserved for diagnosis. Rocky was not created;
its configured box remains `rockylinux/9@6.0.0`. Neither guest's actual version
or kernel is claimed. The four unrelated VMs remain powered off and untouched:
`fluxvirt-lab`, `fluxvirt-cleanroom`, `github-runner-devops-01`, and
`TP-Hardening-1`.

### Independent regression results

Although the real-VM acceptance gate is blocked, the independent local gates
were completed again in this run:

| Evidence class / gate | Result | Actual scope |
| --- | --- | --- |
| Static/unit: tests and reports | PASS | 101 unit cases, including four report tests |
| Static/unit: catalogue / profiles | PASS | 28 entries, all four profile definitions |
| Static/unit: YAML / Ansible lint | PASS | Production lint, 47 processed files, zero failures or warnings |
| Static/unit: Ansible syntax | PASS | All four playbooks |
| Repository hygiene: secrets | PASS | Existing tracked-file secret scanner |
| Repository hygiene: dependencies | PASS | Existing pinned-requirements audit; no known vulnerabilities reported at execution time |
| Container: Molecule Ubuntu | PASS | Seven lifecycle actions, second convergence changed zero; container cleaned up |
| Container: Molecule Rocky | PASS | Seven lifecycle actions independently, second convergence changed zero; container cleaned up |
| Container: report validation | PASS | Fresh JSON parses, Markdown matches its renderer, catalogue digest and metadata checked |
| Ubuntu real VM | BLOCKED | Guest stalls before SSH and HardenOps execution |
| Rocky real VM | NOT RUN | Sequential workflow stopped at Ubuntu blocker |
| Live-VM integration | NOT RUN | No healthy hardened guest available |

Container reports record Ubuntu 24.04 and Rocky 9.3 userspace, both x86_64,
sharing the controller kernel. Each Minimal report contains 4 AUDIT_ONLY,
2 MANUAL, 1 OUT_OF_SCOPE_REFERENCE_REQUIRED and 21 NOT_APPLICABLE entries,
with zero automated or independently passed entries. These are not VM or
SELinux/reboot/persistent-kernel validation results.

Local evidence is retained in the ignored directory
`artifacts/real-vm-validation-2026-09-30/`: gate logs, separate container reports,
console captures, provider logs, memory and network observations, and the
interrupted-provisioning record. No credentials or private-key contents were
recorded. No new control, profile, functionality or source recommendation was
added. README statements remain accurate and were not rewritten.

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
