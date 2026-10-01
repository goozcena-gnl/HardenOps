# Distribution and lab support

HardenOps v0.1 targets Ubuntu Server 24.04 LTS and Rocky Linux 9. Distribution
facts gate execution; other Debian and Red Hat derivatives are not accepted merely
because they share a package manager. Minimal and Intermediary are the only
operational profiles. The production Ansible paths are shared between families.

## Controller and providers

Use Linux with Python 3.12 or 3.13, GNU Make, OpenSSH, Vagrant 2.4 or newer, and
hardware virtualization. Create a Python virtual environment before `make install`.
Ansible 2.21 supports Python 3.9 on the target, including Rocky 9's default Python;
see the [Ansible support matrix](https://docs.ansible.com/projects/ansible-core/devel/reference_appendices/release_and_maintenance.html).
Native Windows is not an Ansible control node. A Linux VM/controller is the
recommended Windows route; WSL requires separately configured Vagrant/provider
connectivity. The adopted one-vCPU Ubuntu VirtualBox path has passed the local full
Minimal-to-Intermediary real-VM gate, independent verification, idempotence and
reboot persistence described in [validation.md](validation.md), after a focused
R14 persistence correction. Rocky Linux 9 real-VM acceptance remains pending.

The default provider is libvirt/KVM. Install libvirt, QEMU/KVM and the Vagrant
libvirt provider using the [provider installation guide](https://vagrant-libvirt.github.io/vagrant-libvirt/installation.html).
Ensure your account can access the libvirt daemon before deploying.
VirtualBox is an optional alternative: `make deploy DISTRO=ubuntu2404 PROVIDER=virtualbox`.
Only amd64/x86_64 boxes are selected in v0.1.

| Target / selected provider | Pinned Vagrant box | Version | Architecture |
| --- | --- | --- | --- |
| Ubuntu 24.04 / libvirt | `bento/ubuntu-24.04` | `202508.03.0` | amd64 |
| Ubuntu 24.04 / VirtualBox | `cloud-image/ubuntu-24.04` | `20260926.0.0` | amd64 |
| Rocky Linux 9 / libvirt, VirtualBox | `rockylinux/9` | `6.0.0` | amd64 |

Box/provider metadata was read from the publisher's registry APIs on 2026-09-19:
[Bento Ubuntu metadata](https://vagrantcloud.com/api/v2/vagrant/bento/ubuntu-24.04)
and [Rocky metadata](https://vagrantcloud.com/api/v2/vagrant/rockylinux/9).
The newer Bento `202510.26.0` entry lacks libvirt, so v0.1 deliberately pins the
previous release. Box pins are reproducibility choices, not claims that the base
image is fully patched. Review updates before using the lab beyond isolated tests.
Canonical [stopped publishing Vagrant images starting with Ubuntu 24.04](https://ubuntu.com/docs/public-images/public-images-explanation/vagrant/);
Bento is a third-party image publisher recommended in [HashiCorp's box documentation](https://developer.hashicorp.com/vagrant/docs/boxes).

The Ubuntu VirtualBox override selects the third-party `cloud-image` box after
controlled local stability validation; it does not establish a Bento defect.
The exact [registry provider/version](https://vagrantcloud.com/api/v2/box/cloud-image/ubuntu-24.04/version/20260926.0.0/provider/virtualbox/amd64)
and the linked [build source](https://github.com/alchemy-solutions/vagrant-cloud-images)
were inspected before the image comparison. Provenance confidence is **MEDIUM**:
the publisher and repackaging pipeline are linked, but the registry supplies no
independent `.box` digest or exact artifact-to-input attestation. This is not an
official Canonical Vagrant box; a checksum for the upstream cloud image does not
authenticate the repackaged `.box`.

Ubuntu under VirtualBox intentionally declares **1 vCPU and 2048 MiB RAM**.
The current v0.1 controls, preflights and acceptance tests have no SMP or CPU-count
dependency, so one CPU is sufficient for this local validation scope. Both fresh
candidate guests reported one online CPU. No I/O APIC override is added.
Multi-vCPU behavior on this VirtualBox/WHP host remains outside the validated
local-lab contract; this is not a claim about production CPU topology. Ubuntu
libvirt and both Rocky provider configurations retain their original image pins
and two-CPU allocation.

The lab disables shared folders and inserts a fresh Vagrant SSH key. It uses the
provider's default management/NAT network without adding public networking.
`make deploy` records the selected distro/provider in `.lab/state.json`; subsequent
commands reuse it. Destroy the current lab before changing distribution/provider.
An interrupted deployment can be retried or cleaned up using `make destroy`.

Inventory is derived from `vagrant ssh-config`, with an explicit private-key path
and project-local `.lab/known_hosts`. The OpenSSH `accept-new` policy trusts a host
key on first connection to this disposable local VM and rejects changed keys.
It does not inherit Vagrant's permissive host-key options. For stricter identity
requirements, provision known host keys through a trusted channel before use.
The `.lab` directory and Vagrant-generated keys are ignored by Git. Destroy removes
the lab's connection metadata only after Vagrant successfully destroys the guest;
reports remain available.

## What container tests mean

`make molecule IMAGE=ubuntu:24.04` and `make molecule IMAGE=rockylinux:9` create
unprivileged disposable Docker containers, bootstrap Python if required, apply the
filesystem role to test files, verify observed ownership/modes, and execute
Molecule's second convergence idempotence check. A stricter file is preserved.
They also execute the real read-only planner with the source-mapped catalogue.
These tests use the real distribution userspace and real file state. They do not
run the complete host preflight or claim to test host sysctls, boot, reboot,
SELinux enforcement, AppArmor, kernel modules or mounted partitions. No host
directories are mounted into the test containers.

The GitHub-hosted CI matrix runs these filesystem tests. Full Vagrant validation
requires a dedicated Linux host with libvirt/KVM or VirtualBox; v0.1 does not add
a pretend VM job to hosted CI.

## Full VM acceptance procedure

On a disposable virtualization-capable host, run the following separately for each
distribution (destroy the previous VM before switching):

```sh
make deploy DISTRO=ubuntu2404
make status
make plan LEVEL=minimal
make harden LEVEL=minimal
make harden LEVEL=minimal       # inspect recap: changed=0
make verify LEVEL=minimal
make plan LEVEL=intermediary
make harden LEVEL=intermediary
make harden LEVEL=intermediary  # inspect recap: changed=0
make verify LEVEL=intermediary
vagrant reload                # deliberate reboot to validate persistence
make verify LEVEL=intermediary
make harden LEVEL=minimal      # confirm profile downgrade preserves stronger state
make verify LEVEL=intermediary
make destroy
```

Repeat with `DISTRO=rocky9`. Keep the emitted JSON/Markdown reports with the
Ansible recaps. A read-only or missing kernel feature must be reported explicitly,
not counted as a passing control. Audit/manual entries remain review items.
If reboot is reported as necessary, schedule it deliberately and re-run verification
after the VM comes back. Container success is not evidence of this VM procedure.
