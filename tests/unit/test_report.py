"""Reports retain source traceability and avoid misleading aggregate scores."""

import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[2] / "tools" / "generate_report.py"
SPEC = importlib.util.spec_from_file_location("generate_report", MODULE)
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def sample_report():
    return {"schema_version": 1, "host": "lab", "profile": "intermediary", "generated_at": "2026-09-19T00:00:00Z",
            "facts": {"distribution": "Ubuntu", "distribution_version": "24.04", "kernel": "6.8", "architecture": "x86_64"},
            "summary": {"total_controls": 1, "applicable_controls": 1, "automated_controls": 1,
                        "verified_controls": 1, "reboot_required_controls": 0, "changes_required": 0, "results": {"PASS": 1}},
            "controls": [{"id": "bp028_r9_test", "source": {"document": "ANSSI-BP-028", "recommendation": "R9", "page": 20},
                          "level": "intermediary", "enforcement": "AUTOMATED", "result": "PASS", "title": "Example title",
                          "reason": "Runtime matched", "expected": "1", "observed": "1", "desired": "1"}]}


def test_markdown_includes_traceability_and_evidence():
    markdown = renderer.render_report(sample_report())
    assert "ANSSI-BP-028 R9, p. 20" in markdown
    assert "bp028_r9_test" in markdown
    assert "Observed:" in markdown
    assert "**PASS**" in markdown
    assert "certification" in markdown
    assert "%" not in markdown


def test_table_cells_cannot_inject_extra_columns():
    report = sample_report()
    report["controls"][0]["id"] = "control|extra\nrow"
    assert "control\\|extra row" in renderer.render_report(report)


def test_unknown_report_version_rejected():
    report = sample_report()
    report["schema_version"] = 2
    with pytest.raises(ValueError, match="schema_version"):
        renderer.render_report(report)


def test_evidence_cannot_terminate_code_fence():
    report = sample_report()
    report["controls"][0]["observed"] = "````\nmisleading text"
    assert "\\u0060\\u0060\\u0060\\u0060" in renderer.render_report(report)
