"""Establish the owner's approved governance on a Brain, as the owner, through its server.

    python tools/establish_governance.py --server URL [--decisions FILE]
        [--apply --attributed-to <owner Participant>] [--json]

WHAT IT DOES, FOR EACH APPROVED ITEM (docs/cutover/governance-2026-10-29.json):

- A SUCCESSOR names the predecessor it replaces. Its proposal is FOUND, not
  written twice: an existing proposal to supersede that predecessor whose words
  are exactly the approved words (baseline v3 writes one) is the one
  established; only when none exists is one proposed. Then the owner's
  `establish-replacement` makes it standing: the predecessor becomes history and
  stops being delivered, and the successor takes over its placement.
- A NEW rule is written and established.
- Then each is placed on the whole Brain at the approved delivery level
  (Governance Condensation), and the other material the decisions name
  (the Discipline, the Workflow) is placed at its level.

WHAT IT REFUSES. A predecessor that is not standing now (already ended or
replaced) is refused rather than guessed at; so is a second proposal with the
approved words, which would leave two candidates for one successor. Words are
compared exactly: the authoritative text is never rewritten here.

The default is a dry run that changes nothing and says what it would do. Writing
needs --apply and the owner's Participant. Everything goes through the server's
own owner doors, so every act is checked and recorded as every other act is.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
DECISIONS = ROOT / "docs" / "cutover" / "governance-2026-10-29.json"


class Server:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"X-Mentis-Client": "1",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            return {"error": exc.read().decode("utf-8", "replace")[:500]}


def text_of(entry):
    return ((entry or {}).get("body") or {}).get("text")


def plan_item(srv, item):
    """What establishing one item needs here. Reads only."""
    pred = item.get("replaces")
    if not pred:
        same = [r for r in srv.call("GET", "/api/governed?kind=rule&limit=200&q=" +
                                    urllib.parse.quote(item["text"][:60]))
                .get("groups", {}).get("standing", [])
                if text_of(srv.call("GET", f"/api/entries/{r['entry']}")) == item["text"]]
        if same:
            return {"how": "already-standing", "entry": same[0]["entry"]}
        return {"how": "write-new"}
    got = srv.call("GET", f"/api/entries/{pred}")
    if got.get("missing") or got.get("error"):
        return {"how": "refused", "why": f"{pred} is not in this Brain"}
    if not got.get("stands"):
        succ = got.get("superseded_by") or []
        succ = [succ] if isinstance(succ, str) else list(succ)
        done = [e for e in succ
                if text_of(srv.call("GET", f"/api/entries/{e}")) == item["text"]]
        if done:
            return {"how": "already-established", "entry": done[0]}
        return {"how": "refused", "why": f"{pred} does not stand now "
                                         f"(superseded by {succ}); decide afresh"}
    proposals = [r["entry"] for r in
                 (((got.get("proposed") or {}).get("successors") or {}).get("items") or [])]
    exact = [e for e in proposals
             if text_of(srv.call("GET", f"/api/entries/{e}")) == item["text"]]
    if len(exact) > 1:
        return {"how": "refused", "why": f"{len(exact)} proposals carry the approved "
                                         f"words for {pred}: {exact}"}
    return {"how": "establish-proposal", "predecessor": pred,
            "proposal": exact[0] if exact else None,
            "other_proposals": [e for e in proposals if e not in exact]}


def apply_item(srv, item, plan, owner):
    because = f"owner-approved governance ({item['title']}), DAY-TO-DAY transition"
    if plan["how"] == "write-new":
        got = srv.call("POST", "/api/entries", {"kind": "rule", "body": {"text": item["text"]},
                                                "establish": True, "attributed_to": owner,
                                                "because": because})
        if got.get("error"):
            return {"error": got["error"]}
        entry = got.get("entry") or got.get("id")
    elif plan["how"] == "establish-proposal":
        proposal = plan["proposal"]
        if proposal is None:
            got = srv.call("POST", f"/api/entries/{plan['predecessor']}/propose-supersession",
                           {"attributed_to": owner, "because": because,
                            "body": {"text": item["text"]}})
            if got.get("error"):
                return {"error": got["error"]}
            proposal = got.get("proposal") or got.get("replacement")
        got = srv.call("POST", f"/api/entries/{plan['predecessor']}/establish-replacement",
                       {"attributed_to": owner, "because": because, "replacement": proposal})
        if got.get("error"):
            return {"error": got["error"], "proposal": proposal}
        entry = proposal
    else:
        entry = plan.get("entry")
    placed = place(srv, entry, item["placement"], owner, because)
    return {"entry": entry, "placement": placed}


def place(srv, entry, plc, owner, because):
    body = {"attributed_to": owner, "because": because, "whole_brain": True}
    if plc.get("delivery") and plc["delivery"] != "full":
        body["delivery"] = plc["delivery"]
        if plc.get("when"):
            body["when"] = plc["when"]
    got = srv.call("POST", f"/api/entries/{entry}/place", body)
    return got.get("placement") or got


def material_named(srv, what):
    """The standing entry a `delivery_of_other_material` row means, by its name."""
    name = what.split(":", 1)[1].split("(")[0].strip()
    kind = "discipline" if what.lower().startswith("discipline") else "workflow"
    rows = srv.call("GET", f"/api/governed?kind={kind}&limit=100").get("groups", {}).get("standing", [])
    for r in rows:
        e = srv.call("GET", f"/api/entries/{r['entry']}")
        if (e.get("body") or {}).get("name") == name:
            return r["entry"]
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--server", required=True)
    ap.add_argument("--decisions", default=str(DECISIONS))
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--attributed-to", help="the owner's Participant; required to apply")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.apply and not a.attributed_to:
        ap.error("--apply needs --attributed-to with the owner's Participant")
    srv = Server(a.server)
    spec = json.loads(pathlib.Path(a.decisions).read_text(encoding="utf-8"))
    report = {"server": a.server, "applied": a.apply, "items": [], "other_material": []}
    plans = [(item, plan_item(srv, item)) for item in spec["items"]]
    refused = [(i["key"], p["why"]) for i, p in plans if p["how"] == "refused"]
    if refused:
        report["refused"] = refused
    for item, plan in plans:
        row = {"key": item["key"], "title": item["title"], **plan,
               "delivery": item["placement"].get("delivery")}
        if a.apply and not refused:
            row["result"] = apply_item(srv, item, plan, a.attributed_to)
        report["items"].append(row)
    for m in spec.get("delivery_of_other_material") or ():
        entry = material_named(srv, m["what"])
        row = {"what": m["what"], "entry": entry, "delivery": m["delivery"]}
        if a.apply and not refused and entry:
            row["placement"] = place(srv, entry, m, a.attributed_to,
                                     "owner-approved delivery level, DAY-TO-DAY transition")
        report["other_material"].append(row)
    if a.json:
        print(json.dumps(report, indent=1))
    else:
        print(f"{'APPLIED' if a.apply and not refused else 'DRY RUN'} against {a.server}")
        for r in report["items"]:
            print(f"- {r['title']}: {r['how']}"
                  + (f" (proposal {r.get('proposal')})" if r.get("proposal") else "")
                  + (f" -> {r['result']}" if r.get("result") else "")
                  + (f" REFUSED: {r['why']}" if r.get("why") else ""))
        for r in report["other_material"]:
            print(f"- {r['what']}: {r['entry']} at {r['delivery']}"
                  + (f" -> {r.get('placement')}" if r.get("placement") else ""))
        if refused:
            print("Nothing was written: resolve the refusals first.")
    return 1 if refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
