"""MEASUREMENT ONLY. The one gate for bench work that uses real CPU: timed runs, captures, test
files, builds, answers. Every entry point takes it through `take()`, so none of them holds its
own idea of what the lock is. Part of workload_sha.

    hold = benchgate.take(kind="capture", holder="census", purpose="...", code=CODE_DIR)
    ...                                 # the work
    hold.write_result(path, result)     # stops the sampler, releases, stamps, writes

    benchgate.py run --kind build --holder NAME --purpose WHY --code DIR -- cargo build
    benchgate.py status                 exit 0 free, 1 held by a live process, 2 stale or unreadable
    benchgate.py break --reason WHY     an unreadable lock; never a live holder's
    benchgate.py sha                    the workload_sha this tree would record

WHAT IT DOES
  Lock      HOME/RUNLOCK, by exclusive create, holding JSON: holder, pid, purpose, start time.
            Held by a live process: `take` REFUSES, exit 3, with nothing run. It never waits in
            process, because a process waiting on the bench is itself seen by the sampler and would
            invalidate the run it is waiting for. Waiting belongs in a shell: gate_wait.sh.
  Dead      A holder whose pid is gone (or reused: the create time is checked) is moved aside to
            HOME/stale-locks/ under a breaker file, written to HOME/gate-events.jsonl, and
            named in the new holder's isolation record. It does not invalidate anything itself; what
            the dead holder left running is seen by the first scan, which then refuses.
  Unreadable A lock with no pid in it past a short grace cannot be shown dead: `take` refuses and says
            to use `break`.
  Sampling  A separate process from just after the lock is taken until just before it is released,
            every SAMPLE_S. The first scan finishing clean is the preflight: the work starts after it.
            Any sighting marks the result invalid in the result itself.
  Refusal   `refuse_unless_comparable` is what compare.py and answers.py call. No override exists.

WHERE THINGS ARE
  tools/bench/ holds code only. HOME, outside Git, holds the results, the bundle, the lock and the run
  directories. BENCH_HOME moves it, which is how tests stay off the real one.

WHAT THE SAMPLER CANNOT DO
  A raw process that starts and ends between two samples is not seen (at most SAMPLE_S). Nothing
  here can stop a raw `cargo` or `pytest` from starting: those are detected, not prevented.
"""
import argparse, hashlib, json, os, pathlib, re, shutil, statistics, subprocess, sys, time, uuid

import psutil

MEASURE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path(os.environ.get("BENCH_HOME") or r"C:\Work\Mentis-workspace\day-to-day\r1-bench")
BENCH = HOME
LOCK = HOME / "RUNLOCK"
EVENTS = HOME / "gate-events.jsonl"
STALE_DIR = HOME / "stale-locks"
SAMPLES = HOME / "gate-samples"
GATE_RESULTS = HOME / "gate-results"
RESULTS = HOME / "results"
RUN = HOME / "run"
#: The object reader every candidate's server is given (MENTIS_FLUID_DIST), built from b8e324c's
#: apps/fluid-web. A clone has no dist: without this, object reads answer "not extracted" and the
#: JS engine never runs, which is how v1 ran. Part of the workload's hash.
BUNDLE_DIR = HOME / "bundle"
#: BRAIN-COPY's master: read-only, and never opened through SQLite. Fresh copies are made from it.
MASTER = pathlib.Path(r"C:\Work\Mentis-workspace\r1-fixtures\brain-copy-master")

REFUSED = 3                 # the exit code: nothing ran
FAILED = 4                  # the exit code: it ran, and an invalid run, a bad status or a difference came of it
SAMPLE_S = 2.0
BUSY_EVERY = 30             # samples: the machine's other busy processes, about once a minute
MAX_GAP_S = 30.0            # a longer gap between samples means the run was not watched: invalid
TOOL_CPU_S = 2.0            # a small tool in the bench tree past this much CPU is bench work
GRACE_S = 10.0              # how young a lock with no readable holder may be
FIRST_SAMPLE_BOUND_S = 90.0

BENCH_PORTS = range(8831, 8840)
DAY_TO_DAY_PORTS = {8760: "day-to-day server", 8773: "day-to-day 8773", 8790: "day-to-day 8790", 8791: "day-to-day 8791"}

#: A process with this name is bench work wherever it runs: it would contend for the same cores.
WORK_NAMES = {"cargo", "rustc", "pytest", "py.test", "esbuild", "vite", "vitest", "webpack", "rollup", "tsc"}
#: Each is an entry point or runner of the bench; a python running one of them is bench work.
WORK_SCRIPTS = {"capture.py", "run_tests.py", "run_workload.py", "answers.py", "check_cpu.py", "diag.py",
                "pytest", "py.test", "pytest.py", "gate_demo.py", "load.py", "probe.py", "writer.py"}
UI_BUILD = re.compile(r"(?:^|[\s\\/])(?:vite|esbuild|webpack|rollup|tsc|vitest)(?:\.js|\.cmd|\.mjs)?(?:\s|$)|\brun\s+build\b", re.I)
NODE_LIKE = {"node", "npm", "npx", "pnpm", "yarn", "bun", "deno"}
#: Agent runtimes and what they run beside them: recorded, never bench work.
AGENT_NAMES = {"claude", "codex", "gemini", "mars", "kimi"}
AGENT_CMD = re.compile(r"claude-agent|claude-code|@anthropic-ai|kimi-code|@openai[/\\]codex|"
                       r"from mentis\.worker import serve|mcp_bridge\.py|run_turn\.py", re.I)
#: A shell or terminal in the bench tree is a place, not work: what it runs is seen by itself.
SHELLS = {"bash", "sh", "dash", "zsh", "powershell", "pwsh", "cmd", "conhost", "mintty", "windowsterminal", "openconsole"}
#: Small tools that read: recorded, and bench work only past TOOL_CPU_S of CPU.
TOOLS = {"rg", "grep", "egrep", "git", "ls", "cat", "head", "tail", "sed", "awk", "gawk", "cut", "wc", "find", "sleep",
         "date", "tr", "sort", "uniq", "which", "env", "dirname", "basename", "stat", "tee", "whoami"}
#: Not worth a command line and a cwd each: they do not run bench work and most refuse the read.
NEVER_LOOK = {"system idle process", "system", "registry", "smss", "csrss", "wininit", "winlogon", "services", "lsass",
              "svchost", "fontdrvhost", "dwm", "memory compression", "secure system", "wudfhost", "spoolsv", "dllhost",
              "sihost", "taskhostw", "runtimebroker", "searchhost", "searchindexer", "ctfmon", "audiodg", "wmiprvse",
              "startmenuexperiencehost", "shellexperiencehost", "textinputhost", "lockapp", "msmpeng", "nissrv"}
GATE_STATUS = re.compile(r"benchgate\.py[\"']?\s+status\b", re.I)
GATE_SAMPLER = re.compile(r"benchgate\.py[\"']?\s+sample\b", re.I)


def _tree_forms():
    forms = set()
    for root in (HOME, MEASURE, MASTER):
        b = str(root).replace("\\", "/").lower()
        forms.add(b)
        if len(b) > 2 and b[1] == ":":
            forms.add(f"/{b[0]}{b[2:]}")
    return forms


TREE = _tree_forms()


def in_tree(*texts):
    for t in texts:
        if t:
            low = t.replace("\\", "/").lower()
            if any(f in low for f in TREE):
                return True
    return False


def bare(name):
    n = (name or "").lower()
    return n[:-4] if n.endswith(".exe") else n


def classify(name, argv, cwd="", ports=()):
    """(category, why). Pure, so its rules can be tested. `bench` invalidates a run; `agent`, `shell`
    and `tool` are recorded; `other` is not this gate's business."""
    n = bare(name)
    cmd = " ".join(argv or [])
    bases = {os.path.basename(x.replace("\\", "/")).lower() for x in (argv or [])}
    if GATE_SAMPLER.search(cmd):
        return "shell", "a gate's sampler, which stops with its holder"
    if GATE_STATUS.search(cmd):
        return "tool", "the gate's own status"
    if n in WORK_NAMES:
        return "bench", f"a process named {n}"
    agent = n in AGENT_NAMES or (n in NODE_LIKE or n.startswith("python") or n in SHELLS) and bool(AGENT_CMD.search(cmd))
    python = n.startswith("python") or n in ("py", "pypy", "pypy3")
    if python and not agent:
        hit = bases & WORK_SCRIPTS
        if hit:
            return "bench", f"python running {sorted(hit)[0]}"
    if n in NODE_LIKE and not agent and UI_BUILD.search(cmd):
        return "bench", "a UI build"
    bench_port = [p for p in ports if p in BENCH_PORTS]
    if bench_port:
        return "bench", f"serving on {bench_port[0]}"
    if agent:
        return "agent", "an agent runtime"
    if not in_tree(cmd, cwd):
        return "other", ""
    if n in SHELLS:
        return "shell", "a shell in the bench tree"
    if n in TOOLS:
        return "tool", "a small tool in the bench tree"
    return "bench", "running from the bench tree"


class Refused(SystemExit):
    """Nothing ran. Exit 3 unless caught, with the reason on stderr."""

    def __init__(self, why):
        print(f"benchgate: REFUSED: {why}", file=sys.stderr, flush=True)
        self.why = why
        super().__init__(REFUSED)


def event(what, **kw):
    line = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "t": round(time.time(), 2), "event": what, "pid": os.getpid(), **kw}
    try:
        pathlib.Path(EVENTS).parent.mkdir(parents=True, exist_ok=True)
        with open(EVENTS, "a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
    except OSError as e:
        print("benchgate: could not write an event:", repr(e), file=sys.stderr, flush=True)


# ---- identity -------------------------------------------------------------------------------

#: What the hash covers, relative to tools/bench/, and the bundle in HOME. README and compare.py are outside it.
HASHED = ("benchgate.py", "wl_common.py", "load.py", "probe.py", "writer.py", "run_workload.py", "answers.py",
          "trace/sitecustomize.py")


def workload_sha():
    h = hashlib.sha256()
    for name in HASHED:
        h.update(name.encode())
        h.update((MEASURE / name).read_bytes())
    h.update(b"bundle/render-check.js")
    h.update((BUNDLE_DIR / "render-check.js").read_bytes())
    return h.hexdigest()[:16]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def brain_of(master):
    """What a result ran on, by hashing the file: two snapshots prove nothing about the code."""
    return {"master": str(master), "corpus_db_sha256": sha256_of(pathlib.Path(master, "corpus.db"))}


def commit_of(code):
    """The code a result ran on. An exported tree has no git: BENCH_CODE_COMMIT names its commit."""
    def git(*args):
        try:
            return subprocess.run(["git", "-C", code, *args], capture_output=True, text=True, timeout=30).stdout.strip()
        except OSError:
            return ""
    head = git("rev-parse", "--short", "HEAD")
    given = os.environ.get("BENCH_CODE_COMMIT", "")
    if given and not head:
        return {"dir": code, "commit": given, "given_by": "BENCH_CODE_COMMIT", "branch": "", "dirty_files": None}
    return {"dir": code, "commit": head, "branch": git("branch", "--show-current"),
            "dirty_files": len([x for x in git("status", "--porcelain").splitlines() if x.strip()])}


# ---- the lock -------------------------------------------------------------------------------


def read_lock(path=None):
    """The holder written in the lock, or None if it is absent, or {'unreadable': text}."""
    try:
        text = pathlib.Path(path or LOCK).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        d = json.loads(text)
        if isinstance(d, dict) and "pid" in d:
            return d
    except ValueError:
        pass
    m = re.search(r"\bpid (\d+)", text)      # the format before this gate
    if m:
        return {"pid": int(m.group(1)), "holder": text.strip()[:200], "legacy": True}
    return {"unreadable": text[:200]}


def holder_state(d, lock=None):
    """'live', 'dead' or 'unreadable'."""
    if "unreadable" in d:
        try:
            age = time.time() - pathlib.Path(lock or LOCK).stat().st_mtime
        except OSError:
            return "dead"
        return "live" if age < GRACE_S else "unreadable"
    try:
        p = psutil.Process(d["pid"])
        if d.get("create_time") and abs(p.create_time() - d["create_time"]) > 2:
            return "dead"       # the pid has been reused
        if p.status() == psutil.STATUS_ZOMBIE:
            return "dead"
        return "live"
    except psutil.NoSuchProcess:
        return "dead"
    except psutil.Error:
        return "live"           # it exists and will not say more


def break_stale(d, why, lock=None):
    """Move a lock aside, once, under a breaker file. Returns what was recorded, or None if somebody
    else got there first. The lock is read again under the breaker, so a live one is never moved."""
    lock = pathlib.Path(lock or LOCK)
    breaker = lock.with_name(lock.name + ".breaking")
    try:
        fd = os.open(breaker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        other = read_lock(breaker) or {}
        try:
            age = time.time() - breaker.stat().st_mtime
        except OSError:
            return None
        if age > GRACE_S and holder_state(other, breaker) != "live":
            breaker.unlink(missing_ok=True)
        return None
    try:
        os.write(fd, json.dumps({"pid": os.getpid(), "create_time": psutil.Process().create_time()}).encode())
        os.close(fd)
        now = read_lock(lock)
        if now is None or now != d:
            return None
        (lock.parent / STALE_DIR.name).mkdir(exist_ok=True)
        kept = lock.parent / STALE_DIR.name / f"RUNLOCK-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        os.replace(lock, kept)
        rec = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "was": d, "why": why, "kept_as": kept.name, "by_pid": os.getpid()}
        event("stale lock moved aside", **rec)
        print(f"benchgate: stale lock moved aside ({why}): {json.dumps(d)[:300]}; kept as {kept.name}", file=sys.stderr, flush=True)
        return rec
    finally:
        breaker.unlink(missing_ok=True)


def acquire(me, lock=None):
    """Exclusive create, or Refused. Returns the stale locks it moved aside to get there."""
    lock = pathlib.Path(lock or LOCK)
    lock.parent.mkdir(parents=True, exist_ok=True)
    stale = []
    body = json.dumps(me, indent=1)
    for _ in range(20):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            d = read_lock(lock)
            if d is None:
                continue
            state = holder_state(d, lock)
            if state == "dead":
                rec = break_stale(d, "its holder is not running", lock)
                if rec:
                    stale.append(rec)
                else:
                    time.sleep(0.2)
                continue
            if state == "unreadable":
                event("refused", wanted=me, unreadable=d["unreadable"])
                raise Refused(f"{lock} names no holder, so it cannot be shown dead: {d['unreadable']!r}. "
                              "Look, then: benchgate.py break --reason WHY")
            event("refused", wanted={k: me[k] for k in ("holder", "purpose")}, held_by=d)
            raise Refused(f"held by {d.get('holder')}, pid {d.get('pid')}, since {d.get('started', '?')}: {d.get('purpose', '')}")
        os.write(fd, body.encode())
        os.close(fd)
        return stale
    raise Refused(f"{lock} could not be taken: it kept changing")


class Hold:
    """A held lock with its sampler running. Create it with `take`."""

    def __init__(self, kind, holder, purpose, code):
        self.kind, self.holder, self.purpose = kind, holder, purpose
        self.code = commit_of(code) if isinstance(code, str) else dict(code or {})
        self.workload_sha = workload_sha()
        self.token = uuid.uuid4().hex
        self.lock = LOCK
        self.reasons, self.checks, self.stale = [], [], []
        self.record = None
        self.sampler = None
        self.binary = []

    # the sampler's file: one JSON line per sample
    def _start_sampler(self):
        SAMPLES.mkdir(parents=True, exist_ok=True)
        self.samples = SAMPLES / f"{self.token}.jsonl"
        self.stop_file = SAMPLES / f"{self.token}.stop"
        self.sampler = subprocess.Popen(
            [sys.executable, "-B", str(MEASURE / "benchgate.py"), "sample", "--holder", str(os.getpid()),
             "--token", self.token, "--out", str(self.samples), "--stop", str(self.stop_file), "--lock", str(self.lock)],
            stdout=subprocess.DEVNULL, stderr=open(str(self.samples) + ".err", "w"), cwd=str(MEASURE))
        t0 = time.time()
        while not self.read_samples()[0]:
            if self.sampler.poll() is not None or time.time() - t0 > FIRST_SAMPLE_BOUND_S:
                return False
            time.sleep(0.05)
        return True

    def read_samples(self):
        rows = []
        try:
            with open(self.samples, encoding="utf-8") as f:
                for line in f:
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        pass            # the line being written
        except OSError:
            pass
        return rows, summarise(rows)

    def sightings(self):
        return self.read_samples()[1]["sightings"]

    def invalidate(self, why):
        self.reasons.append(why)

    def watch_binaries(self, binary):
        """[{path, sha256}]: a binary that changes during the work invalidates it, as the code does."""
        self.binary = binary

    def stamp(self, result):
        """Identity now; the isolation record says it is in progress until `finish`."""
        result["workload_sha"] = self.workload_sha
        result["code"] = self.code
        result["isolation"] = self.record or {"state": "in progress", "holder": self.holder, "token": self.token}
        return result

    def finish(self, completed=True):
        """Stop the sampler, release the lock, return the isolation record. Safe to call twice."""
        if self.record:
            return self.record
        if not completed:
            self.reasons.append("the work did not complete")
        rows, s = [], summarise([])
        if self.sampler:
            self.stop_file.write_text("stop")
            try:
                self.sampler.wait(30)
            except subprocess.TimeoutExpired:
                self.sampler.kill()
                self.reasons.append("the sampler had to be killed")
            rows, s = self.read_samples()
            for f in (self.samples, self.stop_file, pathlib.Path(str(self.samples) + ".err")):
                pathlib.Path(f).unlink(missing_ok=True)
        now = read_lock(self.lock)
        kept = bool(now) and now.get("token") == self.token
        if kept:
            pathlib.Path(self.lock).unlink(missing_ok=True)
        else:
            self.reasons.append(f"the lock was not ours at release: {json.dumps(now)[:200]}")
        released = time.strftime("%Y-%m-%d %H:%M:%S")
        sha_end = workload_sha()
        self.checks.append({"check": "workload_sha unchanged to the end", "ok": sha_end == self.workload_sha})
        if sha_end != self.workload_sha:
            self.reasons.append(f"workload_sha changed during the work: {self.workload_sha} to {sha_end}")
        for b in self.binary:
            try:
                now_sha = sha256_of(b["path"])
            except OSError as e:
                now_sha = repr(e)
            self.checks.append({"check": f"{b['path']} unchanged to the end", "ok": now_sha == b["sha256"]})
            if now_sha != b["sha256"]:
                self.reasons.append(f"a binary changed during the work: {b['path']}, {b['sha256']} to {now_sha}")
        self.checks.append({"check": "sampled throughout", "max_gap_s": s["max_gap_s"], "ok": s["count"] > 0 and s["max_gap_s"] <= MAX_GAP_S})
        if not s["count"]:
            self.reasons.append("no samples")
        elif s["max_gap_s"] > MAX_GAP_S:
            self.reasons.append(f"not watched for {s['max_gap_s']} s: the longest gap between samples")
        self.checks.append({"check": "lock held by this token at every sample", "ok": s["lock_lost_samples"] == 0})
        if s["lock_lost_samples"]:
            self.reasons.append(f"the lock was missing or another's at {s['lock_lost_samples']} samples")
        for x in s["sightings"]:
            self.reasons.append(f"seen at {x['first_seen']}, {x['samples']} samples: pid {x['pid']} {x['name']}, {x['why']}: {x['cmd'][:120]}")
        self.record = {
            "state": "released", "kind": self.kind, "holder": self.holder, "holder_pid": os.getpid(), "purpose": self.purpose,
            "token": self.token, "acquired_at": self.acquired_at, "released_at": released,
            "stale_locks_moved_aside": self.stale, "checks": self.checks,
            "sample_interval_s": SAMPLE_S, "sample_count": s["count"], "first_sample": s["first"], "last_sample": s["last"],
            "max_gap_between_samples_s": s["max_gap_s"], "sampler_cost": s["cost"],
            "sightings": s["sightings"], "expected_agents_and_servers": s["expected"], "shells_and_tools_in_tree": s["tree"],
            "machine_busy_context": s["busy"], "valid": not self.reasons, "invalid_reasons": self.reasons,
        }
        event("released", holder=self.holder, purpose=self.purpose, token=self.token, valid=not self.reasons, reasons=self.reasons)
        return self.record

    def write_result(self, path, result, completed=True):
        self.finish(completed)
        self.stamp(result)
        tmp = pathlib.Path(str(path) + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1, ensure_ascii=False)
        os.replace(tmp, path)
        return result


def summarise(rows):
    """What the sampler saw, from its lines."""
    out = {"count": 0, "first": None, "last": None, "max_gap_s": 0.0, "lock_lost_samples": 0, "sightings": [], "expected": [],
           "tree": [], "busy": {"samples": 0, "machine_pct_by_sample": [], "processes": []},
           "cost": {"cpu_s": None, "wall_s": None, "core_pct": None, "scan_ms_p50": None, "scan_ms_max": None}}
    ticks = [r for r in rows if "tick" in r]
    if not ticks:
        return out
    ts = [r["t"] for r in ticks]
    out["count"] = len(ticks)
    out["first"] = time.strftime("%H:%M:%S", time.localtime(ts[0]))
    out["last"] = time.strftime("%H:%M:%S", time.localtime(ts[-1]))
    out["max_gap_s"] = round(max([b - a for a, b in zip(ts, ts[1:])], default=0.0), 1)
    out["lock_lost_samples"] = sum(1 for r in ticks if not r.get("lock_ok", True))
    procs, seen = {}, {}
    for r in rows:
        for p in r.get("new", []):
            procs[p["key"]] = p
        if "tick" in r:
            for k in r.get("bench", []):
                s = seen.setdefault(k, {"first": r["t"], "last": r["t"], "samples": 0})
                s["last"] = r["t"]
                s["samples"] += 1
    for k, s in seen.items():
        p = procs.get(k, {"pid": k, "name": "?", "cmd": "", "why": "?"})
        out["sightings"].append({"pid": p["pid"], "name": p["name"], "why": p.get("why_now") or p["why"], "cmd": p["cmd"], "cwd": p.get("cwd", ""),
                                 "first_seen": time.strftime("%H:%M:%S", time.localtime(s["first"])),
                                 "last_seen": time.strftime("%H:%M:%S", time.localtime(s["last"])), "samples": s["samples"]})
    for p in procs.values():
        row = {"pid": p["pid"], "name": p["name"], "cmd": p["cmd"][:140], "first_seen": p["first_seen"]}
        if p["category"] == "agent" or p.get("role"):
            out["expected"].append({**row, "role": p.get("role") or "agent runtime"})
        elif p["category"] in ("shell", "tool"):
            out["tree"].append({**row, "what": p["category"]})
    busy = {}
    machine = []
    for r in rows:
        if "busy" in r:
            machine.append(r["machine_pct"])
            for x in r["busy"]:
                b = busy.setdefault(x["pid"], {"pid": x["pid"], "name": x["name"], "role": x.get("role", ""), "pcts": []})
                b["pcts"].append(x["pct"])
    out["busy"] = {"samples": len(machine), "machine_pct_by_sample": machine, "over_5pct_of_a_core": sorted(
        ({"pid": b["pid"], "name": b["name"], "role": b["role"], "samples": len(b["pcts"]), "pct_of_a_core_max": max(b["pcts"]),
          "pct_of_a_core_mean": round(statistics.mean(b["pcts"]), 1)} for b in busy.values()),
        key=lambda b: -b["pct_of_a_core_mean"] * b["samples"])[:25]}
    ms = sorted(r["ms"] for r in ticks)
    wall = ts[-1] - ts[0]
    cpu = ticks[-1]["cpu_s"]
    out["cost"] = {"how": "measured by the sampler in its own process: process_time, and wall per scan",
                   "cpu_s": round(cpu, 2), "wall_s": round(wall, 1), "core_pct": round(100 * cpu / wall, 2) if wall > 0 else None,
                   "first_scan_ms": round(ticks[0]["ms"], 1), "scan_ms_p50": round(ms[len(ms) // 2], 1), "scan_ms_max": round(ms[-1], 1)}
    return out


def busy_processes(window_s=2.0, over_pct=5.0):
    """Everything on the machine using over 5% of one core across a short window."""
    procs = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            p.cpu_percent(None)
            procs.append(p)
        except psutil.Error:
            pass
    psutil.cpu_percent(None)
    time.sleep(window_s)
    out = []
    for p in procs:
        try:
            pct = p.cpu_percent(None)
            if pct >= over_pct and p.pid != 0 and p.info["name"] != "System Idle Process":
                out.append({"pid": p.pid, "name": p.info["name"], "pct_of_one_core": round(pct, 1),
                            "cmd": " ".join(p.cmdline())[:120]})
        except psutil.Error:
            pass
    return {"machine_pct": psutil.cpu_percent(None), "over_5pct_of_a_core": sorted(out, key=lambda x: -x["pct_of_one_core"])}


def take(kind, holder, purpose, code, require_commit=True):
    """The lock, the first clean scan and a running sampler; or Refused, with nothing run."""
    hold = Hold(kind, holder, purpose, code)
    if require_commit and not hold.code.get("commit"):
        event("refused", wanted={"holder": holder, "purpose": purpose}, why="no code commit", code=hold.code)
        raise Refused(f"no code commit for {hold.code.get('dir')}: a result must say what it ran on. An exported tree "
                      "gives it with BENCH_CODE_COMMIT")
    me = {"holder": holder, "pid": os.getpid(), "create_time": psutil.Process().create_time(), "purpose": purpose,
          "kind": kind, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "token": hold.token}
    hold.stale = acquire(me, hold.lock)
    hold.acquired_at = me["started"]
    event("taken", holder=holder, purpose=purpose, kind=kind, token=hold.token, stale_moved=len(hold.stale))
    ok = hold._start_sampler()
    rows, s = hold.read_samples()
    if not ok or s["sightings"]:
        why = "the sampler did not start" if not ok else "other bench work is running: " + "; ".join(
            f"pid {x['pid']} {x['name']} ({x['why']}): {x['cmd'][:100]}" for x in s["sightings"])
        if hold.sampler and hold.sampler.poll() is None:
            hold.stop_file.write_text("stop")
            try:
                hold.sampler.wait(30)
            except subprocess.TimeoutExpired:
                hold.sampler.kill()
        for f in (hold.samples, hold.stop_file, pathlib.Path(str(hold.samples) + ".err")):
            pathlib.Path(f).unlink(missing_ok=True)
        pathlib.Path(hold.lock).unlink(missing_ok=True)
        event("refused", wanted={"holder": holder, "purpose": purpose}, why=why)
        raise Refused(why)
    hold.checks.append({"check": "lock taken by exclusive create", "ok": True})
    hold.checks.append({"check": "first scan before any work: names, scripts, UI builds, ports 8831-8839, bench tree",
                        "found": [], "ok": True, "scan_ms": s["cost"]["first_scan_ms"]})
    return hold


# ---- what may be compared ------------------------------------------------------------------


def why_not_a_candidate(label, r):
    """Reasons this one result cannot pass as a candidate. Empty: it can."""
    why = []
    if str(label).replace("\\", "/").startswith("pilots/") or r.get("pilot"):
        why.append("it is a pilot")
    if not r.get("workload_sha"):
        why.append("it records no workload_sha")
    if not (r.get("brain") or {}).get("corpus_db_sha256"):
        why.append("it records no brain digest")
    iso = r.get("isolation")
    if not iso:
        why.append("it has no isolation record")
    elif iso.get("state") != "released":
        why.append("its isolation record is unfinished: the holder never released")
    elif iso.get("valid") is not True:
        why.append("it is marked invalid: " + "; ".join(iso.get("invalid_reasons") or ["no reason given"]))
    return why


def refusals(results):
    """Everything wrong with comparing these {label: result}."""
    out = [f"{k}: {w}" for k, r in results.items() for w in why_not_a_candidate(k, r)]
    shas = {r.get("workload_sha") for r in results.values()}
    if len(shas) > 1:
        out.append("workload_sha differs: " + ", ".join(f"{k} {r.get('workload_sha')}" for k, r in results.items()))
    brains = {(r.get("brain") or {}).get("corpus_db_sha256") for r in results.values()}
    if len(brains) > 1:
        out.append("the Brain differs: " + ", ".join(
            f"{k} {(r.get('brain') or {}).get('corpus_db_sha256')}" for k, r in results.items()))
    now = workload_sha()
    stale = [k for k, r in results.items() if r.get("workload_sha") and r.get("workload_sha") != now]
    if stale:
        out.append(f"this tree's workload_sha is {now}, which {', '.join(stale)} did not run")
    return out


def refuse_unless_comparable(results):
    """Called by every comparison. There is no flag for it."""
    why = refusals(results)
    if why:
        event("comparison refused", labels=list(results), reasons=why)
        raise Refused("comparison refused:\n  " + "\n  ".join(why))


# ---- the sampler: its own process -----------------------------------------------------------


def ppid_map():
    return psutil._psplatform.ppid_map()


class Scanner:
    """One scan a tick. Reads a command line and a cwd only when a pid first appears."""

    def __init__(self, holder_pid):
        self.holder = holder_pid
        self.holder_ctime = psutil.Process(holder_pid).create_time()
        self.ancestors = {p.pid for p in psutil.Process(holder_pid).parents()}
        self.ours = {holder_pid, os.getpid()}
        self.known = {}             # pid -> what we know of it
        self.cpu_last, self.cpu_t = {}, None

    def look(self, pid, ports):
        try:
            p = psutil.Process(pid)
            name = p.name()
            ctime = p.create_time()
        except psutil.Error:
            return None
        cmd, argv, cwd = "", [], ""
        if bare(name) not in NEVER_LOOK:
            try:
                argv = p.cmdline()
                cmd = " ".join(argv)
            except psutil.Error:
                pass
            try:
                cwd = p.cwd()
            except psutil.Error:
                pass
        category, why = classify(name, argv, cwd, ports)
        return {"pid": pid, "key": f"{pid}:{round(ctime)}", "name": name, "argv": argv, "cmd": cmd[:400], "cwd": cwd[:200],
                "category": category, "why": why, "ctime": ctime, "first_seen": time.strftime("%H:%M:%S"), "proc": p}

    def tick(self):
        pmap = ppid_map()
        listening = {}
        try:
            for c in psutil.net_connections("tcp"):
                if c.status == psutil.CONN_LISTEN and c.pid and c.laddr:
                    listening.setdefault(c.pid, set()).add(c.laddr.port)
        except psutil.Error:
            pass
        for pid in list(self.known):
            if pid not in pmap:
                del self.known[pid]
        self.ours &= set(pmap) | {self.holder}
        # whatever the holder started, however deep, stays ours while it lives
        children = {}
        for pid, parent in pmap.items():
            children.setdefault(parent, []).append(pid)
        stack = list(self.ours)
        while stack:
            for kid in children.get(stack.pop(), []):
                if kid not in self.ours:
                    try:
                        if psutil.Process(kid).create_time() + 1 < self.holder_ctime:
                            continue            # a parent pid that has been reused
                    except psutil.Error:
                        continue
                    self.ours.add(kid)
                    stack.append(kid)
        new, bench = [], []
        for pid in pmap:
            if pid in self.ours or pid in self.ancestors or pid in (0, 4):
                continue
            ports = sorted(listening.get(pid, ()))
            k = self.known.get(pid)
            if k is None or (ports and set(ports) - k.get("ports", set())):
                fresh = self.look(pid, ports)
                if fresh is None:
                    continue
                fresh["ports"] = set(ports)
                roles = [DAY_TO_DAY_PORTS[p] for p in ports if p in DAY_TO_DAY_PORTS]
                if roles:
                    fresh["role"] = roles[0]
                elif bare(fresh["name"]) == "mars":
                    fresh["role"] = "MARS"
                self.known[pid] = k = fresh
                if k["category"] != "other" or roles:
                    new.append({x: k[x] for x in ("pid", "key", "name", "cmd", "cwd", "category", "why", "first_seen")} | ({"role": k["role"]} if k.get("role") else {}))
            if k["category"] == "tool" and not k.get("promoted"):
                try:
                    t = k["proc"].cpu_times()
                    if t.user + t.system > TOOL_CPU_S:
                        k["category"], k["promoted"] = "bench", True
                        k["why"] = f"a small tool in the bench tree, past {TOOL_CPU_S} s of CPU"
                        new.append({x: k[x] for x in ("pid", "key", "name", "cmd", "cwd", "category", "why", "first_seen")})
                except psutil.Error:
                    pass
            if k["category"] == "bench":
                bench.append(k["key"])
        return new, bench, pmap

    def busy(self, pmap):
        """Every other process's use of a core since the last call. The costly part of a sample."""
        now, t = {}, time.time()
        for pid in pmap:
            if pid in self.ours or pid == 0:
                continue
            try:
                c = psutil.Process(pid).cpu_times()
                now[pid] = c.user + c.system
            except psutil.Error:
                pass
        out = []
        if self.cpu_t is not None:
            span = max(0.1, t - self.cpu_t)
            for pid, v in now.items():
                pct = 100 * (v - self.cpu_last.get(pid, v)) / span
                if pct >= 5:
                    k = self.known.get(pid) or {}
                    name = k.get("name")
                    if name is None:
                        try:
                            name = psutil.Process(pid).name()
                        except psutil.Error:
                            name = "?"
                    out.append({"pid": pid, "name": name, "pct": round(pct, 1), "role": k.get("role", "")})
        self.cpu_last, self.cpu_t = now, t
        return out


def sample_main(a):
    scan = Scanner(a.holder)
    lock = pathlib.Path(a.lock)
    stop = pathlib.Path(a.stop)
    n = 0
    psutil.cpu_percent(None)
    with open(a.out, "a", encoding="utf-8", buffering=1) as f:
        while True:
            t0 = time.perf_counter()
            new, bench, pmap = scan.tick()
            d = read_lock(lock) or {}
            row = {"tick": n, "t": time.time(), "bench": bench, "new": new, "lock_ok": d.get("token") == a.token}
            if n % BUSY_EVERY == 0:
                row["busy"] = scan.busy(pmap)
                row["machine_pct"] = psutil.cpu_percent(None)
            row["ms"] = (time.perf_counter() - t0) * 1000
            row["cpu_s"] = time.process_time()
            f.write(json.dumps(row) + "\n")
            n += 1
            if a.holder not in pmap:
                return
            end = time.time() + max(0.05, SAMPLE_S - (time.perf_counter() - t0))
            while time.time() < end:
                if stop.exists():
                    return
                time.sleep(min(0.25, max(0.01, end - time.time())))


# ---- the command line ------------------------------------------------------------------------


def status_main():
    d = read_lock()
    if d is None:
        print("free")
        return 0
    state = holder_state(d)
    print(state, json.dumps(d))
    return 1 if state == "live" else 2


def break_main(a):
    d = read_lock()
    if d is None:
        print("free: nothing to break")
        return 0
    if holder_state(d) == "live":
        print("REFUSED: its holder is running:", json.dumps(d), file=sys.stderr)
        return REFUSED
    rec = break_stale(d, a.reason)
    print(json.dumps(rec))
    return 0 if rec else 1


def run_main(a):
    """A build, or anything else that must go through the gate and is not an entry point itself."""
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    if not cmd:
        print("nothing to run", file=sys.stderr)
        return 2
    if a.commit:
        code = {"dir": a.code or os.getcwd(), "commit": a.commit, "given_by": "--commit"}
    else:
        code = a.code or os.getcwd()
    hold = take(kind=a.kind, holder=a.holder, purpose=a.purpose, code=code)
    t = time.time()
    rc = 127
    try:
        exe = shutil.which(cmd[0]) or cmd[0]
        rc = subprocess.run([exe] + cmd[1:]).returncode
    finally:
        GATE_RESULTS.mkdir(parents=True, exist_ok=True)
        out = pathlib.Path(a.result) if a.result else GATE_RESULTS / f"{time.strftime('%Y%m%d-%H%M%S')}-{a.kind}-{os.getpid()}.json"
        hold.write_result(out, {"kind": a.kind, "cmd": cmd, "rc": rc, "seconds": round(time.time() - t, 1)}, completed=rc != 127)
        print(f"benchgate: {a.kind} rc {rc}; valid {hold.record['valid']}; {out}", file=sys.stderr, flush=True)
    return rc


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="what", required=True)
    sub.add_parser("status")
    sub.add_parser("sha")
    b = sub.add_parser("break")
    b.add_argument("--reason", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--holder", type=int, required=True)
    s.add_argument("--token", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--stop", required=True)
    s.add_argument("--lock", required=True)
    r = sub.add_parser("run")
    r.add_argument("--kind", default="build")
    r.add_argument("--holder", required=True)
    r.add_argument("--purpose", required=True)
    r.add_argument("--code", help="the code directory this runs on")
    r.add_argument("--commit", help="the commit, for what is not a git directory")
    r.add_argument("--result", help="where the result goes; default HOME/gate-results/")
    r.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    if a.what == "status":
        return status_main()
    if a.what == "sha":
        print(workload_sha())
        return 0
    if a.what == "break":
        return break_main(a)
    if a.what == "sample":
        return sample_main(a)
    return run_main(a)


if __name__ == "__main__":
    sys.exit(main())
