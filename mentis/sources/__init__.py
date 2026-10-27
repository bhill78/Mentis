"""Bulk Source: external material observed, acquired as Admissions, read back.

WHAT THIS IS. The generic half of the Bulk Source connector: the observation
shape, latest-observation replay, scope-qualified absence and the one write
path. A connector (today only `mentis.sources.filesystem`) surveys its source
and hands this module observations; this module compares them with the latest
recorded observation of each source object and appends what changed. It holds
no table, no registry and no index of its own -- every observation is an
ordinary Admission, every sweep an ordinary operational act, and the bytes are
in the corpus's own held store.

THE DISTINCTIONS THIS KEEPS, as decided (conversation ent-cc71013e9872, Turns
24, 27 and 29):

  collection declaration   an operational act, append-only, in the Brain:
                           stable collection id, name, declarer, time and the
                           include/exclude filters that define its scope.
                           Never a source of content and never "live".
  machine-local binding    collection id -> absolute root on THIS machine
                           (`mentis.sources.bindings`). Never in the Brain.
  source identity          collection id + normalised relative path. Not the
                           absolute path, not the blob digest, not an inode.
  Admission                a historical observation of one source object at
                           one sweep. Not the live file.
  retained bytes           an acquired object's exact bytes, `held` under
                           their sha256. Not the live file either.
  live external source     whatever sits under a bound root now; reachable
                           only through a binding, only while sweeping.

  unbound   != absent        a sweep without a binding refuses; it infers
                             nothing.
  visible   != acquired      a file seen but not selected is never read.
  refused   != acquired      a selected file that could not be held (over the
                             held limit, unreadable, a reparse point) gets no
                             Admission, and is never inferred absent either.

WHAT THIS NEVER DOES. It never establishes, promotes or interprets anything:
the only thing it writes is Admissions, the act that produced them, and the
`produced` links between the two. There is no argument that yields an
epistemic entry.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from mentis.spine import held

#: Where a Bulk Source observation lives inside an Admission's envelope.
ENVELOPE = "bulk_source"

#: The acts. Vocabulary, not behaviour: the spine branches on none of them.
DECLARED = "source-collection-declared"
SWEPT = "source-swept"
#: A COLLECTION'S SCOPE, REVISED (owner decision 1, Sources slice 1). Append
#: only: the collection id never changes, and the declaration is never
#: rewritten. The latest revision IS the effective scope; with none, the
#: declaration is. Material that leaves scope is not examined by later
#: sweeps -- never inferred absent -- because `examined()` asks the effective
#: scope and `diff` already keeps silence outside it as `not_examined`.
SCOPE_REVISED = "source-scope-revised"

#: The relation from a sweep act to each Admission it produced. The same one
#: every other crossing uses, so lineage is read one way everywhere.
from mentis.conversation import PRODUCED  # noqa: E402

#: WHERE A CONNECTOR'S NON-PATTERN SCOPE FIELDS LIVE (the Git connector's
#: ref and commit window). A declaration, a revision and the effective scope
#: carry them as `options`, a plain dict the generic code compares and never
#: interprets; a connector that declares none -- the filesystem -- has `{}`
#: and records exactly what it did before they existed.
OPTIONS = "options"

#: THE STABLE SOURCE STATE. What decides whether an observation is new. Fresh
#: per-sweep context -- batch, sweep time, the act -- is deliberately NOT in
#: it: a token that included them would make every resweep append, which is
#: the defect the recovered audit warned of. Everything that can change what
#: the record says about the object IS in it: its state, its exact bytes, how
#: they are retained, its relations as authored and as resolved, and what the
#: bytes were found to be.
STABLE = ("state", "retention", "digest", "size", "payload_type",
          "encoding", "relations")

#: The exact words for a selected file the held store will not take. Decided
#: in Turn 29; deliberately not a number. The limit is whatever `held`
#: accepts today -- see `held.MAX_BYTES` -- and is not a Bulk Source semantic.
OVER_HELD_LIMIT = "not acquired: over held limit"


class Refused(ValueError):
    """The connector will not do this, and says why. Nothing was written."""


class PlanChanged(Refused):
    """What would be recorded now is not what was previewed. Nothing was
    written; plan again and confirm what is actually there."""


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def source_id(connector: str, collection: str) -> str:
    """Where a collection's Admissions are recorded: `<connector>:<col-id>`."""
    return f"{connector}:{collection}"


# -- declarations and scope, across every connector ---------------------------

def declarations(corpus) -> list[dict]:
    """Every declared collection, whatever its connector. A connector's own
    listing filters this; the reads never do, so a second connector's
    material is not invisible to them."""
    return [{**a["detail"], "declaration": a["id"], "at": a["at"]}
            for a in corpus.operational(act=DECLARED)
            if a["detail"].get("collection") and a["detail"].get("connector")]


def declaration(corpus, collection: str) -> dict | None:
    for d in declarations(corpus):
        if d["collection"] == collection:
            return d
    return None


def revisions(corpus, collection: str) -> list[dict]:
    """Every recorded revision of one collection's scope, in append order."""
    return [{**a["detail"], "act": a["id"], "at": a["at"]}
            for a in corpus.operational(act=SCOPE_REVISED)
            if a["detail"].get("collection") == collection]


def effective_scope(corpus, collection: str, decl: dict | None = None) -> dict:
    """The scope in force: the latest revision, or the declaration.

    `act` is the act that put it in force -- the revision, or the
    declaration itself -- and is what a plan id names, so a plan made under
    one scope is refused under another."""
    decl = decl or declaration(corpus, collection)
    if decl is None:
        raise Refused(f"{collection!r} is not a collection declared in this "
                      "corpus")
    revs = revisions(corpus, collection)
    if revs:
        r = revs[-1]
        return {"include": list(r["scope"]["include"]),
                "exclude": list(r["scope"]["exclude"]),
                "options": dict(r["scope"].get("options") or {}),
                "act": r["act"], "declaration": decl["declaration"],
                "revision": r["act"], "revised_by": r.get("revised_by"),
                "at": r["at"]}
    return {"include": list(decl.get("include") or []),
            "exclude": list(decl.get("exclude") or []),
            "options": dict(decl.get("options") or {}),
            "act": decl["declaration"], "declaration": decl["declaration"],
            "revision": None, "revised_by": None, "at": decl.get("at")}


def record_revision(corpus, cv, collection: str, *, include, exclude, by,
                    because=None, written_by=None, options=None) -> str:
    """Append a scope revision. Refuses one that changes nothing: an act that
    says the scope moved when it did not would be a false record.

    `options` are the connector's own NON-PATTERN SCOPE FIELDS (a Git ref and
    a commit window, say), carried and compared as data. None keeps the ones
    in force, so a folder -- which declares none -- records exactly what it
    always did."""
    decl = declaration(corpus, collection)
    if decl is None:
        raise Refused(f"{collection!r} is not a collection declared in this "
                      "corpus")
    was = effective_scope(corpus, collection, decl)
    options = dict(was["options"] if options is None else options)
    if (list(include), list(exclude), options) == (
            was["include"], was["exclude"], was["options"]):
        raise Refused("that is already this collection's scope; nothing "
                      "was recorded")
    scope = {"include": list(include), "exclude": list(exclude)}
    previous = {"include": was["include"], "exclude": was["exclude"],
                "act": was["act"]}
    if options or was["options"]:
        scope["options"] = options
        previous["options"] = was["options"]
    detail = {"collection": collection, "connector": decl["connector"],
              "scope": scope,
              "revised_by": by, "because": because or None,
              "written_by": written_by,
              "previous": previous}
    return cv.record_act(actor=by, act=SCOPE_REVISED, about=[collection],
                         because=because or "a Bulk Source scope revised",
                         detail=detail)


def token(obs: dict) -> str:
    """The stable state of one observation, as a digest."""
    return hashlib.sha256(canonical(
        {k: obs.get(k) for k in STABLE}).encode("utf-8")).hexdigest()


def observation(entry: dict) -> dict:
    """The Bulk Source observation an Admission carries, or {}."""
    return ((entry.get("body") or {}).get("envelope") or {}).get(ENVELOPE) or {}


def latest(corpus, source: str) -> dict[str, dict]:
    """The latest recorded Admission of every source object, by APPEND ORDER.

    Never by timestamp: two observations in one clock tick are still one
    before the other, and the record's own order is the answer."""
    out: dict[str, dict] = {}
    for e in corpus.admissions_from(source):
        obj = observation(e).get("object")
        if obj is not None:
            out[obj] = e
    return out


def fingerprint(prior: dict[str, dict]) -> str:
    """Where the record stood for this source: which Admission is latest for
    each object. A plan confirmed against a record that has moved since is
    refused, because what was previewed is no longer what would be written."""
    return hashlib.sha256(canonical(
        sorted((k, v["id"]) for k, v in prior.items())).encode()).hexdigest()


def diff(prior: dict[str, dict], observations: list[dict], *, examined,
         withheld, compare=None) -> dict:
    """What recording these observations would append. Pure: writes nothing.

    `examined(obj)` says whether this sweep's scope was COMPLETE for an
    object, which is the only thing that lets its silence mean absence.
    `withheld` names objects the sweep saw but did not acquire; they are
    neither admitted nor absent, and their latest observation stands.

    DUPLICATE IDENTITIES REFUSE THE BATCH. Two observations of one object in
    one sweep cannot both be the latest, and choosing one silently would be
    the connector deciding what the source said.
    """
    seen: dict[str, int] = {}
    for o in observations:
        seen[o["object"]] = seen.get(o["object"], 0) + 1
    dup = sorted(k for k, n in seen.items() if n > 1)
    if dup:
        raise Refused(f"{len(dup)} source identities occur more than once in "
                      f"this batch: {dup[:10]}. Nothing was recorded.")
    clash = sorted(set(seen) & set(withheld))
    if clash:
        raise Refused(f"observed and withheld at once: {clash[:10]}")

    admit, unchanged, kept = [], [], []
    for o in observations:
        was = prior.get(o["object"])
        t = token(o)
        if was is None:
            admit.append((o, "new", t))
        elif observation(was).get("token") == t:
            unchanged.append(o["object"])
        elif observation(was).get("state") == "absent":
            admit.append((o, "reappeared", t))
        else:
            outcome = compare(observation(was), o) if compare else None
            if outcome == "kept":
                kept.append(o["object"])
            else:
                admit.append((o, "widened" if outcome == "widened" else "changed", t))
    absent, not_examined = [], []
    for obj, was in prior.items():
        if obj in seen or obj in withheld:
            continue
        if observation(was).get("state") == "absent":
            continue
        if examined(obj):
            absent.append(obj)
        else:
            not_examined.append(obj)
    return {"admit": admit, "absent": sorted(absent),
            "unchanged": sorted(unchanged), "not_examined": sorted(not_examined),
            "withheld": sorted(withheld), "kept": sorted(kept)}


def prepare(corpus, *, source: str, observations: list[dict], examined,
            withheld, compare=None) -> dict:
    """What `apply` would compare, worked out BEFORE its transaction (R1).

    Replaying a source's history and diffing a sweep against it is the part
    of a sweep that grows with the collection, and inside the transaction it
    is time every other writer in the process waits through: about 1.5 s of
    a 3.4 s confirm that changed 3,000 of 30,000 objects. Done here, outside,
    it costs nobody anything.

    It decides nothing. `apply` uses it only if the source's latest position
    in append order is still `mark` INSIDE its transaction -- then the record
    it was computed from is the record, because nothing is ever removed or
    rewritten -- and otherwise works it out again in there, as it always
    did. `mark` is read FIRST: an Admission landing between it and the
    replay makes the two disagree, and that only ever means "work it out
    again", never a stale answer used.
    """
    mark = corpus.last_admission_seq(source)
    prior = latest(corpus, source)
    return {"source": source, "mark": mark, "prior": prior,
            "diff": diff(prior, observations, examined=examined,
                         withheld=withheld, compare=compare)}


def apply(corpus, cv, *, source: str, collection: str, connector: str,
          observations: list[dict], examined, withheld, scope: dict,
          act_detail: dict, actor, written_by=None, check=None,
          observed_at=None, prepared=None, compare=None) -> dict:
    """Record one sweep: Admissions, the act that produced them, and the
    `produced` links -- one transaction, against the record AS IT IS INSIDE
    that transaction.

    `check(prior, d)` is called under the write lock before anything is
    appended; a connector uses it to refuse a confirmation whose plan no
    longer matches. Held bytes must already be in the store: possession
    comes before the record of it, as `Corpus.admit` insists.

    `prepared` is `prepare(...)` over these same observations, taken before
    the transaction. It is used only if the source has not moved since; see
    `prepare`. Either way `check` sees the prior and diff of the record as it
    is inside the transaction.
    """
    batch = f"batch-{uuid.uuid4().hex[:12]}"
    with corpus.atomic():
        if (prepared is not None and prepared["source"] == source
                and corpus.last_admission_seq(source) == prepared["mark"]):
            prior, d = prepared["prior"], prepared["diff"]
        else:
            prior = latest(corpus, source)
            d = diff(prior, observations, examined=examined,
                     withheld=withheld, compare=compare)
        if check is not None:
            check(prior, d)
        items = [_admission(source=source, collection=collection,
                            connector=connector, obs=o, action=action, tok=t,
                            batch=batch, scope=scope, observed_at=observed_at)
                 for o, action, t in d["admit"]]
        for obj in d["absent"]:
            o = {"object": obj, "state": "absent", "retention": None,
                 "digest": None, "size": None, "payload_type": None,
                 "encoding": None, "relations": []}
            items.append(_admission(source=source, collection=collection,
                                    connector=connector, obs=o,
                                    action="absent", tok=token(o),
                                    batch=batch, scope=scope,
                                    observed_at=observed_at))
        # ONE APPEND FOR THE ADMISSIONS AND ONE FOR THE LINKS, not one per
        # row: the same rows, chain and order as `admit` and `write` once
        # each would give, in a fraction of the time every other writer
        # spends waiting for this transaction (R1).
        made = corpus.admit_many(items, attributed_to=actor,
                                 written_by=written_by)
        detail = dict(act_detail)
        detail.update({
            # WHAT THE SERVER OBSERVED OF THE REQUEST, on the act as on the
            # Admissions: an act has no `written_by` of its own.
            "written_by": written_by,
            "collection": collection, "connector": connector, "batch": batch,
            "scope": scope,
            "counts": {"new": sum(1 for _, a, _ in d["admit"] if a == "new"),
                       "changed": sum(1 for _, a, _ in d["admit"]
                                      if a == "changed"),
                       "reappeared": sum(1 for _, a, _ in d["admit"]
                                         if a == "reappeared"),
                       "kept": len(d["kept"]),
                       "widened": sum(1 for _, a, _ in d["admit"] if a == "widened"),
                       "absent": len(d["absent"]),
                       "unchanged": len(d["unchanged"]),
                       "withheld": len(d["withheld"]),
                       "not_examined": len(d["not_examined"])},
        })
        act = cv.record_act(actor=actor, act=SWEPT, about=[collection, *made],
                            because="a confirmed Bulk Source sweep",
                            detail=detail)
        corpus.link_many([{"from": act, "to": adm, "relation": PRODUCED}
                          for adm in made],
                         body={"reason": "observed in a Bulk Source sweep"},
                         attributed_to=actor, written_by=written_by)
    return {"act": act, "batch": batch, "admitted": made, **{
        k: d[k] for k in ("absent", "unchanged", "not_examined", "withheld", "kept")},
        "admitted_by_action": {a: [o["object"] for o, x, _ in d["admit"]
                                   if x == a]
                               for a in ("new", "changed", "reappeared", "widened")}}


def _admission(*, source, collection, connector, obs, action, tok, batch,
               scope, observed_at) -> dict:
    """One Admission of a sweep, as `Corpus.admit`'s arguments."""
    env = {k: obs.get(k) for k in STABLE}
    env.update({"object": obs["object"], "collection": collection,
                "connector": connector, "token": tok, "action": action,
                "batch": batch, "scope": scope,
                "native": obs.get("native") or {}})
    name = obs["object"].rsplit("/", 1)[-1]
    envelope = {ENVELOPE: env, "door": "bulk-source", "claimed_name": name,
                "claimed_media_type": obs.get("payload_type"),
                "size": obs.get("size")}
    if obs["state"] == "present":
        return dict(
            source=source, locator=held.LOCATOR + obs["digest"],
            observed_at=observed_at, payload=None, content="held",
            payload_type=obs.get("payload_type") or "application/octet-stream",
            envelope=envelope, batch=batch)
    return dict(
        source=source, locator=f"{source}/{obs['object']}",
        observed_at=observed_at, payload=None, content="absent",
        payload_type="application/octet-stream", envelope=envelope,
        batch=batch)
