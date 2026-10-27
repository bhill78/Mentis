"""Import apply: `mentis brain import <brain> <zip> --apply` writes the
conflict-free part of an export (design adm-6cebfabd6e9c slice 2, O3-O7).

Every Brain is disposable, under tmp_path. A FORK IS MADE THE WAY ADOPTION
MAKES IT: the origin is closed and copied folder for folder, then the
`brain-forked` act Mark IV's installer wrote (`record_fork` below) gives the
copy its fork identity. What is
pinned:

  * a Conversation exported from A applies to B, B verifies, and the owner
    here establishes the imported structure -- and nothing else;
  * the same file again is a no-op that says so; a file from B's own fork
    is refused;
  * a fork continued on both sides interleaves by time, and the act records
    the whole numbering before and after (O3);
  * a rename on both sides, or only there over a Conversation that stands
    here, is skipped and reported, and no second Conversation appears;
  * an unresolved @name keeps out only what names that Participant (O4);
  * a Kind that differs keeps out its rows and their dependents (O6);
  * a foreign answer to a question answered here is kept out and recorded
    (O7);
  * an imported rule arrives as a candidate, not in force, placed nowhere;
  * a failure inside the transaction leaves B byte-identical;
  * decision forms travel (gap 2), and a server starting over B afterwards
    resumes no run, closes nothing for the foreign execution and owes no
    decision.
"""

from __future__ import annotations

import shutil

import pytest

import mentis.api as api
from mentis.bootstrap.baseline import OWNER_ABOUT
from mentis.brain.__main__ import main as brain_main
from mentis.conversation import placements_now, text
from mentis.exchange import ExchangeRefused, apply as apply_mod
from mentis.exchange.apply import IMPORT_APPLIED, ImportFailed, apply
from mentis.exchange.export import export
from mentis.spine import brainlock, migrations
from tests._brains import new_brain
from tests.test_exchange_export import _files, _heads, build, open_brain, tick


def empty_brain(path) -> str:
    """A fresh Brain at the same schema, its vocabulary defined as any Brain
    in use has it. (Mark IV's tests/test_exchange_preview.py, not lifted.)"""
    new_brain(path)
    c, _ = open_brain(path)
    c.close()
    return str(path)


def record_fork(brain: str) -> dict:
    """The `brain-forked` act adoption wrote (Mark IV's `installer.
    record_fork`, gone with the installer), written here the same way: by
    the owner the baseline identifies, with a new fork id and the heads it
    forked at. Exchange reads it (`mentis.exchange.identity`)."""
    import time
    import uuid
    from mentis.exchange.identity import BRAIN_FORKED
    from mentis.spine.store import Store
    store = Store(brain, access="write")
    try:
        with store.write():
            conn = store._conn
            heads = migrations._heads(conn)
            row = conn.execute(
                "SELECT id FROM entry WHERE def_name = 'participant' "
                "AND family = 'entry' AND link_relation IS NULL "
                "AND json_extract(body, '$.about') = ? ORDER BY seq LIMIT 1",
                (OWNER_ABOUT,)).fetchone()
            fork_id = uuid.uuid4().hex
            store.append_operational({
                "id": f"opr-{uuid.uuid4().hex[:12]}", "at": time.time(),
                "actor": row[0] if row else "human", "act": BRAIN_FORKED,
                "because": "adopted: this copy's own fork identity",
                "detail": {"fork_id": fork_id, "heads": heads,
                           "adopted_at": brain, "install": None}})
    finally:
        store.close()
    return {"fork_id": fork_id, "written": True}


@pytest.fixture
def W(tmp_path):
    W = build(tmp_path / "origin")
    W["me"] = W["cv"].create_participant("Owner", about=OWNER_ABOUT)
    # a request with no run under it, for forms asked after the fork
    W["request2"] = W["cv"].expect(W["t1"], of=W["coach"], kind="result",
                                   by=W["owner"])
    W["out"] = tmp_path / "out"
    W["out"].mkdir()
    W["backups"] = tmp_path / "backups"
    yield W
    W["corpus"].close()


def adopted_fork(W, tmp_path, name="fork") -> str:
    """A closed copy of the origin, adopted: its own `brain-forked` act."""
    W["corpus"].close()
    dest = str(tmp_path / name)
    shutil.copytree(W["path"], dest,
                    ignore=shutil.ignore_patterns(*brainlock.LOCK_FILES))
    assert record_fork(dest)["written"]
    W["corpus"] = api.open_corpus(W["path"])
    W["cv"] = api.conversations(W["corpus"])
    return dest


_n = [0]


def exported(W, **kw) -> str:
    _n[0] += 1
    path = str(W["out"] / f"x{_n[0]}.zip")
    export(W["path"], out=path, **kw)
    return path


def applied(dest, src, W) -> dict:
    _n[0] += 1
    return apply(dest, src, backup_dest=str(W["backups"] / f"b{_n[0]}"))


def acts_of(path, act) -> list:
    c = api.open_corpus(path, access="read")
    try:
        return c.operational(act=act)
    finally:
        c.close()


def skipped_ids(out) -> dict:
    return {s["id"]: s["why"] for s in out["skipped"]}


def added_ids(out) -> set:
    return {r["id"] for r in out["rows"]}


# -- a conversation from A applies to B ------------------------------------------

def test_a_conversation_from_a_applies_to_b_and_b_verifies(W, tmp_path,
                                                          capsys):
    dest = adopted_fork(W, tmp_path)
    cv = W["cv"]
    tick()
    newer = cv.say(W["cid"], W["coach"], [text("said there after the fork")])
    fresh = cv.open_conversation("Fresh", attributed_to=W["owner"])
    topic = cv.open_topic(fresh, "Fresh topic", attributed_to=W["owner"])
    hello = cv.say(fresh, W["owner"], [text("hello fresh")])
    src_fresh = exported(W, conversation=fresh)
    src_cid = exported(W, conversation=W["cid"])

    out = applied(dest, src_fresh, W)
    assert out["applied"] and out["skipped"] == [], out["skipped"]
    assert {fresh, topic, hello} <= added_ids(out)
    assert out["by"] == W["me"]
    assert out["origin"] == {"corpus_id": W["corpus"].corpus_id,
                             "fork_id": W["corpus"].corpus_id}
    for r in out["rows"]:
        assert r["fingerprint"] and r["origin_hash"] and r["origin_seq"]
    # the owner here established the new Conversation and Topic, nothing else
    assert set(out["established"]) == {fresh, topic}
    capsys.readouterr()
    assert brain_main(["import", dest, src_cid, "--apply",
                       "--backup-dest", str(W["backups"] / "cli")]) == 0
    said = capsys.readouterr().out
    assert said.startswith("Import applied")

    c, cv2 = open_brain(dest)
    try:
        assert c.read([newer]) and c.read([hello])
        assert c.read([fresh])[0] == W["corpus"].read([fresh])[0]
        names = [x["body"]["name"] for x in cv2.all_conversations()]
        assert names.count("Fresh") == 1
        assert c.stands(fresh)["stands"] and c.stands(topic)["stands"]
        assert not c.stands(hello)["stands"]              # Turns: never
        assert [t["turn"] for t in cv2.turns(fresh)] == [hello]
        assert cv2.turns(W["cid"])[-1]["turn"] == newer
        [first, second] = c.operational(act=IMPORT_APPLIED)
        assert first["actor"] == W["me"]
        d = first["detail"]
        assert d["manifest_sha256"] and d["counts"]["entries"] >= 5
        assert {p["there"] for p in d["participants"]} >= {W["owner"]}
        assert d["numbering"][fresh]["before"] == []
        assert d["numbering"][fresh]["after"] == [{"turn": hello,
                                                   "number": 1}]
        [est] = c.operational(act="import-established")
        assert est["actor"] == W["me"]
    finally:
        c.close()
    assert migrations.verify(dest)["ok"]                  # `brain verify`


def test_applying_the_same_file_again_is_a_no_op(W, tmp_path):
    dest = adopted_fork(W, tmp_path)
    W["cv"].say(W["cid"], W["coach"], [text("new there")])
    src = exported(W, conversation=W["cid"])
    first = applied(dest, src, W)
    assert first["applied"]
    before = _heads(dest)
    again = applied(dest, src, W)
    assert again == {"applied": False, "already": first["act"],
                     "manifest_sha256": first["manifest_sha256"],
                     "words": f"already applied by {first['act']}; nothing "
                              f"was written"}
    assert _heads(dest) == before
    assert apply_mod.describe(again).startswith("Import: already applied")


def test_a_file_from_this_brains_own_fork_is_refused(W, tmp_path):
    dest = adopted_fork(W, tmp_path)
    src = str(W["out"] / "own.zip")
    export(dest, out=src, conversation=W["cid"])
    before = _files(dest)
    with pytest.raises(ExchangeRefused, match="this Brain's own fork"):
        applied(dest, src, W)
    assert _files(dest) == before


# -- O3: both sides continued ----------------------------------------------------

def test_both_sides_continued_interleave_and_the_numbering_is_recorded(
        W, tmp_path):
    dest = adopted_fork(W, tmp_path)
    c2, cv2 = open_brain(dest)
    tick()
    here1 = cv2.say(W["cid"], W["owner"], [text("here, first")])
    tick()
    there = W["cv"].say(W["cid"], W["coach"], [text("there, between")])
    tick()
    here2 = cv2.say(W["cid"], W["owner"], [text("here, second")])
    was = {t["turn"]: t["number"] for t in cv2.turns(W["cid"])}
    c2.close()
    out = applied(dest, exported(W, conversation=W["cid"]), W)
    assert there in added_ids(out)
    m = out["numbering"][W["cid"]]
    n = was[here2]
    assert m["renumbered"] == [{"turn": here2, "before": n, "after": n + 1}]
    assert {t["turn"]: t["number"] for t in m["before"]} == was
    c2, cv2 = open_brain(dest)
    try:
        now = [{"turn": t["turn"], "number": t["number"]}
               for t in cv2.turns(W["cid"])]
        assert m["after"] == now                       # what readers number
        assert {t["turn"]: t["number"] for t in now}[there] == n
        assert {t["turn"]: t["number"] for t in now}[here1] == was[here1]
        [act] = c2.operational(act=IMPORT_APPLIED)
        assert act["detail"]["numbering"][W["cid"]]["renumbered"] == \
            m["renumbered"]
    finally:
        c2.close()
    assert migrations.verify(dest)["ok"]


# -- §5: renames (gap 1) ---------------------------------------------------------

def _conversation_names(path) -> list:
    c, cv = open_brain(path)
    try:
        return sorted(x["body"]["name"] for x in cv.all_conversations())
    finally:
        c.close()


def test_a_rename_on_both_sides_is_skipped_and_no_duplicate_appears(
        W, tmp_path):
    dest = adopted_fork(W, tmp_path)
    c2, cv2 = open_brain(dest)
    cv2.rename_conversation(W["cid"], "Beta", by=W["owner"])
    c2.close()
    before = _conversation_names(dest)
    there = W["cv"].rename_conversation(W["cid"], "Alpha", by=W["owner"])
    tick()
    turn = W["cv"].say(W["cid"], W["coach"], [text("still arrives")])
    out = applied(dest, exported(W, conversation=W["cid"]), W)
    skipped = skipped_ids(out)
    for rid in (there["version"], there["link"], there["act"]):
        assert "named 'Beta' here, named 'Alpha' there" in skipped[rid]
    assert turn in added_ids(out)
    assert _conversation_names(dest) == before
    assert "Alpha" not in before


def test_a_rename_only_there_over_what_stands_here_is_skipped(W, tmp_path):
    """Gap 1: the door would write it as a proposal, which lists as a second
    Conversation. Apply sends neither the version nor its link."""
    dest = adopted_fork(W, tmp_path)
    before = _conversation_names(dest)
    there = W["cv"].rename_conversation(W["cid"], "Alpha", by=W["owner"])
    renamed = W["cv"].rename_participant(W["coach"], "Trainer",
                                         by=W["owner"])
    out = applied(dest, exported(W, conversation=W["cid"]), W)
    skipped = skipped_ids(out)
    assert ("named 'Planning 2' here, named 'Alpha' there"
            in skipped[there["version"]])
    assert {there["link"], there["act"]} <= set(skipped)
    assert renamed["version"] in skipped and renamed["link"] in skipped
    assert out["rewritten"] == []          # nothing became a proposal
    assert _conversation_names(dest) == before
    c, cv = open_brain(dest)
    try:
        assert c.proposed_supersessions(W["cid"])["successors"]["total"] == 0
        aliases = [p["body"]["alias"] for p in cv.all_participants()]
        assert "Trainer" not in aliases and aliases.count("Coach") == 1
    finally:
        c.close()


# -- O4: an unresolved @name ------------------------------------------------------

def test_an_unresolved_name_keeps_out_only_what_names_them(W, tmp_path):
    dest = adopted_fork(W, tmp_path)
    c2, cv2 = open_brain(dest)
    mine = cv2.create_participant("Newcomer")
    c2.close()
    theirs = W["cv"].create_participant("Newcomer")
    W["cv"].join(theirs, W["cid"])
    tick()
    by_them = W["cv"].say(W["cid"], theirs, [text("from the newcomer")])
    tick()
    by_coach = W["cv"].say(W["cid"], W["coach"], [text("from the coach")])
    out = applied(dest, exported(W, conversation=W["cid"]), W)
    skipped = skipped_ids(out)
    assert "unresolved-name" in skipped[theirs]
    assert by_them in skipped and theirs in skipped[by_them]
    assert by_coach in added_ids(out)
    [p] = [p for p in out["participants"] if p["there"] == theirs]
    assert p["here"] is None and p["how"].startswith("unresolved")
    c2, cv2 = open_brain(dest)
    try:
        assert not c2.read([theirs]) and not c2.read([by_them])
        assert c2.read([mine]) and c2.read([by_coach])
    finally:
        c2.close()
    assert migrations.verify(dest)["ok"]


def _preview_renumbered(dest, src) -> dict:
    from mentis.exchange import format as fmt
    from mentis.exchange.preview import classify
    c = api.open_corpus(dest, access="read")
    try:
        plan = classify(c, fmt.read(src))
    finally:
        c.close()
    return {x.subject: x.detail["renumbered"] for x in plan.conflicts
            if x.type == "renumbering"}


def test_the_preview_renumbers_only_over_what_the_apply_writes(W, tmp_path):
    """Review ent-cca01f8347bb, finding 4: a Turn kept out (here by an
    unresolved @name, O4) renumbers nothing. The preview's "#a -> #b" is
    computed last, over the rows the apply writes, and equals what the
    apply records."""
    dest = adopted_fork(W, tmp_path)
    c2, cv2 = open_brain(dest)
    cv2.create_participant("Newcomer")
    c2.close()
    theirs = W["cv"].create_participant("Newcomer")
    W["cv"].join(theirs, W["cid"])
    c2, cv2 = open_brain(dest)
    tick()
    cv2.say(W["cid"], W["owner"], [text("here, first")])
    tick()
    by_them = W["cv"].say(W["cid"], theirs, [text("kept out")])
    tick()
    cv2.say(W["cid"], W["owner"], [text("here, second")])
    c2.close()
    tick()
    by_coach = W["cv"].say(W["cid"], W["coach"], [text("arrives last")])
    src = exported(W, conversation=W["cid"])
    shown = _preview_renumbered(dest, src)
    out = applied(dest, src, W)
    assert by_them in skipped_ids(out) and by_coach in added_ids(out)
    recorded = {cid: m["renumbered"] for cid, m in out["numbering"].items()
                if m["renumbered"]}
    assert shown == recorded == {}      # by_them alone would have moved one


def test_the_preview_renumbering_equals_what_the_apply_records(W, tmp_path):
    dest = adopted_fork(W, tmp_path)
    c2, cv2 = open_brain(dest)
    tick()
    cv2.say(W["cid"], W["owner"], [text("here, first")])
    c2.close()
    tick()
    W["cv"].say(W["cid"], W["coach"], [text("there, between")])
    c2, cv2 = open_brain(dest)
    tick()
    cv2.say(W["cid"], W["owner"], [text("here, second")])
    c2.close()
    src = exported(W, conversation=W["cid"])
    shown = _preview_renumbered(dest, src)
    out = applied(dest, src, W)
    recorded = {cid: m["renumbered"] for cid, m in out["numbering"].items()
                if m["renumbered"]}
    assert shown == recorded and len(recorded[W["cid"]]) == 1


# -- O6: a Kind that differs -------------------------------------------------------

def test_a_kind_that_differs_is_refused_with_its_dependents(W, tmp_path):
    dest = adopted_fork(W, tmp_path)
    c2 = api.open_corpus(dest)
    c2.define_kind("memo", fields=["text", "about"],
                   properties={"meaning": "a memo here"}, attributed_to="human")
    c2.close()
    c = W["corpus"]
    c.define_kind("memo", fields=["text"],
                  properties={"meaning": "a memo there"}, attributed_to="human")
    memo = c.write(kind="memo", body={"text": "hello"}, attributed_to=W["coach"])
    grounds = c.write(body={"reason": "from"}, attributed_to=W["coach"],
                      link={"from": memo, "to": W["t1"],
                            "relation": "extracted-from"})
    out = applied(dest, exported(W, item=memo), W)
    skipped = skipped_ids(out)
    assert "kind-differs" in skipped[memo] and grounds in skipped
    assert {x["type"] for x in out["conflicts"]} == {"kind-differs"}
    c2 = api.open_corpus(dest, access="read")
    try:
        assert c2.read([memo]) == [] and c2.read([grounds]) == []
    finally:
        c2.close()


# -- O7: a question answered on both sides --------------------------------------

def _answer(cv, W, label):
    reply = cv.say(W["cid"], W["owner"], [text(label)], replies_to=W["t2"])
    return cv.record_act(actor=W["owner"], act="decision-answered",
                         conversation=W["cid"], turn=W["t2"],
                         caused_by=W["question"], about=[reply],
                         detail={"reply": reply, "label": label})


def test_a_foreign_answer_to_a_question_answered_here_is_kept_out(W,
                                                                  tmp_path):
    dest = adopted_fork(W, tmp_path)
    c2, cv2 = open_brain(dest)
    here = _answer(cv2, W, "No")
    c2.close()
    there = _answer(W["cv"], W, "Yes")
    out = applied(dest, exported(W, conversation=W["cid"]), W)
    assert "answered-both" in skipped_ids(out)[there]
    [a] = out["answers"]
    assert a["kept_here"] == here and a["shown_from_there"] == there
    assert a["here_answer"]["label"] == "No"
    assert a["there_answer"]["label"] == "Yes"
    # THE REPLY THAT SAYS IT IS HELD BACK WITH IT (ent-8df809da5880): drawn
    # under the post on its own it would read as the other machine's "Yes"
    # beside the "No" kept here
    [there_act] = W["corpus"].operational(id=there)
    reply = there_act["detail"]["reply"]
    assert "answered-both" in skipped_ids(out)[reply]
    c2, cv2 = open_brain(dest)
    try:
        assert c2.operational(id=there) == []
        assert not c2.read([reply])
        s = cv2.expectation_state(W["question"])
        assert s["answer"]["act"] == here
        said = [" ".join(p.get("text", "") for p in
                         t["entry"]["body"].get("parts") or ())
                for t in cv2.turns(W["cid"])]
        assert "No" in said and "Yes" not in said
        [act] = c2.operational(act=IMPORT_APPLIED)
        assert act["detail"]["answers"] == out["answers"]
    finally:
        c2.close()


# -- ent-8c875afebee5: a reply that would answer work open here ---------------------

def _open_on_both_sides(W, tmp_path):
    """A request open at the copy, so open on both machines; then, on A, a
    Turn before its carrier's reply, the reply, a Turn said here on B, and
    one more on A."""
    cv = W["cv"]
    t9 = cv.say(W["cid"], W["owner"], [text("@Coach please do X")],
                addressed_to=[W["coach"]])
    req = cv.expect(t9, of=W["coach"], kind="result", by=W["owner"])
    dest = adopted_fork(W, tmp_path)
    cv = W["cv"]
    tick()
    first = cv.say(W["cid"], W["owner"], [text("said there first")])
    tick()
    reply = cv.say(W["cid"], W["coach"], [text("X is done")], replies_to=t9)
    [link] = [e["id"] for e in W["corpus"].links(relation="replies-to",
                                                 frm=reply)]
    tick()
    c2, cv2 = open_brain(dest)
    here = cv2.say(W["cid"], W["owner"], [text("said here")])
    assert not cv2.expectation_state(req)["response_present"]
    c2.close()
    tick()
    last = cv.say(W["cid"], W["owner"], [text("said there last")])
    assert cv.expectation_state(req)["response_present"]          # on A
    return dest, req, {"first": first, "reply": reply, "link": link,
                       "here": here, "last": last}


def test_a_carriers_reply_to_a_request_open_on_both_sides_is_held_back(
        W, tmp_path):
    """The door refuses it (ent-8b37c98bb8d5); the selection holds it back
    by the door's own rule, so the rest of the file still applies."""
    from mentis.exchange import format as fmt
    from mentis.exchange.preview import classify, describe
    dest, req, t = _open_on_both_sides(W, tmp_path)
    src = exported(W, conversation=W["cid"])
    c = api.open_corpus(dest, access="read")
    try:
        plan = classify(c, fmt.read(src))
    finally:
        c.close()
    [held] = [x for x in plan.conflicts if x.type == "answers-work-here"]
    assert held.subject == t["link"] and held.detail["post"] == t["reply"]
    assert req in held.words and "open on this Brain" in held.words
    assert {t["link"], t["reply"]} <= set(held.blocks)
    assert "answers-work-here" in describe(plan)

    out = applied(dest, src, W)
    assert out["applied"]
    skipped = skipped_ids(out)
    for rid in (t["link"], t["reply"]):
        assert "open on this Brain" in skipped[rid], skipped
    assert {t["first"], t["last"]} <= added_ids(out)
    c2, cv2 = open_brain(dest)
    try:
        assert not cv2.expectation_state(req)["response_present"]
        assert not c2.read([t["reply"]]) and not c2.read([t["link"]])
        assert c2.read([t["first"]]) and c2.read([t["last"]])
    finally:
        c2.close()
    assert migrations.verify(dest)["ok"]


def test_a_held_back_reply_renumbers_nothing_and_the_preview_agrees(
        W, tmp_path):
    dest, _, t = _open_on_both_sides(W, tmp_path)
    src = exported(W, conversation=W["cid"])
    shown = _preview_renumbered(dest, src)
    out = applied(dest, src, W)
    recorded = {cid: m["renumbered"] for cid, m in out["numbering"].items()
                if m["renumbered"]}
    assert shown == recorded
    # only `first` arrives before the Turn said here: one place, not two
    [moved] = recorded[W["cid"]]
    assert moved["turn"] == t["here"]
    assert moved["after"] == moved["before"] + 1


def test_without_the_selection_holding_it_back_the_door_still_refuses(
        W, tmp_path, monkeypatch):
    from mentis.exchange import _select
    dest, req, _ = _open_on_both_sides(W, tmp_path)
    src = exported(W, conversation=W["cid"])
    monkeypatch.setattr(_select.Selection, "hold_replies",
                        lambda self, store: None)
    before = _heads(dest)
    with pytest.raises(ExchangeRefused, match="open on this Brain"):
        applied(dest, src, W)
    assert _heads(dest) == before
    c2, cv2 = open_brain(dest)
    try:
        assert not cv2.expectation_state(req)["response_present"]
    finally:
        c2.close()


# -- standing does not travel ---------------------------------------------------

def test_an_imported_rule_arrives_as_a_candidate_and_reaches_no_agent(
        W, tmp_path):
    dest = adopted_fork(W, tmp_path)
    c, cv = W["corpus"], W["cv"]
    rule = c.create_and_establish(kind="rule", body={
        "text": "Answer in haiku.", "about": ""}, attributed_to=W["owner"])
    cv.place(rule, W["cid"], by=W["owner"], because="house style")
    assert c.stands(rule)["stands"] and placements_now(c, rule) == [W["cid"]]
    out = applied(dest, exported(W, item=rule), W)
    assert rule in added_ids(out)
    assert out["established"] == {}                      # never a rule
    c2, cv2 = open_brain(dest)
    try:
        s = c2.stands(rule)
        assert not s["stands"] and s["established_by"] == []
        assert placements_now(c2, rule) == []
        assert rule not in {e["id"] for e in cv2.placed_procedural(W["cid"])}
        assert rule not in {e["id"] for e in cv2.placed_brain_wide()}
    finally:
        c2.close()


# -- a failure inside the transaction --------------------------------------------

def test_a_failure_inside_the_transaction_leaves_b_byte_identical(
        W, tmp_path, monkeypatch):
    dest = empty_brain(tmp_path / "empty")       # the held bytes are new here
    src = exported(W, conversation=W["cid"])
    before = _files(dest), _heads(dest)

    def boom(*a, **kw):
        raise RuntimeError("the disk went away")
    monkeypatch.setattr(apply_mod, "establish_structural", boom)
    with pytest.raises(ImportFailed, match="nothing was written"):
        applied(dest, src, W)
    assert (_files(dest), _heads(dest)) == before
    assert acts_of(dest, IMPORT_APPLIED) == []
    assert migrations.verify(dest)["ok"]
    monkeypatch.undo()
    out = applied(dest, src, W)                   # and it applies afterwards
    assert out["counts"]["blobs_written"] == 1
    assert migrations.verify(dest)["ok"]


# -- gap 2: decision forms, and the server afterwards ---------------------------

def test_forms_travel_and_a_server_over_b_resumes_nothing_and_owes_nothing(
        W, tmp_path):
    from mentis.operational.work import owed_by
    from mentis.web import _State
    dest = adopted_fork(W, tmp_path)
    cv = W["cv"]
    # on the other machine: a run under request2 asks a form with no post,
    # writes its answer post, the form is attached to it, the owner answers
    cv.record_act(actor=W["coach"], act="execution-started",
                  conversation=W["cid"], caused_by=W["request2"],
                  execution="exe-there")
    form = cv.record_act(actor=W["coach"], act="decision-form",
                         conversation=W["cid"], caused_by=W["request2"],
                         execution="exe-there", detail={"questions": 1})
    question = cv.expect(None, of=W["owner"], kind="decision", by=W["coach"],
                         caused_by=W["request2"], conversation=W["cid"],
                         detail={"form": form, "index": 0,
                                 "question": "Merge it?",
                                 "options": [{"label": "Yes"},
                                             {"label": "No"}]})
    tick()
    post = cv.say(W["cid"], W["coach"], [text("the run's answer")])
    assert cv.attach_pending_forms("exe-there", post, by=W["coach"]) == [form]
    tick()
    reply = cv.say(W["cid"], W["owner"], [text("Yes")], replies_to=post)
    answer = cv.record_act(actor=W["owner"], act="decision-answered",
                           conversation=W["cid"], turn=post,
                           caused_by=question, about=[reply],
                           detail={"reply": reply, "label": "Yes"})
    # a second form whose question is still open there: not carried
    form2 = cv.record_act(actor=W["coach"], act="decision-form",
                          conversation=W["cid"], turn=post,
                          caused_by=W["request2"], execution="exe-there",
                          detail={"questions": 1})
    open_q = cv.expect(post, of=W["owner"], kind="decision", by=W["coach"],
                       caused_by=W["request2"], detail={
                           "form": form2, "index": 0, "question": "Later?"})
    out = applied(dest, exported(W, conversation=W["cid"]), W)
    added, skipped = added_ids(out), skipped_ids(out)
    assert {form, question, answer, post, reply} <= added
    assert "decision form not carried" in skipped[form2]
    assert open_q in skipped

    c2, cv2 = open_brain(dest)
    try:
        [f] = c2.operational(id=form)
        assert f["execution"] == "exe-there"          # kept as recorded
        [att] = [a for a in c2.operational(caused_by=form)
                 if a["act"] == "decision-form-attached"]
        assert att["execution"] == "exe-there" and att["turn"] == post
        assert c2.operational(execution="exe-there") == [f, att]
        assert not any(a["act"] == "execution-started"
                       for a in c2.operational(execution="exe-there"))
        drawn = cv2.decision_form(form)
        assert drawn["post"] == post and drawn["closed"]
        assert cv2.expectation_state(question)["answer"]["act"] == answer
        acts_before = {a["id"] for a in c2.operational()}
    finally:
        c2.close()
    assert migrations.verify(dest)["ok"]

    st = _State(dest)                               # a server starting over B
    try:
        new = [a for a in st.cv.history() if a["id"] not in acts_before]
        imported_ids = {form, question, answer, att["id"], W["request2"]}
        for a in new:
            assert a.get("execution") != "exe-there", a
            assert a.get("caused_by") not in imported_ids, a
            assert not set(a.get("about") or ()) & imported_ids, a
        assert not [a for a in new if a["act"] == "work-resumed"]
        assert all(r["execution"] != "exe-there"
                   for r in st.cv.open_runs())
        owed = owed_by(st.cv, W["owner"], limit=100)["owed"]
        assert not {o["expectation"] for o in owed} & {question, open_q}
    finally:
        st.corpus.close()


# -- a row the door rewrote, carried again (ent-4b4f11a83d1d) ---------------------

def _supersede(W, old, text_) -> dict:
    """On the origin: the next version of a rule and its `supersedes` link,
    as an approved replacement leaves them."""
    c = W["corpus"]
    new = c.write(kind="rule", body={"text": text_, "about": ""},
                  attributed_to=W["owner"])
    link = c.write(body={}, attributed_to=W["owner"],
                   link={"from": new, "to": old,
                         "relation": c.superseding_relation()})
    return {"version": new, "link": link}

def test_a_row_written_here_as_a_proposal_reads_as_already_here_next_time(
        W, tmp_path):
    """A foreign supersession of a rule that stands here is written as a
    proposal (the door's rewrite). A later, different export from the same
    origin carries that row again as the origin wrote it: it is already
    here, rewritten on import -- not damage -- and the import applies with
    no duplicate."""
    rule = W["corpus"].create_and_establish(kind="rule", body={
        "text": "Answer briefly.", "about": ""}, attributed_to=W["owner"])
    dest = adopted_fork(W, tmp_path)
    v2 = _supersede(W, rule, "Answer very briefly.")
    first = applied(dest, exported(W, item=rule), W)
    [rw] = first["rewritten"]
    assert rw["target"] == rule and rw["id"] == v2["link"]
    [row] = [r for r in first["rows"] if r["id"] == v2["link"]]
    assert row["written_as"] == rw["written_as"]
    assert row["written_fingerprint"] != row["fingerprint"]

    tick()
    v3 = _supersede(W, v2["version"], "One line.")
    src = exported(W, item=rule)
    from mentis.exchange import format as fmt
    from mentis.exchange.preview import classify
    c = api.open_corpus(dest, access="read")
    try:
        plan = classify(c, fmt.read(src))
    finally:
        c.close()
    assert plan.refused == []
    p = plan.row(v2["link"])
    assert p.state == "identical" and "rewritten on import" in p.reason
    second = applied(dest, src, W)                  # no longer "corrupt"
    assert second["applied"] and v3["version"] in added_ids(second)
    assert v2["link"] not in added_ids(second)
    c = api.open_corpus(dest, access="read")
    try:
        assert len(c.read([v2["link"]])) == 1
        assert c.verify_chain()["intact"]
    finally:
        c.close()
    assert migrations.verify(dest)["ok"]


def test_a_rewritten_row_that_differs_any_other_way_is_still_corrupt(
        W, tmp_path):
    """The record of a rewrite excuses exactly the row it wrote: the same
    id arriving with yet another body is damage, as before."""
    import json as _json
    import zipfile
    rule = W["corpus"].create_and_establish(kind="rule", body={
        "text": "Answer briefly.", "about": ""}, attributed_to=W["owner"])
    dest = adopted_fork(W, tmp_path)
    v2 = _supersede(W, rule, "Answer very briefly.")
    src = exported(W, item=rule)
    assert applied(dest, src, W)["rewritten"]
    with zipfile.ZipFile(src) as z:
        members = {n: z.read(n) for n in z.namelist()}
    rows = [_json.loads(x) for x in
            members["entries.jsonl"].decode().splitlines() if x]
    for r in rows:
        if r["id"] == v2["link"]:
            r["recorded_at"] = r["recorded_at"] + 1
    from mentis.exchange import format as fmt
    from mentis.exchange.preview import CORRUPT, _Classifier
    from mentis.exchange._rows import one_read
    x = fmt.read(src)
    x.entries = rows
    c = api.open_corpus(dest, access="read")
    try:
        with one_read(c._store) as r:
            k = _Classifier(r, x)
            k.rows()
        assert k.plans[v2["link"]].state == CORRUPT
    finally:
        c.close()


# -- nobody else writing (review ent-cca01f8347bb, finding 3) ----------------------

_SERVER = r"""
import sys
from mentis.spine import brainlock
import mentis.api as api
lock = brainlock.serve(sys.argv[1], port=1)
c = api.open_corpus(sys.argv[1])
print("serving", flush=True)
sys.stdin.read()
c.close()
lock.release()
"""


def test_an_apply_while_mentis_serves_the_brain_is_refused(W, tmp_path):
    """A separate server process serves B: the apply refuses, says to stop
    Mentis first, and writes nothing; once it stops, the same file applies."""
    import os
    import subprocess
    import sys
    dest = adopted_fork(W, tmp_path)
    src = exported(W, conversation=W["cid"])
    before = _heads(dest)
    server = subprocess.Popen(
        [sys.executable, "-c", _SERVER, dest], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        assert server.stdout.readline().strip() == "serving"
        with pytest.raises(ExchangeRefused, match="Stop Mentis first"):
            applied(dest, src, W)
        # the server's own open leaves its -wal and -shm; the record is as
        # it was
        assert _heads(dest) == before
        assert acts_of(dest, IMPORT_APPLIED) == []
    finally:
        server.communicate("", timeout=60)
    assert applied(dest, src, W)["applied"]


def test_an_apply_while_another_opener_holds_the_brain_is_refused(W,
                                                                   tmp_path):
    dest = adopted_fork(W, tmp_path)
    src = exported(W, conversation=W["cid"])
    holder = api.open_corpus(dest)
    try:
        with pytest.raises(ExchangeRefused, match="open elsewhere"):
            applied(dest, src, W)
    finally:
        holder.close()
    assert acts_of(dest, IMPORT_APPLIED) == []


def test_a_write_here_during_the_backup_is_planned_against(W, tmp_path,
                                                           monkeypatch):
    """The Plan is made again inside the transaction that appends: an edit
    made here while the backup was taken is a diverged line, reported, and
    the other machine's edit is not written beside it."""
    from mentis.conversation import versions
    from mentis.spine import backup as _backup
    dest = adopted_fork(W, tmp_path)
    versions.edit(W["cv"], W["t1"], by=W["owner"], text="edited THERE")
    src = exported(W, conversation=W["cid"])
    real = _backup.backup

    def backup_while_the_owner_edits_here(root, **kw):
        out = real(root, **kw)
        c, cv = open_brain(dest)
        try:
            versions.edit(cv, W["t1"], by=W["owner"], text="edited HERE")
        finally:
            c.close()
        return out
    monkeypatch.setattr(_backup, "backup", backup_while_the_owner_edits_here)
    out = applied(dest, src, W)
    assert any(s["why"].startswith("diverged-line") for s in out["skipped"])
    c = api.open_corpus(dest, access="read")
    try:
        sup = c.superseding_relation()
        assert len(c.links(relation=sup, to=W["t1"])) == 1
    finally:
        c.close()
    assert migrations.verify(dest)["ok"]


# -- RP5: R1 and R2 held back by apply -----------------------------------------

def test_R1_reply_link_attributed_to_carrier_is_held_back_by_apply(W, tmp_path):
    """A Turn by someone else with a replies-to link attributed to the carrier:
    held back by apply as answers-work-here while the rest applies."""
    from mentis.exchange import format as fmt
    from mentis.exchange.preview import classify, describe
    cv = W["cv"]
    t9 = cv.say(W["cid"], W["owner"], [text("@Coach do task Z")], addressed_to=[W["coach"]])
    req = cv.expect(t9, of=W["coach"], kind="result", by=W["owner"])
    dest = adopted_fork(W, tmp_path)
    cv = W["cv"]
    tick()
    reply = cv.say(W["cid"], W["owner"], [text("done by non-carrier")])
    link = W["corpus"].write(
        body={"reason": "replies to this turn"},
        attributed_to=W["coach"], written_by=W["coach"],
        link={"from": reply, "to": t9, "relation": "replies-to"})
    last = cv.say(W["cid"], W["owner"], [text("unrelated later turn")])

    src = exported(W, conversation=W["cid"])
    c = api.open_corpus(dest, access="read")
    try:
        plan = classify(c, fmt.read(src))
    finally:
        c.close()
    [held] = [x for x in plan.conflicts if x.type == "answers-work-here"]
    assert held.subject == link and held.detail["post"] == reply
    assert req in held.words and "open on this Brain" in held.words
    assert {link, reply} <= set(held.blocks)
    assert "answers-work-here" in describe(plan)

    out = applied(dest, src, W)
    assert out["applied"]
    skipped = skipped_ids(out)
    for rid in (link, reply):
        assert "open on this Brain" in skipped[rid], skipped
    assert last in added_ids(out)

    c2, cv2 = open_brain(dest)
    try:
        assert not cv2.expectation_state(req)["response_present"]
        assert not c2.read([reply]) and not c2.read([link])
        assert c2.read([last])
    finally:
        c2.close()
    assert migrations.verify(dest)["ok"]


def test_R2_marked_ready_is_held_back_by_apply(W, tmp_path, monkeypatch):
    """Marked-ready response-set entries answering an input open here are
    held back by apply as answers-work-here while the rest applies."""
    from mentis.conversation import render_check as R
    from mentis.conversation import responses as Rs
    from mentis.exchange import format as fmt
    from mentis.exchange.preview import classify, describe
    from mentis.operational.work import owed_by
    monkeypatch.setattr(R, "answers", lambda *a, **k: {
        "checked": False, "engine_absent": True, "why_not": "probe"})
    cv = W["cv"]
    form_text = ("```form version=1 name=leave\n"
                 "who: text \"Your name\" required\n```")
    post = cv.say(W["cid"], W["coach"], [text(form_text)])
    sid = Rs.open_set(cv, post, block="leave", by=W["coach"])["set"]
    exp = cv.expect(post, of=W["me"], kind="input", by=W["coach"],
                    caused_by=W["request2"],
                    detail={"response_set": sid, "ready_before": []})
    dest = adopted_fork(W, tmp_path)
    cv = W["cv"]
    tick()
    Rs.answer(cv, sid, field="who", value="Brian", by=W["me"])
    mr = Rs.mark_ready(cv, sid, by=W["me"])
    mrid = next(v for k, v in mr.items()
                if isinstance(v, str) and v.startswith("ent-") and k != "set")

    src = exported(W, item=mrid)
    c = api.open_corpus(dest, access="read")
    try:
        plan = classify(c, fmt.read(src))
    finally:
        c.close()
    conflicts = [x for x in plan.conflicts if x.type == "answers-work-here"]
    assert conflicts, "expected answers-work-here conflict"
    assert any(mrid in x.words or mrid == x.subject for x in conflicts)

    out = applied(dest, src, W)
    assert out["applied"]
    skipped = skipped_ids(out)
    assert mrid in skipped

    c2, cv2 = open_brain(dest)
    try:
        after = cv2.expectation_state(exp)
        assert not after["response_present"]
        owed = [o["expectation"] for o in owed_by(cv2, W["me"], limit=50)["owed"]]
        assert exp in owed
        assert not c2.read([mrid])
    finally:
        c2.close()
    assert migrations.verify(dest)["ok"]
