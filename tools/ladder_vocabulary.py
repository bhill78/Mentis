"""Rehearse vocabulary and optional proposal migration on an explicit server.

Defaults to dry-run. The HTTP door keeps this tool away from a live Brain's
files and lets the owner review the exact append-only definition changes.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def plan(corpus):
    """Carry existing properties forward whole; change only the approved delta."""
    from mentis.spine import seed
    wanted = {k["kind"]: k for k in seed.KINDS if k["kind"] in
              ("solution", "hypothesis", "lesson", "finding", "outcome", "problem",
               "rule", "decision")}
    changes = []
    for name, template in wanted.items():
        current = corpus.current_definition(name)
        before = current["body"] if current else None
        after = dict(before or template)
        fields = list(after.get("fields") or [])
        for field in template["fields"]:
            if field not in fields:
                fields.append(field)
        after["fields"] = fields
        # Only the approved delta, per Kind; nothing else is restated. The four
        # concluded Kinds gain `requires_basis` (owner decision 1).
        properties = {"hypothesis": ("standing_apt", "expects_falsifier", "requires_basis"),
                      "problem": ("standing_apt",), "outcome": ("standing_apt",),
                      "solution": ("requires_basis",), "finding": ("requires_basis",),
                      "lesson": ("requires_basis",)}
        for prop in properties.get(name, ()):
            if prop in template:
                after[prop] = template[prop]
        if before != after:
            changes.append({"name": name, "family": "kind", "before": before, "after": after})
    # The relations the ladder writes that an older Brain may lack: an
    # outcome's `in-context`, a decline, a withdrawal.
    for name in ("in-context", "declines", "withdraws"):
        relation = next(r for r in seed.RELATIONS if r["relation"] == name)
        current = corpus.current_definition(name)
        if current is None:
            changes.append({"name": name, "family": "relation", "before": None, "after": relation})
        elif "relation" not in current["body"]:
            raise ValueError(f"{name} is defined as a Kind; vocabulary repair needs an explicit decision")
    return changes


def apply(corpus, changes, *, by):
    with corpus.atomic():
        for change in changes:
            props = dict(change["after"])
            if change["family"] == "kind":
                props.pop("kind", None)
                fields = props.pop("fields")
                corpus.define_kind(change["name"], fields=fields, properties=props, attributed_to=by)
            else:
                props.pop("relation", None)
                inverse = props.pop("inverse")
                props.pop("substrate_role", None)
                corpus.define_relation(change["name"], inverse=inverse, properties=props, attributed_to=by)
    return len(changes)


def migration_candidates(cv):
    from mentis.conversation.register import kind_definitions
    from mentis.conversation.ladder_writes import requests
    from mentis.conversation.versions import inert_refusal
    corpus = cv._c
    return [e["id"] for kind, d in kind_definitions(corpus).items()
            if d.get("standing_apt") is True and d.get("knowing") in ("that", "how")
            for e in corpus.entries_of_kind(kind)
            if not corpus.stands(e["id"])["stands"]
            and not corpus.stands(e["id"])["superseded_by"]
            and not requests(corpus, e["id"])
            and not inert_refusal(corpus, e["id"])]


def proposer(cv, eid):
    """Who proposed this candidate, read from the record (see `migrate`)."""
    from mentis.conversation.ladder import _recording_act
    corpus = cv._c
    act = _recording_act(corpus, eid)
    if act and act.get("actor"):
        return act["actor"]
    relation = corpus.proposal_relation("supersedes")
    links = corpus.links(relation=relation, frm=eid) if relation else []
    if links:
        return min(links, key=lambda x: x["recorded_at"]).get("attributed_to")
    got = corpus.read([eid])
    return got[0].get("attributed_to") if got else None


def migrate(cv, *, by, conversation, dry_run=True):
    """Owner decision 5: existing unestablished, non-superseded `standing_apt`
    candidates become Adoption requested. An old `propose_revision` candidate
    carries its `proposes-to-supersede` predecessors into the request's
    `replaces` (`ladder_writes.request`), so adopting it supersedes them. A
    candidate the request refuses is skipped and reported; it does not abort
    the others.

    THE REQUEST IS THE PROPOSER'S. Whoever proposed the candidate -- the
    actor of the act that proposed it, else whoever wrote its
    `proposes-to-supersede`, else whoever wrote it -- is who asked; the
    migration performs the act and is recorded beside it as `migrated_by`."""
    from mentis.conversation.ladder_writes import proposed_predecessors, request
    candidates = migration_candidates(cv)
    corpus = cv._c
    planned = []
    for eid in candidates:
        ent = corpus.read([eid])
        k = (ent[0].get("definition") or {}).get("name") if ent else None
        body = (ent[0].get("body") or {}) if ent else {}
        text = body.get("text", "")
        who = proposer(cv, eid)
        planned.append({
            "entry": eid,
            "kind": k,
            "text": text[:80] if text else "",
            "replaces": proposed_predecessors(corpus, eid),
            "proposer": who,
            "proposer_alias": cv.alias(who) if who else None,
        })
    requested, skipped = [], []
    if not dry_run:
        for p in planned:
            eid = p["entry"]
            try:
                got = request(cv, entry=eid, by=by, requested_by=p["proposer"],
                              because="migrated existing proposal to explicit adoption request",
                              context={"conversation": conversation})
                requested.append({
                    "entry": eid,
                    "kind": p["kind"],
                    "request": got.get("request"),
                    "ask": got.get("ask"),
                    "requested_by": p["proposer"],
                    "requested_by_alias": p["proposer_alias"],
                    "migrated_by": by,
                })
            except ValueError as exc:
                skipped.append({"entry": eid, "why": str(exc)})
    return {"enabled": True, "entries": candidates, "planned": planned,
            "requested": requested, "skipped": skipped, "dry_run": dry_run}


def format_report(result: dict, *, server: str | None = None) -> str:
    """Format vocabulary plan/apply result as a readable report for owner review."""
    if not isinstance(result, dict):
        return str(result)
    if result.get("error"):
        return f"ERROR: {result['error']}"

    lines = []
    dry_run = result.get("dry_run", True)
    mode = "DRY RUN (no changes written)" if dry_run else "APPLIED (changes committed)"
    lines.append(f"=== Mentis Ladder Vocabulary Report ({mode}) ===")
    if server:
        lines.append(f"Target Server: {server}")
    lines.append("")

    changes = result.get("changes") or []
    written = result.get("written", 0)
    lines.append(f"## Definition Changes ({len(changes)} planned, {written} written)")
    if not changes:
        lines.append("  No pending vocabulary definition changes.")
    else:
        for idx, change in enumerate(changes, 1):
            name = change.get("name")
            family = change.get("family", "definition")
            before = change.get("before")
            after = change.get("after") or {}
            status = "NEW" if before is None else "MODIFIED"
            lines.append(f"{idx}. {family.capitalize()}: {name} [{status}]")
            if before is None:
                if family == "kind":
                    lines.append(f"   Fields: {after.get('fields', [])}")
                    props = {k: v for k, v in after.items() if k not in ("kind", "fields", "meaning")}
                    if props:
                        lines.append(f"   Properties: {props}")
                else:
                    lines.append(f"   Inverse: {after.get('inverse')}")
                    lines.append(f"   Directed: {after.get('directed')}")
            else:
                if family == "kind":
                    b_fields = before.get("fields", [])
                    a_fields = after.get("fields", [])
                    if b_fields != a_fields:
                        added_f = [f for f in a_fields if f not in b_fields]
                        lines.append(f"   Fields added: {added_f} (now: {a_fields})")
                    b_props = {k: v for k, v in before.items() if k not in ("fields", "meaning", "kind")}
                    a_props = {k: v for k, v in after.items() if k not in ("fields", "meaning", "kind")}
                    prop_diffs = []
                    for k in sorted(set(b_props) | set(a_props)):
                        if b_props.get(k) != a_props.get(k):
                            prop_diffs.append(f"{k}: {b_props.get(k)} -> {a_props.get(k)}")
                    if prop_diffs:
                        lines.append(f"   Properties changed: {', '.join(prop_diffs)}")
                else:
                    lines.append("   Updated relation definition.")

    migration = result.get("migration")
    if migration:
        lines.append("")
        m_dry = migration.get("dry_run", True)
        m_mode = "Planned (dry run)" if m_dry else "Migrated (adoption requests opened)"
        planned = migration.get("planned") or []
        requested = migration.get("requested") or []
        skipped = migration.get("skipped") or []

        lines.append(f"## Candidate Proposal Migration ({len(planned)} candidates, {m_mode})")
        if requested:
            for idx, r in enumerate(requested, 1):
                eid = r.get("entry")
                kind = r.get("kind") or "entry"
                req = r.get("request")
                ask = r.get("ask")
                proposer = r.get("requested_by")
                alias = r.get("requested_by_alias")
                who = f"{proposer} ({alias})" if alias else proposer
                lines.append(f"{idx}. {eid} ({kind})")
                lines.append(f"   Original proposer: {who}")
                lines.append(f"   Adoption request: {req} (ask: {ask})")
        elif planned:
            for idx, p in enumerate(planned, 1):
                eid = p.get("entry")
                kind = p.get("kind") or "entry"
                replaces = p.get("replaces") or []
                proposer = p.get("proposer")
                alias = p.get("proposer_alias")
                who = f"{proposer} ({alias})" if alias else proposer
                rep_str = f"replaces: {', '.join(replaces)}" if replaces else "no predecessor"
                text = p.get("text") or ""
                summary = f" - \"{text[:50]}...\"" if text else ""
                lines.append(f"{idx}. {eid} ({kind}){summary}")
                lines.append(f"   Proposer: {who}")
                lines.append(f"   Predecessors: {rep_str}")

        if skipped:
            lines.append("")
            lines.append(f"## Skipped Candidates ({len(skipped)})")
            for idx, s in enumerate(skipped, 1):
                lines.append(f"{idx}. {s.get('entry')}: {s.get('why')}")

    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Changes planned: {len(changes)}")
    lines.append(f"- Changes written: {written}")
    if migration:
        lines.append(f"- Candidates: {len(migration.get('planned', []))}")
        lines.append(f"- Candidates migrated: {len(migration.get('requested', []))}")
        lines.append(f"- Candidates skipped: {len(migration.get('skipped', []))}")
    return "\n".join(lines)


def server_refusal(server, *, day_to_day=False):
    try:
        url = urllib.parse.urlparse(server)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            return "server must be an explicit HTTP(S) origin"
        if url.path not in ("", "/") or url.query or url.fragment:
            return "server must be an origin without path, query or fragment"
        if url.port == 8760 and not day_to_day:
            return "port 8760 is DAY-TO-DAY; refused without --day-to-day"
    except ValueError as exc:
        return str(exc)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    parser.add_argument("--day-to-day", action="store_true")
    parser.add_argument("--migrate-proposed", action="store_true")
    parser.add_argument("--conversation")
    parser.add_argument("--attributed-to", help="owner Participant reference; required to apply")
    parser.add_argument("--json", action="store_true", help="output raw JSON instead of human-readable report")
    args = parser.parse_args(argv)
    refusal = server_refusal(args.server, day_to_day=args.day_to_day)
    if refusal:
        parser.error(refusal)
    if args.apply and not args.attributed_to:
        parser.error("--apply requires --attributed-to with the owner's Participant reference")
    payload = json.dumps({"attributed_to": args.attributed_to, "apply": args.apply, "migrate_proposed": args.migrate_proposed,
                          "conversation": args.conversation}).encode()
    req = urllib.request.Request(args.server.rstrip("/") + "/api/ladder/vocabulary",
                                 data=payload, headers={"Content-Type": "application/json",
                                                        # every JSON route asks for it (mentis.web CLIENT_HEADER)
                                                        "X-Mentis-Client": "1"})
    # A redirect could change the target after its port was checked.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **kw):
            raise ValueError("vocabulary endpoint redirects are refused")
    with urllib.request.build_opener(NoRedirect).open(req, timeout=30) as response:
        result = json.load(response)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_report(result, server=args.server))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
