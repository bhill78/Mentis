"""Prepare, bind, reconcile and freeze after ordinary Composer/Work execution.

Manifests describe inputs. Existing grants alone decide artifact reach.
"""
from __future__ import annotations

import json

from mentis import artifacts
from mentis.conversation import anchors
from mentis.conversation import GOVERNING_PREFIXES, GOVERNING_SCOPES, WHOLE_BRAIN_SCOPE
from mentis.conversation.versions import Refused
from mentis.fluid.inspect import brain_key

from . import _path
from . import perspectives as P
from . import perspectives_evidence as E


def _package(st, mid, kind, **values):
    return {"format": P.FORMAT, "version": 1, "kind": kind,
            "brain": brain_key(st.corpus), "magnet": mid, **values}


# ---------------------------------------------------------------------------
# THE GROUNDED ANSWER MENTIS WRITES ITSELF, from the collected rows and
# nothing else (plan adm-43ecee5872e9 §3 Part F; amendment adm-c38044ee5157 §3;
# owner correction ent-d85254fe5e1b).
#
# This is NOT a second synthesis engine. It is the same mechanism this module
# already has -- a frozen immutable package with its manifest, its originals,
# its support and its provenance, recorded as the Perspective's `answered`
# event, so the client's existing current/superseded answer history renders it
# and a later answer SUPERSEDES by appending rather than overwriting. What it
# adds is the one thing the dispatched path cannot give: an answer that exists
# without an agent run, which is what an evolving summary has to be, because
# nothing in Mentis may wake up to dispatch one (AGENTS.md).
#
# IT IS GROUNDED STRUCTURALLY, not by policy. `_collected` is the only input
# reader here, it reads one verified immutable batch of THIS Magnet, and no
# argument, body field, authorization or grant can point it anywhere else.
# `scope.provenance(..., synthesis=True)` is recorded beside every answer, and
# for a synthesis it is empty and false by construction -- A built three
# independent refusals for that, and nothing here is a fourth.
#: What the answer says about itself, so no reader has to guess who wrote it.
METHOD = "mentis.magnet.synthesis/1"
WRITTEN_BY_MENTIS = (
    "Written by Mentis from this Magnet's collected rows alone. The records it "
    "names are the records it read, quoted as they were captured; nothing "
    "outside this collection was read, and no authorization can widen it. It is "
    "not an agent's interpretation.")
#: Words that carry no subject of their own, so matching a question on them
#: would report every row. The client's own list (`Summary.tsx` COMMON) exists
#: for counting words it shows; this one decides what a question is asking.
COMMON = set((
    "the and that this with have from were was for are not but all any can has had its into than then "
    "they them their there these those which while would should could when what where who whom why how "
    "about above after again against because been before being below between both during each few more "
    "most other over same some such only own too very will just does done here your ours mine theirs "
    "said says say like make made take taken give given well back much many one two three what's "
    "collected collection records record magnet").split())
#: Bounds on what one answer writes down. An answer is a statement, not a dump.
ROWS_NAMED_MOST = 6
SOURCES_NAMED_MOST = 6
EXCERPT_CHARS = 220


def _row_text(row):
    """One collected row's captured words, or "". Reads the row as recorded."""
    value = row.get("value")
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("text"), str):
        return value["text"]
    parts = value.get("parts")
    if not isinstance(parts, list):
        return ""
    return "\n".join(p.get("text", "") for p in parts
                     if isinstance(p, dict) and p.get("type") == "text"
                     and isinstance(p.get("text"), str))


def _excerpt(words, limit=EXCERPT_CHARS):
    one = " ".join(str(words).split())
    return one[:limit] + ("…" if len(one) > limit else "")


def _source_words(one, seen):
    """A captured source in ordinary words, never its recorded id (owner
    ent-1e82a8786c37). Several of a kind are numbered so they stay apart."""
    kind = ((one.get("source") or {}).get("kind") if isinstance(one.get("source"), dict)
            else None) or "source"
    words = {"conversation": "Conversation", "file": "held file", "git": "Git repository",
             "rss-atom": "feed", "web-search": "web search", "web": "web page"}.get(kind, kind)
    seen[words] = seen.get(words, 0) + 1
    return f"{words} {seen[words]}" if seen[words] > 1 else words


def _when(at):
    import datetime
    if not isinstance(at, (int, float)) or isinstance(at, bool):
        return None
    try:
        return datetime.datetime.fromtimestamp(at, datetime.timezone.utc).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _rows_of(page):
    """Every recorded row of the batch, with the source it was captured from."""
    out, seen = [], {}
    for one in page.get("sources") or ():
        if not isinstance(one, dict):
            continue
        words = _source_words(one, seen)
        for row in one.get("results") or ():
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                out.append({"row": row, "key": one.get("key"), "words": words})
    return out


def _terms(question):
    out = []
    for raw in str(question).lower().replace("’", "'").split():
        word = "".join(c for c in raw if c.isalnum() or c in "'-")
        if len(word) >= 4 and word not in COMMON and not word[0].isdigit() and word not in out:
            out.append(word)
    return out[:8]


def _named(terms):
    if len(terms) == 1:
        return f"“{terms[0]}”"
    return ", ".join(f"“{t}”" for t in terms[:-1]) + f" and “{terms[-1]}”"


def _state_of(rows, new_ids, activation, page):
    """THE EVOLVING SUMMARY: what this Magnet has gathered, said once.

    Every line is a statement about the rows this answer read, and every line
    names the rows it was written from, so the citation is the statement's own
    and not a list stapled underneath it.
    """
    lines = []
    kinds = {}
    for got in rows:
        kinds.setdefault(got["words"], []).append(got)
    collected = _when(activation.get("at"))
    lines.append({"text": f"This Magnet has gathered {len(rows)} "
                          f"{'record' if len(rows) == 1 else 'records'} from {len(kinds)} "
                          f"{'source' if len(kinds) == 1 else 'sources'}"
                          + (f", collected {collected}." if collected else "."),
                  "cites": [got["row"]["id"] for got in rows[:ROWS_NAMED_MOST]]})
    if new_ids:
        fresh = [got for got in rows if got["row"]["id"] in set(new_ids)]
        lines.append({"text": f"{len(new_ids)} of them arrived in this collection and were not in "
                              f"the one before it.",
                      "cites": [got["row"]["id"] for got in fresh[:ROWS_NAMED_MOST]]})
        for got in fresh[:ROWS_NAMED_MOST]:
            words = _excerpt(_row_text(got["row"]))
            if words:
                day = _when(got["row"].get("at"))
                lines.append({"text": f"New, from the {got['words']}"
                                      + (f" ({day})" if day else "") + f": “{words}”",
                              "cites": [got["row"]["id"]]})
    for words, got_rows in list(kinds.items())[:SOURCES_NAMED_MOST]:
        # The most recent row THAT RETAINED WORDS, so a source is quoted
        # wherever it can be; a source whose newest row kept no text is still
        # counted, and says that rather than appearing to hold nothing.
        def _at(got):
            at = got["row"].get("at")
            return at if isinstance(at, (int, float)) and not isinstance(at, bool) else 0
        spoken = sorted((g for g in got_rows if _row_text(g["row"]).strip()), key=_at)
        quoted = _excerpt(_row_text(spoken[-1]["row"]), 160) if spoken else ""
        lines.append({"text": f"From the {words}: {len(got_rows)} "
                              f"{'record' if len(got_rows) == 1 else 'records'}"
                              + (f", most recently “{quoted}”" if quoted
                                 else ", none of which retained any words") + ".",
                      "cites": [(spoken[-1] if spoken else sorted(got_rows, key=_at)[-1])["row"]["id"]]})
    days = sorted(d for d in (_when(got["row"].get("at")) for got in rows) if d)
    if days:
        lines.append({"text": f"The material it holds was written on {days[0]}." if days[0] == days[-1]
                      else f"The material it holds was written between {days[0]} and {days[-1]}.",
                      "cites": [rows[0]["row"]["id"]]})
    if page.get("state") and page["state"] != "ok":
        lines.append({"text": f"Not every source reported its whole selected scope, so this is what "
                              f"was collected and not everything that exists (recorded state "
                              f"{page['state']}).", "cites": []})
    return lines


def _about(question, rows):
    """AN OWNER'S QUESTION, ANSWERED FROM THE COLLECTED ROWS.

    It says plainly what it did: which of the collected records bear on the
    question's own words, and what those records say, quoted. Where none of
    them do, it says that instead of writing something that sounds like an
    answer -- which is the one thing #521 §7 forbids.
    """
    terms = _terms(question)
    if not terms:
        return [{"text": "That question names nothing this Magnet's collected records can be "
                         "searched on, so nothing was read to answer it.", "cites": []}]
    scored = []
    for got in rows:
        words = _row_text(got["row"]).lower()
        hits = [t for t in terms if t in words]
        if hits:
            scored.append((len(hits), got, hits))
    scored.sort(key=lambda s: (-s[0], str(s[1]["row"]["id"])))
    if not scored:
        return [{"text": f"None of the {len(rows)} records this Magnet has collected mention "
                         f"{_named(terms)}. Nothing outside this collection was read, so this is "
                         f"what the collection can answer and not an answer from elsewhere.",
                 "cites": []}]
    lines = [{"text": f"{len(scored)} of the {len(rows)} records this Magnet has collected mention "
                      f"{_named(terms)}. Here is what they say.",
              "cites": [got["row"]["id"] for _, got, _ in scored[:ROWS_NAMED_MOST]]}]
    for _, got, hits in scored[:ROWS_NAMED_MOST]:
        day = _when(got["row"].get("at"))
        lines.append({"text": f"From the {got['words']}" + (f" ({day})" if day else "")
                              + f", on {_named(hits)}: “{_excerpt(_row_text(got['row']))}”",
                      "cites": [got["row"]["id"]]})
    if len(scored) > ROWS_NAMED_MOST:
        lines.append({"text": f"{len(scored) - ROWS_NAMED_MOST} further collected records mention "
                              f"the same words and are not quoted here.",
                      "cites": [got["row"]["id"] for _, got, _ in scored[ROWS_NAMED_MOST:]][:ROWS_NAMED_MOST]})
    return lines


def _selections(batch_ref, rows, lines):
    """The exact captured ranges the answer's statements were written from.

    Only rows this answer actually names, and only text parts it can state
    exactly: `E.originals` then validates each range against the retained
    batch, so a citation that does not verify refuses the answer rather than
    being dropped from it.
    """
    wanted, out = {rid for line in lines for rid in line["cites"]}, []
    by_id = {got["row"]["id"]: got for got in rows}
    for rid in sorted(wanted):
        got = by_id.get(rid)
        if not got:
            continue
        row, value = got["row"], got["row"].get("value")
        if not isinstance(value, dict):
            continue
        base = {"batch": batch_ref, "source": got["key"], "item": rid,
                "version": row.get("version"), "stance": "supporting"}
        if row.get("kind") == "file" and row.get("via") == "held-source":
            if type(value.get("offset")) is int and type(value.get("end")) is int:
                out.append({**base, "start": value["offset"], "end": value["end"]})
            continue
        parts = value.get("parts")
        if not isinstance(parts, list):
            if isinstance(value.get("text"), str):
                out.append({**base, "part": 0, "start": 0, "end": len(value["text"])})
            continue
        for i, part in enumerate(parts):
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                out.append({**base, "part": i, "start": 0, "end": len(part["text"])})
    return out


def _collected(st, mid):
    """THE ONE INPUT: this Magnet's own latest verified immutable batch.

    No parameter chooses it, because a synthesis does not get to choose its
    ground. `collection.read` reads recorded Admissions only -- it performs no
    lift, activation or live-source lookup -- and `E.batch` then re-verifies
    the batch's identity, captured definition and operation against the
    activation act that recorded it.
    """
    from . import collection as C
    from mentis.fluid import read as fluid
    try:
        got = C.read(st, mid)
    except C.UnreadableCollection as exc:
        P.refuse("collection-unreadable", f"this Magnet's retained collection cannot be read as "
                 f"the evidence it claims, and no live source was substituted: {exc}")
    except (fluid.NotFound, fluid.BadRequest):
        P.refuse("missing-magnet", "this Magnet has no readable definition")
    if not got.get("activation"):
        P.refuse("nothing-collected", "this Magnet has collected nothing yet, so there is nothing "
                 "to answer from. Collect first; an answer is never written from anything else.")
    return got["activation"], got["page"]


def answer(st, mid, topic, body, by, written_by):
    """Answer this Perspective's question from the collected rows, durably.

    One owner action, one appended answer. The previous answer stays exactly
    where it was recorded -- this supersedes, it never overwrites -- which is
    what makes the evolving summary and an answered question the same thing.
    """
    P.require_grounded()
    activation, page = _collected(st, mid)
    batch_ref = activation["artifact"]["ref"]
    asked = body.get("text")
    fresh = asked is not None and isinstance(asked, str) and bool(asked.strip())
    if asked is not None and not fresh:
        P.refuse("invalid-text", "a question asked here is nonblank text, or is omitted to "
                 "re-answer the saved one")
    previous = P._last(st, mid, topic, "answered")
    before = ((previous or {}).get("data") or {}).get("basis") or {}
    # PART E'S OWN NEW-ITEM COUNT IS THE RE-ANSWER TRIGGER, read here rather
    # than taken from the caller: a re-answer of the same question over a
    # collection that brought nothing new would be a new answer saying the same
    # thing, and the history is append-only. An owner asking something new is
    # always answered -- what is bounded is re-answering, not asking.
    new_ids, new_count = [], None
    if before.get("batch"):
        from . import collection as C
        from mentis.fluid import read as fluid
        try:
            moved = C.new_since(st, mid, since=before["batch"])
            new_ids, new_count = moved["new"], moved["new_count"]
        except (C.UnreadableCollection, fluid.NotFound, fluid.BadRequest):
            new_ids, new_count = [], None
        if not fresh and new_count == 0:
            P.refuse("nothing-new", "this collection holds no record the standing answer did not "
                     "already read, so nothing was re-answered. The answer recorded against this "
                     "question still stands.", batch=batch_ref, new_count=0)
    if fresh:
        got = P._question(st, mid, topic, asked, body.get("reason"), by, written_by)
        question_desc, question_text = got["question"], asked
        question_turn = got["event"]["post"]
    else:
        current = P.state(st, mid, topic, detail=True)
        latest = P._last(st, mid, topic, "question")
        if not current.get("current_question") or not latest:
            P.refuse("question-required", "this Perspective has no saved question to answer")
        question_desc = current["question"]
        question_text = current["current_question"]["text"]
        question_turn = latest["post"]
    # The batch and the question are the whole closure. Reserve the two nodes
    # this answer adds -- its manifest and itself -- so the 32/8 MiB bound the
    # dispatched path enforces is the same bound here.
    closure = E.Closure(st, mid, reserve_refs=2)
    closure.add(batch_ref)
    verified = E.batch(st, mid, closure.nodes[batch_ref], closure.raw[batch_ref])
    closure.add(question_desc["ref"], question_desc)
    rows = _rows_of(verified["page"])
    is_standing = P.standing(st, mid) == topic and not fresh
    lines = (_state_of(rows, new_ids, activation, verified["page"]) if is_standing
             else _about(question_text, rows))
    # NO CITATION IS NO SUPPORT. `E.originals` reads an empty selection list as
    # "every captured range", which is right for a prepared question over a
    # whole batch and wrong here: an answer that names no record must be
    # labelled `unsupported`, never given the whole collection as if it had
    # corroboration it does not claim (contract: zero original support is
    # labelled unsupported, never independent corroboration).
    chosen = _selections(batch_ref, rows, lines)
    originals = E.deduplicate(E.originals({batch_ref: verified}, chosen)) if chosen else []
    words = "\n".join(line["text"] for line in lines)
    manifest = _package(st, mid, "manifest", perspective=topic, synthesis=True, method=METHOD,
        question=question_desc, batches=[closure.nodes[batch_ref]], priors=[], reuse_receipts=[],
        declared_context=[], records=None, definition=None,
        originals=originals, support="supported" if originals else "unsupported",
        omissions=[{"batch": batch_ref, "page_state": verified["page"].get("state"),
                    "sources": [{"key": s.get("key"), "status": s.get("status"),
                                 "reason": s.get("reason"), "kept": s.get("kept")}
                                for s in verified["page"].get("sources") or ()]}],
        edges=closure.edges, direct=[batch_ref, question_desc["ref"]],
        dependencies=list(closure.nodes.values()))
    held_manifest = P.hold(st, mid, manifest, by, name="manifest")
    # WHAT THIS ANSWER WAS ALLOWED TO REACH, AND WHAT IT DID (Part A's
    # published contract, its field names unchanged). A synthesis is
    # `synthesis=True`, for which all of it is empty and false structurally.
    from . import scope
    provenance = scope.provenance(st.cv, mid, turn=question_turn, synthesis=True)
    basis = {"batch": batch_ref, "digest": activation["artifact"]["digest"],
             "collected_at": activation.get("at"), "state": verified["page"].get("state"),
             "rows": len(rows), "new_count": new_count, "new": new_ids[:P.PAGE_MAX],
             "since": before.get("batch")}
    package = _package(st, mid, "answer", perspective=topic, synthesis=True, method=METHOD,
        question=question_desc, question_text=question_text, text=words, lines=lines,
        manifest=held_manifest, originals=originals, support=manifest["support"],
        provenance=provenance, basis=basis, written_by=WRITTEN_BY_MENTIS,
        disclosure=P.DISCLOSURE, dependencies=[held_manifest])
    snap = P.hold(st, mid, package, by, name="answer")
    data = {"text": words, "lines": lines, "answer": snap, "manifest": held_manifest,
            "question": question_desc, "provenance": provenance, "basis": basis,
            "support": manifest["support"], "method": METHOD, "written_by": WRITTEN_BY_MENTIS}
    row = P.event(st, mid, topic, "answered", data, by, snapshot=snap, written_by=written_by)
    return {"perspective": topic, "standing": is_standing, **data, "event": row}


def _question(st, mid, topic, ref):
    rows = st.corpus.operational(act=P.ACT, detail_is={"magnet": mid, "perspective": topic,
        "event": "question"}, detail_names=ref, limit=2)
    if not any(a["detail"]["snapshot"]["ref"] == ref for a in rows):
        P.refuse("wrong-question", "this is not an immutable question revision of this Perspective")
    desc = E.descriptor(st, ref)
    obj = E.native(st, mid, ref, E.bounded_read(st, desc, E.MAX_BYTES), "question")
    if obj.get("perspective") != topic:
        P.refuse("wrong-question", "the question belongs to a different Perspective")
    return desc, obj


def _record_package(st, mid, topic, continuation):
    events, deps, cursor, cost = [], [], None, 0
    # The product follows its own bounded durable-history read. Total bytes
    # are bounded too; no recall window or browser storage reconstructs this.
    while True:
        page = P.history(st, mid, topic, limit=100, cursor=cursor)
        for row in page["events"]:
            cost += len(P.encoded(row))
            if cost > E.MAX_BYTES:
                P.refuse("history-too-large", "this continuation's durable records exceed 8 MiB; "
                         "choose a narrower explicit inquiry or start a fresh inquiry")
            events.append(row)
            if continuation:
                deps.append(row["snapshot"])
                # Event snapshots retain metadata; immutable input packages
                # referenced by prior preparations/answers carry full closure.
                data = row["data"]
                for key in ("manifest", "answer"):
                    if isinstance(data.get(key), dict) and "ref" in data[key]:
                        deps.append(data[key])
        cursor = page["next"]
        if not cursor:
            break
    unique = {d["ref"]: d for d in deps}
    if len(unique) > E.MAX_REFS:
        P.refuse("reference-limit", "this continuation's complete durable history exceeds 32 Admissions; "
                 "choose a narrower explicit inquiry or start fresh")
    return _package(st, mid, "records", perspective=topic, through=page["through"],
                    continuation=continuation, events=events, dependencies=list(unique.values()))


def prepare(st, mid, topic, body, by, written_by):
    P.require_grounded()
    try:
        return _prepare(st, mid, topic, body, by, written_by)
    except Refused as exc:
        if exc.refusal.get("code") == "byte-limit":
            sizes = [E.descriptor(st, r)["size"] for r in E.refs(body.get("batches", []), "batches")]
            P.refuse("byte-limit", f"The selected whole batch sizes are {sizes} bytes. The complete "
                "input package, including its mandatory snapshots, definition and manifest, exceeds the "
                "8 MiB (8388608 byte) limit. Narrow sources, types or dates and Collect a new smaller "
                "batch. Selecting fewer rows cannot shrink a whole batch.", batches=sizes, limit=E.MAX_BYTES)
        raise


def _prepare(st, mid, topic, body, by, written_by):
    q, question = _question(st, mid, topic, body.get("question"))
    batches = E.refs(body.get("batches"), "batches")
    if not batches:
        P.refuse("batch-required", "select at least one retained collection batch")
    priors = E.refs(body.get("priors", []), "priors")
    declared = E.refs(body.get("declared_context", []), "declared_context")
    if type(body.get("continuation", False)) is not bool:
        P.refuse("invalid-continuation", "continuation is true or false")
    # Reserve the manifest node from the outset. Its exact bytes are added
    # before admitting the package; it never escapes the 32/8 MiB bound.
    closure = E.Closure(st, mid, reserve_refs=1)
    captured = {}
    for ref in batches:
        closure.add(ref)
        captured[ref] = E.batch(st, mid, closure.nodes[ref], closure.raw[ref])
    closure.add(q["ref"], q)
    originals = E.originals(captured, body.get("selections"))
    reuse_receipts = []
    for ref in priors:
        closure.add(ref)
        prior = E.native(st, mid, ref, closure.raw[ref], "answer")
        # Reuse is a new qualification, not trust in an older passing receipt.
        prior_topic, intent = prior["perspective"], prior["intent"]
        check = reconcile(st, mid, prior_topic, {"intent": intent, "purpose": "reuse",
                          "execution": prior["execution"]}, by, written_by)
        if check["status"] != "qualified":
            P.refuse("prior-unqualified", "this earlier interpretation is not currently qualified for reuse",
                     ref=ref, reconciliation=check)
        # New reachable context may have been explicitly declared since the
        # immutable answer was frozen. Preserve that current reuse accounting
        # too; the old answer's unchanged dependency list cannot represent it.
        for context in check["declared_context"]:
            closure.add(context, parent=ref)
        closure.add(check["receipt"]["ref"], check["receipt"])
        reuse_receipts.append({"prior": ref, "receipt": check["receipt"]})
        originals.extend(prior.get("originals", []))
    for ref in declared:
        closure.add(ref)
    # Raw current definition, not a normalized projection; old batches also
    # retain their original raw definitions independently in their bytes.
    try:
        path = _path(st.corpus.root, mid)
        size = path.stat().st_size
        if size > E.MAX_BYTES - closure.bytes:
            P.refuse("byte-limit", "the raw definition does not fit the 8 MiB input package")
        with path.open("rb") as stream:
            raw_definition = stream.read(size)
        if len(raw_definition) != size:
            raise OSError("definition changed while read")
        raw_definition.decode("utf-8")
    except (OSError, UnicodeError):
        P.refuse("definition-unreadable", "the Magnet's exact current definition could not be frozen")
    if len(raw_definition) > E.MAX_BYTES - closure.bytes:
        P.refuse("byte-limit", "the raw definition does not fit the 8 MiB input package")
    # The raw bytes are held verbatim; format metadata belongs in the manifest.
    held_definition = artifacts.hold(st.corpus, st.cv, raw_definition, act=artifacts.SUBMITTED,
        actor=by, source=f"magnet-definition:{mid}", door="magnet-perspective-definition",
        claimed_name=f"{mid}-definition.json", claimed_media_type="application/json")
    definition = {"ref": held_definition["admission"], "digest": held_definition["digest"],
                  "size": len(raw_definition), "media_type": "application/json"}
    closure.add(definition["ref"], definition)
    records = P.hold(st, mid, _record_package(st, mid, topic, body.get("continuation", False)),
                     by, name="records")
    closure.add(records["ref"], records)
    originals = E.deduplicate(originals)
    manifest = _package(st, mid, "manifest", perspective=topic, question=q,
        definition=definition, batches=[closure.nodes[r] for r in batches],
        records=records, priors=[closure.nodes[r] for r in priors],
        reuse_receipts=reuse_receipts,
        declared_context=[closure.nodes[r] for r in declared],
        originals=originals, support="supported" if originals else "unsupported",
        omissions=[{"batch": ref, "page_state": obj["page"].get("state"),
                    "sources": [{"key": s["key"], "status": s.get("status"),
                                  "reason": s.get("reason"), "kept": s.get("kept")}
                                 for s in obj["page"]["sources"]]} for ref, obj in captured.items()],
        edges=closure.edges, direct=batches + [q["ref"], definition["ref"], records["ref"]] + priors + declared,
        dependencies=list(closure.nodes.values()))
    manifest_bytes = P.encoded(manifest)
    if closure.bytes + len(manifest_bytes) > E.MAX_BYTES:
        P.refuse("byte-limit", "the complete input package, including its manifest, exceeds 8 MiB "
                 "(8388608 bytes); narrow sources, types or dates and Collect a smaller batch",
                 size=closure.bytes + len(manifest_bytes), limit=E.MAX_BYTES,
                 batches=[closure.nodes[r] for r in batches])
    held_manifest = P.hold(st, mid, manifest, by, name="manifest")
    all_artifacts = list(closure.nodes.values()) + [held_manifest]
    row = P.event(st, mid, topic, "prepared", {"question": q, "manifest": held_manifest,
        "records": records, "artifacts": all_artifacts,
        "closure": {"count": len(all_artifacts), "bytes": closure.bytes + held_manifest["size"]},
        "text": question["text"]}, by, written_by=written_by)
    return _prepared(row, mid, topic)


def _prepared(row, mid, topic):
    d = row["data"]
    return {"intent": row["post"], "magnet": mid, "perspective": topic,
        "brain": row["snapshot_brain"] if "snapshot_brain" in row else None,
        "question": d["question"], "manifest": d["manifest"], "records": d["records"],
        "artifacts": d["artifacts"], "closure": d["closure"], "reach": "work",
        "request_op": "perspective-request:" + row["post"], "text": d["text"],
        "parts": [{"type": "file", "ref": a["ref"], "media_type": a["media_type"],
                   "alt": "Perspective evidence"} for a in d["artifacts"]], "disclosure": P.DISCLOSURE}


def intent(st, mid, topic, identity):
    P._topic(st, mid, topic)
    row = P._last(st, mid, topic, "prepared", post=identity)
    if not row:
        P.refuse("wrong-intent", "this is not a prepared immutable intent of this Perspective")
    # Verify the snapshot instead of trusting mutable definition/config state.
    d = row["snapshot"]
    snap = E.native(st, mid, d["ref"], E.bounded_read(st, E.descriptor(st, d["ref"]), E.MAX_BYTES), "event")
    if snap.get("data") != row["data"] or snap.get("perspective") != topic:
        P.refuse("intent-unreadable", "the durable intent record no longer verifies")
    row["snapshot_brain"] = snap["brain"]
    return row


def binding(st, mid, topic, identity):
    rows = st.corpus.operational(act=P.ACT,
        detail_is={"magnet": mid, "perspective": topic, "event": "bound"},
        detail_names=identity, newest_first=True, limit=2)
    return next((a["detail"]["data"] for a in rows
                 if a["detail"]["data"].get("intent") == identity), None)


def intent_read(st, mid, topic, identity):
    row = intent(st, mid, topic, identity)
    answers = st.corpus.operational(act=P.ACT,
        detail_is={"magnet": mid, "perspective": topic, "event": "answered"},
        detail_names=identity, limit=101)
    return {"brain": brain_key(st.corpus), "magnet": mid, "perspective": topic,
            "grounded_answers": P.GROUNDED_ANSWERS_ENABLED,
            "prepared": _prepared(row, mid, topic), "binding": binding(st, mid, topic, identity),
            "answers": [a["detail"]["data"]["answer"] for a in answers
                        if a["detail"]["data"].get("intent") == identity]}


def bind(st, mid, topic, body, by, written_by):
    row = intent(st, mid, topic, body.get("intent"))
    prepared = _prepared(row, mid, topic)
    request = body.get("request")
    exp = st.cv._act(request) if isinstance(request, str) else None
    if not exp or exp["act"] != "expectation-recorded" or exp.get("conversation") != P.home(st, mid):
        P.refuse("wrong-request", "bind the actual recorded request in this Magnet's own Conversation")
    prior = binding(st, mid, topic, row["post"])
    if prior and prior["request"] != request:
        P.refuse("intent-already-bound", "this intent is already bound to its original request")
    turn = st.corpus.read([exp.get("turn")])
    if (not turn or exp.get("actor") != by or turn[0].get("attributed_to") != by
            or artifacts._written_by_execution(turn[0])):
        P.refuse("wrong-request-author", "the actual asking Turn must be the owner's ordinary request")
    keyed = anchors.outcome_of(st.cv, by, prepared["request_op"])
    result = (keyed or {}).get("result", {})
    if result.get("turn", result.get("post")) != exp["turn"]:
        P.refuse("request-key-mismatch", "the request does not carry this intent's original send operation key")
    if request not in result.get("expectations", []):
        P.refuse("request-key-mismatch", "this expectation was not made by the original asking operation")
    parts = turn[0].get("body", {}).get("parts", [])
    words = "\n".join(p.get("text", "") for p in parts if p.get("type") == "text")
    if not words.startswith(prepared["text"]):
        P.refuse("question-mismatch", "the actual asking Turn does not begin with the frozen question")
    attached = {p.get("ref") for p in parts if p.get("type") == "file"}
    required = {a["ref"] for a in prepared["artifacts"]}
    if required - attached:
        P.refuse("attachments-missing", "attach every immutable input as an actual request file part",
                 missing=sorted(required - attached))
    if artifacts.reach_of(st.cv, request).get("reach") != "work":
        P.refuse("work-reach-required", "Perspective requests must use work reach")
    data = {"intent": row["post"], "request": request, "post": exp["turn"]}
    out = P.event(st, mid, topic, "bound", data, by, written_by=written_by)
    return {**data, "event": out}


def _latest_start(st, request):
    rows = st.corpus.operational(act="execution-started", caused_by=request, newest_first=True, limit=1)
    return rows[0] if rows else None


def _run_for(st, bound_request, execution=None):
    """The original run or an explicit native descendant's actual run.

    Following the existing hand-off line changes no grant or dispatch. It
    permits product reconciliation of normal delegated continuation, while
    unrelated and superseded executions are refused rather than re-bound.
    """
    if not execution:
        return bound_request, _latest_start(st, bound_request)
    rows = st.corpus.operational(act="execution-started", execution=execution, newest_first=True, limit=1)
    if not rows:
        P.refuse("late-execution", "this execution has no actual recorded start")
    start = rows[0]
    actual = start.get("caused_by")
    current = st.cv._act(actual) if actual else None
    seen = set()
    while current and current["id"] not in seen and current["id"] != bound_request:
        seen.add(current["id"])
        current = artifacts._handed_down_from(st.cv, current)
    if not current or current["id"] != bound_request:
        P.refuse("late-execution", "this execution does not carry this intent's request or its native continuation")
    latest = _latest_start(st, actual)
    if not latest or latest["id"] != start["id"]:
        P.refuse("late-execution", "this response is not from the request's latest execution")
    if artifacts.reach_of(st.cv, actual).get("reach") != "work":
        P.refuse("work-reach-required", "a Perspective's native continuation must retain work reach")
    return actual, start


def _actual_grant(st, mid, topic, identity, request, start):
    """Actual delivered facts only. No call to compose/governing_now.

    This baseline's web.dispatch.governing_ids computes CURRENT governance;
    it is not a historical-delivery read. A persisted live receipt is exact.
    Otherwise use the recorded dispatch delivery only when its join is unique;
    ambiguous resumed delivery stays pending instead of guessing by time.
    """
    authority = st.agents.authority
    token = authority.grant_of(start["execution"])
    live = authority.grant_for(token, st.path) if token else None
    if (live and live.get("expectation") == request and live.get("run") == start["id"]
            and live.get("delivered")):
        return {"expectation": request, "delivered": live["delivered"], "run": start["id"]}, "live-grant"
    receipts = _receipt_rows(st, mid, topic, identity)
    for row in receipts:
        d = row["detail"]["data"]
        if d.get("run") == start["id"] and isinstance(d.get("grant"), dict):
            return d["grant"], "recorded-live-grant"
    offered = st.corpus.operational(act=artifacts.MADE_AVAILABLE, execution=start["execution"],
        caused_by=start["id"], limit=2)
    if not offered:
        return None, "delivery-not-known"
    # MADE_AVAILABLE is emitted after actual execution and records the exact
    # dispatch artifact offering. It proves empty governing artifact reach too.
    governing = {w["governing"] for a in offered for w in (a.get("detail") or {}).get("why", [])
                 if w.get("because") == "drawn-on-by-governed" and w.get("governing")}
    # Recover all governing ids from the actual delivery where the baseline
    # has an unambiguous request-tagged boundary. Never recompute them now.
    starts = st.corpus.operational(act="execution-started", caused_by=request,
                                  actor=start["actor"], limit=2)
    if len(starts) == 1:
        deliveries = [d for d in st.corpus.deliveries(participant=start["actor"])
                      if any(s.get("for_expectation") == request for s in d.get("behavioural_sources", []))]
        if len(deliveries) == 1:
            governing.update(s["source_id"] for s in deliveries[0]["behavioural_sources"]
                if s.get("for_expectation") == request and s.get("source_id")
                and s.get("supplied_as") == "governance"
                and not s.get("source_kind", "").endswith("orientation")
                and (s.get("scope") in GOVERNING_SCOPES or s.get("scope") == WHOLE_BRAIN_SCOPE
                     or s.get("scope", "").startswith(GOVERNING_PREFIXES)))
            return {"expectation": request, "delivered": sorted(governing), "run": start["id"]}, "recorded-dispatch"
    # The recorded offering is an authoritative delivered-artifact fact, even
    # when this baseline cannot join all governing ids to a resumed boundary.
    # Preserve and union those exact facts in available(), with current record
    # reach; do not claim the missing governing-delivery join complete.
    return None, "recorded-delivery-join-unavailable"


def _receipt_rows(st, mid, topic, identity):
    return st.corpus.operational(act=P.ACT,
        detail_is={"magnet": mid, "perspective": topic, "event": "reconciled"},
        detail_names=identity, newest_first=True, limit=100)


def _declared(st, mid, topic, identity, supplied):
    refs = list(supplied)
    # Explicit declarations persist as receipt versions, separately from the
    # original immutable manifest. They are never inferred from available().
    for row in _receipt_rows(st, mid, topic, identity):
        refs.extend(row["detail"]["data"].get("declared_context", []))
    return list(dict.fromkeys(refs))


def reconcile(st, mid, topic, body, by, written_by):
    P.require_grounded()
    if body.get("purpose") not in ("resume", "attach", "display", "reuse"):
        P.refuse("purpose-required", "reconcile for resume, attach, display or reuse")
    row = intent(st, mid, topic, body.get("intent"))
    bound = binding(st, mid, topic, row["post"])
    if not bound:
        P.refuse("request-not-bound", "bind the actual request before reconciling its delivered reach")
    request, start = _run_for(st, bound["request"], body.get("execution"))
    declared = _declared(st, mid, topic, row["post"],
                         E.refs(body.get("declared_context", []), "declared_context"))
    prepared = _prepared(row, mid, topic)
    required = {a["ref"] for a in prepared["artifacts"]} | set(declared)
    grant, source = _actual_grant(st, mid, topic, row["post"], request, start) if start else (None, "not-started")
    available, missing, extra, closure, errors = [], [], [], None, []
    status = "pending"
    if grant is not None:
        available = artifacts.available(st.corpus, st.cv, grant)
        # Exclude only this committed run's own produced outputs, never an
        # earlier return on a reused MARS session or prior run of this request.
        returns = st.corpus.operational(act=artifacts.RETURNED, execution=start["execution"],
                                        caused_by=request)
        order = st.corpus.operational_order([start["id"]] + [a["id"] for a in returns])
        outputs = {a["about"][0] for a in returns if a.get("about")
                   and order[a["id"]] > order[start["id"]]}
        reachable = {a["ref"] for a in available}
        missing = sorted(required - reachable)
        extra = [a for a in available if a["ref"] not in required and a["ref"] not in outputs]
        try:
            graph = E.Closure(st, mid)
            graph.add(prepared["manifest"]["ref"], prepared["manifest"])
            for ref in declared:
                graph.add(ref)
            closure = graph.summary()
        except Refused as exc:
            errors.append(exc.refusal)
        if request != bound["request"]:
            absent_parts = {a["ref"] for a in prepared["artifacts"]} - set(
                artifacts.asked_with(st.corpus, st.cv, request))
            if absent_parts:
                errors.append({"code": "continuation-parts-missing",
                    "error": "the native hand-off must attach the immutable package as actual file parts",
                    "missing": sorted(absent_parts)})
        status = "qualified" if not missing and not extra and not errors else "unqualified"
    data = {"intent": row["post"], "request": request, "execution": start["execution"] if start else None,
        "run": start["id"] if start else None, "status": status, "source": source,
        "purpose": body["purpose"], "grant": grant, "declared_context": declared,
        "required_unavailable": missing, "reachable_not_declared": extra, "available": available,
        "closure": closure, "errors": errors, "disclosure": P.DISCLOSURE}
    snap = P.hold(st, mid, _package(st, mid, "receipt", perspective=topic, **data), by, name="receipt")
    P.event(st, mid, topic, "reconciled", data, by, snapshot=snap, written_by=written_by)
    return {"receipt": snap, **data}


def finalize(st, mid, topic, body, by, written_by):
    P.require_grounded()
    row = intent(st, mid, topic, body.get("intent"))
    bound = binding(st, mid, topic, row["post"])
    if not bound:
        P.refuse("request-not-bound", "bind this intent's actual request first")
    request, start = _run_for(st, bound["request"], body.get("execution"))
    if not start or body.get("execution") != start["execution"]:
        P.refuse("late-execution", "a late answer cannot be frozen for a newer execution")
    answer = body.get("answer")
    turns = st.corpus.read([answer]) if isinstance(answer, str) else []
    if (not turns or not st.cv._is_kind(answer, "contribution")
            or st.cv.conversation_of(answer) != P.home(st, mid)
            or turns[0].get("attributed_to") != start["actor"]):
        P.refuse("wrong-answer", "select an actual answer by this request's producing execution")
    # Exact producing association, not merely a same-author reply or prose id.
    acts = st.corpus.operational(execution=start["execution"], turn=answer)
    ids = [a["id"] for a in acts] + [start["id"]]
    order = st.corpus.operational_order(ids)
    proven = any(order[a["id"]] > order[start["id"]]
                 and a.get("caused_by") in (request, start["id"])
                 and a["act"] in ("turn-said", "result-returned", "result-recovered") for a in acts)
    ends = st.corpus.operational(caused_by=start["id"], act=("result-returned", "result-recovered"))
    proven = proven or any((a.get("detail") or {}).get("reply_turn") == answer for a in ends)
    if not proven:
        P.refuse("answer-not-produced", "the record does not associate this answer with this committed run")
    check = reconcile(st, mid, topic, {"intent": row["post"], "execution": start["execution"],
        "purpose": "attach"}, by, written_by)
    if check["status"] != "qualified":
        # Keep the failed/pending receipt durable. The raw reply remains an
        # ordinary reply; no answer artifact or synthesized history is made.
        return {"answer": None, "receipt": check, "event": None, "refused": True,
                "code": "unqualified-answer", "error": "the ordinary reply is not qualified as a synthesis"}
    prepared = _prepared(row, mid, topic)
    desc = prepared["manifest"]
    graph = E.Closure(st, mid)
    graph.add(desc["ref"], desc)
    manifest = graph.objects[desc["ref"]]
    dependencies = [desc]
    dependencies.extend(E.descriptor(st, ref) for ref in check["declared_context"])
    # These were outputs of the producing run, so excluded from its INPUT
    # accounting. They become counted dependencies when this answer is reused.
    dependencies.extend(E.descriptor(st, ref) for ref in E.attachments(turns[0]["body"]["parts"]))
    dependencies = list({d["ref"]: d for d in dependencies}.values())
    snap = P.hold(st, mid, _package(st, mid, "answer", perspective=topic, intent=row["post"],
        request=request, request_post=st.cv._act(request)["turn"], bound_request=bound["request"], answer=answer,
        execution=start["execution"], run=start["id"], manifest=desc,
        parts=turns[0]["body"]["parts"], originals=manifest["originals"], support=manifest["support"],
        receipt=check["receipt"], dependencies=dependencies), by, name="answer")
    out = P.event(st, mid, topic, "answered", {"intent": row["post"], "request": request,
        "answer": snap, "answer_post": answer, "manifest": desc, "execution": start["execution"],
        "run": start["id"]}, by, snapshot=snap, written_by=written_by)
    return {"answer": snap, "receipt": check, "event": out}
