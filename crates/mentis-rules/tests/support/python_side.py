"""The other side of the rules' differential: Python's own answers on a BRAIN-SEED that has been
edited, so a walk has something to walk.

    python_side.py change <brain>    write the changes below, with Python's own commands
    python_side.py commit <brain>    one more post: "just after a commit"
    python_side.py answers <brain>   print Python's answers, as JSON
    python_side.py odd <brain>       hold deleted entries with bodies of every shape, and print
                                     Python's reading of each
    python_side.py odd-topic <brain> hold a deleted Topic Python can't read, and print its answer

BRAIN-SEED has no supersession of its own, so it says nothing about how an edited, renamed, forked
or deleted thing reads. Everything here goes through the commands a real server uses, except what
those commands refuse on purpose (a forked line, a deleted Topic, a withdrawn deletion), which the
record can still hold and the rules must read as Python does.
"""

import json
import secrets
import sqlite3
import sys

import mentis.api as api
from mentis.conversation import versions
from mentis.fluid import read as fluid_read
from mentis.spine.seam import _Boundary as Boundary
from mentis.web.moved import moved

TOPIC_QUESTIONS = ["", "load", "mag", "rev", "sta", "zzzz", "#load", "  LOAD ", "o", "e", "welcome",
                   "café", "σασ", "over", "harbour", "a", "##"]
LIMITS = [None, 1, 2, 3, 500]
MALFORMED = ["x", "1", "1.2", "1.2.3.4", "1..3", "a.b.c", " 1 . 2 . 3 ", "+1.+2.+3", "1_0.2.3",
             "-1.-1.-1", "1.2.3 ", "0.0.0", "99999999.0.0", "0.99999999.0", "0.0.99999999",
             "9" * 5000 + ".0.0", "9" * 40 + ".0.0"]
#: False to Python, so `(body or {})` is empty: `_blank` keeps nothing and `.get` finds nothing.
FALSE_BODIES = ["false", "0", "0.0", "-0", "0e5", "1e-400", '""', "null", "[]", "{}"]
#: True to Python and not an object, so `.items()` and `.get` raise.
TRUE_BODIES = ["true", "1", "1.5", '"x"', "[1]", "[[]]"]
#: A deletion's own body, for `(d["body"] or {}).get("reason") or None`.
DELETION_BODIES = FALSE_BODIES + TRUE_BODIES + [
    '{"reason": ""}', '{"reason": null}', '{"reason": false}', '{"reason": 0}', '{"reason": 0.0}',
    '{"reason": []}', '{"reason": {}}', '{"reason": "why"}', '{"reason": true}', '{"reason": 3}',
    '{"reason": [1]}', '{"reason": {"a": 1}}']


def _text(words):
    return [{"type": "text", "text": words}]


def _open(brain):
    corpus = api.open_corpus(brain)
    return corpus, api.brain(corpus).conversations


def _named(corpus, kind, name, field="name"):
    for entry in corpus.entries_of_kind(kind):
        if entry["body"].get(field) == name:
            return entry["id"]
    raise SystemExit(f"no {kind} named {name!r}")


def change(brain):
    corpus, cv = _open(brain)
    owner = cv.resolve_participant("@r1-owner")
    agent = cv.resolve_participant("@r1-agent")
    known = _named(corpus, "conversation", "R1 known conversation")
    second = _named(corpus, "conversation", "R1 second conversation")
    sup = corpus.superseding_relation()

    def said(where, who, words):
        return cv.say(where, who, _text(words))

    # Turns: edited twice, deleted, edited then deleted.
    twice = said(known, owner, "first words")
    versions.edit(cv, twice, by=owner, text="second words")
    versions.edit(cv, twice, by=owner, text="third words")
    gone = said(known, owner, "words to take back")
    versions.delete(cv, gone, by=owner, because="a reason given")
    both = said(known, agent, "words then gone")
    versions.edit(cv, both, by=agent, text="other words")
    versions.delete(cv, both, by=agent)

    # Names: a Conversation and a Participant renamed, a Topic renamed and one deleted.
    cv.rename_conversation(second, "Second, renamed", by=owner)
    cv.rename_conversation(second, "Café ΣΑΣ renamed again", by=owner)
    cv.rename_participant(agent, "@r1-agent-renamed", by=owner)
    magnets = _named(corpus, "topic", "Magnets")
    cv.edit_topic(magnets, by=owner, name="Lodestones and magnets")
    status = _named(corpus, "topic", "Status board")
    cv.edit_topic(status, by=owner, name="Überblick Status ΣΑΣ")
    review = _named(corpus, "topic", "Review notes")
    record = corpus.write(kind=versions.DELETION, body={"reason": "not wanted"},
                          attributed_to=owner)
    corpus.write(body={"reason": "not wanted"}, attributed_to=owner,
                 link={"from": record, "to": review, "relation": sup})

    # Another Kind: a rule deleted, and a rule replaced and its replacement deleted.
    rules = [e["id"] for e in corpus.entries_of_kind("rule")]
    versions.delete(cv, rules[0], by=owner, because="no longer so")
    replacement = corpus.write(kind="rule", body={"text": "replacement"}, attributed_to=owner)
    corpus.write(body={"reason": "replaced"}, attributed_to=owner,
                 link={"from": replacement, "to": rules[1], "relation": sup})
    record = corpus.write(kind=versions.DELETION, body={"reason": ""}, attributed_to=owner)
    corpus.write(body={"reason": ""}, attributed_to=owner,
                 link={"from": record, "to": replacement, "relation": sup})

    # A line that forks: `history` follows the last, and the deletion may be on the other.
    forked = said(known, owner, "the root of a fork")
    one = corpus.write(kind="contribution", body={"parts": _text("branch one"), "addressed_to": []},
                       attributed_to=owner)
    corpus.write(body={"reason": "one"}, attributed_to=owner,
                 link={"from": one, "to": forked, "relation": sup})
    two = corpus.write(kind="contribution", body={"parts": _text("branch two"), "addressed_to": []},
                       attributed_to=owner)
    corpus.write(body={"reason": "two"}, attributed_to=owner,
                 link={"from": two, "to": forked, "relation": sup})

    # A supersession that was itself withdrawn: the link ended, so the line didn't move.
    withdrawn = said(known, owner, "kept after all")
    later = corpus.write(kind="contribution",
                         body={"parts": _text("never current"), "addressed_to": []},
                         attributed_to=owner)
    link = corpus.write(body={"reason": "by mistake"}, attributed_to=owner,
                        link={"from": later, "to": withdrawn, "relation": sup})
    ender = corpus.write(kind="note", body={"text": "ended that"}, attributed_to=owner)
    corpus.write(body={"reason": "withdrawn"}, attributed_to=owner,
                 link={"from": ender, "to": link, "relation": sup})

    # What `moved` places: acts of every sort, an admission, a filing elsewhere, a delivery.
    corpus.record_operational(actor=owner, act="operation-answered", execution="run-one")
    corpus.record_operational(actor=owner, act="consent-set")
    corpus.record_operational(actor=owner, act="material-edited", conversation=known,
                              execution="run-two", turn=twice)
    corpus.record_operational(actor=owner, act="something-done", turn=twice)
    corpus.record_operational(actor=owner, act="governance-changed", conversation=second)
    corpus.record_operational(actor=owner, act="something-done", conversation="", turn="")
    corpus.admit(source="test:one", locator="a", observed_at=1.0, payload="words",
                 attributed_to=owner)
    corpus.write(body={"reason": "filed"}, attributed_to=owner,
                 link={"from": twice, "to": second, "relation": "linked-into"})
    Boundary(corpus, conversation=known).deliver([twice], participant=owner)
    Boundary(corpus).deliver([twice], participant=owner)
    corpus.close()


def commit(brain):
    corpus, cv = _open(brain)
    owner = cv.resolve_participant("@r1-owner")
    cv.say(_named(corpus, "conversation", "R1 known conversation"), owner, _text("just committed"))
    corpus.close()


def answers(brain):
    corpus, cv = _open(brain)
    db = sqlite3.connect(f"file:{brain}/corpus.db?mode=ro", uri=True)
    ids = [r[0] for r in db.execute("SELECT id FROM entry ORDER BY seq")]
    position = corpus.advance()
    now = {}
    names = {}
    # `Store.by_ids` binds one variable an id, and a real record has more ids than SQLite allows.
    for at in range(0, len(ids), 500):
        some = ids[at:at + 500]
        for entry in corpus.read(some):
            shown = versions.presented(corpus, entry)
            # A time as `repr`'s text: the other side's JSON doesn't round-trip a float exactly.
            revision = shown.get("revision")
            if revision:
                revision = {**revision, "edited_at": repr(revision["edited_at"])}
            deleted = shown.get("deleted")
            if deleted:
                deleted = {**deleted, "at": repr(deleted["at"])}
            now[entry["id"]] = {"root": shown["id"], "body": shown["body"],
                                "revision": revision, "deleted": deleted}
        names.update(fluid_read._names(corpus, some))
    names.update(fluid_read._names(corpus, ["ent-nothing-holds-this", "opr-nothing", ""]))

    # Every position within reach of the head, along each table, and all of them together.
    a, b, c = position
    sinces = {f"{a - n}.{b}.{c}" for n in range(0, 60)}
    sinces |= {f"{a}.{b - n}.{c}" for n in range(0, 25) if b - n >= 0}
    sinces |= {f"{a}.{b}.{c - n}" for n in range(0, c + 1)}
    sinces |= {f"{a - n}.{b - n}.{c}" for n in range(0, 25)}
    sinces |= {f"{a - 201}.{b}.{c}", f"{a - 200}.{b}.{c}", f"{a + 1}.{b}.{c}", f"{a}.{b + 1}.{c}",
               f"{a}.{b}.{c + 1}", f"0{a}.{b}.{c}", f" {a}.{b}.{c}", f"{a - 3}.{b}.{c}.",
               f"{a - 3}.+{b}.{c}", f"{a - 3}.{b}.-0"}
    sinces |= set(MALFORMED)
    placed = {since: moved(corpus, since) for since in sorted(sinces)}

    topics = []
    for q in TOPIC_QUESTIONS:
        for limit in LIMITS:
            topics.append({"q": q, "limit": limit,
                           "answer": fluid_read.topics(cv, q=q, limit=limit or fluid_read.LIST)})

    print(json.dumps({"position": list(position), "now": now, "names": names, "moved": placed,
                      "topics": topics}))
    corpus.close()


def _hold(brain, kind, body):
    """An entry of this Kind whose stored body is this text, which no command writes: they refuse
    it, and the record can still hold it. It goes in beside the others, as a row of this scratch
    copy whose hash nobody checks, so nothing already there is changed."""
    entry = "ent-" + secrets.token_hex(6)
    db = sqlite3.connect(f"{brain}/corpus.db")
    with db:
        db.execute(
            "INSERT INTO entry (id, body, hash, family, def_name, def_version, attributed_to, "
            "written_by, recorded_at, origin, link_from, link_to, link_relation, "
            "link_relation_version, prev_hash) "
            "SELECT ?, ?, ?, family, def_name, def_version, attributed_to, written_by, "
            "recorded_at, origin, link_from, link_to, link_relation, link_relation_version, "
            "prev_hash FROM entry WHERE def_name = ? AND family = 'entry' "
            "AND link_relation IS NULL ORDER BY seq LIMIT 1",
            (entry, body, secrets.token_hex(32), kind))
    db.close()
    return entry


def _delete(corpus, brain, owner, entry, record_body='{"reason": "gone"}'):
    record = _hold(brain, versions.DELETION, record_body)
    corpus.write(body={"reason": "gone"}, attributed_to=owner,
                 link={"from": record, "to": entry, "relation": corpus.superseding_relation()})


def _asked(ask):
    """What Python answers, or the kind of its failure: the door's 500, in Python's words."""
    try:
        return {"answer": ask()}
    except Exception as failure:  # noqa: BLE001  what is compared is that it failed
        return {"raises": type(failure).__name__}


def _now(corpus, entry):
    shown = versions.presented(corpus, corpus.read([entry])[0])
    deleted = shown["deleted"]
    return {"body": shown["body"], "deleted": deleted["record"], "because": deleted["because"]}


def odd(brain):
    corpus, cv = _open(brain)
    owner = cv.resolve_participant("@r1-owner")
    known = _named(corpus, "conversation", "R1 known conversation")
    cases = []

    def case(kind, body, entry, record=None):
        cases.append({"kind": kind, "body": body, "record": record, "id": entry,
                      "now": _asked(lambda: _now(corpus, entry)),
                      "name": _asked(lambda: fluid_read._names(corpus, [entry])[entry])})

    for kind in ["contribution", "conversation", "rule"]:
        for body in FALSE_BODIES + TRUE_BODIES:
            entry = _hold(brain, kind, body)
            _delete(corpus, brain, owner, entry)
            case(kind, body, entry)
    for record in DELETION_BODIES:
        entry = _hold(brain, "contribution", '{"parts": [], "addressed_to": []}')
        _delete(corpus, brain, owner, entry, record)
        case("contribution", None, entry, record)
        # `_names` reads this Kind through `presented`, so the deletion's body decides its name too.
        entry = _hold(brain, "conversation", '{"name": "named"}')
        _delete(corpus, brain, owner, entry, record)
        case("conversation", None, entry, record)

    # Deleted Topics that Python can read: none is offered, and the answer goes on.
    for body in FALSE_BODIES:
        topic = _hold(brain, "topic", body)
        corpus.write(body={"reason": "filed"}, attributed_to=owner,
                     link={"from": topic, "to": known, "relation": "topic-of"})
        _delete(corpus, brain, owner, topic)
    print(json.dumps({"cases": cases, "topics": fluid_read.topics(cv, q="", limit=500)}))
    corpus.close()


def odd_topic(brain):
    corpus, cv = _open(brain)
    owner = cv.resolve_participant("@r1-owner")
    topic = _hold(brain, "topic", "[1]")
    corpus.write(body={"reason": "filed"}, attributed_to=owner,
                 link={"from": topic,
                       "to": _named(corpus, "conversation", "R1 known conversation"),
                       "relation": "topic-of"})
    _delete(corpus, brain, owner, topic)
    print(json.dumps(_asked(lambda: fluid_read.topics(cv, q="", limit=500))))
    corpus.close()


if __name__ == "__main__":
    {"change": change, "commit": commit, "answers": answers, "odd": odd,
     "odd-topic": odd_topic}[sys.argv[1]](sys.argv[2])
