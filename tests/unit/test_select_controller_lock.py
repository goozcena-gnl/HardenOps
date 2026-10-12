"""Offline platform and interpreter guard tests for controller lock selection."""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "tools" / "select_controller_lock.py"
spec = importlib.util.spec_from_file_location("select_controller_lock", SCRIPT)
selector = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = selector
spec.loader.exec_module(selector)


@pytest.fixture
def root(tmp_path):
    (tmp_path / "locks").mkdir()
    (tmp_path / "locks" / "py312.txt").write_text("# 3.12\n")
    (tmp_path / "locks" / "py313.txt").write_text("# 3.13\n")
    return tmp_path


@pytest.mark.parametrize(
    ("version", "filename"),
    [((3, 12), "py312.txt"), ((3, 13), "py313.txt")],
)
def test_selects_matching_lock(root, version, filename):
    assert selector.select_lock("cpython", version, "Linux", "x86_64", root) == (
        root / "locks" / filename
    ).resolve()


@pytest.mark.parametrize(
    ("implementation", "version", "system", "machine"),
    [
        ("pypy", (3, 12), "Linux", "x86_64"),
        ("cpython", (3, 11), "Linux", "x86_64"),
        ("cpython", (3, 14), "Linux", "x86_64"),
        ("cpython", (3, 13), "Windows", "AMD64"),
        ("cpython", (3, 13), "Darwin", "arm64"),
        ("cpython", (3, 13), "Linux", "aarch64"),
    ],
)
def test_unsupported_controller_rejected(root, implementation, version, system, machine):
    with pytest.raises(selector.UnsupportedController):
        selector.select_lock(implementation, version, system, machine, root)


def test_missing_matching_lock_rejected(root):
    (root / "locks" / "py313.txt").unlink()
    with pytest.raises(selector.UnsupportedController, match="missing"):
        selector.select_lock("cpython", (3, 13), "Linux", "x86_64", root)


def test_does_not_select_other_python_lock(root):
    (root / "locks" / "py312.txt").unlink()
    with pytest.raises(selector.UnsupportedController, match="py312.txt"):
        selector.select_lock("cpython", (3, 12), "Linux", "x86_64", root)
