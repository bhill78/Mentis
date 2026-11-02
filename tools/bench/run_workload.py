"""MEASUREMENT ONLY. One command per candidate: starts and stops its own servers, each on
a fresh copy of the BRAIN-COPY master, no MARS, ports 8831-8839, and writes one schema to
HOME/results/<label>/. See docs/rust/contracts/bench.md.

    run_workload.py --command JSON --code DIR --label baseline

Order, all under HOME/RUNLOCK and watched by benchgate's sampler throughout: the gate's first
scan, an untimed statement-capture boot, any extra cold boots, then one main boot: cold probes,
warm-up, the read levels round after round, the levels that write last, so no read level ever
runs on a record the bench has moved.

Exit: 0 for a valid run with nothing badly answered, FAILED when it is invalid or has a bad status,
REFUSED when nothing ran. The result is written either way: a result is evidence.
"""
import argparse, collections, contextlib, json, os, pathlib, platform, re, shutil, sqlite3, stat, statistics, subprocess, sys, time

import psutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import benchgate as G
import wl_common as W

HERE = pathlib.Path(__file__).resolve().parent
PY_DEFAULT = r"C:\Work\Mentis-workspace\r1-fixtures\venv\Scripts\python.exe"
NO_MARS = "workload-no-mars-here"     # {mars}: a command that cannot exist, on top of PATH
PLACEHOLDERS = ("brain", "port", "ws", "mars", "run")
EXECUTABLE = (".exe", ".cmd", ".bat", ".com")
#: The launcher's `--front` default is this, beside it (contracts/launcher.md), so a command that
#: does not name it still ran it.
DEFAULT_FRONT = {"mentis-launch": "mentis-server.exe"}
BOOKKEEPING = ("BEGIN", "COMMIT", "ROLLBACK", "PRAGMA", "SAVEPOINT", "RELEASE", "END")

#: THE LEVELS. name -> kind, n, pace, writes per second, whether the gated agent reads run
#: The agent levels' foreground is only what their background times but no probe does.
AGENT_LEVEL_OPS = ["kinds", "history"]
PACE_S = 5.0
WRITE_PERIOD_S = 2.0   # 30 Turns a minute; see README for how this was drawn from the record
LEVELS = {
    "idle":     dict(kind=None,    n=0,  pace=0,      write=False, agent_phase=True),
    "closed-4": dict(kind="mix",   n=4,  pace=0,      write=False, agent_phase=True),
    "closed-16": dict(kind="mix",  n=16, pace=0,      write=False, agent_phase=True),
    "paced-4":  dict(kind="mix",   n=4,  pace=PACE_S, write=False, agent_phase=True),
    "paced-16": dict(kind="mix",   n=16, pace=PACE_S, write=False, agent_phase=True),
    "agents-1": dict(kind="agent", n=1,  pace=0,      write=False, agent_phase=True, agent_ops=AGENT_LEVEL_OPS),
    "agents-4": dict(kind="agent", n=4,  pace=0,      write=False, agent_phase=True, agent_ops=AGENT_LEVEL_OPS),
    # NEIGHBOURS: Python held busy on routes a candidate never serves outside Python. They
    # never touch topics, the window or the pulse; only the foreground does.
    "n-sql":    dict(kind="sql",   n=4,  pace=0,      write=False, agent_phase=True),
    # JS holds the interpreter and objects._lock: behind it `activity` took 88 s and `find` 84 s
    # (pilot). Its foreground is only what it is there to test, so a cell stays bounded.
    "n-cpu":    dict(kind="cpu",   n=4,  pace=0,      write=False, agent_phase=False, light=True),
    # The whole agent mix: gated reads alone take turns, so they hold about 1 core (pilot, 1.19).
    "n-agents-write": dict(kind="agent", n=4, pace=0, write=True,  agent_phase=True, agent_ops=AGENT_LEVEL_OPS),
    "write":    dict(kind="mix",   n=4,  pace=PACE_S, write=True,  agent_phase=True, window_after=True),
}
REF = "ent-0ceca1e70bd0"          # a Turn every copy from 2026-11-01 holds: what `resolve` asks for
MAX_GRANTS = 6


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if PROGRESS:
        with open(PROGRESS, "a", encoding="utf-8") as f:
            f.write(line + "\n")


PROGRESS = None


def parse_command(text):
    """--command and $env:MENTIS_UNDER_TEST: a JSON array of strings, one per argument.

    Windows PowerShell 5.1 passes `--command $env:MENTIS_UNDER_TEST` with its quotes gone, so a value
    that is that variable's, less its quotes, means the variable. Nothing else is guessed at."""
    env = os.environ.get("MENTIS_UNDER_TEST")
    if env and text == env.replace('"', ""):
        text = env
    try:
        cmd = json.loads(text)
    except ValueError as e:
        raise G.Refused(f"--command is not JSON: {e}")
    if not (isinstance(cmd, list) and cmd and all(isinstance(x, str) for x in cmd)):
        raise G.Refused("--command must be a JSON array of strings, one per argument")
    named = {m for arg in cmd for m in re.findall(r"\{(\w+)\}", arg)}
    unknown = sorted(named - set(PLACEHOLDERS))
    if unknown:
        raise G.Refused(f"--command has unknown placeholders {unknown}; have {list(PLACEHOLDERS)}")
    # A command that names its own Brain would not run on this boot's fresh copy.
    missing = sorted({"brain", "port"} - named)
    if missing:
        raise G.Refused(f"--command must use {missing}: it runs on this boot's copy and port")
    if not shutil.which(cmd[0]):
        raise G.Refused(f"--command: {cmd[0]} is not an executable")
    return cmd


def fill(command, **values):
    out = []
    for arg in command:
        for k, v in values.items():
            arg = arg.replace("{" + k + "}", str(v))
        out.append(arg)
    return out


def binaries(command):
    """Each executable in the command not named python: its path and SHA-256."""
    paths = [shutil.which(command[0])]
    paths += [arg for arg in command[1:] if pathlib.Path(arg).suffix.lower() in EXECUTABLE and pathlib.Path(arg).is_file()]
    front = DEFAULT_FRONT.get(pathlib.Path(command[0]).stem.lower())
    if front and "--front" not in command and (pathlib.Path(paths[0]).parent / front).is_file():
        paths.append(str(pathlib.Path(paths[0]).parent / front))
    return [{"path": str(p), "sha256": G.sha256_of(p)} for p in paths
            if not pathlib.Path(p).stem.lower().startswith("python")]


def make_writable(root):
    """The master's files are read-only, and copies keep that."""
    root = pathlib.Path(root)
    for p in [root, *root.rglob("*")]:
        os.chmod(p, stat.S_IRWXU)


@contextlib.contextmanager
def scratch_db(master, where):
    """A copy of the master's corpus.db to read, since the master is never opened through SQLite."""
    d = pathlib.Path(where) / f"scratch-{os.getpid()}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(pathlib.Path(master, "corpus.db"), d)
        make_writable(d)
        yield d / "corpus.db"
    finally:
        shutil.rmtree(d, ignore_errors=True)


class Server:
    """One server over one fresh copy of the record."""

    def __init__(self, a, tag, trace_dir=None):
        self.a, self.tag = a, tag
        self.dir = pathlib.Path(a.run_dir) / tag
        self.brain, self.ws = self.dir / "brain", self.dir / "ws"
        self.port = a.port
        self.proc = None
        self.trace_dir = trace_dir
        self.pid_name, self.rss_by_name = {}, {}

    def start(self):
        a = self.a
        t = time.time()
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.brain.mkdir(parents=True)
        self.ws.mkdir()
        src = pathlib.Path(a.brain)
        shutil.copy2(src / "corpus.db", self.brain)
        shutil.copy2(src / "mentis-corpus.json", self.brain)
        shutil.copytree(src / "presentation", self.brain / "presentation")
        if (src / "derived").exists():
            shutil.copytree(src / "derived", self.brain / "derived")
        make_writable(self.brain)
        self.copied_s = round(time.time() - t, 1)
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith("MENTIS")}
        path = [p for p in env.get("PATH", "").split(os.pathsep)
                if "mars" not in p.lower() and "mentis" not in p.lower()]
        env["PATH"] = os.pathsep.join(path)
        if shutil.which("mars", path=env["PATH"]):
            raise SystemExit("a `mars` is on the test server's PATH: refusing to start")
        env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", PYTHONPATH=a.code,
                   MENTIS_FLUID_DIST=str(G.BUNDLE_DIR))
        if self.trace_dir:
            env["PYTHONPATH"] = os.pathsep.join([str(HERE / "trace"), a.code])
            env["WORKLOAD_TRACE_DIR"] = str(self.trace_dir)
        for kv in a.server_env:
            k, _, v = kv.partition("=")
            env[k] = v
        self.err = open(self.dir / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            fill(a.command, brain=self.brain, port=self.port, ws=self.ws, mars=NO_MARS, run=self.dir),
            cwd=str(self.dir), env=env, stdout=self.err, stderr=self.err)
        self.root = psutil.Process(self.proc.pid)
        t0 = time.time()
        while True:
            try:
                _, st, _ = W.once(self.port, "GET", "/api/pulse", headers=W.CLIENT, timeout=5)
                if st == 200:
                    break
            except OSError:
                pass
            if self.proc.poll() is not None or time.time() - t0 > 240:
                raise SystemExit(f"server did not start; see {self.dir / 'server.log'}")
            time.sleep(0.25)
        self.up_s = round(time.time() - t0, 1)
        self.quiet_s, self.was_quiet = self.quiet(a.boot_quiet_s)
        return self

    def tree(self):
        procs = [self.root]
        try:
            procs += self.root.children(recursive=True)
        except psutil.Error:
            pass
        return procs

    def cpu_rss(self):
        """{pid: cpu seconds}, rss bytes, thread count, across the server's process tree. What
        each process name holds apart is left in pid_name and rss_by_name."""
        cpu, rss, threads = {}, 0, 0
        self.rss_by_name = {}
        for p in self.tree():
            try:
                with p.oneshot():
                    t = p.cpu_times()
                    cpu[p.pid] = t.user + t.system
                    # the venv's python.exe is only a launcher: its child is the server
                    one = p.memory_info().rss
                    rss += one
                    threads += p.num_threads()
                    name = p.name()
                    self.pid_name[p.pid] = name
                    self.rss_by_name[name] = self.rss_by_name.get(name, 0) + one
            except psutil.Error:
                pass
        return cpu, rss, threads

    def quiet(self, bound):
        """Wait until the server has used under 0.15 cores for 2 s, at most `bound` s."""
        t0 = time.time()
        last, _, _ = self.cpu_rss()
        tl = time.time()
        while time.time() - t0 < bound:
            time.sleep(2)
            now, _, _ = self.cpu_rss()
            used = sum(max(0, now[k] - last.get(k, now[k])) for k in now) / max(0.1, time.time() - tl)
            last, tl = now, time.time()
            if used < 0.15:
                return round(time.time() - t0, 1), True
        return round(time.time() - t0, 1), False

    def engine_runs(self):
        """Refuse to measure a server whose object reads do not reach the JS engine."""
        _, st, b = W.once(self.port, "GET", f"/fluid/api/objects?post={REF}", headers=W.CLIENT, timeout=120)
        d = json.loads(b) if st == 200 else {}
        if d.get("extracted") is not True:
            raise SystemExit(f"object reads do not extract here: {st} {d.get('why_not') or b[:300]!r}")
        return d.get("renderer")

    def names(self):
        out = set()
        for p in self.tree():
            try:
                out.add(p.name())
            except psutil.Error:
                pass
        return sorted(out)

    def info(self):
        try:
            _, st, b = W.once(self.port, "GET", "/api/server", timeout=20)
            return json.loads(b) if st == 200 else {"status": st}
        except OSError as e:
            return {"error": repr(e)}

    def grants(self, n):
        out, permits = [], None
        for _ in range(n):
            _, st, b = W.once(self.port, "POST", "/api/worker/session", {"runtime": "workload"},
                              W.CLIENT, timeout=60)
            d = json.loads(b)
            if st != 200 or "grant" not in d:
                raise SystemExit(f"no grant: {st} {b[:300]!r}")
            out.append(d["grant"])
            permits = d
        return out, {k: permits.get(k) for k in ("scope", "alias", "runtime")}, permits.get("permits")

    def stop(self):
        if not self.proc:
            return
        for p in self.tree()[::-1]:
            try:
                p.kill()
            except psutil.Error:
                pass
        try:
            self.proc.wait(20)
        except subprocess.TimeoutExpired:
            pass
        self.err.close()
        self.proc = None


def spawn(a, script, cfg, name, cell_dir):
    path = pathlib.Path(cell_dir) / f"{name}.cfg.json"
    path.write_text(json.dumps(cfg))
    return subprocess.Popen([a.python, str(HERE / script), str(path)])


def run_probe(a, phase_cfg, name, cell_dir, grace=240):
    p = spawn(a, "probe.py", phase_cfg, name, cell_dir)
    p.wait(timeout=phase_cfg.get("wall_bound", grace))
    return json.load(open(phase_cfg["out"]))


def by_name(records):
    g = {}
    for rec in records:
        g.setdefault(rec[0], []).append(rec)
    return g


def probes_summary(results):
    """Results of the phases: {name: {count,p50,p95,max,errors,bad_status}}."""
    out, raw = {}, {}
    for res in results:
        for name, recs in by_name(res["records"]).items():
            raw.setdefault(name, []).extend(r[2] for r in recs if r[3] == 200)
            n = out.setdefault(name, {"bad_status": 0, "errors": 0})
            n["bad_status"] += sum(1 for r in recs if r[3] != 200)
        for e in res["errors"]:
            n = out.setdefault(e[0], {"bad_status": 0, "errors": 0})
            n["errors"] += 1
    for name, n in out.items():
        n.update(W.summ(raw.get(name, [])))
    return out, raw


def background_summary(d, frm, to):
    # latency: queries STARTED in the window. Throughput: queries that ENDED in it, so a
    # long query begun in the warm-up still counts as work done while it was measured.
    recs = [r for r in d["records"] if frm <= r[2] < to]
    ok = [r for r in recs if r[4] == 200]
    busy = sum(1 for r in recs if r[4] == 503)
    per_worker = collections.Counter(r[0] for r in recs)
    ended = [r for r in d["records"] if frm <= r[2] + r[3] / 1000 < to]
    ended_ok = [r for r in ended if r[4] == 200]
    # LOOPING: it finished a query in the window and came back for another, also in it
    first_end = {}
    for r in ended:
        first_end[r[0]] = min(first_end.get(r[0], r[2] + r[3] / 1000), r[2] + r[3] / 1000)
    looping = {r[0] for r in recs if r[0] in first_end and r[2] >= first_end[r[0]]}
    gaps = {}
    for r in sorted(d["records"], key=lambda r: r[2]):
        if frm <= r[2] < to:
            gaps.setdefault(r[0], []).append(r[2])
    worst_gap = 0.0
    for ts in gaps.values():
        worst_gap = max([worst_gap] + [b - a for a, b in zip(ts, ts[1:])])
    ops = {}
    for r in ok:
        ops.setdefault(r[1], []).append(r[3])
    win = max(0.001, to - frm)
    errs = [e for e in d["errors"] if frm <= e[2] < to]
    return {
        "started": d["n"], "pace": d["pace"], "kind": d["kind"],
        "completed": len(recs), "ok": len(ok), "busy_503": busy,
        "bad_status": sum(1 for r in recs if r[4] not in (200, 503)),
        "errors": len(errs), "error_samples": [e[3] for e in errs[:3]],
        "throughput_qps": round(len(ended_ok) / win, 2),
        **W.summ([r[3] for r in ok]),
        "ops": {k: W.summ(v) for k, v in sorted(ops.items())},
        "workers_finished_cleanly": sum(d["finished"]),
        "unfinished_at_drain": d["unfinished"],
        "workers_looping": len(looping),
        "worst_gap_between_starts_s": round(worst_gap, 1),
        "per_worker_completed": [per_worker.get(i, 0) for i in range(d["n"])],
    }, [r[3] for r in ok]


def client_cpu(client):
    """{pid: cpu seconds} of the load processes; the venv's python.exe is a launcher, so
    its child is what works. Shows the load generators were not themselves saturated."""
    out = {}
    for c in client:
        try:
            root = psutil.Process(c.pid)
            for p in [root] + root.children(recursive=True):
                t = p.cpu_times()
                out[p.pid] = t.user + t.system
        except psutil.Error:
            pass
    return out


def run_cell(a, srv, grants, level, rnd, results_raw):
    L = LEVELS[level]
    cell = pathlib.Path(a.run_dir) / "cells" / f"{level}-r{rnd}"
    cell.mkdir(parents=True, exist_ok=True)
    stop = cell / "STOP"
    t_cell = time.time()
    load, writer = None, None
    lf, wf = cell / "load.json", cell / "write.json"
    far = time.time() + 900
    client = []
    if L["n"]:
        load = spawn(a, "load.py", {
            "port": srv.port, "kind": L["kind"], "n": L["n"], "pace": L["pace"], "stop": str(stop),
            "max_until": far, "out": str(lf), "grants": grants, "ref": REF, "drain_s": a.drain_s,
            "round": rnd}, "load", cell)
        client.append(load)
    if L["write"]:
        writer = spawn(a, "writer.py", {"port": srv.port, "stop": str(stop), "max_until": far,
                                        "out": str(wf), "period": WRITE_PERIOD_S,
                                        "window_after": L.get("window_after", False),
                                        "tag": f"{level}-r{rnd}"}, "writer", cell)
        client.append(writer)
    time.sleep(a.warm_s)                        # warm-up: stated, excluded
    frm = time.time()
    cpu0, _, _ = srv.cpu_rss()
    mach0 = psutil.cpu_percent(None)
    cli0 = client_cpu(client)
    samples = []

    phases = []
    pf = cell / "person.json"
    p_cfg = {"port": srv.port, "phase": "person", "until": time.time() + a.person_s, "out": str(pf),
             "grant": grants[0], "ref": REF, "light": L.get("light", False)}
    pp = spawn(a, "probe.py", p_cfg, "person", cell)

    def sample_until(proc):
        while proc.poll() is None:
            time.sleep(1)
            _, rss, threads = srv.cpu_rss()
            samples.append((rss, threads, psutil.cpu_percent(None), dict(srv.rss_by_name)))
    sample_until(pp)
    phases.append(json.load(open(pf)))
    if L["agent_phase"]:
        af = cell / "agent.json"
        ap = spawn(a, "probe.py", {"port": srv.port, "phase": "agent", "until": time.time() + a.agent_s,
                                   "out": str(af), "grant": grants[0], "ref": REF, "start": rnd,
                                   "ops": L.get("agent_ops")}, "agent", cell)
        sample_until(ap)
        phases.append(json.load(open(af)))
    to = time.time()
    cpu1, rss_end, threads_end = srv.cpu_rss()
    cli1 = client_cpu(client)
    cli_cores = sum(max(0, v - cli0.get(k, v)) for k, v in cli1.items())
    stop.write_text("stop")
    for c in client:
        try:
            c.wait(timeout=a.drain_s + 15)
        except subprocess.TimeoutExpired:
            c.kill()
            log(f"  {level} r{rnd}: client process killed after the drain bound")
    drained = time.time()
    settle_s, settled = srv.quiet(a.settle_s)
    wall = max(0.001, to - frm)
    if writer is not None and L.get("window_after"):
        w = json.load(open(wf))
        phases.append({"records": [r for r in w["after"] if frm <= r[1] < to],
                       "errors": [e for e in w["after_errors"] if frm <= e[1] < to]})
    probes, raw_probes = probes_summary(phases)
    by_process = {}
    for pid, v in cpu1.items():
        p = by_process.setdefault(srv.pid_name.get(pid, "?"), {"cores": 0.0})
        p["cores"] += max(0, v - cpu0.get(pid, v))
    for name, p in by_process.items():
        p["cores"] = round(p["cores"] / wall, 2)
        rss_named = [s[3].get(name, 0) for s in samples] or [srv.rss_by_name.get(name, 0)]
        p["rss_mb_mean"] = round(statistics.mean(rss_named) / 1e6)
        p["rss_mb_max"] = round(max(rss_named) / 1e6)
    row = {
        "level": level, "round": rnd, "at": round(frm, 1),
        "warmup_excluded_s": a.warm_s, "measured_s": round(wall, 1),
        "probes": probes,
        "server": {
            "cores": round(sum(max(0, cpu1[k] - cpu0.get(k, cpu1[k])) for k in cpu1) / wall, 2),
            "rss_mb_mean": round(statistics.mean([s[0] for s in samples] or [rss_end]) / 1e6),
            "rss_mb_max": round(max([s[0] for s in samples] or [rss_end]) / 1e6),
            "threads_end": threads_end,
            "processes": sorted(srv.names()),
            "by_process": by_process},
        "client_cores": round(cli_cores / wall, 2),
        "machine_pct_mean": round(statistics.mean([s[2] for s in samples]), 1) if samples else None,
        "drain_s": round(drained - to, 1), "settle_s": settle_s, "settled": settled,
    }
    raw_bg = None
    if load is not None:
        d = json.load(open(lf))
        row["background"], raw_bg = background_summary(d, frm, to)
    if writer is not None:
        d = json.load(open(wf))
        recs = [r for r in d["records"] if frm <= r[1] < to]
        row["writes"] = {"period_s": d["period"], "completed": len(recs),
                         "per_s": round(len(recs) / wall, 2),
                         "errors": len([e for e in d["errors"] if frm <= e[1] < to]),
                         "error_samples": [e[2] for e in d["errors"][:2]],
                         **W.summ([r[2] for r in recs])}
    bucket = results_raw.setdefault(level, {"probes": {}, "background": [], "write": []})
    for k, v in raw_probes.items():
        bucket["probes"].setdefault(k, []).extend(v)
    if raw_bg:
        bucket["background"].extend(raw_bg)
    if writer is not None:
        bucket["write"].extend(r[2] for r in json.load(open(wf))["records"] if frm <= r[1] < to)
    shutil.rmtree(cell, ignore_errors=True)
    pr = probes
    bg = row.get("background", {})
    log(f"  {level} r{rnd}: topic {pr.get('topic_lookup', {}).get('p50')}/{pr.get('topic_lookup', {}).get('p95')} "
        f"window {pr.get('window_total', {}).get('p50')}/{pr.get('window_total', {}).get('p95')} "
        f"pulse {pr.get('pulse', {}).get('p95')} resolve {pr.get('agent_resolve', {}).get('p50')} "
        f"find {pr.get('agent_find', {}).get('p50')} bg {bg.get('throughput_qps')}q/s {bg.get('workers_looping')}/{bg.get('started')} "
        f"cores {row['server']['cores']} mach {row['machine_pct_mean']} drain {row['drain_s']} settle {settle_s} "
        f"cell {round(time.time() - t_cell)}s")
    return row


def aggregate(runs, raw):
    """Across a level's runs: pooled p50/p95/max/count, and how far the runs differ."""
    out = {"runs": len(runs)}
    names = sorted({k for r in runs for k in r["probes"]})
    probes = {}
    for k in names:
        rows = [r["probes"][k] for r in runs if k in r["probes"]]
        p = W.summ(raw["probes"].get(k, []))
        p["errors"] = sum(x["errors"] for x in rows)
        p["bad_status"] = sum(x["bad_status"] for x in rows)
        p["p50_by_run"] = [x["p50"] for x in rows]
        p["p95_by_run"] = [x["p95"] for x in rows]
        p["count_by_run"] = [x["count"] for x in rows]
        probes[k] = p
    out["probes"] = probes
    bgs = [r["background"] for r in runs if "background" in r]
    if bgs:
        out["background"] = {
            **W.summ(raw["background"]),
            "kind": bgs[0]["kind"], "n": bgs[0]["started"], "pace": bgs[0]["pace"],
            "throughput_qps_by_run": [b["throughput_qps"] for b in bgs],
            "throughput_qps_mean": round(statistics.mean(b["throughput_qps"] for b in bgs), 2),
            "errors": sum(b["errors"] for b in bgs), "busy_503": sum(b["busy_503"] for b in bgs),
            "bad_status": sum(b["bad_status"] for b in bgs),
            "workers_looping_by_run": [b["workers_looping"] for b in bgs],
            "unfinished_at_drain_by_run": [b["unfinished_at_drain"] for b in bgs],
            "worst_gap_s": max(b["worst_gap_between_starts_s"] for b in bgs)}
    w = [r["writes"] for r in runs if "writes" in r]
    if w:
        out["writes"] = {**W.summ(raw["write"]), "per_s_by_run": [x["per_s"] for x in w],
                         "errors": sum(x["errors"] for x in w)}
    out["server"] = {"cores_by_run": [r["server"]["cores"] for r in runs],
                     "cores_mean": round(statistics.mean(r["server"]["cores"] for r in runs), 2),
                     "rss_mb_max": max(r["server"]["rss_mb_max"] for r in runs),
                     "rss_mb_mean": round(statistics.mean(r["server"]["rss_mb_mean"] for r in runs)),
                     "by_process": {name: {
                         "cores_by_run": [r["server"]["by_process"].get(name, {}).get("cores", 0) for r in runs],
                         "cores_mean": round(statistics.mean(r["server"]["by_process"].get(name, {}).get("cores", 0) for r in runs), 2),
                         "rss_mb_max": max(r["server"]["by_process"].get(name, {}).get("rss_mb_max", 0) for r in runs),
                         "rss_mb_mean": round(statistics.mean(r["server"]["by_process"].get(name, {}).get("rss_mb_mean", 0) for r in runs))}
                         for name in sorted({n for r in runs for n in r["server"]["by_process"]})}}
    out["client_cores_mean"] = round(statistics.mean(r["client_cores"] for r in runs), 2)
    ms = [r["machine_pct_mean"] for r in runs if r["machine_pct_mean"] is not None]
    out["machine_pct_by_run"] = ms
    return out


# ---- statement capture: untimed, its own boot, under the same hold ------------------


SHAPE_STR = re.compile(r"'(?:[^']|'')*'")
SHAPE_NUM = re.compile(r"\b\d+(?:\.\d+)?\b")
SHAPE_IN = re.compile(r"\(\s*\?(?:\s*,\s*\?)+\s*\)")


def shape(sql):
    s = SHAPE_STR.sub("?", sql)
    s = SHAPE_NUM.sub("?", s)
    return SHAPE_IN.sub("(?..)", s)[:160]


def load_trace(trace_dir):
    rows = []
    for f in pathlib.Path(trace_dir).glob("trace-*.log"):
        pid = f.stem.split("-")[1]
        for line in open(f, encoding="utf-8", errors="replace"):
            parts = line.rstrip("\n").split("\t", 2)
            if len(parts) == 3:
                try:
                    rows.append((float(parts[0]), pid, parts[1], parts[2]))
                except ValueError:
                    pass
    rows.sort()
    return rows


def count_window(rows, t0, t1):
    inw = [r for r in rows if t0 <= r[0] <= t1]
    # Python's request threads, and every statement of mentis-record's trace: Rust reads only when asked.
    req = [r for r in inw if "process_request" in r[2] or r[2].startswith("rust:")]
    def is_data(sql):
        return sql.split(" ", 1)[0].upper() not in BOOKKEEPING
    shapes = collections.Counter(shape(r[3]) for r in req if is_data(r[3]))
    return {
        "request_thread_statements": len(req),
        "request_thread_data": sum(1 for r in req if is_data(r[3])),
        "request_thread_bookkeeping": sum(1 for r in req if not is_data(r[3])),
        "request_thread_distinct_shapes": len(shapes),
        "all_threads_statements": len(inw),
        "processes": len({r[1] for r in inw}),
        "top_shapes": shapes.most_common(5),
    }


def capture_statements(a, cold_convs):
    log("statement capture: untimed boot with the trace on")
    tdir = pathlib.Path(a.run_dir) / "trace-logs"
    tdir.mkdir(parents=True, exist_ok=True)
    srv = Server(a, "trace", trace_dir=tdir)
    try:
        srv.start()
        port = srv.port
        grants, _, _ = srv.grants(1)
        grant = grants[0]
        windows = []       # (name, phase, t0, t1)

        def timed(name, phase, method, path, body=None, headers=None):
            t0 = time.time()
            _, st, b = W.once(port, method, path, body, headers, timeout=300)
            t1 = time.time()
            windows.append((name, phase, t0, t1 + 0.05, st))
            time.sleep(0.25)    # anything the answer started in the server, kept apart
            return st, b

        def post_window(phase, conv, prefix="window"):
            st, b = timed(prefix + "_collection", phase, "GET", W.collection_path(conv), headers=W.CLIENT)
            ids = [i["id"] for i in json.loads(b).get("items", [])] if st == 200 else []
            if ids:
                timed(prefix + "_posts", phase, "GET", W.posts_path(ids), headers=W.CLIENT)

        def agent(op, phase):
            timed("agent_" + op, phase, "POST", "/api/worker",
                  W.worker_body(op, W.MID, "load", W.WORK_TEXT[0], REF), {W.WORKER: grant})

        def commit(tag):
            # the writer's Turn, on a conversation none of these reads windows, so the record
            # has moved and what is read has not
            _, st, _ = W.once(port, "POST", f"/api/conversations/{W.COMMIT_CONV}/turns",
                           {"author": W.OWNER, "text": f"workload statement pass {tag}", "action": "record-only"},
                           W.CLIENT, timeout=120)
            if st != 200:
                raise SystemExit(f"statement pass: write refused, {st}")
            time.sleep(0.25)

        n_commit = [0]

        def read(name, phase, fn):
            if phase == "post_commit":
                n_commit[0] += 1
                commit(n_commit[0])
            fn()

        def get_read(name, phase, path):
            read(name, phase, lambda: timed(name, phase, "GET", path, headers=W.CLIENT))

        t_idle = time.time()
        time.sleep(5)
        idle = (t_idle, time.time())
        for phase in ("cold", "warm", "warm", "warm", "post_commit", "post_commit"):
            get_read("pulse", phase, "/api/pulse")
            get_read("topic_lookup", phase, "/fluid/api/topics?q=load&limit=8")
            read("window", phase, lambda: post_window(phase, W.MID))
            read("window_big", phase, lambda: post_window(phase, W.BIG, "window_big"))
            get_read("activity", phase, W.ACTIVITY)
            get_read("needs_you", phase, W.NEEDS_YOU)
            get_read("needs_you_items", phase, W.NEEDS_ITEMS)
            get_read("turns", phase, W.turns_path())
            for op in ("resolve", "resolve_conv", "orient", "recall", "find", "kinds", "brief",
                       "work_overview", "governed", "history"):
                read(op, phase, lambda: agent(op, phase))
        srv.stop()
        rows = load_trace(tdir)
        res = {"how": "Python sqlite3 trace callback on every connection in the server's process tree "
                      "(trace/sitecustomize.py), on an untimed boot of its own; one request at a time on a "
                      "quiet server, conversation " + W.MID,
               "note": "A statement run outside Python's sqlite3 is invisible to this: for a candidate that reads "
                       "through its own native connection, a low number here is not evidence of fewer statements.",
               "any_statements_seen": bool(rows),
               "idle_all_threads_per_s": round(len([r for r in rows if idle[0] <= r[0] <= idle[1]]) / (idle[1] - idle[0]), 2),
               "reads": {}}
        reads = {}
        for name, phase, t0, t1, st in windows:
            c = count_window(rows, t0, t1)
            c["status"] = st
            reads.setdefault(name, {"cold": None, "warm_runs": [], "post_commit_runs": []})
            if phase == "cold":
                reads[name]["cold"] = c
            elif phase == "warm":
                reads[name]["warm_runs"].append(c)
            else:
                reads[name]["post_commit_runs"].append(c)
        for name, v in reads.items():
            warm, after = v.pop("warm_runs"), v.pop("post_commit_runs")
            v["warm_data_statements_by_run"] = [w["request_thread_data"] for w in warm]
            v["warm"] = warm[-1] if warm else None
            v["post_commit_data_statements_by_run"] = [w["request_thread_data"] for w in after]
            v["post_commit"] = after[-1] if after else None
        for prefix, total in (("window", "post_window"), ("window_big", "post_window_big")):
            c, p = reads.get(prefix + "_collection"), reads.get(prefix + "_posts")
            if c and p:
                # one commit before the collection and none between it and its posts: the
                # posts read is the one straight after the collection, so its count is what a
                # window costs once the collection has refilled what the two share
                reads[total] = {
                    "cold_data_statements": c["cold"]["request_thread_data"] + p["cold"]["request_thread_data"],
                    "warm_data_statements": c["warm"]["request_thread_data"] + p["warm"]["request_thread_data"],
                    "post_commit_data_statements": c["post_commit"]["request_thread_data"] + p["post_commit"]["request_thread_data"],
                    "note": f"derived: {prefix}_collection + {prefix}_posts"}
        res["reads"] = reads
        return res
    finally:
        srv.stop()


# ---- the run -----------------------------------------------------------------------


def record_delta(brain, baseline_db):
    db = pathlib.Path(brain, "corpus.db")
    base = sqlite3.connect(f"file:{pathlib.Path(baseline_db).as_posix()}?mode=ro", uri=True)
    now = sqlite3.connect(db)
    out = {}
    try:
        for t in ("entry", "operational", "delivery"):
            b = base.execute(f"select max(seq) from {t}").fetchone()[0] or 0
            out[f"new_{t}"] = now.execute(f"select count(*) from {t} where seq > ?", (b,)).fetchone()[0]
        b = base.execute("select max(seq) from operational").fetchone()[0] or 0
        out["new_acts"] = dict(now.execute("select act, count(*) from operational where seq > ? group by act", (b,)).fetchall())
    finally:
        base.close()
        now.close()
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--command", required=True, help="what to start: a JSON array of strings, with "
                    "{brain} {port} {ws} {mars} {run}. See docs/rust/contracts/bench.md")
    ap.add_argument("--code", required=True, help="code directory: what goes on PYTHONPATH, whose commit is recorded")
    ap.add_argument("--label", required=True, help="HOME/results/<label>/")
    ap.add_argument("--port", type=int, default=8831)
    ap.add_argument("--brain", default=str(G.MASTER))
    ap.add_argument("--python", default=PY_DEFAULT)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--levels", default="", help="comma list; default every level")
    ap.add_argument("--cold-boots", type=int, default=0, help="boots for the cold case, beside the main boot's")
    ap.add_argument("--skip-statements", action="store_true")
    ap.add_argument("--warm-s", type=float, default=4.0, dest="warm_s")
    ap.add_argument("--person-s", type=float, default=14.0, dest="person_s")
    ap.add_argument("--agent-s", type=float, default=6.0, dest="agent_s")
    ap.add_argument("--drain-s", type=float, default=45.0, dest="drain_s")
    ap.add_argument("--settle-s", type=float, default=12.0, dest="settle_s")
    ap.add_argument("--boot-quiet-s", type=float, default=120.0, dest="boot_quiet_s")
    ap.add_argument("--warm-walk-s", type=float, default=90.0, dest="warm_walk_s")
    ap.add_argument("--warm-cell-s", type=float, default=20.0, dest="warm_cell_s")
    ap.add_argument("--server-env", action="append", default=[], help="KEY=VALUE for this candidate's server")
    ap.add_argument("--warm-convs", type=int, default=0, dest="warm_convs",
                    help="pilots: warm only this many conversations' windows; 0, every one")
    ap.add_argument("--keep-run-dir", action="store_true")
    a = ap.parse_args()
    if not 8831 <= a.port <= 8839:
        raise SystemExit("this work uses ports 8831-8839")
    a.code = str(pathlib.Path(a.code).resolve())
    command = a.command = parse_command(a.command)
    out = G.RESULTS / a.label
    if (out / "workload.json").exists():
        raise G.Refused(f"{out / 'workload.json'} exists: a result is evidence and is not overwritten; use another label")
    out.mkdir(parents=True, exist_ok=True)
    a.run_dir = str(G.RUN / a.label)
    global PROGRESS
    PROGRESS = out / "progress.log"
    levels = [x for x in a.levels.split(",") if x] or list(LEVELS)
    bad = [x for x in levels if x not in LEVELS]
    if bad:
        raise SystemExit(f"unknown levels {bad}; have {list(LEVELS)}")
    try:
        with __import__("socket").create_connection(("127.0.0.1", a.port), 1):
            raise SystemExit(f"port {a.port} already answers")
    except OSError:
        pass
    binary, brain = binaries(command), G.brain_of(a.brain)
    # From before the first boot to the end, statement boot included. Held: exit 3, nothing run.
    hold = G.take(kind="timed run", holder=f"{os.environ.get('BENCH_HOLDER', '?')} run_workload.py",
                  purpose=f"timed run {a.label}, about 35 minutes", code=a.code)
    hold.watch_binaries(binary)
    started = time.time()
    res = {"schema": W.SCHEMA, "label": a.label, "pilot": a.label.replace("\\", "/").startswith("pilots/"),
           "command": command, "binary": binary, "brain": brain,
           "environment": {"logical_cpus": psutil.cpu_count(), "ram_gb": round(psutil.virtual_memory().total / 1e9, 1),
                           "platform": platform.platform(), "python": platform.python_version(),
                           "sqlite": sqlite3.sqlite_version},
           "config": {"rounds": a.rounds, "warm_s": a.warm_s, "person_s": a.person_s, "agent_s": a.agent_s,
                      "pace_s": PACE_S, "write_period_s": WRITE_PERIOD_S, "mix": W.MIX, "agent_mix": W.AGENT_MIX,
                      "sql_mix": W.SQL_MIX, "cpu_convs": W.CPU_CONVS,
                      "walk_page": W.WALK_PAGE,
                      "convs": W.CONVS, "cold_convs": W.COLD_CONVS, "levels": levels, "cold_boots": a.cold_boots,
                      "level_defs": {k: LEVELS[k] for k in levels},
                      "server_env": a.server_env, "port": a.port,
                      "warm_convs": a.warm_convs},
           "started": time.strftime("%Y-%m-%d %H:%M:%S"), "cold": {}, "levels": {}, "statements": None}
    hold.stamp(res)
    seen = [0]

    def save():
        res["wall_s"] = round(time.time() - started)
        (out / "workload.json").write_text(json.dumps(res, indent=1))
        sightings = hold.sightings() if not hold.record else []
        for x in sightings[seen[0]:]:
            log(f"SIGHTING, this result is invalid: pid {x['pid']} {x['name']}, {x['why']}: {x['cmd'][:120]}")
        seen[0] = max(seen[0], len(sightings))
    srv = None
    raw = {}
    completed = False
    try:
        res["preflight"] = {"checks": hold.checks, "stale_locks_moved_aside": hold.stale, "machine": G.busy_processes()}
        log(f"preflight: gate taken, no other bench work; machine {res['preflight']['machine']['machine_pct']}%")
        save()
        if not a.skip_statements:
            t = time.time()
            res["statements"] = capture_statements(a, W.COLD_CONVS)
            res["statements"]["wall_s"] = round(time.time() - t)
            save()
        cold_all = []
        grants = []

        def cold_phase(srv, boot):
            cdir = pathlib.Path(a.run_dir) / "cold"
            cdir.mkdir(parents=True, exist_ok=True)
            f = cdir / f"cold-{boot}.json"
            cfg = {"port": srv.port, "phase": "cold", "cold_convs": W.COLD_CONVS, "out": str(f),
                   "grant": grants[0], "ref": REF, "wall_bound": 600}
            return run_probe(a, cfg, f"cold-{boot}", cdir, grace=600)

        if a.cold_boots:
            for boot in range(a.cold_boots):
                srv = Server(a, f"cold{boot}")
                srv.start()
                grants = srv.grants(1)[0]
                r = cold_phase(srv, boot)
                cold_all.append(r)
                log(f"cold boot {boot}: up {srv.up_s}s quiet {srv.quiet_s}s")
                srv.stop()
        srv = Server(a, "main")
        srv.start()
        grants, gscope, permits = srv.grants(MAX_GRANTS)
        res["grant"] = {"how": "POST /api/worker/session {runtime: 'workload'} with no MARS and no agent run: the route a "
                               "hand-started session uses. No source change.", **gscope,
                        "gated_ops_admitted": sorted(set(permits or []) & {"find", "recall", "orient", "resolve"})}
        res["server"] = {"up_s": srv.up_s, "quiet_s": srv.quiet_s, "was_quiet": srv.was_quiet,
                         "copied_s": srv.copied_s, "info": srv.info(), "tree_exes": srv.names()}
        log(f"main boot: up {srv.up_s}s quiet {srv.quiet_s}s ({srv.was_quiet}) tree {srv.names()}")
        if a.cold_boots or not a.skip_statements:
            cold_all.append(cold_phase(srv, "main"))
        res["server"]["object_renderer"] = srv.engine_runs()     # after the cold probes: it is a read
        coldp, coldraw = probes_summary(cold_all)
        res["cold"] = {"how": "first reads of a boot, each on a fresh copy, server quiet first, nothing else running",
                       "boots": len(cold_all), "by_probe": coldp,
                       "raw_ms": {k: v for k, v in coldraw.items()}}
        save()
        # warm-up of the server itself: stated, excluded
        t = time.time()
        for conv in W.CONVS[:a.warm_convs or None]:
            _, st, b = W.once(srv.port, "GET", W.collection_path(conv), headers=W.CLIENT, timeout=180)
            ids = [i["id"] for i in json.loads(b).get("items", [])] if st == 200 else []
            if ids:
                W.once(srv.port, "GET", W.posts_path(ids), headers=W.CLIENT, timeout=300)
        windows_s = round(time.time() - t, 1)
        log(f"warm-up windows: {windows_s}s")
        # At about 0.2 s per extraction a whole walk is over 10 minutes (v1 had no engine). A level reads a
        # conversation's newest pages, and each worker starts again at the newest.
        walked, whole, t_walk = 0, True, time.time()
        for conv in W.CONVS:
            before = None
            for _ in range(W.WARM_PAGES):
                if time.time() - t_walk > a.warm_walk_s:
                    whole = False
                    break
                _, st, b = W.once(srv.port, "GET", W.objects_path(conv, before), headers=W.CLIENT, timeout=180)
                walked += 1
                d = json.loads(b) if st == 200 else {}
                before = d.get("before")
                if not before:      # a page with no objects still has older pages
                    break
        for word in W.WORDS[:2]:
            W.once(srv.port, "GET", f"/api/references?q={word}&limit=8", headers=W.CLIENT, timeout=180)
        res["warmup"] = {"windows_s": windows_s, "walk_pages": walked, "walk_pages_per_conv": W.WARM_PAGES,
                         "walk_completed": whole, "walk_s": round(time.time() - t_walk, 1),
                         "then": f"closed-4 for {a.warm_cell_s}s, unmeasured"}
        log(f"warm-up walk: {walked} pages, complete {whole}, {res['warmup']['walk_s']}s")
        if "write" in levels or any(LEVELS[l]["kind"] for l in levels):
            cell = pathlib.Path(a.run_dir) / "warmcell"
            cell.mkdir(parents=True, exist_ok=True)
            p = spawn(a, "load.py", {"port": srv.port, "kind": "mix", "n": 4, "pace": 0, "stop": str(cell / "STOP"),
                                     "max_until": time.time() + a.warm_cell_s, "out": str(cell / "o.json"),
                                     "grants": grants, "ref": REF, "drain_s": a.drain_s}, "warm", cell)
            p.wait(timeout=a.warm_cell_s + a.drain_s + 30)
            d = json.load(open(cell / "o.json"))
            res["warmup"]["warm_cell"] = {"unfinished": d["unfinished"], "completed": len(d["records"])}
        res["warmup"]["quiet_s"], _ = srv.quiet(a.settle_s)
        # A level that writes moves the record, so those run last, after every read level.
        reads = [l for l in levels if not LEVELS[l]["write"]]
        moving = [l for l in levels if LEVELS[l]["write"]]
        rows = {l: [] for l in levels}

        def one(level, r):
            rows[level].append(run_cell(a, srv, grants, level, r, raw))
            res["levels"][level] = {"aggregate": aggregate(rows[level], raw[level]), "runs": rows[level]}
            save()

        for r in range(a.rounds):
            # each round starts elsewhere, so no level always follows the same one
            shift = r * 3 % max(1, len(reads))
            for level in reads[shift:] + reads[:shift]:
                one(level, r)
        for r in range(a.rounds):
            for level in moving:
                one(level, r)
        res["server"]["tree_exes_end"] = srv.names()
        tail = pathlib.Path(srv.dir, "server.log")
        srv.stop()
        with scratch_db(a.brain, a.run_dir) as base_db:
            res["record_delta"] = record_delta(srv.brain, base_db)
        log(f"record delta: {res['record_delta']}")
        res["server"]["log_head"] = tail.read_text(encoding="utf-8", errors="replace")[:1500]
        (out / "raw.json").write_text(json.dumps(raw))
        if not a.keep_run_dir:
            shutil.rmtree(a.run_dir, ignore_errors=True)
        completed = True
    finally:
        if srv:
            srv.stop()
        res["machine_at_end"] = G.busy_processes()
        res["code_after"] = G.commit_of(a.code)
        if (res["code_after"].get("commit"), res["code_after"].get("dirty_files")) != (res["code"].get("commit"), res["code"].get("dirty_files")):
            hold.invalidate(f"the code changed during the run: {res['code']} to {res['code_after']}")
        res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
        res["wall_s"] = round(time.time() - started)
        hold.write_result(out / "workload.json", res, completed=completed)
    iso = res["isolation"]
    log(f"done: wall {res['wall_s']}s; {out / 'workload.json'}; valid {iso['valid']}, {iso['sample_count']} samples, "
        f"{len(iso['sightings'])} sightings, sampler {iso['sampler_cost'].get('core_pct')}% of a core")
    for why in iso["invalid_reasons"]:
        log(f"INVALID: {why}")
    bad = W.bad_statuses(res)
    for why in bad:
        log(f"BAD STATUS: {why}")
    return G.FAILED if bad or not iso["valid"] else 0


if __name__ == "__main__":
    sys.exit(main())
