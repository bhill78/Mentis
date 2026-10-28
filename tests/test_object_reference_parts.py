"""Object reference parts (Fluid final W4; fluid-arrange DROP.md, both owner
decisions of 2026-10-28).

An object inside a post is referenced by its post and key -- no new Kind, no
new entry for it -- in a content part of an ordinary post. What must hold:

  * where every post is written (the owner's door and a worker's `respond`):
    `ref` is a post that stands, `exact` resolves at that version with the
    same key, `about` is bounded, and a refusal is said in words and writes
    nothing;
  * it is a REFERENCE part, never an attachment;
  * the resolve read answers with the current live object or why not --
    never a substitute;
  * an addressed agent is given THAT ONE OBJECT, from the asking post, one
    hop: a held artifact offered through `available`, a Markdown object's
    source and provenance from `exact`; unresolved said in words; nothing
    else from the originating post;
  * `worker._turn_line` renders it with its key and exact address.

The server's object reader runs the UI's bundle in an embedded engine; these
tests replace only that reader (`objects._run`) with one keyed the same way
for the posts they write, so they need no UI build.
"""
from __future__ import annotations

import json
import time
import urllib.request

import pytest

from mentis import artifacts
from mentis.conversation import objectref, text, versions
from mentis.fluid import objects
from tests._loop import _written, a_conversation, post, say, world  # noqa: F401

CHART = "```chart version=1 name=xp\nlabel,xp\nCaptain,1650\nLean,1250\n```"
#: The real reader, kept before any test replaces it.
_REAL_RUN = objects._run


@pytest.fixture(autouse=True)
def engine(monkeypatch):
    """The object reader, for these posts: a text part holding a chart is
    one block object keyed `<root>:p<i>:chart:xp`; an attachment part is a
    media object keyed `<root>:part:<i>`, as the bundle keys media."""
    def run(post, bundle):
        out = []
        for i, p in enumerate(post["parts"]):
            t = p.get("text") or ""
            if p.get("type") == "text" and "```chart" in t:
                md = t[t.index("```chart"):]
                out.append({"key": f"{post['id']}:p{i}:chart:xp", "part": i,
                            "kind": "block", "type": "chart",
                            "title": "Adjusted XP", "name": "xp",
                            "identity": "declared", "stable": True,
                            "parent": None, "page": None, "line": 1,
                            "end": 5, "formats": ["json", "md", "csv"],
                            "md": md, "json": {"type": "chart"}})
            if p.get("type") in ("image", "file"):
                out.append({"key": f"{post['id']}:part:{i}", "part": i,
                            "kind": "media", "type": "attachment",
                            "title": p.get("alt") or p.get("ref"),
                            "name": None, "identity": "positional",
                            "stable": False, "parent": None, "page": None,
                            "line": None, "end": None, "ref": p.get("ref"),
                            "media_type": p.get("media_type"),
                            "formats": ["json"], "json": {}})
        return {"objects": out}, None, {"bundle": "test", "sha256": "0"}
    monkeypatch.setattr(objects, "_run", run)
    objects._cache.clear()
    objects._kinds.clear()
    yield
    objects._cache.clear()
    objects._kinds.clear()


def _chart_post(world, cid, words="the XP chart"):
    out = say(world, cid, f"{words}\n\n{CHART}", action="record-only")
    return out["turn"]


def _part(world, root, key=None, **over):
    """The part the composer builds for the chart in `root`."""
    key = key or f"{root}:p0:chart:xp"
    p = {"type": "object", "ref": root, "key": key,
         "exact": f"exact:{root}:0:{key}", "text": "Adjusted XP",
         "about": {"kind": "chart", "title": "Adjusted XP",
                   "home": None, "home_name": "Dungeons and Dragons",
                   "number": 4, "by": "@brian"}}
    p.update(over)
    return p


def _reply(world, cid, to, *parts, **kw):
    return say(world, cid, "", replies_to=to, action="record-only",
               parts=[text("see "), *parts], **kw)


# -- written ---------------------------------------------------------------------

def test_a_reply_carrying_an_object_reference_is_written_as_it_was_given(world):
    dnd = a_conversation(world, "Dungeons and Dragons")
    s8 = a_conversation(world, "Session 8 planning")
    chart = _chart_post(world, dnd)
    target = say(world, s8, "Which ambush do we run?",
                 action="record-only")["turn"]
    part = _part(world, chart)
    out = _reply(world, s8, target, part)
    assert "error" not in out, out
    got = world["cv"].corpus.read([out["turn"]])[0]
    assert got["body"]["parts"][1] == part
    # NO NEW ENTRY FOR THE OBJECT: the reply, its links and its act only.
    assert world["cv"].conversation_of(out["turn"]) == s8


def test_it_is_a_reference_part_and_never_an_attachment(world):
    assert "object" in versions._REFERENCE_PARTS
    dnd = a_conversation(world)
    chart = _chart_post(world, dnd)
    part = _part(world, chart)
    # Its characters are part of what the author typed, as other references'.
    assert versions.flow_text([text("see "), part]) == "see Adjusted XP"
    # An edit that keeps its characters keeps the reference where they are.
    assert versions.reparted([text("see "), part], "now see Adjusted XP!") \
        == [text("now see "), part, text("!")]
    # Not annotated as an artifact, and offers nothing as one.
    assert artifacts.annotate_part(world["cv"].corpus, part) == part
    assert artifacts.held_refs(world["cv"].corpus, [part]) == []


# -- refused, in words, writing nothing ------------------------------------------

def _refused(world, cid, to, part):
    before = _written(world)
    out = _reply(world, cid, to, part)
    assert "error" in out, out
    assert out["field"] == "parts" and out["part"] == 1
    assert _written(world) == before
    return out["error"]


@pytest.fixture()
def two(world):
    dnd = a_conversation(world, "Dungeons and Dragons")
    s8 = a_conversation(world, "Session 8 planning")
    chart = _chart_post(world, dnd)
    target = say(world, s8, "Which ambush?", action="record-only")["turn"]
    return {"dnd": dnd, "s8": s8, "chart": chart, "target": target}


def test_a_ref_the_record_does_not_hold_is_refused(world, two):
    why = _refused(world, two["s8"], two["target"],
                   _part(world, "ent-000000000000"))
    assert why == "the record holds no post ent-000000000000"


def test_a_ref_that_is_not_a_post_is_refused(world, two):
    why = _refused(world, two["s8"], two["target"],
                   _part(world, two["dnd"], key="k",
                         exact=f"exact:{two['dnd']}:0:k"))
    assert why.startswith(f"{two['dnd']} is not a post")


def test_a_deleted_post_is_refused(world, two):
    cv = world["cv"]
    versions.delete(cv, two["chart"], by=world["who"]["@brian"])
    why = _refused(world, two["s8"], two["target"], _part(world, two["chart"]))
    assert why.startswith("an object reference names a post that was deleted")


def test_a_later_version_named_as_the_post_is_refused(world, two):
    cv = world["cv"]
    v2 = versions.edit(cv, two["chart"], by=world["who"]["@brian"],
                       text=f"edited\n\n{CHART}")["version"]
    why = _refused(world, two["s8"], two["target"],
                   _part(world, v2, key=f"{v2}:p0:chart:xp"))
    assert why.startswith(f"{v2} is a later version of the post "
                          f"{two['chart']}")


def test_an_exact_that_is_not_an_address_is_refused(world, two):
    why = _refused(world, two["s8"], two["target"],
                   _part(world, two["chart"], exact="the chart"))
    assert why.startswith("not an object address")


def test_a_live_address_in_place_of_exact_is_refused(world, two):
    key = f"{two['chart']}:p0:chart:xp"
    why = _refused(world, two["s8"], two["target"],
                   _part(world, two["chart"],
                         exact=f"live:{two['chart']}:{key}"))
    assert "exact is an exact: address" in why


def test_an_exact_naming_another_key_is_refused(world, two):
    c = two["chart"]
    why = _refused(world, two["s8"], two["target"],
                   _part(world, c, exact=f"exact:{c}:0:{c}:p0:chart:other"))
    assert why == (f"the exact address names the object "
                   f"'{c}:p0:chart:other', not '{c}:p0:chart:xp'")


def test_a_key_the_version_does_not_hold_is_refused(world, two):
    c = two["chart"]
    key = f"{c}:p0:chart:gone"
    why = _refused(world, two["s8"], two["target"],
                   _part(world, c, key=key, exact=f"exact:{c}:0:{key}"))
    assert why == (f"that object does not resolve: version {c} of {c} has "
                   f"no object '{key}'")


def test_the_wrong_part_index_is_refused(world, two):
    c = two["chart"]
    key = f"{c}:p0:chart:xp"
    why = _refused(world, two["s8"], two["target"],
                   _part(world, c, exact=f"exact:{c}:3:{key}"))
    assert why.startswith("that object does not resolve: the object")
    assert "is in part 0" in why


def test_a_version_of_another_post_is_refused(world, two):
    other = _chart_post(world, two["dnd"], "another chart")
    key = f"{two['chart']}:p0:chart:xp"
    why = _refused(world, two["s8"], two["target"],
                   _part(world, two["chart"], key=key,
                         exact=f"exact:{other}:0:{key}"))
    # The key is the other post's to give, so it is not in that version.
    assert why.startswith("that object does not resolve")


def test_about_is_bounded(world, two):
    c = two["chart"]
    long = _part(world, c)
    long["about"] = {**long["about"], "title": "x" * 201}
    assert _refused(world, two["s8"], two["target"], long) == \
        "about.title is at most 200 characters"
    unknown = _part(world, c)
    unknown["about"] = {**unknown["about"], "content": "1650,1425"}
    assert _refused(world, two["s8"], two["target"], unknown).startswith(
        "an object reference's about holds only kind, title")
    missing = _part(world, c)
    del missing["about"]
    assert _refused(world, two["s8"], two["target"], missing).startswith(
        "an object reference describes what it names")
    wrong = _part(world, c)
    wrong["about"] = {**wrong["about"], "number": "four"}
    assert _refused(world, two["s8"], two["target"], wrong) == \
        "about.number is a number"


def test_a_part_carries_only_its_own_fields_and_says_what_it_shows(world, two):
    c = two["chart"]
    assert _refused(world, two["s8"], two["target"],
                    _part(world, c, content="a copy")).startswith(
        "an object reference carries only type, ref, key, exact, text, about")
    assert _refused(world, two["s8"], two["target"],
                    _part(world, c, text="")) == \
        "an object reference says what the author sees (its text)"
    assert _refused(world, two["s8"], two["target"],
                    _part(world, c, text="x" * 301)) == \
        "an object reference's text is at most 300 characters"


def test_without_the_engine_the_structure_is_still_checked(world, two,
                                                         monkeypatch):
    """No render engine (Intel macOS, by decision): the key cannot be read
    here, so a well-formed part naming a version of its post is written;
    one naming another post's version is still refused."""
    monkeypatch.setattr(objects, "_run",
                        lambda post, bundle: (None, "no engine here", None))
    objects._cache.clear()
    c = two["chart"]
    assert "error" not in _reply(world, two["s8"], two["target"],
                                 _part(world, c))
    other = _chart_post(world, two["dnd"], "another")
    key = f"{c}:p0:chart:xp"
    why = _refused(world, two["s8"], two["target"],
                   _part(world, c, exact=f"exact:{other}:0:{key}"))
    assert why == f"{other} is a version of the post {other}, not of {c}"


def test_with_the_real_reader_a_listed_object_is_accepted_as_listed(
        world, two, monkeypatch):
    """The UI's own bundle (built by `vite build`) keys the chart; the part
    built from its listing is accepted, and a key it did not give is not."""
    if not objects.BUNDLE.exists():
        pytest.skip("the UI is not built here (no dist/render-check.js)")
    try:
        import quickjs  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("no render engine on this platform")
    monkeypatch.setattr(objects, "_run", _REAL_RUN)
    objects._cache.clear()
    listing = objects.post_objects(world["cv"].corpus, two["chart"])
    assert listing["extracted"] is True, listing
    [o] = [x for x in listing["objects"] if x["kind"] == "block"]
    part = {"type": "object", "ref": two["chart"], "key": o["key"],
            "exact": o["address"]["exact"], "text": o["title"] or "chart",
            "about": {"kind": o["type"], "title": o["title"]}}
    assert "error" not in _reply(world, two["s8"], two["target"], part)
    wrong = {**part, "key": o["key"] + "x",
             "exact": o["address"]["exact"] + "x"}
    assert _refused(world, two["s8"], two["target"], wrong).startswith(
        "that object does not resolve")


# -- resolved when read ----------------------------------------------------------

def _resolve(world, post_id):
    from mentis import fluid
    st = world["state"]
    with st.cv.reading():
        return fluid.route(st, "/fluid/api/object-refs",
                           {"post": [post_id]})


def test_the_resolve_read_answers_with_the_live_object(world, two):
    out = _reply(world, two["s8"], two["target"], _part(world, two["chart"]))
    got = _resolve(world, out["turn"])
    assert got["post"] == out["turn"]
    [r] = got["references"]
    assert r["part"] == 1 and r["resolves"] is True
    assert r["object"]["key"] == f"{two['chart']}:p0:chart:xp"
    assert r["object"]["address"]["live"] == r["live"]
    assert r["home"] == two["dnd"] and r["home_name"] == "Dungeons and Dragons"
    assert r["exact_resolves"] is True


def test_a_reference_whose_object_was_edited_out_says_so(world, two):
    out = _reply(world, two["s8"], two["target"], _part(world, two["chart"]))
    versions.edit(world["cv"], two["chart"], by=world["who"]["@brian"],
                  text="no chart any more")
    [r] = _resolve(world, out["turn"])["references"]
    # NEVER A SUBSTITUTE: the current version has no such key, and says so;
    # what the author saw is still there at its exact address.
    assert r["resolves"] is False and "object" not in r
    assert r["why"].startswith("no longer resolves: the current version")
    assert r["exact_resolves"] is True
    assert r["about"]["title"] == "Adjusted XP"


def test_a_reference_whose_post_was_deleted_says_so(world, two):
    out = _reply(world, two["s8"], two["target"], _part(world, two["chart"]))
    versions.delete(world["cv"], two["chart"], by=world["who"]["@brian"])
    [r] = _resolve(world, out["turn"])["references"]
    assert r["resolves"] is False and r.get("deleted") is True
    assert r["why"] == "the post was deleted; its objects are not served"
    assert r["exact_resolves"] is False


def test_one_reference_is_resolved_before_it_is_sent(world, two):
    from mentis import fluid
    st = world["state"]
    key = f"{two['chart']}:p0:chart:xp"
    with st.cv.reading():
        r = fluid.route(st, "/fluid/api/object-refs",
                        {"ref": [two["chart"]], "key": [key]})
    assert r["resolves"] is True and r["live"] == f"live:{two['chart']}:{key}"


# -- an addressed agent is given that one object ---------------------------------

def _hold(world, cid, data, name):
    cv = world["cv"]
    owner = world["who"]["@brian"]
    held = artifacts.hold(cv.corpus, cv, data, act="artifact-submitted",
                          actor=owner, source=f"submission:{owner}",
                          door="human-ingress", conversation=cid)
    return {**artifacts.part(held["admission"], corpus=cv.corpus),
            "alt": name}


def _ask(world, cid, to, *parts):
    """The owner's reply addressed to Ada, asking for work, carrying parts."""
    out = say(world, cid, "", replies_to=to, action="ask-participant",
              parts=[text("@Ada what does this show? "), *parts],
              addressed_to=[world["who"]["@Ada"]],
              dispatch=[{"participant": world["who"]["@Ada"],
                         "work": "read the chart"}])
    assert "error" not in out, out
    return out["expectations"][0]


def test_a_markdown_object_is_given_by_its_source_and_provenance(world, two):
    cv = world["cv"]
    part = _part(world, two["chart"])
    exp = _ask(world, two["s8"], two["target"], part)
    [c] = objectref.for_request(cv.corpus, cv, exp)
    assert c["resolves"] is True and c["exact"] == part["exact"]
    assert c["live"] == f"live:{two['chart']}:{part['key']}"
    assert c["source"].startswith("```chart version=1 name=xp")
    assert c["home_name"] == "Dungeons and Dragons" and c["by"]
    assert "artifact" not in c
    said = objectref.context_lines([c])
    assert "Adjusted XP (chart) from Dungeons and Dragons #" in said
    assert part["exact"] in said and c["live"] in said
    assert "Captain,1650" in said
    assert "nothing else from that post is given" in said
    # A chart holds no artifact: nothing is offered for it.
    assert artifacts.object_referenced_by_request(cv.corpus, cv, exp) == []


def test_a_held_object_is_offered_alone_and_nothing_else_of_its_post(world,
                                                                  two):
    cv = world["cv"]
    plan = _hold(world, two["dnd"], b"the map of the ford", "ford.png")
    other = _hold(world, two["dnd"], b"the encounter table", "table.csv")
    src = say(world, two["dnd"], "", action="record-only",
              parts=[text("two files"), plan, other])["turn"]
    key = f"{src}:part:1"
    part = _part(world, src, key=key, exact=f"exact:{src}:1:{key}",
                 text="ford.png")
    exp = _ask(world, two["s8"], two["target"], part)
    offered = artifacts.available(cv.corpus, cv, {"expectation": exp})
    mine = [w for w in offered if w["because"] == "referenced-object"]
    assert mine == [{"ref": plan["ref"], "because": "referenced-object",
                     "object": part["exact"], "referenced_turn": src,
                     "referenced_by": cv.expectation_state(exp)["turn"]}]
    assert other["ref"] not in [w["ref"] for w in offered]
    # And reachable through the one door that decides it, the other not.
    grant = {"expectation": exp, "conversation": two["s8"]}
    assert artifacts.reachable(cv.corpus, cv, grant, plan["ref"])[0]
    said = objectref.context_lines(
        objectref.for_request(cv.corpus, cv, exp), [plan["ref"]])
    assert f"It is the held artifact {plan['ref']}, offered below" in said


def test_a_turn_reference_still_hands_on_what_its_post_holds(world, two):
    """Whole-post behaviour is unchanged beside it."""
    cv = world["cv"]
    plan = _hold(world, two["dnd"], b"the map", "ford.png")
    src = say(world, two["dnd"], "", action="record-only",
              parts=[text("a file"), plan])["turn"]
    exp = _ask(world, two["s8"], two["target"],
               {"type": "turn", "ref": src, "text": "#1"})
    assert [w["because"] for w in artifacts.available(
        cv.corpus, cv, {"expectation": exp})] == ["referenced"]
    assert objectref.for_request(cv.corpus, cv, exp) == []


def test_an_object_that_no_longer_resolves_is_said_and_nothing_given(world,
                                                                   two):
    cv = world["cv"]
    exp = _ask(world, two["s8"], two["target"], _part(world, two["chart"]))
    versions.delete(cv, two["chart"], by=world["who"]["@brian"])
    [c] = objectref.for_request(cv.corpus, cv, exp)
    assert c["resolves"] is False and "source" not in c
    said = objectref.context_lines([c])
    assert "NOT AVAILABLE: the post was deleted" in said
    assert "Nothing was substituted for it." in said
    assert artifacts.object_referenced_by_request(cv.corpus, cv, exp) == []


def test_one_hop_only(world, two):
    """The referenced post's own object references are not followed."""
    cv = world["cv"]
    deeper = _chart_post(world, two["dnd"], "the original chart")
    between = say(world, two["dnd"], "", action="record-only",
                  parts=[text(f"see\n\n{CHART}"),
                         _part(world, deeper)])["turn"]
    exp = _ask(world, two["s8"], two["target"], _part(world, between))
    got = objectref.for_request(cv.corpus, cv, exp)
    assert [c["ref"] for c in got] == [between]


def test_the_run_is_told_in_its_work(world, two, monkeypatch):
    """Through the real dispatch: the context reaches the prompt."""
    import mentis.web as web
    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    from tests._loop import script_every_backend
    prompts = []

    def perform(spec):
        prompts.append(spec.prompt)
        now = time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn", text="done",
                         started_at=now, finished_at=now)

    script_every_backend(world["state"].agents, perform)
    monkeypatch.setattr(web, "dispatch_soon",
                        lambda st, **kw: D.dispatch(world["state"], **kw))
    part = _part(world, two["chart"])
    _ask(world, two["s8"], two["target"], part)
    [prompt] = prompts
    assert "OBJECTS THIS REQUEST REFERENCES" in prompt
    assert part["exact"] in prompt and "Captain,1650" in prompt


# -- the worker's side -------------------------------------------------------------

def test_turn_line_renders_its_key_and_exact_address(world, two):
    from mentis.worker import Surface
    part = _part(world, two["chart"])
    s = Surface(world["root"], corpus=world["state"].corpus)
    line = s._turn_line({"body": {"parts": [text("see "), part]}})
    assert line == (f"see Adjusted XP[object:{two['chart']}#{part['key']} "
                    f"{part['exact']}]")


def test_a_worker_reply_is_held_to_the_same_rule(world, two):
    from mentis.worker import CAPABILITY_HEADER
    cv = world["cv"]
    coach = cv.create_participant("@Coach")
    out = say(world, two["s8"], "@Coach look", action="ask-participant",
              dispatch=[{"participant": coach, "work": "look",
                         "coordinate": True}])
    parent = out["expectations"][0]
    grants = world["state"].agents.authority
    iid = f"coord-objref-{parent[-6:]}"
    grants.authorise_for(iid, dict(scope="organising",
                                   operations=cv.authority_of(parent)[
                                       "operations"],
                                   expectation=parent, conversation=two["s8"],
                                   participant=coach, runtime="claude"))
    token = grants._grant(iid, world["state"].path)

    def respond(parts):
        req = urllib.request.Request(
            world["base"] + "/api/worker", method="POST",
            data=json.dumps({"op": "respond",
                             "args": {"parts": parts}}).encode(),
            headers={"Content-Type": "application/json",
                     CAPABILITY_HEADER: token})
        try:
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    before = _written(world)
    bad = respond([text("see "), _part(world, two["chart"], key="nope",
                                       exact=f"exact:{two['chart']}:0:nope")])
    assert "this reply cannot carry that object reference (part 1)" in \
        json.dumps(bad)
    assert _written(world) == before
    good = respond([text("see "), _part(world, two["chart"])])
    assert good.get("ok") is True, good
    assert cv.corpus.read([good["turn"]])[0]["body"]["parts"][1]["type"] \
        == "object"
