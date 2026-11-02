"""MEASUREMENT ONLY. The background: N workers in a process of their own, so this
process's interpreter lock cannot inflate what the probes observe. Reads only.

usage: load.py CONFIG.json     (written by run_workload.py)
  kind   mix     wl_common.MIX, over Fluid's routes
         agent   wl_common.AGENT_MIX, through /api/worker, one grant per worker
         sql     wl_common.SQL_MIX: the neighbour that is statements
         cpu     whole object indexes page by page over wl_common.CPU_CONVS: the neighbour
                 that is the JS engine, on posts not yet extracted
  n      workers
  pace   0: closed loop, each worker's next query starts when its last ended.
         Otherwise all workers fire every `pace` seconds at the same instant, as one
         commit waking every standing query would. A worker still busy at its instant
         fires as soon as it is free: today's client has no coalescing.
  stop   runs until this file exists
Every completed query is written out with its start time, so the controller cuts the
warm-up on the same clock as everything else.
"""
import json, os, random, sys, threading, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wl_common as W

cfg = json.load(open(sys.argv[1]))
PORT, KIND, N, PACE = cfg["port"], cfg["kind"], cfg["n"], cfg["pace"]
stopping = threading.Event()
records, errors, lock = [], [], threading.Lock()
finished = [False] * N
TIMEOUT = 120


def watch():
    while not stopping.is_set():
        if os.path.exists(cfg["stop"]) or time.time() > cfg["max_until"]:
            stopping.set()
        time.sleep(0.05)


def read_ok(c, path):
    st, b = c.ask("GET", path, headers=W.CLIENT)
    return st, b


def mix_op(c, op, rnd, cursors, k):
    conv = W.CONVS[k % len(W.CONVS)]
    if op == "window":
        st, b = read_ok(c, W.collection_path(conv))
        ids = [i["id"] for i in json.loads(b).get("items", [])] if st == 200 else []
        if ids:
            st, _ = read_ok(c, W.posts_path(ids))
        return st
    if op == "objects":
        st, b = read_ok(c, W.objects_path(conv, cursors.get(conv)))
        cursors[conv] = json.loads(b).get("before") if st == 200 else None
        return st
    if op == "about":
        return read_ok(c, f"/fluid/api/conversations?ids={conv}")[0]
    if op == "activity":
        return read_ok(c, W.ACTIVITY)[0]
    if op == "needs_you":
        return read_ok(c, W.NEEDS_YOU)[0]
    if op == "scan":
        return read_ok(c, f"/api/references?q={rnd.choice(W.WORDS)}&limit=8")[0]
    raise SystemExit(f"mix? {op}")


def walk_op(c, cursors, state):
    """One page of a whole object index; at its end, on to the next conversation."""
    conv = W.CPU_CONVS[state["k"] % len(W.CPU_CONVS)]
    st, b = read_ok(c, W.objects_path(conv, cursors.get(conv), W.WALK_PAGE))
    before = json.loads(b).get("before") if st == 200 else None
    cursors[conv] = before
    if not before:
        state["k"] += 1
    return st


def agent_op(c, op, rnd, grant, k):
    conv = W.CONVS[k % len(W.CONVS)]
    body = W.worker_body(op, conv, rnd.choice(W.WORDS), rnd.choice(W.WORK_TEXT), cfg["ref"])
    st, _ = c.ask("POST", "/api/worker", body=body, headers={W.WORKER: grant})
    return st


def worker(i, t0):
    rnd = random.Random(i * 7 + 1)
    c = W.Conn(PORT, TIMEOUT)
    cursors = {}
    seq = {"agent": W.AGENT_MIX, "sql": W.SQL_MIX, "cpu": ("objects_walk",), "mix": W.MIX}[KIND]
    pos, k = i, i * 3        # workers start apart in the round and in the conversations
    walk = {"k": i * 3 + cfg.get("round", 0) * W.CPU_ROUND_SHIFT}
    next_at = t0
    while not stopping.is_set():
        if PACE:
            d = next_at - time.time()
            if d > 0 and stopping.wait(d):
                break
            next_at += PACE
        op = seq[pos % len(seq)]
        pos += 1
        k += 1
        started = time.time()
        tp = time.perf_counter()
        try:
            if KIND == "agent":
                st = agent_op(c, op, rnd, cfg["grants"][i], k)
            elif KIND == "cpu":
                st = walk_op(c, cursors, walk)
            else:
                st = mix_op(c, op, rnd, cursors, k)
            ms = (time.perf_counter() - tp) * 1000
            with lock:
                records.append((i, op, round(started, 3), round(ms, 1), st))
        except Exception as exc:  # noqa: BLE001  an error is a result
            with lock:
                errors.append((i, op, round(started, 3), repr(exc)[:160]))
    c.close()
    finished[i] = True


threading.Thread(target=watch, daemon=True).start()
T0 = time.time() + 0.05
ths = [threading.Thread(target=worker, args=(i, T0), daemon=True) for i in range(N)]
for t in ths:
    t.start()
while not stopping.is_set():
    time.sleep(0.05)
stopped_at = time.time()
# a query in flight when the stop came is given time, then counted as unfinished
for t in ths:
    t.join(max(0.0, stopped_at + cfg.get("drain_s", 45) - time.time()))
json.dump({"kind": KIND, "n": N, "pace": PACE, "t0": T0, "stopped_at": stopped_at,
           "drained_at": time.time(), "records": records, "errors": errors,
           "finished": finished, "unfinished": sum(t.is_alive() for t in ths)},
          open(cfg["out"], "w"))
os._exit(0)
