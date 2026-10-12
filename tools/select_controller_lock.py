#!/usr/bin/env python3
"""Select the reviewed CPython/Linux controller lock; fail closed elsewhere."""
from __future__ import annotations

import platform
import sys
from pathlib import Path


class UnsupportedController(ValueError):
    """The controller is outside the validated lock scope."""


def select_lock(
    implementation: str,
    version: tuple[int, int],
    system: str,
    machine: str,
    repository: Path,
) -> Path:
    if implementation != "cpython" or system != "Linux" or machine != "x86_64":
        raise UnsupportedController(
            f"Locks require CPython on Linux x86_64; got "
            f"{implementation}, {system}, {machine}"
        )
    supported = {(3, 12): "py312.txt", (3, 13): "py313.txt"}
    if version not in supported:
        raise UnsupportedController(
            f"Locks support Python 3.12/3.13; got {version[0]}.{version[1]}"
        )
    lock = repository / "locks" / supported[version]
    if not lock.is_file():
        raise UnsupportedController(f"Required controller lock is missing: {lock}")
    return lock.resolve()


def main() -> int:
    repository = Path(__file__).resolve().parent.parent
    try:
        lock = select_lock(
            sys.implementation.name,
            sys.version_info[:2],
            platform.system(),
            platform.machine(),
            repository,
        )
    except UnsupportedController as exc:
        print(f"HARDENOPS LOCK ERROR: {exc}", file=sys.stderr)
        return 2
    print(lock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
