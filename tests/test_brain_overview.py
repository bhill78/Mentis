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


def test_the_portable_estimate_is_its_parts_and_matches_a_portable_backup_except_its_manifest(world, me, tmp_path):
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
    kept = sum(f.stat().st_size for n in backup.AUX if (dest / n).exists()
               for f in ([dest / n] if (dest / n).is_file() else (dest / n).rglob("*")) if f.is_file())
    assert kept == parts["kept"]["bytes"]
    # THE ONE THING A BACKUP WRITES THAT THE ESTIMATE LEAVES OUT, and says so:
    # its own list of contents. Everything else in the backup is counted.
    assert got["portable"]["not_counted"] == ["BACKUP.json"]
    written = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    assert written - (dest / "BACKUP.json").stat().st_size == got["portable"]["bytes"]


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
    derived = next(o for o in got["storage"]["other"] if o["what"] == "derived")
    assert derived["bytes"] >= 321 and derived["portable"] is False
    assert got["portable"]["left_out"]["other_bytes"] >= 321
    assert all(k["portable"] for k in got["storage"]["kept"])
    assert not any(o["what"] == "other" for o in got["storage"]["other"])

    # WHAT MENTIS DID NOT PUT THERE IS COUNTED TOGETHER, NEVER NAMED
    os.makedirs(os.path.join(root, "holiday-photos-2026"))
    with open(os.path.join(root, "holiday-photos-2026", "beach.jpg"), "wb") as fh:
        fh.write(b"y" * 700)
    with open(os.path.join(root, "salary-notes.txt"), "wb") as fh:
        fh.write(b"z" * 50)
    more = _overview(world)
    rest = next(o for o in more["storage"]["other"] if o["what"] == "other")
    assert rest["files"] == 2 and rest["bytes"] == 750 and rest["portable"] is False
    said = str(more)
    assert "holiday" not in said and "salary" not in said and "beach" not in said
    assert "name" not in rest and all("name" not in i for i in more["storage"]["kept"] + more["storage"]["other"])


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


def test_within_the_kept_period_an_ordinary_read_walks_no_directory_at_all(world, me, monkeypatch):
    os.makedirs(os.path.join(world["root"], "derived", "deep"), exist_ok=True)
    first = _overview(world)
    listed = []
    real = brain_overview._entries
    monkeypatch.setattr(brain_overview, "_entries", lambda path: listed.append(path) or real(path))
    monkeypatch.setattr(brain_overview.os, "listdir", lambda *a: listed.append(a) or [])
    monkeypatch.setattr(brain_overview.os, "walk", lambda *a, **k: listed.append(a) or iter(()))
    again = _overview(world, measure=False)
    assert listed == [], "an ordinary read listed a directory"
    assert again["storage"]["measured_at"] == first["storage"]["measured_at"]
    assert again["storage"]["other"] == first["storage"]["other"] and again["storage"]["kept"] == first["storage"]["kept"]
    # the record's own counts are never the kept ones: a new file is counted at once
    _hold(world, me, b"arrived after the measurement")
    later = _overview(world, measure=False)
    assert listed == []
    assert later["counts"]["files"]["unique"] == first["counts"]["files"]["unique"] + 1
    # and it is not called missing because the measurement is older than it is
    assert later["storage"]["files"]["missing"] == 0
    assert later["storage"]["files"]["on_disk"] == first["storage"]["files"]["on_disk"] + 1
    fresh = _overview(world)
    assert listed and fresh["storage"]["files"]["missing"] == 0
    assert fresh["storage"]["measured_at"] > first["storage"]["measured_at"]


def test_a_kept_measurement_is_never_changed_and_a_file_that_goes_is_not_carried_forward(world, me):
    walked = _hold(world, me, b"there when the folder was measured")
    first = _overview(world)
    kept = brain_overview._measured[world["root"]]
    names_at_walk = dict(kept["at_name"])
    with pytest.raises(TypeError):
        kept["at_name"]["0" * 64] = 1                 # it cannot be written to

    # A FILE NAMED AFTER THE MEASUREMENT: seen for the answer, not written into it
    late = _hold(world, me, b"named after the folder was measured")
    seen = _overview(world, measure=False)
    assert seen["storage"]["files"]["on_disk"] == first["storage"]["files"]["on_disk"] + 1
    assert seen["storage"]["files"]["missing"] == 0
    assert brain_overview._measured[world["root"]] is kept and dict(kept["at_name"]) == names_at_walk
    # ... so when it goes again, the next answer says so, under the same measuring time
    os.remove(held.path(world["root"], late["digest"]))
    gone = _overview(world, measure=False)
    assert gone["storage"]["measured_at"] == first["storage"]["measured_at"]
    assert gone["storage"]["files"]["on_disk"] == first["storage"]["files"]["on_disk"]
    assert gone["storage"]["files"]["missing"] == 1
    assert gone["storage"]["files"]["missing_bytes"] == len(b"named after the folder was measured")

    # A FILE THAT WAS THERE AT THE MEASUREMENT AND IS REMOVED: the dated
    # measurement still has it; measuring again does not
    os.remove(held.path(world["root"], walked["digest"]))
    dated = _overview(world, measure=False)
    assert dated["storage"]["measured_at"] == first["storage"]["measured_at"]
    assert dated["storage"]["files"]["missing"] == 1
    again = _overview(world)
    assert again["storage"]["measured_at"] > first["storage"]["measured_at"]
    assert again["storage"]["files"]["missing"] == 2
    assert again["storage"]["files"]["on_disk"] == first["storage"]["files"]["on_disk"] - 1


def test_two_measurements_asked_for_at_once_are_one_walk(world, me, monkeypatch):
    import threading
    _hold(world, me, b"something to measure")
    _overview(world)
    started, release, walks = threading.Event(), threading.Event(), []
    real = brain_overview._walk_folder

    def slow(root):
        walks.append(root)
        started.set()
        assert release.wait(20)
        return real(root)

    monkeypatch.setattr(brain_overview, "_walk_folder", slow)
    answers = []
    ask = lambda measure: answers.append(_overview(world, measure=measure))  # noqa: E731
    a = threading.Thread(target=ask, args=(True,))
    a.start()
    assert started.wait(20)
    others = [threading.Thread(target=ask, args=(True,)) for _ in range(3)]
    for t in others:
        t.start()
    # the others are waiting on the one walk, not starting their own
    deadline = __import__("time").time() + 2
    while __import__("time").time() < deadline and len(walks) == 1:
        __import__("time").sleep(0.05)
    assert len(walks) == 1
    release.set()
    for t in [a, *others]:
        t.join(30)
    assert len(answers) == 4 and len(walks) == 1
    assert len({x["storage"]["measured_at"] for x in answers}) == 1
    assert world["root"] not in brain_overview._measuring
    # a walk that fails leaves nothing running, and the next one works
    monkeypatch.setattr(brain_overview, "_walk_folder", lambda root: (_ for _ in ()).throw(RuntimeError("no")))
    with pytest.raises(Exception):
        _overview(world)
    assert world["root"] not in brain_overview._measuring
    monkeypatch.setattr(brain_overview, "_walk_folder", real)
    assert _overview(world)["storage"]["files"]["missing"] == 0


def test_what_could_not_be_read_is_not_measured_with_the_reason_never_zero(world, me, monkeypatch):
    _hold(world, me, b"a stored file")
    root = world["root"]
    os.makedirs(os.path.join(root, "presentation", "pictures"), exist_ok=True)
    with open(os.path.join(root, "presentation", "pictures", "a.png"), "wb") as fh:
        fh.write(b"p" * 400)
    whole = _overview(world)
    assert whole["portable"]["bytes"] and whole["portable"]["why_not"] is None
    assert whole["storage"]["files"]["why_not"] is None and whole["storage"]["database"]["why_not"] is None
    real_entries, real_stat = brain_overview._entries, brain_overview._stat_size

    def denied(under):
        def entries(path):
            if os.path.normcase(under) in os.path.normcase(path):
                raise PermissionError(13, "Access is denied")
            return real_entries(path)
        return entries

    # a folder of stored files that cannot be listed
    shard = os.path.join(root, "artifacts", "sha256")
    monkeypatch.setattr(brain_overview, "_entries", denied(shard))
    got = _overview(world)
    f = got["storage"]["files"]
    assert f["why_not"] == "access was denied"
    assert all(f[k] is None for k in ("on_disk", "bytes", "missing", "unnamed", "stray", "purged_present"))
    assert got["portable"]["bytes"] is None
    assert got["portable"]["why_not"] == "the stored files could not all be read (access was denied)"
    files = next(x for x in got["portable"]["parts"] if x["part"] == "files")
    assert files["bytes"] is None and files["count"] is None
    assert got["portable"]["left_out"]["missing_files"] is None

    # a carried folder that cannot be listed: that item, and the estimate
    monkeypatch.setattr(brain_overview, "_entries", denied(os.path.join(root, "presentation", "pictures")))
    got = _overview(world)
    item = next(k for k in got["storage"]["kept"] if k["what"] == "presentation")
    assert item["bytes"] is None and item["why_not"] == "access was denied"
    assert item["files"] is None          # not the files it happened to reach
    assert got["storage"]["files"]["why_not"] is None and got["storage"]["files"]["bytes"] is not None
    assert got["portable"]["bytes"] is None
    assert got["portable"]["why_not"] == "part of the Brain's folder could not be read (access was denied)"
    assert next(x for x in got["portable"]["parts"] if x["part"] == "kept")["bytes"] is None

    # something NOT carried that cannot be read does not unmake the estimate
    os.makedirs(os.path.join(root, "derived", "x"), exist_ok=True)
    monkeypatch.setattr(brain_overview, "_entries", denied(os.path.join(root, "derived")))
    got = _overview(world)
    derived = next(o for o in got["storage"]["other"] if o["what"] == "derived")
    assert derived["bytes"] is None and derived["files"] is None and derived["why_not"] == "access was denied"
    assert got["portable"]["left_out"]["other_bytes"] is None
    assert got["portable"]["bytes"] == whole["portable"]["bytes"]
    monkeypatch.setattr(brain_overview, "_entries", real_entries)

    # a database file whose size cannot be read
    def stat(path):
        if path.endswith("corpus.db"):
            raise PermissionError(13, "Access is denied")
        return real_stat(path)
    monkeypatch.setattr(brain_overview, "_stat_size", stat)
    got = _overview(world)
    assert got["storage"]["database"]["bytes"] is None and got["storage"]["database"]["why_not"] == "access was denied"
    assert got["portable"]["left_out"]["sidecar_bytes"] is None
    monkeypatch.setattr(brain_overview, "_stat_size", real_stat)

    # the page count that could not be read
    monkeypatch.setattr(type(world["state"].corpus), "database_pages",
                        lambda self: (_ for _ in ()).throw(OSError("disk I/O error")))
    got = _overview(world)
    assert got["portable"]["bytes"] is None
    assert got["portable"]["why_not"] == "the database's size could not be read (it could not be read)"
    assert got["storage"]["database"]["copy_bytes"] is None


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


def test_no_store_is_none_and_a_store_that_cannot_be_looked_at_is_not_measured(world, me, monkeypatch):
    import shutil
    root = world["root"]
    store = os.path.join(root, "artifacts")
    # NO `artifacts/` AT ALL: truly no stored files, and that is a measurement
    shutil.rmtree(store, ignore_errors=True)
    none = _overview(world)
    f = none["storage"]["files"]
    assert f["why_not"] is None and f["on_disk"] == 0 and f["bytes"] == 0
    assert none["portable"]["bytes"] is not None and none["portable"]["why_not"] is None

    # `artifacts/` IS THERE AND CANNOT BE LOOKED AT: not measured, never "empty"
    _hold(world, me, b"a stored file")
    real = os.stat

    def stat(path, *a, **k):
        if os.path.normcase(os.fspath(path)) == os.path.normcase(store):
            raise PermissionError(13, "Access is denied", store)
        return real(path, *a, **k)
    monkeypatch.setattr(brain_overview.os, "stat", stat)
    got = _overview(world)
    monkeypatch.setattr(brain_overview.os, "stat", real)
    f = got["storage"]["files"]
    assert f["why_not"] == "access was denied" and f["on_disk"] is None and f["bytes"] is None
    assert got["portable"]["bytes"] is None
    assert got["portable"]["why_not"] == "the stored files could not all be read (access was denied)"

    # a top-level item whose own stat fails: no count, no size, the reason
    os.makedirs(os.path.join(root, "derived"), exist_ok=True)
    derived = os.path.join(root, "derived")

    def stat2(path, *a, **k):
        if os.path.normcase(os.fspath(path)) == os.path.normcase(derived):
            raise PermissionError(13, "Access is denied", derived)
        return real(path, *a, **k)
    monkeypatch.setattr(brain_overview.os, "stat", stat2)
    got = _overview(world)
    monkeypatch.setattr(brain_overview.os, "stat", real)
    item = next(o for o in got["storage"]["other"] if o["what"] == "derived")
    assert item == {"what": "derived", "files": None, "bytes": None, "why_not": "access was denied", "portable": False}


def test_no_reason_in_the_answer_ever_carries_a_path(world, me, monkeypatch):
    import json
    import re
    import sqlite3
    _hold(world, me, b"a stored file")
    root = world["root"]
    os.makedirs(os.path.join(root, "derived"), exist_ok=True)
    secret = os.path.join(root, "artifacts", "sha256", "ab", "private-name.bin")
    assert os.path.isabs(secret)

    def pathless(got):
        said = json.dumps(got)
        assert root not in said and root.replace("\\", "/") not in said and "private-name" not in said
        assert json.dumps(root)[1:-1] not in said
        reasons = [got["portable"]["why_not"], got["storage"]["files"]["why_not"], got["storage"]["database"]["why_not"],
                   got["storage"]["folder_why_not"],
                   *(i["why_not"] for i in got["storage"]["kept"] + got["storage"]["other"])]
        for why in filter(None, reasons):
            assert "\\" not in why and "/" not in why, why
            assert not re.search(r"[A-Za-z]:", why), why
        return got

    # the page count fails with a message that is nothing but a path
    for exc in (sqlite3.OperationalError(f"unable to open database file: {secret}"),
                OSError(f"cannot read {secret}"), RuntimeError(secret),
                PermissionError(13, f"denied on {secret}", secret)):
        monkeypatch.setattr(type(world["state"].corpus), "database_pages",
                            lambda self, exc=exc: (_ for _ in ()).throw(exc))
        got = pathless(_overview(world))
        assert got["portable"]["bytes"] is None and got["portable"]["why_not"]
    monkeypatch.undo()
    assert pathless(_overview(world))["portable"]["bytes"] is not None

    # the disk refuses with the path in its own words
    real = brain_overview._entries

    def entries(path):
        if os.path.normcase(path) != os.path.normcase(root):
            raise PermissionError(13, f"Access is denied: '{path}'", path)
        return real(path)
    monkeypatch.setattr(brain_overview, "_entries", entries)
    got = pathless(_overview(world))
    assert got["storage"]["files"]["why_not"] == "access was denied"
    assert got["portable"]["why_not"] == "the stored files could not all be read (access was denied)"
    monkeypatch.setattr(brain_overview, "_entries", real)

    # NOTHING AN EXCEPTION SAYS IS PASSED ON, however harmless it looks: a
    # bare word can be a file's name or a volume's
    import errno
    for exc, said in ((PermissionError(13, "Access is denied", secret), "access was denied"),
                      (PermissionError(13, "denied secret-host-volume"), "access was denied"),
                      (OSError(errno.EIO, "payroll"), "the disk reported a read error"),
                      (OSError(errno.EBUSY, "salaries.xlsx"), "it is in use by another program"),
                      (OSError("payroll"), "it could not be read"),
                      (OSError(9999, "secretword"), "it could not be read"),
                      (FileNotFoundError(2, "budget", "budget"), "it was not found"),
                      (sqlite3.OperationalError(secret), "the database could not be read"),
                      (RuntimeError("secretword"), "it could not be read"),
                      (KeyError("secretword"), "it could not be read")):
        assert brain_overview._why(exc) == said
        assert brain_overview._why(exc) in brain_overview.REASONS

    def stat(path):
        raise OSError(errno.EIO, "payroll")
    monkeypatch.setattr(brain_overview, "_stat_size", stat)
    got = pathless(_overview(world))
    assert "payroll" not in json.dumps(got)
    assert got["storage"]["database"]["why_not"] == "the disk reported a read error"
    monkeypatch.undo()

    # AN ADMISSION'S SOURCE IS FREE TEXT AND CAN BE A PATH: it is never returned
    st = world["state"]
    for source in ("/home/brian/private/ledger:2026", "\\\\fileserver\\finance\\ledger",
                   "C:\\Users\\brian\\ledger", "odd-source-word:x"):
        artifacts.hold(st.corpus, st.cv, ("from " + source).encode(), act="artifact-submitted", actor=me,
                       source=source, door="human-ingress")
    got = pathless(_overview(world))
    said = json.dumps(got)
    for word in ("brian", "ledger", "fileserver", "finance", "odd-source-word", "/home"):
        assert word not in said, word
    origins = got["counts"]["files"]["origins"]
    other = [o for o in origins if o["group"] == "other"]
    assert len(other) == 1 and other[0]["origin"] is None and other[0]["unique"] >= 4
    assert {o["group"] for o in origins} <= {"attached", "returned", "source", "other"}
    assert all(o["origin"] is None for o in origins if o["group"] != "source")
    assert sum(o["references"] for o in origins) == got["counts"]["files"]["references"]


#: EVERY NUMBER IN THE PHYSICAL HALF OF THE ANSWER, and what reading it rests
#: on. A number added to the answer and not added here fails the test below,
#: so none can be left numeric after the read it rests on has failed.
#:   listing   the Brain's folder could not be listed
#:   store     `artifacts/` could not be looked at, or walked
#:   item:<x>  that item of the folder could not all be read
#:   db        a database file's size could not be read
#:   pages     the database's page count could not be read
_RESTS_ON = {
    "storage.measured_at": set(), "storage.kept_for_s": set(),
    "storage.database.bytes": {"db"}, "storage.database.copy_bytes": {"pages"},
    "storage.database.files[corpus.db].bytes": {"db"},
    "storage.database.files[corpus.db-wal].bytes": set(), "storage.database.files[corpus.db-shm].bytes": set(),
    **{f"storage.files.{k}": {"store"} for k in (
        "on_disk", "bytes", "missing", "missing_bytes", "unnamed", "unnamed_bytes",
        "purged_present", "purged_present_bytes", "stray", "stray_bytes")},
    **{f"storage.kept[{w}].{k}": {"listing", f"item:{w}"} for w in ("presentation", "runtime-notes", "identity")
       for k in ("files", "bytes")},
    **{f"{where}[{w}].{k}": {"listing", f"item:{w}"} for where in ("storage.other", "portable.left_out.other")
       for w in ("derived", "agent-policy", "other") for k in ("files", "bytes")},
    "portable.bytes": {"listing", "store", "pages", "item:presentation", "item:runtime-notes", "item:identity"},
    "portable.parts[database].bytes": {"pages"},
    "portable.parts[files].bytes": {"store"}, "portable.parts[files].count": {"store"},
    "portable.parts[kept].bytes": {"listing", "item:presentation", "item:runtime-notes", "item:identity"},
    "portable.parts[kept].count": {"listing"},
    "portable.left_out.sources": set(),
    **{f"portable.left_out.{k}": {"store"} for k in (
        "purged_files", "purged_bytes", "missing_files", "stray_files", "stray_bytes")},
    "portable.left_out.other_bytes": {"listing", "item:derived", "item:agent-policy", "item:other"},
    "portable.left_out.sidecar_bytes": {"db"},
}


def _numbers(node, path=""):
    """{path: value} of every number or null under `node`, list items keyed
    by what they are."""
    out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            if not k.endswith("why_not"):           # a reason, not a number
                out.update(_numbers(v, f"{path}.{k}" if path else k))
    elif isinstance(node, list):
        for v in node:
            if isinstance(v, dict):
                key = v.get("what") or v.get("part") or v.get("name")
                out.update(_numbers({k: x for k, x in v.items() if k not in ("what", "part", "name")}, f"{path}[{key}]"))
    elif node is None or (isinstance(node, (int, float)) and not isinstance(node, bool)):
        out[path] = node
    return out


def test_every_number_that_rests_on_a_failed_read_is_null_with_a_reason(world, me, monkeypatch):
    import errno
    root = world["root"]
    _hold(world, me, b"a stored file")
    for name in ("presentation", "instances", "derived", "holiday"):
        os.makedirs(os.path.join(root, name, "inner"), exist_ok=True)
        with open(os.path.join(root, name, "inner", "f.bin"), "wb") as fh:
            fh.write(b"x" * 100)
    with open(os.path.join(root, "mcp-policy.json"), "w") as fh:
        fh.write("{}")
    if not os.path.exists(os.path.join(root, "mentis-corpus.json")):
        with open(os.path.join(root, "mentis-corpus.json"), "w") as fh:
            fh.write("{}")

    def physical(got):
        return _numbers({"storage": got["storage"], "portable": got["portable"]})

    whole = physical(_overview(world))
    numeric = {k for k, v in whole.items() if v is not None}
    # every number there is has been classified, and all of them are read here
    assert numeric == {k for k in whole}, {k for k, v in whole.items() if v is None}
    assert set(whole) - {k for k in _RESTS_ON} == set(), "a number in the answer that the table does not know"
    assert {k for k in _RESTS_ON if "wal" not in k and "shm" not in k} - set(whole) == set(), "a number the table expects is gone"

    real_entries, real_stat, real_os_stat = brain_overview._entries, brain_overview._stat_size, os.stat
    inside = lambda path, under: os.path.normcase(os.path.join(root, under)) in os.path.normcase(os.fspath(path))  # noqa: E731
    same = lambda path, name: os.path.normcase(os.fspath(path)) == os.path.normcase(os.path.join(root, name) if name else root)  # noqa: E731

    def refuse_entries(when):
        def entries(path):
            if when(path):
                raise PermissionError(13, "nope")
            return real_entries(path)
        return lambda: monkeypatch.setattr(brain_overview, "_entries", entries)

    def refuse_os_stat(when):
        def stat(path, *a, **k):
            if when(path):
                raise OSError(errno.EIO, "nope")
            return real_os_stat(path, *a, **k)
        return lambda: monkeypatch.setattr(brain_overview.os, "stat", stat)

    def refuse_size(when):
        def size(path):
            if when(path):
                raise OSError(errno.EIO, "nope")
            return real_stat(path)
        return lambda: monkeypatch.setattr(brain_overview, "_stat_size", size)

    def refuse_pages():
        monkeypatch.setattr(type(world["state"].corpus), "database_pages",
                            lambda self: (_ for _ in ()).throw(sqlite3.OperationalError("nope")))

    import sqlite3
    points = {
        "the folder's listing": ({"listing"}, refuse_entries(lambda p: same(p, ""))),
        "artifacts/ stat": ({"store"}, refuse_os_stat(lambda p: same(p, "artifacts"))),
        "artifacts/ walk": ({"store"}, refuse_entries(lambda p: inside(p, os.path.join("artifacts", "sha256")))),
        "presentation": ({"item:presentation"}, refuse_entries(lambda p: inside(p, os.path.join("presentation", "inner")))),
        "instances": ({"item:runtime-notes"}, refuse_entries(lambda p: inside(p, os.path.join("instances", "inner")))),
        "mentis-corpus.json": ({"item:identity"}, refuse_os_stat(lambda p: same(p, "mentis-corpus.json"))),
        "derived": ({"item:derived"}, refuse_entries(lambda p: inside(p, "derived"))),
        "mcp-policy.json": ({"item:agent-policy"}, refuse_os_stat(lambda p: same(p, "mcp-policy.json"))),
        "an unknown folder": ({"item:other"}, refuse_entries(lambda p: inside(p, "holiday"))),
        "corpus.db": ({"db"}, refuse_size(lambda p: same(p, "corpus.db"))),
        "page count": ({"pages"}, refuse_pages),
    }
    for label, (failed, arrange) in points.items():
        arrange()
        got = _overview(world)
        monkeypatch.undo()
        seen = physical(got)
        for path, rests in _RESTS_ON.items():
            if path not in whole:
                continue
            if rests & failed:
                # null -- or, for an item of a folder that could not be listed, not there at all
                assert seen.get(path) is None, f"{label}: {path} is still {seen.get(path)!r}"
            else:
                assert seen.get(path) is not None, f"{label}: {path} was lost though it does not rest on that"
        # ... and a reason is given, one of this module's own
        reasons = [got["portable"]["why_not"], got["storage"]["files"]["why_not"], got["storage"]["database"]["why_not"],
                   got["storage"]["folder_why_not"],
                   *(i["why_not"] for i in got["storage"]["kept"] + got["storage"]["other"])]
        given = [r for r in reasons if r]
        assert given, f"{label}: nothing says why"
        assert "nope" not in str(got)
        assert any(r in brain_overview.REASONS or any(x in r for x in brain_overview.REASONS) for r in given)
    assert physical(_overview(world)).keys() == whole.keys()
