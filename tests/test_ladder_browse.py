"""Manage Brain in Quiet Chat: the one Brain list, the bounded item detail, and
the targeted reads under them. Read-side only: nothing here adds a rule, a
status or an approval."""
import pytest

from mentis.conversation import ladder as read
from mentis.web import _State, _routes, _surface, fixture
from mentis.web import ladder as web_ladder
from mentis.worker import _operate


@pytest.fixture
def world(tmp_path):
    root = str(tmp_path / "corpus")
    fixture.build(root)
    st = _State(root, str(tmp_path))
    cv = st.cv
    owner = cv.resolve_participant("@brian")
    agent = cv.resolve_participant("@Ada")
    conv = cv.open_conversation("Brain browse checks")
    turn = cv.say(conv, owner, [{"type": "text", "text": "work"}])
    exp = cv.expect(turn, of=agent, kind="result", by=owner)
    grant = {"participant": agent, "runtime": "codex", "instance": "inst-browse",
             "conversation": conv, "expectation": exp, "scope": "organising"}
    yield st, owner, agent, conv, grant
    st.corpus.close()


def run(w, name, **args):
    return _operate(_surface(w[0]), name, args, w[4])


def record(w, kind="lesson", **kw):
    kw.setdefault("basis", [w[3]])
    return run(w, "record_material", kind=kind,
               body=kw.pop("body", {"text": "a lesson", "limits": "local"}), **kw)["entry"]


def post(w, eid, act, **kw):
    return _routes(w[0], f"/api/entries/{eid}/{act}", {},
                   {"attributed_to": w[1], "because": "owner reviewed", **kw}, "POST")


def get(w, path, **query):
    return _routes(w[0], path, {k: [str(v)] for k, v in query.items()}, None, "GET")


def browse(w, **query):
    got = get(w, "/api/ladder/browse", **query)
    assert "error" not in got, got
    return got


# -- the store's targeted act reads --------------------------------------------

def test_acts_about_one_entry_are_exactly_the_acts_that_name_it(world):
    st = world[0]
    one, other = record(world), record(world, body={"text": "another lesson"})
    whole = [a["id"] for a in st.corpus.operational() if one in (a.get("about") or ())]
    assert whole, "the recording act names what it recorded"
    assert [a["id"] for a in st.corpus.operational(about=one)] == whole
    assert all(other not in (a.get("about") or ()) or one in a["about"]
               for a in st.corpus.operational(about=one))
    assert st.corpus.operational(about="ent-000000000000") == []


def test_the_narrowing_never_decides_by_itself(world):
    """The SQL narrowing can only over-match; the exact check still decides."""
    st = world[0]
    eid = record(world)
    assert st.corpus.operational(about=eid[:-1]) == [], "a prefix of an id is not that id"
    assert all(eid in a["about"] for a in st.corpus.operational(about=eid))
    with pytest.raises(ValueError):
        st.corpus.operational(about="")


def test_asks_about_reads_the_same_asks_as_before(world):
    st = world[0]
    eid = record(world)
    assert st.cv.asks_about(eid) == []
    run(world, "request_adoption", entry=eid, because="ready")
    asks = st.cv.asks_about(eid)
    assert len(asks) == 1
    # the old read: every expectation, decoded, checked in Python
    old = [a["id"] for a in st.corpus.operational()
           if a["act"] == "expectation-recorded" and eid in (a["detail"] or {}).get("material", ())]
    assert [a["expectation"] for a in asks] == old


# -- the list ------------------------------------------------------------------

def test_browse_says_the_ladders_own_status_and_never_guesses(world):
    """A declined candidate is Declined, not Recorded; an adopted one Adopted."""
    declined, adopted, plain = record(world), record(world, body={"text": "second"}), record(world, body={"text": "third"})
    run(world, "request_adoption", entry=declined, because="please")
    post(world, declined, "decline", request=world[0].corpus.links(relation="proposes", to=declined)[0]["id"])
    run(world, "request_adoption", entry=adopted, because="please")
    post(world, adopted, "adopt")
    rows = {r["id"]: r for r in browse(world, view="knowledge", limit=200)["items"]}
    for eid in (declined, adopted, plain):
        assert rows[eid]["status"] == read.adoption_status(world[0].corpus, eid)
    assert (rows[declined]["status"], rows[adopted]["status"], rows[plain]["status"]) == (
        "declined", "adopted", "recorded")
    assert rows[adopted]["governs"] is False and rows[adopted]["adoptable"] is True


def test_views_split_knowledge_from_governing_and_all_holds_each_once(world):
    lesson = record(world)
    rule = record(world, "rule", body={"text": "always check"}, basis=[])
    knowledge = {r["id"] for r in browse(world, view="knowledge", limit=200)["items"]}
    governing = {r["id"]: r for r in browse(world, view="governing", limit=200)["items"]}
    everything = [r["id"] for r in browse(world, view="all", limit=200)["items"]]
    assert lesson in knowledge and lesson not in governing
    assert rule in governing and rule not in knowledge
    assert governing[rule]["governs"] is True
    assert len(everything) == len(set(everything))
    assert {lesson, rule} <= set(everything)
    assert get(world, "/api/ladder/browse", view="nonsense")["error"]


def test_browse_is_paged_newest_first_and_says_the_total(world):
    made = [record(world, body={"text": f"lesson number {n}"}) for n in range(7)]
    first = browse(world, view="knowledge", q="lesson number", limit=3)
    assert first["total"] == 7 and len(first["items"]) == 3
    second = browse(world, view="knowledge", q="lesson number", limit=3, offset=3)
    third = browse(world, view="knowledge", q="lesson number", limit=3, offset=6)
    seen = [r["id"] for page in (first, second, third) for r in page["items"]]
    assert sorted(seen) == sorted(made) and len(seen) == 7, "every record once across the pages"
    times = [r["recorded_at"] for page in (first, second, third) for r in page["items"]]
    assert times == sorted(times, reverse=True)
    assert get(world, "/api/ladder/browse", limit=0)["error"]
    assert get(world, "/api/ladder/browse", limit=201)["error"]


def test_kinds_come_from_the_record_and_filter_it(world):
    record(world)
    note = record(world, "note", body={"text": "kept for later"}, basis=[])
    got = browse(world, view="knowledge", limit=200)
    kinds = {k["kind"]: k for k in got["kinds"]}
    assert kinds["note"]["count"] >= 1 and kinds["lesson"]["count"] >= 1
    assert kinds["note"]["governs"] is False
    only = browse(world, view="knowledge", kind="note", limit=200)
    assert note in [r["id"] for r in only["items"]]
    assert {r["kind"] for r in only["items"]} == {"note"}
    # the options stay whole while one is chosen: choosing does not empty them
    assert {k["kind"] for k in only["kinds"]} == set(kinds)


def test_status_filter_and_search(world):
    asked = record(world, body={"text": "the zebra lesson"})
    record(world, body={"text": "the plain lesson"})
    run(world, "request_adoption", entry=asked, because="please")
    got = browse(world, view="all", status="adoption_requested", limit=200)
    assert [r["id"] for r in got["items"]] == [asked]
    assert [r["id"] for r in browse(world, view="knowledge", q="ZEBRA")["items"]] == [asked]
    assert [r["id"] for r in browse(world, view="knowledge", q=asked)["items"]] == [asked]


def test_replaced_and_deleted_are_counted_and_left_out_until_asked_for(world):
    eid = record(world, "rule", body={"text": "a rule to end"}, basis=[])
    post(world, eid, "establish")
    before = browse(world, view="governing", limit=200)
    assert eid in [r["id"] for r in before["items"]]
    post(world, eid, "delete")
    after = browse(world, view="governing", limit=200)
    assert eid not in [r["id"] for r in after["items"]]
    assert after["past"] == before["past"] + 1
    with_past = browse(world, view="governing", past=1, limit=200)
    row = next(r for r in with_past["items"] if r["id"] == eid)
    assert row["status"] == "deleted"


def test_bookkeeping_notes_are_never_listed_as_adopted(world):
    eid = record(world)
    run(world, "request_adoption", entry=eid, because="the reason is a note")
    post(world, eid, "adopt")
    rows = browse(world, view="all", limit=200)["items"]
    assert all(not (r["status"] == "adopted" and not r["adoptable"]) for r in rows)


def test_needs_you_is_the_bells_own_list_resolved_to_records(world):
    from mentis.fluid.home import asking_owner
    st, owner = world[0], world[1]
    quiet, asked = record(world), record(world, body={"text": "asked of the owner"})
    assert browse(world, view="needs-you")["items"] == []
    run(world, "request_adoption", entry=asked, because="please decide")
    got = browse(world, view="needs-you")
    assert [r["id"] for r in got["items"]] == [asked] and got["total"] == 1
    assert got["items"][0]["ask"] in [ask for _, ask in asking_owner(st.cv, owner)]
    assert quiet not in [r["id"] for r in got["items"]]
    post(world, asked, "adopt")
    assert browse(world, view="needs-you")["items"] == [], "answered: no longer waiting"


# -- the item ------------------------------------------------------------------

def test_detail_is_bounded_and_still_counts_everything(world, monkeypatch):
    st, _, agent, conv, _ = world
    eid = record(world)
    rows = [{"execution": f"exe-{i:04d}", "participant": agent, "runtime": "codex",
             "conversation": conv, "at": 1000.0 + i,
             "behavioural_sources": [{"source_id": eid, "tier": "experience"},
                                     {"source_id": eid, "tier": "experience"}]}
            for i in range(60)]
    monkeypatch.setattr(type(st.cv._c), "deliveries", lambda self: rows)
    calls = []
    real_alias = st.cv.alias
    monkeypatch.setattr(st.cv, "alias", lambda who: calls.append(who) or real_alias(who))
    got = get(world, f"/api/ladder/items/{eid}")
    assert got["delivered_total"] == 60 and got["usage"]["delivered"] == 60
    assert len(got["delivered"]) == web_ladder.DELIVERED_SHOWN
    assert [d["execution"] for d in got["delivered"]][:2] == ["exe-0059", "exe-0058"], "the newest first"
    assert calls.count(agent) <= 2, "a participant is named once per reader, not once per run"
    assert len(get(world, f"/api/ladder/items/{eid}", delivered_limit=0)["delivered"]) == 0
    assert len(get(world, f"/api/ladder/items/{eid}", delivered_limit=500)["delivered"]) == 60
    assert get(world, f"/api/ladder/items/{eid}", delivered_limit=501)["error"]
    # the list counts the same deliveries the item does
    row = next(i for i in get(world, "/api/ladder/items", limit=1000)["items"] if i["id"] == eid)
    assert row["delivered_to"] == 60


def test_detail_carries_history_requests_and_where_things_are(world):
    st, owner, agent, conv, grant = world
    eid = record(world)
    run(world, "request_adoption", entry=eid, because="it held twice")
    got = get(world, f"/api/ladder/items/{eid}")
    assert [h["act"] for h in got["history"]][0] == "material-recorded"
    assert all(h["by_alias"] for h in got["history"])
    assert [r["because"] for r in got["adoption"]["requests"]] == ["it held twice"]
    assert got["adoption"]["requests"][0]["closed"] is False
    assert got["owner"] == owner
    assert got["said"] == "a lesson"
    post(world, eid, "adopt")
    adopted = get(world, f"/api/ladder/items/{eid}")
    assert adopted["status"] == "adopted"
    assert adopted["adoption"]["adopted"]["by"] == owner
    assert adopted["adoption"]["adopted"]["by_alias"] == st.cv.alias(owner)
    assert adopted["adoption"]["requests"][0]["closed_by"] == "adopted"
    assert adopted["superseded_by"] == []


def test_an_outcome_says_where_it_was_observed_and_what_cites_is_named(world):
    st, owner, agent, conv, grant = world
    eid = record(world)
    turn = st.cv.expectation_state(grant["expectation"])["turn"]
    out = record(world, "outcome", body={"text": "it held", "result": "inconclusive", "attempted": True},
                 basis=[], outcome_of=eid, in_context=turn)
    got = get(world, f"/api/ladder/items/{eid}")
    assert [o["id"] for o in got["outcomes"]] == [out]
    where = got["outcomes"][0]["where"]
    assert where == {"conversation": conv, "conversation_name": st.cv.conversation_name(conv),
                     "turn": turn, "number": st.cv.turn_number(turn)}
    cited = {c["entry"]: c for c in got["cited_by"]}
    assert cited[out]["label"], "what cites it is said in its own words, not only by id"
    assert got["cited_total"] == len(got["cited_by"])


def test_inconclusive_is_counted_by_name_and_other_keeps_its_meaning(world, monkeypatch):
    st, owner, agent, conv, grant = world
    eid = record(world)
    turn = st.cv.expectation_state(grant["expectation"])["turn"]
    monkeypatch.setattr(type(st.cv._c), "deliveries", lambda self: [{
        "execution": "exe-first", "participant": agent, "runtime": "codex", "conversation": conv,
        "at": 0.0, "behavioural_sources": [{"source_id": eid, "tier": "experience"}]}])
    for result in ("worked", "failed", "inconclusive", "inconclusive", "partial"):
        record(world, "outcome", body={"text": result, "result": result, "attempted": True},
               basis=[], outcome_of=eid, in_context=turn)
    after = read.usage(st.corpus, st.cv, eid)["outcomes_after_delivery"]
    assert after == {"worked": 1, "failed": 1, "other": 3, "inconclusive": 2}
    assert get(world, f"/api/ladder/items/{eid}")["usage"]["outcomes_after_delivery"] == after


def test_a_replaced_record_names_its_successor(world):
    old = record(world, "rule", body={"text": "the first wording"}, basis=[])
    post(world, old, "establish")
    new = record(world, "rule", body={"text": "the second wording"}, basis=[])
    post(world, new, "establish")
    assert "error" not in post(world, old, "supersede", replacement=new)
    got = get(world, f"/api/ladder/items/{old}")
    assert got["status"] == "superseded"
    assert [(s["id"], s["label"], s["deleted"]) for s in got["superseded_by"]] == [
        (new, "the second wording", False)]


def test_words_of_a_kind_without_text_are_its_first_stated_field(world):
    st = world[0]
    made = _routes(st, "/api/personas", {}, {"name": "Reviewer", "behaviour": "review carefully",
                                             "attributed_to": world[1]}, "POST")
    persona = made.get("persona") or made.get("entry") or made.get("id")
    assert persona, made
    got = get(world, f"/api/ladder/items/{persona}")
    assert got["said"], "a Persona has words although it has no `text`"
    row = next(r for r in browse(world, view="governing", limit=200)["items"] if r["id"] == persona)
    assert row["text"] == got["said"]


# -- summaries: presentation, beside the record --------------------------------

def write(w, path, **body):
    return _routes(w[0], path, {}, {"attributed_to": w[1], **body}, "POST")


def test_a_row_without_a_kept_summary_shows_its_own_first_sentence(world):
    from mentis import record_summaries as rs
    eid = record(world, body={"text": "Background tests die with the run. The brief has to say to wait for them, "
                                      "because MARS does not await a process the run left behind."})
    row = next(r for r in browse(world, view="knowledge", limit=200)["items"] if r["id"] == eid)
    assert (row["summary"], row["summary_source"]) == ("Background tests die with the run.", "derived")
    assert rs.read(world[0].corpus.root) == {}, "a derived summary is computed, never stored"
    long = "x" * 30 + " " + "word " * 80
    assert len(rs.derive(long)) <= 141 and rs.derive(long).endswith("…")
    assert rs.derive("Met. All four named cases now pass.") == "Met. All four named cases now pass."
    assert rs.derive("You are Caretaker: the steward.", name="Caretaker") == "Caretaker: You are Caretaker: the steward."[11:] \
        or rs.derive("You are Caretaker: the steward.", name="Caretaker").startswith("Caretaker")
    assert rs.derive("") == ""


def test_the_owner_corrects_a_summary_and_the_record_is_untouched(world):
    from mentis import record_summaries as rs
    st = world[0]
    eid = record(world, body={"text": "The cache may be stale after a deploy; not yet confirmed.", "limits": "dev"})
    before = (st.corpus.read([eid])[0], len(st.corpus.operational()), st.corpus.stands(eid))
    got = write(world, f"/api/ladder/summaries/{eid}", summary="  The cache may be stale\nafter a deploy (unconfirmed). ")
    assert got["summary"]["text"] == "The cache may be stale after a deploy (unconfirmed)."
    assert got["summary"]["source"] == "written" and got["summary"]["by"] == world[1]
    row = next(r for r in browse(world, view="knowledge", limit=200)["items"] if r["id"] == eid)
    assert (row["summary"], row["summary_source"]) == ("The cache may be stale after a deploy (unconfirmed).", "written")
    detail = get(world, f"/api/ladder/items/{eid}")
    assert detail["summary"]["text"] == row["summary"] and detail["summary"]["by_alias"]
    assert detail["text"] == "The cache may be stale after a deploy; not yet confirmed.", "the wording is unchanged"
    assert (st.corpus.read([eid])[0], len(st.corpus.operational()), st.corpus.stands(eid)) == before, \
        "no entry, no act and no standing changed"
    assert [r["id"] for r in browse(world, view="knowledge", q="unconfirmed")["items"]] == [eid], "found by its summary"
    # corrected again: the earlier one is kept beside it
    write(world, f"/api/ladder/summaries/{eid}", summary="Possibly stale cache after deploys.")
    kept = rs.read(st.corpus.root)[eid]
    assert kept["summary"] == "Possibly stale cache after deploys." and kept["earlier"][0]["summary"].startswith("The cache may")
    # forgotten: back to its own first sentence
    assert write(world, f"/api/ladder/summaries/{eid}", remove=True)["summary"]["source"] == "derived"


def test_only_the_owner_keeps_summaries_and_bad_ones_are_refused(world):
    st, owner, agent = world[0], world[1], world[2]
    eid = record(world)
    path = f"/api/ladder/summaries/{eid}"
    assert "only the owner" in _routes(st, path, {}, {"attributed_to": agent, "summary": "x y"}, "POST")["error"]
    assert _routes(st, path, {}, {"summary": "nobody said who"}, "POST").get("error")
    assert "worker grant" in web_ladder.routes(st, path, {}, {"attributed_to": owner, "summary": "x"}, "POST",
                                               presented=world[4])["error"]
    assert write(world, path, summary="   ")["error"]
    assert "200" in write(world, path, summary="w" * 201)["error"]
    assert write(world, "/api/ladder/summaries/ent-000000000000", summary="x")["error"]
    from mentis import record_summaries as rs
    assert rs.read(st.corpus.root) == {}


def test_a_generated_batch_says_what_wrote_it_and_never_replaces_a_written_one(world):
    from mentis import record_summaries as rs
    st = world[0]
    a, b = record(world, body={"text": "first lesson words"}), record(world, body={"text": "second lesson words"})
    write(world, f"/api/ladder/summaries/{a}", summary="Written by the owner.")
    assert write(world, "/api/ladder/summaries", items=[{"id": a, "summary": "x"}])["error"], "a batch names its model"
    got = write(world, "/api/ladder/summaries", model="test-model-1", items=[
        {"id": a, "summary": "A generated one."}, {"id": b, "summary": "Second lesson, summarised."},
        {"id": "ent-000000000000", "summary": "nothing"}, {"id": b[:5], "summary": ""}])
    assert got["kept"] == [b]
    assert {r["id"] for r in got["refused"]} == {a, "ent-000000000000", b[:5]}
    kept = rs.read(st.corpus.root)
    assert kept[a]["summary"] == "Written by the owner." and kept[a]["source"] == "written"
    assert (kept[b]["source"], kept[b]["model"], kept[b]["by"]) == ("generated", "test-model-1", world[1])
    detail = get(world, f"/api/ladder/items/{b}")["summary"]
    assert (detail["source"], detail["model"]) == ("generated", "test-model-1")
    # the owner's correction replaces a generated one
    assert write(world, f"/api/ladder/summaries/{b}", summary="Corrected.")["summary"]["source"] == "written"


def test_missing_lists_what_has_no_kept_summary_with_its_words(world):
    a, b = record(world, body={"text": "alpha words"}), record(world, body={"text": "beta words"})
    write(world, f"/api/ladder/summaries/{a}", summary="Alpha.")
    got = get(world, "/api/ladder/summaries/missing", limit=500)
    ids = {r["id"]: r for r in got["items"]}
    assert a not in ids and ids[b]["words"] == "beta words" and ids[b]["kind"] == "lesson"
    assert got["total"] == len(got["items"])
    assert get(world, "/api/ladder/summaries/missing", limit=0)["error"]


def test_a_summary_written_for_other_words_is_not_shown(world):
    from mentis import record_summaries as rs
    st = world[0]
    eid = record(world, body={"text": "the words it has"})
    rs.put(st.corpus.root, eid, "About something else.", words="different words", source="written", by=world[1])
    row = next(r for r in browse(world, view="knowledge", limit=200)["items"] if r["id"] == eid)
    assert row["summary_source"] == "derived" and row["summary"] == "the words it has"


def test_nothing_that_forms_context_reads_summaries():
    """Presentation only: the store is imported by the Ladder's web reads and
    the batch tool, and by nothing that composes, retrieves, delivers or governs."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[1] / "mentis"
    users = sorted(str(p.relative_to(root)).replace("\\", "/") for p in root.rglob("*.py")
                   if p.name != "record_summaries.py"
                   and re.search(r"record_summaries", p.read_text("utf-8")))
    assert users == ["web/ladder.py"], users
