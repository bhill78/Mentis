"""The same cold window reads over HTTP, Python alone and the pair, each on a fresh copy and a new process:
what a read a person waits on costs per request and per extraction it had to make (`opr-ad1faac8373e`).
Reported, never a gate.

    <venv>\\Scripts\\python.exe tools/r2/window_cost.py <directory for its two copies> [port]

`MENTIS_UNDER_TEST` and `MENTIS_R1_FIXTURES` as for `tests/front`. Reads in one order on each side:
`thread=1` batches first, since nothing is warm, then each sampled post's objects, then the same reads
from four clients at once on posts not yet read. The figures are only for the machine as it stood.
"""

from __future__ import annotations

import concurrent.futures
import json
import pathlib
import statistics
import sys
import time

from tests.front.pair import CLIENT, Pair, ask, process_tree, rows
from tools.r1 import common, copy_brain, py_alone

MANIFEST = common.EVIDENCE / "brain-copy-manifest.json"
WAIT_S = 600.0


def _summary(values: list[float]) -> dict:
    ordered = sorted(values)
    return {"n": len(values), "total_s": round(sum(values) / 1000, 2),
            "mean_ms": round(statistics.fmean(values), 1),
            "p50_ms": round(ordered[len(ordered) // 2], 1),
            "p95_ms": round(ordered[int(len(ordered) * 0.95)], 1),
            "max_ms": round(ordered[-1], 1)}


def _timed(port: int, target: str) -> tuple[float, bytes]:
    started = time.perf_counter()
    got = ask(port, "GET", target, headers=CLIENT, wait=WAIT_S)
    assert got.status == 200, got
    return (time.perf_counter() - started) * 1000, got.body


def _measure(port: int, posts: list[str]) -> dict:
    batches = [",".join(posts[at:at + 64]) for at in range(0, 64 * 40, 320)]
    thread = [_timed(port, f"/fluid/api/posts?ids={ids}&thread=1") for ids in batches]
    extracted = sum(p.get("thread", {}).get("replies", 0) for _, body in thread
                    for p in json.loads(body)["posts"])
    alone = [_timed(port, f"/fluid/api/objects?post={post}")[0] for post in posts[3000:6000:8]]
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        together = list(pool.map(lambda post: _timed(port, f"/fluid/api/objects?post={post}")[0],
                                 posts[3001:6000:8]))
    return {"thread_1_batches_of_64": _summary([one for one, _ in thread]),
            "replies_those_batches_count": extracted,
            "objects_one_post_cold": _summary(alone),
            "objects_one_post_cold_four_clients": _summary(together)}


def main(argv: list[str]) -> int:
    base = pathlib.Path(argv[0])
    port = int(argv[1]) if len(argv) > 1 else 8980
    py_copy = copy_brain.fresh(base / "py" / "brain", common.master_dir(), MANIFEST)
    pair_copy = copy_brain.fresh(base / "pair" / "brain", common.master_dir(), MANIFEST)
    posts = [row[0] for row in rows(pair_copy, """
        SELECT DISTINCT e.id FROM entry e JOIN entry l
          ON l.link_from = e.id AND l.link_relation = 'in-conversation'
        WHERE e.family = 'entry' AND e.def_name = 'contribution' AND e.link_relation IS NULL
        ORDER BY e.seq""")]
    out = {}
    with py_alone.running(py_copy, port=port, code=common.REPO):
        out["python"] = _measure(port, posts)
    with Pair(pair_copy, port=port + 1) as pair:
        out["rust"] = _measure(pair.port, posts)
        out["rust_python_child_cores_s"] = [p for p in process_tree(pair.python_pid)]
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
