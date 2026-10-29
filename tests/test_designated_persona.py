"""A directly addressed Participant works as its designated Persona.

OWNER RULING 2026-10-29: "Directly addressing a participant should
automatically use its designated Persona unless I explicitly select another.
This applies to all participants, not just @Caretaker."

What holds, through the real post door, the real dispatch path and the real
HTTP routes:

  * a designation is an established `designated-as` link, Participant ->
    Persona; a new one supersedes the old; null ends it; writing refuses a
    non-Participant, a non-Persona and a Persona that does not stand;
  * `persona` absent or null in a dispatch spec -> the designated Persona;
    a Persona id -> that Persona; "none" -> explicitly none; resolved once in
    `owe` and recorded on the request (`persona`, `persona_from`);
  * with no designation, the Participant's own intake designation applies --
    only for the intake carrier;
  * several standing, or a Persona that no longer stands -> no Persona, with
    the reason recorded;
  * superseding the Persona carries the designation forward;
  * the POST route is the owner's; `/api/who` and `/api/participants` show it;
  * a resumed carrier keeps the Persona (`started_persona`);
  * unaddressed intake is unchanged;
  * export and import refuse the link; a designation write moves the context
    cache's governance domain.
"""

from __future__ import annotations

import pytest

import mentis.api as api
from mentis.conversation import DESIGNATED_AS
from tests._loop import a_conversation, get, post, say, world  # noqa: F401
from tests.test_delegate_activity import _dispatch_sent, door_runs  # noqa: F401


# -- material ------------------------------------------------------------------

def _persona(world, name, behaviour="behave"):
    """An ESTABLISHED Persona, which is what a designation may name."""
    return world["cv"].corpus.create_and_establish(
        kind="persona", body={"name": name, "behaviour": behaviour,
                              "about": name},
        attributed_to=world["who"]["@brian"])


def _owner(world):
    return world["who"]["@brian"]


def _bob(world, cid=None):
    cv = world["cv"]
    bob = cv.create_participant("@Bob")
    if cid:
        cv.join(bob, cid, attributed_to=_owner(world))
    return bob


def _ask(world, cid, participant, **spec):
    out = say(world, cid, "please do this", action="ask-participant",
              dispatch=[{"participant": participant, "work": "do it", **spec}])
    assert "error" not in out, out
    exp = out["expectations"][0]
    sent = next(s for s in world["sent"] if s.get("expectation") == exp)
    return exp, sent, world["cv"]._act(exp)["detail"]


def _end_entry(world, eid):
    """End an entry with a deletion record, as the delete door does."""
    corpus = world["cv"].corpus
    rec = corpus.write(kind="deletion", body={"reason": "gone"},
                       attributed_to=_owner(world))
    corpus.write(body={"reason": "gone"}, attributed_to=_owner(world),
                 link={"from": rec, "to": eid,
                       "relation": corpus.superseding_relation()})
    assert not corpus.stands(eid)["stands"]


# -- the record -----------------------------------------------------------------

def test_a_designation_is_an_established_link_and_a_new_one_supersedes(world):
    cv = world["cv"]
    bob = _bob(world)
    p1, p2 = _persona(world, "Builder"), _persona(world, "Reviewer")
    first = cv.designate_persona(bob, p1, by=_owner(world), because="builds")
    got = cv.corpus.read([first])[0]
    assert got["link"] == {**got["link"], "from": bob, "to": p1,
                           "relation": DESIGNATED_AS}
    assert cv.corpus.stands(first)["stands"]
    assert cv.designated_persona(bob)["persona"] == p1
    second = cv.designate_persona(bob, p2, by=_owner(world))
    assert not cv.corpus.stands(first)["stands"]
    now = cv.designated_persona(bob)
    assert now == {**now, "resolved": True, "persona": p2,
                   "source": "designation", "designation": second}
    ended = cv.end_designation(bob, by=_owner(world), because="no longer")
    assert [e["ends"] for e in ended] == [second]
    assert cv.designated_persona(bob)["resolved"] is False
    assert len(cv.persona_designations(bob)) == 2      # history is kept


def test_writing_refuses_what_could_not_be_a_designation(world):
    cv = world["cv"]
    bob = _bob(world)
    p = _persona(world, "Builder")
    ended = _persona(world, "Ended")
    _end_entry(world, ended)
    with pytest.raises(ValueError):
        cv.designate_persona(p, p, by=_owner(world))          # not a Participant
    with pytest.raises(ValueError):
        cv.designate_persona(bob, bob, by=_owner(world))      # not a Persona
    with pytest.raises(ValueError):
        cv.designate_persona(bob, ended, by=_owner(world))
    assert cv.persona_designations(bob) == []


# -- addressing -------------------------------------------------------------------

@pytest.mark.parametrize("spec", [{}, {"persona": None}],
                         ids=["absent", "null"])
def test_nothing_chosen_uses_the_designated_persona(world, spec):
    cv = world["cv"]
    cid = a_conversation(world)
    bob = _bob(world, cid)
    p = _persona(world, "Builder")
    cv.designate_persona(bob, p, by=_owner(world))
    exp, sent, detail = _ask(world, cid, bob, **spec)
    assert sent["persona"] == p
    assert detail["persona"] == p and detail["persona_from"] == "designation"


def test_an_explicitly_chosen_persona_wins(world):
    cv = world["cv"]
    cid = a_conversation(world)
    bob = _bob(world, cid)
    designated, chosen = _persona(world, "Builder"), _persona(world, "Reviewer")
    cv.designate_persona(bob, designated, by=_owner(world))
    _, sent, detail = _ask(world, cid, bob, persona=chosen)
    assert sent["persona"] == chosen
    assert detail["persona"] == chosen and detail["persona_from"] == "chosen"


def test_none_is_explicitly_no_persona(world):
    cv = world["cv"]
    cid = a_conversation(world)
    bob = _bob(world, cid)
    cv.designate_persona(bob, _persona(world, "Builder"), by=_owner(world))
    _, sent, detail = _ask(world, cid, bob, persona="none")
    assert sent["persona"] is None
    assert detail["persona"] is None and detail["persona_from"] == "none-chosen"


def test_the_intake_designation_applies_to_the_intake_carrier_only(world):
    cv = world["cv"]
    assert cv.intake_carrier()["participant"] == world["steward"]
    cid = a_conversation(world)
    bob = _bob(world, cid)
    _, sent, detail = _ask(world, cid, world["steward"])
    assert sent["persona"] == world["persona"]
    assert detail["persona_from"] == "intake"
    # somebody else is not covered by the steward's intake designation
    _, sent, detail = _ask(world, cid, bob)
    assert sent["persona"] is None
    assert detail["persona_from"] == "unresolved" and detail["persona_why"]
    # and a designation of its own wins over the intake fallback
    own = _persona(world, "Steward, addressed")
    cv.designate_persona(world["steward"], own, by=_owner(world))
    _, sent, detail = _ask(world, cid, world["steward"])
    assert sent["persona"] == own and detail["persona_from"] == "designation"


def test_no_intake_fallback_when_intake_does_not_resolve(world):
    # the intake Persona ended: intake is unresolved, so the steward has no
    # designated Persona at all
    cv = world["cv"]
    _end_entry(world, world["persona"])
    assert not cv.intake_carrier()["resolved"]
    got = cv.designated_persona(world["steward"])
    assert got["resolved"] is False and got["persona"] is None


def test_several_standing_designations_are_unresolved(world):
    cv = world["cv"]
    cid = a_conversation(world)
    bob = _bob(world, cid)
    corpus = cv.corpus
    for name in ("Builder", "Reviewer"):
        # written by hand, as a record could hold them: never by recency
        link = corpus.write(body={"reason": "by hand"},
                            attributed_to=_owner(world),
                            link={"from": bob, "to": _persona(world, name),
                                  "relation": DESIGNATED_AS})
        corpus.establish(link, attributed_to=_owner(world))
    got = cv.designated_persona(bob)
    assert got["resolved"] is False and "several" in got["why"]
    _, sent, detail = _ask(world, cid, bob)
    assert sent["persona"] is None
    assert detail["persona_from"] == "unresolved"
    assert "several" in detail["persona_why"]


def test_a_designation_whose_persona_was_ended_is_unresolved(world):
    cv = world["cv"]
    cid = a_conversation(world)
    bob = _bob(world, cid)
    p = _persona(world, "Builder")
    cv.designate_persona(bob, p, by=_owner(world))
    _end_entry(world, p)
    got = cv.designated_persona(bob)
    assert got["resolved"] is False and got["persona"] is None
    _, sent, detail = _ask(world, cid, bob)
    assert sent["persona"] is None
    assert detail["persona_from"] == "unresolved" and detail["persona_why"]


def test_superseding_the_persona_carries_the_designation_forward(world):
    cv = world["cv"]
    bob = _bob(world)
    old, new = _persona(world, "Builder"), _persona(world, "Builder, v2")
    first = cv.designate_persona(bob, old, by=_owner(world))
    out = post(world, f"/api/entries/{old}/supersede",
               {"replacement": new, "attributed_to": _owner(world),
                "because": "revised"})
    assert "error" not in out, out
    assert not cv.corpus.stands(first)["stands"]
    got = cv.designated_persona(bob)
    assert got["resolved"] and got["persona"] == new
    assert got["designation"] != first


# -- HTTP -----------------------------------------------------------------------

def test_the_route_is_the_owners_and_null_ends_the_designation(world):
    cv = world["cv"]
    bob = _bob(world)
    p = _persona(world, "Builder")
    path = f"/api/participants/{bob}/designated-persona"
    refused = post(world, path, {"persona": p, "because": "try",
                                 "attributed_to": world["who"]["@Nadia"]})
    assert "error" in refused and "owner" in refused["error"]
    assert cv.persona_designations(bob) == []
    out = post(world, path, {"persona": p, "because": "builds things",
                             "attributed_to": _owner(world)})
    assert "error" not in out, out
    assert out["designated_persona"] == {"resolved": True, "persona": p,
                                         "name": "Builder",
                                         "source": "designation", "why": None}
    assert cv.corpus.read([out["designation"]])[0]["attributed_to"] == _owner(world)
    bad = post(world, path, {"persona": bob, "attributed_to": _owner(world)})
    assert "error" in bad
    ended = post(world, path, {"persona": None, "because": "not any more",
                               "attributed_to": _owner(world)})
    assert ended["ended"] and ended["designated_persona"]["resolved"] is False
    assert cv.designated_persona(bob)["resolved"] is False


def test_who_and_participants_show_the_designation(world):
    cv = world["cv"]
    bob = _bob(world)
    p = _persona(world, "Builder")
    assert get(world, f"/api/who/{bob}")["designated_persona"]["resolved"] is False
    cv.designate_persona(bob, p, by=_owner(world))
    who = get(world, f"/api/who/{bob}")["designated_persona"]
    assert who == {"resolved": True, "persona": p, "name": "Builder",
                   "source": "designation", "why": None}
    rows = {r["participant"]: r for r in
            get(world, "/api/participants")["participants"]}
    assert rows[bob]["designated_persona"]["persona"] == p
    # the intake carrier reads as "intake"
    steward = get(world, f"/api/who/{world['steward']}")["designated_persona"]
    assert steward["source"] == "intake" and steward["persona"] == world["persona"]


# -- what must not change ---------------------------------------------------------

def test_a_resumed_carrier_keeps_its_designated_persona(world, door_runs):
    cv = world["cv"]
    p = _persona(world, "Carrier")
    cv.designate_persona(world["steward"], p, by=_owner(world))
    bob = cv.create_participant("@Bob")
    cid = a_conversation(world)
    asked = say(world, cid, "change the software", action="ask-participant",
                dispatch=[{"participant": world["steward"], "persona": None,
                           "work": "carry it [[hand-on]]"}])
    parent = asked["expectations"][0]
    door_runs["calls"].append([{"participant": bob, "work": "build part one",
                                "return_to_me": True}])
    spec, _ = _dispatch_sent(world, parent)
    assert spec["persona"] == p
    child = next(a["id"] for a in cv.history(caused_by=parent)
                 if a["act"] == "expectation-recorded")
    _dispatch_sent(world, child)
    assert [a for a in cv.history(caused_by=parent) if a["act"] == "work-resumed"]
    spec, _ = _dispatch_sent(world, parent)
    assert spec["persona"] == p, "the resumed carrier lost its designated Persona"


def test_unaddressed_intake_is_unchanged(world):
    cv = world["cv"]
    # a designation of the carrier's own is NOT what intake wears
    cv.designate_persona(world["steward"], _persona(world, "Other"),
                         by=_owner(world))
    cid = a_conversation(world)
    out = say(world, cid, "somebody please", action="ask-mentis")
    assert out.get("assigned"), out
    exp = out["expectations"][0] if out.get("expectations") else out["expectation"]
    sent = next(s for s in world["sent"] if s.get("expectation") == exp)
    assert sent["persona"] == world["persona"]
    assert "persona_from" not in (cv._act(exp)["detail"] or {})


def test_export_and_import_refuse_the_link(world):
    from mentis.exchange.export import never_carried
    from mentis.spine.imported import REFUSED_RELATIONS, ImportRefused
    cv = world["cv"]
    bob = _bob(world)
    link = cv.designate_persona(bob, _persona(world, "Builder"),
                                by=_owner(world))
    assert DESIGNATED_AS in REFUSED_RELATIONS

    class _R:
        def establishes(self):
            return "establishes"
    assert DESIGNATED_AS in never_carried(_R())

    row = dict(cv.corpus.read([link])[0])
    row["id"] = "ent-0000designat"
    with pytest.raises(ImportRefused) as refused:
        cv.corpus._store.append_imported([row], [])
    assert DESIGNATED_AS in str(refused.value)


def test_a_designation_write_moves_the_governance_cache(tmp_path):
    from mentis.core.context_cache import ContextCache, Revisions
    from mentis.web import fixture
    from mentis.worker import Surface

    revs = Revisions()
    cache = ContextCache(revisions=revs)
    revs.add_listener(cache.invalidate_domains)
    cache.get("k_gov", lambda: 1, deps=frozenset({"governance"}))
    cache.get("k_work", lambda: 2, deps=frozenset({"work"}))
    revs.note_write({"family": "entry", "link": {
        "relation": DESIGNATED_AS, "from": "ent-p", "to": "ent-persona"}})
    assert "k_gov" not in cache._entries
    assert "k_work" in cache._entries, "an unregistered relation moves everything"

    # and through the store's own write hook
    root = tmp_path / "corpus"
    world = fixture.build(str(root))
    corpus = api.open_corpus(str(root), access="write")
    s = Surface(str(root), corpus=corpus)
    here = world["design"]
    assert s.orient(here)["cache"]["hit"] is False
    assert s.orient(here)["cache"]["hit"] is True
    p = corpus.create_and_establish(
        kind="persona", body={"name": "Builder", "behaviour": "b", "about": ""},
        attributed_to=world["who"]["@brian"])
    assert s.orient(here)["cache"]["hit"] is False
    assert s.orient(here)["cache"]["hit"] is True
    s.cv.designate_persona(world["who"]["@Nadia"], p, by=world["who"]["@brian"])
    assert s.orient(here)["cache"]["hit"] is False


def test_the_run_line_says_where_the_persona_came_from(world):
    """The run summary Fluid's run line reads carries `persona_from`, so it can
    say "(designated)" (found at integration: the Fluid side read a field the
    run summary did not report)."""
    from mentis.operational.runs import asked_with
    cv = world["cv"]
    persona = cv.define_persona("Reviewer", "Judge the candidate.")
    who = cv.create_participant("@Rev")
    cid = cv.open_conversation("Here", attributed_to=world["who"]["@brian"])
    cv.join(world["who"]["@brian"], cid)
    cv.join(who, cid)
    turn = cv.say(cid, world["who"]["@brian"], [{"type": "text", "text": "check it"}], addressed_to=[who])
    exp = cv.expect(turn, of=who, kind="result", by=world["who"]["@brian"],
                    detail={"persona": persona, "persona_from": "designation"})
    start = cv.record_act(actor=who, act="execution-started", conversation=cid, turn=turn,
                          caused_by=exp, because="test", detail={"persona": persona})
    got = asked_with(cv, cv._act(start))
    assert got["persona"] == persona and got["persona_from"] == "designation"


def test_only_the_owners_post_takes_the_designation():
    """Found by the independent review: the ruling is the owner's addressing.
    A post by anyone else names its Persona or goes without one."""
    from mentis.conversation.posting import addressed_persona

    class CV:
        def designated_persona(self, participant):
            return {"resolved": True, "persona": "ent-p", "source": "designation"}

    spec = {"participant": "ent-x", "persona": None}
    assert addressed_persona(CV(), spec)["persona"] == "ent-p"
    assert addressed_persona(CV(), spec, by_owner=False) == {}
    assert addressed_persona(CV(), {**spec, "persona": "ent-q"}, by_owner=False)["persona"] == "ent-q"
