"""Are the work and obligation reads from the kept model the old projection?

Stage 1b moved Home's Work, `/api/work` (the owner's, and a Conversation's
work pills), `/api/owed` and a Conversation's `owed` onto the one kept
current-work model (`operational.read_model`). This computes each of them
both ways over ONE Brain, at one moment, with one run observation, and says
every difference:

  OLD  projected from the record as those routes did before: `work_overview.
       overview` without a kept model; Home's Work placed from its own
       projection (`OLD_HOME_WORK`, the replaced code, kept here verbatim as
       the reference); `owed_by` and `expectations(open_only=True)` read again.
  NEW  the same functions answered from the kept model, as the routes now
       call them.

    python tools/work_model_diff.py <Brain COPY dir> [--conversations N]
           [--json OUT] [--timing]
    python tools/work_model_diff.py http://127.0.0.1:<port> --http

NEVER THE LIVE BRAIN: make a copy with SQLite's backup API from a read-only
connection (AGENTS.md). The copy is opened for reading by this script; the
kept model writes nothing. Exit status 0 when every compared read is equal.
`compare(cv, observe)` is what `tests/test_read_model.py` runs on a fixture.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

#: A server that could ask MARS and holds no run: what the copy's server sees.
QUIET = {"runs": {}, "instances": {}, "why_not": None}


def _canon(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


# -- the replaced code, verbatim: Home's Work as it was projected --------------

def OLD_HOME_WORK(cv, runtime, *, state="all", before=None, limit=30, at=None):
    """`fluid.home.work_collection` before Stage 1b (2c26ef7), with the
    route's state argument replaced by `cv` and `runtime`."""
    from mentis.fluid import home as H
    from mentis.operational import work_overview as wo
    stage = state[len(H.STAGE):] if state.startswith(H.STAGE) else None
    viewer = wo.owner_of(cv)
    ctx = H._Ctx(cv)
    trunks = wo._trunks(cv)
    H._prime(ctx, trunks)
    found = wo._found_ids(cv)
    seq = cv._write_order([a["id"] for a in trunks])
    rows = []
    counts = {s: 0 for s in H.PLACED + (H.NOT_STARTED,)}
    stages = {s: 0 for s in wo.STAGES}
    for a in trunks:
        item, where = H._project(ctx, a, viewer=viewer, runtime=runtime,
                                 found=found)
        counts[where] += 1
        at_stage = item.get("stage") or "unknown"
        stages[at_stage] += 1
        if stage is not None:
            if at_stage != stage:
                continue
        elif where == H.NOT_STARTED or (state != "all" and where != state):
            continue
        rank = H.PLACED.index(where) if where in H.PLACED else len(H.PLACED)
        rows.append(((rank, -H._newest(item),
                      -seq.get(a["id"], -1)), a["id"]))
    counts["all"] = sum(counts[s] for s in H.PLACED)
    rows.sort()
    if before:
        rank, newest, s = H._parse_key(before, 3)
        mark = (int(rank), -float(newest), -int(s))
        rows = [r for r in rows if r[0] > mark]
    page = rows[:limit]
    more = len(rows) > len(page)
    last = page[-1][0] if page else None
    return {"key": H.WORK, "state": state, "items": [r[1] for r in page],
            "before": H._key_cursor(last[0], -last[1], -last[2])
            if more and last else None,
            "counts": counts, "limit": limit, "viewer": viewer,
            "stages": stages,
            "needs_you_unknown": viewer is None,
            "needs_you_why": wo.NO_VIEWER if viewer is None else None,
            "runtime_why_not": runtime.get("why_not"),
            "cursor": at}


class _St:
    """What `work_collection` reads of a server's state."""

    def __init__(self, cv, observe):
        self.cv, self._observe = cv, observe


def _new_home_work(st, **kw):
    from mentis.fluid import home as H
    return H.work_collection(st, **kw)


# -- the comparison --------------------------------------------------------------

def _differ(old, new, path=""):
    """Where two answers differ: up to a few paths, each with both values."""
    if _canon(old) == _canon(new):
        return []
    if isinstance(old, dict) and isinstance(new, dict):
        out = []
        for k in sorted(set(old) | set(new), key=str):
            out += _differ(old.get(k), new.get(k), f"{path}.{k}")
        return out
    if (isinstance(old, list) and isinstance(new, list)
            and len(old) == len(new)):
        out = []
        for i, (a, b) in enumerate(zip(old, new)):
            out += _differ(a, b, f"{path}[{i}]")
        return out
    return [{"at": path or ".", "old": old, "new": new}]


def compare(cv, observe=lambda: QUIET, *, conversations=4,
            timing=False) -> dict:
    """Every compared read, both ways; `equal` is True when none differs.

    `observe` is the run observation both ways are given. The kept model
    is a fresh one of this record (`current_work.CurrentWork`), brought up
    to it here, so the comparison is of one moment."""
    from mentis.operational import current_work as cw
    from mentis.operational import read_model as rm
    from mentis.operational import work_overview as wo
    from mentis.operational.work import owed_by
    from mentis.web import _surface  # noqa: F401  (imports the web package)

    cw.forget()
    model = rm.PythonReadModel(cv, observe=observe)
    t = time.perf_counter()
    model._kept.current(wait=True)
    build_s = time.perf_counter() - t
    runtime = observe()
    owner = wo.owner_of(cv)
    checks, times = [], {"kept_build_s": round(build_s, 2)}

    def check(name, old_fn, new_fn):
        t0 = time.perf_counter()
        with cv.reading():
            old = old_fn()
        t1 = time.perf_counter()
        with cv.reading():
            new = new_fn()
        t2 = time.perf_counter()
        diffs = _differ(old, new)
        checks.append({"read": name, "equal": not diffs,
                       "differences": len(diffs), "first": diffs[:5],
                       "old_s": round(t1 - t0, 3), "new_s": round(t2 - t1, 3)})

    # -- /api/work for the owner, Brain-wide and today's Ledger ----------------
    view = model.work_items()

    def api_work(conversation=None, **kw):
        v = model.work_items(rm.Scope(conversation=conversation))
        return (lambda: wo.overview(cv, viewer=owner, runtime=runtime,
                                    conversation=conversation, **kw),
                lambda: wo.overview(cv, viewer=owner, runtime=v.runtime,
                                    conversation=conversation, kept=v, **kw))

    check("/api/work", *api_work())
    day = time.strftime("%Y-%m-%dT00:00:00", time.localtime())
    week = time.strftime("%Y-%m-%dT00:00:00",
                         time.localtime(time.time() - 7 * 86400))
    check(f"/api/work?active_since={day}&completed_since={day}",
          *api_work(active_since=day, completed_since=day))
    check(f"/api/work?active_since={week}&limit=20",
          *api_work(active_since=week, limit=20))

    # -- /api/work?conversation= (the work pills), the busiest Conversations --
    by_conv = {}
    for a in view.trunks.values():
        by_conv[a.get("conversation")] = by_conv.get(a.get("conversation"),
                                                     0) + 1
    busiest = sorted((c for c in by_conv if c), key=lambda c: -by_conv[c])
    for cid in busiest[:conversations]:
        check(f"/api/work?conversation={cid}", *api_work(conversation=cid))

    # -- /fluid/api/home/work, every state and the next page -------------------
    st = _St(cv, observe)
    st._read_model = model
    for state in ("all", "needs-you", "in-flight", "ended", "unknown",
                  "completed", "stage:building"):
        check(f"/fluid/api/home/work?state={state}",
              lambda s=state: OLD_HOME_WORK(cv, runtime, state=s),
              lambda s=state: _new_home_work(st, state=s, before=None,
                                             limit=30, at=None))
    first = _new_home_work(st, state="all", before=None, limit=30, at=None)
    if first["before"]:
        check("/fluid/api/home/work?state=all&before=<page 2>",
              lambda: OLD_HOME_WORK(cv, runtime, before=first["before"]),
              lambda: _new_home_work(st, state="all", before=first["before"],
                                     limit=30, at=None))

    # -- /api/owed, for everybody who owes anything ----------------------------
    with cv.reading():
        carriers = sorted({s["expected_of"] for s in
                           model.owed().rows if s["expected_of"]},
                          key=lambda p: (p != owner, p))
    for who in carriers:
        check(f"/api/owed?participant={who}&limit=1000",
              lambda w=who: owed_by(cv, w, limit=1000),
              lambda w=who: owed_by(cv, w, limit=1000, owed=model.owed(
                  rm.Scope(participant=w)).rows))

    # -- a Conversation's owed (`?batch=0`) ------------------------------------
    for cid in busiest[:conversations] + sorted(
            {s["conversation"] for s in model.owed().rows} - set(busiest[:conversations])):
        check(f"/api/conversations/{cid}?batch=0 owed",
              lambda c=cid: [{k: v for k, v in o.items()
                              if k != "latest_activity"}
                             for o in cv.expectations(conversation=c,
                                                      open_only=True)
                             if not o["response_present"]],
              lambda c=cid: [{k: v for k, v in o.items()
                              if k != "latest_activity"}
                             for o in model.owed(
                                 rm.Scope(conversation=c)).rows])

    # -- and the model's own reconcile: rebuilt, nothing differs ---------------
    differ = model._kept.reconcile()
    checks.append({"read": "reconcile (kept vs rebuilt)",
                   "equal": not differ, "differences": len(differ),
                   "first": differ[:5]})
    out = {"equal": all(c["equal"] for c in checks), "checks": checks,
           "trunks": len(view.order), "obligations": len(view.states),
           "open": len(model.owed().rows), **times}
    if timing:
        out["timing"] = _timing(cv, model, st)
    return out


def _p(xs, q):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))] * 1000, 1)


def _timing(cv, model, st, n=60, writes=15) -> dict:
    """Home's Work from the kept model as a server keeps it -- maintained on
    its own thread (`CurrentWork.start`) -- p50/p95 warm, and the first read
    after each write: a reply by the owner to a piece of work's post, written
    to the COPY here. Nothing is served, so nothing can be dispatched."""
    from mentis.conversation import text
    from mentis.operational import current_work as cw
    model._kept.start()

    def home():
        t = time.perf_counter()
        with cv.reading():
            _new_home_work(st, state="all", before=None, limit=30, at=None)
        return time.perf_counter() - t
    home()
    warm = [home() for _ in range(n)]
    view = model.work_items()
    trunk = next(t for t in reversed(view.order) if view.trunks[t].get("turn"))
    act = view.trunks[trunk]
    after = []
    for i in range(writes):
        cv.say(act["conversation"], view.viewer or "mentis",
               [text(f"timing write {i} on a Brain copy")],
               replies_to=act["turn"])
        after.append(home())
    return {"home_work_warm_ms": {"p50": _p(warm, .5), "p95": _p(warm, .95),
                                  "n": len(warm)},
            "home_work_after_write_ms": {"p50": _p(after, .5),
                                         "p95": _p(after, .95),
                                         "n": len(after)},
            "model_at_record_after_last_read":
                model._kept._model.cursor
                == cw.cursor_text(cv._c._store.advance())}


def http_timing(base, n=60) -> dict:
    """Home's Work over HTTP from a server serving a COPY, warm: p50/p95.
    It only reads: a write through a server can dispatch an agent."""
    import urllib.request

    def call(path):
        req = urllib.request.Request(base + path,
                                     headers={"X-Mentis-Client": "1"})
        t = time.perf_counter()
        with urllib.request.urlopen(req, timeout=120) as r:
            r.read()
        return time.perf_counter() - t

    call("/fluid/api/home/work")                 # the first build, waited for
    warm = [call("/fluid/api/home/work") for _ in range(n)]
    return {"home_work_warm_ms": {"p50": _p(warm, .5), "p95": _p(warm, .95),
                                  "n": len(warm)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("brain", help="a Brain COPY directory, or with --http "
                                  "the URL of a server serving one")
    ap.add_argument("--conversations", type=int, default=4)
    ap.add_argument("--json", default=None)
    ap.add_argument("--timing", action="store_true",
                    help="also time Home's Work, writing replies to the COPY")
    ap.add_argument("--http", action="store_true",
                    help="time Home's Work over HTTP from the server at this "
                         "URL (serving a COPY); reads only")
    a = ap.parse_args(argv)
    if a.http:
        print("timing", _canon(http_timing(a.brain.rstrip("/"))))
        return 0
    from mentis.worker import Surface
    s = Surface(a.brain)
    got = compare(s.cv, conversations=a.conversations, timing=a.timing)
    for c in got["checks"]:
        print(f"{'EQUAL' if c['equal'] else 'DIFFERS':8} {c['read']}"
              + (f"  old {c['old_s']}s new {c['new_s']}s" if "old_s" in c
                 else "")
              + ("" if c["equal"] else f"  ({c['differences']}: "
                 f"{_canon(c['first'])[:400]})"))
    print(f"trunks {got['trunks']}, obligations {got['obligations']} "
          f"({got['open']} open), kept build {got['kept_build_s']}s")
    if a.timing:
        print("timing", _canon(got["timing"]))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(got, indent=1,
                                                   default=str))
    print("ALL EQUAL" if got["equal"] else "DIFFERENCES FOUND")
    return 0 if got["equal"] else 1


if __name__ == "__main__":
    sys.exit(main())
