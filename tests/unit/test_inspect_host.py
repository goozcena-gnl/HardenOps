"""Host-state decision tests use synthetic Linux metadata, never harden the test host."""

import copy
import importlib.util
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE = Path(__file__).resolve().parents[2] / "tools" / "inspect_host.py"
SPEC = importlib.util.spec_from_file_location("inspect_host", MODULE)
inspector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspector)


class MemoryReader:
    def __init__(self):
        self.files = {}
        self.commands = []
        self.command_output = {"available": True, "lines": ["nginx.service enabled", "sshd.service enabled"]}
        self.directory_entries = {}

    def add(self, path, text="", mode=0o644, uid=0, gid=0, kind=stat.S_IFREG):
        self.files[path] = (text, SimpleNamespace(st_mode=kind | mode, st_uid=uid, st_gid=gid))

    def text(self, path, limit=256000):
        if path not in self.files:
            raise FileNotFoundError(path)
        text, metadata = self.files[path]
        if stat.S_ISLNK(metadata.st_mode):
            raise OSError("Symlink refused")
        return text

    def metadata(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path][1]

    def group_name(self, gid):
        return {0: "root", 42: "shadow", 100: "users"}.get(gid, str(gid))

    def command_runner(self, argv):
        self.commands.append(argv)
        return self.command_output

    def children(self, absolute, limit=5000):
        return self.directory_entries.get(absolute, []), 0, False


@pytest.fixture
def control():
    return {
        "id": "bp028_r9_kptr_restrict", "level": "intermediary", "domain": "kernel",
        "title": "Restrict kernel pointers", "description": "Kernel pointer visibility",
        "source": {"document": "ANSSI-BP-028", "recommendation": "R9", "page": 20},
        "enforcement": {"status": "AUTOMATED"},
        "applicability": {"os_families": ["Debian", "RedHat"]},
        "verification": {"type": "sysctl", "key": "kernel.kptr_restrict", "expected": "1", "accepted_values": ["1", "2"], "remediable_values": ["0"]},
        "reboot_required": False, "risk": "low",
    }


@pytest.fixture
def payload(control):
    return {"host": "unit.example", "controls": [control], "level": "intermediary",
            "config": {"workload_profile": "generic_server", "network": {"routing": False, "ipv6_required": True}},
            "facts": {"distribution": "Ubuntu", "distribution_version": "24.04", "os_family": "Debian",
                      "architecture": "x86_64", "kernel": "6.8.0-test"}}


def sysctl_reader(control, runtime="1", persisted="1"):
    reader = MemoryReader()
    reader.add("/proc/sys/kernel/kptr_restrict", runtime)
    if persisted is not None:
        reader.add("/etc/sysctl.d/99-z-hardenops-%s.conf" % control["id"], "kernel.kptr_restrict = %s\n" % persisted)
    return reader


def result(payload, reader):
    return inspector.inspect(payload, reader)["controls"][0]


def test_runtime_and_owned_persistence_pass(payload, control):
    report = inspector.inspect(payload, sysctl_reader(control))
    assert report["controls"][0]["result"] == "PASS"
    assert report["summary"]["results"]["PASS"] == 1
    assert report["summary"]["changes_required"] == 0
    assert report["controls"][0]["source"] == control["source"]


def test_stronger_explicitly_accepted_value_preserved(payload, control):
    finding = result(payload, sysctl_reader(control, "2", "2"))
    assert finding["result"] == "PASS"
    assert finding["desired"] == "2"


@pytest.mark.parametrize("runtime,persisted,desired", [("1", "2", "2"), ("2", "1", "2"), ("0", "2", "2"), ("0", "0", "1")])
def test_runtime_and_persistence_drift_keep_strongest_known_value(payload, control, runtime, persisted, desired):
    finding = result(payload, sysctl_reader(control, runtime, persisted))
    assert finding["result"] == "FAIL"
    assert finding["desired"] == desired
    assert finding["needs_change"] is True


def test_runtime_pass_is_not_enough_without_persistence(payload, control):
    finding = result(payload, sysctl_reader(control, persisted=None))
    assert finding["result"] == "FAIL"
    assert finding["observed"]["persistence"]["value"] is None


def test_legacy_migration_preserves_stronger_value_and_restricted_mode(payload, control):
    reader = sysctl_reader(control, "1", None)
    reader.add("/etc/sysctl.d/90-hardenops-%s.conf" % control["id"], "kernel.kptr_restrict=2\n", mode=0o400)
    finding = result(payload, reader)
    assert finding["result"] == "FAIL" and finding["needs_change"]
    assert finding["desired"] == "2" and finding["desired_persistence_mode"] == "0400"
    assert Path(finding["observed"]["persistence"]["path"]).name > "99-protect-links.conf"


@pytest.mark.parametrize("mode,uid,kind", [(0o666, 0, stat.S_IFREG), (0o644, 1000, stat.S_IFREG), (0o644, 0, stat.S_IFLNK)])
def test_unsafe_legacy_file_is_not_migrated(payload, control, mode, uid, kind):
    reader = sysctl_reader(control)
    reader.add("/etc/sysctl.d/90-hardenops-%s.conf" % control["id"], "kernel.kptr_restrict=1\n", mode=mode, uid=uid, kind=kind)
    finding = result(payload, reader)
    assert finding["result"] == "UNSUPPORTED" and not finding["needs_change"]


def test_matching_legacy_file_still_requires_migration(payload, control):
    reader = sysctl_reader(control)
    reader.add("/etc/sysctl.d/90-hardenops-%s.conf" % control["id"], "kernel.kptr_restrict=1\n")
    assert result(payload, reader)["needs_change"]


def apport_reader(control):
    control["verification"] = {"type": "sysctl", "key": "fs.suid_dumpable", "expected": "0", "accepted_values": ["0"], "remediable_values": ["1", "2"]}
    reader = MemoryReader()
    reader.add("/proc/sys/fs/suid_dumpable", "0")
    reader.add("/etc/sysctl.d/99-z-hardenops-%s.conf" % control["id"], "fs.suid_dumpable=0\n")
    reader.add("/usr/lib/systemd/system/apport.service", "[Service]\nExecStart=/usr/share/apport/apport --start\n")
    return reader


def test_apport_start_requires_its_owned_reapplication_hook(payload, control):
    reader = apport_reader(control)
    finding = result(payload, reader)
    assert finding["result"] == "FAIL" and finding["needs_change"]
    hook = finding["observed"]["persistence"]["apport"]
    assert hook["required"]
    reader.add(hook["path"], hook["content"], mode=0o400)
    finding = result(payload, reader)
    assert finding["result"] == "PASS"
    assert finding["observed"]["persistence"]["apport"]["mode"] == "0400"


@pytest.mark.parametrize("unsafe", ["symlink", "writable", "unexpected_content", "directory_symlink"])
def test_unsafe_apport_hook_is_never_replaced(payload, control, unsafe):
    reader = apport_reader(control)
    hook = result(payload, reader)["observed"]["persistence"]["apport"]
    reader.add(hook["path"], hook["content"])
    if unsafe == "symlink":
        reader.add(hook["path"], kind=stat.S_IFLNK)
    elif unsafe == "writable":
        reader.add(hook["path"], hook["content"], mode=0o666)
    elif unsafe == "unexpected_content":
        reader.add(hook["path"], "[Service]\nExecStartPost=/bin/true\n")
    else:
        reader.add("/etc/systemd/system/apport.service.d", kind=stat.S_IFLNK)
    finding = result(payload, reader)
    assert finding["result"] == "UNSUPPORTED" and not finding["needs_change"]


def test_missing_kernel_feature_is_unsupported(payload):
    finding = result(payload, MemoryReader())
    assert finding["result"] == "UNSUPPORTED"
    assert finding["needs_change"] is False


def test_unknown_larger_numeric_value_is_not_assumed_stronger(payload, control):
    finding = result(payload, sysctl_reader(control, "999", "999"))
    assert finding["result"] == "UNSUPPORTED"
    assert finding["needs_change"] is False


def test_persistence_unsafe_permissions_fail(payload, control):
    reader = sysctl_reader(control)
    reader.add("/etc/sysctl.d/99-z-hardenops-%s.conf" % control["id"], "kernel.kptr_restrict=1", mode=0o666)
    assert result(payload, reader)["result"] == "FAIL"


@pytest.mark.parametrize("content", ["kernel.kptr_restrict=1\nkernel.kptr_restrict=2", "kernel.kptr_restrict=1\nnet.ipv4.ip_forward=1", "invalid line", ""])
def test_ambiguous_persistence_is_never_reloaded(payload, control, content):
    reader = sysctl_reader(control)
    reader.add("/etc/sysctl.d/99-z-hardenops-%s.conf" % control["id"], content)
    finding = result(payload, reader)
    assert finding["result"] == "UNSUPPORTED"
    assert finding["needs_change"] is False


def test_persistent_symlink_is_never_overwritten(payload, control):
    reader = sysctl_reader(control)
    reader.add("/etc/sysctl.d/99-z-hardenops-%s.conf" % control["id"], kind=stat.S_IFLNK)
    finding = result(payload, reader)
    assert finding["result"] == "UNSUPPORTED"
    assert finding["needs_change"] is False


def test_stricter_persistence_permissions_preserved(payload, control):
    reader = sysctl_reader(control, "0", "1")
    reader.add("/etc/sysctl.d/99-z-hardenops-%s.conf" % control["id"], "kernel.kptr_restrict=1", mode=0o400)
    assert result(payload, reader)["desired_persistence_mode"] == "0400"


def test_yama_persisted_three_does_not_trigger_irreversible_runtime_escalation(payload, control):
    control["verification"].update(key="kernel.yama.ptrace_scope", accepted_values=["1", "2", "3"])
    reader = MemoryReader()
    reader.add("/proc/sys/kernel/yama/ptrace_scope", "1")
    reader.add("/etc/sysctl.d/99-z-hardenops-%s.conf" % control["id"], "kernel.yama.ptrace_scope=3")
    finding = result(payload, reader)
    assert finding["result"] == "UNSUPPORTED"
    assert finding["needs_change"] is False


def test_known_sysrq_bitmask_can_be_remediated(payload, control):
    control["verification"] = {"type": "sysctl", "key": "kernel.sysrq", "expected": "0", "accepted_values": ["0"], "remediable_range": [1, 511]}
    reader = MemoryReader()
    reader.add("/proc/sys/kernel/sysrq", "176")
    finding = result(payload, reader)
    assert finding["result"] == "FAIL"
    assert finding["desired"] == "0"


def test_profile_selection_is_cumulative(payload, control):
    lower = copy.deepcopy(control)
    lower.update(id="bp028_minimal_test", level="minimal")
    payload["controls"].append(lower)
    payload["level"] = "minimal"
    report = inspector.inspect(payload, MemoryReader())
    assert [entry["result"] for entry in report["controls"]] == ["NOT_APPLICABLE", "UNSUPPORTED"]
    payload["level"] = "intermediary"
    assert all(entry["result"] == "UNSUPPORTED" for entry in inspector.inspect(payload, MemoryReader())["controls"])


@pytest.mark.parametrize("condition,field,value", [("non_router", "routing", True), ("ipv6_unused", "ipv6_required", True)])
def test_network_conditions_exclude_controls(payload, control, condition, field, value):
    control["applicability"][condition] = True
    payload["config"]["network"][field] = value
    assert result(payload, MemoryReader())["result"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("level", ["enhanced", "high", "invalid", None])
def test_unknown_and_future_profiles_rejected(payload, level):
    payload["level"] = level
    with pytest.raises(ValueError, match="Only minimal and intermediary"):
        inspector.inspect(payload)


@pytest.mark.parametrize("value", ["false", 0, None, [], {}])
def test_network_flags_require_actual_booleans(payload, value):
    payload["config"]["network"]["routing"] = value
    with pytest.raises(ValueError, match="must be a Boolean"):
        inspector.inspect(payload)


def test_unknown_workload_is_rejected(payload):
    payload["config"]["workload_profile"] = "router"
    with pytest.raises(ValueError, match="generic_server"):
        inspector.inspect(payload)


def test_explicit_operator_exception_is_not_applicable(payload, control):
    payload["config"]["disabled_controls"] = [control["id"]]
    finding = result(payload, sysctl_reader(control))
    assert finding["result"] == "NOT_APPLICABLE"
    assert "operator" in finding["reason"]


@pytest.mark.parametrize("disabled", [["bp028_typo"], "bp028_r9_kptr_restrict", [None], ["bp028_r9_kptr_restrict"] * 2])
def test_unknown_or_malformed_exceptions_rejected(payload, disabled):
    payload["config"]["disabled_controls"] = disabled
    with pytest.raises(ValueError, match="disabled_controls"):
        inspector.inspect(payload)


@pytest.mark.parametrize("distribution,version,family", [("Fedora", "44", "RedHat"), ("Ubuntu", "22.04", "Debian"), ("Debian", "12", "Debian"), ("Rocky", "10", "RedHat"), ("Ubuntu", "24.04", "RedHat")])
def test_unsupported_distributions_fail_closed(payload, distribution, version, family):
    payload["facts"].update(distribution=distribution, distribution_version=version, os_family=family)
    with pytest.raises(ValueError, match="Unsupported distribution"):
        inspector.inspect(payload)


def test_supported_rocky_minor_version(payload):
    payload["facts"].update(distribution="Rocky", distribution_version="9.6", os_family="RedHat")
    assert result(payload, MemoryReader())["result"] == "UNSUPPORTED"


def test_report_uses_ansible_detected_host_and_transition_metadata(payload, control):
    payload.pop("host")
    payload["facts"]["host"] = "inventory-host"
    control.update(reversible=True, transition="reversible")
    report = inspector.inspect(payload, MemoryReader())
    assert report["host"] == "inventory-host"
    assert report["controls"][0]["reversible"] is True
    assert report["controls"][0]["transition"] == "reversible"


def test_duplicate_control_id_rejected(payload, control):
    payload["controls"].append(copy.deepcopy(control))
    with pytest.raises(ValueError, match="Duplicate"):
        inspector.inspect(payload)


@pytest.mark.parametrize("key", ["kernel/../passwd", "/etc/shadow", "kernel.ptr;id"])
def test_sysctl_path_injection_rejected(payload, control, key):
    control["verification"]["key"] = key
    with pytest.raises(ValueError, match="Invalid sysctl key"):
        inspector.inspect(payload)


def file_control(control):
    control["verification"] = {"type": "file", "path": "/etc/shadow", "max_mode": "0640", "allowed_groups": ["root", "shadow"]}


def test_stronger_file_mode_and_valid_group_preserved(payload, control):
    file_control(control)
    reader = MemoryReader()
    reader.add("/etc/shadow", mode=0o400, gid=42)
    finding = result(payload, reader)
    assert finding["result"] == "PASS"
    assert finding["desired_mode"] == "0400"
    assert finding["desired_group"] == "shadow"


def test_file_mode_intersection_removes_without_adding_bits(payload, control):
    file_control(control)
    reader = MemoryReader()
    reader.add("/etc/shadow", mode=0o406, gid=100)
    finding = result(payload, reader)
    assert finding["result"] == "FAIL"
    assert finding["desired_mode"] == "0400"
    assert finding["desired_group"] == "root"


def test_non_root_file_ownership_fails(payload, control):
    file_control(control)
    reader = MemoryReader()
    reader.add("/etc/shadow", mode=0o600, uid=1000)
    assert result(payload, reader)["result"] == "FAIL"


def test_sensitive_symlink_is_not_followed(payload, control):
    file_control(control)
    reader = MemoryReader()
    reader.add("/etc/shadow", kind=stat.S_IFLNK)
    finding = result(payload, reader)
    assert finding["result"] == "UNSUPPORTED"
    assert finding["needs_change"] is False


def test_missing_sensitive_file_is_never_created(payload, control):
    file_control(control)
    finding = result(payload, MemoryReader())
    assert finding["result"] == "UNSUPPORTED"
    assert finding["needs_change"] is False


def test_verified_control_failure_is_not_queued_for_enforcement(payload, control):
    control["enforcement"]["status"] = "VERIFIED"
    finding = result(payload, sysctl_reader(control, "0", "0"))
    assert finding["result"] == "FAIL"
    assert finding["needs_change"] is False


def test_account_audit_does_not_read_or_publish_password_fields(payload, control):
    control["enforcement"]["status"] = "AUDIT_ONLY"
    control["verification"] = {"type": "audit", "check": "accounts"}
    reader = MemoryReader()
    reader.add("/etc/passwd", "root:FORBIDDEN:0:0:private:/root:/bin/bash\ndaemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin\n")
    finding = result(payload, reader)
    assert finding["result"] == "AUDIT_ONLY"
    assert finding["observed"]["uid_zero_accounts"] == ["root"]
    assert "FORBIDDEN" not in str(finding)
    assert "private" not in str(finding)


def test_service_inventory_never_becomes_pass(payload, control):
    control["enforcement"]["status"] = "AUDIT_ONLY"
    control["verification"] = {"type": "audit", "check": "services"}
    reader = MemoryReader()
    finding = result(payload, reader)
    assert finding["result"] == "AUDIT_ONLY"
    assert finding["observed"]["count"] == 2
    assert reader.commands[0][0] == "systemctl"


def test_world_writable_directory_requires_sticky_and_root_owner(payload, control):
    control["enforcement"]["status"] = "AUDIT_ONLY"
    control["source"]["recommendation"] = "R54"
    control["verification"] = {"type": "audit", "check": "filesystem"}
    reader = MemoryReader()
    reader.add("/tmp", mode=0o1777, uid=1000, kind=stat.S_IFDIR)
    reader.add("/var/tmp", mode=0o1777, uid=0, kind=stat.S_IFDIR)
    finding = result(payload, reader)
    candidates = finding["observed"]["candidates"]
    assert finding["result"] == "AUDIT_ONLY"
    assert candidates[0]["sticky"] is True
    assert candidates[0]["root_owned"] is False
    assert candidates[0]["protection_satisfied"] is False
    assert candidates[1]["protection_satisfied"] is True


def test_unknown_owner_audit_includes_files_and_directories(payload, control):
    control["enforcement"]["status"] = "AUDIT_ONLY"
    control["source"]["recommendation"] = "R53"
    control["verification"] = {"type": "audit", "check": "filesystem"}
    reader = MemoryReader()
    reader.add("/tmp", mode=0o1777, kind=stat.S_IFDIR)
    reader.add("/etc/passwd", "root:x:0:0:root:/root:/bin/bash\n")
    reader.add("/etc/group", "root:x:0:\n")
    reader.add("/tmp/orphan-dir", uid=1234, kind=stat.S_IFDIR)
    reader.add("/tmp/orphan-file", gid=1234)
    reader.directory_entries["/tmp"] = [(name, reader.metadata(name)) for name in ("/tmp/orphan-dir", "/tmp/orphan-file")]
    finding = result(payload, reader)
    assert finding["observed"]["candidate_count"] == 2
    assert finding["observed"]["complete_system_scan"] is False
    assert "external NSS" in finding["observed"]["identity_scope"]


@pytest.mark.parametrize("status", ["MANUAL", "FUTURE", "OUT_OF_SCOPE_REFERENCE_REQUIRED"])
def test_deferred_statuses_are_explicit(payload, control, status):
    control["enforcement"]["status"] = status
    assert result(payload, MemoryReader())["result"] == status


def test_real_filesystem_reader_uses_fixture_root(tmp_path):
    path = tmp_path / "etc"
    path.mkdir()
    (path / "group").write_text("shadow:x:42:\n", encoding="utf-8")
    reader = inspector.HostReader(tmp_path)
    assert reader.group_name(42) == "shadow"
    assert reader.text("/etc/group") == "shadow:x:42:\n"


def test_bounded_reader_refuses_oversized_file(tmp_path):
    (tmp_path / "large").write_text("12345", encoding="utf-8")
    with pytest.raises(OSError, match="Read limit"):
        inspector.HostReader(tmp_path).text("/large", limit=4)


def test_subprocess_timeout_is_audit_evidence(monkeypatch):
    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 15
        assert "shell" not in kwargs
        raise inspector.subprocess.TimeoutExpired(args[0], 15)
    monkeypatch.setattr(inspector.subprocess, "run", timeout)
    assert inspector.run_command(["systemctl", "list-unit-files"])["available"] is False
