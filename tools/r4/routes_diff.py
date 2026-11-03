"""R4.1's routes against Python, wire bytes with key order, on a backup-API copy of a real Brain.

    <venv python> tools/r4/routes_diff.py copy <source Brain> <new directory>
    <venv python> tools/r4/routes_diff.py shapes <source Brain> <new directory>
    <venv python> tools/r4/routes_diff.py run <copy> --front <mentis-server.exe> --out <dir>
                  [--families a,b] [--sample N] [--port-base 34000]
    <venv python> tools/r4/routes_diff.py load <copy> --front <mentis-server.exe> --out <dir>
                  [--seconds 30] [--port-base 34000]

`copy` takes `corpus.db` through SQLite's backup API from a `mode=ro` connection, and the rest as files.
`run` starts one Python and one front on that copy: the front's upstream is a small counting relay in
this process, so whether Rust answered a request or forwarded it is what the relay saw, and nothing the
front says of itself. Every request is asked of Python directly, then of the front, one at a time.

Requests are built from what the copy holds (its ids, names, cursors and real answers), never from
invented data. A request's family is its route. For each family the report counts `answered` (bytes
identical), `different` (Rust answered, and any byte differs), `forwarded`, and how long each took.
Status line, headers but `Date`, and body are all compared, so key order can't pass unnoticed.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import shutil
import socket
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from tests.front.pair import CLIENT, Answer, exchange, request  # noqa: E402

SECRET = "r41-routes-diff"
NO_MARS = "workload-no-mars-here"
BATCH = 64
EVERY = ("conversations-ids", "conversations-activity", "api-conversations", "fluid-participants",
         "api-participants", "stream", "selection", "latest", "home-needs-you", "needs-you-items",
         "needs-you-asks", "needs-you-post", "anchors", "post-anchors", "changes", "response-sets",
         "response-set", "response-history", "response-accounting")


def copy_brain(source: pathlib.Path, dest: pathlib.Path) -> None:
    dest.mkdir(parents=True)
    src = sqlite3.connect(f"file:{(source / 'corpus.db').as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(dest / "corpus.db")
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    shutil.copy2(source / "mentis-corpus.json", dest)
    for name in ("presentation", "derived", "instances", "artifacts"):
        if (source / name).exists():
            shutil.copytree(source / name, dest / name)


def shapes(source: pathlib.Path, dest: pathlib.Path) -> dict:
    """What the master doesn't hold (a reaction changed or withdrawn, own words, an interpretation, a
    reassigned or withdrawn ask, a missing picture...), written on a new copy by Python's own functions
    on the copy's own posts and people, so `run` can compare them. What Python refuses is reported, not
    worked around: nothing here invents a body."""
    copy_brain(source, dest)
    from mentis.conversation import anchors, responses, versions
    from mentis.operational.work_overview import owner_of
    from mentis.web import _State

    st = _State(str(dest))
    cv, corpus = st.cv, st.corpus
    owner = owner_of(cv)
    claude, codex, renamed = [p["id"] for p in cv.all_participants()
                              if p["id"] != owner and p["body"].get("alias")][:3]
    done: dict = {}

    def shape(name, write):
        try:
            done[name] = "written", write()
        except Exception as exc:  # noqa: BLE001 - what Python refuses is the answer
            done[name] = "refused", f"{type(exc).__name__}: {getattr(exc, 'refusal', exc)}"
        return done[name][1] if done[name][0] == "written" else None

    db = sqlite3.connect(f"file:{(dest / 'corpus.db').as_posix()}?mode=ro", uri=True)
    plain = [r for r in rows(db, """SELECT e.id, h.link_to, e.attributed_to FROM entry e JOIN entry h
        ON h.link_from=e.id AND h.link_relation='in-conversation' WHERE e.def_name='contribution'
        AND json_extract(e.body,'$.parts[0].type')='text' AND length(json_extract(e.body,'$.parts[0].text'))>40
        AND json_array_length(e.body,'$.parts')=1 AND NOT EXISTS(SELECT 1 FROM entry x WHERE x.link_to=e.id
        AND x.link_relation='supersedes') ORDER BY e.seq DESC LIMIT 40""")]
    sets = [r[0] for r in rows(db, "SELECT id FROM entry WHERE family='entry' AND def_name='response-set' "
                                   "AND link_relation IS NULL ORDER BY seq")]
    conversations = [r[0] for r in rows(db, "SELECT link_to FROM entry WHERE link_relation='in-conversation' "
                                            "GROUP BY link_to ORDER BY COUNT(*) DESC LIMIT 6")]
    persona = rows(db, "SELECT id FROM entry WHERE def_name='persona' AND family='entry' AND link_relation "
                       "IS NULL ORDER BY seq DESC LIMIT 1")[0][0]
    pictured = rows(db, "SELECT link_from, link_to FROM entry WHERE link_relation='pictured-by' ORDER BY seq DESC")
    db.close()
    post, home, author = plain[0]
    other_post, other_home, other_author = plain[1]
    gone_post, gone_home, gone_author = plain[2]

    def anchor(on, **more):
        words = corpus.read([on])[0]["body"]["parts"][0]["text"]
        ask = {"version": on, "type": "text-range", "part": 0, "start": 0, "end": 8, "unit": "codepoint",
               "expected_excerpt": words[:8], **more}
        return anchors.create_anchor(cv, ask, by=owner)["anchor"]

    a1 = shape("anchor a range", lambda: anchor(post))
    a2 = shape("anchor a version", lambda: anchors.create_anchor(
        cv, {"version": post, "type": "version"}, by=owner)["anchor"])
    a3 = shape("anchor to be deleted with its post", lambda: anchor(gone_post))
    r1 = shape("react", lambda: anchors.react(cv, a1, {"token": "like"}, by=claude)["reaction"])
    shape("react, changed", lambda: anchors.react(cv, a1, {"token": "love", "changes": r1}, by=claude))
    r3 = shape("react, to withdraw", lambda: anchors.react(cv, a1, {"token": "see"}, by=codex)["reaction"])
    shape("withdrawn by its reactor", lambda: versions.delete(cv, r3, by=codex))
    r4 = shape("react, to be deleted", lambda: anchors.react(cv, a2, {"token": "bad"}, by=claude)["reaction"])
    shape("deleted by somebody else", lambda: versions.delete(cv, r4, by=owner))
    r5 = shape("react, to supersede", lambda: anchors.react(cv, a2, {"token": "old"}, by=codex)["reaction"])

    def superseded_by_another():
        newer = corpus.write(kind="reaction", body={"token": "new", "about": a2}, attributed_to=owner)
        return corpus.write(body={"reason": "generic"}, attributed_to=owner,
                            link={"from": newer, "to": r5, "relation": corpus.superseding_relation()})

    shape("a generic supersession of a reaction", superseded_by_another)
    shape("deep dive", lambda: anchors.deep_dive(cv, a1, {"why": "look further"}, by=owner))
    shape("anchored reply", lambda: cv.say(home, owner, [{"type": "text", "text": "this"},
                                                         {"type": "anchor", "ref": a1}], replies_to=post))
    shape("edit an anchored post", lambda: versions.edit(cv, post, by=author, text="changed words, changed words"))
    shape("delete an anchored post", lambda: versions.delete(cv, gone_post, by=gone_author))

    if sets:
        s = sets[0]
        w1 = shape("own words", lambda: responses.write_words(cv, s, text="first  words", by=owner)["words"])
        shape("own words, again", lambda: responses.write_words(cv, s, text="second words", replaces=[w1], by=owner))
        shape("own words, blank", lambda: responses.write_words(cv, s, text="   ", by=claude))
    if len(sets) > 1:
        s = sets[1]
        w2 = shape("words to interpret", lambda: responses.write_words(cv, s, text="this means that", by=owner)["words"])
        shape("an interpretation", lambda: responses.interpret(
            cv, s, words=w2, passage={"start": 0, "end": 4, "expected_excerpt": "this"},
            proposes={"type": "add-field", "field": {"id": "extra", "kind": "text"}}, by=claude))
    if len(sets) > 2:
        s = sets[2]
        shape("words on a set whose post goes", lambda: responses.write_words(cv, s, text="kept", by=owner))
        shape("a set's post deleted", lambda: versions.delete(cv, corpus.read([s])[0]["body"]["post"], by=owner))

    def ask(turn, of, **kw):
        return cv.expect(turn, of=of, kind=kw.pop("kind", "response"), by=claude, because="asked", **kw)

    t1 = shape("an addressed post", lambda: cv.say(other_home, claude, [{"type": "text", "text": "# **Lead** line\nmore"}],
                                                   addressed_to=[owner, codex]))
    e1 = shape("an ask of the owner", lambda: ask(t1, owner))
    shape("an ask of somebody, reassigned to the owner", lambda: cv.assign(ask(t1, codex), owner, by=owner))
    e2 = shape("an ask of the owner, reassigned away", lambda: ask(t1, owner))
    shape("reassigned away", lambda: cv.assign(e2, codex, by=owner))
    shape("a reply from one addressed", lambda: cv.say(other_home, codex, [{"type": "text", "text": "answering"}],
                                                       replies_to=t1))
    shape("an observed delivery failure", lambda: cv.observe(t1, "delivery-failed", detail=f"{owner} is away"))
    shape("a decision ask", lambda: ask(t1, owner, kind="decision", detail={"options": ["a", "b"]}))
    if sets:
        shape("an input ask", lambda: ask(t1, owner, kind="input", detail={"response_set": sets[0]}))
    shape("an ask on a turn then deleted", lambda: ask(gone_post, owner))
    shape("a met ask", lambda: cv.corpus.record_operational(
        actor=owner, act="expectation-met", caused_by=e1, conversation=other_home, turn=t1, about=[],
        because="done", detail={"withdrawn": True}))

    shape("rename a Conversation", lambda: cv.rename_conversation(conversations[1], "Renamed, Ã©", by=owner))
    shape("a Conversation nobody posted in", lambda: cv.open_conversation("Quiet", attributed_to=owner))
    shape("show a post elsewhere", lambda: cv.link_into(other_post, conversations[2], by=owner))
    shape("show, then end", lambda: (cv.link_into(gone_post, conversations[3], by=owner),
                                     cv.unlink(gone_post, conversations[3], by=owner)))
    topic = shape("a Topic", lambda: cv.open_topic(other_home, "Filed Ã‰", attributed_to=owner))
    shape("file", lambda: cv.assign_topic(other_post, topic, attributed_to=owner))
    shape("rename a Topic", lambda: cv.edit_topic(topic, by=owner, name="Filed again"))
    topic2 = shape("a Topic to unfile", lambda: cv.open_topic(other_home, "Unfiled", attributed_to=owner))
    shape("file, then end", lambda: (cv.assign_topic(t1, topic2, attributed_to=owner),
                                     cv.end_filing(t1, topic2, by=owner)))

    shape("rename a Participant", lambda: cv.rename_participant(renamed, "@Longbus", by=owner))
    shape("declare a runtime", lambda: cv.declare_runtime_default(claude, "claude", by=owner))
    shape("declare runtime-auto", lambda: cv.declare_runtime_default(codex, None, by=owner))
    shape("designate a Persona", lambda: cv.designate_persona(codex, persona, by=owner))

    def several():
        cv.designate_persona(claude, persona, by=owner)
        link = corpus.write(body={"reason": "a second"}, attributed_to=owner,
                            link={"from": claude, "to": persona, "relation": "designated-as"})
        corpus.establish(link, attributed_to=owner, reason="a second")

    shape("two designations standing", several)
    held = shape("a picture's bytes gone", lambda: _unhold(corpus, dest, pictured[0][1]))
    shape("a picture's bytes changed", lambda: _unhold(corpus, dest, pictured[1][1], corrupt=True))
    del held
    corpus.close() if hasattr(corpus, "close") else None
    return done


def _unhold(corpus, dest: pathlib.Path, ref: str, corrupt: bool = False) -> str:
    digest = corpus.read([ref])[0]["body"]["locator"].removeprefix("sha256:")
    path = dest / "artifacts" / "sha256" / digest[:2] / digest
    path.chmod(0o666)
    if corrupt:
        path.write_bytes(b"not those bytes")
    else:
        path.unlink()
    return digest


class Relay:
    """Bytes both ways between the front and Python, noting each request line going up. `live`, if
    given, answers `/private/live` in Python's place; `blocked` makes every other forward fail, as a
    Python that can't answer does."""

    def __init__(self, port: int, upstream: int, live=None):
        self.upstream = upstream
        self.live = live
        self.blocked = False
        self.seen: list[str] = []
        self.lock = threading.Lock()
        self.server = socket.create_server(("127.0.0.1", port))
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                down, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self._one, args=(down,), daemon=True).start()

    def _one(self, down: socket.socket) -> None:
        try:
            first = down.recv(1 << 16)
        except OSError:
            down.close()
            return
        if self.live is not None and first.startswith(b"GET /private/live "):
            self._scripted(down, first)
            return
        if self.blocked:
            down.close()
            return
        try:
            up = socket.create_connection(("127.0.0.1", self.upstream))
        except OSError:
            down.close()
            return
        threading.Thread(target=self._pump, args=(up, down, False), daemon=True).start()
        self._note(first)
        try:
            up.sendall(first)
        except OSError:
            down.close()
            return
        self._pump(down, up, True)

    def _note(self, got: bytes) -> None:
        line = got.split(b"\r\n", 1)[0].decode("latin-1").split(" ")
        if len(line) == 3 and line[2].startswith("HTTP/") and not line[1].startswith("/private/"):
            with self.lock:
                self.seen.append(line[1])

    def _scripted(self, down: socket.socket, first: bytes) -> None:
        """One connection of polls, each answered by what `live` says now."""
        got = first
        try:
            while got:
                answer = self.live()
                if answer is not None:
                    down.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                                 b"Content-Length: " + str(len(answer)).encode() + b"\r\n\r\n" + answer)
                got = down.recv(1 << 16)
        except OSError:
            pass
        down.close()

    def _pump(self, frm: socket.socket, to: socket.socket, upward: bool) -> None:
        try:
            while True:
                got = frm.recv(1 << 16)
                if not got:
                    break
                if upward:
                    self._note(got)
                to.sendall(got)
        except OSError:
            pass
        for sock in (frm, to):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def take(self) -> list[str]:
        with self.lock:
            out, self.seen = self.seen, []
        return out

    def close(self) -> None:
        self.server.close()


def wait_port(port: int, limit: float = 300.0) -> None:
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=.5).close()
            return
        except OSError:
            time.sleep(.1)
    raise SystemExit(f"nothing answered on {port}")


def rows(db: sqlite3.Connection, sql: str, *args) -> list:
    return db.execute(sql, args).fetchall()


def ids_of(db, kind: str) -> list[str]:
    return [r[0] for r in rows(db, "SELECT id FROM entry WHERE family='entry' AND def_name=? "
                                   "AND link_relation IS NULL ORDER BY seq", kind)]


def batches(ids: list[str], size: int = BATCH) -> list[list[str]]:
    return [ids[i:i + size] for i in range(0, len(ids), size)]


class Corpus:
    """The requests, by family. Lazy where a request depends on an earlier real answer."""

    def __init__(self, db, sample: int, ask_python):
        self.db, self.sample, self.ask = db, sample, ask_python
        self.rng = random.Random(41)

    def pick(self, values: list, count: int | None = None) -> list:
        count = self.sample if count is None else count
        return values if len(values) <= count else self.rng.sample(values, count)

    def conversations_ids(self):
        ids = ids_of(self.db, "conversation")
        later = [r[0] for r in rows(self.db, """SELECT l.link_from FROM entry l JOIN entry e ON e.id=l.link_to
            WHERE e.def_name='conversation' AND l.link_relation=(SELECT json_extract(body,'$.relation')
            FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes'
            ORDER BY seq LIMIT 1)""")]
        for batch in batches(ids):
            yield "/fluid/api/conversations?ids=" + ",".join(batch)
        for one in self.pick(later, 10):
            yield f"/fluid/api/conversations?ids={one}"
        post = ids_of(self.db, "contribution")[0]
        yield f"/fluid/api/conversations?ids={ids[0]},{post},ent-000000000000,{ids[0]}"
        yield "/fluid/api/conversations"
        yield "/fluid/api/conversations?ids="
        yield "/fluid/api/conversations?ids=a/b"
        yield "/fluid/api/conversations?ids=" + ",".join(f"x{i}" for i in range(65))

    def conversations_activity(self):
        names = [json.loads(r[0]).get("name") or "" for r in rows(
            self.db, "SELECT body FROM entry WHERE family='entry' AND def_name='conversation' "
                     "AND link_relation IS NULL")]
        topics = [json.loads(r[0]).get("name") or "" for r in rows(
            self.db, "SELECT body FROM entry WHERE family='entry' AND def_name='topic' "
                     "AND link_relation IS NULL LIMIT 200")]
        yield "/fluid/api/conversations?activity=1"
        for limit in ("1", "7", "24", "500", "9999", "0", "abc", ""):
            yield f"/fluid/api/conversations?activity=1&limit={limit}"
        target = "/fluid/api/conversations?activity=1&limit=24"
        for _ in range(100):
            got = self.ask(target)
            yield target
            nxt = got.json.get("next") if got.status == 200 else None
            if not nxt:
                break
            target = f"/fluid/api/conversations?activity=1&limit=24&cursor={nxt}"
        yield "/fluid/api/conversations?activity=1&cursor=ent-000000000000"
        words = [w for n in names + topics for w in n.split() if w]
        for word in self.pick(sorted(set(words)), 30):
            yield "/fluid/api/conversations?activity=1&q=" + urllib.parse.quote(word)
        yield "/fluid/api/conversations?activity=1&q=" + urllib.parse.quote("the a")
        yield "/fluid/api/conversations?activity=1&q=zzzznothing"

    def api_conversations(self):
        yield "/api/conversations"
        yield "/api/conversations?x=1"

    def participants_q(self):
        aliases = [json.loads(r[0]).get("alias") or "" for r in rows(
            self.db, "SELECT body FROM entry WHERE family='entry' AND def_name='participant' "
                     "AND link_relation IS NULL")]
        cuts = {a.strip("@")[:n].lower() for a in aliases for n in (1, 3)} | {a for a in aliases}
        return self.pick(sorted(c for c in cuts if c), 30)

    def fluid_participants(self):
        yield "/fluid/api/participants"
        yield "/fluid/api/participants?runtimes=1"
        for limit in ("1", "5", "24", "500", "9999", "0", "abc"):
            yield f"/fluid/api/participants?limit={limit}"
            yield f"/fluid/api/participants?limit={limit}&runtimes=1"
        for q in self.participants_q():
            yield "/fluid/api/participants?q=" + urllib.parse.quote(q)
            yield "/fluid/api/participants?runtimes=1&q=" + urllib.parse.quote(q)

    def api_participants(self):
        yield "/api/participants"
        for limit in ("1", "24", "0", "abc", "-1"):
            yield f"/api/participants?limit={limit}"
        for q in self.participants_q():
            yield "/api/participants?q=" + urllib.parse.quote(q)

    def stream(self):
        yield "/fluid/api/collections/stream"
        for limit in ("1", "24", "200", "9999", "0", "abc"):
            yield f"/fluid/api/collections/stream?limit={limit}"
        target = "/fluid/api/collections/stream?limit=200"
        pages = 0
        while target and pages < self.sample * 2:
            yield target
            got = self.ask(target)
            before = got.json.get("before") if got.status == 200 else None
            target = before and "/fluid/api/collections/stream?limit=200&before=" + urllib.parse.quote(before)
            if before:
                yield "/fluid/api/collections/stream?limit=3&after=" + urllib.parse.quote(before)
            pages += 1
        posts = ids_of(self.db, "contribution")
        yield "/fluid/api/collections/stream?from=start&limit=5"
        for post in self.pick(posts, 12):
            yield f"/fluid/api/collections/stream?before={post}&limit=3"
            yield f"/fluid/api/collections/stream?after={post}&limit=3"
            yield f"/fluid/api/collections/stream?from={post}&limit=3"
        yield "/fluid/api/collections/stream?before=x&after=y"
        yield "/fluid/api/collections/stream?before=nope"
        yield "/fluid/api/collections/stream?before=ent-000000000000"
        yield "/fluid/api/collections/stream?before=abc_1"
        yield "/fluid/api/collections/stream?before=1.5_x"

    def selection(self):
        posts = ids_of(self.db, "contribution")
        conversations = ids_of(self.db, "conversation")
        links = [r[0] for r in rows(self.db, "SELECT id FROM entry WHERE link_relation='replies-to' LIMIT 5")]
        for batch in batches(self.pick(posts, self.sample * BATCH)):
            yield "/fluid/api/collections/selection?ids=" + ",".join(batch)
        yield ("/fluid/api/collections/selection?ids=" + ",".join(
            posts[-5:] + conversations[:2] + links + ["ent-000000000000", "x", posts[-1]]))
        yield "/fluid/api/collections/selection"
        yield "/fluid/api/collections/selection?ids=a/b"

    def latest(self):
        yield "/fluid/api/latest"
        for limit in ("1", "5", "24", "50", "9999", "0", "abc"):
            yield f"/fluid/api/latest?limit={limit}"
            yield f"/fluid/api/latest?limit={limit}&agent_work=1"
        yield "/fluid/api/latest?agent_work=true"
        yield "/fluid/api/latest?agent_work=yes"
        yield "/fluid/api/latest?agent_work=0"
        conversations = ids_of(self.db, "conversation")
        for one in self.pick(conversations):
            yield f"/fluid/api/latest?conversation={one}&limit=24"
            yield f"/fluid/api/latest?conversation={one}&limit=24&agent_work=1"
        yield "/fluid/api/latest?conversation=ent-000000000000"
        yield "/fluid/api/latest?conversation=" + ids_of(self.db, "contribution")[0]

    def home_needs_you(self):
        yield "/fluid/api/home/needs-you"
        for limit in ("1", "3", "24", "100", "9999", "0", "abc"):
            yield f"/fluid/api/home/needs-you?limit={limit}"
        target = "/fluid/api/home/needs-you?limit=20"
        for _ in range(self.sample):
            yield target
            got = self.ask(target)
            before = got.json.get("before") if got.status == 200 else None
            if not before:
                break
            target = "/fluid/api/home/needs-you?limit=20&before=" + urllib.parse.quote(before)
        first = self.ask("/fluid/api/home/needs-you?limit=5")
        for item in (first.json.get("items") or [])[:3]:
            yield f"/fluid/api/home/needs-you?limit=2&before={item}"
        yield "/fluid/api/home/needs-you?before=opr-000000000000"
        yield "/fluid/api/home/needs-you?before=nope"
        yield "/fluid/api/home/needs-you?before=abc_1"

    def needs_you_items(self):
        yield "/fluid/api/needs-you/items"
        yield "/fluid/api/needs-you/items?x=1"

    def asks(self) -> list[str]:
        return [r[0] for r in rows(self.db, "SELECT id FROM operational WHERE act='expectation-recorded' ORDER BY seq")]

    def needs_you_asks(self):
        asks = self.asks()
        for batch in batches(self.pick(asks, self.sample * BATCH)):
            yield "/fluid/api/needs-you?ids=" + ",".join(batch)
        other = rows(self.db, "SELECT id FROM operational WHERE act='execution-started' LIMIT 2")
        yield "/fluid/api/needs-you?ids=" + ",".join(asks[:2] + [o[0] for o in other] + ["opr-000000000000", asks[0]])
        yield "/fluid/api/needs-you"
        yield "/fluid/api/needs-you?ids=a/b"

    def needs_you_post(self):
        asked = [r[0] for r in rows(self.db, "SELECT DISTINCT turn FROM operational WHERE "
                                             "act='expectation-recorded' AND turn IS NOT NULL")]
        forms = [r[0] for r in rows(self.db, "SELECT DISTINCT turn FROM operational WHERE "
                                             "act IN ('decision-form','decision-form-attached') AND turn IS NOT NULL")]
        roots = [r[0] for r in rows(self.db, "SELECT link_to FROM entry WHERE link_relation='replies-to' "
                                             "GROUP BY link_to ORDER BY COUNT(*) DESC LIMIT 10")]
        for post in self.pick(asked, self.sample) + self.pick(forms, self.sample // 2 + 1) + roots:
            yield f"/fluid/api/needs-you?post={post}"
        open_page = self.ask("/fluid/api/needs-you/items")
        for item in (open_page.json.get("items") or [])[:self.sample]:
            if item.get("post"):
                yield f"/fluid/api/needs-you?post={item['post']}"
        yield "/fluid/api/needs-you?post=ent-000000000000"
        yield "/fluid/api/needs-you?post=" + ids_of(self.db, "conversation")[0]

    def anchored_posts(self) -> list[str]:
        return [r[0] for r in rows(self.db, "SELECT DISTINCT link_to FROM entry WHERE link_relation='anchors-in'")]

    def anchors(self):
        posts = self.anchored_posts()
        plain = ids_of(self.db, "contribution")
        for batch in batches(posts):
            yield "/fluid/api/anchors?posts=" + ",".join(batch)
        for batch in batches(self.pick(plain, self.sample * BATCH)):
            yield "/fluid/api/anchors?posts=" + ",".join(batch)
        yield "/fluid/api/anchors?posts=ent-000000000000," + plain[0]
        yield "/fluid/api/anchors"
        yield "/fluid/api/anchors?posts=a/b"

    def post_anchors(self):
        posts = self.anchored_posts()
        plain = ids_of(self.db, "contribution")
        for post in posts + self.pick(plain, self.sample):
            yield f"/fluid/api/posts/{post}/anchors"
        yield "/fluid/api/posts/ent-000000000000/anchors"
        yield "/fluid/api/posts/" + ids_of(self.db, "conversation")[0] + "/anchors"
        later = rows(self.db, """SELECT l.link_from FROM entry l JOIN entry e ON e.id=l.link_to
            WHERE e.def_name='contribution' AND l.link_relation=(SELECT json_extract(body,'$.relation')
            FROM entry WHERE family='definition' AND json_extract(body,'$.substrate_role')='supersedes'
            ORDER BY seq LIMIT 1) LIMIT 3""")
        for row in later:
            yield f"/fluid/api/posts/{row[0]}/anchors"

    def changes(self):
        yield "/fluid/api/changes"
        now = rows(self.db, "SELECT (SELECT COALESCE(MAX(seq),0) FROM entry), "
                            "(SELECT COALESCE(MAX(seq),0) FROM operational), "
                            "(SELECT COALESCE(MAX(seq),0) FROM delivery)")[0]
        yield f"/fluid/api/changes?since=f1.{now[0]}.{now[1]}.{now[2]}"
        yield f"/fluid/api/changes?since=f1.{now[0] + 1}.{now[1]}.{now[2]}"
        yield f"/fluid/api/changes?since=f1.{now[0] - 500}.{now[1] - 500}.{now[2]}"
        yield "/fluid/api/changes?since=nope"
        yield "/fluid/api/changes?since=f1.1.2"
        yield "/fluid/api/changes?since=f2.1.2.3"
        for back in (1, 2, 3, 5, 10, 20, 50, 100, 200, 201):
            for e, o, d in ((back, back, 0), (back, 0, 0), (0, back, 0), (0, 0, min(back, now[2]))):
                since = f"f1.{now[0] - e}.{now[1] - o}.{now[2] - d}"
                yield f"/fluid/api/changes?since={since}"
                yield f"/fluid/api/changes?since={since}&threads=1"

    def sets(self) -> list[str]:
        return ids_of(self.db, "response-set")

    def response_sets(self):
        posts = [r[0] for r in rows(self.db, "SELECT DISTINCT link_to FROM entry WHERE link_relation='responds-to'")]
        for post in self.pick(posts):
            yield f"/fluid/api/response-sets?post={post}"
        yield "/fluid/api/response-sets"
        yield "/fluid/api/response-sets?post=ent-000000000000"
        yield "/fluid/api/response-sets?post=" + ids_of(self.db, "contribution")[0]

    def response_set(self):
        sets = self.sets()
        for one in self.pick(sets):
            yield f"/fluid/api/response-sets/{one}"
        yield "/fluid/api/response-sets/ent-000000000000"

    def response_history(self):
        sets = self.sets()
        for one in self.pick(sets):
            yield f"/fluid/api/response-sets/{one}/history?words=1"
            fields = rows(self.db, """SELECT DISTINCT json_extract(e.body,'$.field'), e.attributed_to FROM entry l
                JOIN entry e ON e.id=l.link_from WHERE l.link_relation='in-response-set' AND l.link_to=?
                AND e.def_name='answer'""", one)
            for field, by in fields[:6]:
                yield f"/fluid/api/response-sets/{one}/history?field=" + urllib.parse.quote(str(field))
            if fields:
                yield f"/fluid/api/response-sets/{one}/history?words=1&by={fields[0][1]}"
        yield f"/fluid/api/response-sets/{sets[0]}/history" if sets else "/fluid/api/response-sets/x/history"
        yield "/fluid/api/response-sets/ent-000000000000/history?words=1"

    def response_accounting(self):
        sets = self.sets()
        for one in sets:
            yield f"/fluid/api/response-sets/{one}/accounting"
        yield "/fluid/api/response-sets/ent-000000000000/accounting"

    def family(self, name: str):
        return getattr(self, name.replace("-", "_"))()


def fetch(port: int, target: str, wait: float = 120.0) -> tuple[Answer, float]:
    started = time.perf_counter()
    got = Answer(exchange(port, request("GET", target, headers=CLIENT), wait=wait))
    return got, time.perf_counter() - started


def first_difference(a: bytes, b: bytes) -> dict:
    n = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
    return {"at": n, "python_len": len(a), "front_len": len(b),
            "python": a[max(0, n - 120):n + 200].decode("utf-8", "replace"),
            "front": b[max(0, n - 120):n + 200].decode("utf-8", "replace")}


def pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(len(ordered) * p))] * 1000, 2)


def keep_pulsing(port: int, stop: threading.Event) -> None:
    while not stop.wait(1.0):
        try:
            exchange(port, request("GET", "/api/pulse", headers=CLIENT), wait=5.0)
        except OSError:
            pass


def run(args) -> int:
    copy = pathlib.Path(args.copy).resolve()
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    base = args.port_base
    py_port, relay_port, front_port = base, base + 2, base + 3
    db = sqlite3.connect(f"file:{(copy / 'corpus.db').as_posix()}?mode=ro", uri=True)
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.update(MENTIS_BOOT_SECRET=SECRET, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    before = rows(db, "SELECT (SELECT MAX(seq) FROM entry),(SELECT MAX(seq) FROM operational),(SELECT MAX(seq) FROM delivery)")
    py_log = open(out / "python.log", "ab")
    python = subprocess.Popen([sys.executable, "-m", "mentis.web", str(copy), "--host", "127.0.0.1",
                               "--port", str(py_port), "--workspace", str(out / "ws"), "--mars", NO_MARS],
                              cwd=REPO, env=env, stdout=py_log, stderr=py_log)
    relay = Relay(relay_port, py_port)
    front = None
    stop = threading.Event()
    try:
        wait_port(py_port)
        front_log = open(out / "front.log", "ab")
        front = subprocess.Popen([args.front, str(copy), "--host", "127.0.0.1", "--port", str(front_port),
                                  "--upstream", f"http://127.0.0.1:{relay_port}", "--dist", str(out)],
                                 env=env, stdout=front_log, stderr=front_log)
        wait_port(front_port)
        threading.Thread(target=keep_pulsing, args=(front_port, stop), daemon=True).start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            got = fetch(front_port, "/api/pulse", 5.0)[0]
            if got.status == 200 and "live" not in got.json:
                break
            time.sleep(.1)
        else:
            raise SystemExit(f"the snapshot never became fresh: {got}")
        ask_python = lambda target: fetch(py_port, target)[0]  # noqa: E731
        corpus = Corpus(db, args.sample, ask_python)
        families = args.families.split(",") if args.families else list(EVERY)
        report: dict = {}
        with open(out / "differences.jsonl", "w", encoding="utf-8") as diffs:
            for family in families:
                tally = {"requests": 0, "answered": 0, "different": 0, "forwarded": 0,
                         "forwarded_different": 0, "statuses": {}}
                py_times, front_times, forward_times = [], [], []
                seen = set()
                for target in corpus.family(family):
                    if target in seen:
                        continue
                    seen.add(target)
                    theirs, py_took = fetch(py_port, target)
                    relay.take()
                    ours, took = fetch(front_port, target)
                    upward = relay.take()
                    forwarded = target in upward
                    tally["requests"] += 1
                    tally["statuses"][str(theirs.status)] = tally["statuses"].get(str(theirs.status), 0) + 1
                    same = ours.comparable == theirs.comparable
                    py_times.append(py_took)
                    if forwarded:
                        tally["forwarded"] += 1
                        forward_times.append(took)
                        tally["forwarded_different"] += not same
                    elif same:
                        tally["answered"] += 1
                        front_times.append(took)
                    else:
                        tally["different"] += 1
                        front_times.append(took)
                    if not same:
                        diffs.write(json.dumps({
                            "family": family, "target": target, "forwarded": forwarded,
                            "python_status": theirs.status, "front_status": ours.status,
                            "python_headers": [h for h in theirs.headers if h[0] != "Date"],
                            "front_headers": [h for h in ours.headers if h[0] != "Date"],
                            **first_difference(theirs.body, ours.body)}, ensure_ascii=False) + "\n")
                        diffs.flush()
                tally["python_ms"] = {"p50": pct(py_times, .5), "p95": pct(py_times, .95), "max": pct(py_times, 1)}
                tally["rust_answer_ms"] = {"p50": pct(front_times, .5), "p95": pct(front_times, .95), "max": pct(front_times, 1)}
                tally["forward_ms"] = {"p50": pct(forward_times, .5), "p95": pct(forward_times, .95), "max": pct(forward_times, 1)}
                report[family] = tally
                print(family, json.dumps(tally), flush=True)
                (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        after = rows(db, "SELECT (SELECT MAX(seq) FROM entry),(SELECT MAX(seq) FROM operational),(SELECT MAX(seq) FROM delivery)")
        report["_record_unchanged"] = before == after
        (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        total = {k: sum(v[k] for f, v in report.items() if not f.startswith("_"))
                 for k in ("requests", "answered", "different", "forwarded", "forwarded_different")}
        print("TOTAL", json.dumps(total), "record unchanged:", before == after, flush=True)
        return 0 if total["different"] == 0 and total["forwarded_different"] == 0 else 1
    finally:
        stop.set()
        relay.close()
        for proc in (front, python):
            if proc is not None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
                proc.wait(timeout=30)
        db.close()


LOAD_TARGETS = ("/api/conversations", "/fluid/api/conversations?activity=1&limit=24")
#: What a level asks of Python while the routes are measured.
LOAD_BUSY = ("/api/working", "/fluid/api/home/work?limit=50", "/api/activity",
             "/fluid/api/needs-you/items")


def load(args) -> int:
    """The live-dependent routes' forward rate while Python is busy. Figures, no pass or fail."""
    copy = pathlib.Path(args.copy).resolve()
    out = pathlib.Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    base = args.port_base
    py_port, relay_port, front_port = base, base + 2, base + 3
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
    env.update(MENTIS_BOOT_SECRET=SECRET, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.pop("PYTHONPATH", None)
    py_log = open(out / "python.log", "ab")
    python = subprocess.Popen([sys.executable, "-m", "mentis.web", str(copy), "--host", "127.0.0.1",
                               "--port", str(py_port), "--workspace", str(out / "ws"), "--mars", NO_MARS],
                              cwd=REPO, env=env, stdout=py_log, stderr=py_log)
    relay = Relay(relay_port, py_port)
    front = None
    stop = threading.Event()
    report = {}
    try:
        wait_port(py_port)
        front_log = open(out / "front.log", "ab")
        front = subprocess.Popen([args.front, str(copy), "--host", "127.0.0.1", "--port", str(front_port),
                                  "--upstream", f"http://127.0.0.1:{relay_port}", "--dist", str(out)],
                                 env=env, stdout=front_log, stderr=front_log)
        wait_port(front_port)
        threading.Thread(target=keep_pulsing, args=(front_port, stop), daemon=True).start()
        for threads in (0, 2, 8):
            done = threading.Event()

            def busy(which: int) -> None:
                while not done.is_set():
                    fetch(py_port, LOAD_BUSY[which % len(LOAD_BUSY)], 60.0)
                    which += 1

            pool = [threading.Thread(target=busy, args=(i,), daemon=True) for i in range(threads)]
            for one in pool:
                one.start()
            time.sleep(3)
            level = {}
            for target in LOAD_TARGETS:
                times, forwarded, asked = [], 0, 0
                until = time.monotonic() + args.seconds
                while time.monotonic() < until:
                    relay.take()
                    times.append(fetch(front_port, target, 60.0)[1])
                    forwarded += target in relay.take()
                    asked += 1
                level[target] = {"asked": asked, "forwarded": forwarded,
                                 "rate": round(forwarded / max(asked, 1), 3),
                                 "p50_ms": pct(times, .5), "p95_ms": pct(times, .95)}
            done.set()
            for one in pool:
                one.join(90)
            report[f"{threads} busy threads"] = level
            print(threads, json.dumps(level), flush=True)
        (out / "load.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
        return 0
    finally:
        stop.set()
        relay.close()
        for proc in (front, python):
            if proc is not None:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, check=False)
                proc.wait(timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="what", required=True)
    one = sub.add_parser("copy")
    one.add_argument("source")
    one.add_argument("dest")
    two = sub.add_parser("run")
    two.add_argument("copy")
    two.add_argument("--front", required=True)
    two.add_argument("--out", required=True)
    two.add_argument("--families")
    two.add_argument("--sample", type=int, default=20)
    two.add_argument("--port-base", type=int, default=34000)
    four = sub.add_parser("shapes")
    four.add_argument("source")
    four.add_argument("dest")
    three = sub.add_parser("load")
    three.add_argument("copy")
    three.add_argument("--front", required=True)
    three.add_argument("--out", required=True)
    three.add_argument("--seconds", type=float, default=30.0)
    three.add_argument("--port-base", type=int, default=34000)
    args = parser.parse_args()
    if args.what == "load":
        return load(args)
    if args.what == "copy":
        copy_brain(pathlib.Path(args.source), pathlib.Path(args.dest))
        return 0
    if args.what == "shapes":
        for name, (state, what) in shapes(pathlib.Path(args.source), pathlib.Path(args.dest)).items():
            print(f"{state:8} {name}" + (f": {what}" if state == "refused" else ""), flush=True)
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
