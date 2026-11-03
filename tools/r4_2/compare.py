"""The real-data comparison, by route family: requests, Rust answers, forwards, bytes differ.

    python tools/r4_2/compare.py <brain copy> <out dir> <port base> <why.tsv>

`why.tsv` is `views.rs`'s `on_a_brain_copy_why_each_turn_forwards`: each Turn, ANSWERED or why not. A
forward that says Rust would have answered is retried once, so a moment without a fresh overlay isn't
counted as ownership. `review-owned.txt` holds the 117 Turns the review found Rust answering at
5ade14b, which with its seed gives its samples again.

`decisions` targets carry `&n=1`: Python's memo is keyed without `active_executions`, so this is a
fresh key. Nothing here begins an execution, so that memo couldn't be stale anyway;
`tests/front/test_r4_2_views.py` is where a run is live.
"""
import collections
import json
import pathlib
import random
import re
import sqlite3
import sys
import time

from common import HERE, Pair, get, walk

ROOT, OUT, BASE, WHY = sys.argv[1], pathlib.Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
NOT_DELIVERED = b"Python is not answering behind this front"
db = sqlite3.connect(f"file:{ROOT}/corpus.db?mode=ro", uri=True)


def Q(sql, *args):
    return db.execute(sql, args).fetchall()


convs = [r[0] for r in Q("select id from entry where family='entry' and def_name='conversation' "
                         "and link_relation is null order by seq")]
turns = [r[0] for r in Q("select id from entry where family='entry' and def_name='contribution' "
                         "and link_relation is null order by seq")]
home = dict(Q("select link_from, link_to from entry where link_relation='in-conversation' "
              "order by seq desc"))
replied = {r[0] for r in Q("select link_from from entry where link_relation='replies-to'")}
exps = [r[0] for r in Q("select id from operational where act='expectation-recorded' order by seq")]
others = [r[0] for r in Q("select id from entry where family='entry' and def_name in "
                          "('participant','topic','persona') and link_relation is null "
                          "order by seq limit 6")]
print("conversations", len(convs), "turns", len(turns), "replies", len(replied), "expectations",
      len(exps), flush=True)
why = dict(line.split("\t", 1) for line in open(WHY, encoding="utf8").read().splitlines())
was_owned = set((HERE / "review-owned.txt").read_text().split())
owned_now = [t for t in turns if why.get(t) == "ANSWERED"]
print("owned now by the op", len(owned_now), "owned at the review", len(was_owned), flush=True)

rng = random.Random(4242)
ans = [t for t in turns if t in was_owned]
reps = [t for t in turns if t in replied and t in home]
roots = [t for t in turns if t not in replied and t in home and t not in was_owned]
rest = [t for t in turns if t not in was_owned]


def sam(values, n):
    return rng.sample(values, min(n, len(values)))


fam = collections.OrderedDict()
fam["personas"] = ["/api/personas", "/api/personas?x=1"]
fam["intake"] = ["/api/intake", "/api/intake?x=1"]
ff = ["name,about,participants,topics", "name", "about", "participants", "topics", "topics,name",
      "name,name"]
fam["fields"] = [f"/api/conversations/{c}?fields={f}" for c in convs for f in ff]
fam["fields-edge"] = [f"/api/conversations/{convs[0]}?{q}" for q in (
    "fields=", "fields=,", "fields=%20", "fields=bogus", "fields=name,bogus",
    "fields=name&fields=topics", "batch=0&fields=name", "topic=x&fields=name")] + [
    f"/api/conversations/{x}?fields=name" for x in (turns[0], others[0], "nope",
                                                    "ent-000000000000")]
fam["turn-all"] = [f"/api/turns/{t}" for t in turns]
fam["turn-edge"] = [f"/api/turns/{x}" for x in others + ["nope", "opr-000000000000", exps[0],
                                                         convs[0]]]
fam["thread-review-owned"] = [f"/api/conversations/{home[t]}/thread/{t}" for t in ans if t in home]
fam["thread-of-a-reply"] = [f"/api/conversations/{home[t]}/thread/{t}" for t in sam(reps, 500)]
fam["thread-other-roots"] = [f"/api/conversations/{home[t]}/thread/{t}" for t in sam(roots, 300)]
fam["thread-owned-now"] = [f"/api/conversations/{home[t]}/thread/{t}" for t in owned_now
                           if t in home and t not in replied]
fam["thread-edge"] = [f"/api/conversations/{convs[0]}/thread/nope",
                      f"/api/conversations/nope/thread/{turns[0]}",
                      f"/api/conversations/{convs[1]}/thread/{turns[0]}",
                      f"/api/conversations/{others[0]}/thread/{turns[0]}"]
sam(rest, 300)  # the review's forwarded-Turn sample: every Turn is asked now, but the seed moves on
fam["decisions-post"] = [f"/fluid/api/decisions?post={t}&n=1" for t in ans + sam(rest, 400)]
fam["decisions-post-owned-now"] = [f"/fluid/api/decisions?post={t}&n=1" for t in owned_now]
fam["decisions-ids"] = [f"/fluid/api/decisions?ids={e}&n=1" for e in exps]
fam["decisions-edge"] = [
    "/fluid/api/decisions", "/fluid/api/decisions?post=nope",
    f"/fluid/api/decisions?post={others[0]}", f"/fluid/api/decisions?post={convs[0]}",
    "/fluid/api/decisions?ids=nope", "/fluid/api/decisions?ids=,",
    f"/fluid/api/decisions?ids={turns[0]}",
    f"/fluid/api/decisions?ids={exps[0]},{exps[1]},{exps[0]}",
    f"/fluid/api/decisions?ids={exps[0]}&post={turns[0]}", "/fluid/api/decisions?ids=a/b",
    "/fluid/api/decisions?ids=" + ",".join(f"x{i}" for i in range(70)),
    f"/fluid/api/decisions?ids=%1C{exps[0]}%1C"]
fam["id-parse-edge"] = [
    f"/api/turns?ids=%1C{turns[0]}%1C", f"/api/turns?ids={turns[0]}&ids={turns[1]}",
    f"/api/conversations/{convs[0]}?fields=name%1C",
    f"/api/conversations/{convs[0]}?fields=%85name", f"/api/turns/{turns[0]}%20",
    f"/api/turns/{turns[0].replace('-', '%2D')}",
    f"/api/conversations/{convs[0].replace('-', '%2D')}?fields=name",
    f"/api/conversations/{convs[0]}/thread/{turns[0].replace('-', '%2D')}"]
batches = []
for n, k in ((1, 40), (2, 40), (10, 40), (64, 20)):
    for _ in range(k):
        batches.append(",".join(rng.sample(ans, min(n, len(ans)))))
o0 = ans[0]
mixed = [f"{o0},nope,{others[0]}", "nope", f"{o0},{o0}", "%20,%20", "a/b",
         ",".join(f"x{i}" for i in range(65)), f"%20{o0}%20", f"{o0},{exps[0]}", f"{o0},{convs[0]}"]
randall = [",".join(rng.sample(turns, 10)) for _ in range(40)]
fam["batch-review-owned"] = [f"/api/turns?ids={b}" for b in batches]
fam["batch-edge"] = [f"/api/turns?ids={b}" for b in mixed] + ["/api/turns", "/api/turns?ids=&x=1"]
fam["batch-random"] = [f"/api/turns?ids={b}" for b in randall]
new_batches = []
if owned_now:
    for n, k in ((1, 40), (2, 40), (10, 40), (64, 20)):
        for _ in range(k):
            new_batches.append(",".join(rng.sample(owned_now, min(n, len(owned_now)))))
    new_batches += [f"{owned_now[0]},nope", f"{owned_now[0]},{exps[0]}"]
fam["batch-owned-now"] = [f"/api/turns?ids={b}" for b in new_batches]

p = Pair(ROOT, OUT, BASE)
rust = {}
for name, targets in fam.items():
    started = time.time()
    got = []
    for t in targets:
        got.append((t, get(p.fp, t)))
        if len(got) % 1000 == 0:
            print(name, "asked", len(got), round(time.time() - started, 1), "s", flush=True)
    p.ready(True, 20)
    fixed = undelivered = 0
    for i, (t, r) in enumerate(got):
        # The front forwarded and couldn't connect to this harness's proxy, on a machine out of
        # ephemeral ports. Python's own words, for a forward that never arrived: ask until it does.
        gave_up_at = time.monotonic() + 240
        while r[0] == 503 and NOT_DELIVERED in r[1] and time.monotonic() < gave_up_at:
            undelivered += 1
            time.sleep(2)
            r = get(p.fp, t)
            got[i] = (t, r)
        tid = re.split(r"[/=&]", t.split("&n=")[0])[-1]
        if r[0] == 599 and why.get(tid) == "ANSWERED" and "?ids=" not in t:
            again = get(p.fp, t)
            if again[0] != 599:
                got[i] = (t, again)
                fixed += 1
    rust[name] = got
    print(name, len(got), dict(collections.Counter(r[0] for _, r in got)), "retried-into-answer",
          fixed, "undelivered-forwards-asked-again", undelivered, round(time.time() - started, 1),
          "s", flush=True)

table, kinds, examples = {}, collections.Counter(), {}
timing = collections.defaultdict(lambda: ([], []))
forwards = collections.defaultdict(list)
for name, got in rust.items():
    tally = collections.Counter()
    for t, r in got:
        if r[0] == 599:
            tally["forwards"] += 1
            forwards[name].append(r[2])
            continue
        pc, pb, pt, pct = get(p.pp, t)
        timing[name][0].append(r[2])
        timing[name][1].append(pt)
        tally["answers"] += 1
        if (pc, pb, pct) == (r[0], r[1], r[3]):
            continue
        tally["differ"] += 1
        try:
            diffs = walk(json.loads(pb), json.loads(r[1]))
        except ValueError:
            diffs = [("<raw>", pb[:300].decode("utf8", "replace"),
                      r[1][:300].decode("utf8", "replace"))]
        if pc != r[0]:
            diffs.insert(0, ("<status>", pc, r[0]))
        if pct != r[3]:
            diffs.insert(0, ("<ctype>", pct, r[3]))
        for at, a, b in diffs or [("<key order>", pb[:200].decode("utf8", "replace"),
                                   r[1][:200].decode("utf8", "replace"))]:
            key = name + " " + re.sub(r"\[\d+\]", "[]", at)
            kinds[key] += 1
            examples.setdefault(key, (t, repr(a)[:300], repr(b)[:300]))
    table[name] = {"requests": len(got), "answers": tally["answers"], "forwards": tally["forwards"],
                   "differ": tally["differ"],
                   "statuses": dict(collections.Counter(str(r[0]) for _, r in got))}
    print("COMPARE", name, table[name], flush=True)


def pct(values, q):
    return round(sorted(values)[min(len(values) - 1, int(len(values) * q))] * 1e3, 2) if values else None


report = {"table": table, "kinds": kinds, "examples": examples,
          "answer_ms": {n: {"rust_p50": pct(v[0], .5), "rust_p95": pct(v[0], .95),
                            "python_p50": pct(v[1], .5), "python_p95": pct(v[1], .95)}
                        for n, v in timing.items()},
          "forward_ms": {n: {"p50": pct(v, .5), "p95": pct(v, .95)} for n, v in forwards.items()},
          "panics": p.panics(),
          "scope_expired": sum(1 for g in rust.values() for _, r in g
                               if r[0] == 503 and b"ScopeExpired" in r[1])}
(OUT / "report.json").write_text(json.dumps(report, indent=1), encoding="utf8")
print(f"{'family':28} {'requests':>9} {'answers':>8} {'forwards':>9} {'differ':>7}")
for n, row in table.items():
    print(f"{n:28} {row['requests']:>9} {row['answers']:>8} {row['forwards']:>9} {row['differ']:>7}")
for key, n in kinds.most_common(80):
    print(n, key, examples[key][0][:100], "PY", examples[key][1][:220], "RS", examples[key][2][:220])
print("panics", report["panics"], "scope_expired", report["scope_expired"])
p.stop()
