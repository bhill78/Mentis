"""Record summaries, as one bounded batch somebody runs (never a service).

A Brain list row shows one human-readable sentence per record
(`mentis/record_summaries.py`). Where none is kept, the row shows the record's
own first sentence. This tool is how kept summaries are made in bulk:

    python tools/brain_summaries.py export --server http://127.0.0.1:8780 --out missing.json
        Writes the listed records that have no kept summary, with their own
        words. Reads only.

    (somebody, or a model somebody chose, writes one sentence per record into
     a JSON list: [{"id": "ent-...", "summary": "..."}, ...])

    python tools/brain_summaries.py import --server http://127.0.0.1:8780 \
        --file summaries.json --model "<what wrote them>"
        Keeps them as `generated`, each saying who ran the batch, what wrote it
        and when. A summary somebody wrote by hand is never replaced; a refused
        one is reported and the rest are kept.

WHAT IT IS NOT. Nothing runs this for you, nothing re-makes a summary when a
list loads, and nothing here touches the record: a summary is presentation
metadata beside the Brain, read by no agent. The owner corrects any of them in
the record's own view. It writes through the server's owner route, so it acts
on whichever Brain that server serves: name the server deliberately.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

HEADERS = {"X-Mentis-Client": "1", "Content-Type": "application/json"}


def call(server: str, path: str, body=None):
    req = urllib.request.Request(server.rstrip("/") + path, headers=HEADERS,
                                 data=None if body is None else json.dumps(body).encode("utf-8"),
                                 method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            got = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{path}: HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}")
    if isinstance(got, dict) and got.get("error"):
        raise SystemExit(f"{path}: {got['error']}")
    return got


def export(a) -> int:
    items, offset = [], 0
    while True:
        page = call(a.server, f"/api/ladder/summaries/missing?limit=200&offset={offset}")
        items += page["items"]
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            break
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print(f"{len(items)} records without a kept summary written to {a.out}")
    return 0


def owner_of(server: str) -> str:
    who = call(server, "/fluid/api/needs-you/items").get("owner")
    if not who:
        raise SystemExit("the server names no owner; pass --attributed-to")
    return who


def import_(a) -> int:
    with open(a.file, encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list):
        raise SystemExit("the file holds a JSON list of {id, summary}")
    by = a.attributed_to or owner_of(a.server)
    kept, refused = [], []
    for at in range(0, len(items), 200):
        got = call(a.server, "/api/ladder/summaries",
                   {"attributed_to": by, "model": a.model, "items": items[at:at + 200]})
        kept += got["kept"]
        refused += got["refused"]
    print(f"kept {len(kept)}, refused {len(refused)}")
    for r in refused:
        print(f"  refused {r['id']}: {r['why']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="write the records that have no kept summary")
    e.add_argument("--server", required=True)
    e.add_argument("--out", required=True)
    e.set_defaults(run=export)
    i = sub.add_parser("import", help="keep a file of generated summaries")
    i.add_argument("--server", required=True)
    i.add_argument("--file", required=True)
    i.add_argument("--model", required=True, help="what wrote the summaries")
    i.add_argument("--attributed-to", help="the owner's participant id (asked of the server if absent)")
    i.set_defaults(run=import_)
    a = p.parse_args(argv)
    return a.run(a)


if __name__ == "__main__":
    sys.exit(main())
