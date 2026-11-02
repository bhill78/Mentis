"""The other side of the agent reads' differential: what Python's own reads say on a changed
BRAIN-SEED, with the door's words taken off, since they aren't built yet.

    agent_reads_side.py change <brain>           write what these reads have to read
    agent_reads_side.py answers <brain>          print Python's answers, as JSON
    agent_reads_side.py answers-copy <brain>     the same on a Brain copy, sampled, with nothing written
    agent_reads_side.py commit <brain>           one more post: "just after a commit"
    agent_reads_side.py digest <brain>           corpus.db's SHA-256, opening nothing but the file

BRAIN-SEED has no governed material, decision forms or response sets, so the commands that write
them either need a run in progress or the render engine. Where a real command can't be used, this
writes the same rows those commands write: the shapes are `worker.py`'s and `responses.py`'s, each
cited where it is copied, and a Python read is the judge of them either way.
"""

import hashlib
import json
import pathlib
import sqlite3
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "mentis-rules" / "tests" / "support"))

import mentis.api as api  # noqa: E402
from mentis import worker  # noqa: E402
from mentis.conversation import ladder_writes, register  # noqa: E402

import python_side  # noqa: E402

#: The time `kinds` reports, so that side and this one report one.
AT = 1793500123.456


def _text(words):
    return [{"type": "text", "text": words}]


def _turn(corpus, conversation, who, parts, addressed=()):
    """What `cv.say` writes, for parts and addresses it would check against things not here."""
    turn = corpus.write(kind="contribution", attributed_to=who,
                        body={"parts": parts, "addressed_to": list(addressed)})
    corpus.write(body={"reason": "said here"}, attributed_to=who,
                 link={"from": turn, "to": conversation, "relation": "in-conversation"})
    return turn


def _form(cv, *, by, of, conversation, on, questions, detail=None):
    """What `worker._decision_form` writes: one form under a request, one expectation a question."""
    parent = cv.expect(on, of=by, kind="request", by=of, because="the work", conversation=conversation)
    form = cv.record_act(actor=by, act="decision-form", conversation=conversation, turn=on,
                         because="decisions only the owner can make", caused_by=parent,
                         detail={"questions": len(questions), "on": on, **(detail or {})})
    asked = []
    for i, q in enumerate(questions):
        asked.append(cv.expect(on, of=of, kind="decision", by=by, because=q.get("because"),
                               caused_by=parent, conversation=conversation,
                               detail={**({"options": q["options"]} if q.get("options") else {}),
                                       "form": form, "index": i, "question": q["question"]}))
    return form, asked


def change(brain):
    corpus, cv = python_side._open(brain)
    owner = cv.resolve_participant("@r1-owner")
    agent = cv.resolve_participant("@r1-agent-renamed")
    known = python_side._named(corpus, "conversation", "R1 known conversation")
    second = python_side._named(corpus, "conversation", "R1 second conversation")
    sup = corpus.superseding_relation()

    # -- Turns with what `resolve` reads of them ------------------------------------------------
    plain = cv.say(known, owner, _text("plain words"))
    artifact = corpus.admit(source="test:agent-reads", locator="a", observed_at=1.0, payload="words",
                            attributed_to=owner)
    other = cv.say(known, agent, _text("something to point at"))
    _turn(corpus, known, agent, [
        {"type": "text", "text": "see "},
        {"type": "entry", "ref": other, "text": "this"},
        {"type": "object", "ref": other, "key": "block", "exact": "ver-1", "text": "that"},
        {"type": "object", "ref": other, "key": 7, "exact": None},
        {"type": "file", "ref": artifact},
        {"type": "other"},
    ], addressed=[owner, agent])
    # Fences: each goes to the render engine, and an unfenced one mustn't.
    cv.say(known, owner, _text("```checklist version=1 name=c\n- [ ] a\n```"))
    cv.say(known, owner, _text("  ~~~form version=1 name=f\nx\n~~~"))
    cv.say(known, owner, _text("``` python\nnot a block\n```"))
    # An anchor part, which keeps the Turn with Python.
    anchor = corpus.write(kind="anchor", attributed_to=owner,
                          body={"selector": {"type": "version", "version": plain}})
    corpus.write(body={"reason": "in"}, attributed_to=owner,
                 link={"from": anchor, "to": plain, "relation": "anchors-in"})
    _turn(corpus, known, owner, [{"type": "text", "text": "about that"},
                                 {"type": "anchor", "ref": anchor}])
    corpus.write(kind="reaction", attributed_to=agent, body={"token": "+1", "about": anchor})

    # -- Governed material, on every ground -----------------------------------------------------
    def rule(words, **fields):
        return corpus.write(kind="rule", attributed_to=owner, body={"text": words, **fields})

    standing = rule("  a standing rule  ", about="its reason")
    corpus.establish(standing, attributed_to=owner, reason="so")
    cv.place(standing, known, by=owner, because="here")
    wide = rule("a whole-Brain rule")
    corpus.establish(wide, attributed_to=owner, reason="so")
    cv.place(wide, whole_brain=True, by=owner, because="everywhere")
    persona = corpus.write(kind="persona", attributed_to=owner, body={"name": "Reviewer", "behaviour": "r"})
    corpus.establish(persona, attributed_to=owner, reason="so")
    carried = rule("a rule a Persona carries")
    cv.place(carried, persona, by=owner, because="carried")
    idle_persona = corpus.write(kind="persona", attributed_to=owner, body={"name": "Idle", "behaviour": "i"})
    cv.place(rule("placed on nothing that stands"), idle_persona, by=owner, because="carried")
    # A placement ended, which is history and not a place.
    ended_place = rule("placed, then not")
    cv.place(ended_place, second, by=owner, because="for now")
    gone = corpus.write(kind="deletion", attributed_to=owner, body={"reason": "ended"})
    corpus.write(body={"reason": "ended"}, attributed_to=owner,
                 link={"from": gone, "to": corpus.links(relation="scoped-to", frm=ended_place)[0]["id"],
                       "relation": sup})

    # Ended after it held, and replaced before it did.
    held_then = rule("held, then ended")
    corpus.establish(held_then, attributed_to=owner, reason="so")
    newer = rule("what ended it")
    corpus.write(body={"reason": "better"}, attributed_to=owner,
                 link={"from": newer, "to": held_then, "relation": sup})
    never = rule("replaced before anybody established it")
    corpus.write(body={"reason": "better"}, attributed_to=owner,
                 link={"from": rule("what replaced it"), "to": never, "relation": sup})

    # An establishment withdrawn: the link was ended, so it no longer counts.
    undone = rule("established by mistake")
    wrong = corpus.establish(undone, attributed_to=owner, reason="mistake")
    corpus.write(body={"reason": "undone"}, attributed_to=owner,
                 link={"from": corpus.write(kind="note", body={"text": "x"}, attributed_to=owner),
                       "to": wrong, "relation": sup})

    # Proposed successors, seven so a row's cap shows, one withdrawn.
    target = rule("something to replace")
    corpus.establish(target, attributed_to=owner, reason="so")
    last = None
    for n in range(7):
        last = rule(f"proposal number {n}")
        corpus.propose_supersession(last, [target], attributed_to=agent, reason=f"try {n}")
    links = corpus.links(relation=corpus.proposal_relation(), frm=last)
    corpus.write(body={"reason": "withdrawn"}, attributed_to=agent,
                 link={"from": corpus.write(kind="note", body={"text": "y"}, attributed_to=agent),
                       "to": links[0]["id"], "relation": sup})
    cv.place(last, known, by=owner, because="where it would go")

    # Adoption requests, open and declined, which is `proposed` and `recorded`.
    asked = rule("adopt this")
    ladder_writes.request(cv, by=agent, because="please", entry=asked)
    answered = rule("adopt this too")
    ladder_writes.request(cv, by=agent, because="please", entry=answered)
    request = corpus.links(relation="proposes", to=answered)[0]["id"]
    corpus.write(body={"reason": "no", "request": request}, attributed_to=owner,
                 link={"from": owner, "to": answered, "relation": "declines"})

    # Challenges: open, set aside, withdrawn.
    disputed = rule("disputed material")
    corpus.establish(disputed, attributed_to=owner, reason="so")
    for why in ("first", "second", "third"):
        ladder_writes.challenge(cv, target=disputed, because=why, by=agent)
    open_ones = corpus.links(relation="disputes", to=disputed)
    corpus.write(body={"reason": "held", "sets_aside": open_ones[0]["id"]}, attributed_to=owner,
                 link={"from": owner, "to": disputed, "relation": "supports"})
    corpus.write(body={"reason": "taken back", "dispute": open_ones[1]["id"]}, attributed_to=agent,
                 link={"from": agent, "to": disputed, "relation": "withdraws"})

    # Made by an act, named beside the row.
    made = rule("recorded by a run")
    act = cv.record_act(actor=agent, act="material-recorded", conversation=known, turn=plain)
    corpus.write(body={"reason": "made"}, attributed_to=agent,
                 link={"from": act, "to": made, "relation": "produced"})

    # A Kind that states rather than directs, one that declines standing, and one undeclared.
    lesson = corpus.write(kind="lesson", attributed_to=agent, body={"text": "a lesson"})
    corpus.establish(lesson, attributed_to=owner, reason="so")
    corpus.write(kind="lesson", attributed_to=agent, body={"text": "another, in Überblick words"})

    # -- A topic, filed and un-filed ------------------------------------------------------------
    topic = cv.open_topic(known, "Filings", attributed_to=owner)
    cv.assign_topic(plain, topic, attributed_to=owner)
    filing = cv.assign_topic(other, topic, attributed_to=owner)
    gone = corpus.write(kind="deletion", attributed_to=owner, body={"reason": "un-filed"})
    corpus.write(body={"reason": "un-filed"}, attributed_to=owner,
                 link={"from": gone, "to": filing, "relation": sup})

    # -- Decision forms: answered, withdrawn, lapsed, open, attached later ----------------------
    post = cv.say(known, agent, _text("a post asking things"))
    form, asked = _form(cv, by=agent, of=owner, conversation=known, on=post, questions=[
        {"question": "Which one?", "because": "only you know",
         "options": [{"label": "Yes", "consequence": "it goes"}, {"label": "No"}]},
        {"question": "Withdraw me?"},
        {"question": "Let me lapse"},
        {"question": "Still open\nwith a second line that isn't shown"},
    ])
    reply = cv.say(known, owner, _text("my answer"))
    cv.record_act(actor=owner, act="decision-answered", conversation=known, turn=post,
                  caused_by=asked[0], about=[reply], because="answered",
                  detail={"reply": reply, "option": 0, "label": "Yes"})
    cv.record_act(actor=owner, act="expectation-met", conversation=known, turn=post,
                  caused_by=asked[1], about=[reply], because="no longer",
                  detail={"withdrawn": True, "reply": reply})
    cv.record_act(actor=agent, act="expectation-met", conversation=known, turn=post,
                  caused_by=asked[2], because="the run ended",
                  detail={"lapsed": {"reason": "run-gone", "run": "run-one"}})
    # An answer by somebody it wasn't asked of, which answers nothing, and an act two down.
    start = cv.record_act(actor=agent, act="execution-started", conversation=known,
                          caused_by=asked[3], execution="run-three")
    cv.record_act(actor=owner, act="something-done", conversation=known, caused_by=start)

    closed_post = cv.say(known, agent, _text("a post with one question, all closed"))
    _, one = _form(cv, by=agent, of=owner, conversation=known, on=closed_post,
                   questions=[{"question": "Own words?"}])
    words = cv.say(known, owner, _text("my own words"))
    cv.record_act(actor=owner, act="decision-answered", conversation=known, turn=closed_post,
                  caused_by=one[0], about=[words], because="answered",
                  detail={"reply": words, "words": "my own words"})

    # Asked with no post, then put on the run's answer post.
    pending, _ = _form(cv, by=agent, of=owner, conversation=known, on=None,
                       questions=[{"question": "Pending?"}],
                       detail={"operation": {"action": "run", "command": "ls"}, "run": "run-two"})
    answer_post = cv.say(known, agent, _text("the run's answer post"))
    cv.record_act(actor=agent, act="decision-form-attached", conversation=known, turn=answer_post,
                  caused_by=pending, execution="run-two",
                  because="the run that asked it wrote its answer post",
                  detail={"form": pending, "post": answer_post})
    # Reassigned: the latest carrier answers it, and the first doesn't.
    moved_post = cv.say(known, agent, _text("a post whose question moved"))
    _, moved = _form(cv, by=agent, of=owner, conversation=known, on=moved_post,
                     questions=[{"question": "Who now?"}])
    cv.record_act(actor=owner, act="expectation-assigned", conversation=known, caused_by=moved[0],
                  about=[agent])
    cv.record_act(actor=owner, act="decision-answered", conversation=known, turn=moved_post,
                  caused_by=moved[0], about=[words], detail={"reply": words, "label": "Not theirs"})
    # A plain decision, on no form, for `owner_decisions`.
    cv.expect(plain, of=owner, kind="decision", by=agent, because="a reason\nand more",
              conversation=known, detail={})
    long_words = "A question " + "of many words " * 20
    cv.expect(plain, of=owner, kind="decision", by=agent, because="x", conversation=second,
              detail={"question": long_words})

    # -- A response set, written as `responses.open_set` and `answer` write it ------------------
    response_set = corpus.write(kind="response-set", attributed_to=owner, body={
        "post": plain, "part": 0, "block": "c", "mode": "shared", "holder": None})
    corpus.write(body={"reason": "on"}, attributed_to=owner,
                 link={"from": response_set, "to": plain, "relation": "responds-to"})
    for n in range(5):
        member = corpus.write(kind="answer", attributed_to=agent if n % 2 else owner, body={
            "set": response_set, "field": f"f{n}", "value": {"z": n, "a": [n, 1.5]},
            "replaces": [], "version": plain, "note": "a note"})
        corpus.write(body={"reason": "in"}, attributed_to=owner,
                     link={"from": member, "to": response_set, "relation": "in-response-set"})
    interpreted = corpus.write(kind="response-set", attributed_to=owner, body={
        "post": other, "part": 0, "block": "d", "mode": "shared", "holder": None})
    said = corpus.write(kind="own-words", attributed_to=owner, body={"set": interpreted, "text": "my words"})
    corpus.write(body={"reason": "in"}, attributed_to=owner,
                 link={"from": said, "to": interpreted, "relation": "in-response-set"})
    member = corpus.write(kind="interpretation", attributed_to=agent, body={
        "set": interpreted, "words": said, "passage": {"start": 0, "end": 2}, "proposes": {}})
    corpus.write(body={"reason": "in"}, attributed_to=owner,
                 link={"from": member, "to": interpreted, "relation": "in-response-set"})

    # -- An artifact on a deleted Turn, for `history`'s marking ---------------------------------
    carrying = cv.say(known, owner, _text("carries a file"))
    file_one = corpus.admit(source="test:agent-reads", locator="b", observed_at=2.0, payload="bytes",
                            attributed_to=owner)
    submitted = cv.record_act(actor=owner, act="artifact-submitted", conversation=known,
                              turn=carrying, about=[file_one], detail={"name": "a.txt"})
    corpus.write(body={"reason": "made"}, attributed_to=owner,
                 link={"from": submitted, "to": file_one, "relation": "produced"})
    from mentis.conversation import versions
    versions.delete(cv, carrying, by=owner, because="taken back")
    # Returned by a run whose result stands: still in view.
    asking = cv.say(known, owner, _text("asks for a file"))
    result = cv.say(known, agent, _text("here it is"))
    file_two = corpus.admit(source="test:agent-reads", locator="c", observed_at=3.0, payload="bytes",
                            attributed_to=agent)
    request_act = cv.expect(asking, of=agent, kind="request", by=owner, because="w",
                            conversation=known)
    begun = cv.record_act(actor=agent, act="execution-started", conversation=known,
                          caused_by=request_act, execution="run-four")
    cv.record_act(actor=agent, act="result-returned", conversation=known, turn=result,
                  caused_by=begun, execution="run-four")
    returned = cv.record_act(actor=agent, act="artifact-returned", conversation=known, turn=asking,
                             caused_by=request_act, execution="run-four", about=[file_two])
    corpus.write(body={"reason": "made"}, attributed_to=agent,
                 link={"from": returned, "to": file_two, "relation": "produced"})
    versions.delete(cv, asking, by=owner)
    # A held artifact, whose file `resolve` looks for, written by hand as the bytes aren't here.
    corpus.close()
    db = sqlite3.connect(f"{brain}/corpus.db")
    with db:
        db.execute(
            "INSERT INTO entry (id, body, hash, family, def_name, def_version, attributed_to, "
            "written_by, recorded_at, origin, link_from, link_to, link_relation, "
            "link_relation_version, prev_hash) "
            "SELECT 'adm-heldheldheld', json_set(body, '$.content', 'held'), 'not-checked', family, "
            "def_name, def_version, attributed_to, written_by, recorded_at, origin, link_from, "
            "link_to, link_relation, link_relation_version, prev_hash FROM entry WHERE id = ?",
            (artifact,))
        db.execute(
            "INSERT INTO entry (id, body, hash, family, def_name, def_version, attributed_to, "
            "written_by, recorded_at, origin, link_from, link_to, link_relation, "
            "link_relation_version, prev_hash) "
            "SELECT 'adm-acquiredacqu', json_set(body, '$.envelope', json('{\"bulk_source\": \"c\"}')),"
            " 'not-checked', family, def_name, def_version, attributed_to, written_by, recorded_at, "
            "origin, link_from, link_to, link_relation, link_relation_version, prev_hash "
            "FROM entry WHERE id = ?", (artifact,))
    db.close()


def commit(brain):
    python_side.commit(brain)


def _asked(ask):
    try:
        return {"answer": ask()}
    except Exception as failure:  # noqa: BLE001  what is compared is that it failed
        return {"raises": type(failure).__name__}


def _facts_of_kinds(got):
    return {k: v for k, v in got.items() if k not in ("as_read", "groups_mean", "split_none_means")}


def _facts_of_history(got):
    rows = []
    for row in got.get("acts", ()):
        row = dict(row)
        if row.get("deleted"):
            row.pop("note", None)
        rows.append(row)
    return {**got, "acts": rows}


def _facts_of_changes(got):
    return {k: v for k, v in got.items() if k != "note"}


def _facts_of_governed(got):
    return {k: v for k, v in got.items()
            if k not in ("listed_because", "governs_is_per_row", "not_an_ask")}


def _facts_of_resolve(got):
    out = {k: v for k, v in got.items() if k != "known"}
    if out.pop("standing", None) is not None:
        out["has_standing_sentence"] = True
    if out.get("what") == "a Reaction":
        out.pop("note", None)
    for form in out.get("decision_forms", ()):
        form.pop("note", None)
    return out


def _standing(corpus, ids, as_at):
    out = {}
    for one in ids:
        now = corpus.stands(one)
        then = corpus.stands(one, as_at=as_at)
        out[one] = {"now": now, "then": then}
    return out


def answers(brain, sampled=False):
    corpus, cv = python_side._open(brain)
    surface = worker.Surface(brain, corpus=corpus)
    real_time = time.time
    worker.time.time = lambda: AT
    try:
        kinds = _facts_of_kinds(surface.kinds())
    finally:
        worker.time.time = real_time

    db = sqlite3.connect(f"file:{brain}/corpus.db?mode=ro", uri=True)
    ids = [r[0] for r in db.execute("SELECT id FROM entry ORDER BY seq")]
    if sampled:
        by_kind = {}
        for one, kind in db.execute("SELECT id, def_name FROM entry ORDER BY seq DESC"):
            by_kind.setdefault(kind, []).append(one)
        ids = [one for held in by_kind.values() for one in held[:150]]
    ids.append("ent-nothing-holds-this")
    resolved = {one: _asked(lambda one=one: _facts_of_resolve(surface.resolve(one))) for one in ids}

    conversations = [r[0] for r in db.execute(
        "SELECT id FROM entry WHERE def_name = 'conversation' AND family = 'entry' "
        "AND link_relation IS NULL ORDER BY seq DESC LIMIT 12")]
    participants = [r[0] for r in db.execute(
        "SELECT actor FROM operational GROUP BY actor ORDER BY COUNT(*) DESC LIMIT 6")]
    turns = [r[0] for r in db.execute(
        "SELECT turn FROM operational WHERE turn IS NOT NULL "
        "GROUP BY turn ORDER BY COUNT(*) DESC LIMIT 6")]
    filters = [{}]
    filters += [{"conversation": c} for c in conversations[:6]]
    filters += [{"turn": t} for t in turns]
    filters += [{"participant": p} for p in participants]
    filters += [{"conversation": conversations[0], "turn": turns[0]},
                {"conversation": conversations[0], "participant": participants[0]},
                {"turn": "ent-nothing", "participant": "nobody"},
                {"conversation": ""}]
    history = []
    for one in filters:
        for limit in ((40,) if sampled else (40, 1, 3, 1000)):
            got = surface.history(limit=limit, **one)
            history.append({"args": one, "limit": limit, "answer": _facts_of_history(got)})

    sets = [r[0] for r in db.execute(
        "SELECT id FROM entry WHERE def_name = 'response-set' AND family = 'entry' ORDER BY seq "
        "DESC LIMIT 12")]
    forms = [r[0] for r in db.execute(
        "SELECT id FROM operational WHERE act = 'decision-form' ORDER BY seq DESC LIMIT 40")]
    changes = []
    for one in (sets + forms + ["ent-nothing", conversations[0]])[:(40 if sampled else None)]:
        first = surface.set_changes(one)
        mids = [c["entry"] for c in first.get("changes", ())]
        for since in [None, one, "  ", "not-a-member", "it's", *mids[:2]]:
            for limit in (40, 1, 2, 500):
                changes.append({"set": one, "since": since, "limit": limit,
                                "answer": _facts_of_changes(surface.set_changes(one, since, limit))})

    decisions = []
    for one in conversations + ["ent-nothing", " " + conversations[0] + " "]:
        for most in (None, 1, 2, 100):
            decisions.append({"conversation": one, "most": most,
                              "answer": surface.owner_decisions(one, most)})

    kinds_seen = [k["kind"] for k in kinds["kinds"]]
    asked_kinds = [None, "rule", "lesson", "persona", " rule ", "contribution", "no-such-kind", ""]
    asked_kinds += [k for k in kinds_seen if k not in asked_kinds][:(3 if sampled else 200)]
    grid = [{"kind": k} for k in asked_kinds]
    grid += [{"q": q} for q in ("", "replace", "a standing rule", "ZZZZ", "r1-owner", "Überblick",
                                "reviewer", "proposal number", "the rule")]
    grid += [{"state": s} for s in ("proposed", "recorded", "standing", "history", "unknown", "x", " standing ")]
    grid += [{"limit": n} for n in (1, 2, 1000, 0, 1001)]
    grid += [{"limit": 2, "cursor": c} for c in ("", "start", "g1.0", "g1.1", "3", "g1.-1", "x", "g1.999999", "it's")]
    grid += [{"kind": "rule", "state": "history", "q": "rule", "limit": 3, "cursor": "g1.1"}]
    if sampled:
        # Python reads the whole register for each of these, which on a real record is many seconds.
        grid = [{}, {"kind": "rule"}, {"kind": "lesson"}, {"q": "the rule"}, {"state": "standing"},
                {"state": "x"}, {"limit": 3}, {"limit": 5, "cursor": "g1.5"}]
    governed = []
    for one in grid:
        args = {"limit": 40, **one}
        governed.append({"args": one, "limit": args["limit"],
                         "answer": _facts_of_governed(register.governed(surface.brain, **args))})

    standing_ids = ids if not sampled else ids[:600]
    times = [r[0] for r in db.execute("SELECT recorded_at FROM entry ORDER BY seq")]
    as_at = times[(3 * len(times)) // 4]

    print(json.dumps({
        "position": list(corpus.advance()),
        "at": AT,
        "capabilities": {k: v for k, v in surface.capabilities().items() if k != "note"},
        "kinds": kinds,
        "resolve": resolved,
        "history": history,
        "set_changes": changes,
        "owner_decisions": decisions,
        "governed": governed,
        "as_at": as_at,
        "standing": _standing(corpus, standing_ids, as_at),
    }))
    corpus.close()


if __name__ == "__main__":
    what, where = sys.argv[1], sys.argv[2]
    if what == "digest":
        # What a test may not open but through SQLite (`tests/front/test_wrote_nothing.py`).
        print(hashlib.sha256((pathlib.Path(where) / "corpus.db").read_bytes()).hexdigest())
        sys.exit(0)
    if what == "change":
        change(where)
    elif what == "commit":
        commit(where)
    elif what == "answers":
        answers(where)
    elif what == "answers-copy":
        answers(where, sampled=True)
    else:
        raise SystemExit(f"no {what!r}")
