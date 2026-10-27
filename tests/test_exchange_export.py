"""Export: the closure of a Conversation, a Turn and an item (design
adm-6cebfabd6e9c §2, O2), and that exporting writes nothing.

Every Brain here is disposable, made under the test's own tmp_path. What is
pinned:

  * each of the three closures holds exactly what §2 lists, and no row of
    any of them is an `establishes`, `scoped-to` or `carries-intake` link;
    standing is in evidence.json only;
  * run and dispatch acts never travel; the meaning-giving acts do;
  * references not carried are stubs, never rows;
  * held bytes travel by digest;
  * the export writes NOTHING: the Brain's files and its stream heads are
    the same before and after, and it runs beside an open writer;
  * the file goes outside every Brain.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time

import pytest

import mentis.api as api
from mentis import artifacts
from mentis.brain.__main__ import main as brain_main
from mentis.conversation import text, versions
from mentis.conversation.anchors import create_anchor, react
from mentis.exchange import ExchangeRefused, format as fmt
from mentis.exchange.export import export
from mentis.exchange.identity import identity
from mentis.spine import brainlock
from tests._brains import new_brain


def open_brain(path):
    corpus = api.open_corpus(str(path))
    return corpus, api.conversations(corpus)


def tick():
    """Two writes a test orders by time are never in one clock tick."""
    time.sleep(0.005)


def build(path) -> dict:
    """A Brain holding one Conversation with everything §2 names, beside
    things that must NOT travel with it."""
    new_brain(path)
    c, cv = open_brain(path)
    W = {"path": str(path), "corpus": c, "cv": cv}
    owner = W["owner"] = cv.create_participant("brian")
    coach = W["coach"] = cv.create_participant("Coach")
    stranger = W["stranger"] = cv.create_participant("Stranger")
    cid = W["cid"] = cv.open_conversation("Planning", attributed_to=owner)
    cv.join(owner, cid)
    cv.join(coach, cid)
    W["topic"] = cv.open_topic(cid, "Design", attributed_to=owner)
    tick()
    W["t1"] = cv.say(cid, owner, [text("first")], addressed_to=[coach])
    tick()
    W["t2"] = cv.say(cid, coach, [text("second")], replies_to=W["t1"])
    cv.assign_topic(W["t2"], W["topic"], attributed_to=coach)
    W["t2v"] = versions.edit(cv, W["t2"], by=coach,
                             text="second, edited")["version"]
    tick()
    W["t3"] = cv.say(cid, owner, [text("third, then deleted")])
    W["t3del"] = versions.delete(cv, W["t3"], by=owner)["deletion"]
    W["anchor"] = create_anchor(cv, {"version": W["t1"], "type": "version"},
                                by=coach)["anchor"]
    W["reaction"] = react(cv, W["anchor"], {"token": "+1"},
                          by=owner)["reaction"]
    held = artifacts.hold(c, cv, b"bytes the owner attached", act="artifact-"
                          "submitted", actor=owner, source=f"submission:{owner}",
                          door="human-ingress", conversation=cid)
    W["adm"], W["digest"] = held["admission"], held["digest"]
    tick()
    W["t4"] = cv.say(cid, owner, [artifacts.part(W["adm"], corpus=c)])
    W["rename"] = cv.rename_conversation(cid, "Planning 2", by=owner)
    W["addressed"] = cv.address_turn(W["t1"], owner, by=coach)
    # a decision form on t2, one question
    W["request"] = cv.expect(W["t1"], of=coach, kind="result", by=owner)
    W["form"] = cv.record_act(actor=coach, act="decision-form",
                              conversation=cid, turn=W["t2"],
                              caused_by=W["request"],
                              detail={"questions": 1})
    W["question"] = cv.expect(W["t2"], of=owner, kind="decision", by=coach,
                              caused_by=W["request"], detail={
                                  "form": W["form"], "index": 0,
                                  "question": "Ship it?",
                                  "options": [{"label": "Yes"},
                                              {"label": "No"}]})
    # run acts that must never travel
    W["run"] = cv.record_act(actor=coach, act="execution-started",
                             conversation=cid, turn=W["t2"],
                             caused_by=W["request"], execution="exe-1")
    # in-force material placed on the Conversation: never carried
    W["rule"] = c.create_and_establish(kind="rule", body={
        "text": "Keep it short.", "about": ""}, attributed_to=owner)
    cv.place(W["rule"], cid, by=owner, because="house style")
    # another Conversation: a Turn there replies to t1 (inbound, not
    # carried), and a Turn here replies to one there (a stub)
    W["other"] = cv.open_conversation("Elsewhere", attributed_to=stranger)
    W["far"] = cv.say(W["other"], stranger, [text("far away")])
    W["far_reply"] = cv.say(W["other"], stranger, [text("about t1")],
                            replies_to=W["t1"])
    tick()
    W["t5"] = cv.say(cid, coach, [text("about the far post")],
                     replies_to=W["far"])
    # an item grounded on t1, established, with its own version line
    W["finding"] = c.create_and_establish(kind="finding", body={
        "text": "It works."}, attributed_to=coach)
    c.write(body={"reason": "seen in"}, attributed_to=coach,
            link={"from": W["finding"], "to": W["t1"],
                  "relation": "extracted-from"})
    return W


@pytest.fixture
def W(tmp_path):
    W = build(tmp_path / "origin")
    W["out"] = tmp_path / "out"
    W["out"].mkdir()
    yield W
    W["corpus"].close()


def run_export(W, name="x.zip", **kw):
    path = str(W["out"] / name)
    export(W["path"], out=path, **kw)
    return fmt.read(path)


def ids(rows) -> set:
    return {r["id"] for r in rows}


def links_of(x, relation) -> list:
    return [e for e in x.entries if (e.get("link") or {}).get("relation")
            == relation]


def acts_named(x) -> set:
    return {a["act"] for a in x.acts}


NEVER = {"establishes", "scoped-to", "carries-intake"}


def assert_no_standing_rows(x):
    rels = {(e.get("link") or {}).get("relation") for e in x.entries}
    assert not rels & NEVER, rels & NEVER
    assert not acts_named(x) & {"execution-started", "result-returned",
                                "delivery-failed", "work-awaited",
                                "work-resumed", "material-placed"}


# -- the Conversation closure -----------------------------------------------

def test_a_conversation_carries_exactly_its_closure(W):
    x = run_export(W, conversation=W["cid"])
    got = ids(x.entries)
    rename = W["rename"]
    expected_nodes = {
        W["cid"], rename["version"],                     # name line
        W["t1"], W["t2"], W["t2v"], W["t3"], W["t3del"], W["t4"], W["t5"],
        W["topic"], W["owner"], W["coach"],              # members, authors
        W["anchor"], W["reaction"], W["adm"]}
    nodes = {e["id"] for e in x.entries if not e.get("link")}
    assert nodes == expected_nodes, (nodes ^ expected_nodes)
    # nothing of the other Conversation, the rule, the finding or the
    # stranger -- the inbound reply from there is not carried either
    for absent in (W["other"], W["far"], W["far_reply"], W["rule"],
                   W["finding"], W["stranger"]):
        assert absent not in got
    assert not [e for e in x.entries if (e.get("link") or {}).get("from")
                == W["far_reply"]]
    # the thread links among them
    assert {e["link"]["from"] for e in links_of(x, "in-conversation")} == {
        W["t1"], W["t2"], W["t3"], W["t4"], W["t5"]}
    assert {(e["link"]["from"], e["link"]["to"])
            for e in links_of(x, "replies-to")} == {
        (W["t2"], W["t1"]), (W["t5"], W["far"])}
    assert {e["link"]["from"] for e in links_of(x, "participates-in")} == {
        W["owner"], W["coach"]}
    assert [e["link"]["from"] for e in links_of(x, "topic-of")] == [W["topic"]]
    assert [e["link"]["from"] for e in links_of(x, "about-topic")] == [W["t2"]]
    assert [e["link"]["from"] for e in links_of(x, "anchors-in")] == [
        W["anchor"]]
    assert [e["link"]["from"] for e in links_of(x, "reacts-to")] == [
        W["reaction"]]
    sup = {(e["link"]["from"], e["link"]["to"])
           for e in links_of(x, "supersedes")}
    assert {(W["t2v"], W["t2"]), (W["t3del"], W["t3"]),
            (rename["version"], W["cid"])} <= sup
    assert_no_standing_rows(x)
    # the meaning-giving acts, and only those
    assert acts_named(x) == {"conversation-renamed", "turn-addressed",
                             "decision-form", "expectation-recorded"}
    assert ids(x.acts) == {rename["act"], W["addressed"], W["form"],
                           W["question"]}
    # held bytes by digest
    assert x.blob_digests == [W["digest"]]
    assert x.blob(W["digest"]) == b"bytes the owner attached"
    # stubs: the far post, and the request the form hangs off -- never rows
    stubs = {s["id"]: s for s in x.stubs}
    assert W["far"] in stubs and stubs[W["far"]]["kind"] == "contribution"
    assert stubs[W["far"]]["label"] == "far away"
    assert W["request"] in stubs and stubs[W["request"]]["kind"] == "act"
    assert not set(stubs) & got


def test_standing_travels_only_as_evidence(W):
    x = run_export(W, conversation=W["cid"])
    ev = {e["entry"]: e for e in x.evidence}
    # created and established: the Conversation, its Topic, Participants
    assert ev[W["cid"]]["established"][0]["by"] == W["owner"]
    assert ev[W["owner"]]["established"]
    assert ev[W["cid"]]["superseded_by"] == [W["rename"]["version"]]
    # Turns are never established; t3 was deleted
    assert W["t1"] not in ev
    assert ev[W["t3"]]["superseded_by"] == [W["t3del"]]


def test_the_manifest_names_its_origin_ledger_and_members(W):
    x = run_export(W, conversation=W["cid"], by="brian")
    m = x.manifest
    assert m["origin"] == {**identity(W["corpus"]),
                           "marker_corpus_id": W["corpus"].corpus_id}
    assert m["origin"]["fork_id"] == W["corpus"].corpus_id   # never forked
    assert m["marks"] == [{"id": W["cid"], "kind": "conversation"}]
    assert m["by"] == "brian"
    assert m["ledger"] and all(r["checksum"] for r in m["ledger"])
    assert set(m["members"]) == set(fmt.MEMBERS) | {
        fmt.blob_member(W["digest"])}
    assert m["counts"]["entries"] == len(x.entries)
    # every row carries its place on the origin's chain, as evidence
    assert all(e["origin_seq"] and e["origin_hash"] for e in x.entries)
    # definitions: every (name, version) the rows name, with its body hash
    named = {((e.get("definition") or {}).get("name"),
              (e.get("definition") or {}).get("version")) for e in x.entries}
    assert {(d["name"], d["version"]) for d in x.definitions} == named
    for d in x.definitions:
        if d.get("fixed"):                 # the Admission shape: no row
            assert d["name"] == "admission"
            continue
        assert d["body_sha256"] == fmt.body_sha256(d["body"])


def test_the_fingerprint_is_the_row_without_its_chain(W):
    x = run_export(W, conversation=W["cid"])
    row = next(e for e in x.entries if e["id"] == W["t1"])
    from mentis.spine.store import Store
    st = W["corpus"]._store
    raw = dict(st._rows("SELECT * FROM entry WHERE id = ?", (W["t1"],))[0])
    assert fmt.fingerprint(raw) == fmt.fingerprint(row)
    # it ignores where the row sits on a chain ...
    moved = {**row, "origin_seq": 1, "origin_hash": "0" * 64}
    assert fmt.fingerprint(moved) == fmt.fingerprint(row)
    # ... and nothing else
    assert fmt.fingerprint({**row, "attributed_to": "x"}) != \
        fmt.fingerprint(row)
    act = x.acts[0]
    raw_act = dict(st._rows("SELECT * FROM operational WHERE id = ?",
                            (act["id"],))[0])
    assert fmt.fingerprint(raw_act) == fmt.fingerprint(act)
    assert Store.CHAINED["entry"]


# -- the Turn and item closures ---------------------------------------------

def test_a_single_turn_carries_its_line_its_home_and_nothing_else(W):
    x = run_export(W, turn=W["t2"])
    nodes = {e["id"] for e in x.entries if not e.get("link")}
    # its version line, its home (with the name line), its Topic, authors
    assert nodes == {W["t2"], W["t2v"], W["cid"], W["rename"]["version"],
                     W["topic"], W["coach"], W["owner"]}
    links = {(e["link"]["relation"], e["link"]["from"], e["link"]["to"])
             for e in x.entries if e.get("link")}
    assert ("in-conversation", W["t2"], W["cid"]) in links
    assert ("replies-to", W["t2"], W["t1"]) in links       # parent: a stub
    assert ("about-topic", W["t2"], W["topic"]) in links
    assert ("topic-of", W["topic"], W["cid"]) in links
    assert ("supersedes", W["t2v"], W["t2"]) in links
    # no other Turn, no member link, no anchor on another Turn
    assert not {W["t1"], W["t3"], W["t4"], W["anchor"]} & ids(x.entries)
    assert not [r for r in links if r[0] == "participates-in"]
    assert {s["id"] for s in x.stubs} >= {W["t1"]}
    assert_no_standing_rows(x)
    # its form travels with it; the Turn's addressing (on t1) does not
    assert acts_named(x) == {"conversation-renamed", "decision-form",
                             "expectation-recorded"}
    assert x.manifest["marks"] == [{"id": W["t2"], "kind": "turn"}]


def test_a_turn_with_anchors_carries_them(W):
    x = run_export(W, turn=W["t1"])
    got = ids(x.entries)
    assert {W["anchor"], W["reaction"]} <= got
    assert W["addressed"] in ids(x.acts)
    # the replies to it live elsewhere and are not carried
    assert W["t2"] not in got and W["far_reply"] not in got


def test_an_item_carries_its_line_and_grounds_never_its_standing(W):
    c = W["corpus"]
    newer = versions.edit(W["cv"], W["finding"], by=W["coach"],
                          fields={"text": "It works, mostly."})
    x = run_export(W, item=W["finding"])
    nodes = {e["id"] for e in x.entries if not e.get("link")}
    # the item, its next version, its author: its version line travels ...
    assert nodes == {W["finding"], newer["version"], W["coach"]}
    assert [(e["link"]["from"], e["link"]["to"])
            for e in links_of(x, "supersedes")] == [
        (newer["version"], W["finding"])]
    grounds = links_of(x, "extracted-from")
    # an edit rests on what it revises, so both versions name t1
    assert {(g["link"]["from"], g["link"]["to"]) for g in grounds} == {
        (W["finding"], W["t1"]), (newer["version"], W["t1"])}
    assert W["t1"] not in ids(x.entries)
    assert W["t1"] in {s["id"] for s in x.stubs}
    # ... and the standing of either version only as evidence
    assert_no_standing_rows(x)
    ev = {e["entry"]: e for e in x.evidence}
    assert ev[W["finding"]]["established"]
    assert ev[W["finding"]]["superseded_by"] == [newer["version"]]
    assert bool(ev.get(newer["version"], {}).get("established")) == \
        bool(c.stands(newer["version"])["established_by"])


def test_the_wrong_kind_of_root_is_refused_in_words(W):
    with pytest.raises(ExchangeRefused, match="not a conversation"):
        run_export(W, conversation=W["t1"])
    with pytest.raises(ExchangeRefused, match="export it with --turn"):
        run_export(W, "b.zip", item=W["t1"])
    with pytest.raises(ExchangeRefused, match="later version"):
        run_export(W, "c.zip", conversation=W["rename"]["version"])
    with pytest.raises(ExchangeRefused, match="not in this Brain"):
        run_export(W, "d.zip", item="ent-000000000000")
    assert os.listdir(W["out"]) == []


# -- it writes nothing --------------------------------------------------------

def _files(root) -> dict:
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            if n in brainlock.LOCK_FILES:
                continue
            p = os.path.join(d, n)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root)] = hashlib.sha256(
                    f.read()).hexdigest()
    return out


def _heads(path):
    c = api.open_corpus(path, access="read")
    try:
        return c.verify_chain()["streams"], c.advance()
    finally:
        c.close()


def test_the_export_writes_nothing_to_the_brain(W):
    W["corpus"].close()
    before_files, before_heads = _files(W["path"]), _heads(W["path"])
    for flag, root in (("conversation", W["cid"]), ("turn", W["t2"]),
                       ("item", W["finding"])):
        run_export(W, f"{flag}.zip", **{flag: root})
    assert _files(W["path"]) == before_files
    assert _heads(W["path"]) == before_heads
    W["corpus"] = api.open_corpus(W["path"])          # for the teardown


def test_the_export_runs_beside_an_open_writer(W):
    # the fixture's writable Corpus stays open, as a server's would
    assert not W["corpus"].read_only
    x = run_export(W, conversation=W["cid"])
    assert W["cid"] in ids(x.entries)
    W["cv"].say(W["cid"], W["owner"], [text("still writable")])


def test_the_file_goes_outside_every_brain(W):
    with pytest.raises(ExchangeRefused, match="inside the Brain"):
        export(W["path"], out=os.path.join(W["path"], "x.zip"),
               conversation=W["cid"])
    with pytest.raises(ExchangeRefused, match="inside the Brain"):
        os.makedirs(os.path.join(W["path"], "sub"), exist_ok=True)
        export(W["path"], out=os.path.join(W["path"], "sub", "x.zip"),
               conversation=W["cid"])
    run_export(W, conversation=W["cid"])
    with pytest.raises(ExchangeRefused, match="already exists"):
        run_export(W, conversation=W["cid"])


def test_the_command_line_exports(W, capsys):
    out = str(W["out"] / "cli.zip")
    code = brain_main(["export", W["path"], "--conversation", W["cid"],
                       "--out", out])
    assert code == 0, capsys.readouterr()
    assert fmt.read(out).manifest["marks"][0]["id"] == W["cid"]
    code = brain_main(["export", W["path"], "--turn", W["cid"], "--out",
                       str(W["out"] / "bad.zip")])
    assert code == 2
    assert "export refused" in capsys.readouterr().err


def fork(W, tmp_path, name="fork") -> str:
    """A closed copy of the origin Brain: same corpus_id, its own chain."""
    W["corpus"].close()
    dest = str(tmp_path / name)
    shutil.copytree(W["path"], dest,
                    ignore=shutil.ignore_patterns(*brainlock.LOCK_FILES))
    W["corpus"] = api.open_corpus(W["path"])
    W["cv"] = api.conversations(W["corpus"])
    return dest
