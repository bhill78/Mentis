"""The write-side boundary: evidence is ordinary, adoption belongs to the owner."""
import pytest

from mentis.conversation import ladder_writes as writes
from mentis.web import _State, _routes, _surface, fixture
from mentis.worker import _operate, NotPermitted, permitted, TRANSIENT_SCOPE


@pytest.fixture
def world(tmp_path):
    root = str(tmp_path / "corpus")
    fixture.build(root)
    st = _State(root, str(tmp_path))
    cv = st.cv
    owner = cv.resolve_participant("@brian")
    agent = cv.resolve_participant("@Ada")
    conv = cv.open_conversation("Ladder write checks")
    turn = cv.say(conv, owner, [{"type": "text", "text": "work"}])
    exp = cv.expect(turn, of=agent, kind="result", by=owner)
    grant = {"participant": agent, "runtime": "codex", "instance": "inst-ladder",
             "conversation": conv, "expectation": exp, "scope": "organising"}
    yield st, owner, agent, conv, grant
    st.corpus.close()


def run(w, name, **args):
    return _operate(_surface(w[0]), name, args, w[4])


def record(w, kind="lesson", **kw):
    # A basis by default, since lesson, finding, solution and hypothesis
    # declare requires_basis; the Conversation is a held entry to cite.
    kw.setdefault("basis", [w[3]])
    return run(w, "record_material", kind=kind, body=kw.pop("body", {"text": "a lesson", "limits": "local"}), **kw)["entry"]


def post(w, eid, act, **kw):
    return _routes(w[0], f"/api/entries/{eid}/{act}", {},
                   {"attributed_to": w[1], "because": "owner reviewed", **kw}, "POST")


def test_record_asks_nobody_and_has_execution_provenance(world):
    st, _, agent, conv, grant = world
    eid = record(world)
    assert not st.corpus.stands(eid)["stands"]
    assert not st.cv.asks_about(eid)
    assert not st.corpus.links(relation="proposes", to=eid)
    act = next(a for a in st.cv.history() if a["act"] == "material-recorded" and eid in a["about"])
    assert (act["actor"], act["runtime"], act["execution"], act["conversation"]) == (agent, "codex", "inst-ladder", conv)
    assert act["turn"] == st.cv.expectation_state(grant["expectation"])["turn"]
    assert st.corpus.links(relation="produced", to=eid)[0]["link"]["from"] == act["id"]


@pytest.mark.parametrize("kind", ["finding", "solution", "hypothesis", "lesson"])
def test_requires_basis_refuses_unbased_concluded_material(world, kind):
    before = len(world[0].corpus.entries_of_kind(kind))
    with pytest.raises(NotPermitted, match="requires_basis"):
        record(world, kind, body={"text": "concluded"}, basis=[])
    assert len(world[0].corpus.entries_of_kind(kind)) == before


def test_requires_basis_is_the_only_property_read(world):
    """`capturable` stays descriptive; absent `requires_basis` is not required."""
    corpus = world[0].corpus
    assert record(world, "note", body={"text": "kept"}, basis=[])
    was = dict(corpus.current_definition("lesson")["body"])
    was.pop("kind")
    fields = was.pop("fields")
    was["capturable"] = True
    corpus.define_kind("lesson", fields=fields, properties=was, attributed_to=world[1])
    with pytest.raises(NotPermitted, match="requires_basis"):
        record(world, basis=[])
    was.pop("requires_basis")
    was["capturable"] = False
    corpus.define_kind("lesson", fields=fields, properties=was,
                       removing=["requires_basis"], attributed_to=world[1])
    assert record(world, basis=[])


def test_basis_relations(world):
    turn = world[0].cv.expectation_state(world[4]["expectation"])["turn"]
    first = record(world, basis=[turn])
    second = record(world, basis=[first])
    assert world[0].corpus.links(relation="extracted-from", frm=first)[0]["link"]["to"] == turn
    assert world[0].corpus.links(relation="derived-from", frm=second)[0]["link"]["to"] == first
    refused = post(world, first, "derive-from", **{"from": [second]})
    assert "cycle" in refused["error"]


def test_bad_basis_rolls_back(world):
    before = len(world[0].corpus.entries_of_kind("lesson"))
    with pytest.raises(NotPermitted, match="holds no such"):
        record(world, basis=["ent-000000000000"])
    assert len(world[0].corpus.entries_of_kind("lesson")) == before


@pytest.mark.parametrize("missing", ["outcome_of", "in_context", "attempted", "bad_context"])
def test_outcome_requires_context_and_attempt(world, missing):
    target = record(world)
    args = {"outcome_of": target, "in_context": world[3],
            "body": {"text": "tried it", "result": "failed", "attempted": True}}
    if missing in ("outcome_of", "in_context"):
        args.pop(missing)
    elif missing == "attempted":
        args["body"].pop("attempted")
    else:
        args["in_context"] = target
    with pytest.raises(NotPermitted):
        record(world, "outcome", **args)
    assert not world[0].corpus.entries_of_kind("outcome") or all(
        e["body"].get("text") != "tried it" for e in world[0].corpus.entries_of_kind("outcome"))


def test_contextual_outcome_links(world):
    target = record(world)
    eid = record(world, "outcome", body={"text": "tried", "result": "failed", "attempted": True},
                 outcome_of=target, in_context=world[3])
    assert world[0].corpus.links(relation="outcome-of", frm=eid)[0]["link"]["to"] == target


def test_only_standing_apt_kinds_are_adoptable(world):
    eid = record(world, "finding", body={"text": "found"})
    with pytest.raises(NotPermitted, match="not adoptable"):
        run(world, "request_adoption", entry=eid, because="future work")
    assert "not adoptable" in post(world, eid, "adopt")["error"]
    assert run(world, "request_adoption", entry=record(world), because="future work")["request"]


def test_request_once_and_decline_keeps_evidence(world):
    eid = record(world)
    first = run(world, "request_adoption", entry=eid, because="future work")
    second = run(world, "request_adoption", entry=eid, because="again")
    assert first["request"] == second["request"]
    assert len(world[0].cv.asks_about(eid)) == 1
    result = post(world, eid, "decline")
    assert "error" not in result, result
    assert not world[0].cv.asks_about(eid)
    assert not world[0].corpus.stands(eid)["stands"]
    assert not world[0].corpus.links(relation="disputes", to=eid)
    assert world[0].corpus.read([eid])
    assert world[0].corpus.links(relation="declines", to=eid)[0]["body"]["request"] == first["request"]


def test_adopt_closes_ask_and_owner_only(world):
    eid = record(world)
    run(world, "request_adoption", entry=eid, because="future work")
    rejected = post(world, eid, "adopt", attributed_to=world[2])
    assert "owner" in rejected["error"]
    adopted = post(world, eid, "adopt")
    assert "error" not in adopted, adopted
    assert world[0].corpus.stands(eid)["stands"]
    assert not world[0].cv.asks_about(eid)
    assert "already stands" in post(world, eid, "adopt")["error"]


def test_adoption_rollback_includes_ask_closure(world, monkeypatch):
    eid = record(world)
    run(world, "request_adoption", entry=eid, because="future work")
    def fail(*a, **kw):
        raise ValueError("ask closure failed")
    monkeypatch.setattr("mentis.web._answered_asks", fail)
    assert "failed" in post(world, eid, "adopt")["error"]
    assert not world[0].corpus.stands(eid)["stands"]
    assert world[0].cv.asks_about(eid)


def test_revision_adoption_inherits_scope(world):
    old = record(world, "rule", body={"text": "old"})
    assert "error" not in post(world, old, "adopt", scope={"where": world[3]})
    world[4]["delivered"] = [old]
    candidate = run(world, "request_adoption", of=old, body={"text": "new"}, because="work showed a gap")["entry"]
    assert world[0].corpus.stands(old)["stands"]
    assert "error" not in post(world, candidate, "adopt")
    assert not world[0].corpus.stands(old)["stands"]
    assert world[0].corpus.stands(candidate)["stands"]
    assert world[0].corpus.links(relation="scoped-to", frm=candidate)[0]["link"]["to"] == world[3]


def test_adoption_checks_current_falsifier(world):
    eid = record(world, "hypothesis", body={"text": "maybe"})
    assert "error" in post(world, eid, "adopt")
    assert "error" not in post(world, eid, "adopt", falsifier="counterexample")


def test_challenge_revokes_nothing(world):
    eid = record(world)
    evidence = record(world)
    assert "error" not in post(world, eid, "adopt")
    bare = run(world, "challenge", target=eid, because="disagrees")
    assert bare["disputed"] and not world[0].corpus.links(relation="supports", frm=bare["objection"])
    with pytest.raises(NotPermitted, match="say why"):
        run(world, "challenge", target=eid, because=" ")
    result = run(world, "challenge", target=eid, because="counterexample", evidence=[evidence])
    assert world[0].corpus.stands(eid)["stands"]
    # The evidence is the objection's, on its `disputes` link: no `supports`.
    assert not world[0].corpus.links(relation="supports", frm=result["objection"])
    assert world[0].corpus.read([result["disputed"]])[0]["body"]["evidence"] == [evidence]


def _rule_with_objection_evidence(world, legacy):
    from mentis.conversation import ladder as read
    corpus = world[0].corpus
    rule = record(world, "rule", body={"text": "a standing rule"})
    assert "error" not in post(world, rule, "adopt")
    target = record(world)
    if legacy:
        # As challenges wrote it before: objection --supports--> evidence.
        note = corpus.create_and_establish(kind="note", body={"text": "cites the rule"},
                                           attributed_to=world[2])
        dispute = writes.edge(corpus, note, target, "disputes", by=world[2],
                              body={"reason": "cites the rule"})
        writes.edge(corpus, note, rule, "supports", by=world[2])
    else:
        dispute = run(world, "challenge", target=target, because="cites the rule",
                      evidence=[rule])["disputed"]
    return read, corpus, rule, target, dispute


@pytest.mark.parametrize("legacy", [False, True])
def test_objection_evidence_is_never_support(world, legacy):
    """Found by the 2026-10-28 audit: an objection citing a standing rule
    showed on that rule as "why this holds: 1 note"."""
    read, corpus, rule, target, dispute = _rule_with_objection_evidence(world, legacy)
    holds = read.why_this_holds(corpus, rule)
    assert holds["supports"] == [] and "note" not in (holds["why"] or "")
    assert read.cited_by(corpus, rule) == []
    # And the objection stays readable with its evidence.
    row = next(c for c in read.challenges_of(corpus, target) if c["link"] == dispute)
    assert row["evidence"] == [rule] and row["resolution"] == "open"
    # Real support still counts.
    finding = record(world, "finding", body={"text": "it held"})
    writes.edge(corpus, finding, rule, "supports", by=world[2], body={"reason": "observed"})
    assert read.why_this_holds(corpus, rule)["supports"] == [finding]


def test_owner_dispute_writes_evidence_on_the_dispute(world):
    from mentis.conversation import ladder as read
    corpus = world[0].corpus
    rule = record(world, "rule", body={"text": "cited"})
    target = record(world)
    got = post(world, target, "dispute", evidence=[rule])
    assert "error" not in got, got
    assert not corpus.links(relation="supports", frm=got["objection"])
    assert read.challenges_of(corpus, target)[0]["evidence"] == [rule]


def test_set_aside_is_the_owners_act_for_any_target(world):
    eid = record(world)
    challenged = run(world, "challenge", target=eid, because="counterexample", evidence=[world[3]])
    refused = post(world, eid, "set-aside", attributed_to=world[2], dispute=challenged["disputed"])
    assert "only the owner" in refused["error"]
    assert "error" not in post(world, eid, "set-aside", dispute=challenged["disputed"])
    post(world, eid, "adopt")
    challenged = run(world, "challenge", target=eid, because="more", evidence=[world[3]])
    assert "error" in post(world, eid, "set-aside", attributed_to=world[2], dispute=challenged["disputed"])


def test_withdraw_own_challenge_only(world):
    from mentis.conversation.ladder import challenges_of
    corpus = world[0].corpus
    eid = record(world)
    mine = run(world, "challenge", target=eid, because="mine")
    owners = post(world, eid, "dispute", because="the owner's")
    with pytest.raises(NotPermitted, match="only the participant who made"):
        run(world, "withdraw_challenge", dispute=owners["disputed"], because="not mine")
    with pytest.raises(NotPermitted, match="say why"):
        run(world, "withdraw_challenge", dispute=mine["disputed"], because="")
    got = run(world, "withdraw_challenge", dispute=mine["disputed"], because="I was wrong")
    assert corpus.links(relation="withdraws", to=eid)[0]["body"]["dispute"] == mine["disputed"]
    assert any(a["act"] == "challenge-withdrawn" and eid in a["about"] for a in world[0].cv.history())
    rows = {c["link"]: c for c in challenges_of(corpus, eid)}
    assert rows[mine["disputed"]]["resolution"] == "withdrawn"
    assert rows[owners["disputed"]]["resolution"] == "open"
    # Both the challenge and its withdrawal stay in the record.
    assert len(corpus.read([mine["disputed"], got["withdrawn"]])) == 2
    # The owner withdraws the owner's own challenge through the entry act.
    assert "error" not in post(world, eid, "withdraw-challenge", dispute=owners["disputed"])
    refused = post(world, eid, "withdraw-challenge", dispute=mine["disputed"], attributed_to=world[2])
    assert "already withdrawn" in refused["error"]


def test_propose_aliases_are_kept_and_never_lose_the_write(world):
    assert "propose_material" in permitted("organising")
    assert "propose_revision" in permitted("worker")
    result = run(world, "propose_material", kind="lesson", body={"text": "alias"}, basis=[world[3]])
    assert result["request"] and not world[0].corpus.stands(result["entry"])["stands"]


def test_ladder_tools_are_granted_wherever_propose_revision_is():
    from mentis.worker import SESSION_SCOPE
    for name in ("record_material", "request_adoption", "challenge", "withdraw_challenge"):
        assert name in permitted("worker")
        assert name in permitted("organising", [])
        assert name in permitted("organising")
        assert name in permitted(SESSION_SCOPE)
        assert name not in permitted(TRANSIENT_SCOPE)


def test_vocabulary_dry_run_idempotence_and_port_guard(world):
    from tools.ladder_vocabulary import plan, apply, server_refusal
    corpus = world[0].corpus
    before = corpus.current_definition("hypothesis")
    props = dict(before["body"])
    props.pop("kind")
    props["fields"] = ["text"]
    fields = props.pop("fields")
    corpus.define_kind("hypothesis", fields=fields, properties=props, attributed_to=world[1])
    changes = plan(corpus)
    assert any(c["name"] == "hypothesis" for c in changes)
    assert corpus.current_definition("hypothesis")["body"]["fields"] == ["text"]
    apply(corpus, changes, by=world[1])
    assert plan(corpus) == []
    assert server_refusal("http://127.0.0.1:8760")
    assert server_refusal("http://localhost:8760")
    assert server_refusal("http://localhost:8760", day_to_day=True) is None
    assert server_refusal("http://127.0.0.1:18761") is None


def test_migration_is_explicit_and_idempotent(world):
    from tools.ladder_vocabulary import migrate
    eid = record(world)
    rehearsal = migrate(world[0].cv, by=world[1], conversation=world[3])
    assert eid in rehearsal["entries"]
    assert not world[0].cv.asks_about(eid)
    done = migrate(world[0].cv, by=world[1], conversation=world[3], dry_run=False)
    assert eid in {r["entry"] for r in done["requested"]}
    assert world[0].cv.asks_about(eid)
    assert eid not in migrate(world[0].cv, by=world[1], conversation=world[3])["entries"]


def test_fluid_api_contract_uses_read_model(world, monkeypatch):
    source = record(world)
    eid = record(world, basis=[source])
    def get(path, **query):
        return _routes(world[0], path, {k: [v] for k, v in query.items()}, None, "GET")
    items = get("/api/ladder/items", kind="lesson", agent=world[2], conversation=world[3])
    assert items["total"] == 2
    assert items["counts"]["recorded"] == 2
    assert len(get("/api/ladder/items", kind="lesson", limit="1")["items"]) == 1
    assert "error" in get("/api/ladder/items", offset="-1")
    assert get("/api/ladder/items", kind="lesson", runtime="claude")["total"] == 0
    detail = get(f"/api/ladder/items/{eid}")
    assert detail["basis"][0]["ref"] == source
    assert detail["originating"]["conversation"] == world[3]
    asked = run(world, "request_adoption", entry=eid, because="future work")
    card = next(c for c in get("/api/ladder/adoption")["requests"] if c["entry"] == eid)
    assert card["request"] == asked["request"] and card["ask"] == asked["ask"]
    assert card["evidence"][0]["id"] == source
    assert card["wording"]["current"] is None
    assert "error" not in post(world, eid, "adopt")
    assert all(c["entry"] != eid for c in get("/api/ladder/adoption")["requests"])
    adopted = next(i for i in get("/api/ladder/adopted")["items"] if i["id"] == eid)
    assert adopted["status"] == "adopted" and adopted["adopted_by"] == world[1]


def test_register_proposed_requires_a_request(world):
    from mentis.conversation.register import governed
    eid = record(world)
    result = governed(world[0].brain, kind="lesson")
    assert eid in [i["entry"] for i in result["groups"]["recorded"]]
    assert eid not in [i["entry"] for i in result["groups"]["proposed"]]
    run(world, "request_adoption", entry=eid, because="future work")
    result = governed(world[0].brain, kind="lesson")
    assert eid in [i["entry"] for i in result["groups"]["proposed"]]


def test_edit_then_adopt_is_atomic_and_preserves_basis(world):
    eid = record(world)
    run(world, "request_adoption", entry=eid, because="future work")
    result = post(world, eid, "adopt", body={"text": "edited", "limits": "narrow"})
    assert "error" not in result, result
    new = result["entry"]
    assert new != eid and world[0].corpus.stands(new)["stands"]
    assert not world[0].corpus.stands(eid)["stands"]
    assert world[0].corpus.links(relation="derived-from", frm=new)[0]["link"]["to"] == eid
    assert not world[0].cv.asks_about(eid)


def test_vocabulary_cli_against_own_ephemeral_server(world, capsys):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from tools.ladder_vocabulary import main
    corpus = world[0].corpus
    props = dict(corpus.current_definition("hypothesis")["body"])
    props.pop("kind")
    props.pop("fields")
    corpus.define_kind("hypothesis", fields=["text"], properties=props, attributed_to=world[1])
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            result = _routes(world[0], self.path, {}, payload, "POST")
            data = json.dumps(result).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        args = ["--server", f"http://127.0.0.1:{server.server_port}"]
        assert main(args) == 0
        report = capsys.readouterr().out
        assert "=== Mentis Ladder Vocabulary Report" in report
        assert "Definition Changes" in report
        assert main([*args, "--json"]) == 0
        dry = json.loads(capsys.readouterr().out)
        assert dry["dry_run"] and dry["written"] == 0 and dry["changes"]
        assert main([*args, "--apply", "--attributed-to", world[1], "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["written"] == 1
        assert main([*args, "--apply", "--attributed-to", world[1], "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["written"] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_adopt_respects_declared_placement_and_rolls_back(world):
    eid = record(world, "workflow", body={"name": "A", "text": "one activity", "activities": []})
    result = post(world, eid, "adopt", scope={"where": world[3]})
    # Since vocabulary revision operating-model-1 a Workflow is placeable
    # only by reference, and an adoption's placement is a full one.
    assert "error" in result and "placed only by reference" in result["error"]
    assert not world[0].corpus.stands(eid)["stands"]


def test_owner_can_request_an_old_entry_without_an_origin(world):
    eid = world[0].corpus.write(kind="lesson", body={"text": "legacy"}, attributed_to=world[2])
    result = post(world, eid, "request-adoption")
    assert "error" not in result, result
    assert world[0].cv.asks_about(eid)


def test_bookkeeping_notes_are_never_reported_as_adopted(world):
    from mentis.conversation.knowledge import considered
    eid = record(world, body={"text": "zorblax lesson"})
    request = run(world, "request_adoption", entry=eid, because="zorblax request reason")
    challenge = run(world, "challenge", target=eid, because="zorblax objection reason", evidence=[world[3]])
    withdrawn = run(world, "withdraw_challenge", dispute=challenge["disputed"], because="zorblax withdrawal")
    post(world, eid, "decline", because="zorblax decline reason")
    notes = {world[0].corpus.read([request["request"]])[0]["link"]["from"], challenge["objection"],
             withdrawn["note"]}
    notes.update(e["link"]["from"] for e in world[0].corpus.links(relation="declines", to=eid))
    assert len(notes) == 4 and all(world[0].corpus.stands(n)["stands"] for n in notes)
    result = _routes(world[0], "/api/ladder/adopted", {}, None, "GET")
    assert not notes.intersection(i["id"] for i in result["items"])
    # AND ADOPTED RECALL (`considered`) leaves them out too.
    assert not notes.intersection(r["entry"] for r in considered(world[0].corpus, "zorblax"))


def test_compatibility_alias_keeps_evidence_when_adoption_is_ineligible(world):
    result = run(world, "propose_material", kind="finding", body={"text": "found evidence"},
                 basis=[world[3]])
    assert result["entry"] and result["request"] is None and result["request_why_not"]
    assert not world[0].corpus.stands(result["entry"])["stands"]
    assert not world[0].cv.asks_about(result["entry"])


def test_basis_citation_checks_digest_and_byte_range(world):
    from mentis import artifacts
    held = artifacts.hold(world[0].corpus, world[0].cv, b"evidence", act=artifacts.SUBMITTED,
                          actor=world[1], source="test", door="human-ingress",
                          claimed_name="proof.txt", claimed_media_type="text/plain")
    ref, digest = held["admission"], held["digest"]
    cite = f"{ref}@{digest[:12]}[0:4]"
    eid = record(world, basis=[cite])
    assert world[0].corpus.links(relation="extracted-from", frm=eid)[0]["body"]["cite"] == cite
    for bad in (f"{ref}@{'0' * 64}[0:4]", f"{ref}@{digest}[4:3]", f"{ref}@{digest}[0:100]"):
        with pytest.raises(NotPermitted):
            record(world, basis=[bad])


def test_vocabulary_apply_requires_explicit_owner_attribution(world):
    def route(body):
        return _routes(world[0], "/api/ladder/vocabulary", {}, body, "POST")
    assert "error" in route({"apply": True})
    assert "error" in route({"apply": True, "attributed_to": world[2]})
    assert "error" not in route({"apply": True, "attributed_to": world[1]})


def test_vocabulary_adds_declines_to_a_legacy_corpus(world, tmp_path, monkeypatch):
    import mentis.api as api
    from mentis.spine import seed
    from tools.ladder_vocabulary import plan, apply
    with monkeypatch.context() as patch:
        patch.setattr(seed, "RELATIONS", [r for r in seed.RELATIONS if r["relation"] != "declines"])
        corpus = api.create_corpus(str(tmp_path / "legacy"))
    try:
        assert corpus.current_definition("declines") is None
        assert apply(corpus, plan(corpus), by="human") == 1
        assert corpus.current_definition("declines")["body"]["relation"] == "declines"
        assert plan(corpus) == []
    finally:
        corpus.close()


def test_migrated_revision_preserves_replacement_intent(world):
    from tools.ladder_vocabulary import migrate
    corpus = world[0].corpus
    old = record(world, "rule", body={"text": "old rule"})
    post(world, old, "adopt", scope={"where": world[3]})
    candidate = corpus.write(kind="rule", body={"text": "old-style revision"}, attributed_to=world[2])
    corpus.propose_supersession(candidate, [old], attributed_to=world[2], reason="old request format")
    migrate(world[0].cv, by=world[1], conversation=world[3], dry_run=False)
    request = writes.requests(corpus, candidate)[0]
    assert request["body"]["replaces"] == [old]
    assert "error" not in post(world, candidate, "adopt", replaces=None)
    assert corpus.stands(candidate)["stands"] and not corpus.stands(old)["stands"]


def test_explicit_empty_replacements_are_respected(world):
    corpus = world[0].corpus
    old = record(world, "rule", body={"text": "old"})
    post(world, old, "adopt")
    candidate = record(world, "rule", body={"text": "independent"})
    corpus.propose_supersession(candidate, [old], attributed_to=world[2], reason="earlier intention")
    run(world, "request_adoption", entry=candidate, replaces=[], because="adopt independently")
    assert "error" not in post(world, candidate, "adopt")
    assert corpus.stands(old)["stands"] and corpus.stands(candidate)["stands"]


def test_adopted_material_used_as_objection_is_still_listed(world, monkeypatch):
    evidence = record(world, "rule", body={"text": "a governing counterexample"})
    target = record(world)
    post(world, evidence, "establish")
    writes.edge(world[0].corpus, evidence, target, "disputes", by=world[1])
    result = _routes(world[0], "/api/ladder/adopted", {}, None, "GET")
    assert evidence in {i["id"] for i in result["items"]}


def test_vocabulary_adds_in_context_to_a_brain_without_it(world, tmp_path, monkeypatch):
    """Found on INTEGRATION: the live Brain predates `in-context`, so no
    outcome could be recorded until the vocabulary tool brought it in."""
    import mentis.api as api
    from mentis.spine import seed
    from tools.ladder_vocabulary import plan, apply
    with monkeypatch.context() as patch:
        patch.setattr(seed, "RELATIONS", [r for r in seed.RELATIONS if r["relation"] != "in-context"])
        corpus = api.create_corpus(str(tmp_path / "old"))
    try:
        assert corpus.current_definition("in-context") is None
        assert "in-context" in {c["name"] for c in plan(corpus)}
        apply(corpus, plan(corpus), by="human")
        assert corpus.current_definition("in-context")["body"]["inverse"] == "context-of"
        assert plan(corpus) == []
    finally:
        corpus.close()


def test_recorded_material_names_the_persona_the_run_wore(world):
    from mentis.conversation import ladder
    st = world[0]
    persona = st.cv.write_persona("Recorder", behaviour="records", attributed_to=world[1]) \
        if hasattr(st.cv, "write_persona") else st.corpus.write(
            kind="persona", body={"name": "Recorder", "behaviour": "records"}, attributed_to=world[1])
    persona = persona if isinstance(persona, str) else persona["entry"]
    world[4]["persona"] = persona
    eid = record(world)
    act = next(a for a in st.cv.history() if a["act"] == "material-recorded" and eid in a["about"])
    assert act["detail"]["persona"] == persona
    rb = ladder.recorded_by(st.corpus, st.cv, eid)
    assert rb["persona"] == persona and rb["persona_name"] == "Recorder"


# -- supersession: one record from either door, and what an adoption changes --


def _standing_rule(world, text="old rule", **scope):
    old = record(world, "rule", body={"text": text})
    assert "error" not in post(world, old, "adopt", scope=scope or {"where": world[3]})
    return old


def _register_row(world, eid):
    from mentis.conversation.register import governed
    got = governed(world[0].brain, kind="rule", limit=1000)
    return next(r for g in got["groups"].values() for r in g if r["entry"] == eid)


@pytest.mark.parametrize("door", ["of", "replaces"])
def test_both_successor_doors_write_the_same_proposal(world, door):
    """Found by the 2026-10-28 audit: `entry + replaces` wrote the replacement
    only into the request body, so the register said `predecessors: []`."""
    corpus = world[0].corpus
    old = _standing_rule(world)
    world[4]["delivered"] = [old]
    if door == "of":
        got = run(world, "request_adoption", of=old, body={"text": "new rule"}, because="gap")
    else:
        new = record(world, "rule", body={"text": "new rule"})
        got = run(world, "request_adoption", entry=new, replaces=[old], because="gap")
    new = got["entry"]
    row = _register_row(world, new)
    assert row["group"] == "proposed"
    assert [p["entry"] for p in row["proposed"]["predecessors"]["items"]] == [old]
    assert world[3] in row["proposed_reach"]
    assert new in [s["entry"] for s in _register_row(world, old)["proposed"]["successors"]["items"]]
    card = next(c for c in _routes(world[0], "/api/ladder/adoption", {}, None, "GET")["requests"]
                if c["entry"] == new)
    assert [r["id"] for r in card["replaces"]] == [old]
    # Proposing displaces nothing.
    assert corpus.stands(old)["stands"] and not corpus.stands(new)["stands"]
    comp = world[0].cv.compose(conversation=world[3], participant=world[2])
    assert old in {c.source_id for c in comp.components}
    assert new not in {c.source_id for c in comp.components}


def test_session_may_propose_a_successor_to_what_it_can_read(world):
    from mentis.worker import SESSION_SCOPE
    old = _standing_rule(world)
    # A dispatched run proposes successors to what it was delivered, by either door.
    with pytest.raises(NotPermitted, match="not delivered"):
        run(world, "request_adoption", of=old, body={"text": "new"}, because="gap")
    other = record(world, "rule", body={"text": "other"})
    with pytest.raises(NotPermitted, match="not delivered"):
        run(world, "request_adoption", entry=other, replaces=[old], because="gap")
    session = {"participant": world[2], "runtime": "claude", "instance": "sess-1",
               "scope": SESSION_SCOPE}
    got = _operate(_surface(world[0]), "request_adoption",
                   {"of": old, "body": {"text": "new"}, "because": "gap"}, session)
    assert got["status"] == "adoption_requested"
    assert world[0].corpus.stands(old)["stands"]


def test_adopted_successor_governs_in_its_predecessors_place(world):
    """The supersession requirement, end to end: placement is inherited,
    delivery resolves to the successor, history names both, challenges stay."""
    from mentis.conversation import ladder as read, placements_now
    st, corpus, cv = world[0], world[0].corpus, world[0].cv
    persona = _routes(st, "/api/personas", {}, {"name": "Reviewer", "behaviour": "review",
                                                "attributed_to": world[1]}, "POST")["persona"]
    here = _standing_rule(world, "here rule")
    everywhere = _standing_rule(world, "brain rule", whole_brain=True)
    carried = _standing_rule(world, "persona rule", where=persona)
    challenge = run(world, "challenge", target=here, because="doubt it")
    world[4]["delivered"] = [here, everywhere, carried]
    successors = {}
    for old in (here, everywhere, carried):
        before = set(placements_now(corpus, old))
        successors[old] = run(world, "request_adoption", of=old, body={"text": f"new {old}"},
                              because="replace")["entry"]
        assert "error" not in post(world, successors[old], "adopt")
        assert set(placements_now(corpus, successors[old])) == before
    for old, new in successors.items():
        assert not corpus.stands(old)["stands"] and corpus.stands(new)["stands"]
        assert corpus.read([old])  # history, not removed
    comp = cv.compose(conversation=world[3], participant=world[2], persona=persona,
                      behavioural=[here])
    ids = [c.source_id for c in comp.components]
    assert set(successors.values()) <= set(ids)
    assert not {here, everywhere, carried} & set(ids)
    assert len(ids) == len(set(ids))
    named = next(w for w in comp.withheld if w.get("source_id") == here
                 and w.get("delivered_instead"))
    assert named["delivered_instead"] == successors[here]
    # Historical retrieval names both directions.
    assert _register_row(world, here)["group"] == "history"
    assert _register_row(world, here)["superseded_by"] == [successors[here]]
    assert _register_row(world, successors[here])["supersedes"] == [here]
    # The challenge stays visible and revoked nothing.
    assert [c["link"] for c in read.challenges_of(corpus, here)] == [challenge["disputed"]]
    assert corpus.stands(successors[here])["stands"]


def test_whole_brain_successor_reaches_brain_scope_work(world):
    corpus = world[0].corpus
    old = _standing_rule(world, whole_brain=True)
    world[4]["delivered"] = [old]
    new = run(world, "request_adoption", of=old, body={"text": "new"}, because="x")["entry"]
    assert "error" not in post(world, new, "adopt")
    at_brain = world[0].brain.compose(participant=world[2])
    assert new in {c.source_id for c in at_brain.components}
    assert old not in {c.source_id for c in at_brain.components}
    assert corpus.read([old])


@pytest.fixture
def unrepaired(tmp_path, monkeypatch):
    """A Brain whose vocabulary predates the ladder: no declines, withdraws
    or in-context, as the live Brain was until the repair is applied."""
    from mentis.spine import seed
    missing = ("declines", "withdraws", "in-context")
    with monkeypatch.context() as patch:
        patch.setattr(seed, "RELATIONS", [r for r in seed.RELATIONS if r["relation"] not in missing])
        root = str(tmp_path / "corpus")
        fixture.build(root)
    st = _State(root, str(tmp_path))
    cv = st.cv
    owner = cv.resolve_participant("@brian")
    agent = cv.resolve_participant("@Ada")
    conv = cv.open_conversation("Unrepaired")
    turn = cv.say(conv, owner, [{"type": "text", "text": "work"}])
    exp = cv.expect(turn, of=agent, kind="result", by=owner)
    grant = {"participant": agent, "runtime": "codex", "instance": "inst-old",
             "conversation": conv, "expectation": exp, "scope": "organising"}
    assert all(st.corpus.current_definition(r) is None for r in missing)
    yield st, owner, agent, conv, grant
    st.corpus.close()


def test_unrepaired_vocabulary_refuses_naming_the_repair(unrepaired):
    from mentis.conversation.ladder import challenges_of
    w = unrepaired
    corpus = w[0].corpus
    eid = record(w)
    run(w, "request_adoption", entry=eid, because="future work")
    declined = post(w, eid, "decline")
    assert "vocabulary repair" in declined["error"] and "'declines'" in declined["error"]
    mine = run(w, "challenge", target=eid, because="mine")
    with pytest.raises(NotPermitted, match="'withdraws' relation.*vocabulary repair"):
        run(w, "withdraw_challenge", dispute=mine["disputed"], because="I was wrong")
    with pytest.raises(NotPermitted, match="'in-context' relation.*vocabulary repair"):
        record(w, "outcome", body={"text": "tried", "result": "failed", "attempted": True},
               outcome_of=eid, in_context=w[3])
    # Nothing half-written: the request and the challenge are both still open.
    assert w[0].cv.asks_about(eid)
    assert challenges_of(corpus, eid)[0]["resolution"] == "open"
    # Adoption itself needs none of the three.
    assert "error" not in post(w, eid, "adopt")

def test_hypothesis_recordable_with_falsifier_and_limits(world):
    turn = world[3]
    eid = run(world, "record_material", kind="hypothesis",
              body={"text": "A conjectures X", "falsifier": "A test fails", "limits": "Under condition Y"},
              basis=[turn])["entry"]
    assert eid
    entry = world[0].corpus.read([eid])[0]
    assert entry["body"]["falsifier"] == "A test fails"
    assert entry["body"]["limits"] == "Under condition Y"
    result = post(world, eid, "adopt", because="verified", falsifier="A test fails")
    assert "error" not in result, result
    assert world[0].corpus.stands(eid)["stands"]


def test_solution_requires_basis_and_can_be_recorded(world):
    turn = world[3]
    with pytest.raises(NotPermitted, match="declares requires_basis"):
        run(world, "record_material", kind="solution", body={"text": "Try X"})
    result = run(world, "record_material", kind="solution", body={"text": "Try X"}, basis=[turn])
    assert result["entry"]
    assert result["status"] == "recorded"
    assert not result["stands"]
    entry = world[0].corpus.read([result["entry"]])[0]
    assert entry["body"]["text"] == "Try X"


def test_finding_and_lesson_require_basis(world):
    turn = world[3]
    with pytest.raises(NotPermitted, match="declares requires_basis"):
        run(world, "record_material", kind="finding", body={"text": "Found X"})
    res_f = run(world, "record_material", kind="finding", body={"text": "Found X"}, basis=[turn])
    assert res_f["entry"]

    with pytest.raises(NotPermitted, match="declares requires_basis"):
        run(world, "record_material", kind="lesson", body={"text": "Learned X"})
    res_l = run(world, "record_material", kind="lesson", body={"text": "Learned X"}, basis=[res_f["entry"]])
    assert res_l["entry"]


def test_vocabulary_format_report(world):
    from tools.ladder_vocabulary import format_report
    sample_result = {
        "dry_run": True,
        "written": 0,
        "changes": [
            {"name": "hypothesis", "family": "kind",
             "before": {"fields": ["text"], "kind": "hypothesis"},
             "after": {"fields": ["text", "limits", "falsifier"], "kind": "hypothesis", "standing_apt": True, "expects_falsifier": True, "requires_basis": True}},
            {"name": "solution", "family": "kind", "before": None,
             "after": {"fields": ["text"], "kind": "solution", "standing_apt": False, "requires_basis": True}},
            {"name": "declines", "family": "relation", "before": None,
             "after": {"relation": "declines", "inverse": "declined-by", "directed": True}},
        ],
        "migration": {
            "dry_run": True,
            "entries": ["ent-test1"],
            "planned": [{"entry": "ent-test1", "kind": "rule", "text": "Test rule", "replaces": ["ent-old"], "proposer": world[1], "proposer_alias": "@alice"}],
            "requested": [],
            "skipped": [],
        }
    }
    report = format_report(sample_result, server="http://127.0.0.1:8797")
    assert "=== Mentis Ladder Vocabulary Report (DRY RUN" in report
    assert "Target Server: http://127.0.0.1:8797" in report
    assert "Kind: hypothesis [MODIFIED]" in report
    assert "Kind: solution [NEW]" in report
    assert "Relation: declines [NEW]" in report
    assert "Candidate Proposal Migration (1 candidates, Planned" in report
    assert "ent-test1 (rule)" in report
