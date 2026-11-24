"""Build the proposed combined-review governance successors from TEST's raw export.

Nothing this script writes is established governance.  Its input is the JSON export
that contains the current TEST entries (``test-governance-raw.json``), and its output
is the reviewable sheet beside the other governance proposals.

    python tools/governance/build_combined_review_sheet.py test-governance-raw.json

Every changed passage must occur exactly once.  Everything else in the current
Software change Workflow is retained byte-for-byte as a JSON value.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "governance" / "combined-review-2026-11-24.json"

WORKFLOW = "ent-a0db8f1db0f4"
RULE = "ent-8dc9dc46cac9"
SUCCESSOR_DISCIPLINE = "ent-ce173e5672db"
OLD_DISCIPLINE = "ent-80392167cca0"
DAY_WORKFLOW = "ent-5b42a95dbda1"
READING_LOGS = "ent-934f286ed804"

RULE_TEXT = (
    "How coordinated work is organised. The coordinator sets the scope, shared "
    "interfaces, contracts and integration approach first. Builders implement "
    "independent parts in parallel where practical, each on its own standing part "
    "branch, and self-test what they change. Compatible finished parts are integrated "
    "into one isolated development candidate, its integrated tests are run, and where "
    "people use the change its real rendered interface is inspected early. Integration "
    "assembles and preserves the work; it is not acceptance, release authorization or "
    "deployment authorization. Independent review follows risk and complexity: routine, "
    "localised changes need none; when the risk or complexity warrants it, one independent "
    "reviewer or tester evaluates the combined candidate against the request, including "
    "cross-component seams and the rendered product path, and returns one consolidated "
    "findings set. Individual parts are not reviewed separately before integration; an "
    "earlier specialist or contract review is used only where security, authority, "
    "irreversible changes, foundational interfaces or dependency risks warrant it. "
    "Blocking findings go to the relevant builders or the integrator, in parallel where "
    "practical; nonblocking and out-of-scope findings become follow-up work, not correction "
    "rounds. Corrections are integrated and receive focused verification of what they change "
    "and what that touches, not a repeat of the whole review; a genuine remaining blocking "
    "defect is still fixed, and no review count is a reason to accept defective work. "
    "Accepted work is integrated into the cumulative TEST integration branch for the owner's "
    "evaluation. Nothing is retried automatically: a failed part is reassigned or finished "
    "by the integrator, and the report says which."
)


def swap(text: str, old: str, new: str, where: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(
            f"{where}: expected the passage once, found {count}: {old[:100]!r}"
        )
    return text.replace(old, new)


def entry(export: dict, wanted: str) -> dict:
    found = [row for row in export.get("entries", ()) if row.get("id") == wanted]
    if len(found) != 1:
        raise SystemExit(f"expected one {wanted} in export, found {len(found)}")
    row = copy.deepcopy(found[0])
    if isinstance(row.get("body"), str):
        row["body"] = json.loads(row["body"])
    return row


def activity(body: dict, key: str) -> dict:
    found = [row for row in body["activities"] if row.get("key") == key]
    if len(found) != 1:
        raise SystemExit(f"expected one Workflow activity {key!r}, found {len(found)}")
    return found[0]


def build(raw: dict) -> dict:
    current_workflow = entry(raw, WORKFLOW)
    current_rule = entry(raw, RULE)
    wb = copy.deepcopy(current_workflow["body"])

    # The successor Discipline already stands in TEST.  No activity may keep
    # pointing at the Discipline it superseded.
    for row in wb["activities"]:
        if "disciplines" in row:
            row["disciplines"] = [
                SUCCESSOR_DISCIPLINE if ref == OLD_DISCIPLINE else ref
                for ref in row["disciplines"]
            ]

    wb["text"] = swap(
        wb["text"],
        "Orient and recall what applies, record the request, plan the parts, build "
        "independent parts in parallel on branches of their own, review what warrants it, "
        "correct what review found, integrate with git merge, run the targeted tests, commit "
        "and push, then record the outcome with what remains and, separately, any lesson.",
        "Orient and recall what applies, record the request, plan the parts, build independent "
        "parts in parallel on their standing branches and have each Builder self-test its work, "
        "integrate the finished compatible parts into one isolated development candidate, run "
        "the integrated checks and, where people use the change, inspect the real rendered "
        "interface early, obtain one independent combined-candidate review when risk or "
        "complexity warrants it (routine localised changes need none), send its blocking "
        "findings to the relevant Builders or integrator in parallel where practical, correct "
        "and integrate them, perform focused verification of the corrected candidate, then "
        "integrate accepted work into cumulative TEST for the owner's evaluation and record the "
        "outcome with what remains and, separately, any lesson.",
        "workflow.text process sentence",
    )
    wb["text"] = swap(
        wb["text"],
        "a hand-off it still cannot confirm is reported as unconfirmed, with its key, not as "
        "work not done.",
        "a hand-off it still cannot confirm is reported as unconfirmed, with its key, not as "
        "work not done. An authorized hand-off that fails before it is recorded must be retried "
        "once with the same operation key or reported as a failed hand-off with the remaining "
        "work named; it is never reported as done or as a deliberate stop.",
        "workflow.text handoff",
    )

    plan = activity(wb, "plan")
    plan["what"] = swap(
        plan["what"],
        "For each part give its hand-off (as for implement), its difficulty, the capabilities it "
        "requires, and whether it warrants independent review and why, by the criteria above.",
        "For each part give its hand-off (as for implement), its difficulty and the capabilities "
        "it requires. State whether the combined candidate warrants independent review because "
        "of its risk or complexity; routine localised changes need none. Name an earlier "
        "specialist or contract review only for a security or authority boundary, an irreversible "
        "change, a foundational interface, or a dependency choice whose late discovery would "
        "cause major rework.",
        "workflow.plan.what",
    )
    plan["done_when"] = swap(
        plan["done_when"],
        "and whether each warrants review are written where the workers can read them.",
        "and whether the combined candidate warrants review are written where the workers can "
        "read them; any exceptional earlier specialist or contract review is named.",
        "workflow.plan.done_when",
    )

    plan_review = activity(wb, "plan-review")
    plan_review["what"] = (
        "Skip plan review by default. Use one earlier specialist or contract review only for a "
        "security or authority boundary, an irreversible change, a foundational interface, or a "
        "dependency choice whose late discovery would cause major rework. Its author folds in "
        "one findings set and the carrier checks the revision against those findings. It is not "
        "reviewed again unless the owner changes the requirements or a finding leaves an "
        "architectural decision unresolved."
    )
    plan_review["done_when"] = (
        "Any exceptional earlier specialist or contract review has one verdict and findings, "
        "the accepted findings are folded in and checked by the carrier, or the plan records "
        "that the step is skipped."
    )

    integrate = activity(wb, "integrate")
    integrate["done_when"] = (
        "Every finished compatible part is merged, or is recorded as not merged and why; the "
        "integrated candidate's test commands and counts are recorded, and where people use the "
        "change its real rendered interface has been inspected on the product path."
    )
    integrate["what"] += (
        " Immediately after integration and before independent review, run the integrated "
        "targeted checks for everything changed and the execution-boundary tests when dispatch "
        "or mentis.execution changed. Where people use the change through an interface, inspect "
        "the real mounted product path -- navigation, state, permissions and the backend it "
        "calls -- at this point. Record what fails; a candidate with a blocking failure does not "
        "advance to review."
    )
    integrate["what"] = swap(
        integrate["what"],
        "it is delegated with this activity (then verify), not implement, to one integrator.",
        "it is delegated with this activity (then review when warranted, correct, and verify), "
        "not implement, to one integrator.",
        "workflow.integrate delegated sequence",
    )

    review = activity(wb, "review")
    old_review_opening = (
        "Review the parts or results the plan marked as warranting it, against the request's "
        "requirements and what the plan said shows them done. For a part that changes a UI, the "
        "review includes its rendered result against the reference the request names. A review "
        "after integration checks the seams between parts, not each part again."
    )
    new_review_opening = (
        "When the plan says risk or complexity warrants it, after integration one independent "
        "reviewer or tester reviews the exact combined candidate against the whole request, "
        "including cross-component seams and the rendered real product path where people use the "
        "change, and returns one consolidated findings set. Routine localised changes need no "
        "independent review. Do not repeat each Builder's self-tests as separate acceptance "
        "reviews. A specialist may review an earlier slice only for an exception named in the "
        "plan: a security or authority boundary, an irreversible change, a foundational "
        "interface, or a dependency that could cause major rework."
    )
    review["what"] = swap(
        review["what"], old_review_opening, new_review_opening,
        "workflow.review.what",
    )
    review["what"] = swap(
        review["what"],
        "Parts the plan did not mark go straight to integration.",
        "Individual parts are not reviewed separately before integration except for a named "
        "specialist exception.",
        "workflow.review part routing",
    )
    review["what"] = swap(
        review["what"],
        "In a hands-on iteration, independent review is held only for parts whose defects would "
        "lose data, breach authority or security, or break execution or a shared API; the owner's "
        "hands-on testing reviews the rest.",
        "In a hands-on iteration, the combined candidate receives independent review only when "
        "its risk or complexity warrants it; routine localised changes need none, and the owner's "
        "hands-on evaluation is not split into per-part acceptance reviews.",
        "workflow.review hands-on review",
    )
    review["done_when"] = (
        "When review is warranted, the combined candidate has one independent verdict and one "
        "consolidated findings set, each finding carrying its evidence, severity and owning part "
        "or integration seam; otherwise the plan records why routine localised work needs none."
    )

    correct = activity(wb, "correct")
    correct["done_when"] = (
        "Blocking findings are assigned once to their owning Builders or integrator in parallel "
        "where practical and are fixed or recorded as not fixed and why; nonblocking and "
        "out-of-scope findings are recorded as follow-up work; the corrected integrated candidate "
        "receives focused verification of the corrections and what they touch. A genuine "
        "remaining blocking defect is still fixed; no review count is a reason to accept "
        "defective work."
    )
    correct["what"] = swap(
        correct["what"],
        "The re-review checks the corrections and what they touch, not the whole work again.",
        "Focused verification checks the integrated corrections and what they touch, not the "
        "whole review again; a genuine remaining blocking defect is still fixed, and no review "
        "count is a reason to accept defective work.",
        "workflow.correct.what verification",
    )
    correct["what"] = swap(
        correct["what"],
        "A re-review that finds another path of the same invariant sends it back with the "
        "invariant named. A review is not dispatched again when nothing it would check has "
        "changed.",
        "Focused verification that finds another path of the same invariant sends it back with "
        "the invariant named. Verification is not dispatched again when nothing it would check "
        "has changed.",
        "workflow.correct.what remaining re-review",
    )
    correct["who"]["role"] = (
        "the part's author; focused verification goes to the independent reviewer or tester"
    )

    verify = activity(wb, "verify")
    verify["done_when"] = (
        "The focused verification commands and their counts are recorded, and every correction "
        "and what it touches holds or a genuine remaining blocking defect is named for correction."
    )
    verify["what"] = (
        "After corrections are integrated, perform focused verification of each correction and "
        "what it touches. Do not repeat the whole combined-candidate review or unaffected test "
        "scope. A genuine remaining blocking defect is still fixed; no review count is a reason "
        "to accept defective work. If there were no blocking corrections, retain the integrated "
        "checks and early real-interface inspection already recorded. For a hands-on iteration, "
        "leave the accepted candidate running through the existing preview or test process, "
        "started detached from the run so that it outlives it, and have the carrier open its "
        "address and check that it answers and shows the affected interactions. Launch "
        "instructions are not a preview. Where a preview cannot be left running, say that plainly "
        "and do not claim the deliverable met. For a release, run any additional full regression, "
        "cross-browser or platform checks the release calls for."
    )

    # Integration precedes combined review; correction and focused verification follow it.
    rows = {row["key"]: row for row in wb["activities"]}
    order = [row["key"] for row in wb["activities"]]
    moving = {"integrate", "review", "correct", "verify"}
    first = min(order.index(key) for key in moving)
    wb["activities"] = [row for row in wb["activities"] if row["key"] not in moving]
    for offset, key in enumerate(("integrate", "review", "correct", "verify")):
        wb["activities"].insert(first + offset, rows[key])

    outcome = activity(wb, "record-outcome-and-learning")
    outcome["what"] = swap(
        outcome["what"],
        "A review checkout has no branch of its own: once its verdicts and evidence are recorded "
        "and the commits it reviewed are on a remote branch, it is retired when its workstream "
        "needs no more review.",
        "A review checkout has no branch of its own: once its verdicts and evidence are recorded "
        "and the commits it reviewed are on a remote branch, it is retired when that combined-"
        "candidate review and any focused verification using it are complete.",
        "workflow.retirement",
    )

    if OLD_DISCIPLINE in json.dumps(wb, ensure_ascii=False):
        raise SystemExit(f"superseded Discipline {OLD_DISCIPLINE} remains in Workflow")

    return {
        "_about": (
            "PROPOSAL for the owner's approval, not established anywhere. Combined-candidate "
            "review and visible failed hand-offs (owner-approved development-process correction, "
            "2026-11-24). Each item supersedes the standing TEST entry it names and keeps its "
            "placement. Establishing these words is the owner's act "
            "(tools/establish_governance.py --decisions "
            "docs/governance/combined-review-2026-11-24.json, dry run first). The DAY-TO-DAY "
            "application is later, only after code promotion, and uses the same successor bodies "
            "with the DAY-TO-DAY supersession ids stated in application_plan."
        ),
        "ruling": "Proposed 2026-11-24; not established anywhere.",
        "approved": "wording owner-approved; establishment remains the owner's act",
        "occasion": "Combined-candidate review and unrecorded hand-off reliability, 2026-11-24",
        "application_plan": {
            "TEST": {
                "when": "after approval, by an explicit owner establishment action",
                "establish": [
                    {"key": "software-change", "supersedes": WORKFLOW},
                    {"key": "coordinated-work", "supersedes": RULE},
                ],
                "untouched": [],
            },
            "DAY-TO-DAY": {
                "when": "later, after the supporting code is promoted and verified",
                "establish": [
                    {"key": "cli-mars-development", "source": SUCCESSOR_DISCIPLINE,
                     "supersedes": OLD_DISCIPLINE},
                    {"key": "software-change", "supersedes": DAY_WORKFLOW},
                    {"key": "coordinated-work", "supersedes": RULE},
                ],
                "untouched": [
                    {"entry": READING_LOGS, "title": "Reading logs", "assert": "remains standing"}
                ],
            },
            "constraint": "No new competing Discipline or Workflow is established.",
        },
        "items": [
            {"key": "software-change", "title": "Software change (Workflow)",
             "kind": "workflow", "body": wb, "replaces": current_workflow["id"]},
            {"key": "coordinated-work", "title": "How coordinated work is organised (Rule)",
             "kind": "rule", "body": {"text": RULE_TEXT},
             "replaces": current_rule["id"]},
        ],
    }


def main(path: str) -> None:
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    sheet = build(raw)
    OUT.write_text(json.dumps(sheet, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_combined_review_sheet.py test-governance-raw.json")
    main(sys.argv[1])
