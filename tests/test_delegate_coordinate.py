"""Delegating the work a run carries is every run's; coordinating more is not.

OWNER RULINGS: ent-fb17dc421a42 ("Fix F-1 and narrow F-2") on the review of
the #401 candidate; ent-94edb8bc6342 (`coordinate` is the authority,
`delegate` the capability); and the F-2 revision that followed it:

  "A run may hand on the work it is already carrying and may supply the child
  configuration needed for that delegation, including participant,
  runtime/model/effort, requires, and an appropriate worktree/repository
  choice, subject to the parent's existing authority and normal capability
  constraints. This does not grant authority to pick up or organize
  unrelated/unassigned work. coordinate remains required for F-1 ... Do not
  infer coordinate from the Caretaker identity."

So the line this file holds is between DELEGATING OWNED WORK -- a child of the
request this run carries, configured as that work needs -- and COORDINATING
OTHER WORK: picking up discovered work nobody carries (F-1). The repository
half of the line is in tests/test_repository_worktrees.py, which has a real
repository to cut from.

`coordinate` is recorded on the request by whoever made it; a grant recorded
before it existed lists `delegate`, and is read as `coordinate` in exactly one
place, `authority_of`. `worker.may_coordinate` is the one predicate, and no
Participant -- Caretaker included -- implies it. Every grant a run acts under
here is minted by the real dispatch path (`runs`), never written by hand.
"""

from __future__ import annotations

import pytest

from tests._loop import a_conversation, say, world  # noqa: F401
from tests._loop import _answer, _continue, runs  # noqa: F401


def test_only_coordinate_on_the_grant_is_authority_to_coordinate():
    """Not the scope, not `permitted`, not the `delegate` capability."""
    from mentis.worker import AUTHORITY, COORDINATE, ORGANISES, may_coordinate
    assert may_coordinate({"scope": "organising", "operations": ["coordinate"]})
    assert may_coordinate({"scope": "worker", "operations": list(AUTHORITY)})
    for grant in ({"scope": "organising", "operations": ["respond"]},
                  {"scope": "organising", "operations": ["open_topic"]},
                  {"scope": "organising", "operations": list(ORGANISES)},
                  {"scope": "organising", "operations": ["delegate"]},
                  {"scope": "intake", "operations": None},
                  {"scope": "intake"},
                  {"scope": "worker", "operations": None},
                  {"scope": "transient-read", "operations": ()},
                  {}, None):
        assert not may_coordinate(grant), grant
    # `coordinate` is authority, not an operation anybody is shown or calls
    from mentis.worker import OPERATIONS, permitted
    assert COORDINATE not in OPERATIONS and COORDINATE not in ORGANISES
    assert COORDINATE not in permitted("organising", [COORDINATE])
    assert "delegate" not in AUTHORITY and "delegate" not in ORGANISES


# -- grants, minted for real ---------------------------------------------------

def _dispatched(world, runs, cid, who=None, **spec):
    """`who` (the steward unless said) asked by the owner, with `spec` on the
    dispatch: the request, and the grant its run was actually minted."""
    out = say(world, cid, "do the work", action="ask-participant",
              dispatch=[{"participant": who or world["steward"],
                         "work": "the work", **spec}])
    assert "error" not in out, out
    return out["expectations"][0], runs[-1]


def _legacy(world, runs, cid):
    """Work whose grant was recorded before `coordinate` existed, as an old
    grant was: the requester's `authority-granted` act listing `delegate`,
    written directly, then run again under today's code."""
    from mentis.web import dispatch as D
    cv = world["cv"]
    exp, _ = _dispatched(world, runs, cid)
    asked = cv._act(exp)
    cv._c.record_operational(
        actor=asked["actor"], act="authority-granted",
        conversation=asked["conversation"], turn=asked["turn"],
        because="the author said what this work may organise",
        caused_by=exp, about=[],
        detail={"operations": ["delegate"], "source": "explicit",
                "origin": None})
    D.dispatch(world["state"], conversation=cid, turn=asked["turn"],
               participant=world["steward"], work="the work", expectation=exp)
    return exp, runs[-1]


#: Work that may not be coordinated, every way: authority narrowed to
#: organising operations without `coordinate` -- one, or all of them --
#: ordinary work, which holds the `delegate` capability and nothing else, and
#: @Caretaker asked by name, whose identity confers nothing.
NOT_COORDINATING = {"respond-only": {"authority": ["respond"]},
                    "caretaker-by-name": {"who": "@Caretaker"},
                    "open_topic-only": {"authority": ["open_topic"]},
                    "every-organising-operation": {
                        "authority": ["open_topic", "open_conversation",
                                      "summon_participant",
                                      "propose_material", "respond"]},
                    "delegate-capability-only": {}}


#: Work that may be coordinated: the owner's gesture, an explicit grant naming
#: `coordinate`, and a grant recorded before `coordinate` existed.
COORDINATING = ("gesture", "explicit", "legacy-delegate-record")


def _run_of(world, runs, case):
    """A real run of each kind, checked to be on the side of the line its
    case says, and what it carries."""
    from mentis.worker import may_coordinate, permitted
    cid = a_conversation(world)
    if case in NOT_COORDINATING:
        spec = dict(NOT_COORDINATING[case])
        if "who" in spec:
            spec["who"] = world["cv"].create_participant(spec["who"])
        exp, grant = _dispatched(world, runs, cid, **spec)
    elif case == "gesture":
        exp, grant = _dispatched(world, runs, cid, coordinate=True)
    elif case == "explicit":
        exp, grant = _dispatched(world, runs, cid, authority=["coordinate"])
    else:
        exp, grant = _legacy(world, runs, cid)
    assert grant["expectation"] == exp
    # every run holds the capability to hand work on ...
    assert "delegate" in permitted(grant["scope"], grant["operations"])
    # ... and only these are authorised to coordinate
    assert may_coordinate(grant) == (case in COORDINATING)
    return {"cid": cid, "grant": grant, "case": case}


@pytest.fixture(params=sorted(NOT_COORDINATING))
def plain(request, world, runs):
    return _run_of(world, runs, request.param)


@pytest.fixture(params=COORDINATING)
def coordinator(request, world, runs):
    return _run_of(world, runs, request.param)


@pytest.fixture(params=sorted(NOT_COORDINATING) + list(COORDINATING))
def any_run(request, world, runs):
    """Each kind of run, from either side of the line."""
    return _run_of(world, runs, request.param)


def _present(world, cid, alias):
    """A Participant the owner has brought into the Conversation."""
    cv = world["cv"]
    pid = cv.create_participant(alias)
    cv.join(pid, cid, attributed_to=world["who"]["@brian"])
    return pid


def _delegate(world, grant, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "delegate", args, grant)


def _discovered(world, grant):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), "record_discovered_work",
                    {"work": "found on the way", "because": "not this work"},
                    grant)["expectation"]


def _children(cv, parent):
    return [a for a in cv.history(caused_by=parent)
            if a["act"] == "expectation-recorded"]


NOT_GRANTED = "not granted `coordinate`"


# -- how authority is recorded and read ----------------------------------------

def test_the_gesture_records_coordinate_and_never_delegate(world, runs):
    from mentis.worker import AUTHORITY
    cv = world["cv"]
    exp, grant = _dispatched(world, runs, a_conversation(world),
                             coordinate=True)
    recorded = [a for a in cv.history(caused_by=exp)
                if a["act"] == "authority-granted"]
    assert len(recorded) == 1
    assert recorded[0]["detail"]["operations"] == sorted(AUTHORITY)
    assert "coordinate" in recorded[0]["detail"]["operations"]
    assert "delegate" not in recorded[0]["detail"]["operations"]
    assert "coordinate" in grant["operations"]


def test_an_unaddressed_request_records_coordinate_and_never_delegate(world,
                                                                     runs):
    cv = world["cv"]
    out = say(world, a_conversation(world), "somebody coordinate this",
              action="ask-mentis")
    recorded = [a for a in cv.history(caused_by=out["expectation"])
                if a["act"] == "authority-granted"][0]["detail"]["operations"]
    assert "coordinate" in recorded and "delegate" not in recorded
    from mentis.worker import may_coordinate
    assert may_coordinate(runs[-1])


def test_naming_delegate_as_authority_is_refused_and_says_coordinate(world):
    cv = world["cv"]
    cid = a_conversation(world)
    out = say(world, cid, "x", action="ask-participant",
              dispatch=[{"participant": world["who"]["@Ada"], "work": "x",
                         "authority": ["delegate"]}])
    assert "error" in out and "'coordinate'" in out["error"]
    assert "not authority" in out["error"]
    assert cv.turns(cid) == [], "a refused grant wrote a Turn"


def test_a_new_grant_never_records_delegate(world):
    cv = world["cv"]
    out = say(world, a_conversation(world), "x", action="ask-participant",
              dispatch=[{"participant": world["who"]["@Ada"], "work": "x"}])
    with pytest.raises(ValueError, match="coordinate"):
        cv.grant_authority(out["expectations"][0], ["delegate", "respond"],
                           by=world["who"]["@brian"], source="explicit",
                           because="as it used to be written")
    assert cv.authority_of(out["expectations"][0])["act"] is None


def test_a_legacy_delegate_grant_reads_as_coordinate_and_is_not_rewritten(
        world, runs):
    cv = world["cv"]
    exp, grant = _legacy(world, runs, a_conversation(world))
    got = cv.authority_of(exp)
    assert got["operations"] == ["coordinate"]
    assert got["read_as"] == {"delegate": "coordinate"}
    # the record is what it was
    raw = [a for a in cv.history(caused_by=exp)
           if a["act"] == "authority-granted"]
    assert [a["detail"]["operations"] for a in raw] == [["delegate"]]
    # and the run is granted what it is read as
    assert grant["operations"] == ["coordinate"]


def test_continuing_legacy_work_records_coordinate_not_delegate(world, runs):
    """What continuation inherits is what `authority_of` reads, so the new
    grant it writes is a new grant, and records `coordinate`."""
    cv, steward = world["cv"], world["steward"]
    cid = a_conversation(world)
    exp, _ = _legacy(world, runs, cid)
    result = _answer(world, cid, cv._act(exp)["turn"], steward)
    again = _continue(world, cid, result, steward)["expectations"][0]
    recorded = [a for a in cv.history(caused_by=again)
                if a["act"] == "authority-granted"]
    assert [a["detail"]["operations"] for a in recorded] == [["coordinate"]]
    assert recorded[0]["detail"]["source"] == "continuation"
    assert "read_as" not in cv.authority_of(again)


# -- F-1: picking up discovered work -------------------------------------------

def test_without_coordinate_discovered_work_is_not_picked_up(world, plain):
    from mentis.worker import NotPermitted
    cv = world["cv"]
    bob = _present(world, plain["cid"], "@Bob")
    found = _discovered(world, plain["grant"])
    with pytest.raises(NotPermitted, match=NOT_GRANTED):
        _delegate(world, plain["grant"], participant=bob, work="take it",
                  expectation=found)
    assert cv.expectation_state(found)["unassigned"] is True


def test_with_coordinate_discovered_work_is_picked_up(world, coordinator):
    from mentis.web import _surface
    from mentis.worker import NotPermitted
    from tests.gravity_choice import owner_chooses
    cv = world["cv"]
    bob = _present(world, coordinator["cid"], "@Bob")
    found = _discovered(world, coordinator["grant"])
    # `coordinate` is necessary, not sufficient: the owner chooses first
    with pytest.raises(NotPermitted, match="not chosen to pursue"):
        _delegate(world, coordinator["grant"], participant=bob,
                  work="take it", expectation=found)
    owner_chooses(_surface(world["state"]), coordinator["grant"], found)
    out = _delegate(world, coordinator["grant"], participant=bob,
                    work="take it", expectation=found)
    assert out["picked_up"] is True and out["expectation"] == found
    assert cv.expectation_state(found)["expected_of"] == bob


# -- delegating owned work: every run, configured as the work needs ------------

@pytest.mark.parametrize("field,value", [("runtime", "codex"),
                                         ("model", "m-chosen"),
                                         ("effort", "high")])
def test_owned_work_is_handed_on_with_runtime_model_or_effort(
        world, any_run, field, value):
    cv = world["cv"]
    bob = _present(world, any_run["cid"], "@Bob")
    out = _delegate(world, any_run["grant"], participant=bob, work="x",
                    **{field: value})
    child = cv._act(out["expectation"])
    assert child["caused_by"] == any_run["grant"]["expectation"]
    assert child["detail"]["constraints"][field] == value
    assert out["dispatch"][field] == value


def test_owned_work_is_handed_on_with_the_turn_that_decided_it(world,
                                                               any_run):
    cv = world["cv"]
    bob = _present(world, any_run["cid"], "@Bob")
    basis = cv._act(any_run["grant"]["expectation"])["turn"]
    out = _delegate(world, any_run["grant"], participant=bob, work="x",
                    runtime="codex", constraint_basis=basis)
    got = cv._act(out["expectation"])["detail"]["constraints"]
    assert got["basis"] == basis
    assert got["supplied_by"] == any_run["grant"]["participant"]


def test_owned_work_is_handed_on_with_what_it_requires(world, any_run):
    from mentis.api.types import Capability
    cv = world["cv"]
    need = next(iter(Capability)).value
    bob = _present(world, any_run["cid"], "@Bob")
    out = _delegate(world, any_run["grant"], participant=bob, work="x",
                    requires=[need])
    assert out["dispatch"]["requires"] == [need]
    assert cv._act(out["expectation"])["detail"]["requires"] == [need]


def test_owned_work_brings_in_whoever_it_is_handed_to(world, any_run):
    """#401's own case: handing work to somebody brings them in."""
    cv = world["cv"]
    stranger = cv.create_participant("@Stranger")
    out = _delegate(world, any_run["grant"], participant=stranger, work="x")
    assert stranger in cv.participants(any_run["cid"])
    assert cv.expectation_state(out["expectation"])["expected_of"] == stranger


def test_owned_work_is_handed_on_plain_too(world, any_run):
    """No configuration: the child runs on its Participant's own default."""
    cv = world["cv"]
    bob = _present(world, any_run["cid"], "@Bob")
    cv.declare_runtime_default(bob, "codex", by=world["who"]["@brian"])
    out = _delegate(world, any_run["grant"], participant=bob,
                    work="the part that is theirs", return_to_me=True)
    child = cv._act(out["expectation"])
    assert child["caused_by"] == any_run["grant"]["expectation"]
    assert child["detail"]["constraints"]["runtime"] == "codex"
    assert child["detail"]["constraints"]["source"] == "participant-default"


# -- ... still subject to the ordinary checks, whoever hands it on -------------

def test_a_requirement_nothing_can_declare_is_refused(world, any_run):
    from mentis.worker import NotPermitted
    bob = _present(world, any_run["cid"], "@Bob")
    with pytest.raises(NotPermitted, match="no capability"):
        _delegate(world, any_run["grant"], participant=bob, work="x",
                  requires=["teleportation"])


def test_a_basis_that_is_not_the_requesters_turn_is_refused(world, any_run):
    from mentis.worker import NotPermitted
    from mentis.worker import text_part
    cv = world["cv"]
    bob = _present(world, any_run["cid"], "@Bob")
    theirs = cv.say(any_run["cid"], bob, [text_part("use codex")])
    with pytest.raises(NotPermitted, match="not a Turn by the person who"):
        _delegate(world, any_run["grant"], participant=bob, work="x",
                  runtime="codex", constraint_basis=theirs)


def test_the_same_repository_needs_one_declared(world, any_run):
    """`repository: true` is the directory this work declared (headless: a
    directory, no worktree); with none, it is refused for that and never for
    want of `coordinate`."""
    from mentis.worker import NotPermitted
    bob = _present(world, any_run["cid"], "@Bob")
    with pytest.raises(NotPermitted) as refused:
        _delegate(world, any_run["grant"], participant=bob, work="x",
                  repository=True)
    assert "declares no repository directory" in str(refused.value)
    assert "coordinate" not in str(refused.value)


# -- no identity is authority ----------------------------------------------------

def test_caretaker_asked_by_name_delegates_its_work_and_coordinates_nothing(
        world, runs):
    """UI/UX #380-#383, from the record's side: @Caretaker, asked by name and
    granted nothing, hands its work to somebody new on a named runtime -- and
    being Caretaker does not let it pick up work it does not carry."""
    from mentis.worker import NotPermitted, may_coordinate
    cv = world["cv"]
    cid = a_conversation(world, "Mentis UI/UX")
    caretaker = cv.create_participant("@Caretaker")
    codex = cv.create_participant("@Quill")
    exp, grant = _dispatched(world, runs, cid, who=caretaker)
    assert grant["participant"] == caretaker
    assert cv.authority_of(exp)["act"] is None and not may_coordinate(grant)

    request_turn = cv._act(exp)["turn"]
    out = _delegate(world, grant, participant=codex, work="the codex mockup",
                    runtime="codex", constraint_basis=request_turn,
                    return_to_me=True)
    child = cv._act(out["expectation"])["detail"]
    assert codex in cv.participants(cid)
    assert child["constraints"]["runtime"] == "codex"
    assert child["constraints"]["basis"] == request_turn

    found = _discovered(world, grant)
    with pytest.raises(NotPermitted, match=NOT_GRANTED):
        _delegate(world, grant, participant=codex, work="take it",
                  expectation=found)
    assert cv.expectation_state(found)["unassigned"] is True


# -- what the repository correction leaves alone ---------------------------------

def test_scratch_is_unchanged_and_hands_nothing_on():
    """A Scratch answer reads, quotes held artifacts, and leaves no mark: no
    `delegate`, with or without a repository, and no authority to coordinate.
    The door refusing it is tests/test_quick_ask_reads.py."""
    from mentis.worker import (READS, SOURCE_READS, TRANSIENT_SCOPE,
                               may_coordinate, permitted)
    assert permitted(TRANSIENT_SCOPE) == READS + SOURCE_READS + (
        "read_artifact",)
    assert "delegate" not in permitted(TRANSIENT_SCOPE)
    assert not may_coordinate({"scope": TRANSIENT_SCOPE, "operations": ()})
