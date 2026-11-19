"""A Needs You answer has an identity, is recorded once, and the record says what it did.

The incident (TEST, 2026-11-19): the owner answered a decision about findings in their own words.
The post was recorded (#423), the decision correctly stayed open (a decision about findings is
made by a choice, not by words), and the form said "Sent ... the record has not shown it yet",
then "Nothing sent yet" after a refresh. Nothing told the owner their words were recorded and had
not decided anything, and nothing gave the submission an identity a retry could be recognised by.

These are the server's half: the keyed post, the read that says what a keyed post came to, and
the decision read a form is drawn from. The form's half is
apps/fluid-web/tests/fluid_decision_outbox_unit.mjs and tests/test_needs_you_submission_browser.py.
"""

import json
import urllib.error
import urllib.request

from mentis.operational import ask_about_findings, trunk_of
from tests.test_manual_session import _session, world  # noqa: F401


def call(world, path, payload=None):
    req = urllib.request.Request(
        world["url"] + path, data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Mentis-Client": "1"},
        method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"http": e.code, **json.loads(e.read() or b"{}")}


def a_decision_about_findings(world, findings=2):
    """Work that found things along the way, and the one decision Mentis asks the OWNER about
    them. Returns the conversation, the asking post, the decision and the findings."""
    st = world["st"]
    grant, op = _session(world)
    _, opened = op("open_conversation", name="Found along the way")
    _, request = op("record_request", conversation=opened["conversation"], text="root", follow_up="ask")
    root = request["expectation"]
    found = [op("record_discovered_work", under=root, work=f"finding {i + 1}")[1]["expectation"]
             for i in range(findings)]
    trunk = trunk_of(st.brain, root)
    asked = ask_about_findings(
        st.brain, found, conversation=opened["conversation"], by=grant["participant"],
        owner=world["owner"], caused_by=root, originating_turn=trunk["originating_turn"],
        question="What should happen to the things found along the way?")
    exp = st.cv._act(asked["expectation"])
    return {"conversation": exp["conversation"], "post": exp["turn"], "decision": asked["expectation"],
            "findings": found}


def reply(world, d, words, op, **extra):
    """What the decision form posts for an answer in the owner's own words."""
    return {"author": world["owner"], "text": words, "parts": [{"type": "text", "text": words}],
            "replies_to": d["post"], "addressed_to": [], "action": "record-only", "dispatch": [],
            "topics": [], "because": f"answering expectation {d['decision']}", "op": op, **extra}


def the_decision(world, d):
    read = call(world, f"/fluid/api/decisions?post={d['post']}")
    return next(e for e in read["expectations"] if e["id"] == d["decision"])



def turns(world, d):
    return call(world, f"/api/conversations/{d['conversation']}")["turns_total"]


def test_words_alone_are_recorded_and_the_read_says_they_did_not_decide(world):
    """The incident, as the record holds it: the reply IS recorded, the decision IS still open,
    and the read a form is drawn from says both -- before and after any refresh."""
    d = a_decision_about_findings(world)
    before = the_decision(world, d)
    assert before["response_present"] is False and before["answered_by"] is None
    assert any(o.get("per_finding") or o.get("selections") for o in before["options"]), \
        "its options carry what happens to the findings: that is how a form knows words alone leave it open"
    got = call(world, f"/api/conversations/{d['conversation']}/turns",
               reply(world, d, "Pursue the first, keep the second deferred.", "decision:a:1"))
    assert got.get("turn") and isinstance(got.get("number"), int), got
    after = the_decision(world, d)
    assert after["response_present"] is False, "prose selects nothing: the decision is still owed"
    assert after["answered_by"]["turn"] == got["turn"] and after["answered_by"]["number"] == got["number"]
    assert after["answered_by"]["said"].startswith("Pursue the first")
    # and nothing was decided or started by it
    cv = world["st"].cv
    assert not [a for a in cv.history(act="expectation-met") if "selections" in (a["detail"] or {})]


def test_the_same_submission_sent_again_is_one_post(world):
    """A retry, a duplicate click or a resend after a lost acknowledgment carries the same
    operation key: the first answer is returned and nothing is written again."""
    d = a_decision_about_findings(world)
    body = reply(world, d, "My words.", "decision:a:2")
    n = turns(world, d)
    first = call(world, f"/api/conversations/{d['conversation']}/turns", body)
    again = call(world, f"/api/conversations/{d['conversation']}/turns", body)
    third = call(world, f"/api/conversations/{d['conversation']}/turns", body)
    assert first["turn"] == again["turn"] == third["turn"] and again.get("replayed") is True
    assert first["number"] == again["number"]
    assert turns(world, d) == n + 1, "three sends, one post"
    # the same key for something else is refused, and writes nothing
    other = call(world, f"/api/conversations/{d['conversation']}/turns",
                 reply(world, d, "Different words.", "decision:a:2"))
    assert "already used for a different request" in other.get("error", ""), other
    assert turns(world, d) == n + 1


def test_what_a_keyed_post_came_to_can_be_asked_without_writing(world):
    d = a_decision_about_findings(world)
    owner = world["owner"]
    assert call(world, f"/api/operations?op=decision:a:3&author={owner}") == {
        "op": "decision:a:3", "author": owner, "recorded": False, "voided": False}
    n = turns(world, d)
    got = call(world, f"/api/conversations/{d['conversation']}/turns", reply(world, d, "Words.", "decision:a:3"))
    said = call(world, f"/api/operations?op=decision:a:3&author={owner}")
    assert said["recorded"] is True
    assert said["result"]["turn"] == got["turn"] and said["result"]["number"] == got["number"]
    # asking is a read: asked many times, still one post; and it is the author's own key
    for _ in range(3):
        call(world, f"/api/operations?op=decision:a:3&author={owner}")
    assert turns(world, d) == n + 1
    somebody_else = world["st"].cv.create_participant("@Somebody")
    assert call(world, f"/api/operations?op=decision:a:3&author={somebody_else}")["recorded"] is False
    assert "name the operation key" in call(world, "/api/operations?op=decision:a:3").get("error", "")
    assert call(world, f"/api/operations?op=never-sent&author={owner}")["recorded"] is False


def test_a_choice_sent_twice_decides_once_and_starts_its_work_once(world):
    """The authority-bearing case: a duplicate of a CHOICE must not decide twice or start the
    pursued finding as work twice."""
    d = a_decision_about_findings(world)
    cv = world["st"].cv
    opts = the_decision(world, d)["options"]
    pursue_all = next(i for i, o in enumerate(opts) if set((o.get("selections") or {}).values()) == {"pursue"})
    label = opts[pursue_all]["label"]
    body = reply(world, d, label, "decision:a:4",
                 chose={"expectation": d["decision"], "option": pursue_all, "label": label})
    first = call(world, f"/api/conversations/{d['conversation']}/turns", body)
    assert first.get("turn"), first

    def state():
        return (len([a for a in cv.history(act="expectation-met") if "selections" in (a["detail"] or {})]),
                len(cv.history(act="execution-started")), len(cv.history(act="expectation-recorded")),
                turns(world, d))
    once = state()
    assert once[0] == 1, "decided once"
    again = call(world, f"/api/conversations/{d['conversation']}/turns", body)
    assert again["turn"] == first["turn"] and again.get("replayed") is True
    assert state() == once, "the repeat decided nothing, asked nothing and started nothing"
    closed = the_decision(world, d)
    assert closed["response_present"] is True and closed["answered_by"]["turn"] == first["turn"]
    assert closed["answered_by"]["chose"]["option"] == pursue_all


def test_a_second_different_answer_after_the_decision_closed_does_not_decide_again(world):
    """Two tabs, two different choices: the second is a new operation, and the record refuses it
    rather than deciding the same findings twice."""
    d = a_decision_about_findings(world)
    cv = world["st"].cv
    opts = the_decision(world, d)["options"]

    def choose(kind, op):
        i = next(i for i, o in enumerate(opts) if set((o.get("selections") or {}).values()) == {kind})
        return call(world, f"/api/conversations/{d['conversation']}/turns",
                    reply(world, d, opts[i]["label"], op,
                          chose={"expectation": d["decision"], "option": i, "label": opts[i]["label"]}))
    assert choose("defer", "decision:a:5").get("turn")
    second = choose("dismiss", "decision:a:6")
    decided = [a for a in cv.history(act="expectation-met") if "selections" in (a["detail"] or {})]
    assert len(decided) == 1 and set(decided[0]["detail"]["selections"].values()) == {"defer"}, \
        (second, [a["detail"] for a in decided])


def test_giving_an_unanswered_submission_up_is_final_either_way(world):
    """"Not recorded yet" is not "will not be recorded": the request may still be on its way.
    Giving it up is one transaction on the server, after which exactly one thing is true."""
    d = a_decision_about_findings(world)
    owner, n = world["owner"], turns(world, d)
    # never arrived: voided, and the original, turning up late, writes nothing
    assert call(world, "/api/operations/void", {"op": "decision:b:1", "author": owner}) == {
        "author": owner, "op": "decision:b:1", "recorded": False, "voided": True}
    late = call(world, f"/api/conversations/{d['conversation']}/turns",
                reply(world, d, "The first words.", "decision:b:1"))
    assert "already used for a different request" in late.get("error", "") and "turn" not in late, late
    assert turns(world, d) == n, "the given-up answer cannot surface later"
    said = call(world, f"/api/operations?op=decision:b:1&author={owner}")
    assert said["recorded"] is False and said["voided"] is True
    assert call(world, "/api/operations/void", {"op": "decision:b:1", "author": owner})["voided"] is True
    # it HAD landed: nothing changes, and its answer is returned
    got = call(world, f"/api/conversations/{d['conversation']}/turns",
               reply(world, d, "Words that landed.", "decision:b:2"))
    given = call(world, "/api/operations/void", {"op": "decision:b:2", "author": owner})
    assert given["recorded"] is True and given["voided"] is False and given["result"]["turn"] == got["turn"]
    again = call(world, f"/api/conversations/{d['conversation']}/turns",
                 reply(world, d, "Words that landed.", "decision:b:2"))
    assert again["turn"] == got["turn"] and again.get("replayed") is True, \
        "a landed post is not undone by asking to give it up"
    assert turns(world, d) == n + 1
    # and it is the author's own: no author, or one the record does not hold, is refused
    assert "error" in call(world, "/api/operations/void", {"op": "decision:b:3"})
    assert "error" in call(world, "/api/operations/void", {"op": "decision:b:3", "author": "ent-nobody"})
    assert "error" in call(world, "/api/operations/void", {"op": "", "author": owner})


def test_the_post_answer_says_what_a_choice_about_findings_did(world):
    """What the form reports as "what it did" is this, the server's own account, and nothing else."""
    d = a_decision_about_findings(world)
    opts = the_decision(world, d)["options"]
    i = next(i for i, o in enumerate(opts) if set((o.get("selections") or {}).values()) == {"defer"})
    got = call(world, f"/api/conversations/{d['conversation']}/turns",
               reply(world, d, opts[i]["label"], "decision:c:1",
                     chose={"expectation": d["decision"], "option": i, "label": opts[i]["label"]}))
    did = got["reconsidered"]
    assert len(did["deferred"]) == 2 and did["pursued"] == [] and did["dismissed"] == []
    kept = call(world, f"/api/operations?op=decision:c:1&author={world['owner']}")["result"]
    assert kept["reconsidered"]["deferred"] == did["deferred"], \
        "and a page that lost the answer can still learn it"
