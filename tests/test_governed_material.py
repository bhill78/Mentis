"""Authoring what governs work, and the line between written and governing.

WHAT WAS MISSING, EXACTLY. Mark IV already represented governed material and
already delivered it: `conversation-instruction` and `persona` are ordinary
Kinds, `scoped-to` places material at a Conversation, `compose` gathers it and
`record_delivery` evidences what crossed. Nothing could AUTHOR any of it from
normal work -- no route, no affordance -- so a day's work could not record a
rule.

WHAT WAS ALSO WRONG. `compose` withheld superseded material but delivered
material that had never been established. So anything an agent wrote would
have governed the next execution merely because it was written down.

WHAT IS DELIBERATELY NOT HERE. No approval subsystem, no reviewer role, no
queue, no rule or persona table, no Kind list in interface code. Establishing,
superseding and disputing are the substrate's own vocabulary and `stands` has
always computed the answer from them.
"""

from __future__ import annotations

import pytest

from mentis.web import _State, _routes, fixture


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    cv = st.cv
    conv = cv.open_conversation("Cells", about="acceptance")
    owner = cv.resolve_participant("@brian")
    agent = cv.resolve_participant("@Ada")
    for p in (owner, agent):
        cv.join(p, conv)
    return {"st": st, "cv": cv, "corpus": st.corpus, "conv": conv,
            "owner": owner, "agent": agent}


def post(world, path, payload):
    return _routes(world["st"], path, {}, payload, "POST")


def get(world, path, query=None):
    return _routes(world["st"], path, query or {}, None, "GET")


def instructions_path(world):
    return "/api/conversations/" + world["conv"] + "/instructions"


def governs_path(world):
    return "/api/conversations/" + world["conv"] + "/governs"


# -- 1. rule / instruction --------------------------------------------------

def test_an_owner_places_an_instruction_from_inside_the_conversation(world):
    """ACCEPTANCE: create and place a real instruction, in one act."""
    got = post(world, instructions_path(world),
               {"text": "Measure before claiming a regression.",
                "about": "evidence", "attributed_to": world["owner"], "establish": True})
    assert got["governs"] is True
    assert got["standing"]["stands"] is True

    # Placed, not merely created: it is scoped to THIS Conversation.
    placed = [e["id"] for e in world["cv"].instructions(world["conv"])]
    assert got["entry"] in placed

    # ...and inspectable without leaving the Conversation.
    governs = get(world, governs_path(world))
    assert [r["entry"] for r in governs["governing"]] == [got["entry"]]
    assert governs["candidates"] == [] and governs["ended"] == []


def test_a_fresh_agent_receives_it_with_delivery_evidence(world):
    """ACCEPTANCE: through compose, and the delivery records what crossed."""
    cv, conv = world["cv"], world["conv"]
    placed = post(world, instructions_path(world),
                  {"text": "Cite the Turn you are answering.",
                   "attributed_to": world["owner"], "establish": True})["entry"]

    ex = cv.begin_execution(participant=world["agent"], conversation=conv)
    comp = cv.compose(conversation=conv, participant=world["agent"])
    assert "Cite the Turn you are answering." in comp.payload()
    assert placed in [c.source_id for c in comp.components]

    cv.record_delivery(ex, comp, mechanism="test")
    sources = [s for d in world["corpus"].deliveries(participant=world["agent"])
               for s in d["behavioural_sources"]]
    # AND THE ROW SAYS WHICH LADDER IT CAME UP. A `conversation-instruction`
    # declares `knowing: "how"`, so what the delivery records is that this
    # crossed as GOVERNANCE -- not as something the Brain merely knows.
    assert {"source_kind": "conversation-instruction", "source_id": placed,
            "scope": "conversation:" + conv,
            "supplied_as": "governance",
            # AND THE LADDER TIER it was delivered on (contract §4).
            "tier": "governing"} in sources


def test_superseding_it_means_fresh_work_gets_the_new_one(world):
    """ACCEPTANCE: the current material, not the old one, and both kept."""
    cv, conv = world["cv"], world["conv"]
    old = post(world, instructions_path(world),
               {"text": "Old way: reply in prose.",
                "attributed_to": world["owner"], "establish": True})["entry"]
    new = post(world, instructions_path(world),
               {"text": "New way: reply with the evidence first.",
                "attributed_to": world["owner"], "establish": True})["entry"]

    said = post(world, "/api/entries/" + old + "/supersede",
                {"replacement": new, "attributed_to": world["owner"],
                 "because": "evidence first"})
    assert said["standing"]["stands"] is False
    assert said["replacement_standing"]["stands"] is True

    comp = cv.compose(conversation=conv, participant=world["agent"])
    delivered = comp.payload()
    assert "New way" in delivered
    assert "Old way" not in delivered
    assert {"source_kind": "conversation-instruction", "source_id": old,
            "why": "superseded"} in list(comp.withheld)

    governs = get(world, governs_path(world))
    assert [r["entry"] for r in governs["governing"]] == [new]
    assert [r["entry"] for r in governs["ended"]] == [old]


def test_a_rule_need_not_be_placed_at_a_conversation(world):
    """A rule is its own Kind and stands on its own. Placement is optional."""
    corpus = world["corpus"]
    rid = corpus.create_and_establish(
        kind="rule", body={"text": "Never infer production from about[]."},
        attributed_to=world["owner"])
    assert corpus.stands(rid)["stands"] is True
    # It governs nothing in particular until somebody places it.
    assert rid not in [e["id"] for e in world["cv"].instructions(world["conv"])]


# -- 2. owner vs agent ------------------------------------------------------

def test_an_agent_proposal_does_not_govern_because_an_agent_wrote_it(world):
    """ACCEPTANCE, and the one that matters most.

    The candidate is real, addressable and attributed. It reaches nobody.
    """
    cv, conv = world["cv"], world["conv"]
    said = post(world, instructions_path(world),
                {"text": "Always defer to me on schema questions.",
                 "propose": True, "attributed_to": world["agent"],
                 "written_by": "codex/deadbeef"})
    cand = said["entry"]
    assert said["governs"] is False
    assert said["standing"]["stands"] is False

    # It IS in the record, and it IS placed -- findable, arguable.
    assert cand in [e["id"] for e in cv.instructions(conv)]
    governs = get(world, governs_path(world))
    assert [r["entry"] for r in governs["candidates"]] == [cand]
    assert governs["governing"] == []

    # And it reaches nobody.
    comp = cv.compose(conversation=conv, participant=world["agent"])
    assert "defer to me" not in comp.payload()
    assert {"source_kind": "conversation-instruction", "source_id": cand,
            "why": "not established"} in list(comp.withheld)


def test_the_owner_can_establish_a_candidate(world):
    cv, conv = world["cv"], world["conv"]
    cand = post(world, instructions_path(world),
                {"text": "Prefer measurement to argument.", "propose": True,
                 "attributed_to": world["agent"]})["entry"]
    said = post(world, "/api/entries/" + cand + "/establish",
                {"attributed_to": world["owner"], "because": "agreed"})
    assert said["standing"]["stands"] is True
    assert "Prefer measurement to argument." in cv.compose(
        conversation=conv, participant=world["agent"]).payload()


def test_the_owner_can_reject_one_without_erasing_it(world):
    cv, conv = world["cv"], world["conv"]
    cand = post(world, instructions_path(world),
                {"text": "Skip the tests when in a hurry.", "propose": True,
                 "attributed_to": world["agent"]})["entry"]
    said = post(world, "/api/entries/" + cand + "/dispute",
                {"attributed_to": world["owner"], "because": "no"})
    assert said["standing"]["stands"] is False
    assert said["objection"]
    # The objection says why, and is itself part of the record.
    note = world["corpus"].read([said["objection"]])[0]
    assert note["body"]["text"] == "no"
    governs = get(world, governs_path(world))
    row = [r for r in governs["candidates"] if r["entry"] == cand][0]
    assert row["disputed_by"]
    assert "Skip the tests" not in cv.compose(
        conversation=conv, participant=world["agent"]).payload()


def test_a_candidate_left_alone_stays_unresolved(world):
    """Doing nothing is a legitimate answer, and it is not a silent yes."""
    cv, conv = world["cv"], world["conv"]
    cand = post(world, instructions_path(world),
                {"text": "Undecided.", "propose": True,
                 "attributed_to": world["agent"]})["entry"]
    assert world["corpus"].stands(cand)["stands"] is False
    assert "Undecided." not in cv.compose(
        conversation=conv, participant=world["agent"]).payload()
    governs = get(world, governs_path(world))
    assert [r["entry"] for r in governs["candidates"]] == [cand]


def test_disputing_established_material_does_not_end_it(world):
    """Disagreeing is not the same act as ending, so it does not do it."""
    cv, conv = world["cv"], world["conv"]
    eid = post(world, instructions_path(world),
               {"text": "Stands regardless.",
                "attributed_to": world["owner"], "establish": True})["entry"]
    post(world, "/api/entries/" + eid + "/dispute",
         {"attributed_to": world["agent"], "because": "I disagree"})
    assert world["corpus"].stands(eid)["stands"] is True
    assert "Stands regardless." in cv.compose(
        conversation=conv, participant=world["agent"]).payload()


# -- 3. persona -------------------------------------------------------------

def test_a_persona_is_defined_through_its_own_kind(world):
    """ACCEPTANCE: create a Persona. Its declared fields, not a generic form."""
    said = post(world, "/api/personas",
                {"name": "Reviewer", "behaviour": "challenge the claim",
                 "about": "review work", "attributed_to": world["owner"]})
    assert said["standing"]["stands"] is True
    listed = get(world, "/api/personas")["personas"]
    assert said["persona"] in [p["persona"] for p in listed]
    assert [p["name"] for p in listed
            if p["persona"] == said["persona"]] == ["Reviewer"]


def test_a_persona_needs_its_own_fields(world):
    assert "error" in post(world, "/api/personas", {"name": "Empty"})
    assert "error" in post(world, "/api/personas",
                           {"behaviour": "no name given"})


def test_kinds_are_asked_for_not_hard_coded(world):
    """The authoring surface asks the record what a Kind declares."""
    kinds = {k["kind"]: k for k in get(world, "/api/kinds")["kinds"]}
    assert kinds["persona"]["fields"] == ["name", "behaviour", "about"]
    assert kinds["conversation-instruction"]["fields"] == ["text", "about"]
    assert "rule" in kinds


def test_naming_a_candidate_directly_does_not_deliver_it(world):
    """The one path that could have been used to get round the rule.

    `compose(behavioural=[...])` names material explicitly, which is how
    Brain-scope work says what applies. Asking for a candidate by its id is
    still asking for something nobody established.
    """
    cv, conv = world["cv"], world["conv"]
    cand = post(world, instructions_path(world),
                {"text": "Named directly.", "propose": True,
                 "attributed_to": world["agent"]})["entry"]
    comp = cv.compose(conversation=conv, participant=world["agent"],
                      behavioural=[cand])
    assert "Named directly." not in comp.payload()
    assert {"source_kind": "conversation-instruction", "source_id": cand,
            "why": "not established"} in list(comp.withheld)

    # ...and at Brain scope, which routes through the same seam.
    at_brain = world["st"].brain.compose(participant=world["agent"],
                                         behavioural=[cand])
    assert "Named directly." not in at_brain.payload()


def test_the_granted_capability_establishes_nothing(world):
    """The worker surface exposes reads, and a grant is good at one route.

    WHAT THIS DOES AND DOES NOT ESTABLISH. It establishes that the
    capability Mentis ISSUES confers no power to write: the tools are
    reads, `_result` raises on anything else, and the grant is refused at
    every other route.

    It does NOT establish that a dispatched worker cannot write. An earlier
    version of this said `nothing it can reach writes`, and that was
    false -- measured afterwards: an Antigravity worker, which Mentis runs
    unattended by design, used its ordinary shell to POST to the local API
    and created a Conversation. Its shell is owner-approved authority for
    autonomous work, not something this grant gave it. The two claims are
    different and only the first one is tested here.
    """
    from mentis.worker import TOOLS, _result
    from mentis.web import _surface
    assert {t["name"] for t in TOOLS} == {"orient", "find", "resolve",
                                          "history", "kinds", "sources",
                                          "source_history", "source_links",
                                          "read_source", "search_sources",
                                          # the render check's dry run reads
                                          # nothing of the record and writes
                                          # nothing (Markdown Renderer Maturation)
                                          "check_rendering",
                                          # agent access: governed material,
                                          # owner decisions, the capability
                                          # vocabulary and a brief, all reads
                                          "governed", "owner_decisions",
                                          "capabilities", "brief",
                                          # what the Brain knows about some
                                          # work, and what is outstanding:
                                          # both reads (CLI reconnect)
                                          "recall", "work_overview"}
    surface = _surface(world["st"])
    before = len(world["corpus"].all_entries())
    for name in ("establish", "supersede", "dispute", "instruct"):
        with pytest.raises(KeyError):
            _result(surface, name, {})
    assert len(world["corpus"].all_entries()) == before


def test_the_composer_contract_carries_the_persona(world, monkeypatch):
    """What the UI sends is what dispatch receives.

    The persona travels on the dispatch spec beside runtime and model,
    because all three are answers to how the work is carried out.
    """
    import mentis.web as web
    seen = {}
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: seen.update(kw))

    per = post(world, "/api/personas",
               {"name": "Terse", "behaviour": "one line",
                "attributed_to": world["owner"]})["persona"]
    post(world, "/api/conversations/" + world["conv"] + "/turns", {
        "author": world["owner"], "text": "do it",
        "addressed_to": [world["agent"]],
        "dispatch": [{"participant": world["agent"], "runtime": "codex",
                      "model": None, "effort": None, "persona": per,
                      "new_instance": False}]})
    assert seen["persona"] == per
    assert seen["runtime"] == "codex"
    assert seen["participant"] == world["agent"]


def test_an_unset_persona_stays_unset(world, monkeypatch):
    """Unset is a real answer: asked as themselves, not as a default."""
    import mentis.web as web
    seen = {}
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: seen.update(kw))
    post(world, "/api/conversations/" + world["conv"] + "/turns", {
        "author": world["owner"], "text": "do it",
        "addressed_to": [world["agent"]],
        "dispatch": [{"participant": world["agent"], "persona": None}]})
    assert seen["persona"] is None


def test_a_rule_is_written_through_the_generic_door(world):
    """ACCEPTANCE: a durable rule, created and inspectable, no route of its own.

    A rule is an entry of a declared Kind. It does not need a door built for
    it, and building one would put a Kind name in the interface.
    """
    said = post(world, "/api/entries",
                {"kind": "rule",
                 "body": {"text": "Production is `produced`, never about[]."},
                 "attributed_to": world["owner"]})
    assert said["standing"]["stands"] is True
    got = get(world, "/api/entries/" + said["entry"])
    assert got["body"]["text"].startswith("Production is")


def test_the_generic_door_refuses_what_the_kind_does_not_declare(world):
    """The Kind decides its fields and the spine enforces it."""
    said = post(world, "/api/entries",
                {"kind": "rule", "body": {"text": "ok", "invented": "no"},
                 "attributed_to": world["owner"]})
    assert "error" in said
    assert "allows" in said["error"]

    assert "error" in post(world, "/api/entries",
                           {"kind": "not-a-kind", "body": {"text": "x"}})
    assert "error" in post(world, "/api/entries", {"kind": "rule"})


def test_the_generic_door_can_propose_rather_than_establish(world):
    said = post(world, "/api/entries",
                # a rule: a lesson would also owe a basis (requires_basis)
                {"kind": "rule", "body": {"text": "Measure first."},
                 "establish": False, "attributed_to": world["agent"]})
    assert said["standing"]["stands"] is False
    assert world["corpus"].read([said["entry"]])


def test_a_worker_reading_material_is_told_whether_it_stands(world):
    """FOUND BY REVIEW. Text without status reads like text with authority.

    A worker is meant to be able to read a proposal -- that is how it argues
    with one. Handing it over unqualified is what invites it to be obeyed.
    """
    from mentis.web import _surface
    cand = post(world, instructions_path(world),
                {"text": "A proposal.", "propose": True,
                 "attributed_to": world["agent"]})["entry"]
    held = post(world, instructions_path(world),
                {"text": "The real one.", "establish": True,
                 "attributed_to": world["owner"]})["entry"]
    surface = _surface(world["st"])

    proposed = surface.resolve(cand)
    assert proposed["stands"] is False
    assert "established by nobody" in proposed["standing"]

    governing = surface.resolve(held)
    assert governing["stands"] is True
    assert "governing" in governing["standing"]


def test_a_superseded_persona_is_not_carried_into_fresh_work(world):
    """FOUND BY REVIEW. Reconstruction rendered ended behaviour as current."""
    from mentis.operational import reconstruct
    cv, conv = world["cv"], world["conv"]
    old = post(world, "/api/personas",
               {"name": "Old", "behaviour": "the old way",
                "attributed_to": world["owner"]})["persona"]
    ex = cv.begin_execution(participant=world["agent"], conversation=conv,
                            persona=old)
    cv.record_delivery(ex, cv.compose(conversation=conv,
                                      participant=world["agent"], persona=old),
                       mechanism="test")
    assert reconstruct(world["st"].brain, world["agent"]).persona["id"] == old

    new = post(world, "/api/personas",
               {"name": "New", "behaviour": "the new way",
                "attributed_to": world["owner"]})["persona"]
    post(world, "/api/entries/" + old + "/supersede",
         {"because": "the replacement says it better",
          "replacement": new, "attributed_to": world["owner"]})

    rec = reconstruct(world["st"].brain, world["agent"])
    assert rec.persona is None
    assert any("no longer stands" in m for m in rec.missing)
    assert "the old way" not in rec.rendered()


def test_a_replacement_has_to_be_able_to_replace(world):
    """FOUND BY REVIEW. Only existence was checked."""
    held = post(world, instructions_path(world),
                {"text": "Holds.", "establish": True,
                 "attributed_to": world["owner"]})["entry"]
    cand = post(world, instructions_path(world),
                {"text": "Merely proposed.", "propose": True,
                 "attributed_to": world["agent"]})["entry"]
    persona = post(world, "/api/personas",
                   {"name": "Other kind", "behaviour": "x",
                    "attributed_to": world["owner"]})["persona"]

    assert "does not stand" in post(
        world, "/api/entries/" + held + "/supersede",
        {"because": "the replacement says it better",
         "replacement": cand, "attributed_to": world["owner"]})["error"]
    assert "same Kind" in post(
        world, "/api/entries/" + held + "/supersede",
        {"because": "the replacement says it better",
         "replacement": persona, "attributed_to": world["owner"]})["error"]
    assert "cannot supersede itself" in post(
        world, "/api/entries/" + held + "/supersede",
        {"because": "the replacement says it better",
         "replacement": held, "attributed_to": world["owner"]})["error"]
    assert world["corpus"].stands(held)["stands"] is True


def test_an_instruction_cannot_be_placed_at_a_conversation_that_is_not_one(world):
    """FOUND BY REVIEW. A dangling claim of applicability."""
    said = _routes(world["st"], "/api/conversations/ent-000000000000/instructions",
                   {}, {"text": "nowhere", "establish": True}, "POST")
    assert "error" in said and "no such conversation" in said["error"]


def test_a_persona_can_be_proposed_too(world):
    """FOUND BY REVIEW. `propose` was accepted and ignored here."""
    said = post(world, "/api/personas",
                {"name": "Suggested", "behaviour": "maybe", "propose": True,
                 "attributed_to": world["agent"]})
    assert said["standing"]["stands"] is False
    assert said["persona"] not in [p["persona"]
                                   for p in get(world, "/api/personas")["personas"]]


def test_a_session_told_the_old_material_is_a_different_binding(world):
    """FOUND BY REVIEW, and the deepest one.

    Composition withholds superseded material from the next payload -- but a
    REUSED runtime session was already told it, and a model cannot be
    un-told. So the old instruction went on applying while the record said it
    had ended. A session that was told different things is a different
    binding, so changing what governs stops matching it.
    """
    from mentis.web.dispatch import address_for
    cv, conv = world["cv"], world["conv"]
    before = address_for(cv, world["agent"], runtime="claude",
                         conversation=conv)

    old = post(world, instructions_path(world),
               {"text": "The old way.", "establish": True,
                "attributed_to": world["owner"]})["entry"]
    with_old = address_for(cv, world["agent"], runtime="claude",
                           conversation=conv)
    assert with_old.binding_key() != before.binding_key()

    new = post(world, instructions_path(world),
               {"text": "The new way.", "establish": True,
                "attributed_to": world["owner"]})["entry"]
    post(world, "/api/entries/" + old + "/supersede",
         {"because": "the replacement says it better",
          "replacement": new, "attributed_to": world["owner"]})
    with_new = address_for(cv, world["agent"], runtime="claude",
                           conversation=conv)
    assert with_new.binding_key() != with_old.binding_key(), (
        "a session told the superseded material would have been reused")

    # It is a fingerprint of WHAT governs, not of when it changed: the same
    # material means the same binding.
    assert address_for(cv, world["agent"], runtime="claude",
                       conversation=conv).binding_key() == with_new.binding_key()


def test_a_replacement_must_hold_where_the_old_one_did(world):
    """FOUND BY REVIEW. Placement is what makes an instruction apply."""
    placed = post(world, instructions_path(world),
                  {"text": "Applies here.", "establish": True,
                   "attributed_to": world["owner"]})["entry"]
    unplaced = post(world, "/api/entries",
                    {"kind": "conversation-instruction",
                     "body": {"text": "Applies nowhere."},
                     "attributed_to": world["owner"]})["entry"]
    said = post(world, "/api/entries/" + placed + "/supersede",
                {"because": "the replacement says it better",
                 "replacement": unplaced, "attributed_to": world["owner"]})
    assert "not placed where this material applies" in said["error"]
    assert world["corpus"].stands(placed)["stands"] is True


def test_material_that_never_held_is_not_called_ended(world):
    """FOUND BY REVIEW. `ended` credits material with a standing it had."""
    cand = post(world, instructions_path(world),
                {"text": "Never established.", "propose": True,
                 "attributed_to": world["agent"]})["entry"]
    better = post(world, instructions_path(world),
                  {"text": "The answer.", "establish": True,
                   "attributed_to": world["owner"]})["entry"]
    world["corpus"].write(
        body={"reason": "answered"}, attributed_to=world["owner"],
        link={"from": better, "to": cand, "relation": "supersedes"})
    governs = get(world, governs_path(world))
    assert cand not in [r["entry"] for r in governs["ended"]]
    # THE OWNER'S DECISION: the supersession answered the proposal, so it is
    # no longer a candidate either. It is kept, as replaced.
    assert cand not in [r["entry"] for r in governs["candidates"]]
    assert [r["entry"] for r in governs["replaced"]] == [cand]


def test_replaced_material_is_kept_unchanged_and_the_spine_stays_generic(world):
    """Replaced-before-establishment is how the interface READS the record, not
    a rule the substrate enforces. The entry is preserved as written, and the
    generic route still does what it always did if asked."""
    corpus = world["corpus"]
    cand = post(world, instructions_path(world),
                {"text": "Proposed, then answered.", "propose": True,
                 "attributed_to": world["agent"]})["entry"]
    better = post(world, instructions_path(world),
                  {"text": "The answer.", "establish": True,
                   "attributed_to": world["owner"]})["entry"]
    before = corpus.read([cand])[0]
    said = post(world, "/api/entries/" + cand + "/supersede",
                {"because": "the replacement says it better",
                 "replacement": better, "attributed_to": world["owner"]})
    assert "error" not in said, said

    after = corpus.read([cand])[0]
    assert after["body"] == before["body"], "the replaced proposal was rewritten"
    assert after["attributed_to"] == before["attributed_to"], "authorship moved"
    d = get(world, "/api/entries/" + cand)
    assert d["stands"] is False and d["established_by"] == []
    assert d["superseded_by"] == [better]

    # Not refused by the spine: the interface stops offering it, nothing more.
    out = post(world, "/api/entries/" + cand + "/establish",
               {"attributed_to": world["owner"], "because": "accepted"})
    assert "error" not in out, out


def test_the_owners_place_act_carries_the_delivery_level(world):
    # GOVERNANCE CONDENSATION IS THE OWNER'S TO SAY AT PLACEMENT, through the
    # same door every placement goes through: the level and condition reach the
    # `scoped-to` link, an invalid level is refused in words, and compose then
    # delivers the rule as a conditional reference rather than in full.
    from mentis.conversation.condense import CONDITIONAL, condense
    made = post(world, "/api/entries", {
        "kind": "rule", "body": {"text": "Release notes name every migration."},
        "attributed_to": world["owner"], "because": "release practice"})
    rid = made.get("entry") or made.get("id")
    bad = post(world, f"/api/entries/{rid}/place", {
        "attributed_to": world["owner"], "because": "release work",
        "where": world["conv"], "delivery": "sometimes"})
    assert bad.get("error")
    got = post(world, f"/api/entries/{rid}/place", {
        "attributed_to": world["owner"], "because": "release work",
        "where": world["conv"], "delivery": "conditional",
        "when": "writing release notes"})
    assert not got.get("error"), got
    comp = world["cv"].compose(conversation=world["conv"],
                               participant=world["agent"])
    level = next(d for d in condense(world["corpus"], comp)
                 if d.component.source_id == rid)
    assert level.level == CONDITIONAL
    assert level.condition == "writing release notes"


def test_material_placed_by_condition_or_reference_does_not_decide_the_runtime(world):
    # Found in the integrated verification: a Discipline placed conditionally
    # (and a Workflow by reference) left no runtime eligible for any post in
    # the Conversation. Only material delivered in full narrows selection.
    from mentis.web.dispatch import delivered_in_full, governing_ids, requirements_of
    cv, corpus, conv = world["cv"], world["corpus"], world["conv"]
    owner = world["owner"]
    full = corpus.create_and_establish(kind="discipline", body={
        "name": "Full", "about": "always", "text": "t",
        "requires": ["call_mentis_tools"]}, attributed_to=owner)
    light = corpus.create_and_establish(kind="discipline", body={
        "name": "Light", "about": "when testing", "text": "t",
        "requires": ["write_unattended"]}, attributed_to=owner)
    cv.place(full, conv, by=owner, because="always")
    cv.place(light, conv, by=owner, because="sometimes", delivery="conditional",
             when="writing tests")
    ids = governing_ids(cv, conv)
    assert {full, light} <= ids
    kept = delivered_in_full(cv, conv, ids)
    assert full in kept and light not in kept
    assert "write_unattended" not in requirements_of(cv, kept)
    # Named for the work, it is delivered in full, and so it counts.
    assert light in delivered_in_full(cv, conv, ids, named=[light])


# -- 4. managing a conversation's instructions from inside it ----------------

def test_only_the_owner_establishes_through_the_conversation_door(world):
    """The route's own rule: an owner establishes, anything else proposes.
    `establish: true` naming somebody else is refused and writes nothing,
    the answer `/api/entries/<id>/establish` already gives."""
    corpus = world["corpus"]
    before = len(corpus.entries_of_kind("conversation-instruction"))
    said = post(world, instructions_path(world),
                {"text": "Agents may establish.", "establish": True,
                 "attributed_to": world["agent"]})
    assert "only the owner may establish" in said["error"]
    assert len(corpus.entries_of_kind("conversation-instruction")) == before
    governs = get(world, governs_path(world))
    assert governs["governing"] == [] and governs["candidates"] == []
    # Proposing is still open to them.
    cand = post(world, instructions_path(world),
                {"text": "Agents may propose.",
                 "attributed_to": world["agent"]})
    assert cand["governs"] is False
    assert [r["entry"] for r in get(world, governs_path(world))["candidates"]] \
        == [cand["entry"]]


def test_a_conversation_instruction_is_placed_here_not_brain_wide(world):
    """Conversation placement stays apart from Brain-wide governance."""
    eid = post(world, instructions_path(world),
               {"text": "Only here.", "establish": True,
                "attributed_to": world["owner"]})["entry"]
    row = get(world, governs_path(world))["governing"][0]
    assert row["entry"] == eid and row["placed"] == ["conversation"]
    assert eid not in [e["id"] for e in world["cv"].placed_brain_wide()]
    other = world["cv"].open_conversation("Elsewhere")
    assert eid not in [r["entry"] for r in
                       get(world, f"/api/conversations/{other}/governs")["governing"]]


def test_a_pending_edit_is_shown_beside_what_still_governs(world):
    """An edit of a governing instruction is a proposed next version, placed
    nowhere until approved. The read says so on the row, and approving it
    makes the new version govern here and the old one ended."""
    cv, conv, owner = world["cv"], world["conv"], world["owner"]
    old = post(world, instructions_path(world),
               {"text": "Reply in prose.", "establish": True,
                "attributed_to": owner})["entry"]
    edited = post(world, f"/api/entries/{old}/edit",
                  {"body": {"text": "Reply with evidence first."},
                   "attributed_to": owner, "because": "evidence first"})
    assert edited["mode"] == "proposed", edited
    version = edited["version"]

    governs = get(world, governs_path(world))
    [row] = governs["governing"]
    assert row["entry"] == old
    successors = row["proposed"]["successors"]["items"]
    assert [s["entry"] for s in successors] == [version]
    assert successors[0]["state"] == "candidate"
    assert "Reply with evidence first." not in cv.compose(
        conversation=conv, participant=world["agent"]).payload()

    said = post(world, f"/api/entries/{old}/establish-replacement",
                {"replacement": version, "attributed_to": owner,
                 "because": "approved"})
    assert "error" not in said, said
    governs = get(world, governs_path(world))
    assert [r["entry"] for r in governs["governing"]] == [version]
    assert [r["entry"] for r in governs["ended"]] == [old]
    assert "Reply with evidence first." in cv.compose(
        conversation=conv, participant=world["agent"]).payload()


def test_removing_an_instruction_from_here_ends_only_its_placement(world):
    """`unplace` ends the placement; the material and its standing stay."""
    eid = post(world, instructions_path(world),
               {"text": "No longer here.", "establish": True,
                "attributed_to": world["owner"]})["entry"]
    said = post(world, f"/api/entries/{eid}/unplace",
                {"where": world["conv"], "attributed_to": world["owner"],
                 "because": "not for this conversation"})
    assert "error" not in said, said
    assert said["standing"]["stands"] is True
    governs = get(world, governs_path(world))
    assert eid not in [r["entry"] for k in ("governing", "candidates", "ended",
                                            "replaced") for r in governs[k]]
    assert "No longer here." not in world["cv"].compose(
        conversation=world["conv"], participant=world["agent"]).payload()


def test_orientation_reads_governs_without_proposals(world):
    """The proposal read is the surface's; other callers do not pay for it."""
    post(world, instructions_path(world),
         {"text": "Plain.", "establish": True, "attributed_to": world["owner"]})
    [row] = world["cv"].governs(world["conv"])["governing"]
    assert "proposed" not in row
