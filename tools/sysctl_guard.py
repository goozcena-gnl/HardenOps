#!/usr/bin/env python3
"""Descriptor-bound storage for owned sysctls; explicit single-key activation.

The trust boundary excludes hostile root and concurrent privileged configuration
writers. Directory descriptors and no-follow opens prevent an unprivileged path
substitution; snapshot comparisons detect stale plans, not an atomic transaction
against another root process. No file supplied by the guest is passed to sysctl -p.
"""

import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

LIMIT = 256_000
APPORT = "/etc/systemd/system/apport.service.d/90-hardenops-suid-dumpable.conf"


class UnsafePath(OSError):
    """Untrusted storage or a changed precondition requires operator review."""


def safe_metadata(metadata, directory=False):
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    return (kind(metadata.st_mode) and metadata.st_uid == 0
            and not metadata.st_mode & 0o022
            and (directory or metadata.st_nlink == 1))


def identity(metadata, directory=False):
    values = [metadata.st_dev, metadata.st_ino, metadata.st_uid,
              metadata.st_gid, stat.S_IMODE(metadata.st_mode)]
    if not directory:
        values += [metadata.st_nlink, metadata.st_size,
                   metadata.st_mtime_ns, metadata.st_ctime_ns]
    return values


@contextmanager
def trusted_parent(path, root="/", missing_ok=False, create=False):
    """Walk from the trusted root anchor, retaining checked directory descriptors.

    ``root`` is an internal fixture seam, never accepted by the production CLI.
    Only the final Apport drop-in directory may be created, never unsafe parents.
    """
    parts = PurePosixPath(path).parts
    if not path.startswith("/") or ".." in parts or len(parts) < 3:
        raise UnsafePath("Invalid owned path")
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise UnsafePath("No-follow directory descriptors are required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    opened = []
    try:
        descriptor = os.open(root, flags)
        opened.append(descriptor)
        metadata = os.fstat(descriptor)
        if not safe_metadata(metadata, directory=True):
            raise UnsafePath("Untrusted root anchor")
        parents = [["/", identity(metadata, directory=True)]]
        for index, part in enumerate(parts[1:-1], 1):
            try:
                child = os.open(part, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if create and path == APPORT and index == len(parts) - 2:
                    os.mkdir(part, 0o755, dir_fd=descriptor)
                    child = os.open(part, flags, dir_fd=descriptor)
                elif missing_ok and path == APPORT and index == len(parts) - 2:
                    yield descriptor, parts[-1], parents, list(parts[index:-1])
                    return
                else:
                    raise UnsafePath("Required owned directory is missing")
            opened.append(child)
            metadata = os.fstat(child)
            if not safe_metadata(metadata, directory=True):
                raise UnsafePath("Untrusted owned directory: " + part)
            parents.append([part, identity(metadata, directory=True)])
            descriptor = child
        yield descriptor, parts[-1], parents, []
    finally:
        for descriptor in reversed(opened):
            os.close(descriptor)


def read_at(directory, name):
    """Validate metadata and read bytes from the very same no-follow descriptor."""
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
    except FileNotFoundError:
        return {"exists": False, "content": None}
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not safe_metadata(before):
            raise UnsafePath("Owned file must be regular, root-owned, single-link and not writable by others")
        content = stream.read(LIMIT + 1)
        after = os.fstat(stream.fileno())
        if len(content) > LIMIT or identity(before) != identity(after):
            raise UnsafePath("Owned file changed during read or exceeds limit")
        if identity(os.stat(name, dir_fd=directory, follow_symlinks=False)) != identity(after):
            raise UnsafePath("Owned path changed during read")
    try:
        text = content.decode("utf-8")
    except UnicodeError as exc:
        raise UnsafePath("Invalid owned file encoding") from exc
    return {"exists": True, "uid": before.st_uid, "gid": before.st_gid,
            "mode": format(stat.S_IMODE(before.st_mode), "04o"),
            "identity": identity(before), "sha256": hashlib.sha256(content).hexdigest(),
            "content": text}


def snapshot_file(path, root="/", missing_ok=False):
    with trusted_parent(path, root, missing_ok=missing_ok) as (directory, name, parents, missing):
        result = {"exists": False, "content": None} if missing else read_at(directory, name)
        result.update(parents=parents, missing_parents=missing)
        return result


def token(snapshot):
    return {key: value for key, value in snapshot.items() if key != "content"}


def assignment(content, key):
    values = []
    for line in content.splitlines():
        line = line.split("#", 1)[0].split(";", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise UnsafePath("Unexpected owned persistence content")
        name, value = (part.strip() for part in line.split("=", 1))
        if name != key:
            raise UnsafePath("Unexpected key in owned persistence")
        values.append(value)
    if len(values) != 1:
        raise UnsafePath("Expected exactly one owned assignment")
    return values[0]


def apport_content(sysctl_file):
    return "[Service]\nExecStartPost=/usr/sbin/sysctl -p %s\n" % sysctl_file


def assert_snapshot(path, expected, root, missing_ok=False):
    current = snapshot_file(path, root, missing_ok=missing_ok)
    if token(current) != expected:
        raise UnsafePath("Owned storage changed since inspection: " + path)
    return current


def replace_file(path, content, mode, expected, root):
    """Publish only canonical bytes, with final metadata before publication."""
    assert_snapshot(path, token(expected), root, missing_ok=path == APPORT)
    with trusted_parent(path, root, create=path == APPORT) as (directory, name, _, _):
        current = read_at(directory, name)
        # Parents may now include a directory we just created; leaf identity must
        # still match. This comparison is not a CAS against privileged writers.
        if token(current) != {k: v for k, v in token(expected).items()
                              if k not in {"parents", "missing_parents"}}:
            raise UnsafePath("Owned leaf changed before replacement")
        if current["content"] == content and current.get("mode") == mode and current.get("gid") == 0:
            return False
        temporary = ".hardenops-" + secrets.token_hex(16)
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchown(stream.fileno(), 0, 0)
                os.fchmod(stream.fileno(), int(mode, 8))
                stream.write(content.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            if token(read_at(directory, name)) != token(current):
                raise UnsafePath("Owned leaf changed during replacement")
            os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
    return True


def remove_legacy(path, expected, root):
    assert_snapshot(path, token(expected), root)
    with trusted_parent(path, root) as (directory, name, _, _):
        if token(read_at(directory, name)) != {k: v for k, v in token(expected).items()
                                              if k not in {"parents", "missing_parents"}}:
            raise UnsafePath("Legacy leaf changed before removal")
        os.unlink(name, dir_fd=directory)
        os.fsync(directory)


def runtime_value(key):
    result = subprocess.run(["/usr/sbin/sysctl", "-n", key], capture_output=True,
                            text=True, timeout=15, check=True,
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    return result.stdout.strip()


def activate(key, value):
    result = subprocess.run(["/usr/sbin/sysctl", "-w", key + "=" + value],
                            capture_output=True, text=True, timeout=15, check=True,
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    if result.stderr.strip():
        raise UnsafePath("sysctl activation reported an error")


def apply_control(control, check=False, root="/", read_runtime=runtime_value, set_runtime=activate):
    """Revalidate the observed lease and apply only its approved single key."""
    identifier = control["id"]
    verification = control["verification"]
    key, desired = verification["key"], control["desired"]
    accepted = verification.get("accepted_values", [verification["expected"]])
    if (not re.fullmatch(r"[a-z][a-z0-9_]{2,95}", identifier)
            or not re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+", key)
            or not isinstance(desired, str) or not re.fullmatch(r"-?\d+", desired)
            or desired not in accepted or control["enforcement"] != "AUTOMATED"):
        raise UnsafePath("Invalid approved sysctl decision")
    path = f"/etc/sysctl.d/99-z-hardenops-{identifier!s}.conf"
    legacy_path = f"/etc/sysctl.d/90-hardenops-{identifier!s}.conf"
    observed = control["observed"]
    persistence = observed["persistence"]
    if persistence["path"] != path or persistence["legacy"]["path"] != legacy_path:
        raise UnsafePath("Unexpected owned path")
    current = assert_snapshot(path, persistence["snapshot"], root)
    legacy = assert_snapshot(legacy_path, persistence["legacy"]["snapshot"], root)
    live = read_runtime(key)
    if live != observed["runtime"]:
        raise UnsafePath("Runtime changed since inspection; replan required")
    known = accepted + verification.get("remediable_values", [])
    if key == "kernel.sysrq" and verification.get("remediable_range") == [1, 511]:
        known += [str(value) for value in range(1, 512)]
    values = [live] + [assignment(item["content"], key) for item in (current, legacy) if item["exists"]]
    if any(value not in known for value in values):
        raise UnsafePath("Unrecognized sysctl value")
    strongest = max((value for value in values if value in accepted),
                    key=accepted.index, default=verification["expected"])
    if desired != strongest or (key == "kernel.yama.ptrace_scope" and desired == "3" and live != "3"):
        raise UnsafePath("Decision would weaken state or activate irreversible Yama")
    mode = format(int(current.get("mode", "0644"), 8) & int(legacy.get("mode", "0644"), 8) & 0o644, "04o")
    hook = persistence["apport"]
    required = key == "fs.suid_dumpable" and any(
        (Path(root) / unit).is_file() for unit in (
            "usr/lib/systemd/system/apport.service", "lib/systemd/system/apport.service"))
    if hook["required"] != required:
        raise UnsafePath("Apport applicability changed since inspection")
    override = assert_snapshot(APPORT, hook["snapshot"], root, missing_ok=True) if required else None
    if override and override["exists"] and override["content"] != apport_content(path):
        raise UnsafePath("Unexpected Apport override")
    hook_mode = format(int(override.get("mode", "0644"), 8) & 0o644, "04o") if required else None
    canonical = key + " = " + desired + "\n"
    changed = (current["content"] != canonical or current.get("mode") != mode
               or current.get("gid") != 0 or live != desired or legacy["exists"])
    apport_changed = bool(required and (override["content"] != apport_content(path)
                                       or override.get("mode") != hook_mode or override.get("gid") != 0))
    if not check:
        changed = replace_file(path, canonical, mode, current, root) or changed
        if required:
            apport_changed = replace_file(APPORT, apport_content(path), hook_mode, override, root)
        # Never reload a pathname. Recheck the approved runtime just before the
        # explicit key/value call. Concurrent root writers are outside the lease.
        if read_runtime(key) != live:
            raise UnsafePath("Runtime changed before activation; replan required")
        if live != desired:
            set_runtime(key, desired)
        if legacy["exists"]:
            remove_legacy(legacy_path, legacy, root)
    return {"changed": bool(changed or apport_changed), "apport_changed": apport_changed}


def main():
    try:
        raw = sys.stdin.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise UnsafePath("Input exceeds limit")
        request = json.loads(raw)
        if type(request.get("check")) is not bool:
            raise UnsafePath("Explicit check-mode Boolean required")
        if os.geteuid() != 0:
            raise UnsafePath("Root required")
        result = apply_control(request["control"], check=request["check"])
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        print("Guarded sysctl refused: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
