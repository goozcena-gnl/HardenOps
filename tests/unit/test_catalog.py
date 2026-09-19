"""Regression tests for source mapping and unsafe catalogue/profile declarations."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("catalog_validator", ROOT / "tools/validate_catalog.py")
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)
CATALOG = yaml.safe_load((ROOT / "controls/anssi_bp_028.yml").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "controls/schema.json").read_text(encoding="utf-8"))


@pytest.fixture
def catalog():
    return copy.deepcopy(CATALOG)


def test_source_reviewed_catalog_is_valid(catalog):
    assert validator.validate_catalog(catalog, SCHEMA) == []


def test_duplicate_ids_are_rejected(catalog):
    catalog["controls"].append(copy.deepcopy(catalog["controls"][0]))
    assert any("Duplicate control" in error for error in validator.validate_catalog(catalog, SCHEMA))


@pytest.mark.parametrize("field,value", [
    ("level", "unknown"), ("level", "minimal"),
    ("source", {"document": "ANSSI-BP-028", "page": 19}),
    ("enforcement", {"status": "PASS"}),
    ("applicability", {"os_families": ["Suse"]}),
    ("verification", {"type": "manual"}),
])
def test_invalid_declarations_are_rejected(catalog, field, value):
    catalog["controls"][0][field] = value
    assert validator.validate_catalog(catalog, SCHEMA)


def test_baseline_must_be_an_accepted_value(catalog):
    catalog["controls"][0]["verification"]["accepted_values"] = ["2"]
    assert any("expected value" in error for error in validator.validate_catalog(catalog, SCHEMA))


def test_accepted_value_cannot_be_marked_for_reduction(catalog):
    catalog["controls"][0]["verification"]["remediable_values"].append("1")
    assert any("disjoint" in error for error in validator.validate_catalog(catalog, SCHEMA))


def test_numeric_ranges_cannot_replace_control_specific_semantics(catalog):
    verification = catalog["controls"][0]["verification"]
    del verification["remediable_values"]
    verification["remediable_range"] = [1, 511]
    assert any("reserved for kernel.sysrq" in error for error in validator.validate_catalog(catalog, SCHEMA))


@pytest.mark.parametrize("recommendation,gate", [("R12", "non_router"), ("R13", "ipv6_unused")])
def test_network_safety_gates_are_required(catalog, recommendation, gate):
    control = next(item for item in catalog["controls"] if item["source"]["recommendation"] == recommendation)
    del control["applicability"][gate]
    assert any(gate in error for error in validator.validate_catalog(catalog, SCHEMA))


def test_missing_reference_cannot_silently_be_marked_implemented(catalog):
    control = next(item for item in catalog["controls"] if item["source"]["recommendation"] == "R68")
    control["enforcement"]["status"] = "MANUAL"
    assert any("missing password-storage reference" in error for error in validator.validate_catalog(catalog, SCHEMA))


def test_missing_implementation_is_rejected(catalog, tmp_path):
    assert any("implementation is missing" in error for error in validator.validate_catalog(catalog, SCHEMA, tmp_path))


def test_profile_cannot_leak_intermediary_controls_into_minimal(catalog):
    profiles = {name: {"level": name, "implemented": name in {"minimal", "intermediary"}}
                for name in validator.LEVELS}
    profiles["minimal"]["controls"] = [item["id"] for item in catalog["controls"]]
    assert any("exceeds profile level" in error for error in validator.validate_profiles(profiles, catalog))


def test_future_profile_cannot_claim_support(catalog):
    profiles = {name: {"level": name, "implemented": name in {"minimal", "intermediary"}}
                for name in validator.LEVELS}
    profiles["enhanced"]["implemented"] = True
    assert any("enhanced: implemented" in error for error in validator.validate_profiles(profiles, catalog))


def test_current_profiles_are_cumulative(catalog):
    profiles = {name: {"level": name, "implemented": name in {"minimal", "intermediary"}}
                for name in validator.LEVELS}
    for name in ("minimal", "intermediary"):
        profiles[name]["controls"] = [item["id"] for item in catalog["controls"]
                                     if validator.LEVELS[item["level"]] <= validator.LEVELS[name]]
    for name, profile in profiles.items():
        profile["includes_levels"] = ([item for item in validator.LEVELS
                                       if validator.LEVELS[item] <= validator.LEVELS[name]]
                                      if profile["implemented"] else [])
    assert validator.validate_profiles(profiles, catalog) == []


def test_profile_level_inheritance_must_be_cumulative(catalog):
    profiles = {name: {"level": name, "implemented": name in {"minimal", "intermediary"},
                       "includes_levels": []} for name in validator.LEVELS}
    profiles["minimal"]["includes_levels"] = ["minimal"]
    profiles["intermediary"]["includes_levels"] = ["intermediary"]
    assert any("intermediary: includes_levels" in error
               for error in validator.validate_profiles(profiles, catalog))
