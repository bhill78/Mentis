"""A run that returns with uncommitted changes, or after sending work to the background, returned
INCOMPLETE -- recorded so, told to its parent when it resumes, and warned of before a review.

THE FAILURE THIS EXISTS FOR (Quiet Chat, 2026-11-06). A Builder started its regression suite in the
background and ended its turn; MARS closed the session and the suite died with it. Twice the
Builder's fixes were left uncommitted. Each return read as an ordinary return, the coordinator was
resumed as though it had a result, and a review was sent over work that was not all there.

MARS reads what a turn left behind (`_meta["mars/background"]`, `_meta["mars/workspace"]`, its own
read-only git check); Mentis only records it and reads the record. Through the real delegate,
dispatch and resumption, with the run's result scripted:

  * a dirty work tree -> `result-returned` has `incomplete.uncommitted` and `returned_incomplete`;
  * background work -> `incomplete.background`;
  * a clean return -> neither;
  * the parent's resume text names the incomplete child, and shows a child's answered decision;
  * a review delegated over an incomplete return is warned, not refused.
"""

from __future__ import annotations

import time

import pytest

from mentis.execution import RunResult
from mentis.web import dispatch as D
from tests._loop import _coordinator, a_conversation, grant_of_run, post, world  # noqa: F401
from tests._loop import script_every_backend
from tests.test_delegate_coordinate import _present

ROOT = "C:/Work/app"
DIRTY = [{"root": ROOT, "head": "abc123", "dirty": [" M src/a.py", "?? src/new.py"],
          "truncated": False}]
CLEAN = [{"root": ROOT, "head": "abc123", "dirty": [], "truncated": False}]
BACKGROUND = [{"toolCallId": "toolu_1", "title": "pytest -q tests",
               "backgroundTaskId": "b7x", "timedOutAfterMs": 600000}]
QUESTION = "Ship the candidate as it is, or wait for the corrected one?"
OPTIONS = [{"label": "Ship it", "consequence": "it goes out today"},
           {"label": "Wait", "consequence": "nothing ships until it is corrected"}]


@pytest.fixture()
def fake(world):
    """Runs return as the test says, by the expectation they carry: `left` gives a run's
    RunResult `background` / `workspace` (what MARS read at its turn end); one in `ask` raises
    a decision form while running."""
    from mentis.web import _surface
    from mentis.worker import _operate
    svc = world["state"].agents
    plan = {"left": {}, "ask": set()}

    def perform(spec):
        grant = grant_of_run(svc, spec, world["state"].path)
        if grant["expectation"] in plan["ask"]:
            _operate(_surface(world["state"]), "request_decision",
                     {"question": QUESTION, "options": OPTIONS,
                      "because": "only the owner can choose"}, grant)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done: here is what I did",
                         started_at=now, finished_at=now,
                         **plan["left"].get(grant["expectation"], {}))

    script_every_backend(svc, perform)
    return plan


def _delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def _run(world, out, who):
    return D.dispatch(world["state"], conversation=out["conversation"], turn=out["turn"],
                      participant=who, work=out["dispatch"]["work"],
                      expectation=out["expectation"])


def _returned(cv, expectation) -> dict:
    s = cv._child_state(expectation)
    assert s["state"] == "returned", s
    act = cv._act(s["ended_by"])
    assert act["act"] == D.RETURNED
    return act["detail"]


def _builder(world, fake, left=None):
    """P coordinates and delegates a Builder B, returning to it; B's run leaves `left`."""
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    builder = _present(world, cid, "@Builder")
    b = _delegate(world, grant, participant=builder, work="build the candidate",
                  return_to_me=True)
    if left:
        fake["left"][b["expectation"]] = left
    return world["cv"], cid, parent, grant, (b, builder)


# -- what is recorded on result-returned ----------------------------------------------------------


def test_a_dirty_work_tree_is_recorded_as_an_incomplete_return(world, fake):
    cv, _, _, _, (b, builder) = _builder(world, fake, {"workspace": DIRTY})
    _run(world, b, builder)
    detail = _returned(cv, b["expectation"])
    assert detail["returned_incomplete"] is True
    assert detail["incomplete"] == {
        "background": [],
        "uncommitted": [{"root": ROOT, "head": "abc123",
                         "dirty": [" M src/a.py", "?? src/new.py"]}]}
    # MARS's own reading is kept, as reported, beside it
    assert detail["runtime_evidence"]["workspace"] == DIRTY


def test_background_work_is_recorded_as_an_incomplete_return(world, fake):
    cv, _, _, _, (b, builder) = _builder(world, fake, {"background": BACKGROUND,
                                                       "workspace": CLEAN})
    _run(world, b, builder)
    detail = _returned(cv, b["expectation"])
    assert detail["returned_incomplete"] is True
    assert detail["incomplete"] == {"background": BACKGROUND, "uncommitted": []}


def test_a_clean_return_is_unchanged(world, fake):
    cv, _, _, _, (b, builder) = _builder(world, fake, {"workspace": CLEAN})
    _run(world, b, builder)
    detail = _returned(cv, b["expectation"])
    assert "incomplete" not in detail and "returned_incomplete" not in detail
    # and one MARS said nothing about at all
    cv, _, _, _, (b, builder) = _builder(world, fake)
    _run(world, b, builder)
    detail = _returned(cv, b["expectation"])
    assert "incomplete" not in detail and "returned_incomplete" not in detail


# -- what the parent is told when it resumes ------------------------------------------------------


def test_the_parents_resume_text_names_the_incomplete_child(world, fake):
    cv, _, parent, _, (b, builder) = _builder(world, fake, {"workspace": DIRTY,
                                                            "background": BACKGROUND})
    world["sent"].clear()
    _run(world, b, builder)
    assert [k["expectation"] for k in world["sent"]] == [parent]
    work = world["sent"][-1]["work"]
    assert f"  returned INCOMPLETE: uncommitted changes in {ROOT} (2 files)" in work
    assert ("  returned INCOMPLETE: sent work to the background, which was stopped when its "
            "run ended (pytest -q tests)") in work


def test_a_clean_childs_resume_text_says_nothing_incomplete(world, fake):
    cv, _, parent, _, (b, builder) = _builder(world, fake, {"workspace": CLEAN})
    world["sent"].clear()
    _run(world, b, builder)
    assert [k["expectation"] for k in world["sent"]] == [parent]
    assert "INCOMPLETE" not in world["sent"][-1]["work"]


def test_the_resume_text_shows_a_childs_answered_decision(world, fake):
    cv, cid, parent, grant, (b, builder) = _builder(world, fake)
    reviewer = _present(world, cid, "@Reviewer")
    r = _delegate(world, grant, participant=reviewer, work="review the candidate",
                  return_to_me=True)
    fake["ask"].add(r["expectation"])
    _run(world, b, builder)
    _run(world, r, reviewer)
    from mentis.conversation import DECISION_FORM
    fid = next(a["id"] for a in cv.history(caused_by=r["expectation"])
               if a["act"] == DECISION_FORM)
    form = cv.decision_form(fid)
    q = form["questions"][0]
    world["sent"].clear()
    got = post(world, f"/api/conversations/{form['conversation']}/turns",
               {"author": world["who"]["@brian"], "text": "Wait", "action": "record-only",
                "replies_to": form["post"], "addressed_to": [],
                "chose": {"expectation": q["expectation"], "option": 1, "label": "Wait"}})
    assert "error" not in got, got
    assert [k["expectation"] for k in world["sent"]] == [parent]
    work = world["sent"][-1]["work"]
    assert (f"- decision @Reviewer asked ({q['expectation']}): {QUESTION} -- "
            f"answered: chose 'Wait'") in work


# -- a review over an incomplete return ------------------------------------------------------------


def test_a_review_over_an_incomplete_return_is_warned(world, fake):
    cv, cid, parent, grant, (b, builder) = _builder(world, fake, {"workspace": DIRTY})
    _run(world, b, builder)
    reviewer = _present(world, cid, "@Reviewer")
    out = _delegate(world, grant, participant=reviewer, work="review the candidate",
                    review_of=b["expectation"], return_to_me=True)
    assert out.get("expectation"), out
    warned = [w for w in out.get("warnings") or () if "not review-ready" in w]
    assert warned == [
        f"@Builder ({b['expectation']}) returned INCOMPLETE: uncommitted changes in {ROOT} "
        f"(2 files). That work is not review-ready: a review now would not see all of it. "
        f"Have it finished and committed first, or say in the review that it is incomplete"]
    # reviewing this work as a whole names the same child
    out = _delegate(world, grant, participant=reviewer, work="review all of it",
                    review_of=parent, return_to_me=True)
    assert any(b["expectation"] in w and "not review-ready" in w
               for w in out.get("warnings") or ())


def test_a_review_over_a_clean_return_is_not_warned(world, fake):
    cv, cid, parent, grant, (b, builder) = _builder(world, fake, {"workspace": CLEAN})
    _run(world, b, builder)
    reviewer = _present(world, cid, "@Reviewer")
    out = _delegate(world, grant, participant=reviewer, work="review the candidate",
                    review_of=b["expectation"], return_to_me=True)
    assert out.get("expectation"), out
    assert not [w for w in out.get("warnings") or () if "review-ready" in w]


def test_other_work_over_an_incomplete_return_is_not_warned(world, fake):
    cv, cid, parent, grant, (b, builder) = _builder(world, fake, {"workspace": DIRTY})
    _run(world, b, builder)
    out = _delegate(world, grant, participant=builder, work="finish and commit it",
                    return_to_me=True)
    assert not [w for w in out.get("warnings") or () if "review-ready" in w]


def test_a_dirty_return_finished_by_a_later_delegation_is_not_warned(world, fake):
    """FINDING B: a Builder returns dirty, a later "finish and commit" delegation to the same
    Builder returns clean; a review of the whole work is not warned about the superseded return."""
    cv, cid, parent, grant, (b, builder) = _builder(world, fake, {"workspace": DIRTY})
    _run(world, b, builder)
    time.sleep(0.01)
    fix = _delegate(world, grant, participant=builder, work="finish and commit it",
                    return_to_me=True)
    fake["left"][fix["expectation"]] = {"workspace": CLEAN}
    _run(world, fix, builder)
    reviewer = _present(world, cid, "@Reviewer")
    out = _delegate(world, grant, participant=reviewer, work="review all of it",
                    review_of=parent, return_to_me=True)
    assert out.get("expectation"), out
    assert not [w for w in out.get("warnings") or () if "review-ready" in w]


# -- only what the run edited counts (`edited`, from MARS) -----------------------------------------


def test_files_the_run_did_not_edit_do_not_make_it_incomplete(world, fake):
    left = [{"root": ROOT, "head": "abc123", "edited": ["src/a.py"],
             "dirty": ["?? notes/old.txt", " M src/other.py"], "truncated": False}]
    cv, _, _, _, (b, builder) = _builder(world, fake, {"workspace": left})
    _run(world, b, builder)
    detail = _returned(cv, b["expectation"])
    assert "incomplete" not in detail and "returned_incomplete" not in detail
    assert detail["runtime_evidence"]["workspace"] == left   # the full reading is kept


def test_only_the_edited_files_dirty_lines_count(world, fake):
    left = [{"root": ROOT, "head": "abc123",
             "edited": ["src/a.py", "src/renamed.py", "pkg/new.py"],
             "dirty": [" M src/a.py", "?? notes/old.txt", "R  src/old.py -> src/renamed.py",
                       "?? pkg/", " M src/other.py"], "truncated": False}]
    cv, _, _, _, (b, builder) = _builder(world, fake, {"workspace": left})
    _run(world, b, builder)
    detail = _returned(cv, b["expectation"])
    assert detail["returned_incomplete"] is True
    assert detail["incomplete"]["uncommitted"] == [{
        "root": ROOT, "head": "abc123",
        "dirty": [" M src/a.py", "R  src/old.py -> src/renamed.py", "?? pkg/"]}]
    assert detail["runtime_evidence"]["workspace"] == left


def test_without_edited_every_dirty_line_counts():
    left = [{"root": ROOT, "head": "h", "dirty": ["?? notes/old.txt"]}]
    assert D.incomplete_of({"workspace": left})["uncommitted"][0]["dirty"] == ["?? notes/old.txt"]
    # a rename counts by its old side too
    left = [{"root": ROOT, "head": "h", "edited": ["src/old.py"],
             "dirty": ["R  src/old.py -> src/new.py"]}]
    assert D.incomplete_of({"workspace": left})["uncommitted"][0]["dirty"] == left[0]["dirty"]


# -- FINDING C: the tooling context does not displace the closing block --------------------------


def test_tooling_goes_before_the_closing_block():
    from mentis.execution.mars import with_tooling
    prompt = D.SPLIT.join(["# Your task\n\ndo it", "reply format",
                           D._closing_block("do it\n- [ ] tests pass", None)])
    out = with_tooling(prompt, "TOOLING: you have PowerShell")
    assert out.rstrip().endswith("- [ ] tests pass")
    before, closing = out.split("\n# Before you return", 1)
    assert "TOOLING: you have PowerShell" in before
    assert "TOOLING" not in closing
    assert out.replace("TOOLING: you have PowerShell" + D.SPLIT, "") == prompt
    # a prompt without one: appended as before
    assert with_tooling("plain work", "T") == "plain work\n\n---\nT"


def test_a_truncated_probe_or_an_error_alone_is_not_incomplete(world, fake):
    """MARS's last entry when it hit a probe limit has no root; an error entry has no dirty
    lines. Neither is a work tree with uncommitted changes, and both are kept as evidence."""
    left = [{"root": ROOT, "error": "git status did not finish within 5s", "edited": ["a.py"]},
            {"truncated_probe": True, "reason": "directories"}]
    cv, _, _, _, (b, builder) = _builder(world, fake, {"workspace": left})
    _run(world, b, builder)
    detail = _returned(cv, b["expectation"])
    assert "incomplete" not in detail and "returned_incomplete" not in detail
    assert detail["runtime_evidence"]["workspace"] == left
    # beside a dirty tree, the probe entry is skipped and the tree still counts
    dirty = [{**DIRTY[0], "edited": ["src/a.py"]}, {"truncated_probe": True, "reason": "deadline"}]
    assert D.incomplete_of({"workspace": dirty})["uncommitted"] == [
        {"root": ROOT, "head": "abc123", "dirty": [" M src/a.py"]}]


def test_an_untracked_directory_matches_an_edited_file_under_it():
    left = [{"root": ROOT, "head": "h", "dirty": ["?? sub/", "?? other/"], "truncated": False,
             "edited": ["sub/new.txt"]}]
    assert D.incomplete_of({"workspace": left})["uncommitted"][0]["dirty"] == ["?? sub/"]
