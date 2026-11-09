"""A finding is offered and started as the work it names, not as the reason it is real.

THE DRIFT THIS EXISTS FOR (Quiet Chat, 2026-11-08). A finding's work was "Reconcile base branch
for Quiet Chat ...", and its reason began "Both Track A (quiet-nav-rails-codex) and Track B
(quiet-nav-floating-antigravity) worktrees were branched from origin/main ...". The owner was
offered "Pursue: Both Track A (quiet-nav-rails-codex) and Track B (quiet-nav-floating-antigravity"
-- read, reasonably, as pursuing the two navigation tracks -- and the Caretaker started for the
finding was handed that reason as its work. The decision's selections were right; its words were
the reason's.
"""

from __future__ import annotations

from mentis.conversation import posting
from mentis.operational import ask_about_findings, finding_words, trunk_of
from tests._loop import _coordinator, a_conversation, world  # noqa: F401

WORK = ("Reconcile base branch for Quiet Chat parallel navigation experiment "
        "(origin/main vs the unmerged article-first candidate)")
REASON = ("Both Track A (quiet-nav-rails-codex) and Track B (quiet-nav-floating-antigravity) "
          "worktrees were branched from origin/main, where Quiet Chat is at the Round 4 baseline")


def _finding(world):
    from mentis.web import _surface
    from mentis.worker import _operate
    cid = a_conversation(world)
    _coach, parent, grant = _coordinator(world, cid)
    found = _operate(_surface(world["state"]), "record_discovered_work",
                     {"work": WORK, "because": REASON}, grant)
    return cid, parent, grant, found["expectation"]


def test_a_finding_is_labelled_by_its_work_not_its_reason(world):
    cv = world["cv"]
    cid, parent, grant, f = _finding(world)
    assert cv._act(f)["because"] == REASON
    assert finding_words(cv, f).startswith("Reconcile base branch")
    brain = world["state"].brain
    asked = ask_about_findings(
        brain, [f], conversation=cid, by=grant["participant"], owner=world["who"]["@brian"],
        caused_by=parent, originating_turn=trunk_of(brain, parent)["originating_turn"],
        question="Finished. Pursue, keep deferred or dismiss each.")
    labels = [o["label"] for o in asked["options"]]
    assert labels[0].startswith("Pursue: Reconcile base branch for Quiet Chat")
    assert not any("Track A" in lab for lab in labels)
    # cut at a word, and said to be cut
    assert labels[0].endswith("…") and len(labels[0]) <= len("Pursue: ") + 80
    # what an option MEANS is still its selections, unchanged
    assert asked["options"][0]["selections"] == {f: "pursue"}


def test_a_pursued_finding_is_started_with_its_work(world):
    cv = world["cv"]
    _cid, _parent, _grant, f = _finding(world)
    started = []
    out = posting.pursue_chosen(cv, [f], by=world["who"]["@brian"], decision=None,
                                enqueue=lambda **kw: started.append(kw))
    assert out and out[0]["assigned"], out
    assert started[0]["expectation"] == f
    assert started[0]["work"].startswith("Reconcile base branch")
    assert "Track A" not in started[0]["work"]


def test_a_finding_with_no_turn_words_falls_back_to_its_reason(world):
    cv = world["cv"]
    _cid, _parent, _grant, f = _finding(world)
    from unittest import mock
    with mock.patch.object(cv._c, "read", return_value=[]):
        assert finding_words(cv, f) == REASON
