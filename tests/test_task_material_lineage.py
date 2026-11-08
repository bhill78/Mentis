"""Work handed down from the owner's request can read what that request was asked with.

THE REFUSAL THIS EXISTS FOR (Quiet Chat, 2026-11-08). The owner's request carried five
screenshots. The coordinator delegated the plan to a Planner, naming that request among the
delegation's `references` but handing on no artifacts, and the Planner's `read_artifact` was
refused: "not offered to this execution, and delegated work is bounded to what its delegation
handed it". The owner: an agent authorised to perform work must be able to access the original
request's materials without redundant manual attachment or owner approval.

What holds now, through the real Ask @Participant, delegate and read_artifact:

  * a child -- and a grandchild -- reads the owner request's attachments with nothing handed on;
    they are offered to its run, each saying which request it came from;
  * an owner's continuation of the work reads the original request's attachments too;
  * an explicit hand-off still offers what lies outside that line, and returns still flow back;
  * work on another line, in another Conversation, or after the asking Turn was deleted reads
    nothing by knowing an id, and a restricted line's returns stay its own.
"""

from __future__ import annotations

import base64

import pytest

from mentis import artifacts
from mentis.conversation import text, versions
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_delegate_coordinate import _present


def _hold(world, cid, data, name):
    cv = world["cv"]
    owner = world["who"]["@brian"]
    held = artifacts.hold(cv.corpus, cv, data, act="artifact-submitted", actor=owner,
                          source=f"submission:{owner}", door="human-ingress",
                          conversation=cid)
    return {**artifacts.part(held["admission"], corpus=cv.corpus), "alt": name}


def _grant(world, expectation, cid, participant, *, coordinate=False):
    """The grant a run carrying `expectation` holds, minted as dispatch mints it."""
    cv = world["cv"]
    grants = world["state"].agents.authority
    iid = f"run-{len(grants._grants)}-{expectation[-6:]}"
    ops = cv.authority_of(expectation)["operations"] if coordinate else []
    grants.authorise_for(iid, dict(scope="organising" if coordinate else "worker",
                                   operations=ops, expectation=expectation,
                                   conversation=cid, participant=participant,
                                   runtime="claude"))
    return grants.grant_for(grants._grant(iid, world["state"].path), world["state"].path)


def _op(world, grant, operation, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), operation, args, grant)


@pytest.fixture()
def task(world):
    """The owner asks @Coach to coordinate, with two screenshots on the request; @Coach
    delegates the plan to @Planner, referencing the request and handing on nothing."""
    cid = a_conversation(world, "Quiet Chat")
    coach = world["cv"].create_participant("@Coach")
    shots = [_hold(world, cid, b"\x89PNG article view", "article.png"),
             _hold(world, cid, b"\x89PNG settings view", "settings.png")]
    out = say(world, cid, "", action="ask-participant", addressed_to=[coach],
              parts=[text("@Coach restore the article-first experience, as shown"), *shots],
              dispatch=[{"participant": coach, "work": "coordinate", "coordinate": True}])
    assert "error" not in out, out
    root = out["expectations"][0]
    coach_grant = _grant(world, root, cid, coach, coordinate=True)
    planner = _present(world, cid, "@Planner")
    child = _op(world, coach_grant, "delegate", participant=planner,
                work="write the plan", return_to_me=True,
                references=[world["cv"].expectation_state(root)["turn"]])
    assert "error" not in child and child.get("expectation"), child
    world["sent"].clear()
    return {"cid": cid, "root": root, "coach": coach, "coach_grant": coach_grant,
            "planner": planner, "child": child["expectation"],
            "child_grant": _grant(world, child["expectation"], cid, planner),
            "shots": [s["ref"] for s in shots]}


def _read(world, grant, ref):
    return _op(world, grant, "read_artifact", ref=ref, why="the owner's screenshot")


def test_a_delegated_builder_reads_the_owner_requests_images_handed_nothing(world, task):
    cv = world["cv"]
    offered = artifacts.available(cv.corpus, cv, {"expectation": task["child"]})
    inherited = [w for w in offered if w["because"] == "inherited-from-request"]
    assert [w["ref"] for w in inherited] == task["shots"]
    assert all(w["request"] == task["root"] and w["source"] == "asked-with"
               for w in inherited)
    for ref in task["shots"]:
        got = _read(world, task["child_grant"], ref)
        assert "error" not in got and got.get("ref", ref) == ref, got
    # the read is recorded with why it was reachable
    supplied = [a for a in cv.history(caused_by=task["child"])
                if a["act"] == artifacts.SUPPLIED]
    assert supplied and all((a["detail"]["reachable"] or {}).get("because")
                            == "inherited-from-request" for a in supplied)


def test_a_further_delegation_reads_them_too(world, task):
    builder = _present(world, task["cid"], "@Builder")
    grand = _op(world, task["child_grant"], "delegate", participant=builder,
                work="build part one", return_to_me=True)
    assert "error" not in grand, grand
    g = _grant(world, grand["expectation"], task["cid"], builder)
    assert all("error" not in _read(world, g, r) for r in task["shots"])


def test_an_owner_continuation_reads_the_original_requests_images(world, task):
    cv = world["cv"]
    reply = cv.say(task["cid"], task["coach"], [text("plan is up")],
                   replies_to=cv.expectation_state(task["root"])["turn"])
    cont = say(world, task["cid"], "carry on", replies_to=reply, action="ask-participant",
               dispatch=[{"participant": task["coach"], "work": "carry on"}])
    assert "error" not in cont, cont
    exp = cont["expectations"][0]
    assert cv._act(exp)["caused_by"] == task["root"]
    offered = [w["ref"] for w in artifacts.available(cv.corpus, cv, {"expectation": exp})]
    assert set(task["shots"]) <= set(offered)


def test_work_on_another_line_cannot_read_them_by_knowing_the_id(world, task):
    cv = world["cv"]
    # another request in the same Conversation, delegated: bounded to its own line
    other = say(world, task["cid"], "@Coach something else", action="ask-participant",
                addressed_to=[task["coach"]],
                dispatch=[{"participant": task["coach"], "work": "other", "coordinate": True}])
    og = _grant(world, other["expectations"][0], task["cid"], task["coach"], coordinate=True)
    stranger = _present(world, task["cid"], "@Stranger")
    side = _op(world, og, "delegate", participant=stranger, work="unrelated")
    sg = _grant(world, side["expectation"], task["cid"], stranger)
    from mentis.worker import NotPermitted
    for ref in task["shots"]:
        assert artifacts.reachable(cv.corpus, cv, sg, ref)[0] is None
        with pytest.raises(NotPermitted, match="not reachable"):
            _read(world, sg, ref)
    # and work in another Conversation reaches nothing of this one
    elsewhere = a_conversation(world, "Elsewhere")
    far = say(world, elsewhere, "@Coach elsewhere", action="ask-participant",
              addressed_to=[task["coach"]],
              dispatch=[{"participant": task["coach"], "work": "far"}])
    fg = _grant(world, far["expectations"][0], elsewhere, task["coach"])
    assert all(artifacts.reachable(cv.corpus, cv, fg, r)[0] is None for r in task["shots"])


def test_a_deleted_asking_turn_hands_nothing_down(world, task):
    cv = world["cv"]
    versions.delete(cv, cv.expectation_state(task["root"])["turn"],
                    by=world["who"]["@brian"])
    assert not [w for w in artifacts.available(cv.corpus, cv, {"expectation": task["child"]})
                if w["because"] == "inherited-from-request"]
    assert all(artifacts.reachable(cv.corpus, cv, task["child_grant"], r)[0] is None
               for r in task["shots"])


def test_returns_still_flow_and_a_restricted_lines_returns_stay_its_own(world, task,
                                                                     tmp_path):
    cv = world["cv"]
    plan, secret = tmp_path / "plan.md", tmp_path / "secret.md"
    plan.write_text("# the plan")
    secret.write_text("secret")
    # the Planner returns a file; its parent reads it, as before
    made = _op(world, task["child_grant"], "return_artifact", path=str(plan),
               bytes_b64=base64.b64encode(plan.read_bytes()).decode(), because="the plan")
    ref = made.get("ref") or made.get("admission")
    assert ref, made
    assert artifacts.reachable(cv.corpus, cv, task["coach_grant"], ref)[0] is not None
    # a restricted sibling line keeps its returns from the Planner's line
    sibling = _present(world, task["cid"], "@Sibling")
    sib = _op(world, task["coach_grant"], "delegate", participant=sibling,
              work="private part", return_to_me=True)
    artifacts.restrict(cv, sib["expectation"], by=world["who"]["@brian"], because="private")
    sg = _grant(world, sib["expectation"], task["cid"], sibling)
    kept = _op(world, sg, "return_artifact", path=str(secret),
               bytes_b64=base64.b64encode(secret.read_bytes()).decode(), because="private notes")
    kref = kept.get("ref") or kept.get("admission")
    assert artifacts.reachable(cv.corpus, cv, task["child_grant"], kref)[0] is None
    # while the restricted line itself still reads the owner's screenshots
    assert all(artifacts.reachable(cv.corpus, cv, sg, r)[0] is not None
               for r in task["shots"])


# -- found by the independent review: picked-up work follows its pick-up ---------------------------

def _owner_request(world, cid, who, words, shots=()):
    out = say(world, cid, "", action="ask-participant", addressed_to=[who],
              parts=[text(words), *shots],
              dispatch=[{"participant": who, "work": words, "coordinate": True}])
    assert "error" not in out, out
    return out["expectations"][0]


def test_picked_up_work_inherits_the_request_it_was_picked_up_under(world, task):
    """Not the line it was found on: a finding's `caused_by` is only where it was found."""
    from mentis.web import _surface
    from tests.gravity_choice import owner_chooses
    cv = world["cv"]
    found = _op(world, task["child_grant"], "record_discovered_work",
                work="found on the way", because="side")["expectation"]
    owner_chooses(_surface(world["state"]), task["child_grant"], found)
    # a finding nobody picked up starts its own part: it inherits nothing
    assert not [w for w in artifacts.available(cv.corpus, cv, {"expectation": found})
                if w["because"] == "inherited-from-request"]
    coach2 = _present(world, task["cid"], "@Coach2")
    s2 = _hold(world, task["cid"], b"\x89PNG r2", "r2.png")
    r2 = _owner_request(world, task["cid"], coach2, "@Coach2 other work", [s2])
    g2 = _grant(world, r2, task["cid"], coach2, coordinate=True)
    x = _present(world, task["cid"], "@X")
    assert _op(world, g2, "delegate", participant=x, work="take it",
               expectation=found).get("picked_up")
    xg = _grant(world, found, task["cid"], x)
    assert artifacts.reachable(cv.corpus, cv, xg, s2["ref"])[0] is not None
    assert all(artifacts.reachable(cv.corpus, cv, xg, r)[0] is None for r in task["shots"])


def test_a_restricted_return_does_not_reach_another_line_through_a_picked_up_finding(
        world, task, tmp_path):
    from mentis.web import _surface
    from mentis.worker import NotPermitted
    from tests.gravity_choice import owner_chooses
    cv = world["cv"]
    cid = task["cid"]
    sib = _present(world, cid, "@Sib")
    s = _op(world, task["coach_grant"], "delegate", participant=sib, work="private part",
            return_to_me=True)
    artifacts.restrict(cv, s["expectation"], by=world["who"]["@brian"], because="private")
    sg = _grant(world, s["expectation"], cid, sib)
    p = tmp_path / "secret.md"
    p.write_text("secret")
    kref = _op(world, sg, "return_artifact", path=str(p),
               bytes_b64=base64.b64encode(p.read_bytes()).decode(), because="private")
    kref = kref.get("ref") or kref.get("admission")
    # the coordinator (an ancestor, exempt) hands it to @Part explicitly
    part = _present(world, cid, "@Part")
    h = _op(world, task["coach_grant"], "delegate", participant=part, work="use it",
            artifacts=[kref])
    pg = _grant(world, h["expectation"], cid, part)
    found = _op(world, pg, "record_discovered_work", work="side thing",
                because="side")["expectation"]
    owner_chooses(_surface(world["state"]), pg, found)
    # another request's coordinator picks the finding up for @X
    coach2 = _present(world, cid, "@Coach2")
    r2 = _owner_request(world, cid, coach2, "@Coach2 other")
    g2 = _grant(world, r2, cid, coach2, coordinate=True)
    x = _present(world, cid, "@X")
    assert _op(world, g2, "delegate", participant=x, work="take it",
               expectation=found).get("picked_up")
    xg = _grant(world, found, cid, x)
    assert artifacts.reachable(cv.corpus, cv, xg, kref)[0] is None
    with pytest.raises(NotPermitted):
        _op(world, xg, "delegate", participant=_present(world, cid, "@Y"),
            work="pass on", artifacts=[kref])
