"""Opt-in Testinfra checks against an already hardened, real supported VM.

Run only with --hosts=... and HARDENOPS_LIVE_TESTS=1 after make harden. Tests
inspect actual /proc and file metadata via Testinfra, independently of Ansible.
"""

import os
import shlex
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("HARDENOPS_LIVE_TESTS") != "1", reason="Requires an explicitly selected hardened VM")]


def load_controls():
    yaml = pytest.importorskip("yaml")
    path = Path(__file__).resolve().parents[2] / "controls" / "anssi_bp_028.yml"
    catalogue = yaml.safe_load(path.read_text(encoding="utf-8"))
    return catalogue["controls"] if isinstance(catalogue, dict) else catalogue


def require_applicable(control):
    levels = {"minimal": 0, "intermediary": 1, "enhanced": 2, "high": 3}
    selected = os.environ.get("HARDENOPS_LEVEL", "minimal")
    if selected not in {"minimal", "intermediary"}:
        pytest.fail("HARDENOPS_LEVEL must be minimal or intermediary")
    # Optional comma-separated IDs mirror config.disabled_controls in the report.
    disabled = [item.strip() for item in os.environ.get("HARDENOPS_DISABLED_CONTROLS", "").split(",") if item.strip()]
    if not set(disabled) <= {entry["id"] for entry in load_controls()}:
        pytest.fail("HARDENOPS_DISABLED_CONTROLS contains an unknown control ID")
    if control["id"] in disabled:
        pytest.skip("Explicit operator exception: " + control["id"])
    if levels[control["level"]] > levels[selected]:
        pytest.skip("Control is outside selected cumulative profile")
    for flag, default in (("HARDENOPS_ROUTING", "false"), ("HARDENOPS_IPV6_REQUIRED", "true")):
        if os.environ.get(flag, default) not in {"true", "false"}:
            pytest.fail(flag + " must be true or false")
    if control["applicability"].get("non_router") and os.environ.get("HARDENOPS_ROUTING", "false") == "true":
        pytest.skip("NOT_APPLICABLE: routing is enabled")
    if control["applicability"].get("ipv6_unused") and os.environ.get("HARDENOPS_IPV6_REQUIRED", "true") == "true":
        pytest.skip("NOT_APPLICABLE: IPv6 is required")


def deterministic_controls(verification_type):
    return [control for control in load_controls()
            if control["enforcement"]["status"] in {"AUTOMATED", "VERIFIED"}
            and control["verification"]["type"] == verification_type]


def test_supported_distribution(host):
    release = {}
    for line in host.file("/etc/os-release").content_string.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            parsed = shlex.split(value, comments=True)
            release[key] = parsed[0] if parsed else ""
    distro, version = release.get("ID"), release.get("VERSION_ID", "")
    assert (distro == "ubuntu" and version == "24.04") or (
        distro == "rocky" and version.split(".")[0] == "9"), release


@pytest.mark.parametrize("control", deterministic_controls("sysctl"), ids=lambda item: item["id"])
def test_selected_runtime_control(host, control):
    require_applicable(control)
    verification = control["verification"]
    key = verification["key"]
    runtime = host.file("/proc/sys/" + key.replace(".", "/"))
    if not runtime.exists:
        pytest.skip("UNSUPPORTED: kernel does not expose " + key)
    accepted = verification.get("accepted_values", [verification["expected"]])
    assert runtime.content_string.strip() in accepted
    owned_path = "/etc/sysctl.d/99-z-hardenops-%s.conf" % control["id"]
    persistent = host.file(owned_path)
    assert persistent.is_file and not persistent.is_symlink and persistent.user == "root"
    assert not (persistent.mode & 0o022)
    assignments = []
    for line in persistent.content_string.splitlines():
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        assert "=" in line, "Unparseable owned persistence content"
        assignments.append(line.split("=", 1))
    assert len(assignments) == 1
    assert assignments[0][0].strip() == key
    assert assignments[0][1].strip() == runtime.content_string.strip()
    assert not host.file("/etc/sysctl.d/90-hardenops-%s.conf" % control["id"]).exists
    if key == "fs.suid_dumpable" and host.file("/usr/lib/systemd/system/apport.service").exists:
        hook = host.file("/etc/systemd/system/apport.service.d/90-hardenops-suid-dumpable.conf")
        assert hook.is_file and not hook.is_symlink and hook.user == "root" and not (hook.mode & 0o022)
        assert hook.content_string == "[Service]\nExecStartPost=/usr/sbin/sysctl -p %s\n" % owned_path


@pytest.mark.parametrize("control", deterministic_controls("file"), ids=lambda item: item["id"])
def test_sensitive_file_permissions(host, control):
    require_applicable(control)
    verification = control["verification"]
    file = host.file(verification["path"])
    if not file.exists:
        pytest.skip("UNSUPPORTED: expected sensitive file is absent")
    assert file.is_file and not file.is_symlink
    assert file.user == "root"
    assert file.group in verification["allowed_groups"]
    assert not (file.mode & ~int(verification["max_mode"], 8))
