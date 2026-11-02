"""MEASUREMENT ONLY. A write load on the server's OWN COPY of the record, at a stated
rate, in a process of its own. Each write is a record-only Turn by the owner in one of
the background's conversations: `posting.post` documents record-only as "the Turn.
Nothing else, ever", so no expectation and no dispatch can come of it.

usage: writer.py CONFIG.json     (written by run_workload.py)
No catch-up: a write that returns late does not make the next ones come faster.

With `window_after` (the `write` level only, never a neighbour: the window is a route a
candidate may serve outside Python), each commit is followed at once by one window read of
the conversation just written, as the writer's own next read. Its times go out as probes.
"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wl_common as W

cfg = json.load(open(sys.argv[1]))
period = cfg["period"]
records, errors = [], []
after, after_errors = [], []    # (probe name, started, ms, status)


def window_after(conv):
    started = time.time()
    try:
        ms1, st, b = W.once(cfg["port"], "GET", W.collection_path(conv), headers=W.CLIENT)
        after.append(("after_commit_collection", round(started, 3), round(ms1, 1), st))
        ids = [i["id"] for i in json.loads(b).get("items", [])] if st == 200 else []
        if ids:
            started2 = time.time()
            ms2, st, _ = W.once(cfg["port"], "GET", W.posts_path(ids), headers=W.CLIENT)
            after.append(("after_commit_posts", round(started2, 3), round(ms2, 1), st))
            if st == 200:
                after.append(("after_commit_total", round(started2, 3), round(ms1 + ms2, 1), 200))
    except OSError as exc:
        after_errors.append(("after_commit_total", round(started, 3), repr(exc)[:160]))


c = W.Conn(cfg["port"], 120)
i = 0
next_at = time.time()
while not os.path.exists(cfg["stop"]) and time.time() < cfg["max_until"]:
    d = next_at - time.time()
    if d > 0:
        time.sleep(min(d, 0.05))
        continue
    next_at = max(next_at + period, time.time())
    conv = W.CONVS[i % len(W.CONVS)]
    i += 1
    started = time.time()
    t = time.perf_counter()
    try:
        st, b = c.ask("POST", f"/api/conversations/{conv}/turns",
                      body={"author": W.OWNER, "text": f"workload write {cfg.get('tag', '')} #{i}",
                            "action": "record-only"},
                      headers=W.CLIENT)
        ms = (time.perf_counter() - t) * 1000
        refused = st != 200 or b'"error"' in b[:200]
        records.append(("write", round(started, 3), round(ms, 1), st))
        if refused:
            errors.append(("write", round(started, 3), b[:200].decode("utf-8", "replace")))
        elif cfg.get("window_after"):
            window_after(conv)
    except OSError as exc:
        errors.append(("write", round(started, 3), repr(exc)[:160]))
c.close()
json.dump({"records": records, "errors": errors, "period": period,
           "after": after, "after_errors": after_errors}, open(cfg["out"], "w"))
