"""THE BRAIN OVERVIEW (`GET /api/brain/overview`): what it counts, and that it
counts it once, from the record and the disk, and writes nothing.

A disposable fixture Brain behind a real HTTP server (`tests/_loop.py`'s
`world`). Every number asserted here is one the test constructed: so many
conversations and posts, so many records of each Kind and status, the same
bytes attached twice, a source connected from outside the Brain, a file the
owner purged.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from mentis import api, artifacts
from mentis.spine import held
from mentis.web import brain_overview

from tests._loop import world, post, get  # noqa: F401


@pytest.fixture
def me(world):
    return world["who"]["@brian"]


def _overview(world, measure=True):
    return get(world, "/api/brain/overview" + ("?measure=1" if measure else ""))


def _hold(world, me, data, name="note.txt"):
    st = world["state"]
    return artifacts.hold(st.corpus, st.cv, data, act="artifact-submitted", actor=me,
                          source=f"submission:{me}", door="human-ingress", claimed_name=name)


def _statuses(rows):
    return {r["status"]: r["count"] for r in rows}


def _kinds(rows):
    return {r["kind"]: r["count"] for r in rows}


def test_conversations_and_posts_are_what_the_conversation_list_says(world, me):
    before = _overview(world)["counts"]
    a = post(world, "/api/conversations", {"name": "Counted one"})["conversation"]
    post(world, "/api/conversations", {"name": "Counted two"})
    for words in ("first", "second", "third"):
        post(world, f"/api/conversations/{a}/turns", {"author": me, "text": words})
    after = _overview(world)["counts"]
    assert after["conversations"]["total"] == before["conversations"]["total"] + 2
    assert after["posts"] == before["posts"] + 3
    listed = get(world, "/api/conversations")["conversations"]
    assert after["conversations"]["total"] == len(listed)
    assert after["posts"] == sum(c["turns"] for c in listed)


def test_records_by_kind_and_standing_match_the_brain_browser(world, me):
    made = []
    for kind, words in (("rule", "Deploy to TEST first."), ("rule", "Ask before a restart."),
                        ("decision", "Releases are tagged."), ("note", "The deploy was refused."),
                        ("note", "A second observation.")):
        made.append(post(world, "/api/entries", {"kind": kind, "body": {"text": words},
                                                 "attributed_to": me, "establish": False})["entry"])
    post(world, f"/api/entries/{made[0]}/establish", {"attributed_to": me, "because": "the owner said so"})
    got = _overview(world)["counts"]

    for view, part in (("knowledge", "knowledge"), ("governing", "governing")):
        browse = get(world, f"/api/ladder/browse?view={view}&limit=1")
        assert got[part]["total"] == browse["total"], view
        assert _kinds(got[part]["kinds"]) == {k["kind"]: k["count"] for k in browse["kinds"]}, view
        assert got[part]["past"] == browse["past"], view
        # every current record has exactly one standing
        assert sum(_statuses(got[part]["standing"]).values()) == got[part]["total"]
    for status in ("adopted", "recorded", "adoption_requested", "declined"):
        browse = get(world, f"/api/ladder/browse?view=governing&status={status}&limit=1")
        assert _statuses(got["governing"]["standing"])[status] == browse["total"], status
    assert _statuses(got["governing"]["standing"])["adopted"] >= 1
    assert _kinds(got["knowledge"]["kinds"])["note"] >= 2


def test_a_file_referenced_twice_is_one_file_and_its_bytes_count_once(world, me):
    before = _overview(world)
    data = b"the same bytes, attached twice " * 40
    first = _hold(world, me, data)
    second = _hold(world, me, data, name="again.txt")
    assert first["digest"] == second["digest"] and first["admission"] != second["admission"]
    _hold(world, me, b"other bytes")
    after = _overview(world)

    f0, f1 = before["counts"]["files"], after["counts"]["files"]
    assert f1["references"] == f0["references"] + 3
    assert f1["unique"] == f0["unique"] + 2
    assert f1["recorded_bytes"] == f0["recorded_bytes"] + len(data) + len(b"other bytes")
    s0, s1 = before["storage"]["files"], after["storage"]["files"]
    assert s1["on_disk"] == s0["on_disk"] + 2
    assert s1["bytes"] == s0["bytes"] + len(data) + len(b"other bytes")
    assert s1["missing"] == 0 and s1["unnamed"] == s0["unnamed"]
    attached = next(o for o in f1["origins"] if o["group"] == "attached")
    assert attached["references"] >= 3 and attached["unique"] >= 2
    # the portable estimate carries the bytes once
    p0 = next(p for p in before["portable"]["parts"] if p["part"] == "files")
    p1 = next(p for p in after["portable"]["parts"] if p["part"] == "files")
    assert p1["bytes"] == p0["bytes"] + len(data) + len(b"other bytes")
    assert p1["count"] == p0["count"] + 2


def test_the_portable_estimate_is_its_parts_and_is_what_a_portable_backup_writes(world, me, tmp_path):
    _hold(world, me, b"carried by a backup" * 100)
    got = _overview(world)
    parts = {p["part"]: p for p in got["portable"]["parts"]}
    assert got["portable"]["bytes"] == sum(p["bytes"] for p in parts.values())
    assert parts["database"]["bytes"] == got["storage"]["database"]["copy_bytes"]
    names = {f["name"] for f in got["storage"]["database"]["files"]}
    assert "corpus.db" in names
    assert got["storage"]["database"]["bytes"] == sum(f["bytes"] for f in got["storage"]["database"]["files"])

    # THE REAL THING, measured: a portable backup of this Brain
    from mentis.spine import backup
    dest = tmp_path / "portable"
    backup.backup(world["root"], dest=str(dest), portable=True)
    store = sum(f.stat().st_size for f in (dest / "artifacts").rglob("*") if f.is_file())
    assert store == parts["files"]["bytes"]
    assert (dest / "corpus.db").stat().st_size == parts["database"]["bytes"]
    kept = sum(f.stat().st_size for n in parts["kept"]["names"]
               for f in ([dest / n] if (dest / n).is_file() else (dest / n).rglob("*")) if f.is_file())
    assert kept == parts["kept"]["bytes"]


def test_a_purged_file_and_a_stray_one_are_said_and_left_out(world, me):
    st = world["state"]
    gone = _hold(world, me, b"purged by the owner" * 10)
    held.put(world["root"], b"in the store, named by nothing")
    before = _overview(world)
    files_before = next(p for p in before["portable"]["parts"] if p["part"] == "files")["bytes"]
    assert before["storage"]["files"]["unnamed"] >= 1

    artifacts.purge(st.corpus, st.cv, gone["admission"], by=me, because="the owner decided")
    after = _overview(world)
    assert after["counts"]["files"]["purged_references"] == before["counts"]["files"]["purged_references"] + 1
    assert after["counts"]["files"]["unique"] == before["counts"]["files"]["unique"] - 1
    assert after["counts"]["files"]["references"] == before["counts"]["files"]["references"] - 1
    files_after = next(p for p in after["portable"]["parts"] if p["part"] == "files")["bytes"]
    assert files_after == files_before - len(b"purged by the owner" * 10)

    # a named file whose bytes are gone from the disk is missing, not zero
    kept = _hold(world, me, b"its bytes will be lost")
    os.remove(held.path(world["root"], kept["digest"]))
    lost = _overview(world)
    assert lost["storage"]["files"]["missing"] == 1
    assert lost["storage"]["files"]["missing_bytes"] == len(b"its bytes will be lost")
    assert lost["portable"]["left_out"]["missing_files"] == 1


def test_a_connected_source_is_reported_and_only_its_copies_are_carried(world, me, tmp_path):
    path = str(tmp_path / "shop.sqlite")
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);"
                     "INSERT INTO customers VALUES (1,'Ada'),(2,'Bo');")
    db.commit()
    db.close()
    before = _overview(world)
    src = api.sources(world["state"].corpus)
    plan = src.preview_new(connector="sqlite", name="Shop", root=path, include=["customers"], exclude=[], options={})
    src.acquire_new(plan["draft"], plan["plan"], connector="sqlite", actor=me, written_by="test")
    after = _overview(world)

    sources = after["counts"]["sources"]
    assert sources["total"] == before["counts"]["sources"]["total"] + 1
    shop = next(c for c in sources["collections"] if c["name"] == "Shop")
    assert shop["connector"] == "sqlite" and shop["bound"] is True
    assert after["portable"]["left_out"]["sources"] == sources["total"]
    # where it is on this machine is said nowhere
    assert path not in str(after) and str(tmp_path / "shop.sqlite").replace("\\", "/") not in str(after)
    acquired = next(o for o in after["counts"]["files"]["origins"] if o["origin"] == "sqlite")
    assert acquired["group"] == "source" and acquired["unique"] >= 1
    # the source's own file is outside the Brain: no byte of it is in any total,
    # only the copies taken into the store
    grew = after["storage"]["files"]["bytes"] - before["storage"]["files"]["bytes"]
    assert grew == acquired["bytes"]
    files = lambda o: next(p for p in o["portable"]["parts"] if p["part"] == "files")["bytes"]  # noqa: E731
    assert files(after) - files(before) == acquired["bytes"]


def test_what_is_in_the_folder_and_not_carried_is_listed_with_its_size(world):
    root = world["root"]
    os.makedirs(os.path.join(root, "derived"), exist_ok=True)
    with open(os.path.join(root, "derived", "index.bin"), "wb") as fh:
        fh.write(b"x" * 321)
    got = _overview(world)
    derived = next(o for o in got["storage"]["other"] if o["name"] == "derived")
    assert derived["bytes"] >= 321 and derived["portable"] is False
    assert got["portable"]["left_out"]["other_bytes"] >= 321
    assert all(k["portable"] for k in got["storage"]["kept"])
    assert not any(o["name"].startswith(".mentis") for o in got["storage"]["other"])


def test_it_writes_nothing_and_takes_only_get(world, me):
    _hold(world, me, b"present before the read")
    st = world["state"]
    root = world["root"]

    def state():
        tree = {}
        for dirpath, _, names in os.walk(root):
            for n in names:
                if n.endswith(("-wal", "-shm")):
                    continue
                p = os.path.join(dirpath, n)
                tree[os.path.relpath(p, root)] = (os.path.getsize(p), os.path.getmtime(p))
        return st.corpus.advance(), tree

    was = state()
    for _ in range(3):
        _overview(world)
        _overview(world, measure=False)
    assert state() == was
    assert "error" in post(world, "/api/brain/overview", {})
    assert state() == was


def test_the_store_is_not_walked_on_every_read_and_says_when_it_was_measured(world, me, monkeypatch):
    first = _overview(world)
    walks = []
    real = brain_overview._walk_store
    monkeypatch.setattr(brain_overview, "_walk_store", lambda root: walks.append(root) or real(root))
    again = _overview(world, measure=False)
    assert walks == [] and again["storage"]["files"]["measured_at"] == first["storage"]["files"]["measured_at"]
    # the record's own counts are never the kept ones: a new file is counted at once
    _hold(world, me, b"arrived after the measurement")
    later = _overview(world, measure=False)
    assert later["counts"]["files"]["unique"] == first["counts"]["files"]["unique"] + 1
    assert walks == []
    # and it is not called missing because the measurement is older than it is
    assert later["storage"]["files"]["missing"] == 0
    assert later["storage"]["files"]["on_disk"] == first["storage"]["files"]["on_disk"] + 1
    fresh = _overview(world)
    assert len(walks) == 1 and fresh["storage"]["files"]["missing"] == 0
    assert fresh["storage"]["files"]["measured_at"] > first["storage"]["files"]["measured_at"]


def test_the_record_tally_is_kept_until_the_record_moves(world, me, monkeypatch):
    from mentis.web import ladder
    calls = []
    real = ladder.tally
    monkeypatch.setattr(ladder, "tally", lambda corpus: calls.append(1) or real(corpus))
    _overview(world)
    _overview(world)
    assert len(calls) == 1
    post(world, "/api/entries", {"kind": "note", "body": {"text": "The record moved."},
                                 "attributed_to": me, "establish": False})
    got = _overview(world)
    assert len(calls) == 2
    assert got["counts"]["knowledge"]["total"] == get(world, "/api/ladder/browse?view=knowledge&limit=1")["total"]
