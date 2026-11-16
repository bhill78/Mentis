"""Record summaries, as one bounded batch somebody runs (never a service).

A Brain list row shows one human-readable sentence per record
(`mentis/record_summaries.py`). Where none is kept, the row shows the record's
own first sentence. This tool is how kept summaries are made in bulk, for ONE
Brain at a time -- the Brain the named server serves:

    1. export   the listed records that have no kept summary, with their own
                words and the sha256 of those words (`of`). Reads only.
    2. reuse    from a library of summaries already written AND validated for
                another Brain, take only those whose record here has the SAME
                id AND the SAME words (`of`). Two Brains that began as copies
                diverge; a summary is never carried over on its id alone.
    3. (write)  somebody, or a model somebody chose, writes one sentence for
                each record left: [{"id", "summary"}].
    4. check    every summary against its source record, mechanically: it
                names a record in the export, is one line of at most 200
                characters, and every number and identifier it contains
                occurs in the record. What a machine cannot judge (a lost
                "not", a hypothesis stated as fact) is FLAGGED for a reader;
                nothing with an unreviewed flag or a hard failure is imported.
    5. import   keeps them as `generated`, each saying who ran the batch, what
                wrote it and when. Only records still without a kept summary,
                whose words are still the words that were summarised, are
                written; a summary somebody wrote by hand is never replaced.

    python tools/brain_summaries.py export --server URL --out missing.json
    python tools/brain_summaries.py reuse  --missing missing.json --library validated.json \
                                           --out reused.json --rest to-write.json
    python tools/brain_summaries.py check  --missing missing.json --file summaries.json \
                                           --report report.json [--reviewed reviewed.json]
    python tools/brain_summaries.py import --server URL --missing missing.json \
                                           --file summaries.json --report report.json --model "..."

WHAT IT IS NOT. Nothing runs this for you, nothing re-makes a summary when a
list loads, and nothing here touches the record: a summary is presentation
metadata beside the Brain, read by no agent. The owner corrects any of them in
the record's own view. It writes through the server's owner route, so it acts
on whichever Brain that server serves: name the server deliberately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request

HEADERS = {"X-Mentis-Client": "1", "Content-Type": "application/json"}
MAX_LEN = 200

#: words that carry uncertainty, limits or a negative result: where the record
#: opens with one and the summary has none, a reader looks at the pair
HEDGES = ("may ", "might", "possibl", "probabl", "not yet", "unverified", "unconfirmed",
          "hypothes", "suspect", "appears", "seems", "partial", "inconclusive", "not merged",
          "not deployed", "failed", "blocked", "awaiting", "pending", "unknown", "not established")


def digest(words: str) -> str:
    return hashlib.sha256((words or "").encode("utf-8")).hexdigest()


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


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=1)


def missing_of(server: str) -> list:
    items, offset = [], 0
    while True:
        page = call(server, f"/api/ladder/summaries/missing?limit=200&offset={offset}")
        items += page["items"]
        offset += len(page["items"])
        if not page["items"] or offset >= page["total"]:
            break
    for item in items:
        item["of"] = digest(item.get("words") or "")
    return items


def export(a) -> int:
    items = missing_of(a.server)
    save(a.out, items)
    print(f"{len(items)} records without a kept summary written to {a.out}")
    return 0


def reuse(a) -> int:
    """Carry a validated summary over only where the record is the same record
    with the same words."""
    library = {row["id"]: row for row in load(a.library)}
    took, rest, differs = [], [], 0
    for item in load(a.missing):
        row = library.get(item["id"])
        if row and row.get("of") == item["of"] and isinstance(row.get("summary"), str):
            took.append({"id": item["id"], "summary": row["summary"], "of": item["of"],
                         "reused": True})
        else:
            differs += bool(row)
            rest.append(item)
    save(a.out, took)
    save(a.rest, rest)
    print(f"{len(took)} reused (same id and same words); {len(rest)} left to write"
          f" ({differs} of them have a library summary written for different words)")
    return 0


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/\\-]*[A-Za-z0-9]|[A-Za-z0-9]")


def _specific(token: str) -> bool:
    """A token a summary may only use if the record has it: a number, an
    identifier, or a name written with capitals or punctuation inside."""
    if any(c.isdigit() for c in token):
        return True
    if any(c in token for c in "_./:\\") or (token.count("-") and token.upper() == token):
        return True
    return len(token) > 1 and (token.isupper() or any(c.isupper() for c in token[1:]))


def flags_of(item: dict, summary: str) -> tuple[list, list]:
    """(hard failures, flags for a reader) of one summary against its record."""
    hard, soft = [], []
    if not isinstance(summary, str) or not summary.strip():
        return ["no summary"], soft
    if "\n" in summary or "\r" in summary:
        hard.append("more than one line")
    if len(" ".join(summary.split())) > MAX_LEN:
        hard.append(f"over {MAX_LEN} characters")
    source = " ".join([item.get("words") or "", item.get("name") or "",
                       *(str(v) for v in (item.get("fields") or {}).values())])
    low = source.lower()
    for token in dict.fromkeys(_TOKEN.findall(summary)):
        if _specific(token) and token.lower().strip(".:") not in low:
            soft.append(f"`{token}` is not in the record")
    opening = low[:400]
    if any(h in opening for h in HEDGES) and not any(h in summary.lower() + " " for h in HEDGES):
        soft.append("the record opens with a limit or uncertainty the summary does not carry")
    return hard, soft


def check(a) -> int:
    source = {item["id"]: item for item in load(a.missing)}
    reviewed = {}
    if a.reviewed:
        for row in load(a.reviewed):
            reviewed[row["id"]] = row
    rows, hard_n, open_flags = [], 0, 0
    seen = set()
    for row in load(a.file):
        eid, summary = row.get("id"), row.get("summary")
        item = source.get(eid)
        if item is None:
            rows.append({"id": eid, "hard": ["not a record in this export"], "flags": []})
            hard_n += 1
            continue
        if eid in seen:
            rows.append({"id": eid, "hard": ["named twice"], "flags": []})
            hard_n += 1
            continue
        seen.add(eid)
        hard, soft = flags_of(item, summary)
        if row.get("of") not in (None, item["of"]):
            hard.append("written for different words than this record has")
        said = reviewed.get(eid) or {}
        # a reader's word clears the flags of exactly the summary they read
        cleared = bool(soft) and said.get("summary") == summary and said.get("verdict") == "ok"
        rows.append({"id": eid, "summary": summary, "of": item["of"], "hard": hard, "flags": soft,
                     "reviewed": said.get("by") if cleared else None})
        hard_n += bool(hard)
        open_flags += bool(soft) and not cleared
    absent = [eid for eid in source if eid not in seen]
    report = {"records": len(source), "summaries": len(seen), "hard_failures": hard_n,
              "unreviewed_flags": open_flags, "without_a_summary": absent, "rows": rows}
    save(a.report, report)
    print(f"{len(seen)} summaries for {len(source)} records: {hard_n} hard failures, "
          f"{open_flags} flagged and not yet reviewed, {len(absent)} records without one")
    return 1 if hard_n or open_flags else 0


def owner_of(server: str) -> str:
    who = call(server, "/fluid/api/needs-you/items").get("owner")
    if not who:
        raise SystemExit("the server names no owner; pass --attributed-to")
    return who


def import_(a) -> int:
    report = load(a.report)
    if report.get("hard_failures") or report.get("unreviewed_flags"):
        raise SystemExit("the check report has hard failures or unreviewed flags: nothing is imported")
    passed = {r["id"]: r for r in report["rows"] if not r["hard"] and (not r["flags"] or r["reviewed"])}
    # WHAT THE SERVER HOLDS NOW decides: only records still without a kept
    # summary, whose words are the words that were summarised, are written
    now = {item["id"]: item["of"] for item in missing_of(a.server)}
    items, skipped = [], []
    for row in load(a.file):
        ok = passed.get(row.get("id"))
        if not ok or ok["summary"] != row.get("summary"):
            skipped.append((row.get("id"), "not the summary the check passed"))
        elif row["id"] not in now:
            skipped.append((row["id"], "already has a kept summary, or is no longer listed"))
        elif now[row["id"]] != ok["of"]:
            skipped.append((row["id"], "its words are not the words that were summarised"))
        else:
            items.append({"id": row["id"], "summary": row["summary"]})
    by = a.attributed_to or owner_of(a.server)
    kept, refused = [], []
    for at in range(0, len(items), 200):
        got = call(a.server, "/api/ladder/summaries",
                   {"attributed_to": by, "model": a.model, "items": items[at:at + 200]})
        kept += got["kept"]
        refused += got["refused"]
    print(f"kept {len(kept)}, refused {len(refused)}, skipped {len(skipped)}")
    for r in refused:
        print(f"  refused {r['id']}: {r['why']}")
    for eid, why in skipped:
        print(f"  skipped {eid}: {why}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="write the records that have no kept summary")
    e.add_argument("--server", required=True)
    e.add_argument("--out", required=True)
    e.set_defaults(run=export)
    r = sub.add_parser("reuse", help="take validated summaries whose record has the same id and words")
    r.add_argument("--missing", required=True)
    r.add_argument("--library", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--rest", required=True)
    r.set_defaults(run=reuse)
    c = sub.add_parser("check", help="check summaries against their source records")
    c.add_argument("--missing", required=True)
    c.add_argument("--file", required=True)
    c.add_argument("--report", required=True)
    c.add_argument("--reviewed", help="a reader's verdicts on flagged summaries: [{id, summary, verdict, by}]")
    c.set_defaults(run=check)
    i = sub.add_parser("import", help="keep a checked file of generated summaries")
    i.add_argument("--server", required=True)
    i.add_argument("--missing", required=True)
    i.add_argument("--file", required=True)
    i.add_argument("--report", required=True)
    i.add_argument("--model", required=True, help="what wrote the summaries")
    i.add_argument("--attributed-to", help="the owner's participant id (asked of the server if absent)")
    i.set_defaults(run=import_)
    a = p.parse_args(argv)
    return a.run(a)


if __name__ == "__main__":
    sys.exit(main())
