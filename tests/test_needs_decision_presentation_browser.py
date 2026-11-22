"""WHAT A DECISION IS MISSING, IN WORDS, PER QUESTION -- in real Chrome.

The corrections B1-B3 of the interface review (ent-0fc483e17f76) for owner
request ent-6f6d22b5c962, over the records the request was written about: the
three Agent Presets scope questions and the run-end generated approval, as the
record holds them, in a disposable Brain.

The integrated server and older wire shapes are checked:

  THIS SERVER projects `presentation_status` and `question_references`.
  Historical forms still carry no authored presentation metadata. The pooled
  fallback test explicitly removes the mapping to exercise an older server.

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
from tests.test_quiet_needs_you_inspect_browser import Quiet, _choose, chrome  # noqa: F401

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


@pytest.mark.parametrize("mapping", ["integrated", "older_wire"])
def test_several_questions_are_never_headed_as_one_subject(chrome, world, mapping):  # noqa: F811
    """§B3: keep both contracts. The integrated mapping names each historical
    question, with no invented primary. An older server's pooled fallback is
    explicitly simulated, and must never claim a shared decision subject."""
    w = build(world)
    q = Quiet(chrome, world, w)
    if mapping == "older_wire":
        def without_mapping(route):
            res = route.fetch()
            body = res.json()
            for item in body.get("about") or ():
                item.pop("question_references", None)
            route.fulfill(response=res, json=body)

        q.context.route("**/fluid/api/needs-you/about*", without_mapping)
        _reopen(q)
    row = q.item(w["scope"])
    label = row.evaluate(
        "el => (el.querySelector('.q2-ny-group[data-role=\"subject\"] .q2-ny-label')||{}).innerText || null")
    assert (label or "").upper() != "YOU ARE DECIDING ON"
    if mapping == "older_wire":
        pooled = row.locator(".q2-ny-group[data-role='subject']")
        assert pooled.get_attribute("data-pooled") == "several"
        assert pooled.locator(".q2-ny-label").inner_text().lower() == "named by this form"
        assert row.locator(".q2-ny-questions").count() == 0
    else:
        questions = row.locator(".q2-ny-questions .q2-ny-question")
        assert questions.count() == 3
        for i, qid in enumerate(w["scope_questions"]):
            shown = questions.nth(i)
            assert shown.get_attribute("data-question") == qid
            assert SCOPE_Q[i]["question"][:40] in shown.inner_text()
            assert "The record names no item for this question." in shown.inner_text()
            assert shown.locator("button[data-ref-id]").count() == 0
        assert row.locator(".q2-ny-group[data-role='subject']").count() == 0
    # the one-question item keeps the heading it had
    gen = q.item(w["generated"])
    assert (gen.evaluate("el => (el.querySelector('.q2-ny-group[data-role=\"subject\"] .q2-ny-label')||{}).innerText")
            or "").upper() == "YOU ARE DECIDING ON"
    assert q.errors == []
    q.close()


def test_new_strict_questions_show_their_actual_sources_and_record_the_answer(chrome, world):
    """No replay: strict authoring, per-question roles, exact navigation with a
    retained draft, and the final answer all use this disposable Brain."""
    from mentis.worker import _operate
    from mentis.web import _surface
    from tests.decision_descriptors import question

    cv = world["cv"]
    cid = a_conversation(world, "Strict authored sources")
    coach, parent, grant = _coordinator(world, cid)
    first = cv.say(cid, coach, [text("First chart design; build only.")])
    second = cv.say(cid, coach, [text("Second chart design; build only.")])
    questions = [question("Build the first chart?"), question("Build the second chart?")]
    for item, source in zip(questions, (first, second)):
        item["presentation"]["primary"] = {"kind": "record", "id": source, "label": "Chart design"}
        item["presentation"].pop("primary_reason")
    made = _operate(_surface(world["state"]), "request_decision", {"questions": questions}, grant)
    _operate(_surface(world["state"]), "respond", {"text": "Two chart designs ready."}, grant)
    qids = [item["expectation"] for item in made["questions"]]
    q = Quiet(chrome, world, {"cid": cid})
    try:
        row = q.answer_here(made["form"])
        for i, source in enumerate((first, second)):
            shown = row.locator(f".q2-ny-question[data-question='{qids[i]}']")
            assert shown.get_attribute("data-presentation") == "complete"
            assert questions[i]["question"] in shown.inner_text()
            assert shown.locator("button[data-ref-id]").count() == 1
            assert shown.locator("button[data-ref-id]").get_attribute("data-ref-id") == source
            assert shown.locator(f"[data-ref-id='{(second, first)[i]}']").count() == 0
        answer = row.locator(f".rb-dec-q[data-question='{qids[0]}']")
        _choose(answer, 0, "Build only after reading the first chart.")
        row.locator(f".q2-ny-question[data-question='{qids[0]}'] button[data-ref-id='{first}']").click()
        q.page.locator(f".q2-conv [data-post='{first}']").wait_for(timeout=20000)
        q.back_to_decision()
        answer = q.item(made["form"]).locator(f".rb-dec-q[data-question='{qids[0]}']")
        assert answer.locator("textarea.rb-dec-words").input_value() == "Build only after reading the first chart."
        assert answer.locator("[data-option='0']").get_attribute("aria-checked") == "true"
        q.item(made["form"]).locator(".rb-dec-foot .btn.primary").click()
        for _ in range(60):
            if cv.expectation_state(qids[0])["answer"]:
                break
            q.page.wait_for_timeout(500)
        got = cv.expectation_state(qids[0])["answer"]
        assert got and (got["option"], got["label"]) == (0, "Build"), got
        assert cv.expectation_state(qids[1])["response_present"] is False
    finally:
        q.close()


# ------------------------------- R1/R2: ESSENTIAL INFORMATION, NOT AUTHORITY --
# Review ent-be99511604d4 (report adm-a4191d6c2d8e) reproduced three decisions
# on the real pinned Python that still offered and still SENT their recorded
# choices although the page itself said what was missing:
#
#   R1-A  an action approval whose scope and stage ARE recorded, and whose
#         first alternative has no recorded consequence;
#   R1-B  an approval of something specific whose one named record is not an
#         id this Brain could look up;
#   R2    the general approval asked as its own post. The pinned projection
#         carries no `question` for it at all (`_expectation_view` projects it
#         only for a question of a form), so the backends' own
#         generic-approval rule could not be applied here -- and a retained
#         draft went out through Decide and through "+ continue".
#
# Each of these is answered here with that server's own payload for it
# (`clarification_cases` in the fixture, captured from Python 2f3c2210 the same
# way as the three above), in a disposable Brain.

CLARIFY = WIRE["clarification_cases"]

OPERATION = {
    "summary": "Read the fixture build report", "kind": "execute",
    "command": "Get-Content fixture-report.txt", "cwd": "C:\\fixture",
    "resources": ["C:\\fixture\\fixture-report.txt"], "workspace": "C:\\fixture",
    "within": True, "tool": "shell", "why": "Inspect the fixture result",
}


def clarified(world):  # noqa: F811
    """One conversation holding, side by side: the two incomplete approvals of
    R1, the general approval asked as its own post (R2), a system-produced
    permission form, and an ordinary sufficient question. Each is recorded
    through the same trusted historical constructor; production authoring
    validation is not weakened to build any of them."""
    from mentis.worker import _decision_form
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = a_conversation(world, "Essential information")
    coach, parent, _grant = _coordinator(world, cid)
    request_turn = cv._act(parent)["turn"]

    def act(name, **kw):
        kw.setdefault("caused_by", parent)
        return cv.record_act(actor=coach, act=name, execution="inst-r1r2", runtime="claude", **kw)

    def form(words, question, **kw):
        post = cv.say(cid, coach, [text(words)], addressed_to=[owner], replies_to=request_turn)
        return _decision_form(
            cv, {"because": question["because"], "questions": [question], "on": post},
            actor=coach, parent=parent, here=cid, wrote=None, act=act, where=lambda c: c,
            execution="inst-r1r2", **kw)

    out = {"cid": cid}
    for name in ("action_approval_missing_consequence", "artifact_approval_unreadable_primary"):
        src = CLARIFY[name]["question"]
        f = form(f"A stored decision: {name}.",
                 {k: src[k] for k in ("question", "because", "options")})
        out[name] = f["form"]
        out[name + "_question"] = f["questions"][0]["expectation"]

    # THE GENERAL APPROVAL ASKED AS ITS OWN POST: an expectation of the owner
    # recorded on the asking post, with no form at all.
    standalone = CLARIFY["standalone_generic_approval"]["expectation"]
    post = cv.say(cid, coach, [text("Approve this work?")], addressed_to=[owner], replies_to=request_turn)
    out["standalone"] = cv.expect(
        post, of=owner, by=coach, kind="decision", because=standalone["because"],
        detail={"question": "Approve this work?", "options": standalone["options"]})

    # A SYSTEM-PRODUCED PERMISSION FORM, whose authority is the operation it
    # displays: it must keep Allow once and Deny exactly as they were.
    run = cv.record_act(actor=coach, act="execution-started", conversation=cid, turn=request_turn,
                        execution="inst-r1r2-perm", runtime="claude", caused_by=parent,
                        because="fixture run")
    perm = form("The run waits for permission to read the fixture report.",
                {"question": "Allow reading the fixture build report?",
                 "because": "The run waits for permission to inspect the fixture report.",
                 "options": [{"label": "Allow once", "consequence": "Only this operation; the next one is asked again."},
                             {"label": "Deny", "consequence": "Refuse this operation; the agent is told."}]},
                form_detail={"permission": True, "run": run,
                             "tool": {"title": OPERATION["summary"], "kind": "execute"},
                             "operation": OPERATION})
    out["permission"] = perm["form"]

    # AND AN ORDINARY SUFFICIENT QUESTION in the same browser, to see that
    # nothing is taken from a decision that is missing nothing.
    enough = form("Which first-release scope?", {**SCOPE_Q[1], "because": BECAUSE})
    out["enough"] = enough["form"]
    return out


def _pinned_cases(context, w, masked=None):
    """Each of these questions answered as Python 2f3c2210 answered it: its own
    `presentation` object where it recorded one, and its own
    `presentation_status`. Everything else on the wire is this server's.

    `masked`, where given, is an expectation id answered as COMPLETE instead --
    the one intervention, and only to establish a draft chosen before a read
    said less (R2's retained draft). It is turned off before anything is sent,
    and what is tested after that is the real payload."""
    by_id = {}
    for name in ("action_approval_missing_consequence", "artifact_approval_unreadable_primary"):
        by_id[w[name + "_question"]] = CLARIFY[name]["expectation"]
    by_id[w["standalone"]] = CLARIFY["standalone_generic_approval"]["expectation"]

    def put(d, key):
        if masked and masked.get("on") and key == masked["id"]:
            d["presentation_status"] = {"state": "complete", "problems": []}
            return
        src = by_id.get(key)
        if not src:
            return
        if "presentation" in src:
            d["presentation"] = src["presentation"]
        d["presentation_status"] = src["presentation_status"]

    def handle(route):
        res = route.fetch()
        try:
            body = res.json()
        except Exception:                                   # noqa: BLE001
            return route.fulfill(response=res)
        for f in body.get("decision_forms") or ():
            for q in f.get("questions") or ():
                put(q, q.get("expectation"))
        for e in body.get("expectations") or ():
            put(e, e.get("id"))
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context.route("**/fluid/api/decisions*", handle)
    context.route("**/fluid/api/needs-you/**", handle)


def _reopen(q):
    q.page.reload()
    q.page.wait_for_selector(".q2-gdock-pill", timeout=30000)
    q.open_needs()


@pytest.mark.parametrize("case", ["action_approval_missing_consequence",
                                  "artifact_approval_unreadable_primary"])
def test_an_approval_missing_essential_information_offers_no_affirmative(chrome, world, case):  # noqa: F811
    """R1 (ent-be99511604d4), contract §5 and §5.4. What the record does not
    hold here is NOT its authorisation boundary -- R1-A records its scope and
    its stage, R1-B records both and names a source -- and the owner still
    cannot read what sending one of the choices would mean: what choosing the
    first alternative leads to was never recorded, or the one thing it is about
    cannot be looked up. So neither choice is offered as an answer.

    Nothing is supplied for what is missing, and no option is judged."""
    w = clarified(world)
    q = Quiet(chrome, world, w, width=360, height=900)
    _pinned_cases(q.context, w)
    _reopen(q)
    card = q.answer_here(w[case])
    asked = _question(card)
    assert asked.get_attribute("data-presentation") == "incomplete"
    asked.locator("[data-clarify-needed]").wait_for(timeout=20000)

    # WHAT IS MISSING, IN ITS OWN WORDS, with no field path and no code
    said = _gaps(asked)
    assert said, said
    for g in said:
        assert "presentation." not in g and "_" not in g, g
    if case == "action_approval_missing_consequence":
        assert any("Choice A “Approve”" in g and "was not recorded" in g for g in said), said
        assert asked.locator("[data-no-consequence]").count() == 1
    else:
        assert any("could look up" in g for g in said), said

    # EVERY RECORDED CHOICE IS STILL THERE, WHOLE, AND NONE IS A CONTROL
    wording = asked.locator("[data-wording-only]")
    assert wording.get_attribute("data-wording-only") == "2"
    src = CLARIFY[case]["expectation"]["options"]
    for i, o in enumerate(src):
        row = wording.locator(f"[data-option='{i}']")
        assert o["label"] in row.inner_text()
        if o.get("consequence"):
            assert o["consequence"] in row.inner_text()
    assert wording.locator("[role='radio'], button, input").count() == 0
    assert card.locator("[data-option='0'][role='radio']").count() == 0
    assert card.locator("[data-option='1'][role='radio']").count() == 0

    # AND NOTHING CAN SEND ONE: not a click on the wording, not Decide, and not
    # a Decide forced open from the DOM.
    assert card.locator(".rb-dec-foot .btn.primary").is_disabled()
    wording.locator(".rb-dec-option").first.click()
    assert card.locator(".rb-dec-foot .btn.primary").is_disabled()
    sent: list[str] = []
    q.page.on("request", lambda r: sent.append(r.post_data or "")
              if r.method == "POST" and "/turns" in r.url else None)
    card.locator(".rb-dec-foot .btn.primary").evaluate("el => { el.disabled = false; el.click() }")
    q.page.wait_for_timeout(400)
    assert sent == [], sent
    state = world["cv"].expectation_state(w[case + "_question"])
    assert state["response_present"] is False and not state["answer"]

    # THE WAYS OUT THAT ARE SAFE, reachable by the keyboard alone
    assert _radios(asked) == ["… Your own words", "⊘ Withdraw with a clarification reason"], _radios(asked)
    asked.locator(".rb-dec-options[role='radiogroup'] [role='radio']").first.focus()
    q.page.keyboard.press("ArrowDown")
    assert "Your own words" in q.page.evaluate("() => document.activeElement.innerText")
    q.page.keyboard.press("ArrowDown")
    assert "Withdraw with a clarification reason" in q.page.evaluate("() => document.activeElement.innerText")
    # AND IT ALL FITS A 360-WIDE SCREEN
    assert q.page.evaluate(
        "() => { const f = document.querySelector('.rb-form'); const d = document.scrollingElement;"
        " return [f.scrollWidth - f.clientWidth, d.scrollWidth - d.clientWidth] }") == [0, 0]
    q.close()


def test_a_retained_draft_on_a_standalone_approval_sends_through_neither_path(chrome, world):  # noqa: F811
    """R2: the general approval asked as its own post, on the real pinned
    projection -- which carries no question at all, so what says this may
    authorise something and does not say what is the STATUS that server
    projected for it.

    The draft is established the only way a draft from before a read said less
    can be: the status is answered as complete while it is made, and the real
    payload is restored, without a reload, before anything is sent. After that
    the retained choice is not applied, Decide sends nothing, and "+ continue"
    -- which sent it before -- is not there to be clicked."""
    w = clarified(world)
    q = Quiet(chrome, world, w)
    mask = {"id": w["standalone"], "on": True}
    _pinned_cases(q.context, w, masked=mask)
    _reopen(q)
    card = q.answer_here(w["standalone"])
    _choose(card, 0, "Retain this draft; do not send it.")
    assert card.locator(".rb-dec-foot button", has_text="+ continue").count() == 1, "the path R2 sent through"
    assert card.locator("[data-clarify-needed]").count() == 0

    # THE REAL PAYLOAD, with no reload: the same page, answered as the pinned
    # server answers, while the owner's draft is still held.
    mask["on"] = False
    card.locator("[data-clarify-needed]").wait_for(timeout=25000)
    asked = _question(card)
    assert asked.get_attribute("data-presentation") == "incomplete"
    assert any("what approving it would permit cannot be read from the record" in g for g in _gaps(asked)), _gaps(asked)
    # THE RETAINED CHOICE IS NOT APPLIED, and neither way out of it can send it
    assert card.locator("[data-option='0'][role='radio']").count() == 0
    assert card.locator("[data-wording-only]").get_attribute("data-wording-only") == "2"
    assert card.locator(".rb-dec-foot button", has_text="+ continue").count() == 0
    assert card.locator(".rb-dec-foot .btn.primary").is_disabled()
    sent: list[str] = []
    q.page.on("request", lambda r: sent.append(r.post_data or "")
              if r.method == "POST" and "/turns" in r.url else None)
    card.locator(".rb-dec-foot .btn.primary").evaluate("el => { el.disabled = false; el.click() }")
    q.page.wait_for_timeout(400)
    assert sent == [], sent
    state = world["cv"].expectation_state(w["standalone"])
    assert state["response_present"] is False and not state.get("answer")
    # AND THE OWNER'S OWN WORDS ARE STILL THERE TO ANSWER WITH
    assert card.locator("[data-option='own']").count() == 1
    assert "Withdraw with a clarification reason" in card.inner_text()
    q.close()


def test_what_is_sufficient_and_what_is_a_permission_keep_every_control(chrome, world):  # noqa: F811
    """The other half of R1: the clarification requirement takes the ambiguous
    shortcut and nothing else. On the same wire, in the same browser, a
    system-produced permission form still offers Allow once and Deny with its
    operation and their own consequences, and an ordinary question whose
    alternatives each say what they lead to is still answered by choosing one
    -- recorded as the same question, the same index and the same label."""
    w = clarified(world)
    q = Quiet(chrome, world, w)
    _pinned_cases(q.context, w)
    _reopen(q)

    permission = q.answer_here(w["permission"])
    assert permission.locator("[data-clarify-needed]").count() == 0
    assert permission.locator("[data-wording-only]").count() == 0
    for i, label in enumerate(("Allow once", "Deny")):
        control = permission.locator(f"[data-option='{i}'][role='radio']")
        assert control.count() == 1 and control.is_enabled()
        assert label in control.inner_text()
    assert OPERATION["command"] in permission.text_content()
    assert "Only this operation" in permission.inner_text()

    card = q.answer_here(w["enough"])
    asked = _question(card)
    assert asked.locator("[data-clarify-needed]").count() == 0
    assert asked.locator("[data-wording-only]").count() == 0
    assert _gaps(asked) == [], _gaps(asked)
    for i, o in enumerate(SCOPE_Q[1]["options"]):
        row = asked.locator(f"[data-option='{i}'][role='radio']")
        assert row.count() == 1 and o["label"] in row.inner_text()
    _choose(asked, 1, "")
    card.locator(".rb-dec-foot .btn.primary").click()
    cv = world["cv"]
    qid = cv.decision_form(w["enough"])["questions"][0]["expectation"]
    for _ in range(60):
        if cv.expectation_state(qid)["answer"]:
            break
        q.page.wait_for_timeout(500)
    answer = cv.expectation_state(qid)["answer"]
    assert answer, "the answer reached the record"
    assert (answer["option"], answer["label"]) == (1, SCOPE_Q[1]["options"][1]["label"]), answer
    q.close()


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


# --------------------------------------------- the blocking findings F1-F3 --
#
# Independent re-review ent-4ca09a1119c8 (report adm-beeae910cb61) on
# f4bc2396 reproduced three routes that still recorded an option answer whose
# meaning the record does not establish:
#
#   F1  a stored version 1 question whose first alternative's consequence is
#       BLANK, or is not text at all. The pinned server reports it as
#       `options[0].consequence: nonblank_string`, which withheld nothing: only
#       `required` did.
#   F2  an approval of something specific, asked through the validated door,
#       naming one exact record this Brain does not hold. The question is
#       COMPLETE; what says the owner cannot inspect it is the same read's own
#       resolution of that id.
#   F3  an answer that was attempted before the record was read this way and
#       whose outcome is unknown. "Send again" sent the kept choice, after the
#       page knew the question needed clarifying.
#
# Each is answered here with the pinned Python's own payload for it
# (`correction_cases`, captured the same way as the cases above), in a
# disposable Brain. For F2 that includes `needs-you/about`'s own
# `question_references` -- this server does not project them, and the client
# must be right against the one that does.

CORRECT = WIRE["correction_cases"]
GONE_ID = "ent-deadbeef999999"


def corrected(world):  # noqa: F811
    """One conversation holding each of the three, side by side with a control
    that must keep every control it has: the same approval of something
    specific, naming a record this Brain DOES hold."""
    from mentis.worker import _decision_form
    cv, owner = world["cv"], world["who"]["@brian"]
    cid = a_conversation(world, "Blocking findings F1-F3")
    coach, parent, _grant = _coordinator(world, cid)
    request_turn = cv._act(parent)["turn"]

    def act(name, **kw):
        kw.setdefault("caused_by", parent)
        return cv.record_act(actor=coach, act=name, execution="inst-f1f3", runtime="claude", **kw)

    def on(words):
        return cv.say(cid, coach, [text(words)], addressed_to=[owner], replies_to=request_turn)

    def form(words, question):
        return _decision_form(
            cv, {"because": question["because"], "questions": [question], "on": on(words)},
            actor=coach, parent=parent, here=cid, wrote=None, act=act, where=lambda c: c,
            execution="inst-f1f3")

    out = {"cid": cid}

    # F1: asks on their own posts, recorded with the stored detail the pinned
    # server reported `nonblank_string` for. `cv.expect` is the historical
    # door: the form constructor normalises a blank consequence away and the
    # authoring validator refuses one, so neither of them produces this.
    for name in ("blank_consequence_standalone", "nontext_consequence_standalone"):
        src = CORRECT[name]["expectation"]
        post = on("Approve rebuilding the fixture search index?")
        out[name] = cv.expect(
            post, of=owner, by=coach, kind="decision", because=src["because"],
            detail={"question": "Approve rebuilding the fixture search index?",
                    "options": src["options"], "presentation": src["presentation"]})

    # F2: the approval of something specific, twice -- the exact record it
    # names absent from this Brain, and present in it.
    out["held"] = cv.say(cid, coach, [text("Candidate design: fixture v1.\n\nBuild only; no deployment.")])
    for name in ("required_material_unavailable", "required_material_available"):
        src = CORRECT[name]["expectation"]
        f = form("Decide the fixture candidate design.",
                 {k: src[k] for k in ("question", "because", "options")})
        out[name] = f["form"]
        out[name + "_question"] = f["questions"][0]["expectation"]

    # F3: a question of a form whose first alternative has no consequence at
    # all -- the subject of R1-A, and what the attempted answer was made on.
    src = CLARIFY["action_approval_missing_consequence"]["question"]
    f = form("A stored approval, one consequence missing.",
             {k: src[k] for k in ("question", "because", "options")})
    out["attempted"] = f["form"]
    out["attempted_question"] = f["questions"][0]["expectation"]
    return out


def _corrected_wire(context, w, masked=None):
    """Each question answered as Python 2f3c2210 answered it, and -- for the
    two approvals of something specific -- `needs-you/about`'s own resolution
    of the exact record each names, keyed by THIS Brain's expectation id.

    The available one is re-keyed to a post this Brain really holds, so what is
    replayed is the pinned server's shape and not its Brain's contents. IT
    DECLARES AND RESOLVES THE SAME ID: the question's own declaration is
    re-keyed with the read's resolution of it, as `_pinned` does in
    `test_shared_host_material_browser`. An approval that declares one id and
    is answered about another establishes nothing for that question (B1
    `ANOTHER_ID`), which is a DIFFERENT case and is checked there -- and since
    the form now reads the material at the sending seam in every host,
    including this one (combined review F1), a payload that disagreed with
    itself would hold the control's own answer rather than offering it.

    `masked`, where given, is an expectation id answered as COMPLETE instead:
    the one intervention, used only to establish an answer attempted with the
    earlier page. It is turned off before the correction is tested."""
    status = {}
    refs = {}
    for name in ("blank_consequence_standalone", "nontext_consequence_standalone"):
        status[w[name]] = CORRECT[name]["expectation"]
    for name in ("required_material_unavailable", "required_material_available"):
        qid = w[name + "_question"]
        src = json.loads(json.dumps(CORRECT[name]["expectation"]))
        declared = json.loads(json.dumps(CORRECT[name]["question_reference"]))
        declared["expectation"] = qid
        if name == "required_material_available":
            # the same shape, naming a record THIS Brain holds
            src["presentation"]["primary"]["id"] = w["held"]
            declared["presentation"]["primary"]["id"] = w["held"]
            declared["primary"]["id"] = w["held"]
            declared["primary"]["availability"]["id"] = w["held"]
            declared["primary"]["availability"]["post"] = w["held"]
        status[qid] = src
        refs[qid] = declared
    status[w["attempted_question"]] = CLARIFY["action_approval_missing_consequence"]["expectation"]

    def put(d, key):
        if masked and masked.get("on") and key == masked["id"]:
            d["presentation_status"] = {"state": "complete", "problems": []}
            return
        src = status.get(key)
        if not src:
            return
        if "presentation" in src:
            d["presentation"] = src["presentation"]
        d["presentation_status"] = src["presentation_status"]

    def handle(route):
        res = route.fetch()
        try:
            body = res.json()
        except Exception:                                   # noqa: BLE001
            return route.fulfill(response=res)
        for f in body.get("decision_forms") or ():
            for q in f.get("questions") or ():
                put(q, q.get("expectation"))
        for e in body.get("expectations") or ():
            put(e, e.get("id"))
        # the declared reference and how it stands now, as the pinned read says
        for item in body.get("about") or ():
            declared = refs.get(item.get("id"))
            if declared:
                item["question_references"] = [declared]
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context.route("**/fluid/api/decisions*", handle)
    context.route("**/fluid/api/needs-you/**", handle)


@pytest.mark.parametrize("case,said", [
    ("blank_consequence_standalone", "was recorded with nothing in it"),
    ("nontext_consequence_standalone", "was not recorded as words"),
])
def test_f1_a_consequence_recorded_with_nothing_in_it_offers_no_affirmative(chrome, world, case, said):  # noqa: F811
    """F1. The record holds a consequence for Approve -- three spaces, or a
    number -- so the backend says `nonblank_string` and not `required`. To a
    person both are one thing: what choosing Approve leads to is not in the
    record. Neither offers it as an answer, on Decide or on "+ continue"."""
    w = corrected(world)
    q = Quiet(chrome, world, w, width=360, height=900)
    _corrected_wire(q.context, w)
    _reopen(q)
    card = q.answer_here(w[case])
    asked = _question(card)
    assert asked.get_attribute("data-presentation") == "incomplete"
    asked.locator("[data-clarify-needed]").wait_for(timeout=20000)

    gaps = _gaps(asked)
    assert any("Choice A" in g and "Approve" in g and said in g for g in gaps), gaps
    for g in gaps:
        assert "presentation." not in g and "nonblank" not in g, g
    assert said in asked.locator("[data-no-consequence]").inner_text()

    # EVERY RECORDED CHOICE IS STILL THERE, AND NONE IS A CONTROL
    wording = asked.locator("[data-wording-only]")
    assert wording.get_attribute("data-wording-only") == "2"
    assert wording.locator("[role='radio'], button, input").count() == 0
    assert "Approve" in wording.inner_text()
    assert "Return the plan before rebuilding." in wording.inner_text()
    assert card.locator("[data-option='0'][role='radio']").count() == 0

    # AND NOTHING SENDS ONE: not the wording, not Decide, not a forced Decide,
    # and "+ continue" -- the composer's other path -- is not offered at all.
    sent = []
    q.page.on("request", lambda r: sent.append(r.post_data or "")
              if r.method == "POST" and "/turns" in r.url else None)
    wording.locator(".rb-dec-option").first.click()
    assert card.locator(".rb-dec-foot .btn.primary").is_disabled()
    assert card.locator(".rb-dec-foot button", has_text="+ continue").count() == 0
    card.locator(".rb-dec-foot .btn.primary").evaluate("el => { el.disabled = false; el.click() }")
    q.page.wait_for_timeout(400)
    assert sent == [], sent
    state = world["cv"].expectation_state(w[case])
    assert state["response_present"] is False and not state.get("answer")

    # THE WAYS OUT ARE STILL THERE, AND IT FITS A NARROW SCREEN
    assert len(_radios(asked)) == 2, _radios(asked)
    assert asked.locator("[data-option='own']").count() == 1
    assert "Withdraw with a clarification reason" in asked.inner_text()
    assert q.page.evaluate(
        "() => { const f = document.querySelector('.rb-form'); const d = document.scrollingElement;"
        " return [f.scrollWidth - f.clientWidth, d.scrollWidth - d.clientWidth] }") == [0, 0]
    q.close()


def test_f2_required_exact_material_that_cannot_be_inspected_offers_no_affirmative(chrome, world):  # noqa: F811
    """F2. The question records everything the contract asks of it -- the
    backend says COMPLETE, with no problems at all -- and the one exact record
    it names is not in this Brain. The page already drew that; now it joins the
    two, and the choices of an approval of material nobody can look at are
    wording. The control beside it, the same question naming a record this
    Brain holds, keeps every control it had."""
    w = corrected(world)
    q = Quiet(chrome, world, w, width=360, height=900)
    _corrected_wire(q.context, w)
    _reopen(q)

    card = q.answer_here(w["required_material_unavailable"])
    asked = _question(card)
    # the question itself is complete: this is not a missing field
    assert asked.get_attribute("data-presentation") == "complete"
    asked.locator("[data-clarify-needed]").wait_for(timeout=20000)
    # WHAT IT IS ABOUT IS SAID FIRST, in the asker's words and the record's reason
    said = _gaps(asked)
    assert said and "the exact candidate design" in said[0], said
    assert "This Brain holds nothing with this id." in said[0], said
    for g in said:
        assert "presentation." not in g, g
    # and the source itself is shown as unavailable, not as something to open
    assert card.locator(f"[data-ref-id='{GONE_ID}'][data-ref-state='missing']").count() >= 1
    assert card.locator(f"[data-ref-id='{GONE_ID}'] button").count() == 0

    wording = asked.locator("[data-wording-only]")
    assert wording.get_attribute("data-wording-only") == "2"
    assert "Build this design" in wording.inner_text()
    assert card.locator("[data-option='0'][role='radio']").count() == 0
    sent = []
    q.page.on("request", lambda r: sent.append(r.post_data or "")
              if r.method == "POST" and "/turns" in r.url else None)
    wording.locator(".rb-dec-option").first.click()
    assert card.locator(".rb-dec-foot .btn.primary").is_disabled()
    card.locator(".rb-dec-foot .btn.primary").evaluate("el => { el.disabled = false; el.click() }")
    q.page.wait_for_timeout(400)
    assert sent == [], sent
    state = world["cv"].expectation_state(w["required_material_unavailable_question"])
    assert state["response_present"] is False and not state["answer"]
    assert asked.locator("[data-option='own']").count() == 1
    assert "Withdraw with a clarification reason" in asked.inner_text()

    # THE CONTROL: the same question, naming a record this Brain holds.
    other = q.answer_here(w["required_material_available"])
    enough = _question(other)
    assert enough.get_attribute("data-presentation") == "complete"
    assert enough.locator("[data-clarify-needed]").count() == 0
    assert _gaps(enough) == [], _gaps(enough)
    for i, label in enumerate(("Build this design", "Revise first")):
        control = enough.locator(f"[data-option='{i}'][role='radio']")
        assert control.count() == 1 and control.is_enabled()
        assert label in control.inner_text()
    _choose(enough, 0, "")
    other.locator(".rb-dec-foot .btn.primary").click()
    cv = world["cv"]
    qid = w["required_material_available_question"]
    for _ in range(60):
        if cv.expectation_state(qid)["answer"]:
            break
        q.page.wait_for_timeout(500)
    answer = cv.expectation_state(qid)["answer"]
    assert answer, "an approval whose exact material is there is still answered by choosing"
    assert (answer["option"], answer["label"]) == (0, "Build this design"), answer
    q.close()


def test_f3_an_attempted_choice_is_not_sent_again_once_clarification_is_known(chrome, world):  # noqa: F811
    """F3. An answer attempted with the earlier page, whose outcome the server
    never confirmed: the first request is aborted before it leaves, so nothing
    was recorded and the page correctly keeps it as unknown. The real payload
    is then restored, without a reload, and the question reads as needing
    clarifying.

    "Send again" is the one path left that could record that choice. It is not
    offered, and the handler holds it. NOTHING IS GIVEN UP BY HOLDING IT: the
    words stay exactly as typed, the operation key is unchanged, and both reads
    -- Check again, and Change it first -- are still there, so an answer that
    WAS recorded after all is found and said rather than lost."""
    w = corrected(world)
    q = Quiet(chrome, world, w)
    mask = {"id": w["attempted_question"], "on": True}
    _corrected_wire(q.context, w, masked=mask)
    _reopen(q)
    card = q.answer_here(w["attempted"])
    words = "An answer attempted before the correction."
    _choose(card, 0, words)
    assert card.locator("[data-clarify-needed]").count() == 0

    def fail_send(route):
        if route.request.method == "POST":
            route.abort()
        else:
            route.continue_()

    q.page.route("**/api/conversations/*/turns", fail_send)
    card.locator(".rb-dec-foot .btn.primary").click()
    card.locator("[data-sent='unknown']").wait_for(timeout=20000)
    assert world["cv"].expectation_state(w["attempted_question"])["response_present"] is False
    q.page.unroute("**/api/conversations/*/turns", fail_send)

    # THE REAL PAYLOAD, with no reload
    mask["on"] = False
    card.locator(".rb-dec-q[data-presentation='incomplete']").wait_for(timeout=20000)
    card.locator("[data-resend-held]").wait_for(timeout=20000)
    assert card.locator("[data-resend]").count() == 0, "the path F3 recorded through"
    assert "not sent again from here" in card.locator("[data-resend-held]").inner_text()

    # WHAT WAS ATTEMPTED IS STILL IN FRONT OF THE OWNER, as it was sent: the
    # owner's own words in the field, and the choice it was sent with.
    assert card.locator("textarea.rb-dec-words").input_value() == words
    assert "may or may not have been recorded" in card.locator("[data-sent='unknown']").inner_text()
    assert card.locator("[data-option='0']").first.get_attribute("aria-checked") == "true"
    # and both reads are still offered
    assert card.locator("[data-check]").count() == 1
    assert card.locator("[data-take-back]").count() == 1

    # NOTHING RECORDS IT: the read that is offered writes nothing, and the
    # question is still open in the record afterwards.
    sent = []
    q.page.on("request", lambda r: sent.append(r.post_data or "")
              if r.method == "POST" and "/turns" in r.url else None)
    card.locator("[data-check]").click()
    q.page.wait_for_timeout(800)
    assert sent == [], sent
    assert world["cv"].expectation_state(w["attempted_question"])["response_present"] is False
    q.close()


# ------------------- F1: THE SEAM THAT SENDS, IN THE HOST THAT RESOLVES ------
# Combined review finding F1 (ent-b45998589533, report adm-44c2ee329473).
#
# Quiet Chat's Needs you resolves every reference of the request it draws and
# hands the decision form that resolution (`quiet2/needs/NeedsAbout`
# `refWordsFor`), so the panel above the form and the form itself say one thing
# about one reference. But it is the resolution of the moment the PANEL was
# read. At 678876d5 the form excluded every question of such a form from its
# own read, and `freshlyHeld` returned at once for such a host, so Decide and
# Send again both went out with no read of the exact material in between: an
# approval whose one exact record had been deleted since the panel last read
# was recorded, option and label, with zero reference reads in between.
#
# The form now makes ONE AWAITED READ PER ATTEMPT in every host, and sends
# nothing on a read that does not establish that question's own exact record.
# Nothing else moves: the draft, the question id, the operation key and
# exactly-once recording are untouched, and a read that DOES establish it is
# answered by choosing exactly as before.
#
# The panel's own reads are `about?items=1`; the form's own read is
# `about?ids=<question>`. The tests below tell them apart by that, so what is
# asserted is the form's read and not the panel's.

#: what the one exact record this Brain holds actually says
SOURCE_WORDS = "Exact candidate design: build only, no deployment."
#: the owner's half-made answer, two lines, which nothing here may lose
SEAM_WORDS = "Approve only this exact design.\nSecond line, kept."


def _approval(world, name):  # noqa: F811
    """ONE STRICT `artifact_approval` OF ONE EXACT RECORD THIS BRAIN HOLDS,
    authored through the production door (`request_decision`) -- no replay, no
    historical constructor, no weakened validation."""
    from mentis.worker import _operate
    from mentis.web import _surface
    from tests.decision_descriptors import question

    cv = world["cv"]
    cid = a_conversation(world, name)
    coach, _parent, grant = _coordinator(world, cid)
    source = cv.say(cid, coach, [text(SOURCE_WORDS)])
    item = question("Build the exact candidate design?")
    item["presentation"]["type"] = "artifact_approval"
    item["presentation"]["primary"] = {"kind": "record", "id": source, "label": "Exact candidate design"}
    item["presentation"].pop("primary_reason", None)
    made = _operate(_surface(world["state"]), "request_decision", {"questions": [item]}, grant)
    _operate(_surface(world["state"]), "respond", {"text": "The candidate design is ready."}, grant)
    return {"cid": cid, "form": made["form"], "qid": made["questions"][0]["expectation"],
            "source": source}


def _read(world, path):  # noqa: F811
    import urllib.request
    from tests.conftest import owner_headers
    req = urllib.request.Request(world["base"] + path,
                                 headers={"X-Mentis-Client": "1", **owner_headers()})
    with urllib.request.urlopen(req) as got:
        return json.load(got)


def _availability(world, qid):  # noqa: F811
    """How the backend itself resolves the one record that question declares."""
    about = _read(world, "/fluid/api/needs-you/about?ids=" + qid)
    return about["about"][0]["question_references"][0]["primary"]["availability"]


def _watch(q):
    """The form's own material reads and every post this page makes, from the
    moment this is called."""
    seam, writes = [], []
    q.page.on("request", lambda r: seam.append(r.url)
              if "/needs-you/about?ids=" in r.url else None)
    q.page.on("request", lambda r: writes.append(r.post_data_json)
              if r.method == "POST" and "/turns" in r.url else None)
    return seam, writes


def _cached_panel(world, q):  # noqa: F811
    """THE PANEL KEEPS THE RESOLUTION IT LAST READ -- which is the condition the
    finding is about, pinned so it cannot race. Its list and its details are
    answered from what the backend said a moment ago; THE FORM'S OWN READ
    (`about?ids=`) is passed straight through, because it is the thing under
    test."""
    items = _read(world, "/fluid/api/needs-you/items")
    about = _read(world, "/fluid/api/needs-you/about?items=1")
    q.context.route("**/fluid/api/needs-you/items*", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(items)))
    q.context.route("**/fluid/api/needs-you/about*", lambda route: route.continue_()
                    if "ids=" in route.request.url else route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(about)))


def _kept(q, qid):
    """The attempted answer this browser is holding for that question."""
    return q.page.evaluate(
        "id => Object.entries(localStorage)"
        ".filter(([k]) => k.startsWith('mentis.decisions.sent.v2:'))"
        ".map(([, v]) => JSON.parse(v)).find(v => v.ask === id) || null", qid)


def _drafted(q, w):
    """The form, unfolded, with the first option chosen and two lines typed."""
    row = q.answer_here(w["form"])
    row.locator("[data-primary='ref'] button[data-ref-id]").wait_for(timeout=20000)
    _choose(row.locator(".rb-dec-q").first, 0, SEAM_WORDS)
    return row


def _still_open_with_the_draft(q, world, w, row):  # noqa: F811
    """NOTHING WAS RECORDED AND NOTHING WAS LOST: the question is open in the
    record, and the owner's own two lines are still in front of them."""
    q.page.wait_for_timeout(400)
    assert world["cv"].expectation_state(w["qid"])["response_present"] is False
    row.locator("[data-wording-only]").wait_for(timeout=20000)
    assert row.locator("[role='radio'][data-option='0']").count() == 0
    row.locator("[role='radio'][data-option='own']").click()
    assert row.locator("textarea.rb-dec-words").input_value() == SEAM_WORDS


def test_quiet_answers_an_approval_whose_exact_record_is_there_by_choosing(world, chrome):  # noqa: F811
    """THE POSITIVE CASE FIRST, because the guard must cost the ordinary path
    nothing: the record is there, the read establishes it, and the choice is
    recorded -- option and label as declared, once, with one read made for the
    attempt."""
    w = _approval(world, "Quiet seam: the record is there")
    q = Quiet(chrome, world, {"cid": w["cid"]})
    seam, writes = _watch(q)
    try:
        row = _drafted(q, w)
        assert _availability(world, w["qid"])["state"] == "ok"
        del seam[:]
        row.locator(".rb-dec-foot .btn.primary").click()
        cv = world["cv"]
        for _ in range(80):
            if cv.expectation_state(w["qid"])["answer"]:
                break
            q.page.wait_for_timeout(250)
        got = cv.expectation_state(w["qid"])["answer"]
        assert got and (got["option"], got["label"]) == (0, "Build"), got
        # ONE awaited read was made for this attempt, and ONE post recorded it
        assert len(seam) == 1, seam
        assert len(writes) == 1, writes
        assert writes[0]["chose"] == {"expectation": w["qid"], "option": 0, "label": "Build"}
    finally:
        q.close()


def test_quiet_does_not_approve_a_record_deleted_since_the_panel_read_it(world, chrome):  # noqa: F811
    """THE FINDING ITSELF, at Decide. The panel keeps the resolution it read
    before the deletion and still hands it to the form; the record is gone, the
    backend says so, and the form reads it for itself before sending anything.
    Nothing is recorded, nothing is claimed beyond what the read came to, and
    the owner's two lines are kept."""
    from mentis.conversation import versions
    w = _approval(world, "Quiet seam: deleted before Decide")
    q = Quiet(chrome, world, {"cid": w["cid"]})
    seam, writes = _watch(q)
    try:
        row = _drafted(q, w)
        _cached_panel(world, q)
        versions.delete(world["cv"], w["source"], by=world["who"]["@brian"],
                        because="the exact design was withdrawn")
        assert _availability(world, w["qid"])["state"] == "deleted"
        del seam[:]
        row.locator(".rb-dec-foot .btn.primary").click()
        # what the form's OWN read came to is what the question now says
        row.locator("[data-clarify-needed='record']").wait_for(timeout=20000)
        assert seam, "no material read was made for this attempt"
        assert writes == [], writes
        assert "This post was deleted." in row.inner_text()
        _still_open_with_the_draft(q, world, w, row)
    finally:
        q.close()


def test_quiet_does_not_send_an_attempted_choice_again_after_the_record_goes(world, chrome):  # noqa: F811
    """AND THE SAME SEAM ON THE RECOVERY PATH. An attempt whose outcome is not
    known is sent again under its own key -- except that how the one exact thing
    it approves stands is read again first. Here it was deleted in between, so
    it is held: nothing is sent, nothing is given up, and the key and the words
    are exactly as they were."""
    from mentis.conversation import versions
    w = _approval(world, "Quiet seam: deleted before Send again")
    q = Quiet(chrome, world, {"cid": w["cid"]})
    seam, writes = _watch(q)
    try:
        row = _drafted(q, w)
        _cached_panel(world, q)
        # the first attempt ends without an answer: nothing is known of it
        q.context.route("**/api/conversations/*/turns", lambda route: route.abort())
        q.context.route("**/api/operations*", lambda route: route.abort())
        row.locator(".rb-dec-foot .btn.primary").click()
        row.locator("[data-sent='unknown']").wait_for(timeout=20000)
        first = _kept(q, w["qid"])
        assert first and first["text"] == SEAM_WORDS, first
        assert world["cv"].expectation_state(w["qid"])["response_present"] is False
        # delivery is unblocked, so only the guard can hold the second attempt
        q.context.unroute("**/api/conversations/*/turns")
        versions.delete(world["cv"], w["source"], by=world["who"]["@brian"],
                        because="the exact design was withdrawn")
        assert _availability(world, w["qid"])["state"] == "deleted"
        del seam[:]
        del writes[:]
        row.locator("[data-resend]").click()
        row.locator("[data-resend-held]").wait_for(timeout=20000)
        assert seam, "no material read was made for the second attempt"
        assert row.locator("[data-resend]").count() == 0
        q.page.wait_for_timeout(400)
        assert writes == [], writes
        assert world["cv"].expectation_state(w["qid"])["response_present"] is False
        # the attempt already made is untouched: same key, same words
        again = _kept(q, w["qid"])
        assert again and again["op"] == first["op"] and again["text"] == SEAM_WORDS, again
        assert row.locator("textarea.rb-dec-words").input_value() == SEAM_WORDS
        # and both reads of what became of it are still offered
        assert row.locator("[data-check]").count() == 1
        assert row.locator("[data-take-back]").count() == 1
    finally:
        q.close()


def test_quiet_sends_nothing_on_a_seam_read_that_failed(world, chrome):  # noqa: F811
    """A READ THAT DID NOT FINISH IS NOT AN ANSWER. It is held, and nothing
    whatever is claimed about the record: not that this Brain holds it, and not
    that it does not."""
    w = _approval(world, "Quiet seam: the read failed")
    q = Quiet(chrome, world, {"cid": w["cid"]})
    seam, writes = _watch(q)
    try:
        row = _drafted(q, w)
        _cached_panel(world, q)
        q.context.route("**/fluid/api/needs-you/about?ids=*", lambda route: route.fulfill(
            status=500, content_type="application/json",
            body=json.dumps({"error": "the fixture server refused this read"})))
        del seam[:]
        row.locator(".rb-dec-foot .btn.primary").click()
        note = row.locator("[data-clarify-needed='pending']")
        note.wait_for(timeout=20000)
        assert seam, "no material read was attempted"
        assert writes == [], writes
        said = row.inner_text()
        assert "Nothing here says this Brain does or does not hold it." in said
        for word in ("This Brain holds nothing with this id.", "This post was deleted."):
            assert word not in said, word
        _still_open_with_the_draft(q, world, w, row)
    finally:
        q.close()


def test_quiet_waits_for_the_seam_read_before_it_records_anything(world, chrome):  # noqa: F811
    """THE CHECK IS AWAITED, not started and forgotten. While the read is on its
    way nothing is recorded; when it answers -- here, that the record is gone --
    the choice is held."""
    from mentis.conversation import versions
    w = _approval(world, "Quiet seam: the read is awaited")
    q = Quiet(chrome, world, {"cid": w["cid"]})
    seam, writes = _watch(q)
    caught: list = []
    try:
        row = _drafted(q, w)
        _cached_panel(world, q)
        q.context.route("**/fluid/api/needs-you/about?ids=*", lambda route: caught.append(route))
        versions.delete(world["cv"], w["source"], by=world["who"]["@brian"],
                        because="the exact design was withdrawn")
        del seam[:]
        row.locator(".rb-dec-foot .btn.primary").click()
        for _ in range(40):
            if caught:
                break
            q.page.wait_for_timeout(100)
        assert len(caught) == 1, caught
        # the attempt is waiting on it: nothing has been posted or recorded
        q.page.wait_for_timeout(1200)
        assert writes == [], writes
        assert world["cv"].expectation_state(w["qid"])["response_present"] is False
        # and when it answers, what it answered decides
        caught.pop().continue_()
        row.locator("[data-clarify-needed='record']").wait_for(timeout=20000)
        assert writes == [], writes
        _still_open_with_the_draft(q, world, w, row)
    finally:
        q.close()


def test_quiet_reads_no_material_for_a_question_that_approves_no_exact_record(world, chrome):  # noqa: F811
    """WHAT IS READ FOR, AND NOTHING ELSE. An ordinary choice between
    alternatives declares no approval of one exact record, so no seam read is
    made for it at all and every control it had is answered as before: the
    guard costs the questions it is not about nothing."""
    from mentis.worker import _operate
    from mentis.web import _surface
    from tests.decision_descriptors import question

    cv = world["cv"]
    cid = a_conversation(world, "Quiet seam: nothing to read")
    coach, _parent, grant = _coordinator(world, cid)
    item = question("Which fixture branch should remain?")
    item["presentation"]["type"] = "choice"
    item["presentation"]["primary_reason"] = "This selects a fixture branch, not an artifact."
    made = _operate(_surface(world["state"]), "request_decision", {"questions": [item]}, grant)
    _operate(_surface(world["state"]), "respond", {"text": "Two fixture branches remain."}, grant)
    qid = made["questions"][0]["expectation"]
    q = Quiet(chrome, world, {"cid": cid})
    seam, writes = _watch(q)
    try:
        row = q.answer_here(made["form"])
        _choose(row.locator(".rb-dec-q").first, 0, "Keep the first branch.")
        row.locator(".rb-dec-foot .btn.primary").click()
        for _ in range(80):
            if cv.expectation_state(qid)["answer"]:
                break
            q.page.wait_for_timeout(250)
        got = cv.expectation_state(qid)["answer"]
        assert got and got["option"] == 0, got
        assert seam == [], seam
        assert len(writes) == 1, writes
    finally:
        q.close()
