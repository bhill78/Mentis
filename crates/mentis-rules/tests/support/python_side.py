"""The other side of the rules' differential: Python's own answers on a BRAIN-SEED that has been
edited, so a walk has something to walk.

    python_side.py change <brain>    write the changes below, with Python's own commands
    python_side.py commit <brain>    one more post: "just after a commit"
    python_side.py answers <brain>   print Python's answers, as JSON
    python_side.py odd <brain>       hold deleted entries with bodies of every shape, and print
                                     Python's reading of each
    python_side.py odd-topic <brain> hold a deleted Topic Python can't read, and print its answer
    python_side.py lines <brain>     hold lines and links that fork and loop, links of links and
                                     relation versions with other roles, and print Python's reading
    python_side.py states <brain>    archive, trash and bring back Conversations with Python's own
                                     command, and print Python's lists of each state, as JSON text

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
from mentis.fluid import objects as fluid_objects
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
    # A fixture recorded at PY_COMMIT's schema is brought to this clone's first, explicitly, as a
    # person upgrading would (0002-erasure raises min_reader); a current one is left as it is.
    from mentis.spine import migrations
    if migrations.plan(str(brain)).get("migrations"):
        migrations.apply(str(brain), allow_breaking=True)
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


def _raw_link(db, entry, frm, to, relation, version, at):
    """A link at a time of this test's choosing, as this scratch copy's own row: no command writes
    a link to an id that doesn't exist yet, so none can close a loop of links."""
    db.execute(
        "INSERT INTO entry (id, family, def_name, def_version, body, attributed_to, written_by, "
        "recorded_at, origin, link_from, link_to, link_relation, link_relation_version, prev_hash, "
        "hash) SELECT ?, family, ?, ?, '{\"reason\": \"lines\"}', attributed_to, written_by, ?, "
        "origin, ?, ?, ?, ?, prev_hash, ? FROM entry WHERE link_relation IS NOT NULL "
        "ORDER BY seq LIMIT 1",
        (entry, relation, version, at, frm, to, relation, version, secrets.token_hex(32)))


def _raw_definition(db, like, name, version, role):
    """A version of a relation, with this role, beside what the record already defines."""
    (body,) = db.execute("SELECT body FROM entry WHERE family = 'definition' AND def_name = ? "
                         "ORDER BY seq LIMIT 1", (like,)).fetchone()
    body = {**json.loads(body), "relation": name}
    body.pop("substrate_role", None)
    if role:
        body["substrate_role"] = role
    db.execute(
        "INSERT INTO entry (id, family, def_name, def_version, body, attributed_to, written_by, "
        "recorded_at, origin, link_from, link_to, link_relation, link_relation_version, prev_hash, "
        "hash) SELECT ?, family, ?, ?, ?, attributed_to, written_by, recorded_at, origin, link_from, "
        "link_to, link_relation, link_relation_version, prev_hash, ? FROM entry "
        "WHERE family = 'definition' AND def_name = ? ORDER BY seq LIMIT 1",
        ("ent-" + secrets.token_hex(6), name, version, json.dumps(body), secrets.token_hex(32),
         like))


def lines(brain):
    corpus, _ = _open(brain)
    sup = corpus.superseding_relation()
    sup_version = corpus.current_definition(sup)["definition"]["version"]
    established = corpus._role_relation("establishes")
    established_version = corpus.current_definition(established)["definition"]["version"]
    other = "linked-into"
    other_version = corpus.current_definition(other)["definition"]["version"]
    corpus.close()

    db = sqlite3.connect(f"{brain}/corpus.db")
    asked = []
    times = []

    def node(label, kind="contribution"):
        body = {"parts": _text(label), "addressed_to": []} if kind == "contribution" \
            else {"reason": label} if kind == versions.DELETION else {"text": label}
        entry = _hold(brain, kind, json.dumps(body))
        asked.append(entry)
        return entry

    def link(frm, to, relation=sup, version=sup_version, entry=None):
        """Each a second after the last, so every link is a time standing can be asked as at."""
        entry = entry or "ent-" + secrets.token_hex(6)
        at = 2_000_000_000.0 + len(times)
        times.append(at)
        _raw_link(db, entry, frm, to, relation, version, at)
        db.commit()
        asked.append(entry)
        return entry

    # A straight line, and a rule's: another Kind reads its line differently.
    a, b, c = node("line one"), node("line two"), node("line three")
    link(b, a)
    link(c, b)
    old, new, gone = node("old rule", "rule"), node("new rule", "rule"), node("x", versions.DELETION)
    link(new, old)
    link(gone, new)

    # Forks: the deletion on the branch `history` doesn't follow, then on the one it does.
    root, one, two, ended = node("fork"), node("one"), node("two"), node("x", versions.DELETION)
    link(one, root)
    link(two, root)
    link(ended, one)
    root, one, two, ended = node("fork"), node("one"), node("two"), node("x", versions.DELETION)
    link(one, root)
    link(two, root)
    link(ended, two)
    # And a fork that closes again.
    root, one, two, head = node("diamond"), node("left"), node("right"), node("head")
    link(one, root)
    link(two, root)
    link(head, one)
    link(head, two)

    # Lines that loop: itself, two, and three with something older and something newer on them.
    self_loop = node("itself")
    link(self_loop, self_loop)
    one, two = node("loop one"), node("loop two")
    link(one, two)
    link(two, one)
    one, two, three, older, newer = (node("loop a"), node("loop b"), node("loop c"),
                                     node("before the loop"), node("after the loop"))
    link(one, two)
    link(two, three)
    link(three, one)
    link(two, older)
    link(newer, three)
    # A loop with a deletion on it.
    one, two, ended = node("deleted a"), node("deleted b"), node("x", versions.DELETION)
    link(one, two)
    link(two, one)
    link(ended, one)

    # Links of links of links: each ending the last, so the target's standing changes at each.
    target, by = node("target"), node("by")
    established_link = link(target, target, established, established_version)
    ending = link(by, target)
    for depth in range(5):
        ending = link(node(f"ender {depth}"), ending)
    # The establishing link itself ended, and that ended in turn.
    ending = link(node("ends establishing"), established_link)
    link(node("ends that"), ending)
    # A fork of links: one ender stays, the other is ended; then both are ended.
    target = node("fork of links")
    ended = link(node("by"), target)
    link(node("stays"), ended)
    link(node("ended"), link(node("ending"), ended))
    target = node("both ended")
    ended = link(node("by"), target)
    link(node("first"), link(node("ends first"), ended))
    link(node("second"), link(node("ends second"), ended))

    # Links that loop, which only an id chosen first can close. Something outside points in.
    one, two, three = ("ent-" + secrets.token_hex(6) for _ in range(3))
    link(node("from one"), two, entry=one)
    link(node("from two"), one, entry=two)
    link(node("from outside"), one)
    itself = "ent-" + secrets.token_hex(6)
    link(node("from itself"), itself, entry=itself)
    four, five = ("ent-" + secrets.token_hex(6) for _ in range(2))
    link(node("from three"), four, entry=three)
    link(node("from four"), five, entry=four)
    link(node("from five"), three, entry=five)

    # Other relations: a link on a link is not walked unless it supersedes, and ends nothing.
    target = node("other relation")
    filed = link(node("filed"), target, other, other_version)
    link(node("filed again"), filed, other, other_version)
    target = node("other relation, ended")
    filed = link(node("filed"), target, other, other_version)
    link(node("filed again"), filed, other, other_version)
    link(node("ends it"), filed)
    target = node("ended by another relation")
    ended = link(node("by"), target)
    link(node("not an ending"), ended, other, other_version)

    # What a link's own relation version says: this role, none, the first of two, no definition.
    _raw_definition(db, sup, "t0-ending", 1, "supersedes")
    _raw_definition(db, sup, "t0-ending", 2, None)
    _raw_definition(db, sup, "t0-ending", 3, None)
    _raw_definition(db, sup, "t0-ending", 3, "supersedes")
    _raw_definition(db, sup, "t0-ending", 4, "supersedes")
    _raw_definition(db, sup, "t0-ending", 4, None)
    db.commit()
    for version in (1, 2, 3, 4, 5):
        target = node(f"version {version}")
        ended = link(node("by"), target, "t0-ending", version)
        link(node("ended by"), ended, "t0-ending", version)
        link(node("under the relation"), link(node("plain"), target), "t0-ending", version)

    # Links naming what the record doesn't hold, at either end.
    line = node("names nothing")
    link("ent-nothing-from-here", line)
    link(line, "ent-nothing-to-here")
    db.close()

    asked += ["ent-nothing-holds-this", "ent-nothing-from-here", "ent-nothing-to-here",
              "adm-nothing", "opr-nothing", "not-an-id", ""]
    # Exactly each link's time, which it counts at, and just before it, which it doesn't.
    moments = sorted({*times, *(at - 0.5 for at in times)})

    corpus, _ = _open(brain)
    stands = {entry: {"now": corpus.stands(entry),
                      "then": [corpus.stands(entry, as_at=at) for at in moments]}
              for entry in asked}
    now = {}
    held = {}
    for entry in asked:
        got = corpus.read([entry])
        if not got:
            continue
        shown = versions.presented(corpus, got[0])
        revision = shown.get("revision") or {}
        deleted = shown.get("deleted") or {}
        now[entry] = {"root": shown["id"], "body": shown["body"],
                      "versions": revision.get("versions"), "current": revision.get("current"),
                      "deleted": deleted.get("record")}
        lineage = fluid_objects._lines(corpus, [entry])[entry]
        held[entry] = {"root": corpus.history(entry)[0],
                       "versions": [v["id"] for v in lineage["versions"]],
                       "deletion": (lineage["deletion"] or {}).get("id")}
    print(json.dumps({"ids": asked, "times": [repr(at) for at in moments], "stands": stands,
                      "now": now, "lines": held}))
    corpus.close()


def states(brain):
    """WHERE CONVERSATIONS ARE LISTED (`Conversations.change_conversation_state`): one left
    active, then archived, trashed, archived and back, trashed and back, archived then trashed,
    archived again, trashed and back then archived, archived and back then trashed and back (a row
    left active by its latest act says that act's time). Each answer is `json.dumps`'s own text, so the other side compares bytes."""
    corpus, cv = _open(brain)
    owner = cv.resolve_participant("@r1-owner")
    for n in range(7):                  # enough for every case below, one with a post
        made = cv.open_conversation(f"R1 listed conversation {n}", attributed_to=owner)
        if n == 2:
            cv.say(made, owner, _text("said here"))
    listed = fluid_read.conversation_list(corpus, cv, fluid_read.LIST_MAX)["conversations"]
    ids = [r["id"] for r in listed]
    plan = [["archive"], ["trash"], ["archive", "unarchive"], ["trash", "restore"],
            ["archive", "trash"], ["archive"], ["trash", "restore", "archive"],
            ["archive", "unarchive", "trash", "restore"]]
    for cid, changes in zip(ids[1:], plan):
        for change in changes:
            cv.change_conversation_state(cid, change, by=owner)
    lists = []
    for state in [None, "active", "archived", "trashed"]:
        for q in [None, "r1", "conversation", "zzzz"]:
            for limit in [1, 2, 3, 100]:
                after, pages = None, 0
                while pages < 40:
                    got = fluid_read.conversation_list(corpus, cv, limit, after=after, q=q,
                                                       state=state)
                    lists.append({"state": state, "q": q, "limit": limit, "after": after,
                                  "answer": json.dumps(got)})
                    pages += 1
                    after = got["next"]
                    if not after:
                        break
        # a cursor the list doesn't hold starts it again
        got = fluid_read.conversation_list(corpus, cv, 2, after="ent-nothing-holds-this",
                                           state=state)
        lists.append({"state": state, "q": None, "limit": 2, "after": "ent-nothing-holds-this",
                      "answer": json.dumps(got)})
    asked = ids + ["ent-nothing-holds-this"]
    print(json.dumps({"conversations": len(ids), "states": {
        c: v["state"] for c, v in cv.conversation_states().items()}, "lists": lists,
        "ids": asked, "by_ids": json.dumps(fluid_read.conversations(corpus, cv, asked))}))
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
     "odd-topic": odd_topic, "lines": lines, "states": states}[sys.argv[1]](sys.argv[2])
