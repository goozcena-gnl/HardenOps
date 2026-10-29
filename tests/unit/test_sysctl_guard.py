"""Linux descriptor/race fixtures: no call ever changes a real kernel setting.

Run the filesystem tests as root in a disposable container; ordinary CI still
executes synthetic refusal tests in test_inspect_host and metadata tests here.
"""

import copy
import os
import stat
from types import SimpleNamespace

import pytest

from tools import inspect_host as inspector
from tools import sysctl_guard as guard


@pytest.mark.parametrize("mode,uid,links", [(0o666, 0, 1), (0o644, 1000, 1), (0o644, 0, 2)])
def test_unsafe_metadata_is_never_trusted(mode, uid, links):
    metadata = SimpleNamespace(st_mode=stat.S_IFREG | mode, st_uid=uid, st_nlink=links)
    assert not guard.safe_metadata(metadata)


@pytest.fixture
def root(tmp_path):
    if os.name != "posix" or os.geteuid() != 0:
        pytest.skip("Real root-owned inode fixtures require a disposable Linux root container")
    tmp_path.chmod(0o755)
    for directory in ("etc/sysctl.d", "etc/systemd/system", "usr/lib/systemd/system"):
        (tmp_path / directory).mkdir(parents=True, mode=0o755)
    return tmp_path


class Reader(inspector.HostReader):
    def __init__(self, root, runtime):
        super().__init__(root)
        self.runtime = runtime

    def text(self, absolute, limit=256_000):
        if absolute.startswith("/proc/sys/"):
            return self.runtime
        return super().text(absolute, limit)


def policy(key="kernel.kptr_restrict", accepted=None):
    accepted = accepted or ["2"]
    return {"id": "bp028_r9_kptr_restrict", "enforcement": "AUTOMATED",
            "verification": {"key": key, "expected": accepted[0], "accepted_values": accepted,
                             "remediable_values": ["1", "2"] if key == "fs.suid_dumpable" else ["0", "1"]}}


def owned(root, content="kernel.kptr_restrict=2\n", mode=0o644, legacy=False):
    prefix = "90-hardenops" if legacy else "99-z-hardenops"
    path = root / (f"etc/sysctl.d/{prefix!s}-bp028_r9_kptr_restrict.conf")
    path.write_text(content)
    path.chmod(mode)
    return path


def decision(root, runtime="2", control=None):
    control = copy.deepcopy(control or policy())
    control.update(inspector.inspect_sysctl(control, Reader(root, runtime)))
    return control


def apply(root, control, runtime, calls, check=False):
    return guard.apply_control(control, root=root, check=check,
                               read_runtime=lambda key: runtime,
                               set_runtime=lambda key, value: calls.append((key, value)))


@pytest.mark.parametrize("uid,mode,parent", [(0, 0o777, True), (0, 0o666, False), (1000, 0o644, False)])
def test_three_audit_reproductions_refused_without_activation(root, uid, mode, parent):
    path = owned(root)
    target = path.parent if parent else path
    target.chmod(mode)
    os.chown(target, uid, 0)
    control = decision(root)
    assert control["result"] == "UNSUPPORTED" and not control["needs_change"]
    with pytest.raises(OSError):
        guard.snapshot_file("/" + str(path.relative_to(root)), root)


@pytest.mark.parametrize("parent", ["etc", "etc/sysctl.d"])
def test_intermediate_symlinks_refused_even_when_destination_is_safe(root, parent):
    path = root / parent
    destination = path.with_name(path.name + "-real")
    path.rename(destination)
    path.symlink_to(destination, target_is_directory=True)
    assert decision(root)["result"] == "UNSUPPORTED"


@pytest.mark.parametrize("kind", ["symlink", "fifo", "hardlink", "directory"])
def test_untrusted_leaf_types_refused(root, kind):
    target = owned(root)
    if kind == "hardlink":
        os.link(target, target.with_suffix(".other"))
    else:
        target.unlink()
        if kind == "symlink":
            outside = root / "sentinel"
            outside.write_text("must remain untouched")
            target.symlink_to(outside)
        elif kind == "fifo":
            os.mkfifo(target)
        else:
            target.mkdir()
    assert decision(root)["result"] == "UNSUPPORTED"


@pytest.mark.parametrize("mutation", ["replace", "extra_key", "symlink", "permissions", "parent"])
def test_changed_plan_refused_before_any_write_or_activation(root, mutation):
    target = owned(root, "kernel.kptr_restrict=0\n")
    control = decision(root, "0")
    if mutation == "replace":
        other = target.with_suffix(".replacement")
        other.write_text(target.read_text())
        other.replace(target)
    elif mutation == "extra_key":
        target.write_text("kernel.kptr_restrict=0\nnet.ipv4.ip_forward=1\n")
    elif mutation == "symlink":
        target.unlink()
        sentinel = root / "sentinel"
        sentinel.write_text("untouched")
        target.symlink_to(sentinel)
    elif mutation == "permissions":
        target.chmod(0o666)
    else:
        target.parent.chmod(0o777)
    before = target.read_bytes()
    calls = []
    with pytest.raises(OSError):
        apply(root, control, "0", calls)
    assert calls == [] and target.read_bytes() == before
    assert not list(target.parent.glob(".hardenops-*"))


def test_runtime_strengthening_after_plan_refuses_without_persistence_change(root):
    target = owned(root, "kernel.kptr_restrict=0\n")
    control = decision(root, "0")
    calls = []
    with pytest.raises(guard.UnsafePath, match="Runtime changed"):
        apply(root, control, "2", calls)
    assert target.read_text() == "kernel.kptr_restrict=0\n" and not calls


def test_replacement_during_descriptor_read_is_detected(root, monkeypatch):
    target = owned(root)
    original = guard.os.fstat
    replaced = False

    def raced_fstat(descriptor):
        nonlocal replaced
        metadata = original(descriptor)
        if stat.S_ISREG(metadata.st_mode) and not replaced:
            replaced = True
            replacement = target.with_suffix(".replacement")
            replacement.write_text("kernel.kptr_restrict=0\n")
            replacement.replace(target)
        return metadata

    monkeypatch.setattr(guard.os, "fstat", raced_fstat)
    assert decision(root)["result"] == "UNSUPPORTED"


def test_parent_symlink_inserted_before_open_is_refused(root, monkeypatch):
    owned(root)
    original = guard.os.open

    def raced_open(path, flags, *args, **kwargs):
        if path == "sysctl.d":
            parent = root / "etc/sysctl.d"
            destination = parent.with_name("real-sysctl.d")
            parent.rename(destination)
            parent.symlink_to(destination, target_is_directory=True)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(guard.os, "open", raced_open)
    assert decision(root)["result"] == "UNSUPPORTED"


@pytest.mark.parametrize("content", ["kernel.kptr_restrict=0\nother.key=1\n",
                                    "kernel.kptr_restrict=0\nkernel.kptr_restrict=2\n"])
def test_unapproved_content_never_activated(root, content):
    target = owned(root, content)
    assert decision(root, "0")["result"] == "UNSUPPORTED"
    assert target.read_text() == content


@pytest.mark.parametrize("mode", [0o400, 0o600, 0o640])
def test_canonical_content_protected_before_single_key_activation_and_idempotent(root, mode):
    target = owned(root, "# trusted comment\nkernel.kptr_restrict=0\n", mode)
    control = decision(root, "0")
    calls = []

    def activate(key, value):
        assert target.read_text() == "kernel.kptr_restrict = 2\n"
        assert stat.S_IMODE(target.stat().st_mode) == mode
        assert target.stat().st_uid == 0
        calls.append((key, value))

    got = guard.apply_control(control, root=root, read_runtime=lambda key: "0", set_runtime=activate)
    assert got["changed"] and calls == [("kernel.kptr_restrict", "2")]
    assert not apply(root, decision(root), "2", [], check=False)["changed"]


def test_safe_missing_current_and_strict_legacy_migration(root):
    legacy = owned(root, "kernel.kptr_restrict=2\n", 0o400, legacy=True)
    calls = []
    result = apply(root, decision(root, "0"), "0", calls)
    target = root / "etc/sysctl.d/99-z-hardenops-bp028_r9_kptr_restrict.conf"
    assert result["changed"] and not legacy.exists()
    assert target.read_text() == "kernel.kptr_restrict = 2\n"
    assert stat.S_IMODE(target.stat().st_mode) == 0o400
    assert calls == [("kernel.kptr_restrict", "2")]


def test_missing_current_in_safe_directory_created_with_final_mode(root):
    assert apply(root, decision(root, "0"), "0", [])["changed"]
    target = root / "etc/sysctl.d/99-z-hardenops-bp028_r9_kptr_restrict.conf"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_optional_accepted_values_keeps_inspector_expected_default(root):
    control = policy()
    control["verification"].pop("accepted_values")
    calls = []
    assert apply(root, decision(root, "0", control), "0", calls)["changed"]
    assert calls == [("kernel.kptr_restrict", "2")]


def test_changed_legacy_is_not_deleted(root):
    legacy = owned(root, "kernel.kptr_restrict=2\n", legacy=True)
    control = decision(root, "0")

    def activate(key, value):
        legacy.write_text("kernel.kptr_restrict=2\nother.key=1\n")

    with pytest.raises(guard.UnsafePath):
        guard.apply_control(control, root=root, read_runtime=lambda key: "0", set_runtime=activate)
    assert legacy.exists() and "other.key" in legacy.read_text()


def test_check_mode_no_writes_or_activation(root):
    control = decision(root, "0")
    calls = []
    assert apply(root, control, "0", calls, check=True)["changed"]
    assert calls == [] and list((root / "etc/sysctl.d").iterdir()) == []


@pytest.mark.parametrize("runtime,current,legacy", [("4", "2", None), ("2", "4", None), ("2", "2", "4")])
def test_strongest_accepted_state_preserved_in_guard(root, runtime, current, legacy):
    control = policy("kernel.perf_event_paranoid", ["2", "3", "4"])
    target = owned(root, f"kernel.perf_event_paranoid={current!s}\n")
    if legacy:
        owned(root, f"kernel.perf_event_paranoid={legacy!s}\n", legacy=True)
    calls = []
    assert apply(root, decision(root, runtime, control), runtime, calls)["changed"]
    assert target.read_text() == "kernel.perf_event_paranoid = 4\n"
    assert calls == ([] if runtime == "4" else [("kernel.perf_event_paranoid", "4")])


def test_new_yama_three_refused_by_guard_even_with_forged_decision(root):
    control = policy("kernel.yama.ptrace_scope", ["1", "2", "3"])
    control["verification"]["remediable_values"] = ["0"]
    owned(root, "kernel.yama.ptrace_scope=3\n")
    control = decision(root, "1", control)
    assert control["result"] == "UNSUPPORTED"
    with pytest.raises(guard.UnsafePath, match="irreversible"):
        apply(root, control, "1", [])


def test_sysrq_remediable_mask_still_supported(root):
    control = policy("kernel.sysrq", ["0"])
    control["verification"].pop("remediable_values")
    control["verification"]["remediable_range"] = [1, 511]
    calls = []
    assert apply(root, decision(root, "176", control), "176", calls)["changed"]
    assert calls == [("kernel.sysrq", "0")]


def test_change_while_atomic_file_is_prepared_is_refused(root, monkeypatch):
    target = owned(root, "kernel.kptr_restrict=0\n")
    control = decision(root, "0")
    original = guard.os.fsync

    def raced_fsync(descriptor):
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            target.write_text("kernel.kptr_restrict=0\nother.key=1\n")
        return original(descriptor)

    monkeypatch.setattr(guard.os, "fsync", raced_fsync)
    calls = []
    with pytest.raises(guard.UnsafePath, match="changed during replacement"):
        apply(root, control, "0", calls)
    assert not calls and "other.key" in target.read_text()
    assert not list(target.parent.glob(".hardenops-*"))


def apport_decision(root):
    control = policy("fs.suid_dumpable", ["0"])
    control["verification"].update(expected="0", remediable_values=["1", "2"])
    (root / "usr/lib/systemd/system/apport.service").write_text("[Service]\n")
    return decision(root, "2", control)


def test_apport_exact_dropin_and_stricter_mode_preserved(root):
    control = apport_decision(root)
    calls = []
    assert apply(root, control, "2", calls)["apport_changed"]
    hook = root / guard.APPORT.lstrip("/")
    expected = guard.apport_content(control["observed"]["persistence"]["path"])
    assert hook.read_text() == expected
    hook.chmod(0o400)
    control = decision(root, "0", policy("fs.suid_dumpable", ["0"]))
    control["verification"].update(expected="0", remediable_values=["1", "2"])
    assert not apply(root, control, "0", [])["changed"]
    assert hook.stat().st_mode & 0o777 == 0o400


@pytest.mark.parametrize("parent", ["etc/systemd", "etc/systemd/system", "etc/systemd/system/apport.service.d"])
def test_apport_unsafe_ancestors_refused(root, parent):
    control = apport_decision(root)
    path = root / parent
    path.mkdir(exist_ok=True)
    path.chmod(0o777)
    fresh = decision(root, "2", policy("fs.suid_dumpable", ["0"]))
    assert fresh["result"] == "UNSUPPORTED"
    with pytest.raises(OSError):
        apply(root, control, "2", [])
    assert list((root / "etc/sysctl.d").iterdir()) == []


def test_apport_changed_content_after_plan_refused(root):
    control = apport_decision(root)
    hook = root / guard.APPORT.lstrip("/")
    hook.parent.mkdir()
    hook.write_text("[Service]\nExecStartPost=/bin/true\n")
    with pytest.raises(guard.UnsafePath):
        apply(root, control, "2", [])
    assert list((root / "etc/sysctl.d").iterdir()) == []


def test_missing_apport_system_parent_is_not_silently_created(root):
    control = apport_decision(root)
    (root / "etc/systemd/system").rmdir()
    fresh = decision(root, "2", policy("fs.suid_dumpable", ["0"]))
    assert fresh["result"] == "UNSUPPORTED" and not fresh["needs_change"]
    with pytest.raises(OSError):
        apply(root, control, "2", [])
    assert not (root / "etc/systemd/system").exists()
    assert list((root / "etc/sysctl.d").iterdir()) == []


def test_ubuntu_merged_usr_vendor_discovery_kept(root):
    (root / "lib").symlink_to("usr/lib", target_is_directory=True)
    control = apport_decision(root)
    assert apply(root, control, "2", [])["apport_changed"]


def test_activation_argv_has_no_reload_or_file(monkeypatch):
    calls = []
    monkeypatch.setattr(guard.subprocess, "run", lambda argv, **kw: (
        calls.append((argv, kw)) or SimpleNamespace(stderr="")))
    guard.activate("kernel.kptr_restrict", "2")
    assert calls[0][0] == ["/usr/sbin/sysctl", "-w", "kernel.kptr_restrict=2"]
    assert calls[0][1]["check"] and calls[0][1]["timeout"] == 15
