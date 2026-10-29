"""Governance condensation (operating model §3).

Every Brain here is disposable, made under the test's own tmp_path. What is
pinned, rule by rule:

  1. superseded material never reaches condense: the successor renders and
     the predecessor's id appears nowhere in the text;
  2. non-governing components pass through FULL and render exactly as
     `Composition` renders them -- a delivery of all-FULL components is the
     payload itself, byte for byte;
  3. the Persona being worn is always FULL;
  4. material named for the work, or listed in `known`, is FULL;
  5. a placement declares `delivery`/`when` on its link body; absent means
     FULL, the condition is the link's `when` else the entry's `about`, and
     no condition or one over 240 characters means FULL;
  6. a conditional whose condition the question meets (the knowledge
     channel's term overlap) is FULL;
  7. a reference renders only in the closing index line.

Plus the door: `place` validates and stores the declaration, a Workflow
(whose Kind declares `placeable: "reference"`, as §1's vocabulary revision
makes it) is refused a full placement and accepted a conditional one, and
`placement_delivery` reads the newest live link at a Conversation, on the
whole Brain and on a Persona.
"""

from __future__ import annotations

import pytest

import mentis.api as api
from mentis.conversation import WHOLE_BRAIN_SCOPE
from mentis.conversation.condense import (
    CONDITIONAL, CONDITION_LIMIT, FULL, REFERENCE, condense, render)
from tests._brains import new_brain


@pytest.fixture
def world(tmp_path):
    new_brain(tmp_path / "corpus")
    corpus = api.open_corpus(str(tmp_path / "corpus"))
    cv = api.conversations(corpus)
    owner = cv.create_participant("brian")
    agent = cv.create_participant("Ada")
    conv = cv.open_conversation("Condense", about="acceptance",
                                attributed_to=owner)
    cv.join(owner, conv)
    cv.join(agent, conv)
    yield {"corpus": corpus, "cv": cv, "owner": owner, "agent": agent,
           "conv": conv}
    corpus.close()


def rule(world, text, about=""):
    return world["corpus"].create_and_establish(
        kind="rule", body={"text": text, "about": about},
        attributed_to=world["owner"])


def discipline(world, name, about, text="The principles and procedure."):
    return world["corpus"].create_and_establish(
        kind="discipline", body={"name": name, "about": about, "text": text},
        attributed_to=world["owner"])


def place_link_direct(world, entry, where, body):
    """A placement link written the way links that predate `place`'s
    validation, or that another door wrote, exist: by hand."""
    return world["corpus"].write(
        body=body, attributed_to=world["owner"],
        link={"from": entry, "to": where, "relation": "scoped-to"})


def delivery_for(deliveries, source_id):
    return next(d for d in deliveries if d.component.source_id == source_id)


def compose(world, **kw):
    return world["cv"].compose(conversation=world["conv"],
                               participant=world["agent"], **kw)


# -- 1. standing is resolved before condense ---------------------------------

def test_superseded_material_never_appears(world):
    cv, corpus, conv = world["cv"], world["corpus"], world["conv"]
    old = rule(world, "Old way: reply in prose.")
    new = rule(world, "New way: reply with the evidence first.")
    cv.place(old, conv, by=world["owner"], because="applies here")
    cv.place(new, conv, by=world["owner"], because="applies here")
    corpus.write(body={"reason": "evidence first"},
                 attributed_to=world["owner"],
                 link={"from": new, "to": old,
                       "relation": corpus.superseding_relation()})
    assert corpus.stands(old)["superseded_by"]

    comp = compose(world)
    deliveries = condense(corpus, comp)
    out = render(deliveries)
    assert "New way: reply with the evidence first." in out
    assert "Old way" not in out
    assert old not in out
    assert all(d.component.source_id != old for d in deliveries)


# -- 2. what does not govern passes through, rendered as composed -------------

def test_an_all_full_delivery_is_the_payload_itself(world):
    """Rule 2, and the FULL rendering contract: condense changes nothing that
    is delivered in full, so `render` of an all-full delivery is exactly
    `Composition.payload()` -- orientation, request, persona, placed rule and
    the knowledge channel's lesson alike."""
    cv, corpus = world["cv"], world["corpus"]
    persona = cv.define_persona("Builder", "build carefully",
                                about="building", attributed_to=world["owner"])
    cv.place(rule(world, "Cite the Turn you are answering."), world["conv"],
             by=world["owner"], because="applies here")
    corpus.create_and_establish(
        kind="lesson", body={"text": "quasarcache uses the current path"},
        attributed_to=world["owner"])

    comp = compose(world, persona=persona, request="fix the quasarcache path",
                   question="quasarcache path")
    # The knowledge channel did bring the lesson, so the rule-2 pass-through
    # is exercised by a real knowledge component.
    assert any(c.tier == "adopted" for c in comp.components)

    deliveries = condense(corpus, comp, question="quasarcache path")
    assert all(d.level == FULL for d in deliveries)
    assert render(deliveries) == comp.payload()


# -- 3. the Persona being worn ------------------------------------------------

def test_the_persona_being_worn_is_always_full(world):
    persona = world["cv"].define_persona("Reviewer", "challenge the claim",
                                         about="reviewing",
                                         attributed_to=world["owner"])
    deliveries = condense(world["corpus"], compose(world, persona=persona))
    d = delivery_for(deliveries, persona)
    assert d.level == FULL and d.component.scope == "invocation:persona"


# -- 4. named for the work, or known to it ------------------------------------

def test_named_material_is_full(world):
    named = rule(world, "Named for this invocation only.")
    comp = compose(world, behavioural=[named])
    d = delivery_for(condense(world["corpus"], comp), named)
    assert d.level == FULL and d.component.scope == "invocation:named"


def test_known_material_is_full(world):
    d_id = discipline(world, "Releasing", "cutting a release")
    world["cv"].place(d_id, world["conv"], by=world["owner"],
                      because="applies here", delivery=CONDITIONAL,
                      when="cutting a release")
    comp = compose(world)
    assert delivery_for(condense(world["corpus"], comp), d_id).level \
        == CONDITIONAL
    known = condense(world["corpus"], comp, known={d_id})
    d = delivery_for(known, d_id)
    assert d.level == FULL and "known" in d.why


# -- 5. what the placement declares -------------------------------------------

def test_absent_delivery_is_full(world):
    rid = rule(world, "Placed as material always was.")
    world["cv"].place(rid, world["conv"], by=world["owner"],
                      because="applies here")
    d = delivery_for(condense(world["corpus"], compose(world)), rid)
    assert d.level == FULL and d.condition is None


def test_conditional_renders_the_exact_line(world):
    """The exact §3 format, with the condition from the Discipline's own
    applicability field (`about`, "When it applies") -- a link that carries
    no `when`, as links written before validation did."""
    d_id = discipline(world, "CLI/MARS development",
                      "making a software change through the CLI")
    place_link_direct(world, d_id, world["conv"],
                      {"reason": "applies here", "delivery": CONDITIONAL})

    deliveries = condense(world["corpus"], compose(world))
    d = delivery_for(deliveries, d_id)
    assert d.level == CONDITIONAL
    assert d.condition == "making a software change through the CLI"

    expected = (f"[governs · discipline · conditional] "
                f"CLI/MARS development — making a software change through "
                f"the CLI — applies when: making a software change through "
                f"the CLI. Read it in full with resolve(\"{d_id}\") before "
                f"acting under it. (reference: {d_id})")
    out = render(deliveries)
    assert expected in out
    # AND THE FULL TEXT NEVER APPEARS under a conditional delivery.
    assert "The principles and procedure." not in out


def test_the_link_when_is_the_condition_before_the_entry_about(world):
    d_id = discipline(world, "Releasing", "cutting a release")
    world["cv"].place(d_id, world["conv"], by=world["owner"],
                      because="applies here", delivery=CONDITIONAL,
                      when="tagging a release build")
    d = delivery_for(condense(world["corpus"], compose(world)), d_id)
    assert d.level == CONDITIONAL and d.condition == "tagging a release build"


def test_a_conditional_with_no_condition_is_full(world):
    rid = rule(world, "Placed conditional with nothing to state.")
    place_link_direct(world, rid, world["conv"],
                      {"reason": "applies here", "delivery": CONDITIONAL})
    d = delivery_for(condense(world["corpus"], compose(world)), rid)
    assert d.level == FULL


def test_a_condition_over_the_limit_is_full(world):
    d_id = discipline(world, "Long", "x" * (CONDITION_LIMIT + 1))
    place_link_direct(world, d_id, world["conv"],
                      {"reason": "applies here", "delivery": CONDITIONAL})
    d = delivery_for(condense(world["corpus"], compose(world)), d_id)
    assert d.level == FULL and "shorthand" in d.why


# -- 6. a condition the question meets ----------------------------------------

def test_a_condition_the_question_meets_is_full(world):
    d_id = discipline(world, "Installer", "building the Windows installer")
    world["cv"].place(d_id, world["conv"], by=world["owner"],
                      because="applies here", delivery=CONDITIONAL,
                      when="building the Windows installer")
    comp = compose(world)

    met = delivery_for(condense(world["corpus"], comp,
                                question="build a new Windows installer"),
                       d_id)
    assert met.level == FULL and met.condition == \
        "building the Windows installer"

    unmet = delivery_for(
        condense(world["corpus"], comp,
                 question="summarise the budget committee minutes"), d_id)
    assert unmet.level == CONDITIONAL


# -- 7. references ------------------------------------------------------------

def test_references_render_only_in_the_closing_index_line(world):
    corpus = world["corpus"]
    one = discipline(world, "Installer", "building the installer")
    two = discipline(world, "Releasing", "cutting a release")
    for d_id in (one, two):
        world["cv"].place(d_id, world["conv"], by=world["owner"],
                          because="by reference", delivery=REFERENCE)

    deliveries = condense(corpus, compose(world))
    assert delivery_for(deliveries, one).level == REFERENCE

    out = render(deliveries)
    assert "The principles and procedure." not in out
    index = [l for l in out.split("\n")
             if l.startswith("Also standing, by reference:")]
    assert len(index) == 1
    assert f"{one} (Installer — building the installer)" in index[0]
    assert f"{two} (Releasing — cutting a release)" in index[0]
    # CLOSING: nothing follows the index line.
    assert out.rstrip().endswith(index[0])


# -- the scopes a placement is read at ----------------------------------------

def test_whole_brain_placement_declares_delivery_too(world):
    cv, corpus = world["cv"], world["corpus"]
    d_id = discipline(world, "House style", "writing for this Brain")
    cv.place(d_id, whole_brain=True, by=world["owner"],
             because="applies everywhere", delivery=CONDITIONAL,
             when="writing for this Brain")

    # The read helper resolves the whole-Brain scope constant ...
    assert cv.placement_delivery(d_id, WHOLE_BRAIN_SCOPE) == {
        "delivery": CONDITIONAL, "when": "writing for this Brain"}
    # ... and a composition, whose component carries that scope, condenses.
    d = delivery_for(condense(corpus, compose(world)), d_id)
    assert d.level == CONDITIONAL and d.component.scope == WHOLE_BRAIN_SCOPE


def test_persona_carried_material_reads_its_placement(world):
    cv, corpus = world["cv"], world["corpus"]
    persona = cv.define_persona("Builder", "build carefully",
                                about="building", attributed_to=world["owner"])
    d_id = discipline(world, "UI work", "editing the Fluid UI")
    cv.place(d_id, persona, by=world["owner"], because="carried",
             delivery=CONDITIONAL, when="editing the Fluid UI")

    comp = compose(world, persona=persona)
    carried = delivery_for(condense(corpus, comp), d_id)
    assert carried.level == CONDITIONAL
    assert carried.component.scope == f"persona:{persona}"
    # AND THE PERSONA ITSELF is still full (rule 3 beside rule 5).
    assert delivery_for(condense(corpus, comp), persona).level == FULL


def test_placement_delivery_is_the_newest_live_link(world):
    cv = world["cv"]
    d_id = discipline(world, "House style", "writing for this Brain")
    cv.place(d_id, world["conv"], by=world["owner"], because="first",
             delivery=REFERENCE)
    cv.end_placement(d_id, world["conv"], by=world["owner"],
                     because="changed how much a run needs")
    cv.place(d_id, world["conv"], by=world["owner"], because="second",
             delivery=CONDITIONAL, when="writing for this Brain")
    assert cv.placement_delivery(d_id, world["conv"]) == {
        "delivery": CONDITIONAL, "when": "writing for this Brain"}
    # Ended again, nothing is declared, which is full delivery.
    cv.end_placement(d_id, world["conv"], by=world["owner"],
                     because="no longer placed")
    assert cv.placement_delivery(d_id, world["conv"]) is None


# -- the door -----------------------------------------------------------------

def test_place_validates_the_declaration(world):
    cv, owner, conv = world["cv"], world["owner"], world["conv"]
    rid = rule(world, "A rule to place.")

    with pytest.raises(ValueError, match="one of"):
        cv.place(rid, conv, by=owner, because="x", delivery="sometimes")
    with pytest.raises(ValueError, match="needs the condition"):
        cv.place(rid, conv, by=owner, because="x", delivery=CONDITIONAL)
    with pytest.raises(ValueError, match="needs the condition"):
        cv.place(rid, conv, by=owner, because="x", delivery=CONDITIONAL,
                 when="   ")
    with pytest.raises(ValueError, match="at most"):
        cv.place(rid, conv, by=owner, because="x", delivery=CONDITIONAL,
                 when="x" * (CONDITION_LIMIT + 1))
    with pytest.raises(ValueError, match="belongs to"):
        cv.place(rid, conv, by=owner, because="x", when="no delivery given")

    got = cv.place(rid, conv, by=owner, because="x", delivery=CONDITIONAL,
                   when="when it applies")
    body = corpus_link_body(world, rid, conv, got["placement"])
    assert body == {"reason": "x", "delivery": CONDITIONAL,
                    "when": "when it applies"}


def corpus_link_body(world, frm, to, link_id):
    got = [x for x in world["corpus"].links(relation="scoped-to", frm=frm,
                                            to=to) if x["id"] == link_id]
    assert len(got) == 1
    return got[0]["body"]


def test_a_workflow_is_placed_by_reference_or_not_at_all(world):
    """A Workflow's Kind declares `authoring.placeable: "reference"` -- the
    §1 vocabulary revision, applied here as the new definition version it
    is. A full placement is refused with a clear message; conditional and
    reference are accepted."""
    corpus, cv = world["corpus"], world["cv"]
    current = corpus.current_definition("workflow")["body"]
    props = {k: v for k, v in current.items() if k not in ("kind", "fields")}
    props["authoring"] = {**current["authoring"], "placeable": "reference"}
    corpus.define_kind("workflow", fields=current["fields"], properties=props,
                       attributed_to=world["owner"])

    w = corpus.create_and_establish(
        kind="workflow",
        body={"name": "Software change", "about": "changing software",
              "text": "orient, delegate, integrate, test, record",
              "activities": []},
        attributed_to=world["owner"])

    with pytest.raises(ValueError, match="only by reference"):
        cv.place(w, world["conv"], by=world["owner"], because="x")
    with pytest.raises(ValueError, match="only by reference"):
        cv.place(w, world["conv"], by=world["owner"], because="x",
                 delivery=FULL)
    assert not cv.placement_delivery(w, world["conv"])

    got = cv.place(w, world["conv"], by=world["owner"], because="x",
                   delivery=CONDITIONAL, when="changing software")
    assert got["placement"]
    assert cv.placement_delivery(w, world["conv"]) == {
        "delivery": CONDITIONAL, "when": "changing software"}

    other = rule(world, "An ordinary rule is still placed as before.")
    assert cv.place(other, world["conv"], by=world["owner"],
                    because="x")["placement"]
