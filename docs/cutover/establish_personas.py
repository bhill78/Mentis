"""Establish the owner-approved Persona revisions (Builder, Independent Reviewer).

    python establish_personas.py <server> [--apply]

Approved by the owner on 2026-10-29. The approved texts are baseline v3's (this checkout's
mentis/bootstrap/baseline.json), which the baseline run proposed. For each standing Persona:
find the ONE proposal whose name, behaviour and about are exactly the approved ones, and
establish it with the owner's `establish-replacement`. Refuses rather than guesses (no
proposal, or more than one). Idempotent.
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

OWNER = "ent-5936369158a8"
PERSONAS = {"builder": "ent-850bb263a966", "independent-reviewer": "ent-8c79af1e8b4c"}
BASELINE = pathlib.Path(__file__).resolve().parents[2] / "mentis" / "bootstrap" / "baseline.json"


def call(server, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(server + path, data=data, method=method,
                                 headers={"X-Mentis-Client": "1", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:400]}


def main(server, apply):
    spec = {p["key"]: p for p in json.load(open(BASELINE, encoding="utf-8"))["personas"]}
    rc = 0
    for key, pred in PERSONAS.items():
        want = {f: spec[key].get(f, "") for f in ("name", "behaviour", "about")}
        got = call(server, "GET", f"/api/entries/{pred}")
        if not got.get("stands"):
            done = [e for e in (got.get("superseded_by") or [])
                    if {f: (call(server, "GET", f"/api/entries/{e}")["body"].get(f) or "") for f in want} == want]
            print(f"{key}: {pred} no longer stands; " + (f"already established as {done[0]}" if done else "REFUSED: replaced by something else"))
            rc |= 0 if done else 1
            continue
        props = [r["entry"] for r in ((got.get("proposed") or {}).get("successors") or {}).get("items") or []]
        exact = [e for e in props if {f: (call(server, "GET", f"/api/entries/{e}")["body"].get(f) or "") for f in want} == want]
        if len(exact) != 1:
            print(f"{key}: REFUSED: {len(exact)} proposals carry the approved text ({exact})"); rc = 1; continue
        print(f"{key}: {pred} -> establish {exact[0]}" + ("" if apply else " (dry run)"))
        if apply:
            res = call(server, "POST", f"/api/entries/{pred}/establish-replacement",
                       {"attributed_to": OWNER, "replacement": exact[0],
                        "because": "owner-approved Persona revision (2026-10-29), DAY-TO-DAY transition"})
            ok = not res.get("error") and call(server, "GET", f"/api/entries/{exact[0]}").get("stands") \
                and not call(server, "GET", f"/api/entries/{pred}").get("stands")
            print(f"   {'established' if ok else 'FAILED: ' + str(res)[:300]}"); rc |= 0 if ok else 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], "--apply" in sys.argv))
