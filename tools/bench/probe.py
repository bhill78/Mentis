"""MEASUREMENT ONLY. The foreground, in a process of its own: one read at a time on a
fresh connection, as a person's reads or one agent's calls come.

usage: probe.py CONFIG.json     (written by run_workload.py)
  phase person  pulse, topic lookup, post window (collection + posts?ids=<50>&thread=1),
                and the ungated agent read `resolve`
        agent   the costly agent reads, one at a time: orient, recall, find (gated),
                brief (gated), kinds, work_overview (ungated); or the level's own `ops`
        cold    each first read of a boot, once: nothing may have touched them
"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wl_common as W

cfg = json.load(open(sys.argv[1]))
PORT, GRANT, REF = cfg["port"], cfg.get("grant"), cfg.get("ref")
FG_TIMEOUT = 120
OVERRUN_S = 30
got = []   # (name, started, ms, status)
errs = []


def note(name, started, ms, st):
    got.append((name, round(started, 3), round(ms, 1), st))


def get(name, path):
    started = time.time()
    try:
        ms, st, b = W.once(PORT, "GET", path, headers=W.CLIENT, timeout=FG_TIMEOUT)
    except OSError as exc:
        errs.append((name, round(started, 3), repr(exc)[:160]))
        return None, None
    note(name, started, ms, st)
    return ms, b if st == 200 else None


def window(prefix, conv):
    ms1, b = get(prefix + "_collection", W.collection_path(conv))
    ids = [i["id"] for i in json.loads(b).get("items", [])] if b else []
    if not ids:
        return
    started = time.time()
    ms2, _ = get(prefix + "_posts", W.posts_path(ids))
    if ms2 is not None:
        note(prefix + "_total", started, ms1 + ms2, 200)


def worker(name, op, conv=W.MID, word="load", work=W.WORK_TEXT[0]):
    started = time.time()
    try:
        ms, st, _ = W.once(PORT, "POST", "/api/worker", W.worker_body(op, conv, word, work, REF),
                           {W.WORKER: GRANT}, timeout=FG_TIMEOUT)
        note(name, started, ms, st)
    except OSError as exc:
        errs.append((name, round(started, 3), repr(exc)[:160]))


def person():
    # topics alternate words, windows alternate a mid-sized and the largest conversation.
    # Two lookups per window: a window takes seconds under load, and lookups need the count.
    # After each window one of the v2 reads in turn, so they get counts without taking the
    # lookups' and windows' share of a slow level.
    walk = ("pulse", "topics", "topics", "resolve", "window_mid", "more",
            "pulse", "topics", "topics", "resolve", "window_big", "more")
    more = (("activity", W.ACTIVITY), ("needs_you", W.NEEDS_YOU),
            ("needs_you_items", W.NEEDS_ITEMS), ("turns", W.turns_path()))
    if cfg.get("light"):
        walk = tuple(s for s in walk if s != "more")
    i = 0
    m = 0
    steps = 0
    # At least one whole walk, so a slow level still gets each read, but no more than
    # OVERRUN_S past the end: behind n-cpu a single read can take minutes on main.
    def more_to_do():
        now = time.time()
        return now < cfg["until"] or (steps < len(walk) and now < cfg["until"] + OVERRUN_S)

    while more_to_do():
        for step in walk:
            if not more_to_do():
                break
            steps += 1
            if step == "pulse":
                get("pulse", "/api/pulse")
            elif step == "topics":
                get("topic_lookup", f"/fluid/api/topics?q={W.TOPIC_WORDS[i % len(W.TOPIC_WORDS)]}&limit=8")
                i += 1
            elif step == "window_mid":
                window("window", W.MID)
            elif step == "window_big":
                window("window", W.BIG)
            elif step == "resolve":
                worker("agent_resolve", "resolve")
            elif step == "more":
                get(*more[m % len(more)])
                m += 1
            time.sleep(0.1)


def agent():
    # one starting point per round, so a level too slow to finish a cycle still gets
    # each read over its rounds
    ops = cfg.get("ops") or ["orient", "recall", "find", "kinds", "brief", "work_overview"]
    start = cfg.get("start", 0) * (2 if len(ops) > 2 else 1)
    i = 0
    while time.time() < cfg["until"]:
        op = ops[(start + i) % len(ops)]
        worker("agent_" + op, op, W.CONVS[i % len(W.CONVS)], W.WORDS[i % len(W.WORDS)],
               W.WORK_TEXT[i % len(W.WORK_TEXT)])
        i += 1
        time.sleep(0.1)


def cold():
    # the order is the point: the record's first touches, in a person's order
    get("cold_pulse", "/api/pulse")
    get("cold_topic_lookup", "/fluid/api/topics?q=load&limit=8")
    for conv in cfg["cold_convs"]:
        window("cold_window", conv)
        time.sleep(0.2)
        get("cold_objects_page", W.objects_path(conv, None))   # first extraction of these posts' objects
        time.sleep(0.2)
    worker("cold_agent_resolve", "resolve")
    for op in ("orient", "recall", "find", "kinds", "brief", "work_overview"):
        worker("cold_agent_" + op, op)
    get("cold_activity", W.ACTIVITY)
    get("cold_needs_you", W.NEEDS_YOU)
    get("cold_needs_you_items", W.NEEDS_ITEMS)
    get("cold_turns", W.turns_path())


{"person": person, "agent": agent, "cold": cold}[cfg["phase"]]()
json.dump({"phase": cfg["phase"], "records": got, "errors": errs}, open(cfg["out"], "w"))
