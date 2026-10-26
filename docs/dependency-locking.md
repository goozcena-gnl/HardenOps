# Reviewed Python dependency lock artifacts

These locks preserve a reviewed dependency snapshot. On the Phase 5 adoption
branch, `make install` selects the matching hashed lock for **CPython 3.12 or
3.13 on Linux x86_64**, runs `pip check`, and installs the Ansible Galaxy
collections using the same Python environment's scripts directory. The two
existing required `lint` and Molecule workflows select Python 3.12 and now
cache from [py312.txt](../locks/py312.txt). The
[candidate workflow](../.github/workflows/lock-validation.yml) separately
validates both Python versions. The two locks, direct pins, candidate
validation workflows, pyproject.toml and Dependabot configuration are unchanged.
This does not establish a security guarantee, certification or suitability for
production deployment.

## Scope and recorded results

| Artifact | Interpreter used | Platform | Packages |
| --- | --- | --- | --- |
| [py312.txt](../locks/py312.txt) | CPython 3.12.3 | Ubuntu 24.04.5, Linux x86_64 | 62 |
| [py313.txt](../locks/py313.txt) | CPython 3.13.16 | Ubuntu 24.04.5, Linux x86_64 | 61 |

Both were compiled independently with **pip-tools 7.6.2** and **pip 26.2.1**, using
PyPI and `--generate-hashes --allow-unsafe --resolver=backtracking`. The isolated
3.13 interpreter was installed with **uv 0.12.24**, using Astral's managed CPython
distribution. uv is not required to consume the locks.

The completed 2026-10-09 prototype installed each hashed lock into a fresh venv;
`pip check`, `make lint`, `make validate` and **111 unit tests** passed for each
interpreter. Separate hash-checked binary-only downloads found compatible wheels
for every package. Complete lock and installed-environment audits with
**pip-audit 2.10.1** reported no known vulnerabilities or unverified entries.
These are historical prototype results, not hosted CI results for this change.
The original prototype did not run Molecule, container or real-VM tests.
Candidate CI results must be assessed separately at their exact commit SHA.

The validated scope is Linux x86_64 on the recorded interpreters. Hashes for
other distributions or platforms do not prove compatibility on those platforms.
The latest baseline CI used Python 3.12.15; its observed package versions matched
the prototype's 3.12 lock, but the interpreter builds were different.

Recorded file SHA-256 values:

```text
7949e79bb98a2e548f3d44dd2127a07d22de60ebaa040744f215b5ef37a1908c  locks/py312.txt
ed2dc92e8ffae52e05a5928a4cdef7b71409ddcc5866a7269f80c5ab22197b3f  locks/py313.txt
```

From the repository root, inspect them with `sha256sum locks/py312.txt
locks/py313.txt`. File checksums identify the approved snapshot; package hashes
are separately verified during installation. A deliberate lock update changes
the file checksum and requires a new review.

## Direct input and temporary duplication

[requirements-dev.in](../requirements-dev.in) is a byte-identical copy of
requirements-dev.txt, including the same 11 exact direct pins. It is the input
to both reviewed locks. `make install` now consumes the selected lock instead of
`requirements-dev.txt`. The latter remains a mirrored direct-pin input for
Dependabot and the legacy `make hygiene` direct-dependency audit, but is no
longer the controller install source.

Until a separately reviewed change simplifies this input layout, every direct
dependency update must update both input files together, regenerate both
locks with the matching interpreters, and review the resulting transitive diff.
Reject a maintenance change that leaves these files inconsistent. The existing
candidate lock workflow checks their byte parity and all 11 direct lock pins.

Run this consistency check from the repository root:

```bash
cmp requirements-dev.txt requirements-dev.in
python3 - <<'PY'
from pathlib import Path
import re

pattern = re.compile(r"([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s\\;]+)")
def name(value):
    return re.sub(r"[-_.]+", "-", value).lower()

direct = {}
for line in Path("requirements-dev.in").read_text().splitlines():
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    match = pattern.fullmatch(line)
    assert match, f"Input must contain exact pins: {line}"
    key = name(match[1])
    assert key not in direct, f"Duplicate input: {key}"
    direct[key] = match[2]
assert len(direct) == 11

for file in ("locks/py312.txt", "locks/py313.txt"):
    pins = {}
    for line in Path(file).read_text().splitlines():
        match = pattern.match(line)
        if match:
            key = name(match[1])
            assert key not in pins, f"Duplicate lock pin: {key}"
            pins[key] = match[2]
    assert all(pins.get(key) == version for key, version in direct.items()), file
    print(f"{file}: all 11 direct pins match")
PY
```

This checks input bytes and direct versions. It does not replace full lock hash
coverage checks, dependency compatibility, audits or fresh-install validation.

## Why two independent resolutions are required

[pip-tools resolves conditional requirements in the compiler's environment](https://pip-tools.readthedocs.io/en/stable/).
The current shared package versions are identical. Python 3.12 additionally
requires `typing-extensions==4.16.0` because referencing 0.37.0 declares
`typing-extensions>=4.4.0; python_version < '3.13'`. That requirement is inactive
under 3.13. Compiling both files with one interpreter could erase this difference.
Do not infer the appropriate interpreter from the output filename alone.

## Controlled regeneration

Run from the repository root with both interpreters available. Use separate
disposable resolver venvs outside the checkout. These commands describe a future
maintenance operation; the reviewed artifacts in this change were copied intact
from the validated prototype.

```bash
umask 077
WORK="$(mktemp -d)"
export PIP_CONFIG_FILE=/dev/null
export PIP_INDEX_URL=https://pypi.org/simple
unset PIP_EXTRA_INDEX_URL PIP_TRUSTED_HOST
export PIP_CACHE_DIR="$WORK/pip-cache"

python3.12 tools/bootstrap_python.py prepare --venv "$WORK/resolver-py312"
python3.13 tools/bootstrap_python.py prepare --venv "$WORK/resolver-py313"
for minor in 312 313; do
  "$WORK/resolver-py$minor/bin/python" tools/bootstrap_python.py run -- \
    "$WORK/resolver-py$minor/bin/python" -m pip install \
    --index-url https://pypi.org/simple pip==26.2.2 pip-tools==7.6.2
  CUSTOM_COMPILE_COMMAND="pip-compile --generate-hashes --allow-unsafe --resolver=backtracking --index-url https://pypi.org/simple --no-emit-index-url --no-emit-trusted-host --output-file locks/py$minor.txt requirements-dev.in" \
    "$WORK/resolver-py$minor/bin/python" tools/bootstrap_python.py run -- \
    "$WORK/resolver-py$minor/bin/pip-compile" \
    --generate-hashes --allow-unsafe --resolver=backtracking \
    --index-url https://pypi.org/simple \
    --no-emit-index-url --no-emit-trusted-host \
    --output-file "locks/py$minor.txt" requirements-dev.in
done
```

Without `--upgrade`, pip-tools preferentially reuses compatible existing pins;
the prototype reproduced these files byte-for-byte in that mode. Fresh or
upgraded resolution is time-sensitive and can select newer transitives. Review
the whole diff, record the actual tool/interpreter versions and new checksums,
and validate each changed lock before acceptance. Do not remove hashes, disable
TLS checks or introduce another index to make an update succeed.

## Fresh installation and audits

For each lock, create a separate disposable validation venv with its matching
interpreter. For example, after setting WORK and the PyPI settings above:

```bash
python3.12 tools/bootstrap_python.py prepare --venv "$WORK/validation-py312"
PYTHON="$WORK/validation-py312/bin/python"
LOCK=locks/py312.txt
"$PYTHON" tools/bootstrap_python.py run -- "$PYTHON" -m pip install --index-url https://pypi.org/simple pip==26.2.2
"$PYTHON" tools/bootstrap_python.py run -- "$PYTHON" -m pip install --require-hashes -r "$LOCK"
"$PYTHON" -m pip check
"$PYTHON" tools/bootstrap_python.py run -- "$PYTHON" -m pip download --require-hashes --only-binary=:all: \
  -r "$LOCK" --dest "$WORK/wheels-py312"
"$PYTHON" tools/audit_locked.py --require-hashes -r "$LOCK"
"$PYTHON" tools/audit_locked.py --require-hashes --disable-pip -r "$LOCK"
"$PYTHON" tools/audit_locked.py
```

Repeat independently with python3.13, validation-py313, locks/py313.txt and a
separate wheel directory. pip-audit 2.10.1 is already pinned in both locks.
Keep raw findings and audit coverage; do not suppress findings merely to pass.

The standard lock audit in the prototype reported 60/59 packages, omitting pip
and packaging. The documented [already-resolved input audit](https://github.com/pypa/pip-audit#usage)
with `--require-hashes --disable-pip` covered all 62/61 pins; installed-environment
audits also covered all packages. This mode checks resolved entries without a
pip installation step. It must accompany actual hash-checked installation and
artifact validation, not substitute for them. A zero exit code alone does not
establish complete coverage or absence of unknown vulnerabilities.

## Candidate lock validation in CI

The separate [candidate workflow](../.github/workflows/lock-validation.yml)
uses Linux x86_64 runners, with Python 3.12 and 3.13 selected explicitly.
It verifies identical direct inputs and lock pins, installs each matching lock
into a disposable venv with `--require-hashes --only-binary=:all:`, runs
`pip check`, audits the full lock and installed environment, then runs static
validation and unit tests under each interpreter. A four-job Molecule matrix
tests both locked Python controllers against Ubuntu 24.04 and Rocky Linux 9,
including idempotence and final container destruction. The pip cache uses the
matching lock file as its dependency key. Its automated parity check verifies
identical direct inputs and all 11 direct pins, not transitive lock freshness.

The candidate workflow runs on pull requests, pushes to `main`, and manual
dispatch. Its checks are supplementary and are not required by the existing
main ruleset. The required `lint` and two Molecule jobs now install
the Python 3.12 lock via `make install`. The `hygiene` job still installs its
two standalone pinned scanners and audits the direct requirements file; the
candidate lock jobs separately audit both full locks. Candidate CI execution
is separate from the 2026-10-09 prototype: examine actual workflow results
before claiming that a given lock or Molecule matrix has passed. Full real-VM
validation is still out of scope; Galaxy collection dependencies remain
outside the Python lock boundary.

## Candidate graph closure gate

The additional optional
[graph workflow](../.github/workflows/lock-graph-validation.yml) uses a separate
Python 3.12/3.13 matrix. It pins pip 26.2.1, pip-tools 7.6.2, pytest 9.1.1 and
their compiler/test dependencies, uses PyPI with its normal TLS verification,
and verifies the running interpreter minor before resolution. These are
isolated compiler dependencies, not changes to the 11 production direct pins.

Each job copies its matching committed lock to a disposable reference file and
recompiles requirements-dev.in under its own interpreter, without `--upgrade`.
The [comparator](../tools/check_lock_graph.py) requires byte-identical direct
inputs, 11 exact unmarked direct pins, the expected unique Python header,
exactly pinned packages and SHA-256 hashes. It rejects unsupported directives,
URLs, duplicated packages and duplicated or malformed hashes. It compares the
entire package-name set, versions, normalized extras, formatted markers and
complete hash sets. Comments and generator-command formatting are ignored.
Marker formatting is normalized by packaging; this is not a general proof of
logical equivalence between different marker expressions.

For a retained independent reference, run from the repository root:

```bash
python tools/check_lock_graph.py --python 3.13 \
  --lock locks/py313.txt --independent /tmp/reference-py313.txt
python -m pytest -q tests/test_check_lock_graph.py
```

Repeat the independent compilation and comparison with Python 3.12 and its own
lock/reference. A matching header alone does not authenticate the interpreter;
retain the actual interpreter/version and compilation command evidence.

This gate measures closure consistency, not the newest available versions.
Without `--upgrade`, the resolver can keep an authentic, still-compatible older
transitive pin. A comparator rejects that pin when the independent reference
differs, but does not reject two matching older graphs solely because they are
old. Use explicit targeted updates and advisory review for freshness. Hashes
prove artifact identity, not absence of vulnerabilities or malicious code.

The 15 offline tests include positive and negative cases. They are explicitly
selected by the graph workflow: the existing pytest testpaths configuration
selects tests/unit for `make test`, so it does not automatically collect this
new top-level test module. Run both suites when reviewing a maintenance change.
Hosted graph jobs and all existing checks must be inspected on an eventual PR's
exact head. This preparation does not create a PR, change GitHub rules or claim
hosted validation. The new graph jobs remain optional.

The completed 2026-10-11 local Phase 4D trials used CPython 3.12.3 and 3.13.16,
pip-tools 7.6.2 and pip 26.2.1. Both actual baseline locks matched their independent
62/61-package graphs and all 1012/1010 SHA-256 values. The 15 supplied offline tests
passed under both interpreters. Fifteen additional distinct injections into
copies of the real locks were rejected for the intended reason under both
interpreters, including absent/extra transitives, altered versions, hashes,
extras and markers, malformed or duplicated entries and direct-input divergence.
The retained actual Phase 4C bad 3.13 output was independently rechecked and
rejected for its extra typing-extensions entry. The authentic packaging 26.2
freshness fixture was retained by no-upgrade resolution and passed its matching
graph comparison, confirming the limitation above.

Local `make lint validate test` passed under both interpreters with 111 tests.
An explicit combined run of tests/unit and the new module passed 126 tests under
each interpreter. These are local preparation results, not hosted CI evidence
for a published commit. They were recorded before the Phase 5 Makefile adoption and do not expand the
project's support/security guarantees.

## Reviewing Dependabot and security updates

The existing weekly pip configuration scans the repository root. These new
files may change the files discovered by the next scheduled updater, even though
its settings have not changed. A hosted update of this exact layout has not been
tested. Review every affected file and require both locks to remain consistent
with both direct-input files.

The 2026-10-11 Phase 4C isolated integration test executed the real official
Dependabot fetcher, parser, matcher and pip-compile updater at revision
`4725d253a379379dc85d291268d9607977b3c1af`. Its official image was pinned by
digest and verified signed provenance. That runtime used pip-tools 7.6.1;
independent reference resolutions used the reviewed compiler 7.6.2.

The updater selected Python 3.12.13 for the whole operation and regenerated both
locks with that interpreter. In a fixture-only requests 2.34.2 to 2.34.1 change,
the 3.12 graph and hash sets matched the independent reference. The 3.13 output
incorrectly included `typing-extensions==4.16.0`, producing 62 entries instead of
61. It changed the `.in` input but left requirements-dev.txt unchanged; existing
candidate CI catches that byte divergence. This measured result establishes an
incompatibility for the tested layout and pinned updater, not a claim about all
future Dependabot versions or a hosted update execution.

Separate Phase 4C fixtures showed that an unnecessary hashed package and a
still-compatible older transitive can pass direct-input checks, hashed
installation, pip check and all three audits. Those checks do not prove an exact
dependency closure or freshness. The
[pinned updater implementation](https://github.com/dependabot/dependabot-core/blob/4725d253a379379dc85d291268d9607977b3c1af/python/lib/dependabot/python/file_updater/pip_compile_file_updater.rb)
and its
[Python selection](https://github.com/dependabot/dependabot-core/blob/4725d253a379379dc85d291268d9607977b3c1af/python/lib/dependabot/python/file_parser/python_requirement_parser.rb)
explain why the first matching compiled-file Python header determines the
interpreter for both outputs. Output filenames and retained comments do not
prove which interpreter executed a compilation.

Do not merge an update solely because a bot refreshed both output files. Require
regeneration with the reviewed compiler and matching interpreters, full diff
inspection, input consistency, fresh hashed installs, binary-only checks, audits
of all lock entries and installed packages, and the applicable tests. The required `lint` and Molecule jobs now consume `locks/py312.txt` through
`make install`; the standalone hygiene job continues to audit the mirrored
direct requirements. The candidate lock jobs also exercise both locks and must
be inspected independently for dependency updates.

For a transitive advisory, identify the affected package/version and patched
range from primary advisory evidence. Perform a targeted reviewed
`--upgrade-package PACKAGE==VERSION` regeneration for each affected interpreter,
then audit and test the resulting graph. Do not hand-edit a pin while leaving
its old hashes, relax a direct pin silently, or suppress the finding. If a fixed
transitive version conflicts with a direct requirement, stop for an explicit
direct dependency compatibility decision. Routine global `--upgrade` updates
need a broader dependency review. Keep Black and other tool transitives within
these audits; a direct dependency's lower bound is not a safety guarantee.

## Galaxy and adoption limitations

[requirements.yml](../requirements.yml) is separate from these Python locks.
It pins ansible.posix 2.2.2 and community.docker 5.3.0, but their transitive
Galaxy graph and collection artifact hashes are not fully locked. The prototype
also installed community.library_inventory_filtering_v1 1.1.5 through Galaxy
dependency resolution. These Python hashes neither pin nor audit that collection
graph. Galaxy reproducibility requires separate review and validation.

The Phase 5 Makefile installation now selects one of the two hashed locks via
[select_controller_lock.py](../tools/select_controller_lock.py). It fails closed
outside CPython 3.12/3.13 on Linux x86_64; it does not install new interpreters
or change existing environments automatically. Run `make install` only in a
fresh, explicitly activated disposable venv (or a reviewed new controller venv).
The prior `requirements-dev.txt` installation remains available in Git
history for a controlled rollback. No historical `v0.1.0` artifact changes.

Making candidate jobs required by branch protection, ensuring full transitive
lock freshness and making Dependabot regenerate under the correct two
interpreters remain separate maintenance work. The `.in` duplication remains
a coordinated obligation. Galaxy transitive packages and real VM behavior
remain outside the Python lock guarantee. Retain all support boundaries.


## Proposed guarded Dependabot lock preparation (Phase 6)

The proposed `prepare-dependabot-locks.yml` workflow prepares a review artifact
for an open, same-repository Dependabot pip PR targeting main. Automatic events
are opened, synchronize and reopened; manual workflow_dispatch requires main,
a PR number and its exact 40-character head SHA. It checks out the trusted base
commit with persist-credentials disabled and requests only contents: read and
pull-requests: read. It does not check out or execute scripts from the PR branch,
push a commit, merge a PR, change repository rules or access repository secrets.

The preflight requires eleven exact direct pins, exactly one changed version
line, matching input bytes on the trusted base, eligible bot/branch/repository
metadata and matching expected head/base SHAs. Only the four dependency paths
are permitted. The validated candidate input is mirrored to both direct files;
the PR's generated locks are not trusted or reused. The matching trusted locks
are recompiled under actual Python 3.12 and 3.13 with pip-tools 7.6.2, pip 26.2.1,
generate-hashes, no-reuse-hashes and no upgrade. Each result is recompiled into a
separate reference and compared for exact graph and complete hash-set equality.

The workflow produces requirements-dev.in, requirements-dev.txt, locks/py312.txt
and locks/py313.txt, plus manifest.json and README.txt, for a seven-day Actions
review artifact. The manifest records the PR number, base/head and file SHA-256
values. This is a proposal for maintainer review, not an installed or accepted
dependency update. Independent compiler/test dependencies are wheel-only pins;
those bootstrap pins themselves are not a hashed compiler-environment lock.

Before applying an artifact, independently re-read the open PR and current main
and compare both SHAs to the manifest. If either moved, rerun preparation. The
current prototype validates metadata before resolution but does not re-read it
immediately before upload; it must not be described as eliminating the race
during a long resolution. Never apply a stale artifact. Verify every checksum,
inspect all four diffs and review the complete transitive graph and advisories.
Any later application needs a separate maintainer-controlled commit and normal
push, followed by all applicable CI at that new head and explicit merge approval.

Local WSL tests of API reads and bundle creation cannot establish actual
Dependabot event delivery, GITHUB_TOKEN scopes, artifact upload/retention or the
GitHub approval model. These remain hosted acceptance gates after code review
and separate authorization, using a legitimate eligible bot PR or controlled
test. PR #14 must pass its own normal CI before any future merge. Repository
rules stay unchanged; candidate checks are not automatically made required.

No-upgrade resolution may retain compatible older transitives. Hash equality
proves artifact identity and graph consistency, not freshness or freedom from
vulnerabilities. The workflow itself does not run pip-audit or fresh candidate
lock installations; the local gate and future candidate CI perform those
separate checks. Galaxy dependency reproducibility and real-VM behavior remain
outside this workflow. Existing controllers, approved dependency files, main
and immutable v0.1.0 remain unchanged during preparation.


## Authenticated Python bootstrap

The bootstrap helper uses only the standard library before installing any package.
It downloads the reviewed pip 26.2.2 universal wheel through an explicit public CA
bundle copied unchanged from certifi 2026.10.19, checks the fixed SHA-256, rejects
all redirects, and installs from a private verified snapshot with no index,
dependencies or network access. It never modifies a base Python or system CA store.
The bootstrap CA file and its MPL notice live in `tools/bootstrap/`; updating that
trust snapshot requires review and a corresponding hash change. No certificate
authority is issued or managed by HardenOps.

Use `python3 tools/bootstrap_python.py prepare --venv .venv`, then activate that
venv. `make install` authenticates the cached wheel before seeding the active venv
and hash-installing its selected lock. The target workspace and venv must be
administrator-controlled Linux directories. Cache corruption fails closed rather
than silently replacing unexpected bytes. A missing network cannot establish TLS
safety: provide the authenticated wheel offline or retry through the approved TLS
path. Ambient proxy configuration is not used by the initial downloader.

Run each of the same three audits through `python tools/audit_locked.py`: the
resolved hashed lock, the hashed lock with `--disable-pip`, and the installed
environment. No gate is removed. The wrapper requires pip-audit 2.10.1, replaces
only its temporary-environment seed with the authenticated wheel, and delegates
to its original resolver and advisory engine. Both requirements and project
sources use the adapter. A process constraint keeps pip at 26.2.2 during the
auditor's auxiliary upgrade; all direct dependency pins remain unchanged.

The wrapper and `bootstrap_python.py run -- COMMAND` use a private approved CA
snapshot and empty OpenSSL capath for their subprocesses. They do not certify
other applications' stores or alter WSL/Windows trust. The audited requirement
and project files remain trusted administrator-reviewed configuration. Use only
the configured HTTPS indexes and no trusted-host/TLS-bypass directives.
GitHub jobs create isolated controller/compiler venvs before package downloads;
actual runner images and stores require hosted validation at the final revision.
