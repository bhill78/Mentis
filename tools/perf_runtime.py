"""Per-runtime performance of real dispatched runs (round 2, section 14).

    python -I tools/perf_runtime.py run --base http://127.0.0.1:8863 --brain <brain dir> \
        --label cand --runtime claude [--model M] --kind simple --runs 10 [--concurrency 3] \
        --out perf/raw.jsonl [--cold]
    python -I tools/perf_runtime.py summary perf/raw.jsonl [--md perf/summary.md]

Each run is an owner post that asks one agent for work (`ask-participant`, a runtime named),
exactly as Fluid sends it. What is measured comes from the record and the run's live feed:

  post_to_start_s        owner post -> `execution-started` (dispatch, selection, start)
  post_to_first_seen_s   owner post -> first feed entry seen (polled every 0.2 s; both releases)
  first_event_span_s     timing.first_event - timing.triggered_at (the candidate's WS-P spans)
  post_to_end_s          owner post -> the run's end act (total task duration)
  mars                   MARS's own spawn/initialize/new_session/load ms (candidate)
  usage                  numeric usage the runtime reported on the end act (tokens, cache)
  permission_round_trips `operation-answered` acts of the run (an owner/rule answer per ask)
  permission_audits      compiled-rule audits recorded for the run (no round trip)
  tools                  each tool call in the feed: title, seconds from first seen to done
  continuity             (continuation) asked/resumed/why, and whether the reply still knew
                         the code word given only in the first run (context preserved)
  cancel                 (cancel) stop asked -> end act seconds, and the end act's kind

Kinds: simple (no tools), tool (one Mentis `find` call), continuation (asks the owner one
decision, the harness answers it, the work resumes), cancel (a long answer stopped once it has
started). Nothing here waits on a timer of the server's: it reads the Brain read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

# the owner's interface, and the owner's session (MENTIS_OWNER_TOKEN; mentis.owner_auth)
CLIENT = {"X-Mentis-Client": "1", "Content-Type": "application/json",
          **({"Authorization": "Bearer " + os.environ["MENTIS_OWNER_TOKEN"]}
                 if os.environ.get("MENTIS_OWNER_TOKEN") else {})}
RUN_ENDS = ("result-returned", "delivery-failed", "result-recovered")
WORD = "PLUM-417"
PROMPTS = {
    "simple": "Performance probe. Reply with exactly the word READY and nothing else. "
              "Do not call any tools.",
    "tool": "Performance probe. Call the Mentis tool `find` exactly once with q=\"release\", "
            "then reply with only the number of results it returned. No other tools.",
    "continuation": f"Performance probe of session continuation. Remember this code word: {WORD}. "
                    "Use the Mentis tool `request_decision` once to ask the owner one question, "
                    "'Pick a colour for the probe', with exactly two options: 'blue' and 'green'. "
                    "Then end your run, saying only that you asked. When the work resumes with "
                    "the owner's answer, reply with the code word and the chosen colour, nothing "
                    "else, and use no other tools.",
    "cancel": "Performance probe of cancellation. Write the numbers from 1 to 400, one per line, "
              "with no other text and no tools.",
}


def http(base, path, body=None, timeout=120):
    req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers=CLIENT)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


class Record:
    """The Brain, read-only."""

    def __init__(self, brain):
        self.path = os.path.join(brain, "corpus.db")

    def q(self, sql, *args):
        c = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=30)
        try:
            c.row_factory = sqlite3.Row
            return [dict(r) for r in c.execute(sql, args)]
        finally:
            c.close()

    def acts(self, *, caused_by=None, act=None, execution=None, turn=None):
        where, args = [], []
        for col, val in (("caused_by", caused_by), ("act", act), ("execution", execution), ("turn", turn)):
            if val is not None:
                where.append(f"{col} = ?")
                args.append(val)
        rows = self.q(f"select * from operational where {' and '.join(where) or '1'} order by seq", *args)
        for r in rows:
            r["about"] = json.loads(r.get("about") or "[]")
            r["detail"] = json.loads(r.get("detail") or "{}")
        return rows

    def entry_text(self, ids):
        if not ids:
            return ""
        marks = ",".join("?" * len(ids))
        return " ".join(r["body"] for r in self.q(f"select body from entry where id in ({marks})", *ids))


def owner_of(rec):
    """The Brain's owner Participant: the first participant row whose `about` is the owner's."""
    for r in rec.q("select id, body from entry where def_name = 'participant' order by seq"):
        if (json.loads(r["body"]) or {}).get("about") == "the owner":
            return r["id"]
    raise SystemExit("no owner in this Brain; pass --owner")


def wait_for(fn, timeout, every=0.2):
    end = time.time() + timeout
    while time.time() < end:
        got = fn()
        if got:
            return got
        time.sleep(every)
    return None


def one_run(a, rec, conv, i, kind, cold):
    out = {"label": a.label, "runtime": a.runtime, "model": a.model, "kind": kind, "i": i,
           "concurrency": a.concurrency, "cold": cold}
    spec = {"participant": a.participant, "runtime": a.runtime, "new_instance": True}
    if a.model:
        spec["model"] = a.model
    t_post = time.time()
    s, v = http(a.base, "/fluid/api/posts", {"conversation": conv, "author": a.owner,
                                             "text": PROMPTS[kind], "action": "ask-participant",
                                             "dispatch": [spec]})
    out["post_status"] = s
    if s != 200:
        out["error"] = f"post refused: {json.dumps(v)[:300]}"
        return out
    turn = (v or {}).get("post") or (v or {}).get("turn")
    exp = next(iter((v or {}).get("expectations") or []), None)
    if isinstance(exp, dict):
        exp = exp.get("expectation") or exp.get("id")
    exp = exp or wait_for(lambda: next((x["id"] for x in rec.acts(turn=turn, act="expectation-recorded")), None), 30)
    out["expectation"] = exp
    if not exp:
        out["error"] = f"no expectation recorded for post {turn}: {json.dumps(v)[:300]}"
        return out
    first = run_of(a, rec, exp, t_post, out, kind)
    if kind == "continuation" and first.get("end_act") == "result-returned":
        decision = next((x for x in rec.acts(act="expectation-recorded")
                         if (x.get("detail") or {}).get("expects") == "decision"
                         and x.get("conversation") == conv and x.get("at", 0) >= t_post), None)
        out["decision"] = decision and decision["id"]
        if not decision:
            out["error"] = "the agent asked no decision: no continuation to measure"
            return out
        d = decision.get("detail") or {}
        opts = d.get("options") or []
        label = (opts[0].get("label") if opts and isinstance(opts[0], dict) else (opts[0] if opts else "blue"))
        asked_on = decision.get("turn")
        if d.get("form"):  # a decision form: its own Turn, else the answer post it was attached to
            form = next(iter(rec.q("select turn from operational where id = ?", d["form"])), {})
            attached = rec.acts(caused_by=d["form"], act="decision-form-attached")
            asked_on = form.get("turn") or next((x["turn"] for x in attached if x.get("turn")), None)
        t_answer = time.time()
        s, v = http(a.base, "/fluid/api/posts", {"conversation": conv, "author": a.owner, "text": label,
                                                 "replies_to": asked_on,
                                                 "chose": {"expectation": decision["id"], "option": 0, "label": label}})
        out["answer_status"] = s
        if s != 200:
            out["error"] = f"answer refused: {json.dumps(v)[:300]}"
            return out
        cont = {}
        run_of(a, rec, exp, t_answer, cont, "continuation-2", skip=first.get("run"))
        out["continuation"] = cont
        said = rec.q("select body from entry where attributed_to = ? and recorded_at >= ?",
                     a.participant, t_answer)
        out["continuation"]["reply_has_word"] = any(WORD in r["body"] for r in said)
    return out


def run_of(a, rec, exp, t0, out, kind, skip=None):
    def started_or_refused():
        for x in rec.acts(caused_by=exp):
            if x.get("at", 0) < t0 - 1 or x["id"] == skip:
                continue
            if x["act"] == "execution-started":
                return x
            if x["act"] in RUN_ENDS:  # refused before any run started (e.g. runtime not present)
                return x
        return None
    start = wait_for(started_or_refused, a.timeout)
    if not start:
        out["error"] = "no execution-started within the timeout"
        return out
    if start["act"] != "execution-started":
        out.update(end_act=start["act"], error=f"no run started: {start.get('because')}",
                   post_to_end_s=round(start["at"] - t0, 3))
        return out
    run = start["id"]
    out.update(run=run, post_to_start_s=round(start["at"] - t0, 3),
               start_timing=(start.get("detail") or {}).get("timing"))
    seen, after, tools, stop_asked, perms = None, 0, {}, None, 0
    end = None
    deadline = time.time() + a.timeout
    while time.time() < deadline:
        s, feed = http(a.base, f"/api/runs/{run}/feed?after={after}", timeout=30)
        if s == 200 and isinstance(feed, dict):
            for e in feed.get("events") or []:
                if seen is None and e.get("kind") in ("message", "thought", "tool", "plan"):
                    seen = time.time()
                if e.get("kind") == "tool":
                    t = tools.setdefault(e["id"], {"title": e.get("title"), "first": time.time()})
                    t["title"] = e.get("title") or t["title"]
                    if e.get("status") in ("completed", "failed") and "done" not in t:
                        t["done"] = time.time()
                        t["status"] = e.get("status")
                if e.get("kind") == "permission":
                    perms += 1
            after = feed.get("next", after)
        if kind == "cancel" and seen and stop_asked is None:
            stop_asked = time.time()
            http(a.base, f"/api/runs/{run}/stop", {"why": "perf probe: cancellation"})
        ends = [x for x in rec.acts(caused_by=run) if x["act"] in RUN_ENDS]
        if ends:
            end = ends[0]
            break
        time.sleep(0.2)
    if not end:
        out["error"] = "the run did not end within the timeout"
        return out
    d = end.get("detail") or {}
    timing = d.get("timing") or {}
    out.update(end_act=end["act"], post_to_end_s=round(end["at"] - t0, 3),
               post_to_first_seen_s=round(seen - t0, 3) if seen else None,
               feed_permission_events=perms,
               tools=[{"title": t["title"], "s": round(t["done"] - t["first"], 3) if "done" in t else None,
                       "status": t.get("status")} for t in tools.values()],
               timing=timing, mars=timing.get("mars"),
               usage={k: v for k, v in d.items() if isinstance(v, (int, float)) and
                      any(w in k for w in ("token", "cache", "cost", "usage", "used", "size"))},
               audit=(d.get("audit") or (d.get("runtime_evidence") or {}).get("audit")),
               tool_calls_recorded=len(d.get("tool_calls") or []),
               observed_model=d.get("observed_model"),
               continuity=d.get("continuity"), runtime_session=bool(d.get("runtime_session")),
               because=end.get("because"), reply_ids=[x for x in [d.get("reply")] + (end.get("about") or []) if x])
    if timing.get("first_event") and timing.get("triggered_at"):
        out["first_event_span_s"] = round(timing["first_event"] - timing["triggered_at"], 3)
    if timing.get("session_opened") and timing.get("perform_called"):
        out["session_open_s"] = round(timing["session_opened"] - timing["perform_called"], 3)
    if stop_asked:
        out["cancel"] = {"stop_to_end_s": round(end["at"] - stop_asked, 3), "end_act": end["act"]}
    answered = [x for x in rec.acts(act="operation-answered", execution=start.get("execution"))
                if x.get("at", 0) >= t0]
    audit = out.get("audit") or {}
    # A ROUND TRIP is a permission request the run had to wait on Mentis (or the owner) for:
    # answered acts, else the audit's count of asks that reached Mentis.
    out["permission_round_trips"] = max(len(answered), int(audit.get("asked_mentis") or 0))
    out["permission_audits"] = len([x for x in rec.acts(act="permission-audit", execution=start.get("execution"))
                                    if x.get("execution") == start.get("execution")])
    return out


def cmd_run(a):
    rec = Record(a.brain)
    a.owner = a.owner or owner_of(rec)
    conv = a.conversation
    if not conv:
        s, v = http(a.base, "/api/conversations", {"name": f"perf {a.label} {a.runtime} {a.kind}",
                                                   "author": a.owner})
        conv = v["conversation"]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    lock = threading.Lock()
    done = 0
    i = 0
    while done < a.runs:
        batch = min(a.concurrency, a.runs - done)
        results = [None] * batch
        cold = a.cold and done == 0

        def go(k, n):
            try:
                results[k] = one_run(a, rec, conv, n, a.kind, cold)
            except Exception as exc:  # noqa: BLE001 -- a harness failure is a recorded result
                results[k] = {"label": a.label, "runtime": a.runtime, "kind": a.kind, "i": n,
                              "error": f"harness: {exc!r}"}
        threads = [threading.Thread(target=go, args=(k, i + k)) for k in range(batch)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with lock, open(a.out, "a", encoding="utf-8") as f:
            for r in results:
                r["conversation"] = conv
                f.write(json.dumps(r, default=str) + "\n")
                print(json.dumps({k: r.get(k) for k in ("label", "runtime", "kind", "i", "end_act", "post_to_start_s",
                                                        "post_to_first_seen_s", "first_event_span_s", "post_to_end_s",
                                                        "permission_round_trips", "error")}), flush=True)
        done += batch
        i += batch


def pct(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 2)


def cmd_summary(a):
    rows = [json.loads(l) for l in open(a.file, encoding="utf-8") if l.strip()]
    groups = {}
    for r in rows:
        groups.setdefault((r.get("runtime"), r.get("kind"), r.get("label"), r.get("concurrency"), r.get("cold")), []).append(r)
    lines = ["| runtime | kind | release | conc | cold | n ok/all | start p50/p95 | first seen p50/p95 | first event span p50 | total p50/p95 | perm trips | tools s p50 | notes |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for key in sorted(groups, key=lambda k: tuple(str(x) for x in k)):
        g = groups[key]
        ok = [r for r in g if not r.get("error") and (r.get("end_act") == "result-returned"
                                                       or (r.get("kind") == "cancel" and r.get("end_act")))]
        f = lambda name: [r.get(name) for r in ok]
        tools = [t["s"] for r in ok for t in r.get("tools") or [] if t.get("s") is not None]
        notes = []
        errs = [r.get("error") or r.get("end_act") for r in g if r not in ok]
        if errs:
            notes.append(f"failed: {'; '.join(sorted(set(str(e)[:80] for e in errs)))}")
        cont = [r["continuation"] for r in ok if r.get("continuation")]
        if cont:
            res = [c.get("continuity") or {} for c in cont]
            notes.append(f"continuation total p50 {pct([c.get('post_to_end_s') for c in cont], .5)} s, "
                         f"resumed {sum(1 for x in res if x.get('resumed'))}/{len(cont)}, "
                         f"word kept {sum(1 for c in cont if c.get('reply_has_word'))}/{len(cont)}")
        canc = [r["cancel"] for r in ok if r.get("cancel")]
        if canc:
            notes.append(f"stop->end p50 {pct([c['stop_to_end_s'] for c in canc], .5)} s, ends {sorted(set(c['end_act'] for c in canc))}")
        usage = [r.get("usage") for r in ok if r.get("usage")]
        if usage:
            keys = sorted({k for u in usage for k in u})
            notes.append("usage p50 " + ", ".join(f"{k}={pct([u.get(k) for u in usage], .5)}" for k in keys[:6]))
        lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {key[3]} | {key[4]} | {len(ok)}/{len(g)} | "
                     f"{pct(f('post_to_start_s'), .5)}/{pct(f('post_to_start_s'), .95)} | "
                     f"{pct(f('post_to_first_seen_s'), .5)}/{pct(f('post_to_first_seen_s'), .95)} | "
                     f"{pct(f('first_event_span_s'), .5)} | {pct(f('post_to_end_s'), .5)}/{pct(f('post_to_end_s'), .95)} | "
                     f"{statistics.mean(f('permission_round_trips')) if ok else None} | {pct(tools, .5)} | {' · '.join(notes)} |")
    text = "\n".join(lines)
    sys.stdout.buffer.write((text + chr(10)).encode("utf-8"))
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--base", required=True)
    r.add_argument("--brain", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--runtime", required=True)
    r.add_argument("--model")
    r.add_argument("--kind", choices=sorted(PROMPTS), default="simple")
    r.add_argument("--runs", type=int, default=1)
    r.add_argument("--concurrency", type=int, default=1)
    r.add_argument("--participant", default="ent-15d47a2b6ba4")  # @Builder in the DAY-TO-DAY record
    r.add_argument("--owner")
    r.add_argument("--conversation")
    r.add_argument("--timeout", type=float, default=600)
    r.add_argument("--cold", action="store_true", help="the first run follows a fresh server start")
    r.add_argument("--out", required=True)
    s = sub.add_parser("summary")
    s.add_argument("file")
    s.add_argument("--md")
    a = p.parse_args(argv)
    cmd_run(a) if a.cmd == "run" else cmd_summary(a)


if __name__ == "__main__":
    main()
