"""Apport recovery fixtures: no real sysctl or systemd process is invoked."""

import copy
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import apport_reload as reload
from tools import inspect_host as inspector
from tools import sysctl_guard as guard


@pytest.fixture
def root(tmp_path):
    if os.name != "posix" or os.geteuid() != 0:
        pytest.skip("Root-owned Linux fixture required")
    tmp_path.chmod(0o755)
    for directory in ("etc/sysctl.d", "etc/systemd/system", "usr/lib/systemd/system"):
        (tmp_path / directory).mkdir(parents=True, mode=0o755)
    return tmp_path


@pytest.fixture
def crash_root(root):
    if not Path("/.dockerenv").exists():
        pytest.skip("Crash fixtures require a disposable Docker container")
    if (not root.is_relative_to(Path("/tmp"))
            or not root.resolve().is_relative_to(Path("/tmp").resolve())):
        pytest.skip("Crash fixtures require a temporary directory under /tmp")
    return root


def policy():
    return {"id": "bp028_r14_suid_dumpable", "enforcement": "AUTOMATED",
            "verification": {"key": "fs.suid_dumpable", "expected": "0",
                             "accepted_values": ["0"], "remediable_values": ["1", "2"]}}


class Reader(inspector.HostReader):
    def __init__(self, root, runtime):
        super().__init__(root)
        self.runtime = runtime

    def text(self, absolute, limit=256_000):
        if absolute == "/proc/sys/fs/suid_dumpable":
            return self.runtime
        return super().text(absolute, limit)


def decision(root, runtime="2"):
    control = policy()
    control.update(inspector.inspect_sysctl(control, Reader(root, runtime)))
    return control


def vendor(root):
    (root / "usr/lib/systemd/system/apport.service").write_text("[Service]\n")


def installed(root):
    vendor(root)
    control = decision(root)
    guard.apply_control(control, root=root, read_runtime=lambda key: "2",
                        set_runtime=lambda key, value: None)
    return decision(root, "0")


class Manager:
    def __init__(self, control, loaded=False, hint="no"):
        self.path = f"/etc/sysctl.d/99-z-hardenops-{control['id']}.conf"
        self.loaded = loaded
        self.hint = hint
        self.calls = []
        self.fail_reload = False
        self.stay_stale = False

    def run(self, argv, **kwargs):
        self.calls.append(argv)
        assert kwargs["check"] and kwargs["timeout"] in {15, 30}
        if argv == ["/usr/bin/systemctl", "daemon-reload"]:
            if self.fail_reload:
                raise subprocess.CalledProcessError(1, argv)
            self.loaded = not self.stay_stale
            return SimpleNamespace(stdout="", stderr="")
        assert argv[:4] == ["/usr/bin/systemctl", "show", "apport.service", "--all"]
        command = ("{ path=/usr/sbin/sysctl ; argv[]=/usr/sbin/sysctl -p " + self.path
                   + " ; ignore_errors=no ; start_time=[n/a] ; status=0/0 }") if self.loaded else ""
        return SimpleNamespace(stdout=("LoadState=loaded\nDropInPaths=" + (guard.APPORT if self.loaded else "")
                                      + "\nExecStartPost=" + command + "\nNeedDaemonReload=" + self.hint + "\n"),
                               stderr="")

    def reloads(self):
        return self.calls.count(["/usr/bin/systemctl", "daemon-reload"])


def test_failure_after_publication_then_retry_retains_reload(root):
    vendor(root)
    control = decision(root)
    with pytest.raises(subprocess.CalledProcessError):
        guard.apply_control(control, root=root, read_runtime=lambda key: "2",
                            set_runtime=lambda key, value: (_ for _ in ()).throw(
                                subprocess.CalledProcessError(1, ["fake-sysctl"])))
    assert (root / guard.APPORT.lstrip("/")).is_file()
    retry = guard.apply_control(decision(root), root=root, read_runtime=lambda key: "2",
                                set_runtime=lambda key, value: None)
    assert retry == {"changed": True, "apport_changed": False}
    manager = Manager(control)
    assert reload.reconcile(decision(root, "0"), root=root, run=manager.run)["reloaded"]
    assert manager.reloads() == 1
    assert not reload.reconcile(decision(root, "0"), root=root, run=manager.run)["changed"]
    assert manager.reloads() == 1


def test_pass_observation_does_not_mean_manager_synchronized(root):
    control = installed(root)
    assert control["result"] == "PASS" and not control["needs_change"]
    manager = Manager(control, hint="no")
    assert reload.reconcile(control, root=root, run=manager.run)["reloaded"]


def test_synced_hook_ignores_unrelated_dirty_hint_without_reload(root):
    control = installed(root)
    manager = Manager(control, loaded=True, hint="yes")
    assert not reload.reconcile(control, root=root, run=manager.run)["changed"]
    assert manager.reloads() == 0


@pytest.mark.parametrize("content", ["fs.suid_dumpable = 2\n", "# safe existing file\nfs.suid_dumpable=0\n", None])
def test_existing_hook_does_not_block_legitimate_guard_remediation(root, content):
    installed(root)
    path = root / "etc/sysctl.d/99-z-hardenops-bp028_r14_suid_dumpable.conf"
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    control = decision(root)
    assert control["needs_change"] and control["result"] == "FAIL"
    manager = Manager(control, loaded=True)
    assert not reload.reconcile(control, root=root, run=manager.run)["changed"]
    result = guard.apply_control(control, root=root, read_runtime=lambda key: "2",
                                 set_runtime=lambda key, value: None)
    assert result["changed"] and path.read_text() == "fs.suid_dumpable = 0\n"


def test_no_apport_never_runs_systemctl(root):
    control = decision(root)
    manager = Manager(control)
    assert not reload.reconcile(control, root=root, run=manager.run)["applicable"]
    assert not manager.calls


def test_failure_before_publication_never_reloads(root):
    vendor(root)
    control = decision(root)
    control["observed"]["runtime"] = "1"
    with pytest.raises(guard.UnsafePath, match="Runtime changed"):
        guard.apply_control(control, root=root, read_runtime=lambda key: "2",
                            set_runtime=lambda key, value: pytest.fail("No activation expected"))
    assert not (root / guard.APPORT.lstrip("/")).exists()
    assert list((root / "etc/sysctl.d").iterdir()) == []
    manager = Manager(control)
    assert not reload.reconcile(control, root=root, run=manager.run)["changed"]
    assert not manager.calls


def test_reload_failure_is_not_success_and_retry_recovers(root):
    control = installed(root)
    manager = Manager(control)
    manager.fail_reload = True
    with pytest.raises(subprocess.CalledProcessError):
        reload.reconcile(control, root=root, run=manager.run)
    assert not manager.loaded
    manager.fail_reload = False
    assert reload.reconcile(control, root=root, run=manager.run)["reloaded"]
    assert manager.reloads() == 2
    assert not reload.reconcile(control, root=root, run=manager.run)["changed"]


def test_reload_success_without_loaded_hook_is_refused(root):
    control = installed(root)
    manager = Manager(control)
    manager.stay_stale = True
    with pytest.raises(guard.UnsafePath, match="not loaded"):
        reload.reconcile(control, root=root, run=manager.run)


def test_check_mode_has_no_mutation_or_reload(root):
    control = installed(root)
    before = {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    manager = Manager(control)
    result = reload.reconcile(control, root=root, check=True, run=manager.run)
    assert result["changed"] and not result["reloaded"] and manager.reloads() == 0
    assert before == {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("unsafe", ["content", "symlink", "writable", "current"])
def test_reconciliation_preserves_descriptor_refusals(root, unsafe):
    control = installed(root)
    hook = root / guard.APPORT.lstrip("/")
    if unsafe == "content":
        hook.write_text("[Service]\nExecStartPost=/bin/true\n")
    elif unsafe == "symlink":
        target = hook.with_name("saved")
        hook.rename(target)
        hook.symlink_to(target)
    elif unsafe == "writable":
        hook.chmod(0o666)
    else:
        (root / ("etc/sysctl.d/99-z-hardenops-" + control["id"] + ".conf")).write_text("other.key=0\n")
    manager = Manager(control)
    with pytest.raises(OSError):
        reload.reconcile(control, root=root, run=manager.run)
    assert not manager.calls


@pytest.mark.parametrize("response", ["", "LoadState=loaded\n", "LoadState=loaded\nLoadState=loaded\n",
                                      "LoadState=loaded\nDropInPaths=\nNeedDaemonReload=unknown\n"])
def test_unknown_manager_replies_fail_closed(response):
    with pytest.raises(guard.UnsafePath):
        reload.manager_state(lambda *args, **kwargs: SimpleNamespace(stdout=response))


def test_missing_empty_command_array_is_not_synchronization():
    result = reload.manager_state(lambda *args, **kwargs: SimpleNamespace(
        stdout="LoadState=loaded\nDropInPaths=\nNeedDaemonReload=no\n"))
    assert not reload.loaded_hook(result, "/etc/sysctl.d/owned.conf")


def test_real_systemctl_repeated_command_properties_preserve_order():
    path = "/etc/sysctl.d/owned.conf"
    response = ("ExecStartPost={ path=/bin/true ; argv[]=/bin/true ; ignore_errors=no ; status=0/0 }\n"
                + "ExecStartPost={ path=/usr/sbin/sysctl ; argv[]=/usr/sbin/sysctl -p " + path
                + " ; ignore_errors=no ; status=0/0 }\nLoadState=loaded\nDropInPaths=" + guard.APPORT
                + "\nNeedDaemonReload=no\n")
    result = reload.manager_state(lambda *args, **kwargs: SimpleNamespace(stdout=response))
    assert len(result["commands"]) == 2 and reload.loaded_hook(result, path)


def test_rejects_wrong_or_nonfinal_loaded_command():
    path = "/etc/sysctl.d/owned.conf"
    good = f"path=/usr/sbin/sysctl ; argv[]=/usr/sbin/sysctl -p {path} ; ignore_errors=no ; status=0/0"
    values = {"DropInPaths": guard.APPORT, "commands": [good, "path=/bin/true ;"]}
    assert not reload.loaded_hook(values, path)
    values["commands"] = [good.replace("ignore_errors=no", "ignore_errors=yes")]
    assert not reload.loaded_hook(values, path)


@pytest.mark.parametrize("edit", ["id", "key", "enforcement", "desired"])
def test_invalid_decisions_refused_before_manager_access(root, edit):
    control = installed(root)
    bad = copy.deepcopy(control)
    if edit == "key":
        bad["verification"]["key"] = "kernel.sysrq"
    else:
        bad[edit] = {"id": "../escape", "enforcement": "MANUAL", "desired": "99"}[edit]
    manager = Manager(control)
    with pytest.raises(guard.UnsafePath):
        reload.reconcile(bad, root=root, run=manager.run)
    assert not manager.calls


def test_cli_keeps_reload_error_failed_and_without_json(monkeypatch, capsys):
    monkeypatch.setattr(reload.os, "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"control": policy(), "check": False})))
    monkeypatch.setattr(reload, "reconcile", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("fixture reload failed")))
    assert reload.main() == 2
    output = capsys.readouterr()
    assert output.out == "" and "fixture reload failed" in output.err


@pytest.mark.parametrize("check", [False, True])
def test_cli_refuses_non_root_before_reconcile(monkeypatch, capsys, check):
    monkeypatch.setattr(reload.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"control": policy(), "check": check})))
    monkeypatch.setattr(reload, "reconcile", lambda *args, **kwargs: pytest.fail("No reconciliation expected"))
    assert reload.main() == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Apport metadata refused: Root and an explicit check-mode Boolean are required\n"


WORKER = r'''
import json,os,subprocess,sys
from pathlib import Path
assert Path("/.dockerenv").exists()
root=Path(sys.argv[2]);assert root.is_relative_to(Path("/tmp"))
sys.path.insert(0,sys.argv[3])
from tools import apport_reload as reload,inspect_host as inspector,sysctl_guard as guard
control={"id":"bp028_r14_suid_dumpable","enforcement":"AUTOMATED",
 "verification":{"key":"fs.suid_dumpable","expected":"0","accepted_values":["0"],"remediable_values":["1","2"]}}
class Reader(inspector.HostReader):
 def text(self,path,limit=256000):
  return "2" if path=="/proc/sys/fs/suid_dumpable" else super().text(path,limit)
if sys.argv[1]=="publication-crash":
 control.update(inspector.inspect_sysctl(control,Reader(root)))
 guard.apply_control(control,root=root,read_runtime=lambda key:"2",set_runtime=lambda key,value:os._exit(17))
state_file=root/"manager.json"
state=json.loads(state_file.read_text())
def run(argv,**kwargs):
 if argv==["/usr/bin/systemctl","daemon-reload"]:
  state.update(loaded=True,reloads=state["reloads"]+1);state_file.write_text(json.dumps(state))
  if sys.argv[1]=="reload-crash":os._exit(18)
  return type("Result",(),{"stdout":"","stderr":""})()
 assert argv[:3]==["/usr/bin/systemctl","show","apport.service"]
 path="/etc/sysctl.d/99-z-hardenops-bp028_r14_suid_dumpable.conf"
 command="{ path=/usr/sbin/sysctl ; argv[]=/usr/sbin/sysctl -p "+path+" ; ignore_errors=no ; status=0/0 }" if state["loaded"] else ""
 content="LoadState=loaded\nDropInPaths="+(guard.APPORT if state["loaded"] else "")+"\nExecStartPost="+command+"\nNeedDaemonReload=no\n"
 return type("Result",(),{"stdout":content,"stderr":""})()
print(json.dumps(reload.reconcile(control,root=root,run=run)))
'''


def worker(root, mode):
    return subprocess.run([sys.executable, "-B", "-c", WORKER, mode, str(root),
                           str(Path(reload.__file__).resolve().parents[1])],
                          capture_output=True, text=True, check=False, timeout=15)


def test_abrupt_publication_crash_recovers_in_a_new_process(crash_root):
    root = crash_root
    vendor(root)
    (root / "manager.json").write_text('{"loaded":false,"reloads":0}')
    crashed = worker(root, "publication-crash")
    assert crashed.returncode == 17 and crashed.stdout == ""
    assert (root / guard.APPORT.lstrip("/")).exists()
    recovered = worker(root, "recover")
    assert recovered.returncode == 0, recovered.stderr
    assert json.loads(recovered.stdout)["reloaded"]
    repeated = worker(root, "recover")
    assert repeated.returncode == 0 and not json.loads(repeated.stdout)["changed"]
    assert json.loads((root / "manager.json").read_text())["reloads"] == 1


def test_abrupt_exit_after_reload_does_not_require_an_ack_file(crash_root):
    root = crash_root
    installed(root)
    (root / "manager.json").write_text('{"loaded":false,"reloads":0}')
    crashed = worker(root, "reload-crash")
    assert crashed.returncode == 18 and crashed.stdout == ""
    recovered = worker(root, "recover")
    assert recovered.returncode == 0, recovered.stderr
    assert not json.loads(recovered.stdout)["changed"]
    assert json.loads((root / "manager.json").read_text())["reloads"] == 1
