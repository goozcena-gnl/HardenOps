# Source review and control-selection record

This review records what the supplied publications say and how v0.1 narrows their
recommendations into controls. The publications are reference material; their text
does not override the user's requested implementation scope or authorise changes
to the machine running this project.

## Reviewed editions

| Source | Edition in supplied document | File | SHA-256 |
| --- | --- | --- | --- |
| ANSSI-BP-028, *Configuration Recommendations of a GNU/Linux System* | 2.0, 3 October 2022 | `linux_configuration-en-v2.pdf` (84 PDF pages) | `b0b9d8003b6f0974388dee6d33680867509399283f310c13a6c248f45595ed60` |
| ANSSI-PA-085, *Recommandations pour la protection des systèmes d'information essentiels* | 1.0, 18 December 2020 | `guide_protection_des_systemes_essentiels.pdf` (108 PDF pages) | `29f5a4f0e53163fc3d9b4ae2dc419b7325a87720a1d15e3989233871e3e01def` |

The edition dates come from each publication's printed page 1, not the PDF creation
timestamp. The BP-028 PDF was generated in July 2023; this does not make it a new
edition. The English document describes itself as a courtesy translation and says
the French original prevails if there is a conflict. This implementation was checked
against the supplied English edition; comparison with the French original has not
been performed.

Both publications attribute their original content to ANSSI and use Etalab Open
Licence 2.0. The catalogue is a selected implementation and paraphrase, with source
and update-date attribution here; it is not a republication of either guide. The
source PDFs are not copied into the repository.

**Page convention:** all catalogue `source.page` values and the page references
below are the printed page numbers. For both supplied PDFs, add two to obtain the
one-based PDF viewer page. For example, BP-028 R9 is printed page 19 / PDF page 21.

Text was extracted from both supplied PDFs. The relevant recommendation bodies,
surrounding qualifications, and the BP-028 recommendation summary were read.
Rendered BP-028 printed pages 5 and 68-70 were visually checked to confirm the
coloured level markers, which plain text extraction can misrepresent.

## Level interpretation

BP-028 printed page 5 (Table 1) explicitly defines cumulative target levels. The
highest illuminated letter is the recommendation's level: `M` is Minimal, `M I`
is Intermediary, `M I E` is Enhanced, and `M I E H` is High. An Intermediary target
also includes Minimal recommendations.

The recommendation summary on printed pages 68-70 confirms the levels below.
Appendix tables on printed pages 76-78 compare older and current editions: the
left-hand recommendation IDs and markers there must not be treated as the current
catalogue. For example, old-version R13 and current-version R13 have different
markers. PA-085 does not supply a replacement for this four-level model.

Only selected Minimal and Intermediary controls are operationally supported.
Support for a target profile means support for this project's declared subset;
it does not mean every recommendation at that ANSSI level is implemented.

## Candidate decisions

| BP-028 recommendation | Verified level | Printed pages | Meaning and v0.1 decision |
| --- | --- | --- | --- |
| R9 | Intermediary | 19 | Runtime kernel parameters. Five independent parameters are automated; no opaque R9 pass flag. The `pid_max=65536` value is explicitly an example and is not a universal target. Aggressive perf sampling limits, panic-on-oops and BPF disablement are excluded from this first subset. |
| R11 | Intermediary | 20-21 | Yama with `ptrace_scope` at least 1. Automate the parameter only when the interface is already present; preserve 2 or 3. Boot-time LSM activation is not implemented. |
| R12 | Intermediary | 21-22 | IPv4 settings for a simple non-routing server; the guide notes static addressing and workload constraints. Automate six all/default redirect/source-route parameters behind the non-router gate. Do not apply the full network example blindly to DHCP-based VM labs, routers, asymmetric routing, ARP proxies or high-availability systems. |
| R13 | Intermediary | 22-23 | When IPv6 is unused, disable it using the kernel boot flag and both all/default sysctls. `ipv6_required=true` makes this control NOT_APPLICABLE. When false, it remains MANUAL; runtime-only disablement would not implement the whole recommendation. |
| R14 | Intermediary | 23 | Five filesystem sysctls are independently automated: privileged core dumps, FIFO and regular-file protection, symbolic links and hard links. |
| R30 | Minimal | 34 | Remove unused user accounts. Collect account inventory as AUDIT_ONLY; deciding whether an account is unused requires an owner and business context. No account is deleted or disabled. |
| R32 | Intermediary | 35 | Lock inactive local console TTY and graphical sessions. MANUAL because desktop/console session mechanisms differ. Shell `TMOUT` logout is not equivalent, and the guide does not prescribe a universal duration. |
| R33 | Intermediary | 35-36 | Make privileged administration attributable through individual administrators, controlled elevation and/or process logging. Not selected: account lifecycle, privileged-session usage and log architecture need operational decisions. No broad auditd rule is installed as a claim of complete accountability. |
| R34 | Intermediary | 36 | Disable service-account login. Not selected for enforcement: service identity detection and exceptions require workload knowledge; applying a UID threshold could disable real administrators or required services. |
| R35 | Intermediary | 36 | Give each business service an account dedicated exclusively to it. Not selected; uniqueness of numerical UIDs alone cannot prove service exclusivity. |
| R50 | Intermediary | 48-49 | Sensitive files readable only on strict need to know, with ownership protecting permission changes. Automate a narrow subset: existing `/etc/shadow` and `/etc/gshadow`, root ownership and permissions no broader than 0640. Preserve stricter modes and trusted root/shadow group ownership. Other secret files remain outside this subset. |
| R51 | Enhanced | 49 | Replace secrets and establish access rights during installation. Excluded from supported profiles; it is not a Minimal password-file permission rule. |
| R52 | Intermediary | 49-50 | Protect named sockets/pipes and their containing directories. Not selected; valid application IPC paths and principals depend on workloads. |
| R53 | Minimal | 50 | Analyse files and directories with unknown owners or groups and correct them where justified. Collect bounded filesystem evidence as AUDIT_ONLY; no guessed ownership repair. |
| R54 | Minimal | 51 | World-writable directories require the sticky bit; the accompanying warning requires root ownership. Audit both properties in the declared scan scope. No recursive permission rewriting. |
| R55 | Intermediary | 51 | Users/applications need exclusive temporary directories. Not selected; enabling PAM namespace behaviour or service isolation can change workload semantics. |
| R56 | Minimal | 52 | Only trusted software designed for setuid/setgid execution may have those bits. Inventory is AUDIT_ONLY; neither the presence nor absence of a bit proves software trust. |
| R57 | Enhanced | 52-53 | Minimise root setuid/setgid executables. Excluded from supported profiles. The guide also warns that updates can restore special permissions. |
| R58 | Minimal | 53 | Install only necessary packages. Reviewed but not selected: no universal minimal package list fits these two distributions and unknown workloads. Broad package removal is unsafe. |
| R59 | Minimal | 53 | Repositories must be official distribution/editor sources or internal organisational sources. MANUAL review; a repository name or package list cannot establish origin, authorisation or mirror integrity. |
| R61 | Minimal | 54 | Maintain a regular, responsive security-update procedure. MANUAL; one successful update or an enabled timer cannot prove ongoing maintenance. |
| R62 | Minimal | 55-56 | Keep only services needed for operation and maintenance; remove or disable unnecessary ones. Reviewed but not selected for enforcement because the examples are contextual and do not authorise disabling modern server dependencies. |
| R63 | Intermediary | 56 | Reduce enabled service features to what is required. Reviewed but not selected; SSH forwarding, SMTP, NTP, DNS and HTTP behaviour are workload-dependent. |
| R68 | Minimal | 61 | Protect password storage cryptographically, referring to section 4.6 of publication [9]. OUT_OF_SCOPE_REFERENCE_REQUIRED because that publication was not supplied. Informational PAM examples do not replace the missing requirements. This is separate from R50 permissions. |
| R79 | Intermediary | 67 | Harden and monitor services exposed to uncontrolled flows, measuring deviation from expected behaviour. Reviewed but not selected; a listening-port inventory cannot verify service hardening or behavioural monitoring. |
| R80 | Minimal | 67 | Network services must bind to the correct interfaces. Reviewed but not selected; wildcard listening is not automatically wrong without the workload's intended exposure. |

The deferred candidates are recorded here rather than padded into the active
catalogue as fake implemented controls. No selected recommendation depends on
Enhanced R36/R37/R45/R57 or High R46 as a hidden prerequisite. Existing mandatory
access control is observed by preflight and preserved, not disabled to make tests
pass.

## Selected atomic controls

| Area | Source | Atomic controls | Catalogue treatment |
| --- | --- | ---: | --- |
| Kernel messages, pointers, perf restrictions, ASLR, Magic SysRq | R9 | 5 | AUTOMATED |
| Yama ptrace restriction | R11 | 1 | AUTOMATED |
| all/default IPv4 receive redirects, source route, send redirects | R12 | 6 | AUTOMATED |
| Privileged core dumps and four filesystem protections | R14 | 5 | AUTOMATED |
| Shadow and group-shadow access | R50 | 2 | AUTOMATED |
| Account need and three filesystem inventories | R30, R53, R54, R56 | 4 | AUDIT_ONLY |
| Repository trust, update process, IPv6 lifecycle, local-session locking | R59, R61, R13, R32 | 4 | MANUAL |
| Password storage external-reference review | R68 | 1 | OUT_OF_SCOPE_REFERENCE_REQUIRED |
| **Total** | **14 distinct recommendations** | **28** | **19 automated, 9 requiring review/reference work** |

There are **7 Minimal controls and 21 Intermediary controls**. The Minimal profile
is intentionally an evidence/review baseline in v0.1; all selected automatic
configuration changes belong to Intermediary recommendations. Inventing Minimal
automation by relabelling Intermediary controls would contradict the guide.

`AUTOMATED` describes an available implementation, not an observed pass.
`VERIFIED` is supported as a capability classification but no catalogue entry is
assigned it merely because enforcement exists. Verification results are based on
new host observations. AUDIT_ONLY and MANUAL entries remain those statuses rather
than becoming PASS from absence of detected failures. NOT_APPLICABLE and
UNSUPPORTED are applicability outcomes, not failures or certification results.

The six R12 controls verify exactly the named all/default kernel parameters. They
do not claim that every existing interface has the same value or that full R12 is
implemented. Linux applies different combination rules to different all/interface
parameters, so interface-specific settings need workload review. The report names
the individual key to make this limit visible.

The two R50 controls assume the distribution's `shadow` group is restricted to
principals with a strict need to know. They do not attest group membership policy,
PAM cryptography, ACLs on arbitrary secret files, or all authentication paths.

## Source-informed preservation decisions

R11 explicitly allows stronger values 2 and 3; v0.1 must preserve either. A runtime
value of 3 cannot be reversed until reboot, so the implementation does not select 3
as its baseline. Unsupported Yama is reported instead of manipulating boot flags.

R9 lists `perf_event_paranoid=2`. The guide's nearby comment about denying the whole
unprivileged syscall is broader than the semantics of value 2. The
[Linux kernel documentation](https://www.kernel.org/doc/html/v6.7/admin-guide/sysctl/kernel.html#perf-event-paranoid)
defines values at or above 2 as restricting kernel profiling; v0.1 describes this
as restricted performance monitoring. It explicitly preserves existing 3 and 4.
Ubuntu's
[kernel-team patch explanation](https://lists.ubuntu.com/archives/kernel-team/2025-November/164447.html)
documents additional restrictions at Ubuntu's level 4. Unrecognised values must
trigger review rather than being silently replaced with a weaker baseline.

The [kernel SysRq documentation](https://docs.kernel.org/admin-guide/sysrq.html)
defines the keyboard enable-all value 1 and function bits 2 through 256. SysRq is
the only control with a bounded remediable numeric range (1-511); disabling it
means writing 0 regardless of the subset enabled. Values outside that documented
mask range require review. The sysctl does not prevent privileged use of
`/proc/sysrq-trigger`.

Permission enforcement intersects existing mode bits with the maximum permitted
mode; it never expands a stricter mode to a distribution example. Profile changes
do not uninstall the existing policy or automatically revert stronger settings.
Other sysctl values are not ranked by a generic numerical comparison: bitmasks,
boolean values, and enums require control-specific interpretation.

## PA-085 as complementary design guidance

The following links are architectural interpretations, not a claim to implement
the PA-085 publication or its regulatory setting in full.

| PA-085 recommendation | Printed page | Application in HardenOps |
| --- | --- | --- |
| R2 and R2-: necessary services/features and compensating measures | 19-20 | Restrict the initial control subset, collect inventory before risky remediation, and require explicit workload decisions. Future workload profiles can express approved service needs. |
| R3: secure reference configurations and regular tracking of deviations | 20 | Version-controlled catalogue and cumulative profiles define desired state; Ansible enforces the supported subset; independent observations and timestamped evidence expose differences. Scheduled comparison across reports is future drift detection, not an implemented monitoring service. |
| R30: individual administration accounts | 53 | Preserve the authenticated operator's access, avoid shared-root workflow assumptions, and retain host/control/run identity in evidence. Account lifecycle and identity assurance remain organisational work. |
| R35 and R55: least privilege | 56 and 76 | Use privilege escalation for bounded target tasks; restrict sensitive-file access and kernel interfaces. This does not establish a complete organisational access-rights model. |
| R56 and R57: privileged-account traceability and regular rights review | 77 | Account inventory and auditable code changes provide evidence for review. Maintaining an authoritative identity register and periodic human review are outside this release. |
| R58-R61: security-maintenance policy, monitoring, reliable updates and planned installation | 80-81 | Keep the update procedure explicit and manually reviewed; record dependencies and rerunnable checks. Do not equate a successful hardening run with continued secure maintenance. |

The R3 design chain is:

```text
secure reference configuration
    -> version-controlled catalogue and profiles
    -> applicable Ansible enforcement
    -> independent host-state verification
    -> JSON and Markdown evidence
    -> future comparison over time for drift detection
```

This chain is useful only within the declared coverage. The broader SIE
architecture, network segmentation, secure administration infrastructure,
homologation, incident response and organisational maintenance obligations are
not provided by a Linux lab repository.
