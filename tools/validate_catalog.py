#!/usr/bin/env python3
"""Validate the catalogue structure, reviewed source mapping and profile boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
LEVELS = {"minimal": 0, "intermediary": 1, "enhanced": 2, "high": 3}
# These mappings were checked against BP-028 v2, main text and pp. 68-70.
# An addition requires a source review, not guessing from the recommendation ID.
REVIEWED_LEVELS = {
    "R9": "intermediary", "R11": "intermediary", "R12": "intermediary",
    "R13": "intermediary", "R14": "intermediary", "R30": "minimal",
    "R32": "intermediary", "R33": "intermediary", "R34": "intermediary",
    "R35": "intermediary", "R50": "intermediary", "R51": "enhanced",
    "R52": "intermediary", "R53": "minimal", "R54": "minimal",
    "R55": "intermediary", "R56": "minimal", "R57": "enhanced",
    "R58": "minimal", "R59": "minimal", "R60": "enhanced",
    "R61": "minimal", "R62": "minimal", "R63": "intermediary",
    "R68": "minimal", "R79": "intermediary", "R80": "minimal",
}


def read_yaml(path: Path) -> Any:
    """Read UTF-8 YAML without constructing arbitrary Python objects."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_catalog(catalog: Any, schema: dict[str, Any], root: Path | None = None) -> list[str]:
    """Return actionable validation errors; never mutate catalogue inputs."""
    errors = []
    validator = jsonschema.Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(catalog), key=lambda item: str(list(item.path))):
        location = ".".join(str(part) for part in error.path) or "catalogue"
        errors.append(f"{location}: {error.message}")
    if errors:
        return errors

    seen = set()
    for control in catalog["controls"]:
        identifier = control["id"]
        if identifier in seen:
            errors.append(f"Duplicate control ID: {identifier}")
        seen.add(identifier)
        source = control["source"]["recommendation"]
        if source not in REVIEWED_LEVELS:
            errors.append(f"{identifier}: recommendation {source} needs a verified source review")
        elif control["level"] != REVIEWED_LEVELS[source]:
            errors.append(f"{identifier}: {source} level must be {REVIEWED_LEVELS[source]}")
        if not identifier.startswith(f"bp028_{source.lower()}_"):
            errors.append(f"{identifier}: ID does not match source recommendation {source}")
        status = control["enforcement"]["status"]
        verification = control["verification"]
        if status in {"AUTOMATED", "VERIFIED"} and verification["type"] not in {"sysctl", "file"}:
            errors.append(f"{identifier}: {status} needs an implemented independent state verifier")
        if status == "AUTOMATED":
            implementation = control["enforcement"].get("implementation")
            if not implementation:
                errors.append(f"{identifier}: AUTOMATED requires an implementation path")
            elif root is not None:
                target = (root / implementation).resolve()
                if not target.is_relative_to(root.resolve()) or not target.is_file():
                    errors.append(f"{identifier}: implementation is missing or outside the repository")
        if status == "AUDIT_ONLY" and verification["type"] != "audit":
            errors.append(f"{identifier}: AUDIT_ONLY must collect audit evidence")
        if verification["type"] == "sysctl" and verification["expected"] != verification["accepted_values"][0]:
            errors.append(f"{identifier}: expected value must be first in accepted_values")
        if verification["type"] == "sysctl":
            if set(verification["accepted_values"]) & set(verification.get("remediable_values", [])):
                errors.append(f"{identifier}: accepted and remediable values must be disjoint")
            if "remediable_range" in verification and (
                verification["key"] != "kernel.sysrq" or verification["remediable_range"] != [1, 511]
            ):
                errors.append(f"{identifier}: remediable_range is reserved for kernel.sysrq [1, 511]")
        if source == "R12" and control["applicability"].get("non_router") is not True:
            errors.append(f"{identifier}: R12 needs an explicit non_router gate")
        if source == "R13" and control["applicability"].get("ipv6_unused") is not True:
            errors.append(f"{identifier}: R13 needs an explicit ipv6_unused gate")
        if source == "R68" and status != "OUT_OF_SCOPE_REFERENCE_REQUIRED":
            errors.append(f"{identifier}: R68 requires its missing password-storage reference")
    return errors


def validate_profiles(profiles: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    """Validate operational support and any explicit control selections.

    Profiles may use cumulative level selection or explicit ``controls`` IDs.
    Explicit selections must include all catalogue controls at or below their level.
    """
    errors = []
    known = {control["id"]: control for control in catalog["controls"]}
    for name in LEVELS:
        profile = profiles.get(name)
        if not isinstance(profile, dict):
            errors.append(f"Profile {name}: missing or not a mapping")
            continue
        level = profile.get("level", profile.get("name", name))
        if level != name:
            errors.append(f"Profile {name}: level must be {name}")
        supported = name in {"minimal", "intermediary"}
        if profile.get("implemented") is not supported:
            errors.append(f"Profile {name}: implemented must be {supported}")
        expected_levels = [item for item in LEVELS if LEVELS[item] <= LEVELS[name]] if supported else []
        if profile.get("includes_levels") != expected_levels:
            errors.append(f"Profile {name}: includes_levels must be {expected_levels}")
        selected = profile.get("controls")
        if selected is None:
            continue
        if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
            errors.append(f"Profile {name}: controls must be a list of IDs")
            continue
        if not supported and selected:
            errors.append(f"Profile {name}: future profiles must not declare implemented controls")
        if len(selected) != len(set(selected)):
            errors.append(f"Profile {name}: duplicate control IDs")
        for identifier in selected:
            if identifier not in known:
                errors.append(f"Profile {name}: unknown control {identifier}")
            elif LEVELS[known[identifier]["level"]] > LEVELS[name]:
                errors.append(f"Profile {name}: {identifier} exceeds profile level")
        if supported:
            expected = {identifier for identifier, control in known.items()
                        if LEVELS[control["level"]] <= LEVELS[name]}
            if set(selected) != expected:
                errors.append(f"Profile {name}: explicit controls must match cumulative catalogue selection")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        catalog = read_yaml(root / "controls/anssi_bp_028.yml")
        schema = json.loads((root / "controls/schema.json").read_text(encoding="utf-8"))
        errors = validate_catalog(catalog, schema, root=root)
        if not errors:
            profiles = {name: read_yaml(root / f"profiles/{name}.yml") for name in LEVELS}
            errors.extend(validate_profiles(profiles, catalog))
    except (OSError, ValueError, yaml.YAMLError, jsonschema.SchemaError) as error:
        print(f"FAIL: {error}")
        return 1
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: {len(catalog['controls'])} controls and four profile definitions validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
