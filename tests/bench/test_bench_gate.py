"""MEASUREMENT ONLY. Focused tests of benchgate, on a lock of their own in a temp directory: the real
HOME/RUNLOCK is never touched. A test using `quiet_machine` has the real sampler and skips beside other
bench work; the rest stub it (conftest.py).

Holders and fake processes are siblings here, each a child of the test: what a holder started is its
own and is not reported, so a fake must not be the holder's descendant.
"""
import json, os, pathlib, shutil, subprocess, sys, textwrap, time

import psutil
import pytest

from .conftest import G

BASE_PY = getattr(sys, "_base_executable", sys.executable)
HOLDER = textwrap.dedent("""
    import json, pathlib, sys, time
    sys.path.insert(0, sys.argv[1])
    import benchgate as G
    tmp = pathlib.Path(sys.argv[2])
    G.LOCK, G.EVENTS, G.STALE_DIR, G.SAMPLES = tmp / "RUNLOCK", tmp / "events.jsonl", tmp / "stale-locks", tmp / "samples"
    G.BUNDLE_DIR = tmp / "bundle"
    hold = G.take(kind="test", holder="helper", purpose="hold", code={"commit": "t", "dir": "t"})
    (tmp / "held").write_text("1")
    while not (tmp / "go").exists():
        time.sleep(0.1)
    hold.write_result(tmp / "result.json", {"kind": "test"})
""")


def events(tmp):
    return [json.loads(x) for x in (tmp / "events.jsonl").read_text().splitlines()]


def dead_pid():
    p = subprocess.Popen([BASE_PY, "-c", "pass"])
    p.wait()
    return p.pid


CODE = {"commit": "t", "dir": "t"}


def holder(tmp):
    return subprocess.Popen([BASE_PY, "-B", "-c", HOLDER, str(G.MEASURE), str(tmp)], stderr=subprocess.PIPE, text=True)


def wait_for(path, proc, bound=60):
    t0 = time.time()
    while not path.exists():
        if proc.poll() is not None or time.time() - t0 > bound:
            raise AssertionError(f"no {path.name}; holder rc {proc.poll()}")
        time.sleep(0.05)


def fake_pytest(tmp):
    """`python -m pytest`, exactly what a raw run looks like, and it only sleeps."""
    d = tmp / "fake"
    d.mkdir(exist_ok=True)
    (d / "pytest.py").write_text("import time\ntime.sleep(25)\n")
    return subprocess.Popen([BASE_PY, "-m", "pytest", "--fake"], cwd=str(d), env={**os.environ, "PYTHONPATH": str(d)})


def fake_cargo(tmp):
    """A real process whose image is named cargo.exe."""
    d = tmp / "fakebin"
    d.mkdir(exist_ok=True)
    shutil.copy(r"C:\Windows\System32\ping.exe", d / "cargo.exe")
    return subprocess.Popen([str(d / "cargo.exe"), "-n", "25", "127.0.0.1"], stdout=subprocess.DEVNULL)


def take_or_skip():
    """The real sampler's first scan: another package can start building after `quiet_machine` looked."""
    try:
        return G.take(kind="k", holder="me", purpose="why", code=CODE)
    except G.Refused as e:
        if "other bench work" in e.why:
            pytest.skip(e.why[:200])
        raise


TREE = str(G.BENCH)


@pytest.mark.parametrize("name,argv,cwd,ports,want", [
    ("cargo.exe", ["cargo", "build"], r"C:\elsewhere", (), "bench"),
    ("rustc.exe", ["rustc", "--edition"], "", (), "bench"),
    ("python.exe", ["python", "-m", "pytest", "tests/x.py"], r"C:\elsewhere", (), "bench"),
    ("pytest.exe", ["pytest"], "", (), "bench"),
    ("python.exe", ["python", TREE + r"\census\capture.py", "c", "b", "8832", "o"], "", (), "bench"),
    ("python.exe", ["python", "run_tests.py", "sha", "g", "o"], TREE, (), "bench"),
    ("python.exe", ["python", "run_workload.py", "--label", "S"], "", (), "bench"),
    ("node.exe", ["node", r"C:\x\node_modules\vite\bin\vite.js", "build"], "", (), "bench"),
    ("node.exe", ["node", r"C:\x\npm-cli.js", "run", "build"], "", (), "bench"),
    ("esbuild.exe", ["esbuild"], "", (), "bench"),
    ("python.exe", ["python", "-m", "mentis.web", "x", "--port", "8834"], r"C:\elsewhere", (8834,), "bench"),
    ("python.exe", ["python", "-c", "print(1)"], TREE, (), "bench"),
    ("node.exe", ["node", TREE + r"\x.js"], "", (), "bench"),
    ("cp.exe", ["cp", "a", "b"], TREE, (), "bench"),
    ("bash.exe", ["bash", "-c", "sleep 20"], TREE, (), "shell"),
    ("sleep.exe", ["sleep", "20"], TREE, (), "tool"),
    ("rg.exe", ["rg", "x"], TREE, (), "tool"),
    ("git.exe", ["git", "status"], TREE + r"\src\mentis", (), "tool"),
    ("claude.exe", ["claude", "--add-dir", TREE], TREE, (), "agent"),
    ("mars.exe", ["mars", "stdio"], r"C:\Work\Mentis-dayday", (), "agent"),
    ("python.exe", ["python", "-I", "-c", "from mentis.worker import serve; serve()"], TREE, (), "agent"),
    ("node.exe", ["node", r"C:\x\@agentclientprotocol\claude-agent-acp\dist\index.js"], TREE, (), "agent"),
    ("python.exe", ["python", "-m", "mentis.web", "x", "--port", "8760"], r"C:\Work\Mentis-dayday", (8760,), "other"),
    ("chrome.exe", ["chrome"], r"C:\elsewhere", (), "other"),
    ("python.exe", ["python", "x.py"], r"C:\elsewhere", (), "other"),
    ("python.exe", ["python", "-B", TREE + r"\benchgate.py", "status"], TREE, (), "tool"),
    ("python.exe", ["python", "-B", TREE + r"\benchgate.py", "sample", "--holder", "1"], TREE, (), "shell"),
])
def test_classify(name, argv, cwd, ports, want):
    assert G.classify(name, argv, cwd, ports)[0] == want


def test_git_bash_form_of_the_tree_counts():
    assert G.in_tree("cd /c/Work/Mentis-workspace/day-to-day/r1-bench/run && x")


def test_the_bench_tree_is_the_home_the_tools_and_the_master():
    assert G.in_tree(str(G.MEASURE / "load.py"))
    assert G.in_tree(r"python x.py C:\Work\Mentis-workspace\r1-fixtures\brain-copy-master\corpus.db")
    assert not G.in_tree(r"C:\Work\Mentis-workspace\day-to-day\mirps-shared-ops\measure")


def test_lock_records_holder_pid_purpose_start_and_refuses_a_second(gate):
    hold = G.take(kind="k", holder="me", purpose="why", code=CODE)
    d = G.read_lock()
    assert (d["holder"], d["pid"], d["purpose"]) == ("me", os.getpid(), "why") and d["started"]
    with pytest.raises(G.Refused) as e:
        G.take(kind="k", holder="second", purpose="other", code=CODE)
    assert e.value.code == G.REFUSED and "me" in e.value.why
    rec = hold.finish()
    assert rec["valid"] and not G.LOCK.exists()
    assert rec["acquired_at"] and rec["released_at"] and rec["sample_count"] >= 1 and rec["sampler_cost"]["cpu_s"] is not None
    assert [e["event"] for e in events(gate)] == ["taken", "refused", "released"]


def test_result_carries_identity_and_in_progress_cannot_pass(gate, tmp_path):
    hold = G.take(kind="k", holder="me", purpose="why", code=CODE)
    r = hold.stamp({})
    assert r["workload_sha"] == G.workload_sha() and r["code"]["commit"] == "t"
    r["brain"] = {"corpus_db_sha256": "d1"}
    assert G.why_not_a_candidate("C0", r) == ["its isolation record is unfinished: the holder never released"]
    out = tmp_path / "r.json"
    hold.write_result(out, {"x": 1, "brain": {"corpus_db_sha256": "d1"}})
    r = json.loads(out.read_text())
    assert r["isolation"]["state"] == "released" and G.why_not_a_candidate("C0", r) == []


def test_no_commit_is_refused_and_lock_untouched(gate, tmp_path):
    with pytest.raises(G.Refused):
        G.take(kind="k", holder="me", purpose="why", code=str(tmp_path))
    assert not G.LOCK.exists()


def test_stale_lock_is_moved_aside_recorded_and_named_by_the_new_holder(gate):
    pid = dead_pid()
    G.LOCK.write_text(json.dumps({"holder": "dead one", "pid": pid, "purpose": "p", "started": "s", "create_time": 1.0}))
    hold = G.take(kind="k", holder="me", purpose="why", code=CODE)
    rec = hold.finish()
    moved = rec["stale_locks_moved_aside"]
    assert len(moved) == 1 and moved[0]["was"]["pid"] == pid and rec["valid"]
    assert (gate / "stale-locks" / moved[0]["kept_as"]).exists()
    assert "stale lock moved aside" in [e["event"] for e in events(gate)]


def test_old_format_with_a_dead_pid_is_stale(gate):
    G.LOCK.write_text(f"harness (run_workload.py), pid {dead_pid()}: timed run\n")
    assert G.take(kind="k", holder="me", purpose="why", code=CODE).finish()["stale_locks_moved_aside"]


def test_a_reused_pid_is_not_a_live_holder(gate):
    me = psutil.Process()
    d = {"holder": "x", "pid": me.pid, "create_time": me.create_time() - 1000}
    assert G.holder_state(d) == "dead"
    d["create_time"] = me.create_time()
    assert G.holder_state(d) == "live"


def test_unreadable_lock_refuses_loudly_then_break_clears_it(gate, monkeypatch):
    G.LOCK.write_text("no holder here")
    assert G.holder_state(G.read_lock()) == "live"      # could be mid-write
    monkeypatch.setattr(G, "GRACE_S", -1)
    with pytest.raises(G.Refused) as e:
        G.take(kind="k", holder="me", purpose="why", code=CODE)
    assert "break" in e.value.why
    assert G.break_stale(G.read_lock(), "looked at it")
    assert not G.LOCK.exists()


def test_break_does_not_move_a_lock_that_changed_meanwhile(gate):
    G.LOCK.write_text(json.dumps({"pid": os.getpid(), "holder": "live"}))
    assert G.break_stale({"pid": 1, "holder": "what was read"}, "race") is None
    assert G.LOCK.exists()


def test_preflight_refuses_beside_a_raw_process_and_leaves_no_lock(quiet_machine):
    gate = quiet_machine
    fake = fake_pytest(gate)
    try:
        time.sleep(0.5)
        h = holder(gate)
        err = h.communicate(timeout=120)[1]
        assert h.returncode == G.REFUSED and "other bench work" in err and "pytest" in err
        assert not G.LOCK.exists() and not (gate / "held").exists()
    finally:
        fake.kill()
        fake.wait()


def test_stale_lock_with_what_it_left_running_refuses(quiet_machine):
    gate = quiet_machine
    G.LOCK.write_text(json.dumps({"holder": "dead", "pid": dead_pid(), "started": "s"}))
    fake = fake_pytest(gate)
    try:
        time.sleep(0.5)
        h = holder(gate)
        err = h.communicate(timeout=120)[1]
        assert h.returncode == G.REFUSED and "pytest" in err
        assert "stale lock moved aside" in [e["event"] for e in events(gate)]
        assert not G.LOCK.exists()
    finally:
        fake.kill()
        fake.wait()


@pytest.mark.parametrize("make,word", [(fake_pytest, "pytest"), (fake_cargo, "cargo")])
def test_a_raw_process_during_the_hold_marks_the_result_invalid(quiet_machine, make, word):
    gate = quiet_machine
    h = holder(gate)
    fake = None
    try:
        try:
            wait_for(gate / "held", h)
        except AssertionError:
            err = h.communicate(timeout=30)[1]
            if "other bench work" in err:
                pytest.skip("another package started building after the first look")
            raise
        fake = make(gate)
        time.sleep(2 * G.SAMPLE_S + 1)
        (gate / "go").write_text("1")
        wait_for(gate / "result.json", h)
        h.wait(30)
    finally:
        if fake:
            fake.kill()
            fake.wait()
        if h.poll() is None:
            h.kill()
    r = json.loads((gate / "result.json").read_text())
    iso = r["isolation"]
    assert iso["valid"] is False and iso["sightings"]
    assert any(word in x["cmd"] or word in x["name"] for x in iso["sightings"])
    assert iso["sightings"][0]["first_seen"] and iso["sightings"][0]["samples"] >= 1
    assert any(x.startswith("it is marked invalid") for x in G.why_not_a_candidate("X", r))


def test_what_the_holder_starts_is_not_a_sighting(quiet_machine):
    hold = take_or_skip()
    kid = subprocess.Popen([BASE_PY, "-c", "import time;time.sleep(6)"], cwd=str(G.MEASURE))
    try:
        time.sleep(2 * G.SAMPLE_S + 1)
    finally:
        kid.kill()
        kid.wait()
    rec = hold.finish()
    assert kid.pid not in [x["pid"] for x in rec["sightings"]]
    if rec["sightings"]:
        pytest.skip("another package's work appeared during the hold: " + rec["sightings"][0]["cmd"][:100])
    assert rec["valid"] and rec["sample_count"] >= 2


def test_losing_the_lock_invalidates(quiet_machine):
    hold = take_or_skip()
    G.LOCK.unlink()
    time.sleep(G.SAMPLE_S + 1)
    rec = hold.finish()
    assert not rec["valid"] and any("not ours at release" in x for x in rec["invalid_reasons"])
    assert any("missing or another's" in x for x in rec["invalid_reasons"])


def test_work_that_did_not_complete_is_invalid(gate):
    rec = G.take(kind="k", holder="me", purpose="why", code=CODE).finish(completed=False)
    assert not rec["valid"] and "did not complete" in rec["invalid_reasons"][0]


def test_finish_twice_is_one_record(gate):
    hold = G.take(kind="k", holder="me", purpose="why", code=CODE)
    assert hold.finish() is hold.finish()


GOOD = {"state": "released", "valid": True, "invalid_reasons": []}


def result(sha=None, iso=GOOD, brain="d1"):
    r = {"workload_sha": sha or G.workload_sha(), "brain": {"corpus_db_sha256": brain}}
    if iso:
        r["isolation"] = iso
    return r


def test_refusals(gate):
    now = G.workload_sha()
    assert G.refusals({"a": result(), "b": result()}) == []
    assert any("workload_sha differs" in x for x in G.refusals({"a": result(), "b": result("different")}))
    assert any("no isolation record" in x for x in G.refusals({"a": result(), "b": result(iso=None)}))
    assert any("marked invalid: seen" in x for x in G.refusals({"a": result(iso={**GOOD, "valid": False, "invalid_reasons": ["seen"]})}))
    assert any("is a pilot" in x for x in G.refusals({"pilots/a": result()}))
    assert any("no workload_sha" in x for x in G.refusals({"a": {"isolation": GOOD}}))
    assert any("no brain digest" in x for x in G.refusals({"a": {**result(), "brain": None}}))
    assert any("the Brain differs" in x for x in G.refusals({"a": result(), "b": result(brain="d2")}))
    old = result("older")
    assert any(f"this tree's workload_sha is {now}" in x for x in G.refusals({"a": old, "b": dict(old)}))
    with pytest.raises(G.Refused):
        G.refuse_unless_comparable({"a": result(iso=None)})


def test_refused_comparison_is_logged(gate):
    with pytest.raises(G.Refused):
        G.refuse_unless_comparable({"a": result(iso=None)})
    assert events(gate)[-1]["event"] == "comparison refused"


def test_workload_sha_covers_the_gate_the_tools_and_the_bundle(gate, tmp_path, monkeypatch):
    assert "benchgate.py" in G.HASHED and "answers.py" in G.HASHED and "run_workload.py" in G.HASHED
    code = tmp_path / "tools"
    for name in G.HASHED:
        (code / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(G.MEASURE / name, code / name)
    monkeypatch.setattr(G, "MEASURE", code)
    same = G.workload_sha()
    assert same == G.workload_sha()
    with open(G.BUNDLE_DIR / "render-check.js", "a") as f:
        f.write("// changed\n")
    changed = G.workload_sha()
    assert changed != same
    with open(code / "benchgate.py", "a") as f:
        f.write("# changed\n")
    assert G.workload_sha() != changed


def test_commit_is_given_only_for_a_tree_with_no_git(tmp_path, monkeypatch):
    monkeypatch.setenv("BENCH_CODE_COMMIT", "abc1234")
    got = G.commit_of(str(tmp_path))
    assert got["commit"] == "abc1234" and got["given_by"] == "BENCH_CODE_COMMIT"
