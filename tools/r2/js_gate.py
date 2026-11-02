"""R2's JS gate: the same bundle gives byte-identical extraction across a Brain copy's objects.

    <venv>\\Scripts\\python.exe tools/r2/js_gate.py <brain copy> <bundle> <out dir> <gate.exe>

`<gate.exe>` is `cargo build --release -p mentis-extract --example gate`'s. For every version of every
post, the input is what `objects.input_of` gives the bundle. `quickjs-ng`, as `objects.py` loads it,
and `gate.exe` each read every input, and each output is compared as bytes. Prints one JSON object
and exits 1 on any difference. Reads the copy through `api.open_corpus`: never the live Brain.

**The 205 ms per extraction (`opr-ad1faac8373e`).** Every call is timed with Python's wrapper without the
collection, and one in `GC_SAMPLE` also as `objects.py` calls it (`run_gc=True`, its default), so the
figures say where the time goes. Reported, never a gate.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import statistics
import subprocess
import sys
import time

#: One input in this many is also called as `objects.py` calls it, with the collection.
GC_SAMPLE = 20


def _percentile(values: list[float], share: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * share), len(ordered) - 1)]


def _summary(values: list[float]) -> dict:
    return {"calls": len(values), "total_ms": round(sum(values), 3),
            "mean_ms": round(statistics.fmean(values), 3) if values else 0.0,
            "p50_ms": round(_percentile(values, 0.5), 3),
            "p95_ms": round(_percentile(values, 0.95), 3),
            "max_ms": round(max(values), 3) if values else 0.0}


def main(argv: list[str]) -> int:
    brain, bundle, out, gate = argv
    out_dir = pathlib.Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    import quickjs

    import mentis.api as api
    from mentis.fluid import objects, read
    from mentis.conversation import versions

    corpus = api.open_corpus(brain)
    raw = pathlib.Path(bundle).read_bytes()
    source = raw.decode("utf-8") + (
        "\nfunction mentisObjects(post) {"
        " if (typeof MentisRenderCheck.extractPost !== 'function')"
        "   throw new Error('this bundle has no extractPost: rebuild the UI');"
        " return JSON.stringify(MentisRenderCheck.extractPost(JSON.parse(post))) }")
    started = time.perf_counter()
    fn = quickjs.Function("mentisObjects", source)
    compile_ms = (time.perf_counter() - started) * 1000
    fn.set_time_limit(objects.TIME_LIMIT_S)
    fn.set_memory_limit(objects.MEMORY_LIMIT)

    posts = [e for e in corpus.entries_of_kind(read.CONTRIBUTION)
             if read.homes_of(corpus, [e["id"]])]
    inputs_path = out_dir / "inputs.jsonl"
    expected_path = out_dir / "expected.jsonl"
    with_gc, without_gc, oversized, versions_read = [], [], 0, 0
    failed, gc_differences = [], []
    with open(inputs_path, "w", encoding="utf-8", newline="\n") as inputs, \
            open(expected_path, "w", encoding="utf-8", newline="\n") as expected:
        for post in posts:
            root = post["id"]
            line = versions.lineage(corpus, root)
            returned = objects.returned_refs(corpus, root)
            for version in line["versions"]:
                given = objects.input_of(corpus, root, version, returned)
                size = sum(len(p.get("text") or "") for p in given["parts"]
                           if isinstance(p, dict))
                if size > objects.MAX_CHARS:
                    oversized += 1
                    continue
                text = json.dumps(given)
                versions_read += 1
                started = time.perf_counter()
                try:
                    got = fn(text, run_gc=False)
                except Exception as exc:                  # noqa: BLE001
                    got = None
                    failed.append({"version": version["id"], "why": str(exc)[:300]})
                without_gc.append((time.perf_counter() - started) * 1000)
                # The collection on every call would take the better part of an hour: a sample, each
                # of which also shows that the collection doesn't change what comes back.
                if versions_read % GC_SAMPLE == 1:
                    started = time.perf_counter()
                    try:
                        collected = fn(text)
                    except Exception:                     # noqa: BLE001
                        collected = None
                    with_gc.append((time.perf_counter() - started) * 1000)
                    if collected != got:
                        gc_differences.append(version["id"])
                inputs.write(text + "\n")
                expected.write(("!failed" if got is None else got) + "\n")

    outputs_path = out_dir / "outputs.jsonl"
    done = subprocess.run([gate, bundle, str(inputs_path), str(outputs_path)],
                          capture_output=True, text=True, encoding="utf-8")
    expected_lines = expected_path.read_bytes().split(b"\n")
    output_lines = outputs_path.read_bytes().split(b"\n") if outputs_path.exists() else []
    differences = []
    for at, (ours, theirs) in enumerate(zip(output_lines, expected_lines)):
        # A failure on both sides is forwarded to Python, so it's no difference. Its words can't match.
        if ours.startswith(b"!") and theirs.startswith(b"!"):
            continue
        if ours != theirs:
            differences.append({"line": at, "rust": ours[:300].decode("utf-8", "replace"),
                                "python": theirs[:300].decode("utf-8", "replace")})
    if len(output_lines) != len(expected_lines):
        differences.append({"lines": {"rust": len(output_lines), "python": len(expected_lines)}})
    try:
        rust = json.loads(done.stderr.strip().splitlines()[-1])
    except (IndexError, ValueError):
        rust = {"stderr": done.stderr[-2000:], "exit": done.returncode}
    report = {
        "bundle_sha256": hashlib.sha256(raw).hexdigest(),
        "bundle_bytes": len(raw),
        "posts": len(posts),
        "versions": versions_read,
        "oversized": oversized,
        "python_failures": failed[:20],
        "differences": len(differences),
        "first_differences": differences[:10],
        "python": {
            "compile_ms": round(compile_ms, 3),
            "with_gc": _summary(with_gc),
            "without_gc": _summary(without_gc),
            "gc_changed_the_answer": gc_differences[:20],
        },
        "rust": rust,
    }
    print(json.dumps(report, indent=1))
    return 1 if differences or done.returncode else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
