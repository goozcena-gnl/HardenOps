#!/usr/bin/env -S python3 -I
"""Interpreter fixture for guarded_sysctl.yml; never calls the real sysctl.

Only for an explicitly opted-in disposable container. It executes the actual
streamed production script, with kernel reads/writes replaced at the OS boundary.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

STATE = Path("/tmp/hardenops-guard-kernel.json")
CALLS = Path("/tmp/hardenops-guard-calls.jsonl")


def fake_sysctl(argv, **kwargs):
    if argv[:2] not in (["/usr/sbin/sysctl", "-n"], ["/usr/sbin/sysctl", "-w"]):
        raise RuntimeError("Fixture refuses every other process execution")
    values = json.loads(STATE.read_text())
    if argv[1] == "-n":
        return SimpleNamespace(stdout=values[argv[2]] + "\n", stderr="")
    key, value = argv[2].split("=", 1)
    values[key] = value
    STATE.write_text(json.dumps(values))
    with CALLS.open("a") as output:
        output.write(json.dumps(argv) + "\n")
    return SimpleNamespace(stdout=key + " = " + value + "\n", stderr="")


def main():
    if (not sys.flags.isolated or os.environ.get("HARDENOPS_GUARD_FIXTURES") != "1"
            or not Path("/.dockerenv").is_file() or sys.argv[1:3] != ["-I", "-c"]):
        raise RuntimeError("Explicit isolated disposable-container fixture opt-in required")
    subprocess.run = fake_sysctl
    namespace = {"__name__": "streamed_guard_fixture"}
    exec(compile(sys.argv[3], "<streamed-production-script>", "exec"), namespace)
    if "HostReader" in namespace:
        original = namespace["HostReader"].text

        def fake_text(reader, absolute, limit=256_000):
            if absolute.startswith("/proc/sys/"):
                key = absolute[len("/proc/sys/"):].replace("/", ".")
                return json.loads(STATE.read_text())[key]
            return original(reader, absolute, limit)

        namespace["HostReader"].text = fake_text
    return namespace["main"]()


if __name__ == "__main__":
    sys.exit(main())
