"""The review's section 6: one client, sequential, Python direct beside the fronts, no proxy.

    python tools/r4_2/cost.py <brain copy> <out dir> <port base> <n> <why.tsv> <base front> [<other front>...]

`R42_FRONT` is the front under test. Each other front answers the same requests beside it.
"""
import collections
import os
import pathlib
import random
import sqlite3
import subprocess
import sys
import threading
import time

from common import CODE, FRONT, HERE, PY, SECRET, get, start_front, wait

ROOT, OUT, BASE, N, WHY = (sys.argv[1], pathlib.Path(sys.argv[2]), int(sys.argv[3]),
                           int(sys.argv[4]), sys.argv[5])
FRONTS = {"r4.2": FRONT}
for i, path in enumerate(sys.argv[6:]):
    FRONTS[pathlib.Path(path).parts[-4] if len(pathlib.Path(path).parts) > 4 else f"front{i}"] = path
OUT.mkdir(exist_ok=True, parents=True)
db = sqlite3.connect(f"file:{ROOT}/corpus.db?mode=ro", uri=True)


def Q(sql, *args):
    return db.execute(sql, args).fetchall()


why = dict(line.split("\t", 1) for line in open(WHY, encoding="utf8").read().splitlines())
home = dict(Q("select link_from, link_to from entry where link_relation='in-conversation'"))
rng = random.Random(7)
ans = [t for t, w in why.items() if w == "ANSWERED"]
fwd = [t for t, w in why.items() if w != "ANSWERED"]
exps = [r[0] for r in Q("select id from operational where act='expectation-recorded'")]
convs = [r[0] for r in Q("select id from entry where family='entry' and def_name='conversation' "
                         "and link_relation is null")]
replies = [r[0] for r in Q("select link_from from entry where link_relation='replies-to'")
           if r[0] in home]
env = {**os.environ, "MENTIS_BOOT_SECRET": SECRET, "PYTHONPATH": CODE, "PYTHONIOENCODING": "utf-8",
       "PYTHONDONTWRITEBYTECODE": "1"}
pl = open(OUT / "py.log", "w")
py = subprocess.Popen([PY, "-m", "mentis.web", ROOT, "--host", "127.0.0.1", "--port", str(BASE),
                       "--workspace", str(OUT / "ws")], cwd=CODE, env=env, stdout=pl, stderr=pl)
wait(BASE)
get(BASE, "/api/server")
ports, running, logs = {}, [], []
import common  # noqa: E402

for i, (label, path) in enumerate(FRONTS.items()):
    common.FRONT = path
    log = open(OUT / f"front-{i}.log", "w")
    logs.append(log)
    ports[label] = BASE + 2 + i
    running.append(start_front(ROOT, ports[label], BASE, OUT, log))


def pulse():
    while True:
        for port in ports.values():
            try:
                get(port, "/api/pulse", 5)
            except Exception:  # noqa: BLE001
                pass
        time.sleep(.5)


threading.Thread(target=pulse, daemon=True).start()
time.sleep(1.5)


def pick(values, n):
    return [rng.choice(values) for _ in range(n)] if values else []


rows = collections.OrderedDict()
rows["personas"] = ["/api/personas"] * N
rows["intake"] = ["/api/intake"] * N
rows["fields, all four"] = [f"/api/conversations/{c}?fields=name,about,participants,topics"
                            for c in pick(convs, N)]
rows["fields=name"] = [f"/api/conversations/{c}?fields=name" for c in pick(convs, N)]
rows["Turn, owned shape"] = [f"/api/turns/{t}" for t in pick(ans, N)]
rows["Turn, forwarded shape"] = [f"/api/turns/{t}" for t in pick(fwd, N)]
rows["Batch of 10, owned"] = ["/api/turns?ids=" + ",".join(pick(ans, 10)) for _ in range(N // 2)]
rows["Batch of 64, owned"] = ["/api/turns?ids=" + ",".join(pick(ans, 64)) for _ in range(N // 4)]
rows["Batch of 10, real mix"] = ["/api/turns?ids=" + ",".join(pick(list(why), 10))
                                 for _ in range(N // 2)]
rows["Thread, owned root"] = [f"/api/conversations/{home[t]}/thread/{t}"
                              for t in pick([a for a in ans if a in home], N)]
rows["Thread of a reply"] = [f"/api/conversations/{home[t]}/thread/{t}" for t in pick(replies, N)]
rows["decisions?post"] = [f"/fluid/api/decisions?post={t}&n={i}"
                          for i, t in enumerate(pick(ans, N))]
rows["decisions?ids"] = [f"/fluid/api/decisions?ids={e}&n={i}" for i, e in enumerate(pick(exps, N))]


def pct(values, q):
    return round(sorted(values)[min(len(values) - 1, int(len(values) * q))] * 1e3, 1)


labels = list(ports)
print("route | n | python | " + " | ".join(labels) + " | statuses of " + labels[0])
for name, targets in rows.items():
    times = collections.defaultdict(list)
    statuses = collections.Counter()
    for t in targets:
        for label, port in ports.items():
            got = get(port, t)
            times[label].append(got[2])
            if label == labels[0]:
                statuses[got[0]] += 1
        times["python"].append(get(BASE, t)[2])
    if not targets:
        continue
    cells = " | ".join(f"{pct(times[k], .5)}/{pct(times[k], .95)}" for k in labels)
    print(f"{name} | {len(targets)} | {pct(times['python'], .5)}/{pct(times['python'], .95)} | {cells} "
          f"| {dict(statuses)}", flush=True)
for p in running + [py]:
    p.kill()
    p.wait(20)
os._exit(0)
