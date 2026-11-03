"""The other side of R5.1's byte test: what Python answers for each case, on a changed BRAIN-SEED.

    object_reads_side.py change <brain>    what `agent_reads_side.py change` writes, and what these
                                           routes read: attachments, object references, odd letters
    object_reads_side.py wire <brain>      print every case as JSON, each with Python's answer
    object_reads_side.py declare <brain>   declare a source, so a `find` is the source scan's
    object_reads_side.py grow <brain> <n>  a Conversation of n posts, for the search's cost
    object_reads_side.py sample <brain>    a sample of what a copy of a real Brain answers, timed
    object_reads_side.py letters           `re`'s own relation, for every ASCII character

The Rust side answers each case through the route's handler or the door's read, and compares bytes or
shows it forwarded. Python's `handle_get` and `_api` are read here, not imitated: what they do with an
exception is stated once, in `_fluid` and `_references`.
"""

import json
import pathlib
import random
import re
import sqlite3
import sys
import time
import types
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "mentis-ops" / "tests" / "support"))

import agent_reads_side  # noqa: E402
from agent_reads_side import _text  # noqa: E402
from mentis import artifacts, worker  # noqa: E402
from mentis.conversation import render_check, versions  # noqa: E402
from mentis.fluid import PREFIX, objects as fluid_objects  # noqa: E402
from mentis.fluid import read as fluid_read  # noqa: E402
from mentis.fluid import route as fluid_route  # noqa: E402
from mentis.spine import held  # noqa: E402

import python_side  # noqa: E402

#: The run the door's `with_choices` is told of. It raised no decision.
INSTANCE = "opr-norunbythisname"
#: The most of a document that is drawn.
DOC_MAX = fluid_objects.DOC_MAX

BLOCK = "```chart version=1 form=bar x=item y=value\nitem,value\nA,1\n```"


def _hold(corpus, cv, owner, home, data, name, media="text/plain"):
    return artifacts.hold(corpus, cv, data, act=artifacts.SUBMITTED, actor=owner,
                          source=f"submission:{owner}", door="human-ingress", conversation=home,
                          claimed_name=name, claimed_media_type=media)["admission"]


def change(brain):
    agent_reads_side.change(brain)
    corpus, cv = python_side._open(brain)
    owner = cv.resolve_participant("@r1-owner")
    known = python_side._named(corpus, "conversation", "R1 known conversation")
    second = python_side._named(corpus, "conversation", "R1 second conversation")

    # -- what a search and a find read ---------------------------------------------------------------
    for words in ("KELVIN and kelvin in one", "Kelvin with the sign", "ſo long, İstanbul ı",
                  "a b  two  spaces   here and\ttabs\nand lines", "needle " * 80,
                  "words before " * 30 + "needle" + " words after" * 30,
                  "x" * 300 + " needle " + "y" * 300, "café \U0001f600 needle",
                  "Sigma Σ at the end Σ", "aaa " + "longphrase " * 30 + "bbb", "fencedword\n```form version=1 name=q\nx\n```"):
        cv.say(known, owner, _text(words))
    cv.say(second, owner, [{"type": "text", "text": "a turn "},
                           {"type": "topic", "ref": known, "text": "needle in a reference"},
                           {"type": "media", "ref": known, "text": "needle not in flow"}])
    edited = cv.say(known, owner, _text("needle before its edit"))
    versions.edit(cv, edited, by=owner, text="an edit took it out")
    gone = cv.say(known, owner, _text("needle in a deleted post"))
    versions.delete(cv, gone, by=owner, because="taken back")
    included = cv.say(second, owner, _text("needle included from elsewhere"))
    cv.link_into(included, known, by=owner)

    # -- documents -----------------------------------------------------------------------------------
    plain = _hold(corpus, cv, owner, known, "words é \U0001f600\n".encode(), "plain.md")
    latin = _hold(corpus, cv, owner, known, b"caf\xe9 \xff\xfe \xed\xa0\x80 \xf4\x90\x80\x80 \xc0\xaf end",
                  "latin.txt")
    # Over the limit, with a character the cut splits: each of its bytes, at every distance.
    cuts = [_hold(corpus, cv, owner, known, b"a" * (DOC_MAX - back) + "\U0001f600\U0001f600".encode(),
                  f"cut-{back}.txt") for back in range(0, 5)]
    junk = _hold(corpus, cv, owner, known, b"a" * (DOC_MAX - 2) + b"\xff" * 16, "junk.txt")
    exact = _hold(corpus, cv, owner, known, b"b" * DOC_MAX, "exact.txt")
    missing = _hold(corpus, cv, owner, known, b"bytes that go missing", "missing.txt")
    corrupt = _hold(corpus, cv, owner, known, b"bytes that change", "corrupt.txt")
    purged = _hold(corpus, cv, owner, known, b"bytes that are purged", "purged.txt")
    artifacts.purge(corpus, cv, purged, by=owner, because="R5.1's test")
    for ref, damage in ((missing, None), (corrupt, b"other bytes")):
        digest = held.digest_of(corpus.read([ref])[0]["body"]["locator"])
        path = held.path(corpus.root, digest)
        if damage is None:
            path.unlink()
        else:
            path.write_bytes(damage)

    # -- object references ---------------------------------------------------------------------------
    source = cv.say(known, owner, _text(f"what they point at\n\n{BLOCK}\n"))
    attached = cv.say(known, owner, [artifacts.part(plain, corpus=corpus)])
    got = fluid_objects.post_objects(corpus, source)
    block = next(o for o in got["objects"] if o["kind"] != "post-text")
    media = next(o for o in fluid_objects.post_objects(corpus, attached)["objects"])

    def ref(post, o, **more):
        return {"type": "object", "ref": post, "key": o["key"], "exact": o["address"]["exact"],
                "text": "what the author sees",
                "about": {"kind": o.get("kind"), "title": o.get("title"), "home": known,
                          "home_name": "R1 known conversation", "number": 3, "by": "@r1-owner"},
                **more}

    whole = ref(source, block)
    # Then the object goes in an edit: the exact address still resolves and the live one doesn't.
    later = cv.say(known, owner, _text(f"edited away\n\n{BLOCK}\n"))
    away = fluid_objects.post_objects(corpus, later)
    away = next(o for o in away["objects"] if o["kind"] != "post-text")
    edited_away = ref(later, away)
    versions.edit(cv, later, by=owner, text="no blocks now")
    deleted = cv.say(known, owner, _text(f"deleted away\n\n{BLOCK}\n"))
    of_deleted = next(o for o in fluid_objects.post_objects(corpus, deleted)["objects"]
                      if o["kind"] != "post-text")
    deleted_ref = ref(deleted, of_deleted)
    versions.delete(cv, deleted, by=owner, because="taken back")
    holder = cv.say(known, owner, [
        {"type": "text", "text": "see these "},
        whole,
        ref(attached, media),
        edited_away,
        deleted_ref,
        {**whole, "exact": "not an address"},
        {**whole, "exact": "exact:ent-000000000000:0:nothing"},
        {**whole, "key": "no-such-key"},
        {**whole, "ref": "ent-000000000000"},
        {**whole, "ref": known},
        {**whole, "ref": "", "key": ""},
        {"type": "object", "ref": source, "key": block["key"], "exact": None},
        {"type": "text", "text": " and that"},
    ])
    edited_holder = cv.say(known, owner, [whole])
    versions.edit(cv, edited_holder, by=owner, text="no references now")
    deleted_holder = cv.say(known, owner, [whole])
    versions.delete(cv, deleted_holder, by=owner, because="taken back")
    many = cv.say(known, owner, [whole] * 65)
    plain_post = cv.say(known, owner, _text("no references at all"))
    corpus.close()
    (pathlib.Path(brain) / "r5-1-world.json").write_text(json.dumps({
        "plain": plain, "latin": latin, "cuts": cuts, "junk": junk, "exact": exact,
        "missing": missing, "corrupt": corrupt, "purged": purged, "known": known, "second": second,
        "source": source, "attached": attached, "whole": whole, "holder": holder,
        "edited_holder": edited_holder, "deleted_holder": deleted_holder, "many": many,
        "plain_post": plain_post, "later": later, "deleted": deleted}), encoding="utf-8")


def declare(brain):
    from mentis.sources import DECLARED
    corpus, cv = python_side._open(brain)
    owner = cv.resolve_participant("@r1-owner")
    cv.record_act(actor=owner, act=DECLARED,
                  detail={"collection": "col-1", "connector": "folder", "name": "A declared one"})
    corpus.close()


def grow(brain, count):
    corpus, cv = python_side._open(brain)
    owner = cv.resolve_participant("@r1-owner")
    home = python_side._named(corpus, "conversation", "R1 second conversation")
    for at in range(int(count)):
        cv.say(home, owner, _text(f"post {at} of a long Conversation, with ordinary words in it"))
    corpus.close()
    print(json.dumps({"home": home}))


def _fluid(st, rest, query):
    """`handle_get`'s answers, as far as its routes raise them."""
    try:
        value = fluid_route(st, PREFIX + rest, urllib.parse.parse_qs(query))
    except fluid_read.BadRequest as exc:
        return {"status": 400, "body": json.dumps({"error": str(exc), "kind": "BadRequest"})}
    except fluid_objects.Unresolved as exc:
        return {"status": 404, "body": json.dumps(exc.payload)}
    except Exception as exc:                              # noqa: BLE001
        return {"raises": f"{type(exc).__name__}: {exc}"}
    return {"status": 200, "body": json.dumps(value, default=str)}


def _references(surface, query):
    """`_routes`' `/api/references`."""
    parsed = urllib.parse.parse_qs(query)

    def one(name, default=None):
        got = parsed.get(name)
        return got[0] if got else default

    try:
        ref = one("ref")
        value = (surface.resolve(ref) if ref else
                 surface.find(one("q", "") or "", int(one("limit", 12)), here=one("conversation")))
    except Exception as exc:                              # noqa: BLE001
        return {"raises": f"{type(exc).__name__}: {exc}"}
    return {"status": 200, "body": json.dumps(value, default=str)}


def _worker(surface, corpus, op, args):
    """`_routes`' `/api/worker`, for a grant whose run raised no decision."""
    try:
        value = worker._result(surface, op, dict(args), participant=None, grant={}, scope="brain")
        if op == "check_rendering" and isinstance(value, dict):
            text = args.get("text")
            value = render_check.with_choices(value, [(None, text if isinstance(text, str) else "")],
                                              corpus, INSTANCE, posted=False)
    except Exception as exc:                              # noqa: BLE001
        return {"raises": f"{type(exc).__name__}: {exc}"}
    return {"status": 200, "body": json.dumps(value, default=str)}


def _quote(text):
    return urllib.parse.quote(text, safe="")


def wire(brain):
    corpus, cv = python_side._open(brain)
    surface = worker.Surface(brain, corpus=corpus)
    st = types.SimpleNamespace(corpus=corpus, cv=cv, agents=None)
    w = json.loads((pathlib.Path(brain) / "r5-1-world.json").read_text(encoding="utf-8"))
    db = sqlite3.connect(f"file:{brain}/corpus.db?mode=ro", uri=True)
    posts = [r[0] for r in db.execute(
        "SELECT DISTINCT e.id FROM entry e JOIN entry l ON l.link_from = e.id "
        "AND l.link_relation = 'in-conversation' WHERE e.family = 'entry' "
        "AND e.def_name = 'contribution' AND e.link_relation IS NULL ORDER BY e.seq")]
    versions_of = [r[0] for r in db.execute(
        "SELECT e.id FROM entry e WHERE e.family = 'entry' AND e.def_name = 'contribution' AND "
        "e.id NOT IN (SELECT l.link_from FROM entry l WHERE l.link_relation = 'in-conversation') LIMIT 6")]
    conversations = [r[0] for r in db.execute(
        "SELECT id FROM entry WHERE def_name = 'conversation' AND family = 'entry' "
        "AND link_relation IS NULL ORDER BY seq")]
    topics = [r[0] for r in db.execute("SELECT id FROM entry WHERE def_name = 'topic' LIMIT 4")]
    others = [r[0] for r in db.execute(
        "SELECT id FROM entry WHERE family != 'entry' OR def_name NOT IN ('contribution') "
        "ORDER BY seq DESC LIMIT 40")]
    relations = [r[0] for r in db.execute(
        "SELECT DISTINCT link_relation FROM entry WHERE link_relation IS NOT NULL")]
    db.close()
    known, second, whole = w["known"], w["second"], w["whole"]
    cases = []

    def route(name, rest, sort, *queries):
        for query in queries:
            answer = (_references(surface, query) if name == "references"
                      else _fluid(st, rest, query))
            cases.append({"route": name, "path": PREFIX + rest if rest else "/api/references",
                          "query": query, "sort": sort, **answer})

    # -- /fluid/api/document -------------------------------------------------------------------------
    route("document", "document", "held", f"ref={w['plain']}", f"ref={w['latin']}",
          f"ref={w['exact']}", f"ref={w['junk']}", *[f"ref={r}" for r in w["cuts"]])
    route("document", "document", "no bytes", f"ref={w['missing']}", f"ref={w['corrupt']}",
          f"ref={w['purged']}", "ref=adm-000000000000", f"ref={known}", f"ref={posts[0]}",
          "ref=it%27s", "ref=caf%C3%A9")
    route("document", "document", "refused", "", "ref=", "other=1")

    # -- /fluid/api/object-refs ----------------------------------------------------------------------
    route("object-refs", "object-refs", "post", *[f"post={p}" for p in posts])
    route("object-refs", "object-refs", "post", *[f"post={p}" for p in versions_of])
    route("object-refs", "object-refs", "not a post", f"post={known}", "post=ent-000000000000",
          "post=it%27s", "post=caf%C3%A9", *[f"post={o}" for o in others[:8]])
    key = _quote(whole["key"])
    exact = _quote(whole["exact"])
    route("object-refs", "object-refs", "one part",
          f"ref={whole['ref']}&key={key}", f"ref={whole['ref']}&key={key}&exact={exact}",
          f"ref={whole['ref']}&key=nothing", f"ref={whole['ref']}&key={key}&exact=nonsense",
          f"ref={w['later']}&key={key}", f"ref={w['deleted']}&key={key}",
          f"ref=ent-000000000000&key={key}", f"ref={known}&key={key}",
          f"ref=a:b&key=c:d", "ref=caf%C3%A9&key=x", "ref=x&key=caf%C3%A9",
          f"post={w['plain_post']}&ref={whole['ref']}&key={key}")
    route("object-refs", "object-refs", "refused", "", "post=", "ref=x", "key=x", "ref=&key=x")

    # -- /fluid/api/search ---------------------------------------------------------------------------
    needles = ["longphrase " * 25 + "longphrase", "longphrase " * 22 + "long", "needle", "NEEDLE", "kelvin", "KELVIN", "so", "SO", "i", "istanbul", "caf", "two  spaces",
               "a b", "spaces here", "tabs\nand", "words", "x", "turn", "reference", "needle in a",
               "not in flow", "deleted", "an edit", "before its edit", "zzz-no-such", "a", " e ", "  ",
               "%", "_", ".", "(", "[a-z]", "\\", "*"]
    for conversation in (known, second):
        for needle in needles:
            route("post-search", "search", "needle",
                  f"conversation={conversation}&q={_quote(needle)}",
                  f"conversation={conversation}&q={_quote(needle)}&limit=2")
    route("post-search", "search", "paged",
          f"conversation={known}&q=needle&limit=1", f"conversation={known}&q=needle&limit=500",
          f"conversation={known}&q=needle&limit=9999", f"conversation={known}&q=needle&before={posts[-1]}",
          f"conversation={known}&q=needle&before={posts[3]}&limit=1",
          f"conversation={known}&q=needle&before=1_1", f"conversation={known}&q=needle&before=99999999999_0")
    route("post-search", "search", "refused", "", "q=x", "conversation=", f"conversation={known}",
          f"conversation={known}&q=", f"conversation={known}&q=%20", "conversation=ent-000000000000&q=x",
          f"conversation={posts[0]}&q=x", "conversation=it%27s&q=x", "conversation=caf%C3%A9&q=x",
          f"conversation={known}&q=x&limit=0", f"conversation={known}&q=x&limit=x",
          f"conversation={known}&q=x&before=abc_1", f"conversation={known}&q=x&before=x",
          f"conversation={known}&q=x&before=ent-000000000000",
          f"conversation={known}&q={'y' * 501}", f"conversation={known}&q={'y' * 500}")
    route("post-search", "search", "other letters",
          f"conversation={known}&q={_quote('caf' + chr(0xe9))}",
          f"conversation={known}&q={_quote(chr(0x212a))}elvin",
          f"conversation={known}&q={_quote(chr(0x3a3))}")
    route("post-search", "search", "garbled", f"conversation={known}&q=%ff", f"conversation={known}&q=a#b")

    # -- /api/references: resolve --------------------------------------------------------------------
    route("references", "", "resolve", *[f"ref={p}" for p in posts[:12]], *[f"ref={c}" for c in conversations],
          *[f"ref={t}" for t in topics], "ref=ent-000000000000", "ref=it%27s")

    # -- find, at both doors -------------------------------------------------------------------------
    questions = ["", " ", "#", "@", "##@", "needle", "NEEDLE", "#needle", "@r1", "@r1-owner", "r1", "known",
                 "second", "R1 KNOWN", "topic", "needle topic", "plain", "café", "café", "σ",
                 "Σ", "a b", "two  spaces", "kelvin", "K", "İ", "stanbul", "1", "2", "3", "#2",
                 "9", "0", "007", "99999", "٣", "²", "fencedword", "no-such-relation",
                 "zzz-no-such", "said", "words", " words ", "turn", "x" * 501, "x" * 500, "#" + "x" * 500,
                 *relations[:8], *[p for p in posts[:6]], *conversations[:3], *topics[:2], *others[:10],
                 "ent-000000000000", "opr-000000000000", "adm-000000000000", posts[0].upper(),
                 "ent-", "ent-zz"]
    for question in questions:
        quoted = _quote(question)
        route("references", "", "find", f"q={quoted}", f"q={quoted}&limit=2", f"q={quoted}&limit=1",
              f"q={quoted}&conversation={known}", f"q={quoted}&conversation={second}&limit=3",
              f"q={quoted}&conversation=ent-000000000000")
    route("references", "", "find", "", "limit=3", "conversation=" + known, "q=word&limit=500",
          "q=word&limit=%207", "q=2&limit=100000")
    route("references", "", "odd limit", "q=word&limit=0", "q=word&limit=-1", "q=word&limit=x",
          "q=word&limit=1.5", "q=word&limit=%D9%A3")

    def asked(op, sort, *many):
        for args in many:
            cases.append({"op": op, "args": args, "sort": sort, **_worker(surface, corpus, op, args)})

    asked("find", "find", *[{"q": q} for q in questions], *[{"q": q, "limit": n} for q in questions
                                                            for n in (1, 2, 3)],
          {}, {"q": None}, {"limit": 0}, {"q": "word", "limit": None}, {"q": "word", "limit": 0},
          {"q": "word", "limit": 1000})
    asked("find", "odd arguments", {"q": 5}, {"q": ["x"]}, {"q": True}, {"q": "w", "limit": "3"},
          {"q": "w", "limit": 1.5}, {"q": "w", "limit": -1}, {"q": "w", "limit": True},
          {"q": "w", "limit": 2.0})

    # -- check_rendering -----------------------------------------------------------------------------
    good = BLOCK
    bad = "```chart version=1 form=nothing\nnot,a\nchart\n```"
    two_problems = bad + "\n\nwords\n\n```table version=1 key=missing\na,b\n1,2\n```"
    bare = "```\nno info string\n```"
    timer = (f'```timer version=1 name=t title="x" about={known},ent-000000000000,{posts[0]},{others[0]}\n'
             "```")
    malformed_timer = '```timer version=1 name=t about=not-an-id\n```'
    asked("check_rendering", "checked",
          *[{"text": t} for t in ("plain words", "café \U0001f600", good, bad, two_problems, bare, timer,
                                  malformed_timer, "- one item only", "words\n\n1. one item",
                                  good + "\n\n" + bad, 'quote " and \\ in text', "\ttab\r\nline")],
          {"text": bad, "syntax": "chart"}, {"text": "plain", "syntax": None})
    asked("check_rendering", "too long", {"text": "x" * 400_001}, {"text": "\U0001f600" * 400_001},
          {"text": "x" * 400_000})
    asked("check_rendering", "forward: a NUL", {"text": "a\0b"})
    asked("check_rendering", "nothing given", {}, {"text": ""}, {"text": None}, {"syntax": ""},
          {"text": "", "syntax": ""}, {"text": None, "syntax": None})
    asked("check_rendering", "forward: a list", {"text": "- a\n- b"}, {"text": "pick one:\n1. a\n2. b"},
          {"text": "Which should I do?\n- this\n- that"},
          {"text": "```checklist version=1 name=c title=\"Choose one\"\n- [ ] a\n- [ ] b\n```"},
          {"text": "- a\n- b\n\nx" * 3}, {"text": "x" * 400_001 + "\n- a\n- b"})
    asked("check_rendering", "forward: syntax", {"syntax": "chart"}, {"syntax": "all"}, {"syntax": "nothing"})
    asked("check_rendering", "forward: odd", {"text": 5}, {"text": 0}, {"text": ["x"]}, {"text": True},
          {"syntax": 5}, {"syntax": 0}, {"text": "", "syntax": 1})

    corpus.close()
    print(json.dumps({"cases": cases, "world": w}))


def sample(brain, seed="5"):
    """What a copy of a real Brain answers, with how long Python took: a sample of what each route
    reads there, for the same comparison, a forward rate and a cost. `find` is asked with its acquired
    hits taken off, as the record half it is here: on such a Brain the route itself forwards."""
    corpus, cv = python_side._open(brain)
    surface = worker.Surface(brain, corpus=corpus)
    st = types.SimpleNamespace(corpus=corpus, cv=cv, agents=None)
    pick = random.Random(int(seed))
    db = sqlite3.connect(f"file:{brain}/corpus.db?mode=ro", uri=True)

    def column(sql):
        return [r[0] for r in db.execute(sql)]

    posts = column("SELECT DISTINCT e.id FROM entry e JOIN entry l ON l.link_from = e.id "
                   "AND l.link_relation = 'in-conversation' WHERE e.family = 'entry' "
                   "AND e.def_name = 'contribution' AND e.link_relation IS NULL")
    holding = column("SELECT e.id FROM entry e WHERE e.def_name = 'contribution' AND e.family = 'entry' "
                     "AND e.link_relation IS NULL AND e.body LIKE '%\"object\"%'")
    held_refs = column(
        "SELECT id FROM entry WHERE family = 'admission' AND json_extract(body, '$.content') = 'held' "
        "AND json_extract(body, '$.envelope.bulk_source') IS NULL")
    by_size = [(r[0], r[1]) for r in db.execute(
        "SELECT l.link_to, COUNT(*) FROM entry l WHERE l.link_relation = 'in-conversation' "
        "GROUP BY l.link_to ORDER BY COUNT(*) DESC")]
    aliases = [r[0] for r in db.execute(
        "SELECT json_extract(body, '$.alias') FROM entry WHERE def_name = 'participant' "
        "AND json_extract(body, '$.alias') IS NOT NULL LIMIT 5")]
    declared = column("SELECT COUNT(*) FROM operational WHERE act = 'source-collection-declared'")[0]
    db.close()

    def sampled(rows, count):
        return pick.sample(rows, min(count, len(rows)))

    cases = []

    def timed(call):
        started = time.perf_counter()
        answer = call()
        return {**answer, "py_ms": (time.perf_counter() - started) * 1e3}

    for post in sampled(holding, 80) + sampled(posts, 80):
        cases.append({"route": "object-refs", "path": PREFIX + "object-refs", "query": f"post={post}",
                      "sort": "post", **timed(lambda: _fluid(st, "object-refs", f"post={post}"))})
    for ref in sampled(held_refs, 120):
        cases.append({"route": "document", "path": PREFIX + "document", "query": f"ref={ref}",
                      "sort": "document", **timed(lambda: _fluid(st, "document", f"ref={ref}"))})
    conversations = by_size[:3] + sampled(by_size[3:], 6)
    for home, count in conversations:
        for needle in ("the", "mentis", "rust", "zzz-no-such-words", "Which"):
            query = f"conversation={home}&q={needle}"
            cases.append({"route": "post-search", "path": PREFIX + "search", "query": query,
                          "sort": f"{count} posts",
                          **timed(lambda: _fluid(st, "search", query))})
    for post in sampled(posts, 120):
        said = worker.Surface._turn_line(surface, surface._entry(post))
        args = {"text": said}
        cases.append({"op": "check_rendering", "args": args, "sort": "a post's words",
                      **timed(lambda: _worker(surface, corpus, "check_rendering", args))})

    # The record half of `find`: the same `Surface.find`, with what R5.2 answers taken off.
    surface._acquired_hits = lambda needle: []
    surface._content_hits = lambda q: ([], {
        "non_text": 0, "by_type": {}, "extraction": {}, "extraction_files": [], "unreadable": 0,
        "unreadable_files": [], "over_budget": 0})
    questions = ["mentis", "rust", "zzz-no-such-words", "120", "1", "in-conversation", "carries-intake",
                 *aliases, *sampled(posts, 6), *(c for c, _ in by_size[:2])]
    for question in questions:
        args = {"q": question}
        cases.append({"record_hits": question, "args": args, "sort": "record hits",
                      **timed(lambda: _worker(surface, corpus, "find", args))})
    corpus.close()
    print(json.dumps({"cases": cases, "declared": declared, "posts": len(posts), "holding": len(holding),
                      "held": len(held_refs), "sizes": [c for _, c in by_size[:5]]}))


def letters():
    """`re.IGNORECASE`'s relation for every printable ASCII needle: which code points it matches, past
    itself and its case pair."""
    out = {}
    for code in range(0x20, 0x7f):
        pattern = re.compile(re.escape(chr(code)), re.IGNORECASE)
        out[chr(code)] = [c for c in range(0x110000)
                          if not 0xd800 <= c < 0xe000 and pattern.fullmatch(chr(c))]
    print(json.dumps(out))


if __name__ == "__main__":
    what, *rest = sys.argv[1:]
    if what == "letters":
        letters()
    else:
        {"change": change, "wire": wire, "declare": declare, "grow": grow,
         "sample": sample}[what](*rest)
