"""Regression tests for the supported isolated fixture entrypoint, separate from Ansible transport."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests/integration/guarded_sysctl_python.py"
pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or not Path("/.dockerenv").is_file(),
    reason="The fixture contract requires an explicitly selected disposable Linux container",
)

PROBE = """import json, subprocess, sys
def main():
    print(json.dumps({"isolated": sys.flags.isolated, "ignore_environment": sys.flags.ignore_environment,
        "safe_path": sys.flags.safe_path, "python": list(sys.version_info[:2]),
        "name": __name__, "file_present": "__file__" in globals(),
        "spec_present": "__spec__" in globals(), "registered": __name__ in sys.modules,
        "mock": subprocess.run.__name__, "json_file": json.__file__}))
    return 0
"""


@pytest.fixture
def launch(tmp_path):
    directory = tmp_path / "fixture"
    directory.mkdir()
    executable = directory / "guard-python"
    shutil.copyfile(SOURCE, executable)
    executable.chmod(0o700)
    binary = tmp_path / "bin"
    binary.mkdir()
    (binary / "python3").symlink_to(sys.executable)
    work = tmp_path / "work"
    work.mkdir()
    environment = dict(os.environ, PATH=str(binary) + os.pathsep + os.defpath,
                       HARDENOPS_GUARD_FIXTURES="1", PYTHONDONTWRITEBYTECODE="1")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)

    def run(source=PROBE, data=None, extra=None, options=("-I", "-c"), raw_python=False):
        values = environment | (extra or {})
        values = {key: value for key, value in values.items() if value is not None}
        argv = ([sys.executable] if raw_python else []) + [str(executable), *options, source]
        return subprocess.run(argv, input=json.dumps(data or {}), text=True, capture_output=True,
                              env=values, cwd=work, check=False, timeout=15)

    return SimpleNamespace(run=run, directory=directory, work=work, root=tmp_path)


def test_fixture_starts_a_real_isolated_interpreter(launch):
    result = launch.run()
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["isolated"] == 1
    assert observed["ignore_environment"] == 1
    assert observed["safe_path"] is True
    assert observed["python"] == list(sys.version_info[:2])


def untrusted_directory(launch, location):
    if location == "fixture":
        return launch.directory, {}
    if location == "cwd":
        return launch.work, {}
    path = launch.root / "pythonpath"
    path.mkdir()
    return path, {"PYTHONPATH": str(path), "PYTHONHOME": str(path)}


@pytest.mark.parametrize("location", ["fixture", "cwd", "pythonpath"])
def test_standard_imports_exclude_untrusted_directories(launch, location):
    directory, environment = untrusted_directory(launch, location)
    (directory / "json.py").write_text('raise RuntimeError("Q03_UNAPPROVED_JSON")\n')
    result = launch.run(extra=environment)
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["isolated"] == 1
    assert str(directory) not in observed["json_file"]
    assert "Q03_UNAPPROVED_JSON" not in result.stderr


@pytest.mark.parametrize("location", ["fixture", "cwd", "pythonpath"])
def test_unapproved_temporary_module_is_not_importable(launch, location):
    directory, environment = untrusted_directory(launch, location)
    (directory / "q03_unapproved.py").write_text('raise RuntimeError("Q03_MODULE_EXECUTED")\n')
    result = launch.run('import q03_unapproved\ndef main(): return 0\n', extra=environment)
    assert result.returncode == 1
    assert "ModuleNotFoundError" in result.stderr
    assert "Q03_MODULE_EXECUTED" not in result.stderr
    assert result.stdout == ""


def test_fixture_retains_stream_namespace_and_mock(launch):
    result = launch.run()
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed["name"] == "streamed_guard_fixture"
    assert observed["file_present"] is False
    assert observed["spec_present"] is False
    assert observed["registered"] is False
    assert observed["mock"] == "fake_sysctl"


def mock_files(launch):
    state = launch.root / "kernel.json"
    state.write_text('{"fs.suid_dumpable": "2"}')
    return {"state": str(state), "calls": str(launch.root / "calls.jsonl")}


MOCK_FILES = """import json, subprocess, sys
from pathlib import Path
settings = json.load(sys.stdin)
subprocess.run.__globals__["STATE"] = Path(settings["state"])
subprocess.run.__globals__["CALLS"] = Path(settings["calls"])
"""


def test_hostreader_only_replaces_proc_reads(launch):
    source = MOCK_FILES + """class HostReader:
    def text(self, absolute, limit=256_000): return "NON_PROC"
def main():
    reader = HostReader()
    print(reader.text("/proc/sys/fs/suid_dumpable"))
    print(reader.text("/etc/example"))
    return 0
"""
    result = launch.run(source, mock_files(launch))
    assert result.returncode == 0, result.stderr
    assert result.stdout == "2\nNON_PROC\n"


def test_fake_sysctl_records_only_explicit_key_activation(launch):
    files = mock_files(launch)
    source = MOCK_FILES + """def main():
    value = subprocess.run(["/usr/sbin/sysctl", "-n", "fs.suid_dumpable"])
    print(value.stdout.strip())
    subprocess.run(["/usr/sbin/sysctl", "-w", "fs.suid_dumpable=0"])
    return 0
"""
    result = launch.run(source, files)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "2\n"
    assert json.loads(Path(files["state"]).read_text()) == {"fs.suid_dumpable": "0"}
    assert Path(files["calls"]).read_text().splitlines() == [
        '["/usr/sbin/sysctl", "-w", "fs.suid_dumpable=0"]'
    ]


def test_fake_sysctl_rejects_other_commands(launch):
    source = 'import subprocess\ndef main():\n    subprocess.run(["/usr/bin/true"])\n    return 0\n'
    result = launch.run(source)
    assert result.returncode == 1
    assert "Fixture refuses every other process execution" in result.stderr


@pytest.mark.parametrize("optin", [None, "0"])
def test_optin_is_required(launch, optin):
    result = launch.run(extra={"HARDENOPS_GUARD_FIXTURES": optin})
    assert result.returncode == 1
    assert "isolated disposable-container fixture opt-in required" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("options", [("-c", "-I"), ("-I", "-m"), ()])
def test_request_argv_contract_is_required(launch, options):
    result = launch.run(options=options)
    assert result.returncode == 1
    assert "isolated disposable-container fixture opt-in required" in result.stderr
    assert result.stdout == ""


def test_explicit_nonisolated_interpreter_is_refused(launch):
    result = launch.run(raw_python=True)
    assert result.returncode == 1
    assert "isolated disposable-container fixture opt-in required" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("source,code,message", [
    ("def main(:\n    pass\n", 1, "SyntaxError"),
    ('def main():\n    raise ValueError("Q03_EXCEPTION")\n', 1, "Q03_EXCEPTION"),
    ("def main():\n    return 7\n", 7, ""),
])
def test_source_errors_and_return_codes_are_preserved(launch, source, code, message):
    result = launch.run(source)
    assert result.returncode == code
    assert message in result.stderr
    assert result.stdout == ""


def test_streamed_inspector_rejects_untrusted_version_as_data(launch):
    guard = (ROOT / "tools/sysctl_guard.py").read_text(encoding="utf-8")
    inspector = (ROOT / "tools/inspect_host.py").read_text(encoding="utf-8")
    source = ("import sys, types; guard = types.ModuleType('sysctl_guard'); "
              f"exec({guard!r}, guard.__dict__); sys.modules['sysctl_guard'] = guard; "
              f"exec({inspector!r})")
    marker = launch.root / "must-not-exist"
    payload = {"hardenops_version": f"__import__('pathlib').Path({str(marker)!r}).touch()"}
    result = launch.run(source, payload)
    assert result.returncode == 2
    assert "hardenops_version" in result.stderr
    assert result.stdout == ""
    assert not marker.exists()
