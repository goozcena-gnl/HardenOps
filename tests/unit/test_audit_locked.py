"""Exercise both pinned pip-audit callers without replacing their resolver."""
import importlib
import importlib.metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

audit_locked = importlib.import_module("tools.audit_locked")
bootstrap = importlib.import_module("tools.bootstrap_python")


def test_unreviewed_auditor_refused(monkeypatch):
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "2.10.2")
    with pytest.raises(bootstrap.BootstrapError, match="2.10.1"):
        audit_locked.adapt_virtual_env(Path("unused.whl"))


def test_both_source_aliases_are_adapted(monkeypatch):
    import pip_audit._dependency_source.pyproject as project
    import pip_audit._dependency_source.requirement as requirements

    monkeypatch.setattr(requirements, "VirtualEnv", requirements.VirtualEnv)
    monkeypatch.setattr(project, "VirtualEnv", project.VirtualEnv)
    adapted = audit_locked.adapt_virtual_env(Path("approved.whl"))
    assert requirements.VirtualEnv is adapted
    assert project.VirtualEnv is adapted
    instance = adapted(["--require-hashes", "-r", "lock.txt"],
                       "https://pypi.org/simple", [])
    assert instance.with_pip is False
    assert instance._install_args == ["--require-hashes", "-r", "lock.txt"]


def test_offline_bootstrap_precedes_original_post_setup(monkeypatch):
    import pip_audit._dependency_source.pyproject as project
    import pip_audit._dependency_source.requirement as requirements
    import pip_audit._virtual_env as virtual_env

    monkeypatch.setattr(requirements, "VirtualEnv", requirements.VirtualEnv)
    monkeypatch.setattr(project, "VirtualEnv", project.VirtualEnv)
    order = []
    monkeypatch.setattr(bootstrap, "install_pip",
                        lambda python, wheel: order.append(("bootstrap", python, wheel)))
    monkeypatch.setattr(virtual_env.VirtualEnv, "post_setup",
                        lambda self, context: order.append(("original", context)))
    adapted = audit_locked.adapt_virtual_env(Path("approved.whl"))
    instance = adapted(["-r", "lock.txt"])
    context = SimpleNamespace(env_exe="/owned/venv/bin/python")
    instance.post_setup(context)
    assert order == [("bootstrap", Path(context.env_exe), Path("approved.whl")),
                     ("original", context)]


def test_bootstrap_failure_never_calls_resolver(monkeypatch):
    import pip_audit._dependency_source.pyproject as project
    import pip_audit._dependency_source.requirement as requirements
    import pip_audit._virtual_env as virtual_env

    monkeypatch.setattr(requirements, "VirtualEnv", requirements.VirtualEnv)
    monkeypatch.setattr(project, "VirtualEnv", project.VirtualEnv)

    def failed_bootstrap(*args):
        raise bootstrap.BootstrapError("bad wheel")

    monkeypatch.setattr(bootstrap, "install_pip", failed_bootstrap)
    monkeypatch.setattr(virtual_env.VirtualEnv, "post_setup",
                        lambda *args: pytest.fail("resolver must not run"))
    instance = audit_locked.adapt_virtual_env(Path("bad.whl"))([])
    with pytest.raises(virtual_env.VirtualEnvError, match="bad wheel"):
        instance.post_setup(SimpleNamespace(env_exe="/owned/venv/bin/python"))
