"""Recorded Work results, then bounded request-time availability.

``structural`` is SQLite-only and shared by full and maintained ReadModel reads.
``overview`` / ``detail`` select copies; ``enrich`` must run OUTSIDE every
answers_of cache. None of these readers grants reach or chooses a primary.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from types import SimpleNamespace

ADMISSION = re.compile(r"^adm-[0-9a-f]{12}$")
REFERENCE = re.compile(r"^(?:adm|ent|opr)-[0-9a-f]{12}$")
RETURNS = {"result-returned", "result-recovered"}
UNVERIFIED = "Referenced here; not verified as produced by this work."


def structural(ctx, root):
    """Complete groups, exact update Turns and dependencies, without blob I/O.

    Attached follow-ups are edges, not timestamps: their earlier results keep
    their original order. Awaiting another Work never makes it a descendant.
    """
    cv, corpus = ctx.cv, ctx.cv.corpus
    acts, requests, frontier = {}, {root["id"]}, [root["id"]]
    deps = {root["id"], root.get("turn")}
    while frontier:
        request = frontier.pop()
        rows = ctx.descendants(request)
        for a in rows:
            acts[a["id"]] = a
            deps.update((a["id"], a.get("turn"), a.get("execution")))
            if a["act"] == "expectation-recorded":
                requests.add(a["id"])
            if a["act"] == "follow-up-attached":
                attached = (a.get("detail") or {}).get("request")
                if attached and attached not in requests:
                    req = cv._act(attached)
                    if req and req["act"] == "expectation-recorded":
                        requests.add(attached)
                        acts[attached] = req
                        deps.update((attached, req.get("turn")))
                        frontier.append(attached)
        # Historical handovers also record the explicit carried_under mapping
        # on the attached request's met act. It is an edge only when it names
        # this Work, never merely because the requests share a Conversation.
        for work in {request} | {a["id"] for a in rows
                                 if a["act"] == "expectation-recorded"}:
            for a in corpus.operational(about=work):
                if ((a.get("detail") or {}).get("carried_under") != work
                        or a["act"] != "expectation-met"):
                    continue
                deps.add(a["id"])
                attached = a.get("caused_by")
                req = cv._act(attached)
                if (attached not in requests and req
                        and req["act"] == "expectation-recorded"):
                    requests.add(attached)
                    acts[attached] = req
                    deps.update((attached, req.get("turn")))
                    frontier.append(attached)
    order = ctx.order.prime(list(acts.values()))
    rows = sorted(acts.values(), key=order.key)
    groups, updates, sources = {}, {}, {}

    def owner(a):
        seen = set()
        while a and a["id"] not in seen:
            seen.add(a["id"])
            if a["id"] in requests:
                return a["id"]
            a = acts.get(a.get("caused_by")) or cv._act(a.get("caused_by"))
        return None

    def source(turn):
        if turn not in sources:
            from mentis.conversation.versions import presented
            deps.add(turn)
            got = corpus.read([turn]) if turn else []
            entry = presented(corpus, got[0]) if got else None
            live = bool(entry and not entry.get("deleted")
                        and not entry.get("body", {}).get("erased"))
            sources[turn] = (ctx.link(turn) if live else None, entry)
        return sources[turn]

    def group(a, turn):
        gid = turn or a["id"]
        if gid not in groups:
            link, entry = source(turn)
            seq = (corpus._store._rows("SELECT seq FROM entry WHERE id = ?",
                                       (turn,)) if turn else [])
            groups[gid] = {"id": gid, "source": link,
                           "unplaced": turn is None, "items": [],
                           "_seq": seq[0][0] if seq else order.key(a)[0]}
        return groups[gid]

    def add(g, ref, basis, *, verified=False, src=None, kind="artifact"):
        deps.add(ref)
        item = next((i for i in g["items"] if i["ref"] == ref), None)
        if item is None:
            item = {"ref": ref, "kind": kind, "source": src,
                    "actionable": verified, "basis": [],
                    "association": "verified" if verified else "unverified",
                    "reason": None if verified else UNVERIFIED}
            g["items"].append(item)
        if basis not in item["basis"]:
            item["basis"].append(basis)
        if verified:
            item.update(actionable=True, association="verified", reason=None,
                        source=src)

    # A raw array is complete; resolve.returned is only an eight-item summary.
    for a in rows:
        if a["act"] not in RETURNS | {"outcome-claimed"}:
            continue
        work = owner(a)
        if work is None:
            continue
        d = a.get("detail") or {}
        turn = d.get("reply_turn") or a.get("turn")
        if turn and work == root["id"]:
            link, _ = source(turn)
            if link:
                updates[turn] = link
        if a["act"] not in RETURNS:
            continue
        g = group(a, turn)
        for ref in d.get("returned_artifacts") or ():
            if not isinstance(ref, str) or not ADMISSION.fullmatch(ref):
                continue
            verified = False
            for link in corpus.links(relation="produced", to=ref):
                deps.update((link["id"], link["link"]["from"]))
                made = acts.get(link["link"]["from"])
                if (made and made["act"] == "artifact-returned" and a.get("execution")
                        and made.get("execution") == a.get("execution")
                        and owner(made) == work):
                    verified = True
            add(g, ref, {"kind": "returned-by-run", "act": a["id"],
                         "work": work, "turn": turn,
                         "observation": a["act"]}, verified=verified,
                src=g["source"] if verified else None)

    # Only actual parts of associated result/claim Turns, with submission
    # provenance. Merely echoing an Admission in prose establishes nothing.
    for a in rows:
        if a["act"] not in RETURNS | {"outcome-claimed"}:
            continue
        turn = (a.get("detail") or {}).get("reply_turn") or a.get("turn")
        link, entry = source(turn)
        if not link:
            continue
        for part in (entry.get("body") or {}).get("parts") or ():
            ref = part.get("ref") if isinstance(part, dict) else None
            if (not isinstance(part, dict) or part.get("type") not in ("file", "image")
                    or not isinstance(ref, str) or not ADMISSION.fullmatch(ref)):
                continue
            deps.add(ref)
            for produced in corpus.links(relation="produced", to=ref):
                made = cv._act(produced["link"]["from"])
                deps.update((produced["id"], produced["link"]["from"]))
                if (made and made["act"] == "artifact-submitted"
                        and made.get("turn") == turn):
                    add(group(a, turn), ref,
                        {"kind": "attached-to-turn", "act": made["id"],
                         "work": owner(a), "turn": turn},
                        verified=True, src=link)

    # Claims are retained as facts, never a shortcut to an owner's broad
    # artifact URL. Merge their basis into the actual producer's group.
    for a in rows:
        if a["act"] != "outcome-claimed":
            continue
        d = a.get("detail") or {}
        turn = d.get("reply_turn") or a.get("turn")
        for ref in d.get("results") or ():
            if not isinstance(ref, str) or not REFERENCE.fullmatch(ref):
                continue
            deps.add(ref)
            basis = {"kind": "authored-result-ref", "act": a["id"],
                     "work": owner(a), "turn": turn}
            proven = [g for g in groups.values() if any(
                i["ref"] == ref and i["actionable"] for i in g["items"])]
            if proven:
                for g in proven:
                    add(g, ref, basis)
            else:
                # Do not resolve foreign Admissions for names or origins.
                kind = "artifact" if ADMISSION.fullmatch(ref) else "record"
                add(group(a, turn), ref, basis, kind=kind)
    result = sorted(groups.values(), key=lambda g: (-g["_seq"], g["id"]))
    for g in result:
        g.pop("_seq")
    return {"groups": result, "update_turns": list(updates.values()),
            "deps": sorted(d for d in deps if d)}


def _fingerprint(index):
    return hashlib.sha256(json.dumps(index, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def _cursor(binding, kind, after):
    raw = json.dumps([binding, kind, after], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class RefreshResults(ValueError):
    """A foreign/stale/invalid paging cursor: route returns an explicit 409."""


def _after(token, binding, kind, ids):
    if not token:
        return 0
    try:
        if len(token) > 4096:
            raise ValueError("too long")
        got, typ, after = json.loads(base64.urlsafe_b64decode(
            token + "=" * (-len(token) % 4)))
        if got == binding and typ == kind:
            return ids.index(after) + 1
    except (ValueError, TypeError, UnicodeError):
        pass
    raise RefreshResults("Results changed or this cursor belongs elsewhere; refresh results.")


def page(index, *, work, brain, results_before=None, result_group=None,
         items_after=None, compact=False):
    """Bounded structural page. Cursors bind instance, Work and full order.

    Structural fingerprint is deliberately independent of live blob state.
    It invalidates pages when membership/order/provenance changes, rather
    than silently skipping entries. There is no retained snapshot service.
    """
    if items_after and not result_group or result_group and results_before:
        raise RefreshResults("Use either a group cursor or an item cursor; refresh results.")
    groups = index["groups"]
    binding = [work, brain, _fingerprint(index)]
    if not brain and (results_before or items_after):
        raise RefreshResults("Brain instance is unavailable; refresh results.")
    group_cap, item_cap = (8, 4) if compact else (20, 20)
    start = _after(results_before, binding, "groups", [g["id"] for g in groups])
    chosen = groups[start:start + group_cap]
    if result_group:
        chosen = [g for g in groups if g["id"] == result_group]
        if not chosen:
            raise RefreshResults("Result group is absent; refresh results.")
    shown = []
    for g in chosen:
        offset = _after(items_after, binding, g["id"],
                        [i["ref"] for i in g["items"]]) if result_group else 0
        items = copy.deepcopy(g["items"][offset:offset + item_cap])
        remaining = len(g["items"]) - offset - len(items)
        shown.append({**{k: copy.deepcopy(v) for k, v in g.items() if k != "items"},
                      "items": items,
                      "total_items": len(g["items"]), "omitted_items": remaining,
                      "next_items_after": (_cursor(binding, g["id"], items[-1]["ref"])
                                           if remaining and brain else None)})
    more = not result_group and start + len(chosen) < len(groups)
    omitted = [g for g in groups if g not in chosen]
    return {"groups": shown, "total_groups": len(groups),
            "omitted_groups": len(omitted),
            "omitted_group_items": sum(len(g["items"]) for g in omitted),
            "next_results_before": (_cursor(binding, "groups", chosen[-1]["id"])
                                    if more and chosen and brain else None)}


def overview(cv, answer):
    """Owner HTTP enrichment AFTER wo.overview and OUTSIDE answers_of.

    wo.overview has already applied the ordinary list limit. Never pass the
    complete WorkItems map here, and never cache the returned live answer.
    """
    from mentis.fluid.inspect import brain_key
    out = copy.deepcopy(answer)
    memo = {}
    for item in out["items"]:
        index = item.pop("_result_index", None)
        if index is not None:
            item["result_summary"] = enrich(cv, page(
                index, work=item["expectation"], brain=brain_key(cv.corpus),
                compact=True), memo=memo)
    return out


def detail(cv, answer, *, results_before=None, result_group=None, items_after=None):
    """Owner HTTP detail binding, after wo.detail; no changes to old fields."""
    if answer is None:
        return None
    from mentis.fluid.inspect import brain_key
    out = copy.deepcopy(answer)
    index = out.pop("_result_index")
    out["result_groups"] = enrich(cv, page(
        index, work=out["expectation"], brain=brain_key(cv.corpus),
        results_before=results_before, result_group=result_group,
        items_after=items_after))
    return out


def enrich(cv, selected, *, memo=None):
    """Resolve only selected verified Admissions; copies in, copies out.

    Existing readers own integrity semantics, byte serving and treatment.
    A failed read is unreadable with its reason, never an empty result list.
    """
    from mentis import artifacts
    from mentis.fluid.inspect import WHY
    out = copy.deepcopy(selected)
    memo = {} if memo is None else memo
    from mentis.fluid.inspect import _Resolver
    resolver = _Resolver(SimpleNamespace(cv=cv, corpus=cv.corpus))
    for group in out["groups"]:
        for item in group["items"]:
            if item["kind"] != "artifact":
                inspection = resolver.of(item["ref"])
                available = bool(inspection.get("available") and inspection.get("opens"))
                item.update(inspection=inspection, available=available,
                            actionable=available,
                            reason=inspection.get("why"),
                            association="referenced")
                continue
            if not item["actionable"]:
                continue
            ref = item["ref"]
            if ref not in memo:
                try:
                    memo[ref] = artifacts.public(artifacts.describe(
                        cv.corpus, ref, verify="cached"))
                except Exception as exc:  # an unavailable read remains visible
                    memo[ref] = {"ref": ref, "state": "unreadable",
                                 "reason": f"{type(exc).__name__}: {exc}"}
            descriptor = copy.deepcopy(memo[ref])
            state = descriptor["state"]
            available = state == "held"
            if not available:
                descriptor.pop("url", None)
            item.update(artifact=descriptor, available=available,
                        reason=(None if available else descriptor.get("reason")
                                or WHY.get(state) or f"This result is {state}."),
                        actionable=available)
    out["availability_checked_at"] = datetime.now(timezone.utc).isoformat()
    return out
