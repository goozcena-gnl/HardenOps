"""Manage one Vagrant lab and derive a private Ansible inventory from SSH metadata."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / ".lab"
STATE = LAB / "state.json"
DISTROS = ("ubuntu2404", "rocky9")
PROVIDERS = ("libvirt", "virtualbox")


def parse_ssh_config(text: str) -> dict[str, str]:
    """Accept Vagrant's single-host output, never its host-key disabling options."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        tokens = shlex.split(line)
        if not tokens:
            continue
        key = tokens[0].lower()
        if key in {"hostname", "user", "port", "identityfile"}:
            if len(tokens) != 2 or key in values:
                raise ValueError(f"Ambiguous Vagrant SSH configuration: {key}")
            values[key] = tokens[1]
    if set(values) != {"hostname", "user", "port", "identityfile"}:
        raise ValueError("Incomplete Vagrant SSH configuration; is the VM running?")
    if not 1 <= int(values["port"]) <= 65535:
        raise ValueError("Invalid SSH port")
    return values


def make_inventory(ssh: dict[str, str], lab: Path = LAB) -> dict:
    options = [
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"UserKnownHostsFile={lab / 'known_hosts'}",
    ]
    return {"all": {"children": {"hardenops": {"hosts": {"lab": {
        "ansible_host": ssh["hostname"],
        "ansible_port": int(ssh["port"]),
        "ansible_user": ssh["user"],
        "ansible_ssh_private_key_file": ssh["identityfile"],
        "ansible_ssh_common_args": shlex.join(options),
    }}}}}}


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(path)


def run_vagrant(state: dict, *arguments: str, capture: bool = False) -> str:
    environment = os.environ.copy()
    environment["HARDENOPS_DISTRO"] = state["distro"]
    environment["VAGRANT_DEFAULT_PROVIDER"] = state["provider"]
    result = subprocess.run(
        ["vagrant", *arguments], cwd=ROOT, env=environment, check=True,
        text=True, stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout or ""


def choose_state(existing: dict | None, distro: str | None, provider: str | None) -> dict:
    selected = {"distro": distro or (existing or {}).get("distro", "ubuntu2404"),
                "provider": provider or (existing or {}).get("provider", "libvirt")}
    if selected["distro"] not in DISTROS or selected["provider"] not in PROVIDERS:
        raise ValueError("Unsupported lab distribution or provider")
    if existing and existing != selected:
        raise ValueError("Destroy the current lab before changing DISTRO or PROVIDER")
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deploy", "inventory", "status", "destroy"))
    parser.add_argument("--distro", choices=DISTROS)
    parser.add_argument("--provider", choices=PROVIDERS)
    args = parser.parse_args(argv)
    try:
        existing = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else None
        state = choose_state(existing, args.distro, args.provider)
        if args.action == "deploy":
            # Persist before boot so a failed deployment remains recoverable by destroy.
            save_json(STATE, state)
            run_vagrant(state, "up", "--provider", state["provider"])
        elif not existing:
            raise ValueError("No remembered lab; run make deploy DISTRO=ubuntu2404 first")
        if args.action in ("deploy", "inventory"):
            ssh = parse_ssh_config(run_vagrant(state, "ssh-config", capture=True))
            save_json(LAB / "inventory.yml", make_inventory(ssh))
            print("Inventory refreshed in .lab/inventory.yml")
        elif args.action == "status":
            print(f"Lab: {state['distro']} / {state['provider']}", flush=True)
            run_vagrant(state, "status")
        elif args.action == "destroy":
            run_vagrant(state, "destroy", "--force")
            # Only our named metadata is removed, after successful VM destruction.
            for name in ("state.json", "inventory.yml", "known_hosts", "known_hosts.old"):
                (LAB / name).unlink(missing_ok=True)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Lab error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
