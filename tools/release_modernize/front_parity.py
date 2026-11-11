"""Does the serving Rust front still say what the Python it fronts would say? (task 3)

    python -I front_parity.py BASE ROUTE_TABLE_FILE OUT.json [--conversation ID] [--post ID]

The front was started with `--route-table ROUTE_TABLE_FILE` (a copy of the shipped default).
For every GET route the table gives to Rust, this asks the front (Rust answers), then rewrites
the file with every Rust GET route handed to Python (the front re-reads it within ~1 s, no
restart), asks again (Python answers through the same front), restores the file, and compares
the two JSON bodies with volatile fields removed. A route whose answers differ is listed with
the first differing paths. Run it against the candidate pair AND the old pair: a difference
only the candidate shows is one the candidate's Python changes caused.
"""
import json
import shutil
import sys
import time
import urllib.error
import urllib.request

VOLATILE = {"at", "now", "generated_at", "took_ms", "elapsed_ms", "ms", "served_by", "timing",
            "computed_at", "as_of", "fresh_at", "expires_in_s", "age_s", "since_s", "ago", "ago_s",
            "cursor", "etag", "boot", "boot_id", "process", "words_at"}


def get(base, path):
    req = urllib.request.Request(base + path, headers={"X-Mentis-Client": "1"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def norm(v):
    if isinstance(v, dict):
        return {k: norm(x) for k, x in v.items() if k not in VOLATILE}
    if isinstance(v, list):
        return [norm(x) for x in v]
    return v


def diffs(a, b, here="", out=None, most=8):
    out = [] if out is None else out
    if len(out) >= most:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{here}/{k}: only in {'python' if k in b else 'rust'}")
            else:
                diffs(a[k], b[k], f"{here}/{k}", out, most)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{here}: rust {len(a)} items, python {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            diffs(x, y, f"{here}[{i}]", out, most)
    elif a != b:
        out.append(f"{here}: rust {json.dumps(a)[:80]} python {json.dumps(b)[:80]}")
    return out


def main():
    base, table_file, out = sys.argv[1:4]
    a = sys.argv[4:]
    conv = a[a.index("--conversation") + 1] if "--conversation" in a else None
    post = a[a.index("--post") + 1] if "--post" in a else None
    table = json.load(open(table_file, encoding="utf-8"))
    rust_gets = [r for r in table["routes"] if r["owner"] == "rust" and r["method"] == "GET" and r["path"] != "*"]
    # concrete requests for each Rust route; {} filled from what the record holds
    samples = {
        "/fluid/api/collections/conversation": f"?id={conv}&limit=20" if conv else None,
        "/fluid/api/collections/thread": f"?id={post}" if post else None,
        "/fluid/api/posts": f"?ids={post}&thread=1" if post else None,
        "/fluid/api/objects": f"?post={post}" if post else None,
        "/fluid/api/needs-you": f"?post={post}" if post else None,
        "/fluid/api/decisions": f"?post={post}" if post else None,
        "/fluid/api/conversations": "?activity=1",
        "/fluid/api/anchors": f"?post={post}" if post else None,
        "/fluid/api/search": "?q=release",
        "/fluid/api/object-refs": f"?post={post}" if post else None,
        "/api/references": "?q=release",
        "/fluid/api/needs-you/items": "",
        "/fluid/api/latest": f"?conversation={conv}" if conv else "",
        "/fluid/api/changes": f"?conversation={conv}" if conv else "",
        "/api/conversations/{}": None, "/api/turns/{}": None,
        "/fluid/api/posts/{}/anchors": None, "/fluid/api/objects/{}": None,
        "/fluid/api/magnets/{}/read": None, "/api/conversations/{}/thread/{}": None,
        "/fluid/api/response-sets/{}/history": None, "/fluid/api/response-sets/{}/accounting": None,
    }
    if conv:
        samples["/api/conversations/{}"] = f"/api/conversations/{conv}"
    if post:
        samples["/fluid/api/posts/{}/anchors"] = f"/fluid/api/posts/{post}/anchors"
    asks = []
    for r in rust_gets:
        p = r["path"]
        s = samples.get(p, "")
        if s is None:
            asks.append((r["id"], None)); continue
        asks.append((r["id"], s if s.startswith("/") else p + s))

    def round_():
        got = {}
        for rid, path in asks:
            if path is None:
                continue
            status, body, headers = get(base, path)
            try:
                value = json.loads(body)
            except ValueError:
                value = {"_bytes": len(body)}
            got[rid] = {"path": path, "status": status, "value": value}
        return got

    rust = round_()
    backup = table_file + ".parity-backup"
    shutil.copy2(table_file, backup)
    try:
        flipped = dict(table)
        flipped["routes"] = [dict(r, owner="python") if r in rust_gets else r for r in table["routes"]]
        with open(table_file, "w", encoding="utf-8") as f:
            json.dump(flipped, f)
        time.sleep(3)
        python = round_()
    finally:
        shutil.copy2(backup, table_file)
        import os
        os.unlink(backup)
    time.sleep(2)
    report = {"routes": len(asks), "asked": len(rust), "not_sampled": [rid for rid, p in asks if p is None],
              "same": [], "different": {}}
    for rid in rust:
        r, p = rust[rid], python[rid]
        if r["status"] != p["status"]:
            report["different"][rid] = {"path": r["path"], "status": [r["status"], p["status"]]}
            continue
        d = diffs(norm(r["value"]), norm(p["value"]))
        if d:
            report["different"][rid] = {"path": r["path"], "status": r["status"], "first": d}
        else:
            report["same"].append(rid)
    json.dump(report, open(out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({"asked": report["asked"], "same": len(report["same"]),
                      "different": sorted(report["different"]), "not_sampled": report["not_sampled"]}))


if __name__ == "__main__":
    main()
