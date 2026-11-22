"""Build docs/governance/workspace-continuity-2026-11-22.json: the proposed successors of the
standing Development Discipline and Software change Workflow, made from their EXACT current
bodies (fetched from the Brain they stand in) by the replacements below. Every replaced passage
must occur exactly once, so nothing else in either record changes.

    python tools/governance/build_workspace_continuity_sheet.py DISCIPLINE.json WORKFLOW.json

Each argument is the `GET /api/entries/<id>` answer for the standing record.
"""
import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "governance" / "workspace-continuity-2026-11-22.json"


def swap(text, old, new, where):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f"{where}: expected the passage once, found {n}: {old[:80]!r}")
    return text.replace(old, new)


# ---------------------------------------------------------------- Discipline
D_TEXT = [
    ("Work in a workspace of your own: one clone or branch per piece of work, named for the work "
     "(fix-sources), never for the agent, and never the serving checkout or the main clone. Look "
     "before you create one: list what exists and reuse a clean one that fits.",
     "Work in the checkout your hand-off names. A part has one checkout and one branch for its "
     "whole life: its corrections, continuations and resumed runs work there on that branch, "
     "whichever run, runtime or model carries them. Claim it for your run (claim_resource, a path, "
     "exclusive) before changing anything, and return its path and branch with your result. Make "
     "a checkout only when your hand-off names none: one per part, named for the work "
     "(fix-sources), never for the agent or the run, inside the workspace your run was given, "
     "never the serving checkout or the main clone; look first and reuse a clean one of the same "
     "work that fits. A checkout another live run holds, or one with changes you did not make, is "
     "not yours to work in: stop and say so rather than cloning around it.\n\n"
     "Reviewing, work in the review checkout your hand-off names, never the author's, and change "
     "nothing in the author's checkout. Fetch the exact commit under review from the author's "
     "checkout or branch, check it out detached, and confirm `git rev-parse HEAD` is that commit "
     "and `git status` shows nothing left from an earlier round before you build or test. When the "
     "review needs a clean build, build into a target directory of its own inside the review "
     "checkout. Return the verdict's evidence with the verdict (return_artifact or the Turn).\n\n"
     "Builds and dependencies stay in the checkout that uses them: its own Rust target directory "
     "and its own npm install (the download caches are shared). Never point a checkout's target "
     "directory or build directory at a shared one: Cargo would reuse another checkout's build of "
     "the same crate and test the wrong code. Never link one checkout's node_modules to another's. "
     "Reusing the checkout across rounds is what keeps builds incremental."),
    ("Commit on your own branch with a plain message that says what changed. Do not push, merge "
     "into a shared branch, delete branches or remove workspaces unless the request gives you that "
     "part of the work.",
     "Commit on your part's branch with a plain message that says what changed; a commit is not "
     "acceptance. Do not merge into a shared branch, push to a shared or protected branch (main, "
     "test/integration, a release branch), deploy, delete branches or remove a checkout unless the "
     "request gives you that part of the work. You may delete what you generated in a checkout you "
     "hold and can regenerate -- build output, test temp files, fixtures you made -- once anything "
     "worth keeping from it is recorded; never another run's files, uncommitted work, unrecorded "
     "evidence, a checkout you do not hold, or anything another checkout links to. Retiring "
     "checkouts is the carrier's."),
]
D_TOOL_USE = [
    ("git switch -c <work>, or a plain clone beside the repository (C:\\Work\\Mentis-wt\\<name>, "
     "C:\\Work\\MARS-wt\\<name>);",
     "the checkout your hand-off names, or when it names none git switch -c <work> in a plain "
     "clone inside your workspace; reviewing, git fetch <author's checkout or remote> <branch> then "
     "git checkout --detach <commit> in your review checkout, and git rev-parse HEAD to confirm it;"),
]
D_VERIFICATION = [
    ("git status in the workspace is clean;",
     "git status in the checkout is clean; the Turn names the checkout and branch;"),
]

# ------------------------------------------------------------------ Workflow
W_TEXT = [
    ("One carrier coordinates one objective:",
     "WORKSPACES CARRY ON. Each part has one checkout and one branch, named in its hand-off and "
     "given as `repository` -- a directory named this way must already exist, so the carrier "
     "prepares the checkout (or delegates preparing it) before naming it; its corrections, continuations and resumed runs are delegated to the "
     "same checkout and branch, whichever run, runtime or model carries them. A second checkout for "
     "a part is made only for concurrent work on it that cannot share one. Each workstream has one "
     "review checkout, separate from every author's checkout, reused round after round "
     "(`review_of` with `repository`); concurrent reviews get one each. When the carrier cannot "
     "tell that a checkout is safe to reuse -- a live lease, changes nobody accounts for -- it "
     "settles that before delegating rather than letting a new clone be made. A HAND-OFF THAT "
     "TIMES OUT may still have happened: the carrier reads the record for it (history, "
     "work_overview) before anything else, retries only with the same operation key and the same "
     "repository after waiting, and never starts a second agent for work already running; a "
     "hand-off it still cannot confirm is reported as unconfirmed, with its key, not as work not "
     "done. One carrier coordinates one objective:"),
]
W_ACT = {
    "implement": [
        ("Each works on its own branch or clone, started through MARS or by hand, and each returns "
         "to the carrier.",
         "Each works in its part's checkout on its part's branch, named as `repository`, started "
         "through MARS or by hand; it claims the checkout for its run and returns to the carrier "
         "with the checkout and branch."),
        ("goal; workspace and branch;",
         "goal; the part's checkout and branch (the same ones its earlier rounds used);"),
    ],
    "review": [
        ("Run on a runtime other than the author's, with review_of naming the request being "
         "reviewed.",
         "Run on a runtime other than the author's, with review_of naming the request being "
         "reviewed and `repository` the workstream's review checkout, never the author's; the "
         "reviewer checks out the exact commit under review there and confirms it. For a change a "
         "person uses through an interface, review the real mounted product path -- navigation, "
         "state, permissions and the backend it calls -- before spending rounds on synthetic "
         "harnesses: they check focused regressions, and their passing is not evidence that the "
         "interface works."),
        ("Mark each finding blocking or not.",
         "Mark each finding blocking, not blocking, or out of scope (outside the authorized "
         "request: separate work needing its own authorization). A blocking finding names the "
         "requirement it violates and how to reproduce it."),
    ],
    "correct": [
        ("A correction is bounded to its findings and shown by the targeted tests that check them; "
         "it never reopens planning.",
         "Before correcting, the author names the invariant each finding breaks and checks the "
         "other paths that could break it the same way, and the correction covers them, in the "
         "part's own checkout and branch. A correction is bounded to its findings and shown by the "
         "targeted tests that check them; it never reopens planning. A re-review that finds another "
         "path of the same invariant sends it back with the invariant named. A review is not "
         "dispatched again when nothing it would check has changed."),
        ("Findings that are not blocking are recorded as discovered work, not corrected in this "
         "request,",
         "Findings that are not blocking, and out-of-scope findings, are recorded as discovered "
         "work, not corrected in this request -- the carrier does not turn one into a correction "
         "unless the owner widens the request or another governing requirement makes it blocking, "
         "and does not add acceptance criteria after building began --"),
    ],
    "record-outcome-and-learning": [
        ("remove merged workspaces and branches with git branch -d.",
         "remove merged workspaces and branches with git branch -d. WORKSPACES ARE RETIRED WHEN "
         "THEY HAVE SERVED THEIR PURPOSE, not only when the work ends: before a checkout is retired "
         "its branch is pushed to a provisional branch (wip/<work>/<part>) -- preservation, not "
         "acceptance, merge or deployment; nothing goes to main, test/integration or a release "
         "branch without the owner's authority, and reviewer experiments are not pushed (their "
         "evidence is recorded instead). A superseded checkout or a finished review checkout is "
         "retired once its commits are on a remote branch and its evidence is recorded, and only "
         "when no live lease holds it, nothing in it is uncommitted, and no other checkout links "
         "into it; anything else is kept and reported."),
    ],
}
W_DONE_WHEN = [
    ("and its known non-blocking issues.",
     "and its known non-blocking issues, and which checkouts it leaves and why."),
]


def main(dpath, wpath):
    d = json.load(open(dpath, encoding="utf-8"))
    w = json.load(open(wpath, encoding="utf-8"))
    db, wb = copy.deepcopy(d["body"]), copy.deepcopy(w["body"])
    for old, new in D_TEXT:
        db["text"] = swap(db["text"], old, new, "discipline.text")
    for old, new in D_TOOL_USE:
        db["tool_use"] = swap(db["tool_use"], old, new, "discipline.tool_use")
    for old, new in D_VERIFICATION:
        db["verification"] = swap(db["verification"], old, new, "discipline.verification")
    for old, new in W_TEXT:
        wb["text"] = swap(wb["text"], old, new, "workflow.text")
    for act in wb["activities"]:
        for old, new in W_ACT.get(act["key"], ()):
            act["what"] = swap(act["what"], old, new, f"workflow.{act['key']}")
    hit = {a["key"] for a in wb["activities"]}
    missing = set(W_ACT) - hit
    if missing:
        raise SystemExit(f"activities not found: {missing}")
    for old, new in W_DONE_WHEN:
        wb["done_when"] = swap(wb["done_when"], old, new, "workflow.done_when")
    sheet = {
        "_about": ("PROPOSAL for the owner's approval, not established. Workspace continuity, "
                   "review proportionality and handoff recovery (owner request 2026-11-22, after "
                   "the operational audit: ~445 executions, 335 workspace folders / 62.4 GB, ~25 "
                   "handoff timeouts, non-blocking findings turned into correction rounds). Each "
                   "item supersedes the standing entry it names and keeps its placement. "
                   "Establishing these words is the owner's act (tools/establish_governance.py "
                   "--decisions docs/governance/workspace-continuity-2026-11-22.json, dry run "
                   "first). Pairs with the delegate change on branch workspace-continuity: a "
                   "review may name its own workspace with review_of, and never works in its "
                   "author's checkout."),
        "ruling": "Proposed 2026-11-22; not established.",
        "approved": "not yet: establishing these words is the owner's act",
        "occasion": "Workspace continuity and review proportionality, 2026-11-22",
        "items": [
            {"key": "cli-mars-development", "title": "CLI and MARS development (Discipline)",
             "kind": "discipline", "body": db, "replaces": d["id"]},
            {"key": "software-change", "title": "Software change (Workflow)",
             "kind": "workflow", "body": wb, "replaces": w["id"]},
        ],
    }
    OUT.write_text(json.dumps(sheet, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
