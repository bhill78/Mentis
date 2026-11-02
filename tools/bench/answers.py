"""MEASUREMENT ONLY. What a candidate ANSWERED, since status and timing cannot show it returned
the right thing. It records normalised answers for a fixed list of reads on a fresh copy of the
record, one at a time on a quiet server, and compares them with another result's. It judges
nothing: each difference it lists is for a person to call a defect or an intended change.

    answers.py record --command JSON --code DIR [--brain DIR] --label C0 [--twice]   HOME/results/<label>/answers.json
    answers.py compare C0 S                             HOME/results/S/answers-vs-C0.md
    answers.py selftest C0                              a changed answer must be reported

--twice records on a second fresh copy as well and compares the two: anything that still differs
on the same code is a field normalisation has missed.

WHAT IS NORMALISED, by value and not by key, so a field that holds the record's own data is still
compared. A normalised value cannot show a difference; the counts are kept in `normalised`.
  minted ids    an ent-/opr-/adm-/def- id the copy does not hold was minted by this boot (the
                session, its grant, the after-commit Turn). <new-1>, <new-2> in order of first
                appearance per answer, so a repeat or a reordering of them still shows.
  this run's    a timestamp later than the newest in the copy. A time the record holds is compared.
  time
  paths         this run's directory and the bundle's directory, which differ per run.
  KEYS          the short list in VOLATILE_KEYS: what one answer says about the process and not
                the record. Each is listed with its reason. Their values show no difference at all.

Each recording goes through benchgate: held by somebody else it refuses, exit 3, with nothing run,
and each answers file carries its own workload_sha, code commit and isolation record. `compare`
refuses, with no override, a result whose hash differs, which has no isolation record, or which is
marked invalid, or which ran on a different Brain. `selftest` tests the differ and passes nothing as
a candidate.

Exit: FAILED, 4, on any difference, an invalid recording, a read not answered 200 or a self-check
failure. REFUSED, 3, when nothing ran. A label that already has answers is refused: a result is evidence.
"""
import argparse, calendar, json, os, pathlib, re, shutil, sqlite3, sys, time, types

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_workload as RW
import benchgate as G
import wl_common as W

ID = re.compile(r"\b(?:ent|opr|adm|def)-[0-9a-f]{12}\b")
ISO = re.compile(r"\b(20\d\d-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?)(?:Z|[+-]\d\d:\d\d)?")
#: key -> why it says nothing about what was answered. Filled only from what --twice showed differs.
VOLATILE_KEYS = {}
ROOT = "ent-ca4a27445105"     # census's fixture: the post in MID's window with the most replies
ANSWER_WORD = "workload answers after a commit"


def routes():
    """(name, GET path) in a fixed order. Windows are asked by the ids the collection named."""
    gets = [("pulse", "/api/pulse")]
    for q in W.TOPIC_WORDS + ["zzzz"]:
        gets.append((f"topics {q}", f"/fluid/api/topics?q={q}&limit=8"))
    gets += [("names", f"/fluid/api/names?ids={W.MID},{W.BIG}"),
             ("participants", "/fluid/api/participants?limit=100"),
             ("collection mid", W.collection_path(W.MID)),
             ("collection big", W.collection_path(W.BIG)),
             ("about mid", f"/fluid/api/conversations?ids={W.MID}"),
             ("activity", W.ACTIVITY),
             ("needs_you", W.NEEDS_YOU),
             ("needs_you_items", W.NEEDS_ITEMS),
             ("home briefing", "/fluid/api/home/briefing?limit=30"),
             ("home work", "/fluid/api/home/work?limit=30"),
             ("turns", W.turns_path()),
             ("objects page mid", W.objects_path(W.MID, None)),
             ("objects post", f"/fluid/api/objects?post={ROOT}"),
             ("objects thread", f"/fluid/api/objects?thread={ROOT}"),
             ("thread", f"/fluid/api/collections/thread?root={ROOT}&limit=50"),
             ("stream", "/fluid/api/collections/stream?limit=50"),
             ("latest", "/fluid/api/latest?limit=30"),
             ("references load", "/api/references?q=load&limit=8"),
             ("references ref", f"/api/references?ref={ROOT}"),
             ("api conversations", "/api/conversations"),
             ("api work", "/api/work"),
             ("api owed", "/api/owed")]
    return gets


AGENT_OPS = ["resolve", "resolve_conv", "orient", "recall", "find", "kinds", "brief", "work_overview",
             "governed", "history"]


class Scrub:
    def __init__(self, known, newest, run_dirs):
        self.known, self.newest, self.dirs = known, newest, run_dirs
        self.counts = {"minted_ids": 0, "this_runs_time": 0, "paths": 0, "volatile_keys": 0}
        self.keys = {}

    def text(self, s, new):
        for d in self.dirs:
            for form in (d, d.replace("\\", "\\\\"), d.replace("\\", "/")):
                if form in s:
                    self.counts["paths"] += s.count(form)
                    s = s.replace(form, "<run>")

        def one(m):
            i = m.group(0)
            if i in self.known:
                return i
            self.counts["minted_ids"] += 1
            return new.setdefault(i, f"<new-{len(new) + 1}>")

        def when(m):
            try:
                t = calendar.timegm(time.strptime(m.group(1).replace("T", " ")[:16], "%Y-%m-%d %H:%M"))
            except ValueError:
                return m.group(0)
            if t > self.newest:             # read as UTC; a local time that slips past shows in --twice
                self.counts["this_runs_time"] += 1
                return "<now>"
            return m.group(0)
        return ISO.sub(when, ID.sub(one, s))

    def walk(self, v, new, key=None):
        if key in VOLATILE_KEYS:
            self.counts["volatile_keys"] += 1
            self.keys[key] = self.keys.get(key, 0) + 1
            return "<volatile>"
        if isinstance(v, dict):
            out = {}
            for k, x in v.items():
                out[self.text(k, new)] = self.walk(x, new, k)
            return out
        if isinstance(v, list):
            return [self.walk(x, new) for x in v]
        if isinstance(v, str):
            return self.text(v, new)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and self.newest < v < time.time() + 86400:
            self.counts["this_runs_time"] += 1
            return "<now>"
        return v

    def answer(self, status, body):
        new = {}
        try:
            return {"status": status, "json": self.walk(json.loads(body), new)}
        except ValueError:
            return {"status": status, "text": self.text(body.decode("utf-8", "replace"), new)[:20000]}


def known_ids(db):
    c = sqlite3.connect(f"file:{pathlib.Path(db).as_posix()}?mode=ro", uri=True)
    try:
        ids = {r[0] for r in c.execute("select id from entry")}
        ids |= {r[0] for r in c.execute("select id from operational")}
        newest = max(c.execute("select max(recorded_at) from entry").fetchone()[0],
                     c.execute("select max(at) from operational").fetchone()[0])
    finally:
        c.close()
    return ids, float(newest)


def record_once(a, tag):
    ns = types.SimpleNamespace(code=a.code, brain=a.brain, command=a.command, port=a.port,
                               server_env=a.server_env, boot_quiet_s=120.0,
                               run_dir=str(G.RUN / f"answers-{a.label}-{tag}"))
    binary, brain = RW.binaries(a.command), G.brain_of(a.brain)
    hold = G.take(kind="answers", holder=f"{os.environ.get('BENCH_HOLDER', '?')} answers.py",
                  purpose=f"answers.py record {a.label} copy {tag}", code=a.code)
    hold.watch_binaries(binary)
    srv = RW.Server(ns, "srv")
    with RW.scratch_db(ns.brain, ns.run_dir) as db:
        known, newest = known_ids(db)
    scrub = Scrub(known, newest, [str(pathlib.Path(ns.run_dir).resolve()), str(G.BUNDLE_DIR.resolve())])
    out = {}
    completed = False
    try:
        srv.start()
        renderer = srv.engine_runs()
        grant = srv.grants(1)[0][0]
        port = srv.port

        def get(name, path):
            _, st, b = W.once(port, "GET", path, headers=W.CLIENT, timeout=300)
            out[name] = scrub.answer(st, b)
            return st, b

        ids = {}
        for name, path in routes():
            st, b = get(name, path)
            if name in ("collection mid", "collection big") and st == 200:
                ids[name] = [i["id"] for i in json.loads(b).get("items", [])]
        for name, key in (("posts mid", "collection mid"), ("posts big", "collection big")):
            get(name, W.posts_path(ids[key]))
        for op in AGENT_OPS:
            _, st, b = W.once(port, "POST", "/api/worker", W.worker_body(op, W.MID, "load", W.WORK_TEXT[0], RW.REF),
                              {W.WORKER: grant}, timeout=300)
            out["agent " + op] = scrub.answer(st, b)
        # FRESHNESS: one record-only Turn, then what must already say so
        _, st, b = W.once(port, "POST", f"/api/conversations/{W.MID}/turns",
                          {"author": W.OWNER, "text": ANSWER_WORD, "action": "record-only"}, W.CLIENT, timeout=120)
        out["after commit: the write"] = scrub.answer(st, b)
        st, b = get("after commit: collection mid", W.collection_path(W.MID))
        new_ids = [i["id"] for i in json.loads(b).get("items", [])]
        get("after commit: posts mid", W.posts_path(new_ids))
        get("after commit: about mid", f"/fluid/api/conversations?ids={W.MID}")
        get("after commit: activity", W.ACTIVITY)
        get("after commit: topics load", "/fluid/api/topics?q=load&limit=8")
        _, st, b = W.once(port, "POST", "/api/worker", W.worker_body("history", W.MID, "load", "", RW.REF),
                          {W.WORKER: grant}, timeout=300)
        out["after commit: agent history"] = scrub.answer(st, b)
        completed = True
    finally:
        srv.stop()
        shutil.rmtree(ns.run_dir, ignore_errors=True)
        after = G.commit_of(a.code)
        if (after.get("commit"), after.get("dirty_files")) != (hold.code.get("commit"), hold.code.get("dirty_files")):
            hold.invalidate(f"the code changed during the work: {hold.code} to {after}")
        hold.finish(completed)
    return {"label": a.label, "pilot": a.label.replace("\\", "/").startswith("pilots/"),
            "code": hold.code, "workload_sha": hold.workload_sha, "isolation": hold.record,
            "command": a.command, "binary": binary, "brain": brain,
            "bundle_renderer_sha": (renderer or {}).get("sha256"), "copy_newest_time": newest,
            "recorded": time.strftime("%Y-%m-%d %H:%M:%S"),
            "normalised": {"counts": scrub.counts, "volatile_keys_seen": scrub.keys,
                           "volatile_keys_why": VOLATILE_KEYS},
            "answers": out}


def diff(a, b, path, out, most=400):
    if len(out) >= most:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append((f"{path}.{k}", "(absent)", b[k]))
            elif k not in b:
                out.append((f"{path}.{k}", a[k], "(absent)"))
            else:
                diff(a[k], b[k], f"{path}.{k}", out, most)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((f"{path}[len]", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            diff(x, y, f"{path}[{i}]", out, most)
    elif a != b:
        out.append((path, a, b))


def short(v):
    s = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else v
    s = s.replace("|", "\\|").replace("\n", " ")
    return s if len(s) <= 140 else s[:137] + "..."


def compare(base, other):
    lines, total = [], 0
    names = list(base["answers"]) + [n for n in other["answers"] if n not in base["answers"]]
    rows = []
    for name in names:
        x, y = base["answers"].get(name), other["answers"].get(name)
        found = []
        if x is None or y is None:
            found.append(("(route)", "(absent)" if x is None else "present", "(absent)" if y is None else "present"))
        else:
            diff(x, y, "", found)
        rows.append((name, found))
        total += len(found)
    lines.append(f"# Answers: {other['label']} against {base['label']}\n")
    lines.append(f"{base['label']} {base['code'].get('commit')}, {other['label']} {other['code'].get('commit')}. "
                 f"{len(names)} reads, {sum(1 for _, f in rows if f)} differ, {total} differences listed "
                 f"(at most 400 a read). Measured.\n")
    lines.append("Normalised, so unable to show a difference: "
                 f"{json.dumps(other['normalised']['counts'])}; keys {sorted(other['normalised']['volatile_keys_why'])}.\n")
    lines.append("Each difference is a defect or an intended change. This tool does not say which.\n")
    for name, found in rows:
        if not found:
            continue
        lines.append(f"\n## {name}: {len(found)}\n")
        lines.append(f"| where | {base['label']} | {other['label']} | defect or intended |\n|---|---|---|---|")
        for p, x, y in found[:60]:
            lines.append(f"| `{p}` | {short(x)} | {short(y)} | |")
        if len(found) > 60:
            lines.append(f"\n{len(found) - 60} more in this read.")
    same = [n for n, f in rows if not f]
    lines.append(f"\n## Identical: {len(same)}\n\n" + ", ".join(same))
    return "\n".join(lines) + "\n", total


def load(label, name="answers.json"):
    return json.load(open(G.RESULTS / label / name, encoding="utf-8"))


def not_200(result):
    return {k: v["status"] for k, v in result["answers"].items() if v["status"] != 200}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("record")
    r.add_argument("--command", required=True, help="what to start: a JSON array of strings, as run_workload.py takes it")
    r.add_argument("--code", required=True)
    r.add_argument("--brain", default=str(G.MASTER), help="the master each fresh copy is made from")
    r.add_argument("--label", required=True)
    r.add_argument("--port", type=int, default=8836)
    r.add_argument("--twice", action="store_true")
    r.add_argument("--server-env", action="append", default=[])
    c = sub.add_parser("compare")
    c.add_argument("base")
    c.add_argument("other")
    s = sub.add_parser("selftest")
    s.add_argument("label")
    a = ap.parse_args()
    if a.cmd == "record":
        if not 8831 <= a.port <= 8839:
            raise SystemExit("this work uses ports 8831-8839")
        a.code = str(pathlib.Path(a.code).resolve())
        a.command = RW.parse_command(a.command)
        out = G.RESULTS / a.label
        if (out / "answers.json").exists():
            raise G.Refused(f"{out / 'answers.json'} exists: a result is evidence and is not overwritten; use another label")
        out.mkdir(parents=True, exist_ok=True)
        first = record_once(a, "a")
        (out / "answers.json").write_text(json.dumps(first, indent=0, ensure_ascii=False), encoding="utf-8")
        print(f"{len(first['answers'])} reads; statuses",
              sorted({v['status'] for v in first['answers'].values()}), "normalised", first["normalised"]["counts"])
        bad = not_200(first)
        print("not 200:", bad)
        failed = bool(bad) or not first["isolation"]["valid"]
        print("isolation: valid", first["isolation"]["valid"], "samples", first["isolation"]["sample_count"],
              "sightings", first["isolation"]["sightings"], "workload_sha", first["workload_sha"])
        if a.twice:
            second = record_once(a, "b")
            second["label"] = a.label + " (second copy)"
            (out / "answers-second.json").write_text(json.dumps(second, indent=0, ensure_ascii=False), encoding="utf-8")
            text, total = compare(first, second)
            (out / "answers-self.md").write_text(text, encoding="utf-8")
            print("same code, two fresh copies: differences", total)
            print("second copy: not 200:", not_200(second), "isolation: valid", second["isolation"]["valid"])
            failed = failed or total > 0 or bool(not_200(second)) or not second["isolation"]["valid"]
        return G.FAILED if failed else 0
    elif a.cmd == "compare":
        base, other = load(a.base), load(a.other)
        G.refuse_unless_comparable({a.base: base, a.other: other})
        text, total = compare(base, other)
        path = G.RESULTS / a.other / f"answers-vs-{a.base}.md"
        path.write_text(text, encoding="utf-8")
        print(f"{total} differences; {path}")
        bad = {k: not_200(r) for k, r in ((a.base, base), (a.other, other)) if not_200(r)}
        if bad:
            print("not 200:", bad)
        return G.FAILED if total or bad else 0
    else:
        base = load(a.label)
        other = json.loads(json.dumps(base))
        other["label"] = "selftest"
        t = other["answers"]["topics load"]["json"]
        first = next(iter(t["topics"] if "topics" in t else t))
        other["answers"]["pulse"]["status"] = 500
        del other["answers"]["turns"]
        (t["topics"] if "topics" in t else t).reverse()
        _, total = compare(base, other)
        print("three changes made (a status, a route removed, an order reversed):", total, "differences reported;",
              "PASS" if total >= 3 else "FAIL")
        _, none = compare(base, base)
        print("against itself:", none, "PASS" if none == 0 else "FAIL")
        assert first is not None
        return 0 if total >= 3 and none == 0 else G.FAILED


if __name__ == "__main__":
    sys.exit(main())
