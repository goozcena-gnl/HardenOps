"""Fail-closed test cases for Dependabot lock preparation. No network required."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools/prepare_dependabot_locks.py"
spec = importlib.util.spec_from_file_location("prepare_dependabot_locks", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

BASE = ("# Linux controller\n" + "\n".join(f"package-{i}==1.0" for i in range(11)) + "\n").encode()
UPDATED = BASE.replace(b"package-0==1.0", b"package-0==1.1")
FILES = [{"filename": "requirements-dev.in", "status": "modified"},
         {"filename": "locks/py312.txt", "status": "modified"},
         {"filename": "locks/py313.txt", "status": "modified"}]
SHA1, SHA2 = "a" * 40, "b" * 40
REPO = "goozcena-gnl/HardenOps"


def metadata():
    return {"state": "open", "merged_at": None, "changed_files": 3,
            "user": {"login": "dependabot[bot]"},
            "head": {"sha": SHA1, "ref": "dependabot/pip/example", "repo": {"full_name": REPO}},
            "base": {"sha": SHA2, "ref": "main", "repo": {"full_name": REPO}}}


def test_happy_path():
    assert mod.validate_change(BASE, UPDATED, FILES) == ("package-0", "1.1")
    mod.validate_metadata(metadata(), REPO, SHA1, SHA2)


@pytest.mark.parametrize("bad", [
    BASE,
    UPDATED.replace(b"package-1==1.0", b"package-1==1.1"),
    UPDATED + b"requests==1.0\n",
    UPDATED.replace(b"package-0==1.1", b"other-pkg==1.1"),
    UPDATED.replace(b"# Linux controller", b"# changed comment"),
    UPDATED + b"--extra-index-url https://evil.example\n",
    UPDATED.replace(b"package-2==1.0", b"package-2 @ https://evil.example/evil.whl"),
    UPDATED.replace(b"package-2==1.0", b"package-2==1.0; python_version<'3.13'"),
])
def test_bad_direct_inputs_rejected(bad):
    with pytest.raises(mod.GuardError):
        mod.validate_change(BASE, bad, FILES)


@pytest.mark.parametrize("files", [
    FILES + [{"filename": ".github/workflows/lint.yml", "status": "modified"}],
    FILES[:2] + [{"filename": "Makefile", "status": "modified"}],
    FILES[1:],
    FILES[:1] + [{"filename": "locks/py312.txt", "status": "added"}],
    FILES + [FILES[0]],
])
def test_untrusted_pr_scope_rejected(files):
    with pytest.raises(mod.GuardError):
        mod.validate_change(BASE, UPDATED, files)


@pytest.mark.parametrize("key,value", [
    ("state", "closed"), ("merged_at", "2026-10-12T13:00:00Z"),
    ("user.login", "someone"), ("head.sha", "0" * 40),
    ("head.ref", "feature/unsafe"), ("head.repo.full_name", "other/repo"),
    ("base.sha", "0" * 40), ("base.ref", "testing"),
    ("base.repo.full_name", "other/repo"), ("changed_files", 5),
])
def test_untrusted_pr_metadata_rejected(key, value):
    obj = metadata()
    names = key.split(".")
    target = obj
    for name in names[:-1]:
        target = target[name]
    target[names[-1]] = value
    with pytest.raises(mod.GuardError):
        mod.validate_metadata(obj, REPO, SHA1, SHA2)


def test_mutates_only_mirrored_direct_inputs(tmp_path, monkeypatch):
    (tmp_path / "requirements-dev.txt").write_bytes(BASE)
    (tmp_path / "requirements-dev.in").write_bytes(BASE)
    (tmp_path / "locks").mkdir()
    (tmp_path / "locks/py312.txt").write_bytes(b"historical py312")
    (tmp_path / "locks/py313.txt").write_bytes(b"historical py313")
    import base64
    metadata_data = metadata()
    candidate = {"encoding": "base64", "type": "file",
                 "content": base64.b64encode(UPDATED).decode()}
    answers = [metadata_data, FILES, candidate]
    monkeypatch.setattr(mod, "get_json", lambda url, token: answers.pop(0))
    got = mod.prepare(repo=REPO, number=13, head_sha=SHA1, base_sha=SHA2,
                      token="not-real", root=tmp_path)
    assert got["direct_package"] == "package-0"
    assert (tmp_path / "requirements-dev.txt").read_bytes() == UPDATED
    assert (tmp_path / "requirements-dev.in").read_bytes() == UPDATED
    assert (tmp_path / "locks/py312.txt").read_bytes() == b"historical py312"
    assert (tmp_path / "locks/py313.txt").read_bytes() == b"historical py313"
