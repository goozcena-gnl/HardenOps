#!/usr/bin/env python3
"""Run pinned pip-audit with seed-free, authenticated temporary environments."""
from __future__ import annotations

import importlib.metadata
import os
import sys
import tempfile
from pathlib import Path

if __package__:
    from . import bootstrap_python as bootstrap
else:
    import bootstrap_python as bootstrap


def adapt_virtual_env(wheel: Path):
    if importlib.metadata.version("pip-audit") != "2.10.1":
        raise bootstrap.BootstrapError("Audit adapter requires reviewed pip-audit 2.10.1")
    import pip_audit._dependency_source.pyproject as project_source
    import pip_audit._dependency_source.requirement as requirement_source
    import pip_audit._virtual_env as virtual_env

    original = virtual_env.VirtualEnv

    class ApprovedVirtualEnv(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.with_pip = False

        def post_setup(self, context):
            try:
                bootstrap.install_pip(Path(context.env_exe), wheel)
            except bootstrap.BootstrapError as error:
                raise virtual_env.VirtualEnvError(f"Approved audit bootstrap failed: {error}") from error
            return super().post_setup(context)

    requirement_source.VirtualEnv = ApprovedVirtualEnv
    project_source.VirtualEnv = ApprovedVirtualEnv
    return ApprovedVirtualEnv


def main(arguments: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    try:
        with bootstrap.staged_wheel(bootstrap.default_wheel()) as wheel, \
                bootstrap.trusted_environment(), \
                tempfile.TemporaryDirectory(prefix="hardenops-audit-constraint-") as directory:
            constraint = Path(directory) / "pip.txt"
            constraint.write_text(f"pip=={bootstrap.PIP_VERSION}\n")
            os.environ["PIP_CONSTRAINT"] = str(constraint)
            adapt_virtual_env(wheel)
            from pip_audit._cli import audit

            sys.argv = ["pip-audit", *arguments]
            audit()
    except (bootstrap.BootstrapError, importlib.metadata.PackageNotFoundError) as error:
        print(f"Audit bootstrap refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
