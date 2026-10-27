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
    planned = [{"entry": eid, "replaces": proposed_predecessors(cv._c, eid),
                "proposer": proposer(cv, eid)} for eid in candidates]
    requested, skipped = [], []
    if not dry_run:
        for eid in candidates:
            try:
                got = request(cv, entry=eid, by=by, requested_by=proposer(cv, eid),
                              because="migrated existing proposal to explicit adoption request",
                              context={"conversation": conversation})
                requested.append({"entry": eid, "request": got.get("request"),
                                  "ask": got.get("ask"), "requested_by": proposer(cv, eid),
                                  "migrated_by": by})
            except ValueError as exc:
                skipped.append({"entry": eid, "why": str(exc)})
    return {"enabled": True, "entries": candidates, "planned": planned,
            "requested": requested, "skipped": skipped, "dry_run": dry_run}


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
    print(json.dumps(result, indent=2))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
