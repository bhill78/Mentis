"""The bench's tests: a BENCH_HOME of their own, never the real lock or results.

The gate's sampler sees every `cargo`, `rustc` and `pytest` on the machine, so a real sampler refuses
whenever another package is building. `stub_sampler` stands in for it where the sampler isn't the
subject. `quiet_machine` is for the tests that are about the sampler: it skips, in words, when other
bench work is running.
"""
import json, os, pathlib, sqlite3, stat, sys, time, types

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
TOOLS = REPO / "tools" / "bench"
sys.path.insert(0, str(TOOLS))
import benchgate as G  # noqa: E402

STAND_IN = pathlib.Path(__file__).with_name("stand_in.py")
PORT = 8838


def point_gate_at(monkeypatch, tmp):
    for name, value in (("HOME", tmp), ("BENCH", tmp), ("LOCK", tmp / "RUNLOCK"), ("EVENTS", tmp / "events.jsonl"),
                        ("STALE_DIR", tmp / "stale-locks"), ("SAMPLES", tmp / "samples"),
                        ("GATE_RESULTS", tmp / "gate-results"), ("RESULTS", tmp / "results"), ("RUN", tmp / "run"),
                        ("BUNDLE_DIR", tmp / "bundle")):
        monkeypatch.setattr(G, name, value)
    (tmp / "bundle").mkdir(exist_ok=True)
    (tmp / "bundle" / "render-check.js").write_text("// stand-in bundle\n")


def stub_start(sighting=False):
    def start(self):
        G.SAMPLES.mkdir(parents=True, exist_ok=True)
        self.samples = G.SAMPLES / f"{self.token}.jsonl"
        self.stop_file = G.SAMPLES / f"{self.token}.stop"
        self.sampler = types.SimpleNamespace(wait=lambda t: 0, kill=lambda: None, poll=lambda: None)
        rows = [{"tick": 0, "t": time.time(), "bench": [], "new": [], "lock_ok": True, "ms": 1.0, "cpu_s": 0.01}]
        self.samples.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return True
    return start


@pytest.fixture
def home(tmp_path, monkeypatch):
    t = tmp_path / "home"
    t.mkdir()
    point_gate_at(monkeypatch, t)
    return t


@pytest.fixture
def gate(home, monkeypatch):
    """The lock and the events are real, in a temp directory; the sampler is not."""
    monkeypatch.setattr(G.Hold, "_start_sampler", stub_start())
    return home


@pytest.fixture
def quiet_machine(home):
    """The real sampler, which only passes its first scan with no other bench work on the machine."""
    new, bench, _ = G.Scanner(os.getpid()).tick()
    if bench:
        seen = [p for p in new if p["key"] in bench][:3]
        pytest.skip("other bench work is running, so the real sampler would refuse: "
                    + "; ".join(f"{p['name']} {p['cmd'][:60]}" for p in seen))
    return home


@pytest.fixture
def master(tmp_path):
    """A small master shaped as BRAIN-COPY's: its files read-only, as `copy_brain.py` leaves them."""
    m = tmp_path / "master"
    (m / "presentation").mkdir(parents=True)
    (m / "derived").mkdir()
    (m / "presentation" / "looks.json").write_text("{}")
    (m / "derived" / "d.txt").write_text("d")
    (m / "mentis-corpus.json").write_text('{"role": "test"}')
    c = sqlite3.connect(m / "corpus.db")
    c.executescript("""
        create table entry (seq integer primary key, id text, recorded_at real);
        create table operational (seq integer primary key, id text, at real, act text);
        create table delivery (seq integer primary key);
        insert into entry (id, recorded_at) values ('ent-000000000001', 1000.0);
        insert into operational (id, at, act) values ('opr-000000000001', 1000.0, 'x');
    """)
    c.commit()
    c.close()
    for p in m.rglob("*"):
        if p.is_file():
            os.chmod(p, stat.S_IREAD)
    yield m
    for p in m.rglob("*"):
        if p.is_file():
            os.chmod(p, stat.S_IRWXU)


@pytest.fixture
def code(tmp_path, monkeypatch):
    """--code: an exported tree, whose commit is given."""
    d = tmp_path / "code"
    d.mkdir()
    monkeypatch.setenv("BENCH_CODE_COMMIT", "abc1234")
    return d


def stand_in_command():
    return json.dumps([sys.executable, str(STAND_IN), "{brain}", "--port", "{port}", "--workspace", "{ws}",
                       "--mars", "{mars}", "--run", "{run}"])


def run_main(module, monkeypatch, argv):
    """A tool's main() in this process, so the stubbed sampler applies. Its exit code."""
    monkeypatch.setattr(sys, "argv", [module.__name__ + ".py", *argv])
    try:
        return module.main() or 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
