"""WHAT A DECISION IS MISSING, IN WORDS, PER QUESTION -- in real Chrome.

The corrections B1-B3 of the interface review (ent-0fc483e17f76) for owner
request ent-6f6d22b5c962, over the records the request was written about: the
three Agent Presets scope questions and the run-end generated approval, as the
record holds them, in a disposable Brain.

Two servers are checked, because the client must be right against both:

  THIS SERVER projects no `presentation_status` and no `question_references`
  (it is the cumulative TEST baseline). What the page says about the generated
  approval it has to derive itself, by the backends' own rule.

  THE PINNED BACKENDS (Python 2f3c2210, Rust 47796384) project both. Their
  actual payloads are replayed onto the wire from
  `apps/fluid-web/tests/fixtures/needs_you_pinned_wire.json`, which is what
  that Python answered for these same forms; only the ids are this Brain's.

Build apps/fluid-web first; opt in with MENTIS_QUIET_BROWSER=1.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mentis.conversation import text
from tests._loop import _coordinator, a_conversation, world  # noqa: F401
from tests.test_quiet_needs_you_inspect_browser import Quiet, chrome  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.environ.get("MENTIS_QUIET_BROWSER") != "1",
    reason="set MENTIS_QUIET_BROWSER=1 after building the client",
)

WIRE = json.loads((Path(__file__).parents[1] / "apps/fluid-web/tests/fixtures"
                   / "needs_you_pinned_wire.json").read_text(encoding="utf-8"))

PROPOSAL = "ent-e89925cea328"
CHECK = "ent-53b2e2132df5"

SCOPE_Q = [
    {"question": f"Which first-release scope do you approve for implementation of the reviewed proposal {PROPOSAL}?",
     "options": [
         {"label": "Full bounded presets (recommended)",
          "consequence": "Implement permission and authority defaults, Persona suggestions, fixed runtime/model/effort, and bounded delegation reuse with the stated safeguards."},
         {"label": "Permission-first",
          "consequence": "Implement owner permission and authority presets and lifecycle safeguards; defer Persona associations, runtime presets, and agent-side preset reads."},
         {"label": "Browser-local only",
          "consequence": "Implement a reduced device-bound composer feature without agent-side preset reuse."},
         {"label": "Isolation first",
          "consequence": "Defer preset implementation until stronger separate-principal or container isolation is designed and authorized."}]},
    {"question": "If server presets proceed, how should their storage and backup tradeoff be handled?",
     "options": [
         {"label": "Separate store (recommended)",
          "consequence": "Keep host-path preferences outside Brain backups and Exchange; acknowledge that Brain recovery will not automatically restore presets."},
         {"label": "Include in Brain backups",
          "consequence": "Store presets with backed-up Brain presentation data, accepting that portable backups may contain local workspace paths."}]},
    {"question": "If runtime presets are included, how should preset settings interact with independent reviews?",
     "options": [
         {"label": "Preset-bounded protection (recommended)",
          "consequence": "Do not automatically apply fixed runtime or model defaults to reviews; block preset conflicts while retaining existing non-preset behavior."},
         {"label": "Broader mandatory gate",
          "consequence": "Design a global runtime-independence launch and completion gate, including explicit owner waiver rules for outages or single-runtime installations."}]},
]

GENERATED_QUESTION = (
    "Approve this work?\n"
    "Completed and independently reviewed the first-release proposal; awaiting the owner's scope and implementation decision.\n"
    f"Exact references: artifacts {PROPOSAL}; result post ent-d1cfb7935d43")

BECAUSE = ("The owner required a reviewed first-release scope and explicit approval before implementation. "
           f"The proposal {PROPOSAL} and focused review {CHECK} identify these consequential release choices.")

CONSTRUCTOR = "a decision only the owner can make"


AUTHORED_QUESTION = (
    "Approve this work?\n"
    "I am asking you myself, about the Round 2 candidate, in these same words.")


def build(world):  # noqa: F811
    """The three forms exactly as the record holds them: a three-question scope
    form recorded before the creation contract, a run-end generated approval
    whose form act carries `approval_artifacts`, and a form asked with the same
    general words and the same fallback context whose act carries NOTHING that
    says where it came from (ent-9f0291944c9a)."""
    from mentis.worker import _decision_form
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = a_conversation(world, "Agent Presets")
    coach, parent, _grant = _coordinator(world, cid)
    request_turn = cv._act(parent)["turn"]

    def act(name, **kw):
        kw.setdefault("caused_by", parent)
        return cv.record_act(actor=coach, act=name, execution="inst-b13", runtime="claude", **kw)

    asking = cv.say(cid, coach, [text(
        f"The [revised first-release proposal]({PROPOSAL}) is ready for your decision.")],
        addressed_to=[owner], replies_to=request_turn)
    scope = _decision_form(
        cv, {"because": BECAUSE, "questions": SCOPE_Q, "on": asking},
        actor=coach, parent=parent, here=cid, wrote=None, act=act,
        where=lambda c: c, execution="inst-b13")

    result = cv.say(cid, coach, [text(
        "Completed and independently reviewed the first-release proposal.")],
        addressed_to=[owner], replies_to=request_turn)
    generated = _decision_form(
        cv, {"because": CONSTRUCTOR,
             "questions": [{"question": GENERATED_QUESTION, "because": CONSTRUCTOR,
                            "options": [{"label": "Approve", "consequence": "continue this request with the named work"},
                                        {"label": "Revise", "consequence": "revise this work before proceeding"}]}],
             "on": result},
        actor=coach, parent=parent, here=cid, wrote=None, act=act,
        where=lambda c: c, form_detail={"approval_artifacts": [PROPOSAL]},
        execution="inst-b13")
    # THE SAME WORDS, NOTHING BEHIND THEM: no `form_detail`, so the act records
    # no approval material -- all the record holds is the question itself.
    authored = _decision_form(
        cv, {"because": CONSTRUCTOR,
             "questions": [{"question": AUTHORED_QUESTION, "because": CONSTRUCTOR,
                            "options": [{"label": "Approve", "consequence": "continue this request with the named work"},
                                        {"label": "Revise", "consequence": "revise this work before proceeding"}]}],
             "on": result},
        actor=coach, parent=parent, here=cid, wrote=None, act=act,
        where=lambda c: c, execution="inst-b13")
    return {"cid": cid, "scope": scope["form"],
            "scope_questions": [q["expectation"] for q in scope["questions"]],
            "generated": generated["form"],
            "generated_question": generated["questions"][0]["expectation"],
            "authored": authored["form"],
            "authored_question": authored["questions"][0]["expectation"],
            "asking": asking, "result": result}


def _gaps(card):
    return [x.inner_text() for x in card.locator("[data-dec-gap]").all()]


def _question(card):
    q = card.locator(".rb-dec-q").first
    q.wait_for(timeout=20000)
    return q


# ---------------------------------------------------------------- B1 ------

def test_the_generated_approval_says_its_authority_was_never_recorded(chrome, world):  # noqa: F811
    """§B1, against a server that projects nothing: the page must still say
    that what approving it would permit is not in the record, and must not
    affirm that the question and choices are complete as recorded."""
    w = build(world)
    q = Quiet(chrome, world, w)
    card = q.answer_here(w["generated"])
    asked = _question(card)
    assert asked.get_attribute("data-presentation") == "incomplete"
    said = _gaps(asked)
    assert any("what approving it would permit cannot be read from the record" in g for g in said), said
    assert any("at which stage" in g for g in said), said
    assert any("the record does not say why you are being asked" in g for g in said), said
    # not claimed to be an earlier format that holds everything it should
    assert asked.locator("[data-earlier-format]").count() == 0
    # and the way out of a question that cannot be read is offered
    assert "Withdraw with a clarification reason" in card.inner_text()
    # NO FIELD PATH AND NO CODE, anywhere a person reads (§B2)
    for g in said:
        assert "presentation." not in g and "not_recorded" not in g and "The record is missing" not in g, g

    # THE THREE SCOPE QUESTIONS ARE UNTOUCHED: a sufficient older format, shown
    # as recorded, with every alternative and its own consequence.
    scope = q.answer_here(w["scope"])
    rows = scope.locator(".rb-dec-q")
    assert rows.count() == 3
    first = rows.first
    assert first.locator("[data-earlier-format]").count() == 1
    assert _gaps(first) == []
    assert first.locator(".rb-dec-option").count() == 6      # four alternatives, own words, withdraw
    assert q.errors == []


# ------------------------------------------- origin, where nothing records it --

def test_the_page_never_says_where_an_approval_came_from(chrome, world):  # noqa: F811
    """ent-9f0291944c9a: the general words and the constructor's fallback
    phrase are all the record holds for this form. What is missing -- the
    context, what approving it would permit and at which stage -- is still said
    in full; WHO OR WHAT ASKED IT is not asserted, because nothing records it.

    Both halves of the owner's requirement are checked on one rendered form:
    the fallback phrase is not claimed to be unauthored, and the question's
    prefix is not claimed to prove a run produced it."""
    w = build(world)
    q = Quiet(chrome, world, w)
    card = q.answer_here(w["authored"])
    asked = _question(card)
    assert asked.get_attribute("data-presentation") == "incomplete"
    said = _gaps(asked)
    # WHAT IS MISSING, STILL SAID IN FULL
    assert any("what approving it would permit cannot be read from the record" in g for g in said), said
    assert any("at which stage" in g for g in said), said
    assert any("the record does not say why you are being asked" in g for g in said), said
    # NO ORIGIN ASSERTED, for either the question or the context phrase
    joined = "\n".join(said)
    assert "recorded as a generated approval" not in joined, joined
    assert "is not in the asker" not in joined, joined
    assert "Mentis itself fills" not in joined, joined
    assert any("The record does not say whether this question was written for this work" in g for g in said), said
    assert any("whether the asker wrote them cannot be told from the record" in g for g in said), said
    # the way out of a question that cannot be read is still offered
    assert "Withdraw with a clarification reason" in card.inner_text()
    for g in said:
        assert "presentation." not in g and "not_recorded" not in g, g

    # THE REAL GENERATED APPROVAL READS THE SAME on this wire, because this
    # server projects no approval material either: the page cannot tell them
    # apart, and does not pretend to.
    other = _gaps(_question(q.answer_here(w["generated"])))
    assert "recorded as a generated approval" not in "\n".join(other), other
    assert any("The record does not say whether this question was written for this work" in g for g in other), other

    # AND THE AGENT PRESETS SCOPE QUESTIONS ARE UNTOUCHED BY ALL OF IT: their
    # own words, their own alternatives, nothing said to be missing.
    scope = q.answer_here(w["scope"])
    rows = scope.locator(".rb-dec-q")
    assert rows.count() == 3
    for i in range(3):
        row = rows.nth(i)
        assert _gaps(row) == [], _gaps(row)
        assert row.locator("[data-earlier-format]").count() == 1
        assert SCOPE_Q[i]["question"][:40] in row.inner_text()
        for o in SCOPE_Q[i]["options"]:
            assert o["label"] in row.inner_text()
            assert o["consequence"][:40] in row.inner_text()
    assert q.errors == []


# ---------------------------------------------------------------- B2 ------

def _pinned_status():
    """Exactly what Python 2f3c2210 projected for the generated approval."""
    return WIRE["cases"]["generated_approval"]["decision_form"]["questions"][0]["presentation_status"]


def _projecting(context, status):
    """The server answers as the pinned backends answer."""
    def handle(route):
        res = route.fetch()
        try:
            body = res.json()
        except Exception:                                   # noqa: BLE001
            return route.fulfill(response=res)
        for f in body.get("decision_forms") or ():
            for q in f.get("questions") or ():
                q["presentation_status"] = status
        for e in body.get("expectations") or ():
            e["presentation_status"] = status
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    context.route("**/fluid/api/decisions*", handle)
    context.route("**/fluid/api/needs-you/decisions*", handle)


def test_the_pinned_backends_codes_reach_the_owner_as_words(chrome, world):  # noqa: F811
    """§B2: with the pinned backend's own `presentation_status` on the wire,
    the owner reads sentences -- not "The record is missing presentation.scope
    (not_recorded)."."""
    w = build(world)
    q = Quiet(chrome, world, w)
    _projecting(q.context, _pinned_status())
    q.page.reload()
    q.page.wait_for_selector(".q2-gdock-pill", timeout=30000)
    q.open_needs()
    card = q.answer_here(w["generated"])
    asked = card.locator(".rb-dec-q [data-presentation='incomplete'], .rb-dec-q").first
    asked.wait_for(timeout=15000)
    said = _gaps(card)
    assert said, "the backend's problems are said"
    for g in said:
        assert "presentation." not in g, g
        assert "not_recorded" not in g and "unavailable_or_uncertain" not in g, g
        assert not g.startswith("The record is missing"), g
        assert g.strip().endswith((".", "?", "!")), g
    assert any("what approving it would permit cannot be read from the record" in g for g in said), said
    # its two halves are one thing to a person: said once
    assert sum("what approving it would permit" in g for g in said) == 1
    # AND THE BACKEND'S OWN WORD DRIVES THE SAME THING THE PAGE DERIVES (B4):
    # on this status, Approve is not a control here either.
    assert card.locator("[data-clarify-needed]").count() == 1
    assert card.locator(".rb-dec-options[role='radiogroup'] [data-option='0']").count() == 0
    assert q.errors == []


# ---------------------------------------------------------------- B4 ------

def _radios(card):
    return [x.inner_text().split("\n")[0]
            for x in card.locator(".rb-dec-options[role='radiogroup'] [role='radio']").all()]


def _pinned(context, w):
    """Each form answered as Python 2f3c2210 answered it for that form: the
    generated approval's own `presentation_status`, and the scope questions'
    (`legacy`, nothing missing). Both halves of B4 on one real wire."""
    gen = _pinned_status()
    legacy = WIRE["cases"]["legacy_scope_form"]["decision_form"]["questions"][0]["presentation_status"]
    by_form = {w["generated"]: gen, w["authored"]: gen, w["scope"]: legacy}

    def handle(route):
        res = route.fetch()
        try:
            body = res.json()
        except Exception:                                   # noqa: BLE001
            return route.fulfill(response=res)
        for f in body.get("decision_forms") or ():
            for qq in f.get("questions") or ():
                if f.get("form") in by_form:
                    qq["presentation_status"] = by_form[f["form"]]
        for e in body.get("expectations") or ():
            if e.get("form") in by_form:
                e["presentation_status"] = by_form[e["form"]]
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context.route("**/fluid/api/decisions*", handle)
    context.route("**/fluid/api/needs-you/decisions*", handle)


def test_an_unreadable_approval_offers_no_affirmative_shortcut(chrome, world):  # noqa: F811
    """§B4 (review ent-b2914bea6fb4, contract §5.4): the page says what
    approving this would permit cannot be read from the record, so the choices
    it recorded are NOT offered as answers -- neither Approve nor Revise, since
    which of them would permit what is exactly what is missing. They stay,
    whole, as wording to read. Nothing in the record changes, and the owner is
    left with the three safe ways out.

    Driven by the pinned Python's own status for this form, and its own
    `legacy` status for the scope questions in the same browser."""
    w = build(world)
    q = Quiet(chrome, world, w)
    _pinned(q.context, w)
    q.page.reload()
    q.page.wait_for_selector(".q2-gdock-pill", timeout=30000)
    q.open_needs()
    card = q.answer_here(w["generated"])
    asked = _question(card)
    asked.locator("[data-clarify-needed]").wait_for(timeout=20000)

    # WHY THEY ARE NOT OFFERED, AND WHAT IS
    why = asked.locator("[data-clarify-needed]").inner_text()
    assert "not offered as answers" in why, why
    assert "your own words" in why and "Leave open" in why and "Withdraw with a clarification reason" in why, why
    # no option named as the risky one, and nothing claimed to have been refused
    assert "Approve" not in why and "refus" not in why.lower(), why

    # EVERY RECORDED CHOICE IS STILL THERE, WHOLE, AND IS NOT A CONTROL
    wording = asked.locator("[data-wording-only]")
    assert wording.get_attribute("data-wording-only") == "2"
    for label, then in (("Approve", "continue this request with the named work"),
                        ("Revise", "revise this work before proceeding")):
        assert label in wording.inner_text() and then in wording.inner_text()
    assert wording.locator("[role='radio']").count() == 0
    assert wording.locator("button").count() == 0
    # and no option control survives anywhere in the form
    assert card.locator("[data-option='0'][role='radio']").count() == 0
    assert card.locator("[data-option='1'][role='radio']").count() == 0

    # DECIDE CAN SEND NOTHING: nothing is chosen, and nothing here is choosable
    assert card.locator(".rb-dec-foot .btn", has_text="Leave open").count() == 1
    assert card.locator(".rb-dec-foot .btn.primary").is_disabled()
    wording.locator(".rb-dec-option").first.click()         # a row is wording, not a choice
    assert card.locator(".rb-dec-foot .btn.primary").is_disabled()
    assert "Nothing sent yet" in card.locator(".rb-form-status").inner_text()

    # WHAT IS LEFT IS THE WAYS OUT THAT ARE SAFE, reachable by keyboard alone:
    # the group is one tab stop, and the arrows move and choose within it.
    assert _radios(asked) == ["… Your own words", "⊘ Withdraw with a clarification reason"], _radios(asked)
    asked.locator(".rb-dec-options[role='radiogroup'] [role='radio']").first.focus()
    q.page.keyboard.press("ArrowDown")
    assert "Your own words" in q.page.evaluate("() => document.activeElement.innerText")
    q.page.keyboard.press("ArrowDown")
    assert "Withdraw with a clarification reason" in q.page.evaluate("() => document.activeElement.innerText")

    # AND THE RECORD IS UNTOUCHED BY ALL OF IT: a choice is a draft until
    # Answer sends it, and none of this sent anything.
    state = world["cv"].expectation_state(w["generated_question"])
    assert state["response_present"] is False and not state["answer"]

    # AND THE THREE SCOPE QUESTIONS -- an ordinary decision, missing nothing --
    # keep every control they had, on the same pinned wire.
    scope = q.answer_here(w["scope"])
    rows = scope.locator(".rb-dec-q")
    assert rows.count() == 3
    first = rows.first
    assert first.locator("[data-clarify-needed]").count() == 0
    assert first.locator("[data-wording-only]").count() == 0
    assert first.locator(".rb-dec-options[role='radiogroup'] [data-option='0'][role='radio']").count() == 1
    assert first.locator(".rb-dec-option").count() == 6      # four alternatives, own words, withdraw
    assert q.errors == []


def test_own_words_still_close_it_and_send_exactly_what_they_always_sent(chrome, world):  # noqa: F811
    """§B4: the clarification requirement takes away the ambiguous shortcut and
    nothing else. Own words remain an answer, say so before they are sent, and
    reach the record as the same payload on the same question -- no option, no
    label, no authorisation invented for it."""
    w = build(world)
    q = Quiet(chrome, world, w)
    card = q.answer_here(w["generated"])
    asked = _question(card)
    sent: list[str] = []
    q.page.on("request", lambda r: sent.append(r.post_data or "")
              if r.method == "POST" and "/turns" in r.url else None)
    words = "I cannot tell what Approve would authorise. Say which stage this covers."
    for _ in range(8):
        try:
            own = asked.locator(".rb-dec-options[role='radiogroup'] [data-option='own']")
            if own.get_attribute("aria-checked") != "true":
                own.click()
            box = asked.locator("textarea.rb-dec-words")
            box.wait_for(timeout=3000)
            box.fill(words)
            # said before it is sent: own words ARE the answer, and close it
            assert "close this question" in asked.locator("[data-own-closes]").inner_text()
            if box.input_value() == words and own.get_attribute("aria-checked") == "true":
                break
        except Exception:                                   # noqa: BLE001 -- drawn again
            continue
    # AND THE DRAFT SURVIVES INSPECTING WHAT THE FORM NAMES: the post it was
    # asked on opens by its own exact identity, and the owner comes back to
    # their words. (The historical proposal itself is not in this disposable
    # Brain, so what opens here is the result post the form was asked on.)
    q.item(w["generated"]).locator(f"button[data-ref-id='{w['result']}']").first.click()
    q.page.locator(f".q2-conv [data-post='{w['result']}']").first.wait_for(timeout=20000)
    q.back_to_decision()
    held = q.page.locator(f"[data-question='{w['generated_question']}']")
    held.locator("textarea.rb-dec-words").wait_for(timeout=20000)
    assert held.locator("textarea.rb-dec-words").input_value() == words
    assert held.locator("[data-option='own']").get_attribute("aria-checked") == "true"
    assert held.locator("[data-wording-only]").count() == 1, "and the choices are still wording, not controls"
    card = q.answer_here(w["generated"])
    card.locator(".rb-dec-foot .btn.primary").click()
    cv = world["cv"]
    qid = w["generated_question"]
    for _ in range(60):
        if cv.expectation_state(qid)["answer"] is not None:
            break
        q.page.wait_for_timeout(500)
    answer = cv.expectation_state(qid)["answer"]
    assert answer, "the answer reached the record"
    assert answer.get("option") is None and answer.get("label") is None, answer
    assert cv.expectation_state(qid)["response_present"] is True
    # THE WIRE PAYLOAD: this question, the owner's words, and no choice
    bodies = [json.loads(b) for b in sent if b]
    chose = [b.get("chose") for b in bodies if b.get("chose")]
    assert chose == [{"expectation": qid}], chose
    assert any(words in json.dumps(b) for b in bodies), bodies
    assert q.errors == []


# ---------------------------------------------------------------- B3 ------

def _per_question(context, ids, words):
    """The reads answer as the pinned backends answer: each question's own
    declared references, keyed by its exact expectation id, and each item's own
    questions. The reference objects are the pinned Python's own
    (fixtures/needs_you_pinned_wire.json); only the ids are this Brain's.

    Quiet Chat's Needs you draws the list AND its details from one answer
    (`/fluid/api/needs-you/about?items=1`), so both halves go in there."""
    pinned = WIRE["cases"]["new_contract_form"]["about"]["question_references"]

    def refs():
        out = []
        for i, qid in enumerate(ids):
            src = dict(pinned[i % len(pinned)])
            src["expectation"] = qid
            out.append(src)
        return out

    def answer(route):
        res = route.fetch()
        try:
            body = res.json()
        except Exception:                                   # noqa: BLE001
            return route.fulfill(response=res)
        for a in body.get("about") or ():
            if a.get("form"):
                a["question_references"] = refs()
        for it in body.get("items") or ():
            if len(it.get("asks") or ()) > 1:
                it["questions"] = [{"expectation": a, "question": words.get(a)} for a in it["asks"]]
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context.route("**/fluid/api/needs-you/about*", answer)
    context.route("**/fluid/api/needs-you/items*", answer)


def test_each_question_keeps_its_own_references(chrome, world):  # noqa: F811
    """§B3: a form-wide union must not make one question's primary appear to
    belong to another. With the mapping projected, each question's own source
    is drawn under it; the pooled list is no longer "You are deciding on"."""
    w = build(world)
    q = Quiet(chrome, world, w)
    words = {qid: SCOPE_Q[i]["question"] for i, qid in enumerate(w["scope_questions"])}
    _per_question(q.context, w["scope_questions"], words)
    q.page.reload()
    q.page.wait_for_selector(".q2-gdock-pill", timeout=30000)
    q.open_needs()
    row = q.item(w["scope"])
    row.locator(".q2-ny-questions .q2-ny-question").first.wait_for(timeout=20000)
    seen = row.evaluate(
        "el => ({per_question: [...el.querySelectorAll('.q2-ny-questions .q2-ny-question')]"
        "   .map(x => ({id: x.getAttribute('data-question'),"
        "               label: (x.querySelector('.q2-ny-label')||{}).innerText || '',"
        "               refs: [...x.querySelectorAll('.q2-ny-refs > li')].map(r => r.innerText)})),"
        " pooled_label: (el.querySelector('.q2-ny-group[data-role=\"subject\"] .q2-ny-label')||{}).innerText || null})")
    assert [x["id"] for x in seen["per_question"]] == w["scope_questions"]
    for i, x in enumerate(seen["per_question"]):
        assert SCOPE_Q[i]["question"][:40] in x["label"], x["label"]
    # the first question's declared primary is under the FIRST question only
    assert len(seen["per_question"][0]["refs"]) == 2       # its primary and its supporting material
    assert "The record names no item for this question." in seen["per_question"][1]["refs"][0]
    assert (seen["pooled_label"] or "").upper() != "YOU ARE DECIDING ON"
    assert q.errors == []


def test_several_questions_are_never_headed_as_one_subject(chrome, world):  # noqa: F811
    """§B3 against a server that projects no mapping: the pooled list says what
    it is -- what the form names -- and never that it is what you are deciding
    on, which would read as every question's own subject."""
    w = build(world)
    q = Quiet(chrome, world, w)
    row = q.item(w["scope"])
    label = row.evaluate(
        "el => (el.querySelector('.q2-ny-group[data-role=\"subject\"] .q2-ny-label')||{}).innerText || null")
    assert (label or "").upper() != "YOU ARE DECIDING ON"
    assert row.evaluate("el => el.querySelector('.q2-ny-group[data-role=\"subject\"]').getAttribute('data-pooled')") == "several"
    # the one-question item keeps the heading it had
    gen = q.item(w["generated"])
    assert (gen.evaluate("el => (el.querySelector('.q2-ny-group[data-role=\"subject\"] .q2-ny-label')||{}).innerText")
            or "").upper() == "YOU ARE DECIDING ON"
    assert q.errors == []


# ------------------------------------------------- narrow, keyboard, answer --

def test_narrow_and_keyboard_and_the_answer_itself(chrome, world):  # noqa: F811
    """The corrected lines keep their words on a 360-wide screen -- including
    the recorded choices of an approval that are there to read and the sentence
    saying why (§B4) -- the form is operable by keyboard, and an answer to an
    ordinary decision still records exactly what it did: this question, this
    option index, this label."""
    w = build(world)
    narrow = Quiet(chrome, world, w, width=360, height=740)
    card = narrow.answer_here(w["generated"])
    asked = _question(card)
    assert _gaps(asked), "what is missing is said on a narrow screen too"
    assert asked.locator("[data-clarify-needed]").count() == 1
    assert "Approve" in asked.locator("[data-wording-only]").inner_text()
    assert narrow.page.evaluate(
        "() => { const f = document.querySelector('.rb-form'); const d = document.scrollingElement;"
        " return [f.scrollWidth - f.clientWidth, d.scrollWidth - d.clientWidth] }") == [0, 0]
    # the longer sentence said where the record names no origin keeps its words
    # on the same screen (ent-9f0291944c9a)
    unattributed = _question(narrow.answer_here(w["authored"]))
    assert any("The record does not say whether this question was written for this work" in g
               for g in _gaps(unattributed)), _gaps(unattributed)
    assert narrow.page.evaluate(
        "() => { const f = document.querySelector('.rb-form'); const d = document.scrollingElement;"
        " return [f.scrollWidth - f.clientWidth, d.scrollWidth - d.clientWidth] }") == [0, 0]
    # AN ORDINARY DECISION, MISSING NOTHING: the three Agent Presets scope
    # questions, whose alternatives each say what choosing them leads to.
    card = narrow.answer_here(w["scope"])
    first = card.locator(".rb-dec-q").first
    first.wait_for(timeout=20000)
    # KEYBOARD ONLY: the arrows reach the second alternative, and it is chosen
    # from the keyboard. The form rereads every few seconds and may be drawn
    # again in between, so it is done until it holds.
    chosen = False
    for _ in range(8):
        try:
            first.locator(".rb-dec-option").first.focus()
            # the group is one tab stop and the arrows move and choose within it
            narrow.page.keyboard.press("ArrowDown")
            narrow.page.keyboard.press("ArrowDown")
            assert "Permission-first" in narrow.page.evaluate("() => document.activeElement.innerText")
            card.locator(".rb-form-status", has_text="chosen").first.wait_for(timeout=3000)
            chosen = True
            break
        except Exception:                                   # noqa: BLE001 -- drawn again
            continue
    assert chosen, "the second alternative was never reached and chosen from the keyboard"
    assert first.locator("[data-option='1']").first.get_attribute("aria-checked") == "true"
    assert narrow.page.evaluate(
        "() => { const f = document.querySelector('.rb-form'); const d = document.scrollingElement;"
        " return [f.scrollWidth - f.clientWidth, d.scrollWidth - d.clientWidth] }") == [0, 0]
    card.locator(".rb-dec-foot .btn.primary").click()
    # THE ANSWER AS THE RECORD TAKES IT
    cv = world["cv"]
    qid = w["scope_questions"][0]
    for _ in range(60):
        state = cv.expectation_state(qid)
        if state["answer"]:
            break
        narrow.page.wait_for_timeout(500)
    answer = cv.expectation_state(qid)["answer"]
    assert answer, "the answer reached the record"
    # the same question, the same option index, the same label as before
    assert (answer["option"], answer["label"]) == (1, "Permission-first"), answer
    assert cv.expectation_state(qid)["response_present"] is True
    assert narrow.errors == []
