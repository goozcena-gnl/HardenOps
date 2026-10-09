# Reviewed Python dependency lock artifacts

These locks preserve a reviewed dependency snapshot. They are not yet adopted
by `make install` or GitHub Actions: [requirements-dev.txt](../requirements-dev.txt)
still drives existing installations. The Makefile, workflows, pyproject.toml and
Dependabot configuration are unchanged. This page does not establish a security
guarantee, certification or suitability for production deployment.

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
No Molecule, container or real-VM validation of these locks has occurred.

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
to the two prototype locks. requirements-dev.txt remains the source for existing
installation commands; the duplicate `.in` file does not change their behavior.

Until a separately reviewed adoption change removes this duplication, every
direct dependency update must update both input files together, regenerate both
locks with the matching interpreters, and review the resulting transitive diff.
Reject a maintenance change that leaves these files inconsistent. No automated
CI drift gate has been added in this phase.

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

python3.12 -m venv "$WORK/resolver-py312"
python3.13 -m venv "$WORK/resolver-py313"
for minor in 312 313; do
  "$WORK/resolver-py$minor/bin/python" -m pip install \
    --index-url https://pypi.org/simple pip==26.2.1 pip-tools==7.6.2
  CUSTOM_COMPILE_COMMAND="pip-compile --generate-hashes --allow-unsafe --resolver=backtracking --index-url https://pypi.org/simple --no-emit-index-url --no-emit-trusted-host --output-file locks/py$minor.txt requirements-dev.in" \
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
python3.12 -m venv "$WORK/validation-py312"
PYTHON="$WORK/validation-py312/bin/python"
LOCK=locks/py312.txt
"$PYTHON" -m pip install --index-url https://pypi.org/simple pip==26.2.1
"$PYTHON" -m pip install --require-hashes -r "$LOCK"
"$PYTHON" -m pip check
"$PYTHON" -m pip download --require-hashes --only-binary=:all: \
  -r "$LOCK" --dest "$WORK/wheels-py312"
"$PYTHON" -m pip_audit --require-hashes -r "$LOCK"
"$PYTHON" -m pip_audit --require-hashes --disable-pip -r "$LOCK"
"$PYTHON" -m pip_audit
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

## Reviewing Dependabot and security updates

The existing weekly pip configuration scans the repository root. These new
files may change the files discovered by the next scheduled updater, even though
its settings have not changed. A hosted update of this exact layout has not been
tested. Review every affected file and require both locks to remain consistent
with both direct-input files.

[GitHub documents pip-compile support](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference)
but lists compiler 7.5.3, whereas this snapshot uses 7.6.2. The
[Dependabot updater implementation](https://github.com/dependabot/dependabot-core/blob/main/python/lib/dependabot/python/file_updater/pip_compile_file_updater.rb)
supports multiple outputs from one input while selecting one Python version for
the operation. That is a source-based compatibility concern, not proof that a
hosted update will fail. Correct file discovery, compiler options, hash retention
and independent 3.12/3.13 resolution remain approval gates for future adoption.

Do not merge an update solely because a bot refreshed both output files. Require
regeneration with the reviewed compiler and matching interpreters, full diff
inspection, input consistency, fresh hashed installs, binary-only checks, audits
of all lock entries and installed packages, and the applicable tests. Existing
hosted workflows still install requirements-dev.txt, so their success does not
demonstrate that either new lock was consumed.

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

Production adoption, interpreter selection in the Makefile, workflow matrix
changes, cache keys based on each matching lock and automated drift checks are
future work. The `.in` duplication remains a manual review gate until then.
Retain the existing release and support boundaries; this artifact preparation
does not expand supported platforms or infrastructure guarantees.
