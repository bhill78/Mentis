"""A hand-off keeps the tier of the work it continues; a named runtime that
lacks what the work requires is refused at `delegate` (Quiet Chat, 2026-11-06).

WHAT HAPPENED. Corrections of complex work were delegated naming runtime
claude and stating no difficulty, so they ran at the soft default tier --
claude's coding-tier model -- not the frontier model the work they corrected
had. And an integration was delegated naming codex for browser work; `delegate`
only warned, and the run failed later, before starting, as Unsupported.

What holds now, through the real delegate and dispatch paths:

  * no difficulty and no advisory tier -> the highest tier declared for the
    work it continues (the requests its `references` answered, earlier
    delegations of the same activity key to the same Participant), recorded as
    `inherited` with where from, and filled inside a named runtime;
  * a stated difficulty wins; nothing to inherit -> the default tier, as
    before, and the carrier is warned;
  * a named runtime lacking a required capability -> refused, nothing written,
    the eligible runtimes said; a capacity problem alone still only warns;
  * `capabilities` says, per runtime, what it has, lacks or is unknown for.
"""

from __future__ import annotations

import time

import pytest

from mentis.web import dispatch as D
from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import runs  # noqa: F401
from tests.test_delegate_activity import _discipline, _workflow
from tests.test_model_effort_routing import _claude, _codex, _plain


def _catalogue():
    """The routing catalogue, with what MARS measured of each (2026-10-29):
    claude builds UIs and drives a browser; codex's sandbox cannot."""
    return [{**_claude(), "capabilities": ["build_ui", "drive_browser"]},
            {**_codex(), "lacks": {
                "drive_browser": "its sandbox denied Playwright (EACCES)"}},
            _plain("antigravity", ["argon"], ["low"])]


@pytest.fixture()
def real(world, monkeypatch):
    """Real posting, delegate and dispatch over `_catalogue`; every run
    answers "done". Grants are kept."""
    import mentis.web as web
    st = world["state"]
    svc = st.agents
    svc.execution._backends = _catalogue()
    grants = []

    def perform(spec):
        grants.append(svc.authority.grant_for(svc.authority.grant_of(spec.run_id),
                                              st.path))
        now = time.time()
        from mentis.execution import RunResult
        return RunResult(run_id=spec.run_id, backend=spec.backend, started=True,
                         stop_reason="end_turn", text="done", started_at=now,
                         finished_at=now)

    svc.execution.script = {b["id"]: perform for b in _catalogue()}
    monkeypatch.setattr(web, "dispatch_soon", lambda s, **kw: D.dispatch(st, **kw))
    return {"grants": grants, "ex": svc.execution}


@pytest.fixture()
def carrying(world, real):
    """A real run of the steward carrying an owner's request; @Bob to hand to."""
    cv = world["cv"]
    cid = a_conversation(world)
    got = say(world, cid, "do the work", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "carry it"}])
    assert "error" not in got, got
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    return {"cid": cid, "grant": real["grants"][-1], "bob": bob,
            "parent": got["expectations"][0]}


def _delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def _run(world, out):
    spec = out["dispatch"]
    return D.dispatch(world["state"], conversation=out["conversation"],
                      turn=spec.get("turn") or out["turn"],
                      participant=spec["participant"], work=spec["work"],
                      persona=spec.get("persona"), runtime=spec.get("runtime"),
                      model=spec.get("model"), effort=spec.get("effort"),
                      requires=spec.get("requires") or (),
                      expectation=out["expectation"])


def _latest_start(cv, expectation):
    got = [a for a in cv.history(caused_by=expectation)
           if a["act"] == "execution-started"]
    assert got, "the run did not start"
    return max(got, key=lambda a: a["at"])


def _reply_of(cv, expectation):
    start = _latest_start(cv, expectation)["id"]
    return next(a["turn"] for a in cv.history(caused_by=start)
                if a["act"] == "result-returned")


def _routing(cv, expectation):
    return (cv._act(expectation)["detail"] or {}).get("routing")


def _complex_work_returned(world, carrying):
    """The first round: complex work delegated to @Bob, run, and returned."""
    cv = world["cv"]
    first = _delegate(world, carrying["grant"], participant=carrying["bob"],
                      work="build it", difficulty="complex", requires=[])
    _run(world, first)
    return first["expectation"], _reply_of(cv, first["expectation"])


# -- F2: inheritance -----------------------------------------------------------

def test_a_correction_naming_a_runtime_keeps_the_tier_it_continues(world, carrying):
    cv = world["cv"]
    first, reply = _complex_work_returned(world, carrying)
    fix = _delegate(world, carrying["grant"], participant=carrying["bob"],
                    work="correct what review found", runtime="claude",
                    references=[reply], requires=[])
    routed = _routing(cv, fix["expectation"])
    assert routed["required_tier"] == "frontier"
    assert routed["tier_sources"] == ["inherited"]
    assert routed["inherited_from"] == [first]
    assert "difficulty" not in routed
    assert not any("default tier" in w for w in fix.get("warnings") or ())
    # and it survives the named runtime: claude's frontier model is filled
    _run(world, fix)
    start = _latest_start(cv, fix["expectation"])
    d = start["detail"]
    assert start["runtime"] == "claude"
    assert d["selected_model"] == "opus" and d["selected_effort"] == "high"
    assert d["routing"]["tier_sources"] == ["inherited"]


def test_a_lower_stated_difficulty_is_raised_to_what_is_inherited(world, carrying):
    # CONTRACT SECTION 2 (lineage): work that continues another keeps what that
    # work needed; a lower stated value is RAISED and the delegator warned.
    # (Before requirements, a stated difficulty beat what would be inherited.)
    cv = world["cv"]
    first, reply = _complex_work_returned(world, carrying)
    fix = _delegate(world, carrying["grant"], participant=carrying["bob"],
                    work="a small fix", runtime="claude", difficulty="routine",
                    references=[reply], requires=[])
    routed = _routing(cv, fix["expectation"])
    assert routed["required_tier"] == "frontier"
    assert routed["inherited_tier"] == "frontier"
    assert routed["inherited_from"] == [first]
    req = routed["requirements"]
    assert req["reasoning"]["value"] == "deep"
    assert req["reasoning"]["raised_from"] == {"value": "substantial",
                                               "source": "compat"}
    assert any("raised" in w for w in fix.get("warnings") or ())
    # `new` breaks the lineage: the stated difficulty is what it needs
    fresh = _delegate(world, carrying["grant"], participant=carrying["bob"],
                      work="a small fix", runtime="claude", difficulty="routine",
                      relation="new", references=[reply], requires=[])
    routed = _routing(cv, fresh["expectation"])
    assert routed["required_tier"] == "coding"
    assert routed["tier_sources"] == ["difficulty"]
    assert "inherited_tier" not in routed and "inherited_from" not in routed
    _run(world, fresh)
    assert _latest_start(cv, fresh["expectation"])["detail"]["selected_model"] == "sonnet"


def test_an_earlier_delegation_of_the_same_activity_is_inherited(world, runs):
    cv = world["cv"]
    builder = cv.define_persona("Builder", "Build the part you are given.")
    wf = _workflow(world, persona=builder,
                   disciplines=[_discipline(world, "Targeted tests")])
    cid = a_conversation(world)
    out = say(world, cid, "change the software", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "carry it",
                         "governed": [wf]}])
    assert "error" not in out, out
    grant = runs[-1]
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    first = _delegate(world, grant, participant=bob, work="build part one",
                      activity=f"{wf}#implement", difficulty="architecture",
                      requires=[])
    again = _delegate(world, grant, participant=bob, work="fix part one",
                      activity=f"{wf}#implement", requires=[])
    routed = _routing(cv, again["expectation"])
    assert routed["required_tier"] == "frontier"
    assert routed["tier_sources"] == ["inherited"]
    assert routed["inherited_from"] == [first["expectation"]]
    # another Participant, or another activity, inherits nothing
    eve = cv.create_participant("@Eve")
    cv.join(eve, cid, attributed_to=world["who"]["@brian"])
    other = _delegate(world, grant, participant=eve, work="fix part one",
                      activity=f"{wf}#implement", requires=[])
    assert _routing(cv, other["expectation"]) is None
    step = _delegate(world, grant, participant=bob, work="merge it",
                     activity=f"{wf}#integrate", requires=[])
    assert _routing(cv, step["expectation"]) is None


# -- F2: the default tier is said ----------------------------------------------

def test_nothing_to_inherit_warns_of_the_default_tier_and_changes_nothing(
        world, carrying):
    cv = world["cv"]
    out = _delegate(world, carrying["grant"], participant=carrying["bob"],
                    work="something", runtime="claude", requires=[])
    assert _routing(cv, out["expectation"]) is None
    [said] = [w for w in out.get("warnings") or () if "default tier" in w]
    assert said == (
        'no difficulty was stated and none could be inherited from the work '
        'this continues, so the default tier "coding" applies; on claude that '
        'is sonnet at medium. State `solution` (is the answer known? a small '
        'change whose answer is not known is open) and `reasoning` (how much '
        'thinking it needs, not its size) if the work needs more')
    _run(world, out)
    d = _latest_start(cv, out["expectation"])["detail"]
    assert d["routing"]["tier_sources"] == ["default"]
    assert d["selected_model"] == "sonnet"
    # with no runtime named, the model is not knowable yet
    unnamed = _delegate(world, carrying["grant"], participant=carrying["bob"],
                        work="something else", requires=[])
    assert any(w.endswith('so the default tier "coding" applies. State '
                          '`solution` (is the answer known? a small change '
                          'whose answer is not known is open) and `reasoning` '
                          '(how much thinking it needs, not its size) if the '
                          'work needs more') for w in unnamed.get("warnings") or ()), \
        unnamed.get("warnings")
    # a stated difficulty is not warned about
    stated = _delegate(world, carrying["grant"], participant=carrying["bob"],
                       work="x", difficulty="bounded", requires=[])
    assert not any("default tier" in w for w in stated.get("warnings") or ())


# -- F6: a named runtime lacking a requirement ---------------------------------

def _written(cv, parent):
    return [a["id"] for a in cv.history(caused_by=parent)
            if a["act"] in ("work-delegated", "expectation-recorded")]


def test_a_named_runtime_lacking_a_requirement_is_refused(world, carrying):
    from mentis.worker import NotPermitted
    cv = world["cv"]
    before = _written(cv, carrying["parent"])
    with pytest.raises(NotPermitted) as got:
        _delegate(world, carrying["grant"], participant=carrying["bob"],
                  work="integrate it and check it in the browser",
                  runtime="codex",
                  requires=["call_mentis_tools", "build_ui", "drive_browser"])
    assert str(got.value) == (
        "the named runtime codex cannot be given this work: it lacks "
        "['drive_browser'] (MARS reports codex lacks drive_browser: its "
        "sandbox denied Playwright (EACCES)). Runtimes eligible for "
        "['build_ui', 'call_mentis_tools', 'drive_browser']: antigravity, "
        "claude. Name one of them, or name no runtime and let selection "
        "choose; nothing was recorded")
    assert _written(cv, carrying["parent"]) == before
    assert not [e for e in cv.history(caused_by=carrying["parent"])
                if e["act"] == "expectation-recorded"]


def test_a_named_runtime_with_only_a_capacity_problem_is_warned_and_recorded(
        world, carrying, monkeypatch):
    import mentis.web.quota as Q
    cv = world["cv"]
    t = time.time()
    monkeypatch.setattr(Q, "quota_holds", lambda cv, now=None: {
        "codex": {"until": t + 3600, "why": "codex hit its quota; held",
                  "model": None, "since": t, "basis": "opr-x"}})
    out = _delegate(world, carrying["grant"], participant=carrying["bob"],
                    work="build it", runtime="codex", difficulty="complex",
                    requires=["call_mentis_tools"])
    assert cv._act(out["expectation"])["detail"]["constraints"]["runtime"] == "codex"
    assert any("codex" in w and "cannot take this work now" in w
               and "kept because it was named" in w
               for w in out.get("warnings") or ()), out.get("warnings")


def test_the_capabilities_tool_says_which_runtime_has_which(world, carrying):
    from mentis.web import _surface
    from mentis.worker import _result
    got = _result(_surface(world["state"]), "capabilities", {},
                  grant=carrying["grant"])
    assert "drive_browser" in got["capabilities"]
    rows = got["runtimes"]
    assert set(rows) == {"claude", "codex", "antigravity"}
    assert {"build_ui", "drive_browser", "call_mentis_tools"} <= set(
        rows["claude"]["has"])
    assert rows["codex"]["lacks"] == ["drive_browser"]
    assert "drive_browser" in rows["antigravity"]["unknown"]
    assert all(r["available"] for r in rows.values())
    assert "lacks" not in rows["claude"]


# -- final review corrections ---------------------------------------------------

def test_the_same_key_of_another_workflow_is_not_inherited(world, runs):
    """Finding F: `implement` of another Workflow is other work."""
    cv = world["cv"]
    builder = cv.define_persona("Builder", "Build the part you are given.")
    tests_d = _discipline(world, "Targeted tests")
    wf_a = _workflow(world, persona=builder, disciplines=[tests_d])
    wf_b = _workflow(world, persona=builder, disciplines=[tests_d])
    cid = a_conversation(world)
    out = say(world, cid, "change the software", action="ask-participant",
              dispatch=[{"participant": world["steward"], "work": "carry it",
                         "governed": [wf_a, wf_b]}])
    assert "error" not in out, out
    grant = runs[-1]
    assert {wf_a, wf_b} <= set(grant["delivered"])
    bob = cv.create_participant("@Bob")
    cv.join(bob, cid, attributed_to=world["who"]["@brian"])
    first = _delegate(world, grant, participant=bob, work="build part one",
                      activity=f"{wf_a}#implement", difficulty="architecture",
                      requires=[])
    other = _delegate(world, grant, participant=bob, work="build part two",
                      activity=f"{wf_b}#implement", requires=[])
    assert _routing(cv, other["expectation"]) is None
    same = _delegate(world, grant, participant=bob, work="fix part one",
                     activity=f"{wf_a}#implement", requires=[])
    assert _routing(cv, same["expectation"])["inherited_from"] == [
        first["expectation"]]


def test_unconfirmed_is_not_said_as_lacking(world, carrying, real):
    """Finding G: `lacks` only for what MARS reports missing; an unknown that
    work may not be tried without is said as not confirmed."""
    from mentis.worker import NotPermitted
    cat = _catalogue()
    cat[0]["capabilities"] = [*cat[0]["capabilities"], "reach_local_models"]
    real["ex"]._backends = cat
    with pytest.raises(NotPermitted) as got:
        _delegate(world, carrying["grant"], participant=carrying["bob"],
                  work="local only", runtime="codex",
                  requires=["reach_local_models"])
    assert str(got.value) == (
        "the named runtime codex cannot be given this work: it is not "
        "confirmed to have ['reach_local_models'] (MARS does not say whether "
        "codex has reach_local_models). Runtimes eligible for "
        "['reach_local_models']: claude. Name one of them, or name no runtime "
        "and let selection choose; nothing was recorded")
    with pytest.raises(NotPermitted) as both:
        _delegate(world, carrying["grant"], participant=carrying["bob"],
                  work="local browser work", runtime="codex",
                  requires=["drive_browser", "reach_local_models"])
    assert str(both.value) == (
        "the named runtime codex cannot be given this work: it lacks "
        "['drive_browser'] (MARS reports codex lacks drive_browser: its "
        "sandbox denied Playwright (EACCES)); it is not confirmed to have "
        "['reach_local_models'] (MARS does not say whether codex has "
        "reach_local_models). Runtimes eligible for ['drive_browser', "
        "'reach_local_models']: claude. Name one of them, or name no runtime "
        "and let selection choose; nothing was recorded")
