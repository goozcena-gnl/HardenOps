#!/usr/bin/env python3
"""Reconcile the owned Apport hook with systemd's loaded command, without a journal.

The manager is the durable source of loaded state across controller failures.
NeedDaemonReload is diagnostic only: its mtime heuristic is not content proof.
The root seam and command runner are internal fixture interfaces, never CLI input.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from tools.sysctl_guard import (
        APPORT,
        UnsafePath,
        apport_content,
        assert_snapshot,
        assignment,
        snapshot_file,
        token,
    )
except ModuleNotFoundError:
    from sysctl_guard import (
        APPORT,
        UnsafePath,
        apport_content,
        assert_snapshot,
        assignment,
        snapshot_file,
        token,
    )

PROPERTIES = {"LoadState", "DropInPaths", "ExecStartPost", "NeedDaemonReload"}


def manager_state(run):
    result = run(
        ["/usr/bin/systemctl", "show", "apport.service", "--all", "--property=LoadState",
         "--property=DropInPaths", "--property=ExecStartPost", "--property=NeedDaemonReload"],
        capture_output=True, text=True, timeout=15, check=True,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"},
    )
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in PROPERTIES or (key in values and key != "ExecStartPost"):
            raise UnsafePath("Unexpected systemd property response")
        # systemctl prints one ExecStartPost property per array element.
        if key == "ExecStartPost" and values.get(key):
            values[key] += " " + value
        else:
            values[key] = value
    # systemctl omits empty command-array properties, including with --all.
    # Missing ExecStartPost means unsynchronized, never proof of success.
    if set(values) == PROPERTIES - {"ExecStartPost"}:
        values["ExecStartPost"] = ""
    if (set(values) != PROPERTIES or values["LoadState"] != "loaded"
            or values["NeedDaemonReload"] not in {"yes", "no"}):
        raise UnsafePath("Cannot establish loaded Apport metadata")
    commands = re.findall(r"\{ ([^{}]*) \}", values["ExecStartPost"])
    if " ".join("{ " + command + " }" for command in commands) != values["ExecStartPost"]:
        raise UnsafePath("Unrecognized systemd command representation")
    values["commands"] = commands
    return values


def loaded_hook(values, path):
    if APPORT not in values["DropInPaths"].split() or not values["commands"]:
        return False
    expected = f"path=/usr/sbin/sysctl ; argv[]=/usr/sbin/sysctl -p {path} ; ignore_errors=no ;"
    return values["commands"][-1].startswith(expected)


def reconcile(control, check=False, root="/", run=None):
    identifier = control["id"]
    verification = control["verification"]
    desired = control.get("desired", verification["expected"])
    accepted = verification.get("accepted_values", [verification["expected"]])
    if (not re.fullmatch(r"[a-z][a-z0-9_]{2,95}", identifier)
            or verification["key"] != "fs.suid_dumpable"
            or control["enforcement"] != "AUTOMATED"
            or not isinstance(desired, str) or not re.fullmatch(r"-?\d+", desired)
            or desired not in accepted):
        raise UnsafePath("Invalid approved Apport decision")
    if not any((Path(root) / unit).is_file() for unit in (
            "usr/lib/systemd/system/apport.service", "lib/systemd/system/apport.service")):
        return {"changed": False, "reloaded": False, "applicable": False}
    path = f"/etc/sysctl.d/99-z-hardenops-{identifier}.conf"
    hook = snapshot_file(APPORT, root, missing_ok=True)
    if not hook["exists"]:
        return {"changed": False, "reloaded": False, "applicable": True}
    current = snapshot_file(path, root)
    if hook["content"] != apport_content(path):
        raise UnsafePath("Apport reload requires exact safe owned persistence")
    if not current["exists"]:
        # The guard must first create persistence in its validated directory.
        return {"changed": False, "reloaded": False, "applicable": True}
    if assignment(current["content"], "fs.suid_dumpable") not in (
            accepted + verification.get("remediable_values", [])):
        raise UnsafePath("Unrecognized owned sysctl persistence")
    run = run or subprocess.run
    before = manager_state(run)
    if loaded_hook(before, path):
        return {"changed": False, "reloaded": False, "applicable": True,
                "synchronized": True, "need_daemon_reload": before["NeedDaemonReload"]}
    if check:
        return {"changed": True, "reloaded": False, "applicable": True,
                "synchronized": False, "need_daemon_reload": before["NeedDaemonReload"]}
    assert_snapshot(APPORT, token(hook), root, missing_ok=True)
    assert_snapshot(path, token(current), root)
    run(["/usr/bin/systemctl", "daemon-reload"], capture_output=True, text=True,
        timeout=30, check=True,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    assert_snapshot(APPORT, token(hook), root, missing_ok=True)
    assert_snapshot(path, token(current), root)
    after = manager_state(run)
    if not loaded_hook(after, path):
        raise UnsafePath("Owned Apport command is not loaded after daemon-reload")
    return {"changed": True, "reloaded": True, "applicable": True,
            "synchronized": True, "need_daemon_reload": after["NeedDaemonReload"]}


def main():
    try:
        raw = sys.stdin.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise UnsafePath("Input exceeds limit")
        request = json.loads(raw)
        if type(request.get("check")) is not bool or os.geteuid() != 0:
            raise UnsafePath("Root and an explicit check-mode Boolean are required")
        result = reconcile(request["control"], check=request["check"])
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print("Apport metadata refused: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
