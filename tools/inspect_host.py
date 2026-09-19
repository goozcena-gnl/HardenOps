#!/usr/bin/env python3
"""Read-only Linux host inspection; JSON input/output, Python standard library only.

The controller sends the version-controlled catalogue. This process independently
reads host state; it never invokes an enforcement module or changes the host.
"""

import datetime
import json
import os
import re
import socket
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path

LEVELS = {"minimal": 0, "intermediary": 1, "enhanced": 2, "high": 3}
STATUSES = {
    "AUTOMATED", "VERIFIED", "AUDIT_ONLY", "MANUAL", "FUTURE",
    "OUT_OF_SCOPE_REFERENCE_REQUIRED",
}
RESULTS = (
    "PASS", "FAIL", "AUDIT_ONLY", "MANUAL", "NOT_APPLICABLE", "UNSUPPORTED",
    "FUTURE", "OUT_OF_SCOPE_REFERENCE_REQUIRED",
)
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,95}$")
SYSCTL_KEY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
MAX_INPUT_BYTES = 2 * 1024 * 1024


def validate_input(payload):
    """Fail closed on malformed policy, profile, network assumptions, or OS."""
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")
    level = payload.get("level")
    if level not in ("minimal", "intermediary"):
        raise ValueError("Only minimal and intermediary profiles are implemented in v0.1")
    config = payload.get("config")
    if not isinstance(config, dict) or config.get("workload_profile") != "generic_server":
        raise ValueError("config.workload_profile must be generic_server")
    network = config.get("network")
    if not isinstance(network, dict):
        raise ValueError("config.network is required")
    for field in ("routing", "ipv6_required"):
        if type(network.get(field)) is not bool:
            raise ValueError("config.network.%s must be a Boolean" % field)
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        raise ValueError("Detected facts are required")
    distro = facts.get("distribution")
    version = str(facts.get("distribution_version", ""))
    family = facts.get("os_family")
    supported = (
        distro == "Ubuntu" and re.fullmatch(r"24\.04(?:\.\d+)?", version)
        and family == "Debian"
    ) or (
        distro == "Rocky" and re.fullmatch(r"9(?:\.\d+)*", version)
        and family == "RedHat"
    )
    if not supported:
        raise ValueError("Unsupported distribution: %s %s (%s); supported: Ubuntu 24.04, Rocky 9"
                         % (distro, version, family))
    controls = payload.get("controls")
    if not isinstance(controls, list) or not controls or len(controls) > 1000:
        raise ValueError("controls must be a non-empty list of at most 1000 entries")
    seen = set()
    for control in controls:
        if not isinstance(control, dict):
            raise ValueError("Each control must be an object")
        control_id = control.get("id", "")
        if not isinstance(control_id, str) or not IDENTIFIER.fullmatch(control_id):
            raise ValueError("Invalid control id")
        if control_id in seen:
            raise ValueError("Duplicate control id: " + control_id)
        seen.add(control_id)
        if control.get("level") not in LEVELS:
            raise ValueError("Unknown control level: " + control_id)
        enforcement = control.get("enforcement", {})
        if not isinstance(enforcement, dict) or enforcement.get("status") not in STATUSES:
            raise ValueError("Unknown enforcement status: " + control_id)
        applicability = control.get("applicability", {})
        if not isinstance(applicability, dict):
            raise ValueError("Invalid applicability: " + control_id)
        families = applicability.get("os_families")
        if not isinstance(families, list) or not families or not set(families) <= {"Debian", "RedHat"}:
            raise ValueError("Invalid OS families: " + control_id)
        for field in ("non_router", "ipv6_unused"):
            if field in applicability and type(applicability[field]) is not bool:
                raise ValueError("Applicability conditions must be Booleans: " + control_id)
        source = control.get("source")
        if not isinstance(source, dict) or not source.get("document") or not source.get("recommendation"):
            raise ValueError("Missing source traceability: " + control_id)
        verification = control.get("verification", {})
        if not isinstance(verification, dict):
            raise ValueError("Invalid verification definition: " + control_id)
        verification_type = verification.get("type")
        if enforcement["status"] in {"AUTOMATED", "VERIFIED"} and verification_type not in {"sysctl", "file"}:
            raise ValueError("Deterministic control requires sysctl or file verification: " + control_id)
        if verification_type == "sysctl":
            key = verification.get("key", "")
            if not isinstance(key, str) or not SYSCTL_KEY.fullmatch(key):
                raise ValueError("Invalid sysctl key: " + control_id)
            values = verification.get("accepted_values", [verification.get("expected")])
            if (not isinstance(values, list) or not values
                    or any(not isinstance(value, str) or not re.fullmatch(r"-?\d+", value) for value in values)
                    or len(set(values)) != len(values)
                    or verification.get("expected") != values[0]):
                raise ValueError("accepted_values must list expected then explicitly stronger numeric strings: " + control_id)
            remediable = verification.get("remediable_values", [])
            if (not isinstance(remediable, list)
                    or any(not isinstance(value, str) or not re.fullmatch(r"-?\d+", value) for value in remediable)
                    or len(set(remediable)) != len(remediable) or set(values) & set(remediable)):
                raise ValueError("Invalid explicitly remediable values: " + control_id)
            if "remediable_range" in verification and (key != "kernel.sysrq" or verification["remediable_range"] != [1, 511]):
                raise ValueError("Only kernel.sysrq permits remediable_range [1, 511]")
        elif verification_type == "file":
            path = verification.get("path", "")
            if not isinstance(path, str) or not path.startswith("/") or ".." in Path(path).parts:
                raise ValueError("Invalid absolute file path: " + control_id)
            if not re.fullmatch(r"0[0-7]{3}", str(verification.get("max_mode", ""))):
                raise ValueError("File max_mode must be an octal string: " + control_id)
            groups = verification.get("allowed_groups")
            if not isinstance(groups, list) or not groups or any(not isinstance(group, str) for group in groups):
                raise ValueError("File allowed_groups must be provided: " + control_id)
    disabled = config.get("disabled_controls", [])
    if (not isinstance(disabled, list) or any(not isinstance(item, str) for item in disabled)
            or not set(disabled) <= seen or len(set(disabled)) != len(disabled)):
        raise ValueError("config.disabled_controls must contain unique known control IDs")


def run_command(argv):
    """Bounded, shell-free inventory commands, with no secret-bearing arguments."""
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=15,
                                check=False, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "reason": type(exc).__name__}
    if result.returncode:
        return {"available": False, "reason": "command exit %s" % result.returncode}
    # Output is neither forwarded verbatim nor allowed to grow the evidence file.
    return {"available": True, "lines": result.stdout[:2_000_000].splitlines(),
            "truncated": len(result.stdout) > 2_000_000}


class HostReader:
    """A filesystem adapter permits deterministic tests without touching /proc."""

    def __init__(self, root="/", command_runner=run_command):
        self.root = Path(root)
        self.command_runner = command_runner

    def path(self, absolute):
        return self.root / absolute.lstrip("/")

    def metadata(self, absolute):
        return self.path(absolute).lstat()

    def text(self, absolute, limit=256_000):
        path = self.path(absolute)
        # Do not follow final symlinks in configuration or sensitive account files.
        if path.is_symlink():
            raise OSError("Symlink refused")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "r", encoding="utf-8", errors="replace") as stream:
            text = stream.read(limit + 1)
        if len(text) > limit:
            raise OSError("Read limit exceeded")
        return text

    def group_name(self, gid):
        try:
            for line in self.text("/etc/group").splitlines():
                fields = line.split(":")
                if len(fields) >= 3 and fields[2].isdigit() and int(fields[2]) == gid:
                    return fields[0]
        except OSError:
            pass
        return "root" if gid == 0 else str(gid)

    def children(self, absolute, limit=5000):
        entries, skipped, truncated = [], 0, False
        with os.scandir(self.path(absolute)) as items:
            for index, item in enumerate(items):
                if index >= limit:
                    truncated = True
                    break
                try:
                    metadata = item.stat(follow_symlinks=False)
                    entries.append((absolute.rstrip("/") + "/" + item.name, metadata))
                except OSError:
                    skipped += 1
        return entries, skipped, truncated


def persistence_evidence(reader, control_id, key):
    path = "/etc/sysctl.d/90-hardenops-%s.conf" % control_id
    evidence = {"path": path, "value": None, "safe_file": False, "unsafe_path": False, "exists": False}
    try:
        metadata = reader.metadata(path)
        evidence["exists"] = True
        evidence.update(mode=format(stat.S_IMODE(metadata.st_mode), "04o"), uid=metadata.st_uid)
        if not stat.S_ISREG(metadata.st_mode):
            evidence["unsafe_path"] = True
            evidence["reason"] = "Owned persistence path is not a regular file"
            return evidence
        evidence["safe_file"] = metadata.st_uid == 0 and not (metadata.st_mode & 0o022)
        assignments = []
        for line in reader.text(path).splitlines():
            line = line.split("#", 1)[0].split(";", 1)[0].strip()
            if not line:
                continue
            if "=" not in line:
                evidence["unsafe_path"] = True
                evidence["reason"] = "Unexpected persistence content"
                return evidence
            name, value = (part.strip() for part in line.split("=", 1))
            if name != key:
                evidence["unsafe_path"] = True
                evidence["reason"] = "Unexpected key in owned persistence file"
                return evidence
            assignments.append(value)
        if len(assignments) == 1:
            evidence["value"] = assignments[0]
        else:
            evidence["unsafe_path"] = True
            evidence["reason"] = "Expected exactly one owned assignment"
    except OSError as exc:
        evidence["reason"] = type(exc).__name__
        evidence["unsafe_path"] = evidence["exists"] or not isinstance(exc, FileNotFoundError)
    return evidence


def inspect_sysctl(control, reader):
    verification = control["verification"]
    key = verification["key"]
    accepted = verification.get("accepted_values", [verification["expected"]])
    expected = {"key": key, "accepted_values": accepted,
                "persistence": "same accepted value in safe HardenOps-owned file"}
    try:
        runtime = reader.text("/proc/sys/" + key.replace(".", "/"), limit=128).strip()
    except OSError as exc:
        return dict(result="UNSUPPORTED", reason="Kernel setting unavailable: " + type(exc).__name__,
                    expected=expected, observed=None, desired=verification["expected"], needs_change=False)
    persistent = persistence_evidence(reader, control["id"], key)
    known = accepted + verification.get("remediable_values", [])
    if verification.get("remediable_range") == [1, 511]:
        known += [str(value) for value in range(1, 512)]
    if (persistent["unsafe_path"] or runtime not in known
            or (persistent["value"] is not None and persistent["value"] not in known)):
        return dict(result="UNSUPPORTED", reason="Unsafe persistence path or unrecognized setting value; operator review required",
                    expected=expected, observed={"runtime": runtime, "persistence": persistent},
                    desired=None, needs_change=False)
    known_values = [value for value in (runtime, persistent["value"]) if value in accepted]
    desired = max(known_values, key=accepted.index) if known_values else verification["expected"]
    if key == "kernel.yama.ptrace_scope" and desired == "3" and runtime != "3":
        return dict(result="UNSUPPORTED", reason="Applying persisted Yama value 3 would be irreversible until reboot; operator review required",
                    expected=expected, observed={"runtime": runtime, "persistence": persistent},
                    desired=desired, needs_change=False)
    passed = runtime == desired and persistent["value"] == desired and persistent["safe_file"]
    return dict(result="PASS" if passed else "FAIL",
                reason=("Runtime and owned persistence satisfy the selected baseline" if passed else
                        "Runtime or owned persistence differs from the strongest explicitly accepted observed value"),
                expected=expected, observed={"runtime": runtime, "persistence": persistent},
                desired=desired,
                desired_persistence_mode=format(int(persistent.get("mode", "0644"), 8) & 0o644, "04o"),
                needs_change=not passed)


def inspect_file(control, reader):
    verification = control["verification"]
    expected = {"path": verification["path"], "uid": 0,
                "max_mode": verification["max_mode"], "allowed_groups": verification["allowed_groups"]}
    try:
        metadata = reader.metadata(verification["path"])
    except OSError as exc:
        return dict(result="UNSUPPORTED", reason="Required file unavailable; creation is refused: " + type(exc).__name__,
                    expected=expected, observed=None, needs_change=False)
    if not stat.S_ISREG(metadata.st_mode):
        return dict(result="UNSUPPORTED", reason="Sensitive path must be a regular file, not a symlink or device",
                    expected=expected, observed={"regular_file": False}, needs_change=False)
    mode = stat.S_IMODE(metadata.st_mode)
    max_mode = int(verification["max_mode"], 8)
    desired_mode = format(mode & max_mode, "04o")
    group = reader.group_name(metadata.st_gid)
    passed = metadata.st_uid == 0 and group in verification["allowed_groups"] and not (mode & ~max_mode)
    return dict(result="PASS" if passed else "FAIL",
                reason="Ownership and permission ceiling satisfied" if passed else "Ownership or permissions exceed the allowed baseline",
                expected=expected, observed={"mode": format(mode, "04o"), "uid": metadata.st_uid,
                                             "gid": metadata.st_gid, "group": group},
                desired_mode=desired_mode,
                desired_group=group if group in verification["allowed_groups"] else verification["allowed_groups"][0],
                needs_change=not passed)


def safe_names(lines, limit=80):
    names = sorted({line.strip() for line in lines if re.fullmatch(r"[A-Za-z0-9_.@:+/-]{1,160}", line.strip())})
    return {"count": len(names), "sample": names[:limit], "sample_truncated": len(names) > limit}


def audit_accounts(reader):
    try:
        text = reader.text("/etc/passwd")
    except OSError as exc:
        return {"available": False, "reason": type(exc).__name__}
    accounts = []
    for line in text.splitlines():
        fields = line.split(":")
        if len(fields) == 7 and fields[2].isdigit() and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}\$?", fields[0]):
            accounts.append((fields[0], int(fields[2]), fields[6]))
    return {"available": True, "account_count": len(accounts),
            "uid_zero_accounts": [name for name, uid, _ in accounts if uid == 0],
            "interactive_accounts": [name for name, _, shell in accounts
                                     if shell and shell.rsplit("/", 1)[-1] not in {"false", "nologin", "sync", "shutdown", "halt"}][:80],
            "scope": "Local passwd account names, UIDs and shell classification; no password data read"}


def audit_inventory(reader, argv):
    output = reader.command_runner(argv)
    if not output.get("available"):
        return output
    # The first field is the package or service identifier; descriptions are excluded.
    names = [line.split()[0] for line in output["lines"] if line.split()]
    return dict(available=True, **safe_names(names), output_truncated=output.get("truncated", False))


def filesystem_snapshot(reader):
    """Bounded direct-child sample; never a recursive scan of arbitrary filesystems."""
    if hasattr(reader, "_filesystem_snapshot"):
        return reader._filesystem_snapshot
    observed, entries = [], []
    for directory in ("/tmp", "/var/tmp", "/etc", "/usr/bin", "/usr/sbin"):
        try:
            metadata = reader.metadata(directory)
            entry = {"path": directory, "mode": format(stat.S_IMODE(metadata.st_mode), "04o"),
                     "uid": metadata.st_uid, "gid": metadata.st_gid}
            if stat.S_ISDIR(metadata.st_mode):
                entries.append((directory, metadata))
                children, skipped, truncated = reader.children(directory)
                entries.extend(children)
                entry.update(children_scanned=len(children), unreadable_children=skipped,
                             truncated=truncated)
            observed.append(entry)
        except OSError as exc:
            observed.append({"path": directory, "available": False, "reason": type(exc).__name__})
    reader._filesystem_snapshot = (observed, entries)
    return reader._filesystem_snapshot


def audit_filesystem(reader, recommendation):
    directories, entries = filesystem_snapshot(reader)
    observed = {"directories": directories, "scope": "Listed directories and direct children only; maximum 5000 children per directory; no symlinks followed",
                "excluded": "All unlisted directories, deeper descendants, external identity providers and inaccessible entries",
                "recommendation": recommendation, "complete_system_scan": False}
    local_uids, local_gids = set(), set()
    if recommendation == "R53":
        try:
            for path, output in (("/etc/passwd", local_uids), ("/etc/group", local_gids)):
                for line in reader.text(path).splitlines():
                    fields = line.split(":")
                    if len(fields) >= 3 and fields[2].isdigit():
                        output.add(int(fields[2]))
        except OSError as exc:
            observed.update(available=False, reason="Local identity database unavailable: " + type(exc).__name__)
            return observed
        observed["identity_scope"] = "IDs absent from local passwd/group databases are candidates; external NSS identities require operator validation"
    findings = []
    count = 0
    for path, metadata in entries:
        mode = metadata.st_mode
        regular_or_directory = stat.S_ISREG(mode) or stat.S_ISDIR(mode)
        selected = (
            recommendation == "R53" and regular_or_directory
            and (metadata.st_uid not in local_uids or metadata.st_gid not in local_gids)
        ) or (
            recommendation == "R54" and stat.S_ISDIR(mode) and bool(mode & 0o002)
        ) or (
            recommendation == "R56" and stat.S_ISREG(mode) and bool(mode & 0o6000)
        )
        if selected:
            count += 1
            if len(findings) >= 80:
                continue
            entry = {"path": path, "uid": metadata.st_uid, "gid": metadata.st_gid,
                     "mode": format(stat.S_IMODE(mode), "04o")}
            if recommendation == "R54":
                entry.update(sticky=bool(mode & stat.S_ISVTX), root_owned=metadata.st_uid == 0,
                             protection_satisfied=bool(mode & stat.S_ISVTX) and metadata.st_uid == 0)
            if recommendation == "R53":
                entry.update(uid_in_local_database=metadata.st_uid in local_uids,
                             gid_in_local_database=metadata.st_gid in local_gids)
            findings.append(entry)
    observed.update(candidate_count=count, candidates=findings, candidates_truncated=count > 80)
    return observed


def inspect_audit(control, reader, facts):
    check = control.get("verification", {}).get("check")
    if check == "accounts":
        observed = audit_accounts(reader)
    elif check == "packages":
        argv = ["dpkg-query", "-W", "-f=${binary:Package}\n"] if facts["os_family"] == "Debian" else ["rpm", "-qa", "--qf", "%{NAME}\n"]
        observed = audit_inventory(reader, argv)
    elif check == "services":
        observed = audit_inventory(reader, ["systemctl", "list-unit-files", "--type=service", "--no-legend", "--no-pager"])
    elif check == "filesystem":
        observed = audit_filesystem(reader, control["source"]["recommendation"])
    else:
        observed = {"available": False, "reason": "No bounded inventory implemented for this audit"}
    return dict(result="AUDIT_ONLY", reason="Evidence requires operator review; inventory does not establish recommendation satisfaction",
                expected=control.get("description", "Operator review required"), observed=observed, needs_change=False)


def summarize(controls):
    counts = Counter(control["result"] for control in controls)
    applicable = [control for control in controls if control["result"] != "NOT_APPLICABLE"]
    return {"total_controls": len(controls), "applicable_controls": len(applicable),
            "automated_controls": sum(control["enforcement"] == "AUTOMATED" for control in applicable),
            "verified_controls": sum(control["result"] in {"PASS", "FAIL"} for control in applicable),
            "reboot_required_controls": sum(bool(control["reboot_required"]) for control in applicable),
            "changes_required": sum(control["needs_change"] for control in applicable),
            "results": {result: counts[result] for result in RESULTS}}


def inspect(payload, reader=None):
    validate_input(payload)
    reader = reader or HostReader()
    results = []
    for control in payload["controls"]:
        result = {field: control.get(field) for field in ("id", "source", "domain", "level", "title", "verification", "risk", "reversible", "transition")}
        result.update(enforcement=control["enforcement"]["status"],
                      reboot_required=bool(control.get("reboot_required", False)),
                      needs_change=False, expected=None, observed=None)
        applicability = control["applicability"]
        reason = None
        if control["id"] in payload["config"].get("disabled_controls", []):
            reason = "Control explicitly disabled by operator exception"
        elif LEVELS[control["level"]] > LEVELS[payload["level"]]:
            reason = "Control level exceeds selected cumulative profile"
        elif payload["facts"]["os_family"] not in applicability["os_families"]:
            reason = "Detected OS family is outside this control's applicability"
        elif applicability.get("non_router") and payload["config"]["network"]["routing"]:
            reason = "network.routing=true; generic server setting does not apply"
        elif applicability.get("ipv6_unused") and payload["config"]["network"]["ipv6_required"]:
            reason = "network.ipv6_required=true; IPv6 must remain available"
        if reason:
            result.update(result="NOT_APPLICABLE", reason=reason)
        elif result["enforcement"] in {"MANUAL", "FUTURE", "OUT_OF_SCOPE_REFERENCE_REQUIRED"}:
            result.update(result=result["enforcement"], reason=control.get("description", "Operator action required"))
        elif result["enforcement"] == "AUDIT_ONLY":
            result.update(inspect_audit(control, reader, payload["facts"]))
        elif control["verification"]["type"] == "sysctl":
            result.update(inspect_sysctl(control, reader))
        else:
            result.update(inspect_file(control, reader))
        # A verifier-only finding must never enter the automatic remediation queue.
        if result["enforcement"] != "AUTOMATED":
            result["needs_change"] = False
        results.append(result)
    return {"schema_version": 1, "host": payload.get("host") or payload["facts"].get("host") or socket.gethostname(),
            "hardenops_version": "0.1.0", "catalogue": payload.get("catalogue", {}),
            "facts": payload["facts"], "profile": payload["level"], "config": payload["config"],
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "verification_scope": "Current runtime, sensitive file metadata and HardenOps-owned persistence files; full boot-time sysctl precedence is not proven",
            "controls": results, "summary": summarize(results)}


def main():
    try:
        raw = sys.stdin.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("JSON input exceeds size limit")
        payload = json.loads(raw)
        report = inspect(payload)
    except (ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
