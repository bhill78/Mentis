"""Source writes cross the real worker door, with fixture Brains and no network.

The existing feed and transport suites own acquisition/security correctness.
These checks own grant admission, attribution, confirmed plans, keyed replay,
history preservation, and refusing unsupported/malformed calls before a fetch.
"""
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from mentis import api, worker
from mentis.sources import fetch, reading
from mentis.web import _Handler, _State, fixture
from tests.test_sources_feeds import FEED, RSS, _Stub


@pytest.fixture
def world(tmp_path, monkeypatch):
    root = tmp_path / "brain"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    actor = st.cv.resolve_participant("@Ada")
    here = st.cv.all_conversations()[0]["id"]
    stub = _Stub({FEED: RSS})
    monkeypatch.setattr(fetch, "get", stub)
    handler = type("SourceWriter", (_Handler,), {"state": st})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    count = 0

    def grant(scope="organising", operations=("write_source",), participant=actor):
        nonlocal count
        count += 1
        instance = f"source-writer-{count}"
        st.agents.authority.authorise_for(instance, {
            "scope": scope, "operations": operations, "participant": participant,
            "runtime": "codex", "conversation": here,
        })
        return st.agents.authority._grant(instance, st.path)

    token = grant()

    def call(args, *, capability=token, route="/api/worker"):
        body = {"op": "write_source", "args": args}
        headers = {"Content-Type": "application/json", "X-Mentis-Client": "1"}
        if capability is not None:
            headers[worker.CAPABILITY_HEADER] = capability
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}{route}",
            data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)

    try:
        yield st, actor, stub, grant, call
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def preview(call, **extra):
    status, result = call({"action": "preview", "connector": "rss-atom",
                           "name": "Astronomy", "include": ["*"], "exclude": [],
                           "options": {"feeds": [FEED]}, **extra})
    assert status == 200, result
    return result


def acquire(call, plan, **extra):
    return call({"action": "acquire", "connector": "rss-atom",
                 "draft": plan["draft"], "plan": plan["plan"], **extra})


@pytest.mark.parametrize("scope,operations", [
    ("worker", None), ("worker", ["write_source"]),
    ("no-such-scope", ["write_source"]), ("transient-read", ["write_source"]),
    ("organising", []), ("organising", ["coordinate"]),
    ("magnet:mag-265878e92e5c987c", ["write_source"]),
    ("magnet-synthesis:mag-265878e92e5c987c", ["write_source"]),
])
def test_ungranted_and_confined_work_cannot_write(world, scope, operations):
    st, _, stub, grant, call = world
    before = len(list(st.corpus.operational()))
    status, result = call({"action": "preview"}, capability=grant(scope, operations))
    assert status == 403 and result["refusal"]["boundary"] == "scope", result
    assert not stub.asked
    assert len(list(st.corpus.operational())) == before


def test_operation_is_offered_only_with_existing_authority():
    assert "write_source" in worker.AUTHORITY
    assert "write_source" not in worker.READ_ONLY
    assert "write_source" in worker.permitted("intake", ["write_source"])
    assert "write_source" in worker.permitted("organising", None)
    offered = {t["name"] for t in worker.ALL_TOOLS
               if t["name"] in worker.permitted("organising", ["write_source"])}
    assert "write_source" in offered


def test_no_grant_missing_actor_and_owner_route_are_refused(world):
    st, _, stub, grant, call = world
    assert call({"action": "preview"}, capability=None)[0] == 403
    assert call({"action": "preview"}, capability=grant(participant=None))[0] == 403
    assert call({"action": "preview"}, route="/api/sources/declare")[0] == 403
    assert not stub.asked
    assert api.sources(st.corpus).declarations() == []


def test_preview_confirm_acquisition_attribution_and_keyed_replay(world):
    st, actor, stub, _, call = world
    plan = preview(call, op_key="preview-once")
    replayed_plan = preview(call, op_key="preview-once")
    assert replayed_plan["replayed"] and replayed_plan["draft"] == plan["draft"]
    assert len(stub.asked) == 1
    assert api.sources(st.corpus).declarations() == []
    assert plan["counts"]["new"] == 2
    status, made = acquire(call, plan, op_key="acquire-once")
    assert status == 200, made
    assert len(made["admitted"]) == 2
    declaration = st.cv._act(made["declaration"])
    assert declaration["actor"] == actor
    assert declaration["detail"]["written_by"].startswith("codex/source-w")
    count = len(list(st.corpus.operational()))
    fetches = len(stub.asked)
    status, repeated = acquire(call, plan, op_key="acquire-once")
    assert status == 200 and repeated["replayed"] is True
    assert repeated["admitted"] == made["admitted"]
    assert len(list(st.corpus.operational())) == count
    assert len(stub.asked) == fetches
    status, different = acquire(call, {**plan, "plan": "changed"}, op_key="acquire-once")
    assert status == 403, different
    assert len(stub.asked) == fetches


def test_changed_plan_refuses_without_declaration_or_key(world):
    st, _, _, _, call = world
    plan = preview(call)
    before = len(list(st.corpus.operational()))
    status, result = acquire(call, {**plan, "plan": "wrong"}, op_key="bad-plan")
    assert status == 403 and "not what would be recorded" in result["error"], result
    assert api.sources(st.corpus).declarations() == []
    assert len(list(st.corpus.operational())) == before


def test_refresh_and_revision_preserve_old_admission(world):
    st, actor, stub, _, call = world
    status, made = acquire(call, preview(call))
    assert status == 200, made
    col = made["collection"]
    old = made["admitted"][0]
    old_path = next(row["path"] for row in reading.objects(st.corpus, col)["objects"]
                    if row["ref"] == old)
    old_text = reading.read(st.corpus, ref=old)
    stub.pages[FEED] = RSS.replace("The &lt;b&gt;first&lt;/b&gt; blossom.", "A newly measured discovery.")
    status, planned = call({"action": "plan", "collection": col})
    assert status == 200, planned
    status, swept = call({"action": "sweep", "collection": col,
                          "plan": planned["plan"], "op_key": "refresh-once"})
    assert status == 200 and swept["admitted"], swept
    assert reading.read(st.corpus, ref=old) == old_text
    status, revised = call({"action": "revise_scope", "collection": col,
                            "include": ["*"], "exclude": [],
                            "options": {"since": "2026-11-15"}, "because": "Astronomy window"})
    assert status == 200, revised
    assert st.cv._act(revised["revision"])["actor"] == actor
    assert reading.read(st.corpus, ref=old) == old_text
    history = reading.history(st.corpus, col, old_path)
    assert old in {row["ref"] for row in history["observations"]}


@pytest.mark.parametrize("args", [
    {"action": "bind", "root": "C:/private"},
    {"action": "preview", "connector": "filesystem", "name": "Private"},
    {"action": "preview", "connector": "rss-atom", "name": "x", "actor": "human"},
    {"action": "preview", "connector": "rss-atom", "name": "x", "written_by": "owner"},
    {"action": "preview", "connector": "rss-atom", "name": "x", "include": "*"},
    {"action": "preview", "connector": "rss-atom", "name": "x", "options": []},
    {"action": "preview", "connector": "rss-atom", "name": "x",
     "options": {"feeds": ["http://127.0.0.1/feed"]}},
    {"action": "plan", "collection": {}},
    {"action": "plan", "collection": "col-none", "scope": {"include": "*"}},
    {"action": "sweep", "collection": "col-none", "plan": "x", "acknowledge_binding_change": True},
    {"action": []},
])
def test_malformed_and_extra_authority_are_refused_before_fetch(world, args):
    st, _, stub, _, call = world
    before = len(list(st.corpus.operational()))
    status, result = call({**args, "op_key": "refused"})
    assert status == 403, result
    assert not stub.asked
    assert len(list(st.corpus.operational())) == before


def test_existing_local_collection_cannot_be_swept(world):
    st, actor, stub, _, call = world
    made = api.sources(st.corpus).declare("Local", declarer=actor)
    status, result = call({"action": "plan", "collection": made["collection"]})
    assert status == 403 and "public network" in result["error"], result
    assert not stub.asked


def test_upstream_refusal_is_retained_without_fallback_or_cap_change(world):
    st, _, stub, _, call = world
    stub.pages[FEED] = fetch.Unreachable("publisher answered HTTP 403", status=403)
    status, planned = call({"action": "preview", "connector": "rss-atom",
                            "name": "Astronomy", "options": {"feeds": [FEED]}})
    assert status == 403, planned
    assert len(stub.asked) == 1
    assert "403" in json.dumps(planned)
    assert api.sources(st.corpus).declarations() == []


def test_session_needs_a_request_it_carries(world):
    _, _, stub, grant, call = world
    status, result = call({"action": "preview"}, capability=grant("manual-session", ["write_source"]))
    assert status == 403 and result["refusal"]["boundary"] == "coordination", result
    assert not stub.asked


def test_revoked_operation_cannot_replay_a_kept_answer(world):
    st, _, stub, _, call = world
    preview(call, op_key="once")
    # Same live grant, narrowed by the existing authority implementation.
    authority = dict(st.agents.authority._authority["source-writer-1"])
    st.agents.authority.authorise_for("source-writer-1", {**authority, "operations": []})
    status, result = call({"action": "preview", "op_key": "once"})
    assert status == 403 and result["refusal"]["boundary"] == "scope", result
    assert len(stub.asked) == 1


def test_proposed_scope_must_match_the_confirmed_plan(world):
    st, _, _, _, call = world
    status, made = acquire(call, preview(call))
    assert status == 200, made
    col = made["collection"]
    scope = {"include": ["*"], "exclude": [], "options": {"since": "2026-11-15"}}
    status, planned = call({"action": "plan", "collection": col, "scope": scope})
    assert status == 200, planned
    prior = api.sources(st.corpus).effective_scope(col)
    status, bad = call({"action": "sweep", "collection": col, "plan": planned["plan"]})
    assert status == 403, bad
    assert api.sources(st.corpus).effective_scope(col) == prior
    status, good = call({"action": "sweep", "collection": col,
                         "plan": planned["plan"], "scope": scope})
    assert status == 200, good
    assert api.sources(st.corpus).effective_scope(col)["options"]["since"] == "2026-11-15"


def test_prepared_astronomy_options_are_accepted_without_fetch(world):
    st, _, stub, _, _ = world
    config = json.loads((Path(__file__).resolve().parents[1] /
                         "docs/astronomy-test-sources.json").read_text(encoding="utf-8"))
    src = api.sources(st.corpus)
    assert config["server"] == "http://127.0.0.1:8780"
    for item in config["previews"]:
        args = item["args"]
        src.check_options(args["connector"], args["options"])
        assert src.checked_options(args["connector"], args["options"])
    assert not stub.asked
