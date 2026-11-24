"""The 2026-11-24 governance sheet is a successor proposal, never an edit."""
from __future__ import annotations

import importlib.util
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "governance" / "build_combined_review_sheet.py"
SHEET = ROOT / "docs" / "governance" / "combined-review-2026-11-24.json"
WORKSPACE = ROOT / "docs" / "governance" / "workspace-continuity-2026-11-22.json"


def _generator():
    spec = importlib.util.spec_from_file_location("combined_review_sheet", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_combined_review_sheet_is_exact_and_only_supersedes_the_named_entries():
    gen = _generator()
    prior = json.loads(WORKSPACE.read_text(encoding="utf-8"))
    workflow = next(row for row in prior["items"] if row["key"] == "software-change")
    raw = {"entries": [
        {"id": gen.WORKFLOW, "def_name": "workflow",
         "body": json.dumps(workflow["body"])},
        {"id": gen.RULE, "def_name": "rule", "body": json.dumps({"text": "old"})},
    ]}
    built = gen.build(raw)
    assert built == json.loads(SHEET.read_text(encoding="utf-8"))

    items = {row["key"]: row for row in built["items"]}
    body = items["software-change"]["body"]
    assert gen.OLD_DISCIPLINE not in json.dumps(body)
    assert items["coordinated-work"]["body"]["text"] == gen.RULE_TEXT
    assert [row["key"] for row in body["activities"]] == [
        "orient-recall", "record-request", "plan", "plan-review", "implement",
        "integrate", "review", "correct", "verify", "record-outcome-and-learning",
    ]
    assert {row["replaces"] for row in built["items"]} == {gen.WORKFLOW, gen.RULE}

    plans = built["application_plan"]
    assert {row["supersedes"] for row in plans["TEST"]["establish"]} == {
        gen.WORKFLOW, gen.RULE}
    assert {row["supersedes"] for row in plans["DAY-TO-DAY"]["establish"]} == {
        gen.OLD_DISCIPLINE, gen.DAY_WORKFLOW, gen.RULE}
    assert plans["DAY-TO-DAY"]["untouched"] == [
        {"entry": gen.READING_LOGS, "title": "Reading logs", "assert": "remains standing"}
    ]
    assert gen.READING_LOGS not in {
        row["supersedes"] for plan in plans.values() if isinstance(plan, dict)
        for row in plan.get("establish", ())
    }

