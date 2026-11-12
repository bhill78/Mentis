"""Requirement lineage (docs/model-selection-contract.md section 2):
`continues`/`revises` inherit solution and reasoning from what they continue
(raised, with a warning); `new` breaks it; continuation is read from the
record -- a referenced returned result, a Turn that replies to one, the same
parent/participant/activity -- and never a model or effort. A resumed run keeps
its requirements; a request recorded by the old code still reads and resumes.
"""

from __future__ import annotations

from mentis.web import dispatch as D
from tests._catalogue_world import (cat_carrying, cat_real, delegate,  # noqa: F401
                                    latest_start, reply_of, routing_of, run)
from tests._loop import a_conversation, runs, say, world  # noqa: F401
from tests.test_delegate_activity import _discipline, _workflow


def _deep(world, carrying, **args):
    cv = world["cv"]
    first = delegate(world, carrying["grant"], participant=carrying["bob"],
                     work="design it", requires=[], solution="open",
                     reasoning="deep", **args)
    run(world, first)
    return first["expectation"], reply_of(cv, first["expectation"])


def test_a_continuation_inherits_and_a_lower_statement_is_raised(world,
                                                                  cat_carrying):
    cv = world["cv"]
    first, reply = _deep(world, cat_carrying)
    fix = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="small correction", requires=[], reasoning="light",
                   solution="specified", references=[reply])
    req = routing_of(cv, fix["expectation"])["requirements"]
    found = req["relation"].pop("found")
    assert req["relation"] == {"value": "continues", "ref": [first],
                               "source": "inherited"}
    assert found == [f"{first}: a result was returned on {reply}, which this "
                     f"references"], "how the record found it, recorded"
    assert req["reasoning"]["value"] == "deep"
    assert req["reasoning"]["raised_from"] == {"value": "light",
                                               "source": "stated"}
    assert req["solution"]["value"] == "open"
    raised = [w for w in fix["warnings"] if "raised" in w]
    assert len(raised) == 2 and "state relation `new`" in raised[0]
    # NEVER A MODEL OR EFFORT: the run selects for the need it inherited
    run(world, fix)
    d = latest_start(cv, fix["expectation"])["detail"]
    assert d["requested_model"] is None and d["requested_effort"] is None
    assert d["selected_model"] in ("claude-opus-5", "gpt-6.1-sol")
    assert d["requirements"]["reasoning"]["source"] == "inherited"


def test_nothing_stated_inherits_whole(world, cat_carrying):
    cv = world["cv"]
    first, reply = _deep(world, cat_carrying)
    fix = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="correct it", requires=[], references=[reply])
    routed = routing_of(cv, fix["expectation"])
    assert routed["requirements"]["reasoning"] == {"value": "deep",
                                                   "source": "inherited",
                                                   "from": [first]}
    assert routed["required_tier"] == "frontier"
    assert routed["inherited_tier"] == "frontier", "the old field, for old readers"
    assert routed["inherited_from"] == [first]
    assert not any("raised" in w for w in fix.get("warnings") or ())


def test_new_breaks_the_lineage(world, cat_carrying):
    cv = world["cv"]
    _, reply = _deep(world, cat_carrying)
    fresh = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="unrelated", requires=[], relation="new",
                     reasoning="light", references=[reply])
    req = routing_of(cv, fresh["expectation"])["requirements"]
    detected = req["relation"].pop("detected")
    assert req["relation"] == {"value": "new", "ref": [], "source": "stated"}
    # HONOURED, AND RECORDED AS OVERRIDING what the record found (round 2)
    assert detected["overridden"] is True and detected["value"] == "continues"
    assert detected["ref"] and detected["found"]
    assert any("relation 'new' was stated" in w for w in fresh["warnings"])
    assert req["reasoning"] == {"value": "light", "source": "stated", "from": []}
    assert "inherited_tier" not in routing_of(cv, fresh["expectation"])


def test_verifies_takes_its_own(world, cat_carrying):
    cv = world["cv"]
    first, reply = _deep(world, cat_carrying)
    check = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="check the tests pass", requires=[],
                     relation="verifies", relation_ref=[first],
                     solution="specified", reasoning="light",
                     references=[reply])
    req = routing_of(cv, check["expectation"])["requirements"]
    assert req["reasoning"]["value"] == "light"
    assert req["relation"]["value"] == "verifies"


def test_revises_by_ref_inherits_from_what_it_names(world, cat_carrying):
    cv = world["cv"]
    first, _ = _deep(world, cat_carrying)
    started = latest_start(cv, first)["id"]
    again = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="revise it", requires=[], relation="revises",
                     relation_ref=[started])
    req = routing_of(cv, again["expectation"])["requirements"]
    assert req["relation"] == {"value": "revises", "ref": [started],
                               "source": "stated"}
    assert req["reasoning"] == {"value": "deep", "source": "inherited",
                                "from": [first]}


def test_a_turn_that_replies_to_a_returned_result_continues_it(world,
                                                              cat_carrying):
    cv = world["cv"]
    first, reply = _deep(world, cat_carrying)
    remark = cv.say(cat_carrying["cid"], world["who"]["@brian"],
                    [{"type": "text", "text": "this part is wrong"}],
                    replies_to=reply)
    fix = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="fix what was remarked", requires=[], references=[remark])
    req = routing_of(cv, fix["expectation"])["requirements"]
    assert req["relation"]["ref"] == [first]
    assert req["reasoning"]["value"] == "deep"


def test_same_parent_participant_and_activity_continues(world, runs):
    cv = world["cv"]
    builder = cv.define_persona("Builder", "Build the part you are given.")
    wf = _workflow(world, persona=builder,
                   disciplines=[_discipline(world, "Targeted tests")])
    cid = a_conversation(world)
    out = say(world, cid, "change the software", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "carry it",
                         "governed": [wf]}])
    grant = runs[-1]
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    first = delegate(world, grant, participant=bob, work="build part one",
                     activity=f"{wf}#implement", solution="open",
                     reasoning="deep", requires=[])
    again = delegate(world, grant, participant=bob, work="fix part one",
                     activity=f"{wf}#implement", requires=[])
    req = routing_of(cv, again["expectation"])["requirements"]
    assert req["relation"]["ref"] == [first["expectation"]]
    assert req["solution"]["value"] == "open"
    eve = cv.create_participant("@Eve")
    cv.join(eve, cid, attributed_to=world["who"]["@brian"])
    other = delegate(world, grant, participant=eve, work="fix part one",
                     activity=f"{wf}#implement", requires=[])
    assert "requirements" not in (routing_of(cv, other["expectation"]) or {})


def test_an_older_record_is_inherited_through_its_routing(world, cat_carrying):
    """A request recorded before requirements: its `difficulty` (and an advisory
    tier) are read through `requirements.from_routing`."""
    cv = world["cv"]
    first = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                     work="old work", requires=[])
    run(world, first)
    # what the old code wrote: routing with only the legacy fields
    old = cv.record_act(actor=world["who"]["@brian"], act="expectation-recorded",
                        detail={"routing": {"required_tier": "frontier",
                                            "target_effort": "high",
                                            "tier_sources": ["difficulty"],
                                            "difficulty": "debugging"}})
    got = D.inherited_requirements(cv, [old])
    assert got == {"solution": "open", "reasoning": "deep", "from": [old]}
    advised = cv.record_act(actor=world["who"]["@brian"], act="expectation-recorded",
                            detail={"routing": {"required_tier": "coding",
                                                "advisory_tier": "coding",
                                                "tier_sources": ["advisory"]}})
    assert D.inherited_requirements(cv, [advised]) == {
        "solution": "specified", "reasoning": "substantial", "from": [advised]}
    assert D.inherited_requirements(cv, [first["expectation"]]) is None


def test_a_resumed_run_keeps_its_requirements(world, cat_carrying):
    cv = world["cv"]
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="design it", requires=[], solution="open",
                   reasoning="substantial")
    run(world, out)
    run(world, out)        # a second run of the same request
    starts = [a for a in cv.history(caused_by=out["expectation"])
              if a["act"] == "execution-started"]
    assert len(starts) == 2
    for s in starts:
        d = s["detail"]
        assert d["requirements"] == routing_of(cv, out["expectation"])["requirements"]
        assert d["selected_model"] == "claude-opus-5"
    now = D.routing_now(cv, out["expectation"])
    assert now["requirements"]["solution"]["value"] == "open"


def test_a_historical_request_still_reads_and_resumes(world, cat_carrying):
    """A request and execution-started written by the old code (no
    `requirements`, no `selection`): dispatch resumes it on exactly the tier it
    recorded, and the evidence projection reads it."""
    from mentis import evidence as E
    cv = world["cv"]
    out = delegate(world, cat_carrying["grant"], participant=cat_carrying["bob"],
                   work="old work", requires=[], difficulty="complex")
    exp = out["expectation"]
    # rewrite nothing: build the OLD shape beside it as the old code wrote it
    turn = cv._act(exp)["turn"]
    old = cv.expect(turn, of=cat_carrying["bob"], kind="result",
                    by=world["who"]["@brian"],
                    detail={"routing": {"required_tier": "frontier",
                                        "target_effort": "high",
                                        "tier_sources": ["difficulty"],
                                        "difficulty": "complex"}})
    old_start = cv.record_act(actor=cat_carrying["bob"], act="execution-started",
                              caused_by=old, runtime="claude", execution="h-old",
                              detail={"selected_model": "claude-opus-5",
                                      "selected_effort": "high",
                                      "effective_model": "claude-opus-5",
                                      "routing": {"required_tier": "frontier",
                                                  "tier_sources": ["difficulty"],
                                                  "difficulty": "complex"}})
    routed = D.routing_now(cv, old)
    assert "requirements" not in routed and routed["required_tier"] == "frontier"
    need = D.need_of(routed)
    assert (need["level"], need["open"]) == ("deep", True)
    rows = E.per_execution(cv, expectation=old)
    assert rows[0]["started"] == old_start
    assert rows[0]["requirements"]["solution"] == "open"
    run(world, {**out, "expectation": old})
    d = latest_start(cv, old)["detail"]
    assert d["selected_model"] in ("claude-opus-5", "gpt-6.1-sol")
    assert d["selected_effort"] == "high"
    assert d["requirements"]["solution"] == {"value": "open", "source": "compat",
                                             "from": []}
    assert d["routing"]["required_tier"] == "frontier"
