#!/usr/bin/env python3
"""Render independently collected JSON evidence as a readable Markdown report."""

import argparse
import json
from pathlib import Path


def cell(value):
    return str(value if value is not None else "—").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def code(value):
    # Four-backtick fences cannot be closed by ordinary triple-backtick content.
    rendered = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
    return "````json\n" + rendered.replace("````", "\\u0060\\u0060\\u0060\\u0060") + "\n````"


def render_report(report):
    if report.get("schema_version") != 1 or not isinstance(report.get("controls"), list):
        raise ValueError("Expected a HardenOps schema_version 1 report")
    facts = report["facts"]
    summary = report["summary"]
    lines = ["# HardenOps verification report", "", "- Host: " + cell(report["host"]),
             "- Distribution: %s %s" % (cell(facts.get("distribution")), cell(facts.get("distribution_version"))),
             "- Kernel: " + cell(facts.get("kernel")), "- Architecture: " + cell(facts.get("architecture")),
             "- Profile: " + cell(report["profile"]), "- Collected at: " + cell(report["generated_at"]), "",
             "- Catalogue SHA-256: " + cell(report.get("catalogue", {}).get("sha256", "not supplied")), "",
             "This report covers selected ANSSI-BP-028 controls. It is not certification, regulatory compliance, or a formal security audit.", "",
             "## Counts", "", "| Measure | Count |", "| --- | ---: |"]
    labels = {"total_controls": "Catalogue entries", "applicable_controls": "Selected applicable entries (including manual and unsupported)",
              "automated_controls": "Selected applicable automated entries", "verified_controls": "Entries independently evaluated as PASS or FAIL",
              "reboot_required_controls": "Selected applicable entries marked reboot required", "changes_required": "Automated entries requiring change"}
    for field, label in labels.items():
        lines.append("| %s | %s |" % (label, summary[field]))
    for result, count in summary["results"].items():
        lines.append("| %s | %s |" % (result, count))
    lines.extend(["", "Counts describe this catalogue and selected profile, not coverage of the entire ANSSI guide.", "",
                  "## Control results", "", "| Control | Source | Level | Enforcement | Result |", "| --- | --- | --- | --- | --- |"])
    for control in report["controls"]:
        source = control["source"]
        citation = "%s %s, p. %s" % (source["document"], source["recommendation"], source.get("page", "unspecified"))
        lines.append("| %s | %s | %s | %s | %s |" % tuple(cell(item) for item in
                     (control["id"], citation, control["level"], control["enforcement"], control["result"])))
    lines.extend(["", "## Evidence", "", cell(report.get("verification_scope", "Independent host inspection")), ""])
    for control in report["controls"]:
        lines.extend(["### " + cell(control["id"]), "", cell(control["title"]), "",
                      "**%s** — %s" % (cell(control["result"]), cell(control["reason"])), "",
                      "Expected:", "", code(control.get("expected")), "", "Observed:", "", code(control.get("observed")), ""])
        if "desired" in control:
            lines.extend(["Next safe target (preserves explicitly accepted stronger state): " + cell(control["desired"]), ""])
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Path to report.json")
    parser.add_argument("--output", type=Path, help="Defaults to report.md next to the JSON input")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        rendered = render_report(report)
        destination = args.output or args.report.with_suffix(".md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, "Cannot generate report: %s\n" % exc)
    print(str(destination))


if __name__ == "__main__":
    main()
