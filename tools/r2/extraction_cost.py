"""Where a cold extraction's time goes in Python (`opr-ad1faac8373e`, "about 205 ms each on the bench").
Reported, never a gate.

    <venv>\\Scripts\\python.exe tools/r2/extraction_cost.py <brain copy> <bundle> [every]

Calls `objects.extract` on every `every`th post, as the server does, in this one process, with each
step timed from outside: nothing in Mentis changes. Hashing a held file happens once per file version
in a process, so the first read of an attachment costs its whole file and the later ones nothing: the
figures are of a cold process, which is what a first window after a boot is.
"""

from __future__ import annotations

import json
import pathlib
import statistics
import sys
import time


def main(argv: list[str]) -> int:
    brain, bundle, every = argv[0], argv[1], int(argv[2]) if len(argv) > 2 else 10
    import mentis.api as api
    from mentis import artifacts
    from mentis.conversation import versions
    from mentis.fluid import objects, read

    corpus = api.open_corpus(brain)
    posts = [e for e in corpus.entries_of_kind(read.CONTRIBUTION) if read.homes_of(corpus, [e["id"]])]
    spent: dict[str, float] = {}
    calls: dict[str, int] = {}

    def timed(owner, name, label):
        inner = getattr(owner, name)

        def wrapper(*args, **kw):
            started = time.perf_counter()
            try:
                return inner(*args, **kw)
            finally:
                spent[label] = spent.get(label, 0.0) + time.perf_counter() - started
                calls[label] = calls.get(label, 0) + 1
        setattr(owner, name, wrapper)

    timed(objects, "returned_refs", "returned_refs")
    timed(objects, "input_of", "input_of (holds describe)")
    timed(objects, "_run", "_run (the engine, with _load)")
    timed(objects, "_load", "_load (reads and hashes the bundle, every call)")
    timed(objects, "_bundle_digest", "_bundle_digest")
    timed(artifacts, "_state_cached", "_state_cached (hashes a held file, once)")
    timed(objects.json, "dumps", "json.dumps")
    timed(objects.json, "loads", "json.loads")

    each, hashed = [], {}
    pre = time.perf_counter()
    lines = [(post["id"], versions.lineage(corpus, post["id"])["versions"][-1]) for post in posts[::every]]
    lineage_ms = (time.perf_counter() - pre) * 1000
    bundle_path = pathlib.Path(bundle)
    for root, version in lines:
        started = time.perf_counter()
        got = objects.extract(corpus, root, version, bundle=bundle_path)
        each.append((time.perf_counter() - started) * 1000)
        assert got.get("extracted") is True, got.get("why_not")
    held = list(artifacts._VERIFIED)
    each_sorted = sorted(each)
    print(json.dumps({
        "extractions": len(each),
        "of_posts": len(posts),
        "lineage_ms_each_outside_extract": round(lineage_ms / len(lines), 3),
        "extract_ms": {
            "mean": round(statistics.fmean(each), 3),
            "p50": round(each_sorted[len(each) // 2], 3),
            "p95": round(each_sorted[int(len(each) * 0.95)], 3),
            "max": round(each_sorted[-1], 3),
            "total": round(sum(each), 1),
        },
        "steps_ms": {k: {"total": round(v * 1000, 1), "calls": calls[k],
                         "per_extraction": round(v * 1000 / len(each), 3)}
                     for k, v in sorted(spent.items(), key=lambda kv: -kv[1])},
        "held_files_hashed": len(held),
        "held_bytes_hashed": sum(key[2] for key in held),
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
