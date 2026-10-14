#!/usr/bin/env python3
"""Validate a same-repository Dependabot pip PR and mirror its direct pins.

Only the trusted default-branch checkout is used for executable files. No
untrusted PR scripts are checked out or run. This script never pushes commits.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.request
from pathlib import Path

ALLOWED_FILES = frozenset({
    "requirements-dev.in", "requirements-dev.txt", "locks/py312.txt", "locks/py313.txt"
})
PIN = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9._-]*)==([0-9][a-zA-Z0-9.!+_-]*)$")
SHA = re.compile(r"^[a-f0-9]{40}$")


class GuardError(ValueError):
    """The PR is not an eligible single-package update."""


def pins(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in data.decode("utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        m = PIN.fullmatch(text)
        if not m:
            raise GuardError(f"Unsupported direct pin syntax: {text[:90]}")
        name = re.sub(r"[-_.]+", "-", m.group(1)).lower()
        if name in result:
            raise GuardError(f"Duplicate direct pin: {name}")
        result[name] = m.group(2)
    if len(result) != 11:
        raise GuardError(f"Expected 11 direct pins, got {len(result)}")
    return result


def validate_change(base: bytes, candidate: bytes, files: list[dict]) -> tuple[str, str]:
    paths = {x.get("filename") for x in files}
    if (not paths or "requirements-dev.in" not in paths or
            not paths <= ALLOWED_FILES or
            any(x.get("status") != "modified" for x in files) or
            len(paths) != len(files)):
        raise GuardError("Unexpected PR file scope or missing input")
    before, after = pins(base), pins(candidate)
    if set(before) != set(after):
        raise GuardError("Direct package set changed")
    changed = [name for name in before if before[name] != after[name]]
    if len(changed) != 1:
        raise GuardError(f"Expected exactly one changed direct pin, got {len(changed)}")
    left, right = base.splitlines(keepends=True), candidate.splitlines(keepends=True)
    if len(left) != len(right) or sum(a != b for a, b in zip(left, right)) != 1:
        raise GuardError("Direct input must differ by exactly one version line")
    return changed[0], after[changed[0]]


def validate_metadata(pr: dict, repo: str, sha: str, base_sha: str) -> None:
    if not SHA.fullmatch(sha) or not SHA.fullmatch(base_sha):
        raise GuardError("Malformed SHA")
    if pr.get("state") != "open" or pr.get("merged_at"):
        raise GuardError("PR is not open and unmerged")
    if pr.get("user", {}).get("login") != "dependabot[bot]":
        raise GuardError("PR author is not Dependabot")
    head, base = pr.get("head", {}), pr.get("base", {})
    if (head.get("sha") != sha or not head.get("ref", "").startswith("dependabot/pip/") or
            head.get("repo", {}).get("full_name") != repo or
            base.get("ref") != "main" or base.get("sha") != base_sha or
            base.get("repo", {}).get("full_name") != repo):
        raise GuardError("PR head/base/branch did not match reviewed inputs")
    if pr.get("changed_files", 999) > len(ALLOWED_FILES):
        raise GuardError("Too many changed files")


def get_json(url: str, token: str) -> dict | list:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "HardenOps-Lock-Preparation",
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)


def prepare(*, repo: str, number: int, head_sha: str, base_sha: str,
            token: str, root: Path) -> dict:
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo) or not 1 <= number <= 999999:
        raise GuardError("Invalid repository or PR number")
    if not SHA.fullmatch(head_sha) or not SHA.fullmatch(base_sha):
        raise GuardError("Invalid SHA")
    prefix = f"https://api.github.com/repos/{repo}"
    pr = get_json(f"{prefix}/pulls/{number}", token)
    validate_metadata(pr, repo, head_sha, base_sha)
    files = get_json(f"{prefix}/pulls/{number}/files?per_page=100", token)
    if len(files) != pr["changed_files"]:
        raise GuardError("Incomplete PR file listing")
    response = get_json(f"{prefix}/contents/requirements-dev.in?ref={head_sha}", token)
    if response.get("encoding") != "base64" or response.get("type") != "file":
        raise GuardError("Expected plain requirements file")
    raw = base64.b64decode("".join(response["content"].split()), validate=True)
    if len(raw) > 4096 or b"\x00" in raw:
        raise GuardError("Invalid requirements input size/content")
    base = (root / "requirements-dev.in").read_bytes()
    if (root / "requirements-dev.txt").read_bytes() != base:
        raise GuardError("Trusted base direct inputs already differ")
    name, version = validate_change(base, raw, files)
    # A fully generated replacement is intentional: never re-use the updater's
    # Python 3.13 lock, and never execute files fetched from the PR.
    (root / "requirements-dev.in").write_bytes(raw)
    (root / "requirements-dev.txt").write_bytes(raw)
    return {"pr": number, "head_sha": head_sha, "base_sha": base_sha,
            "direct_package": name, "selected_version": version}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    event = os.environ.get("GITHUB_EVENT_NAME")
    if (event == "workflow_dispatch" and os.environ.get("GITHUB_REF") != "refs/heads/main") or (event == "pull_request" and os.environ.get("GITHUB_BASE_REF") != "main") or event not in {"workflow_dispatch", "pull_request"}:
        parser.error("Run only for protected main or PRs targeting main")
    token, repo, base = (os.environ.get(k, "") for k in
                         ("GH_TOKEN", "GITHUB_REPOSITORY", "TARGET_BASE_SHA"))
    if not token:
        parser.error("Missing read-only GITHUB_TOKEN")
    try:
        result = prepare(repo=repo, number=args.pr, head_sha=args.expected_head,
                         base_sha=base, token=token, root=args.root)
    except (GuardError, OSError, UnicodeError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print("DEPENDABOT_REGEN_INPUT_OK " + json.dumps(result, sort_keys=True))
    path = args.root / "dependabot-lock-manifest.json"
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
