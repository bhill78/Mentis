"""Workspace continuity in delegation (owner correction 2026-11-22).

A part's corrections are handed the part's existing checkout (`repository`), and
a review works in its OWN review workspace while still naming what it reviews
(`review_of`), so a standing review checkout can be reused across rounds and the
review keeps avoiding its author's runtime. A review is never put to work in the
checkout its author declared.

Checked through the real delegate operation and the real dispatch path, with
only the runs scripted (`tests/_loop.runs`).
"""

from __future__ import annotations

import os

import pytest

from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401


def _delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def _run(world, out):
    from mentis.web import dispatch as D
    spec = out["dispatch"]
    return D.dispatch(world["state"], conversation=out["conversation"],
                      turn=spec.get("turn") or out["turn"],
                      participant=spec["participant"], work=spec["work"],
                      persona=spec.get("persona"), runtime=spec.get("runtime"),
                      model=spec.get("model"), effort=spec.get("effort"),
                      requires=spec.get("requires") or (),
                      expectation=out["expectation"])


def _started(cv, expectation):
    got = [a for a in cv.history(caused_by=expectation)
           if a["act"] == "execution-started"]
    assert got, "the run did not start"
    return got[-1]


def _checkout(path):
    os.makedirs(os.path.join(path, ".git"), exist_ok=True)
    return str(path)


@pytest.fixture()
def built(world, runs, tmp_path):
    """@Ada carries the work (on codex) and delegated a part to @Bob, built in
    Bob's own checkout. Returns Ada's grant and the part's request."""
    cv = world["cv"]
    ada = world["who"]["@Ada"]
    cid = a_conversation(world)
    asked = say(world, cid, "@Ada build it", action="ask-participant",
                dispatch=[{"participant": ada, "work": "build it",
                           "runtime": "codex"}])
    assert "error" not in asked, asked
    top = asked["expectations"][0]
    grant = runs[-1]
    builder_ws = _checkout(tmp_path / "part-a")
    bob = cv.create_participant("@Bob")
    part = _delegate(world, grant, participant=bob, work="build part A",
                     repository=builder_ws, runtime="codex")
    assert "error" not in part, part
    return {"cid": cid, "top": top, "grant": grant, "part": part,
            "builder_ws": builder_ws, "bob": bob, "tmp": tmp_path,
            "reviewer": cv.define_persona("Reviewer", "Review the work."),
            "rev": cv.create_participant("@Rev")}


def test_a_correction_is_handed_the_parts_existing_checkout(world, built):
    from mentis.web.dispatch import declared_workspace
    b = built
    again = _delegate(world, b["grant"], participant=b["bob"],
                      work="correct part A: B1", repository=b["builder_ws"],
                      runtime="codex")
    assert declared_workspace(world["cv"], again["expectation"]) == \
        os.path.normpath(b["builder_ws"])


def test_a_review_without_its_own_workspace_is_refused_in_the_authors_checkout(
        world, built):
    from mentis.worker import NotPermitted
    b = built
    with pytest.raises(NotPermitted, match="does not work in its author's checkout"):
        _delegate(world, b["grant"], participant=b["rev"], work="review part A",
                  persona=b["reviewer"], review_of=b["part"]["expectation"])


@pytest.mark.parametrize("where", ["same", "inside", "around"])
def test_a_review_workspace_overlapping_the_authors_checkout_is_refused(
        world, built, where):
    from mentis.worker import NotPermitted
    b = built
    path = {"same": b["builder_ws"],
            "inside": os.path.join(b["builder_ws"], "sub"),
            "around": str(b["tmp"])}[where]
    os.makedirs(path, exist_ok=True)
    with pytest.raises(NotPermitted, match="overlaps the checkout"):
        _delegate(world, b["grant"], participant=b["rev"], work="review part A",
                  persona=b["reviewer"], review_of=b["part"]["expectation"],
                  repository=path)


def test_a_review_works_in_its_own_workspace_and_stays_independent(world, built):
    from mentis.web.dispatch import declared, declared_workspace
    b = built
    cv = world["cv"]
    review_ws = _checkout(b["tmp"] / "review-part-a")
    first = _delegate(world, b["grant"], participant=b["rev"], work="review part A",
                      persona=b["reviewer"], review_of=b["part"]["expectation"],
                      repository=review_ws)
    decl = declared(cv, first["expectation"])
    assert decl["review_of"] == b["part"]["expectation"]
    assert declared_workspace(cv, first["expectation"]) == os.path.normpath(review_ws)
    _run(world, first)
    assert _started(cv, first["expectation"])["runtime"] != "codex", \
        "the review ran on the author's runtime"
    # THE SAME REVIEW WORKSPACE serves the next round.
    again = _delegate(world, b["grant"], participant=b["rev"],
                      work="re-review part A's correction", persona=b["reviewer"],
                      review_of=b["part"]["expectation"], repository=review_ws)
    assert declared_workspace(cv, again["expectation"]) == os.path.normpath(review_ws)


def test_a_review_of_work_in_a_workspace_root_still_works_there(world, runs, tmp_path):
    """Unchanged: a reviewed directory that is not a checkout (a workspace root)
    is where an unnamed review works."""
    from mentis.web.dispatch import declared_workspace
    cv = world["cv"]
    cid = a_conversation(world)
    asked = say(world, cid, "@Ada build it", action="ask-participant",
                dispatch=[{"participant": world["who"]["@Ada"], "work": "build it",
                           "runtime": "codex"}])
    grant = runs[-1]
    root = str(tmp_path / "workspace-root")
    os.makedirs(root)
    part = _delegate(world, grant, participant=cv.create_participant("@Bob"),
                     work="build part A", repository=root)
    review = _delegate(world, grant, participant=cv.create_participant("@Rev"),
                       work="review part A",
                       persona=cv.define_persona("Reviewer", "Review the work."),
                       review_of=part["expectation"])
    assert declared_workspace(cv, review["expectation"]) == os.path.normpath(root)


def test_a_link_into_the_authors_checkout_is_still_the_authors_checkout(world, runs, tmp_path):
    """A declared directory that is a junction into a subdirectory of a checkout
    is judged by where it leads, so a review is not put to work there."""
    import _winapi
    from mentis.worker import NotPermitted
    cv = world["cv"]
    cid = a_conversation(world)
    say(world, cid, "@Ada build it", action="ask-participant",
        dispatch=[{"participant": world["who"]["@Ada"], "work": "build it",
                   "runtime": "codex"}])
    grant = runs[-1]
    inner = tmp_path / "checkout" / "crate"
    os.makedirs(inner)
    _checkout(tmp_path / "checkout")
    alias = str(tmp_path / "alias-to-crate")
    _winapi.CreateJunction(str(inner), alias)
    part = _delegate(world, grant, participant=cv.create_participant("@Bob"),
                     work="build the crate", repository=alias)
    with pytest.raises(NotPermitted, match="does not work in its author's checkout"):
        _delegate(world, grant, participant=cv.create_participant("@Rev"),
                  work="review the crate",
                  persona=cv.define_persona("Reviewer", "Review the work."),
                  review_of=part["expectation"])
