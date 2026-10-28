"""Held artifacts: bytes that crossed into Mentis, and the record of it.

ONE PRIMITIVE, TWO DOORS. Bytes cross into Mentis two ways:

  worker return   a dispatched execution hands back a file from its own
                  directory (`return_artifact`)
  human ingress   the owner attaches a file to a Turn

After the bytes cross, both are exactly the same thing -- `hold`:

  <corpus>/artifacts/sha256/<2 hex>/<64 hex>              the bytes (spine.held)
  an Admission, content "held", locator "sha256:<hex>"    the record of possession
  an act (artifact-returned | artifact-submitted)         who brought them across
  a `produced` link from that act to the Admission        and that it made it

Only the act name, the actor and the `source` differ. Everything downstream --
describing, serving, Turn references, granting to an execution -- reads the
Admission and never asks which door the bytes came in by. Identical bytes are
stored once; every crossing keeps its own Admission, because deduplication is
physical and provenance is not.

WHAT THIS DOES NOT DO. It never reads a path -- it is handed bytes -- never
lists a workspace or a client's disk, never infers a return from prose, and
never serves a Content-Type on the sender's word alone.

PROVENANCE. Ported, not merged, from two prototypes by @Jim: the returned-
artifact execution (b29cce03, result ent-d5d2f4df4b38) and the artifact-ingress
execution (the second b29cce03 run, ent-091bd6ec6261), whose admit/crossing
split this keeps. Only behaviour those runs measured is carried over; what they
left as prototype (purge, the integrity sweep, `produced` bootstrap, grants
that follow delegation) is new here and tested here.
"""

from __future__ import annotations

import re

from mentis.conversation import ARTIFACT_RETURNED, PRODUCED, PURGED
from mentis.spine import held

MAX_BYTES = held.MAX_BYTES
LOCATOR = held.LOCATOR

#: The acts. Vocabulary, not behaviour: the spine branches on none of them.
RETURNED = ARTIFACT_RETURNED            # an execution handed bytes back
SUBMITTED = "artifact-submitted"        # a person attached bytes to a Turn
SUPPLIED = "artifact-supplied"          # bytes sent to an execution's tools
MADE_AVAILABLE = "artifacts-made-available"   # refs offered to a run
PURGE = "artifact-purged"               # the owner ended possession

#: The states an artifact reference can be in. Kept apart on purpose: each is
#: a different answer, and collapsing any two would make the record say
#: something it does not.
STATES = ("unknown", "not-an-artifact", "not-held", "held",
          "held-but-missing", "held-but-corrupt", "purged")


# -- what Mentis will actually serve ------------------------------------------
#
# THE SENDER'S media_type IS A CLAIM -- a worker's or a browser's alike -- and it
# is recorded as one. A treatment a browser would PARSE AS ITSELF (a raster
# image, a PDF) is granted only by the bytes' own signature. Any UTF-8 text is
# served as text/plain, and the claim may only choose among views that are safe
# for any text. Anything else is a download. Measured in the prototype: hostile
# HTML served this way fired 0 of its 7 beacons. Five signatures, not a
# file-inspection framework.

_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
)

#: The extension a materialised copy is given, by VIEW -- never by the
#: sender's filename, which is metadata and may be anything.
_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
        "image/webp": ".webp", "application/pdf": ".pdf",
        "html": ".html.txt", "markdown": ".md", "text": ".txt",
        "download": ".bin"}

#: THE LARGEST IMAGE `read_artifact` WILL SEND (Sources B, B1). There was no
#: cap on images before -- only the 25 MB held-store cap on any crossing --
#: and an image is not only written to the worker's directory but shown to
#: the model, which refuses much past 5 MB. So one is set here, for every
#: image `read_artifact` serves, whichever door it came in by. The largest
#: image in the owner's D&D Knowledge collection is about 1.5 MB. Over it is
#: a refusal that names the size, never a truncation.
READ_IMAGE_MAX = 5 * 1024 * 1024


def _signature(data: bytes) -> str | None:
    """The type the bytes' own signature says, or None. WebP is a RIFF
    container, so it is told by two marks rather than a prefix."""
    for sig, ctype in _SIGNATURES:
        if data.startswith(sig):
            return ctype
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def treatment(data: bytes, claimed: str | None) -> dict:
    """What these bytes will be served as, and how they may be drawn.

    `view` is one of image | pdf | html | markdown | text | download. `agrees`
    says whether the sender's claim matched; a claim that did not is recorded,
    not obeyed.
    """
    claim = (claimed or "").split(";")[0].strip().lower() or None
    ctype = _signature(data)
    if ctype is not None:
        view = "pdf" if ctype == "application/pdf" else "image"
        return {"content_type": ctype, "view": view,
                # A PDF viewer is a program; it is offered as a download.
                "disposition": "attachment" if view == "pdf" else "inline",
                "ext": _EXT[ctype], "claimed": claim,
                "agrees": claim == ctype}
    if _is_text(data):
        if claim in ("text/html", "application/xhtml+xml"):
            view = "html"
        elif claim in ("text/markdown", "text/x-markdown"):
            view = "markdown"
        else:
            view = "text"
        return {"content_type": "text/plain; charset=utf-8", "view": view,
                "disposition": "inline", "ext": _EXT[view], "claimed": claim,
                "agrees": claim is None or claim.startswith("text/")
                or claim in ("application/json", "image/svg+xml",
                             "application/xhtml+xml")}
    return {"content_type": "application/octet-stream", "view": "download",
            "disposition": "attachment", "ext": _EXT["download"],
            "claimed": claim, "agrees": False}


# -- the record of possession: ONE function for both doors ---------------------

def hold(corpus, cv, data: bytes, *, act: str, actor, source: str, door: str,
         claimed_name=None, claimed_media_type=None, claimed_path=None,
         claimed_digest=None, execution=None, runtime=None, conversation=None,
         turn=None, caused_by=None, because=None, written_by=None) -> dict:
    """Bytes first, then the record: Admission, act and `produced`, together.

    The bytes are written before anything names them, so no Admission can ever
    name bytes that were not there when it was written. The three records are
    one transaction, so there is never an Admission nobody brought across or
    an act that produced nothing.

    `claimed_digest` is what the sender computed on its side. A mismatch is a
    refusal: what arrived is not what was sent.
    """
    digest, fresh = held.put(corpus.root, data)
    if claimed_digest and claimed_digest != digest:
        raise ValueError(f"sent as {claimed_digest}, arrived as {digest}")
    envelope = {"size": len(data), "door": door,
                "claimed_name": claimed_name,
                "claimed_media_type": claimed_media_type}
    if claimed_path is not None:
        # Evidence of where the sender said it came from. Never followed.
        envelope["claimed_path"] = claimed_path
    with corpus.atomic():
        adm = corpus.admit(
            source=source, locator=LOCATOR + digest, observed_at=None,
            payload=None, content="held",
            payload_type=claimed_media_type or "application/octet-stream",
            envelope=envelope, attributed_to=actor, written_by=written_by)
        aid = cv.record_act(actor=actor, act=act, conversation=conversation,
                            turn=turn, execution=execution, runtime=runtime,
                            caused_by=caused_by, about=[adm], because=because,
                            detail={"digest": digest, "size": len(data),
                                    "claimed_name": claimed_name,
                                    "new_blob": fresh})
        corpus.write(body={"reason": "bytes crossed into Mentis"},
                     attributed_to=actor, written_by=written_by,
                     link={"from": aid, "to": adm, "relation": PRODUCED})
    return {"admission": adm, "act": aid, "digest": digest,
            "size": len(data), "new_blob": fresh}


def part(ref: str, *, corpus=None, text=None) -> dict:
    """A Turn part naming a held artifact. Ordinary: a type and a ref.

    `image` when the bytes are an image, `file` otherwise -- decided from the
    bytes when the corpus is given, so a claim cannot make a part an image.
    """
    kind = "file"
    if corpus is not None:
        d = describe(corpus, ref)
        if d.get("treatment", {}).get("view") == "image":
            kind = "image"
        out = {"type": kind, "ref": ref,
               "media_type": d.get("claimed_media_type"),
               "alt": d.get("name")}
    else:
        out = {"type": kind, "ref": ref}
    if text:
        out["text"] = text
    return out


# -- the human door: staged now, recorded when a Turn names it ------------------
#
# AS DECIDED (ent-8de47c31e5ef, restated for S4): attaching -- paste, drop or
# pick -- STAGES bytes and records nothing. The Admission, the
# artifact-submitted act and the Turn's reference are written when the Turn is
# posted, in one transaction. An abandoned draft leaves an unnamed blob: inert,
# never served (nothing names it), and eligible for `discard_unnamed`.

STAGED = LOCATOR          # a staged part's ref is `sha256:<hex>`


def stage(corpus_root: str, data: bytes, claimed_media_type=None) -> dict:
    """Hold bytes a browser sent. NO RECORD: nothing here says anybody
    submitted anything. No path arrives, because a browser has none."""
    digest, fresh = held.put(corpus_root, data)
    t = treatment(data, claimed_media_type)
    return {"staged": STAGED + digest, "digest": digest, "size": len(data),
            "new_blob": fresh, "view": t["view"],
            "served_as": t["content_type"], "claim_agrees": t["agrees"],
            "recorded": False,
            "note": "held, not recorded: it becomes a submission only when a "
                    "Turn that names it is posted"}


def staged_parts(corpus, parts) -> list[tuple[int, str]]:
    """(index, digest) of every part naming staged bytes. Refuses, before
    anything is written, a staged ref whose bytes are not here."""
    out = []
    for i, p in enumerate(parts or []):
        ref = p.get("ref") if isinstance(p, dict) else None
        if isinstance(ref, str) and ref.startswith(STAGED):
            digest = held.digest_of(ref)
            if digest is None or not held.has(corpus.root, digest):
                raise ValueError(f"{ref} was never received here; attach it "
                                 "again")
            out.append((i, digest))
    return out


def submit_staged(corpus, cv, parts, *, author, conversation,
                  written_by=None) -> tuple[list, list]:
    """The Admissions for a Turn's staged parts, rewritten to name them.

    Run INSIDE the Turn's transaction, before the Turn is said; the acts are
    written after it by `record_submissions`, which needs the Turn's id. One
    Admission per crossing, even for bytes already held: deduplication is
    physical, provenance is not. The part's type is decided by the bytes --
    a claim cannot make a part an image.
    """
    parts = list(parts)
    pending = []
    for i, digest in staged_parts(corpus, parts):
        p = dict(parts[i])
        data = held.read(corpus.root, digest)
        view = treatment(data, p.get("media_type"))["view"]
        adm = corpus.admit(
            source=f"submission:{author}", locator=LOCATOR + digest,
            observed_at=None, payload=None, content="held",
            payload_type=p.get("media_type") or "application/octet-stream",
            envelope={"size": len(data), "door": "human-ingress",
                      "claimed_name": p.get("alt"),
                      "claimed_media_type": p.get("media_type")},
            attributed_to=author, written_by=written_by)
        parts[i] = {**p, "ref": adm,
                    "type": "image" if view == "image" else "file"}
        pending.append({"admission": adm, "digest": digest,
                        "size": len(data), "name": p.get("alt")})
    return parts, pending


def record_submissions(corpus, cv, pending, *, author, conversation, turn,
                       written_by=None) -> list[str]:
    """The artifact-submitted act and `produced`, for each, now the Turn
    exists. Same transaction as the Turn."""
    acts = []
    for s in pending:
        aid = cv.record_act(actor=author, act=SUBMITTED,
                            conversation=conversation, turn=turn,
                            about=[s["admission"]],
                            because="attached by its author to this Turn",
                            detail={"digest": s["digest"], "size": s["size"],
                                    "claimed_name": s["name"]})
        corpus.write(body={"reason": "bytes crossed into Mentis"},
                     attributed_to=author, written_by=written_by,
                     link={"from": aid, "to": s["admission"],
                           "relation": PRODUCED})
        acts.append(aid)
    return acts


def discard_unnamed(corpus, *, older_than_s: float) -> dict:
    """Remove bytes NOTHING in the record names -- staged for a draft that was
    never posted -- once they are older than the caller says. Explicit and
    owner-run: a draft still open in a browser names its staged bytes only
    in that browser, so no age is safe to assume here."""
    import time as _time
    # A purged Admission names bytes Mentis no longer possesses: what it
    # left behind is unnamed, like any draft's.
    named = _live_digests(corpus)
    removed, kept = [], []
    now = _time.time()
    for d in held.blobs(corpus.root):
        if d in named:
            continue
        age = now - held.path(corpus.root, d).stat().st_mtime
        if age >= older_than_s:
            held.remove(corpus.root, d)
            removed.append(d)
        else:
            kept.append(d)
    return {"removed": removed, "kept_younger": kept}


def annotate_part(corpus, part):
    """A Turn part as the interface sees it: what stands behind its ref,
    read now, verified once per file version. Unknown refs are left as they
    were -- a part naming something that is not an artifact is not one."""
    if not isinstance(part, dict) or part.get("type") == "text" \
            or not part.get("ref"):
        return part
    if part.get("type") in ("acquired", "object"):
        # A REFERENCE TO ACQUIRED MATERIAL, NOT AN ATTACHMENT. Its bytes are
        # held, but nothing was attached: annotated as an artifact it would be
        # drawn as a file in the Turn. It is drawn as the reference it is.
        # So is an object reference (`objectref`): its ref is a post.
        return part
    d = describe(corpus, part["ref"], verify="cached")
    if d["state"] in ("unknown", "not-an-artifact"):
        return part
    return {**part, "artifact": public(d)}


# -- what stands behind a reference -------------------------------------------

def _purges(corpus, ref) -> list[dict]:
    return corpus.links(relation=PURGED, to=ref)


#: Verified digests, keyed by what would change if the file did. A listing
#: asks on every render, and hashing every held file every time is the cost
#: the alternative -- not verifying, and calling a corrupt file healthy --
#: was ruled out to avoid. Any change to the file's size or mtime re-hashes.
_VERIFIED: dict[tuple, str] = {}


def _state_cached(root, digest) -> str:
    try:
        st = held.path(root, digest).stat()
    except (FileNotFoundError, ValueError):
        return "missing"
    key = (str(root), digest, st.st_size, st.st_mtime_ns)
    if key not in _VERIFIED:
        _VERIFIED[key] = held.state(root, digest, verify=True)[0]
    return _VERIFIED[key]


def describe(corpus, ref: str, *, verify: bool | str = True) -> dict:
    """What the record says stands behind a ref. Every answer kept apart:

      unknown           this corpus holds no entry with that id
      not-an-artifact   it holds one, and it is not an Admission
      not-held          an Admission whose content is inline/external/absent
      held              the bytes are here and (verified) hash to their name
      held-but-missing  the record says held; no file is there
      held-but-corrupt  a file is there; it does not hash to its name
      purged            the owner ended possession; the record of it stays

    `verify`: True reads and hashes the bytes (and returns them as `_bytes`
    -- never send that anywhere; `public` drops it); "cached" hashes once per
    file version, for listings; False only asks whether the file is there.
    """
    got = corpus.read([ref]) if isinstance(ref, str) and ref else []
    if not got or got[0]["family"] != "admission":
        return {"ref": ref, "state": "unknown" if not got else "not-an-artifact"}
    body = got[0]["body"]
    if body.get("content") != "held":
        return {"ref": ref, "state": "not-held", "content": body.get("content"),
                "locator": body.get("locator")}
    env = body.get("envelope") or {}
    digest = held.digest_of(body.get("locator")) or ""
    out = {"ref": ref, "digest": digest, "size": env.get("size"),
           "claimed_media_type": body.get("payload_type"),
           "name": env.get("claimed_name"), "door": env.get("door"),
           "source": body.get("source"),
           "url": f"/api/artifacts/{ref}"}
    purges = _purges(corpus, ref)
    if purges:
        # PURGED IS ITS OWN ANSWER, not missing and not absent. Whether any
        # bytes remain under that digest is said separately, because another
        # Admission may still hold the same bytes, and a purge that crashed
        # between its act and the delete leaves them behind.
        return {**out, "state": "purged",
                "purged_by": [l["link"]["from"] for l in purges],
                "bytes_remain": held.has(corpus.root, digest)}
    if verify == "cached":
        st, data = _state_cached(corpus.root, digest), None
    else:
        st, data = held.state(corpus.root, digest, verify=bool(verify))
    out["state"] = {"present": "held", "missing": "held-but-missing",
                    "corrupt": "held-but-corrupt"}[st]
    if data is not None:
        out["treatment"] = treatment(data, body.get("payload_type"))
        out["_bytes"] = data
    return out


def public(d: dict) -> dict:
    d = dict(d)
    d.pop("_bytes", None)
    return d


def held_refs(corpus, parts) -> list[str]:
    """The Admission ids among these parts that name held artifacts.

    Held means the RECORD says held and nothing purged it; whether the bytes
    are intact is asked when they are read, not here.
    """
    out = []
    for p in parts or []:
        ref = p.get("ref") if isinstance(p, dict) else None
        if ref and describe(corpus, ref, verify=False)["state"] in (
                "held", "held-but-missing", "held-but-corrupt"):
            if ref not in out:
                out.append(ref)
    return out


# -- what an execution may read ------------------------------------------------

def _asking_turns(cv, expectation) -> list[str]:
    """The Turns that ASKED for this work.

    The expectation's own Turn, and any Turn a `work-delegated` act about it
    was recorded on -- which is where picked-up discovered work is handed over,
    since its expectation stays on the Turn that discovered it.
    """
    if not expectation:
        return []
    try:
        turns = [cv.expectation_state(expectation)["turn"]]
    except ValueError:
        return []                   # not a request: it was asked with nothing
    # Picked-up work: the assignment names the work it was picked up under,
    # and the delegation act under THAT work names this expectation and the
    # Turn the handover was written on.
    for asg in cv.history(caused_by=expectation):
        under = (asg["detail"] or {}).get("picked_up_under")             if asg["act"] == "expectation-assigned" else None
        for a in cv.history(caused_by=under) if under else ():
            if a["act"] == "work-delegated" and expectation in (a["about"]
                                                                 or ()):
                turns.append(a["turn"])
    return list(dict.fromkeys(x for x in turns if x))


def _parts_of(corpus, turn) -> list:
    """The Turn's parts AS IT NOW READS: an edit keeps every artifact part, and
    a deleted Turn holds nothing for new work to be handed."""
    from mentis.conversation.versions import presented
    got = corpus.read([turn])
    return (presented(corpus, got[0])["body"].get("parts") or []) if got else []


def asked_with(corpus, cv, expectation) -> list[str]:
    """The held artifacts on the Turns that ASKED for this work."""
    refs: list[str] = []
    for t in _asking_turns(cv, expectation):
        for r in held_refs(corpus, _parts_of(corpus, t)):
            if r not in refs:
                refs.append(r)
    return refs


def referenced_by_request(corpus, cv, expectation) -> list[dict]:
    """The held artifacts DIRECTLY in a Turn the asking Turns explicitly
    reference, each with the reference that brought it.

    FOUND IN PRODUCTION ACCEPTANCE (#85 -> #86): "describe the image in #85",
    with #85 a structured Turn reference, reached a run granted nothing,
    because only the asking Turn's own parts were read. Asking about an
    earlier Turn is asking with what it holds.

    DELIBERATELY NARROW. Only a structured `turn` part counts -- never prose,
    and never a Conversation or Topic reference, which would reach everything
    in it. One hop: what the referenced Turn itself only references is not in
    it, and is not walked to.
    """
    out: list[dict] = []
    seen: set = set()
    for t in _asking_turns(cv, expectation):
        for p in _parts_of(corpus, t):
            if not isinstance(p, dict) or p.get("type") != "turn":
                continue
            target = p.get("ref")
            got = corpus.read([target]) if target else []
            # A Turn, checked: an entry names its definition, and that name
            # is its Kind.
            if not got or (got[0].get("definition") or {}).get(
                    "name") != "contribution":
                continue
            # A DELETED TURN IS NOT NEW PROVENANCE: naming it hands nothing on.
            for r in held_refs(corpus, _parts_of(corpus, target)):
                if r not in seen:
                    seen.add(r)
                    out.append({"ref": r, "because": "referenced",
                                "referenced_turn": target,
                                "referenced_by": t})
    return out


def object_referenced_by_request(corpus, cv, expectation) -> list[dict]:
    """The held artifact an asking Turn's OBJECT reference names, each with
    the reference that brought it (the owner's decision, 2026-10-28: an
    object reference gives an addressed agent THAT ONE OBJECT).

    NARROWER STILL than `referenced_by_request`: not what the post holds,
    only the one object named -- an attachment, or a file a run returned --
    read at the version the author selected (`objectref.for_request`). A
    Markdown object (a chart, a table, a form) holds no artifact and offers
    none; its source is told in the run's context. One hop, and the post
    must not have been deleted, as for a `turn` reference."""
    from mentis.conversation import objectref
    out: list[dict] = []
    for c in objectref.for_request(corpus, cv, expectation, content=False):
        r = c.get("artifact")
        if r and c.get("resolves") and held_refs(corpus, [{"ref": r}]):
            out.append({"ref": r, "because": "referenced-object",
                        "object": c["exact"], "referenced_turn": c["ref"],
                        "referenced_by": c["turn"]})
    return out


# -- named by the owner in the request -----------------------------------------
#
# THE OWNER'S CORRECTION (Anchored Interaction, Turn ent-cb649f419cd5): "When
# the OWNER explicitly references a valid held artifact ID in the request that
# starts/carries work, that artifact is offered to that request." Attaching
# the same artifact through the composer communicated no additional intent or
# authority, so asking for it was ceremony. Owner-authored current request +
# explicit valid artifact id = an explicit offer to that request -- recorded
# like `asked-with`, on MADE_AVAILABLE and SUPPLIED, as `named-by-owner`.
#
# DELIBERATELY NARROW, and the owner listed what it does NOT mean:
#   * an agent gains no reach by discovering an id, writing one in prose, in
#     a delegation, in discovered work or in a decision request: a request an
#     execution made is never read here (`_raised_by_execution`);
#   * an id anywhere else in the Conversation's history grants nothing: ONLY
#     the request's own asking Turn is read -- not referenced Turns, not
#     handover Turns, not replies, not other Turns;
#   * `resolve`/`find` grant nothing, and naming a Turn does not hand on what
#     that Turn's prose names (prose is read only on the asking Turn itself);
#   * nothing becomes ambient: the offer is to THIS request (and to what it
#     hands on through `delegate(artifacts=...)`, which checks `reachable`),
#     never to the Conversation or the Brain -- `in_conversation` is untouched;
#   * no bytes are copied, no Admission is made and provenance is unchanged.
#
# THE OWNER'S TURN IS THE AUTHORITY, so quoted text in it counts: if the owner
# pastes an agent's message naming an id into their own request, that is the
# owner's request naming it. What the owner's interface records as theirs is
# theirs (web `_routes`, "WHY THERE IS NO AUTHORITY GUARD ON THIS DOOR"); no
# stronger owner authentication is built, by the owner's instruction.
#
# THE OWNER'S TWO FURTHER DECISIONS (Anchored Interaction):
#   * Turn ent-79a7ef1a40fa -- "what I send is mine": an id that reaches the
#     owner's draft by ANY means, including the Brief's answer line and the
#     "Send back to agent" copy button, counts as the owner naming it once
#     the owner sends it. Neither button needs a guard; the rule is unchanged.
#   * Turn ent-6b36672dd8bc -- naming a returned piece of restricted work
#     offers it to the request, exactly as attaching it does
#     (`test_restricted_returns_named_by_the_owner_are_offered_as_if_attached`).

ADMISSION_TOKEN = re.compile(r"(?<![0-9A-Za-z_-])adm-[0-9a-f]{12}(?![0-9A-Za-z_])")

# The worker surface's three ways of recording a request, each leaving its own
# act about the expectation it made (`mentis/worker.py`). A request carrying
# any of them was made by an execution, not asked by a person.
_EXECUTION_REQUEST_ACTS = ("work-delegated", "work-discovered",
                           "decision-requested")


def _raised_by_execution(cv, exp: dict) -> bool:
    if _delegation(cv, exp) is not None:
        return True
    # A question of a decision form may be on no post (P7): its
    # `decision-requested` is then found under the work it was asked in.
    return any(a["act"] in _EXECUTION_REQUEST_ACTS
               and exp["id"] in (a["about"] or ())
               for a in (cv.history(turn=exp["turn"]) if exp.get("turn")
                         else cv.history(caused_by=exp.get("caused_by"))
                         if exp.get("caused_by") else ()))


def _written_by_execution(entry: dict) -> bool:
    """A Turn the worker surface wrote says so in `written_by` (runtime and
    execution); one through the owner's door says what the server observed,
    which for a request presenting no grant is `unattributed-local-request`.
    NOT merely defence in depth beside `_raised_by_execution`: for a runtime
    dispatched AS the owner's Participant (a grandchild may `delegate` to
    @brian, since `delegate` refuses only the work's own requester), its Turn
    is attributed to the owner and, recorded as a request through the owner
    door, carries no worker act -- this is the ONLY guard that refuses it
    (pinned by `test_a_runtime_dispatched_as_the_owner_names_nothing`)."""
    w = entry.get("written_by")
    return bool(w) and w != "unattributed-local-request"


def named_by_owner(corpus, cv, expectation) -> list[dict]:
    """The held artifacts the person who asked for this work named, by exact
    id, in the text of the Turn they asked it on. See the block above."""
    from mentis.conversation.versions import presented
    exp = _expectation_act(cv, expectation)
    if exp is None or not exp.get("turn") or _raised_by_execution(cv, exp):
        return []
    got = corpus.read([exp["turn"]])
    if not got or got[0].get("attributed_to") != exp.get("actor") \
            or _written_by_execution(got[0]):
        return []
    # AS IT NOW READS: a deleted Turn names nothing, and an edit counts only
    # as the asker's own. `versions.edit` refuses anybody else's, but the
    # owner door's generic `revise` act (web `_routes`, `act == "revise"`,
    # `/api/entries/{id}/revise`) lets a NON-author install a new current
    # version of the asking Turn; that version records `edited_by` as theirs,
    # and this check is what refuses it (pinned by
    # `test_a_non_author_revision_of_the_asking_turn_names_nothing`).
    now = presented(corpus, got[0])
    if now.get("deleted") or (now.get("revision") or {}).get(
            "edited_by", exp.get("actor")) != exp.get("actor"):
        return []
    named: list[str] = []
    for p in now["body"].get("parts") or []:
        if isinstance(p, dict) and p.get("type") == "text" \
                and isinstance(p.get("text"), str):
            named += ADMISSION_TOKEN.findall(p["text"])
    held_named = held_refs(corpus, [{"ref": r} for r in
                                    dict.fromkeys(named)])
    return [{"ref": r, "because": "named-by-owner", "turn": exp["turn"]}
            for r in held_named]


def returned_under(cv, expectation) -> list[str]:
    """What runs carrying this expectation returned, in order. Any run: a
    resumed or continued run of the same work already had these."""
    if not expectation:
        return []
    return [r for a in cv.history(caused_by=expectation)
            if a["act"] == RETURNED for r in a["about"][:1]]


def available(corpus, cv, grant: dict) -> list[dict]:
    """What THIS execution may read, and why, and nothing else.

      * what the request it carries was made with;
      * what the person who asked for it named by exact id in the text of
        the Turn they asked it on (`named_by_owner`);
      * what is directly in a Turn that request explicitly references
        (`referenced_by_request`);
      * the one held artifact an object reference on that Turn names
        (`object_referenced_by_request`);
      * what earlier runs of the same work returned;
      * what the children this work DECLARED it was waiting on returned --
        the delegations made with `return_to_me`. A resumed coordinator reads
        its children's returns; side work it did not wait on stays out.
      * what the STANDING governing material this run was told draws on
        (`drawn_on_by_governed`): a Discipline's reference or example that
        is a held artifact, listed in its delivery by reference.

    Not every artifact in the Conversation and not every one in the Brain.
    Each ref appears once, with the first reason that admitted it. This is
    what was MADE AVAILABLE; whether bytes were sent is `SUPPLIED`.
    """
    exp = grant.get("expectation")
    if not exp:
        return []
    why = [{"ref": r, "because": "asked-with"}
           for r in asked_with(corpus, cv, exp)]
    why += named_by_owner(corpus, cv, exp)
    why += referenced_by_request(corpus, cv, exp)
    why += object_referenced_by_request(corpus, cv, exp)
    why += [{"ref": r, "because": "returned-under"}
            for r in returned_under(cv, exp)]
    for child in cv.waiting_on(exp)["required"]:
        why += [{"ref": r, "because": "returned-by-child",
                 "child": child.get("expectation")}
                for r in child.get("returned_artifacts") or []]
    why += drawn_on_by_governed(corpus, cv, grant.get("delivered") or ())
    out, seen = [], set()
    for w in why:
        if w["ref"] not in seen:
            seen.add(w["ref"])
            # NOT OFFERED WHAT THE DOOR WOULD REFUSE (Sources B). An acquired
            # file a Turn cites is held bytes, but unless it is an image it is
            # read with `read_source`, never `read_artifact`, so listing it
            # here would offer a read that is then refused.
            acquired = acquired_reach(corpus, w["ref"])
            if acquired is not None and acquired[0] is None:
                continue
            out.append(w)
    return out


def drawn_on_by_governed(corpus, cv, delivered) -> list[dict]:
    """The held artifacts that governing material THIS RUN WAS TOLD draws on.

    `delivered` is the run's own composition, by source id (on its grant; see
    `dispatch._dispatch`) -- named for its work, carried by its Persona or
    placed where it runs. Only material that STILL STANDS opens anything: a
    Discipline superseded mid-run no longer offers its references, and one
    nobody established never did. Only links nothing has ended, to artifacts
    whose line was not deleted (`Conversations.drawn_on`). It reaches nothing
    the material does not name, and nothing at all for material the run was
    not told.
    """
    from mentis.conversation import KNOWING_HOW, knowing_of
    out = []
    for eid in dict.fromkeys(delivered):
        if not str(eid).startswith("ent-") or not corpus.stands(eid)["stands"]:
            continue
        # AND ONLY MATERIAL THAT DIRECTS WORK, asked of its Kind's declaration.
        # `delivered` is already only governing material; this is the same
        # question asked again where bytes are at stake.
        got = corpus.read([eid])
        kind = ((got[0].get("definition") or {}).get("name")) if got else None
        if knowing_of(corpus, kind) != KNOWING_HOW:
            continue
        for row in cv.drawn_on(eid):
            if row["artifact"] and held_refs(corpus, [{"ref": row["to"]}]):
                out.append({"ref": row["to"],
                            "because": "drawn-on-by-governed",
                            "governing": eid, "role": row["role"],
                            "label": row["label"]})
    return out


def granted(corpus, cv, grant: dict) -> list[str]:
    """The refs `available` admits, in order -- what is OFFERED to a run."""
    return [w["ref"] for w in available(corpus, cv, grant)]


# -- what an execution may REACH ---------------------------------------------
#
# FOUND IN PRODUCTION (Mentis Features / Upgrades #49 -> #50). The owner asked
# Caretaker to zip the screenshots Huey, Dewey and Louie had returned into the
# same Conversation. Every one was held by Mentis, every one was named in a
# reply sitting a few Turns up, and `read_artifact` refused all fourteen,
# because the door admitted only what `available` OFFERS -- what the request
# was made with, what it explicitly referenced, and its own lineage. Collating
# other agents' outputs is ordinary work, and asking the owner to download and
# re-upload fourteen files Mentis already holds is not a boundary, it is a
# chore.
#
# THE RULE, as the owner stated it: unless restricted, an agent may inspect
# the responses and returned artifacts of other agents that are reachable
# through the Conversation it was asked to operate on. Three things are kept
# apart, and the record says each:
#
#   * OFFERED (`available`, recorded as MADE_AVAILABLE): the short list sent
#     to a run by reference in its prompt. Unchanged -- a Conversation-wide
#     list in every prompt would be noise.
#   * REACHABLE (`reachable`): what the door admits on request. The offered
#     list, plus -- for work a person asked for -- what is held in that
#     Conversation.
#   * SUPPLIED (SUPPLIED): bytes actually sent, each with the reason it was
#     reachable.
#
# NOT AMBIENT. Reach is the Conversation the work is IN, never the Brain: an
# artifact held in another Conversation stays out. DELEGATED work is bounded:
# a child receives what its delegation handed it (and its own lineage), not
# its parent's Conversation, unless the delegation explicitly widened it
# (`reach="conversation"`, admissible only from work that has that reach
# itself). RESTRICTED work keeps its returns to itself and its own lineage:
# nobody else reaches them through the Conversation, whatever their reach.
#
# STILL RECORD-MEDIATED. Everything here is read off the record -- the act
# that produced the Admission, the Turns as they now read -- and the bytes
# come from Mentis's custody. A deleted Turn holds nothing, a purged artifact
# has no bytes, and where the producing worker's workspace went is irrelevant.

RESTRICTED = "work-restricted"          # this work's returns are its own
REACH_CONVERSATION = "conversation"
REACH_WORK = "work"


def _expectation_act(cv, expectation) -> dict | None:
    a = cv._act(expectation) if expectation else None
    return a if a and a["act"] == "expectation-recorded" else None


def _delegation(cv, exp: dict) -> dict | None:
    """Was this work handed out by another execution (a child, or picked-up
    discovered work), rather than asked for by a person? `None` if not, else
    what the delegation said about reach.

    Read off the delegation acts, never off `caused_by`: a person continuing
    earlier work records a request caused by the earlier one, and that is not
    a delegation.
    """
    if any(a["act"] == "work-delegated" and exp["id"] in (a["about"] or ())
           for a in cv.history(turn=exp["turn"])):
        return {"reach": (exp["detail"] or {}).get("reach")}
    picked = [a for a in cv.history(caused_by=exp["id"])
              if a["act"] == "expectation-assigned"
              and (a["detail"] or {}).get("picked_up_under")]
    if picked:
        # The latest pick-up is the one in force; its own detail says reach.
        return {"reach": (picked[-1]["detail"] or {}).get("reach")}
    return None


def reach_of(cv, expectation) -> dict:
    """How far the work carrying `expectation` reaches, and why."""
    exp = _expectation_act(cv, expectation)
    if exp is None:
        return {"reach": None, "because": "this execution carries no request"}
    handed = _delegation(cv, exp)
    if handed is not None:
        if handed["reach"] == REACH_CONVERSATION:
            return {"reach": REACH_CONVERSATION,
                    "conversation": exp["conversation"],
                    "because": "delegated work whose delegation widened it to "
                               "the Conversation"}
        return {"reach": REACH_WORK, "conversation": exp["conversation"],
                "because": "delegated work is bounded to what its delegation "
                           "handed it and its own lineage"}
    if (exp["detail"] or {}).get("reach") == REACH_WORK:
        return {"reach": REACH_WORK, "conversation": exp["conversation"],
                "because": "the request was bounded to what it was made with"}
    return {"reach": REACH_CONVERSATION, "conversation": exp["conversation"],
            "because": "work asked for directly in this Conversation, not "
                       "delegated by another execution"}


def restriction_of(cv, expectation) -> str | None:
    """The request in this work's lineage that was restricted, if any.

    A restriction covers the work it was recorded on and everything delegated
    beneath it, so the walk goes up `caused_by` through expectations.
    """
    seen = set()
    cur = _expectation_act(cv, expectation)
    while cur is not None and cur["id"] not in seen:
        seen.add(cur["id"])
        if any(a["act"] == RESTRICTED
               for a in cv.history(caused_by=cur["id"])):
            return cur["id"]
        cur = _expectation_act(cv, cur.get("caused_by"))
    return None


def restrict(cv, expectation, *, by, because: str) -> str:
    """Record that this work's returns are its own. Appended, never removed
    by rewriting; nothing already supplied is recalled."""
    exp = _expectation_act(cv, expectation)
    if exp is None:
        raise ValueError(f"{expectation!r} is not a request in this record")
    if not (because or "").strip():
        raise ValueError("a restriction says why")
    return cv.record_act(actor=by, act=RESTRICTED,
                         conversation=exp["conversation"], turn=exp["turn"],
                         caused_by=expectation, about=[expectation],
                         because=because)


def _lineage(cv, expectation) -> set:
    out, cur = set(), _expectation_act(cv, expectation)
    while cur is not None and cur["id"] not in out:
        out.add(cur["id"])
        cur = _expectation_act(cv, cur.get("caused_by"))
    return out


def producing_act(corpus, cv, ref) -> dict | None:
    """The act that brought these bytes across, joined by `produced`."""
    for link in corpus.links(relation=PRODUCED, to=ref):
        a = cv._act(link["link"]["from"])
        if a is not None:
            return a
    return None


def _live(corpus, turn) -> bool:
    """A Turn that exists and has not been deleted, as it now reads."""
    from mentis.conversation.versions import presented
    got = corpus.read([turn]) if turn else []
    return bool(got) and not presented(corpus, got[0]).get("deleted")


def _result_turns(cv, made: dict) -> list:
    """The Turns the returning run posted as its results for the request the
    return was made under. Any of them still standing keeps the work's
    returns in view."""
    if not made.get("execution"):
        return []
    # ONLY THE RESULTS OF THE SAME REQUEST (found by review): a long-lived
    # carrier answers many, and another request's live result must not keep
    # this one's returns in view. A result is caused by the run's start, and
    # the start by the request it carried.
    out = []
    for a in cv.history(execution=made["execution"]):
        if a["act"] != "result-returned" or not a.get("turn"):
            continue
        start = cv._act(a.get("caused_by"))
        if start is not None and start.get("caused_by") == made.get(
                "caused_by"):
            out.append(a["turn"])
    return out


def in_conversation(corpus, cv, conversation, ref, *,
                    reader=None) -> tuple[dict | None, str]:
    """Is `ref` held in `conversation`, and if so how? `(reason, "")` or
    `(None, why_not)`.

    WHERE THE BYTES CAME IN DECIDES IT, not where a ref was later written.
    Found by review: counting any part of any live Turn let a worker post a
    ref from another Conversation in its own reply and then read it -- the
    ref laundered into this Conversation by being mentioned. So the
    producing act must have been recorded HERE:

      * returned here by a run (`returned-in-conversation`), and withdrawn
        when every Turn that carried that work -- the asking Turn and the
        result Turns -- has been deleted;
      * attached here by a person (`posted-in-conversation`), and only while
        a live Turn here still carries it.

    RESTRICTION reaches only along a line, never sideways: the reader is
    exempt only if it IS the restricted work, descends from it, or is an
    ancestor of the work that returned it. A sibling under the same
    coordinator is not exempt (found by review).
    """
    st = describe(corpus, ref, verify=False)["state"]
    if st not in ("held", "held-but-missing", "held-but-corrupt"):
        return None, f"it is {st}"
    made = producing_act(corpus, cv, ref)
    if made is None or made.get("conversation") != conversation:
        return None, "it is not held in this Conversation"
    producer = {"act": made["id"], "kind": made["act"],
                "actor": made.get("actor"),
                "execution": made.get("execution"),
                "expectation": made.get("caused_by")}
    if made["act"] == RETURNED:
        barred = (restriction_of(cv, made["caused_by"])
                  if made.get("caused_by") else None)
        if barred and not (barred in _lineage(cv, reader)
                           or (reader and reader in _lineage(
                               cv, made["caused_by"]))):
            return None, f"it was returned under restricted work ({barred})"
        carriers = [made.get("turn")] + _result_turns(cv, made)
        carriers = [t for t in dict.fromkeys(carriers) if t]
        if carriers and not any(_live(corpus, t) for t in carriers):
            return None, ("every Turn that carried the work that returned "
                          "it has been deleted")
        return {"ref": ref, "because": "returned-in-conversation",
                "conversation": conversation, "producer": producer}, ""
    # Attached by a person: the Turn it came in on first, then any other live
    # Turn here BY THAT SAME PERSON that carries it (reused without
    # re-upload). Not somebody else's echo of it (found by review): a
    # worker quoting an upload must not keep it reachable after the person
    # who attached it deleted it.
    first = made.get("turn")
    if first and ref in held_refs(corpus, _parts_of(corpus, first)):
        return {"ref": ref, "because": "posted-in-conversation",
                "conversation": conversation, "turn": first,
                "producer": producer}, ""
    for row in cv.turns(conversation):
        if row["turn"] == first or row["entry"].get(
                "attributed_to") != made.get("actor"):
            continue
        if ref in held_refs(corpus, _parts_of(corpus, row["turn"])):
            return {"ref": ref, "because": "posted-in-conversation",
                    "conversation": conversation, "turn": row["turn"],
                    "producer": producer}, ""
    return None, "no live Turn in this Conversation carries it"


def reachable(corpus, cv, grant: dict, ref: str) -> tuple[dict | None, str]:
    """Whether THIS execution may read `ref`, and why -- what the door checks.

    `(reason, "")` when it may, `(None, why_not)` when it may not. The reason
    is recorded on the SUPPLIED act, so the record says why bytes went where.
    """
    from mentis.worker import TRANSIENT_SCOPE
    if grant.get("scope") == TRANSIENT_SCOPE:
        return quick_ask_reach(corpus, cv, ref)
    acquired = acquired_reach(corpus, ref)
    if acquired is not None:
        return acquired
    for w in available(corpus, cv, grant):
        if w["ref"] == ref:
            return w, ""
    exp = grant.get("expectation")
    reach = reach_of(cv, exp)
    if reach["reach"] != REACH_CONVERSATION:
        return None, (f"it was not offered to this execution, and "
                      f"{reach['because']}")
    here = reach["conversation"]
    if grant.get("conversation") and grant["conversation"] != here:
        return None, "the grant and its request name different Conversations"
    got, why_not = in_conversation(corpus, cv, here, ref, reader=exp)
    if got is None:
        return None, f"it was not offered to this execution, and {why_not}"
    got["reach"] = reach["because"]
    return got, ""


# -- what a Quick Ask may REACH ------------------------------------------------
#
# BY OWNER DECISION (opr-9fa00d2183a9): "Quick Ask can quote acquired files and
# held artifacts. Its reads stay unrecorded, as all Quick Ask reads are." A
# Quick Ask carries no request, so it has nothing OFFERED and no Conversation
# or lineage to reach through, and `available`/`granted` have nothing to say
# about it. Its reach is stated on its own instead:
#
#   * any artifact the corpus holds -- bytes that crossed one of the two
#     artifact doors (RETURNED, SUBMITTED), in any Conversation.
#   * an acquired IMAGE (`acquired_reach`, below), exactly as a dispatched
#     agent reaches one. Any other Bulk Source acquisition is read with
#     `read_source`, bounded.
#   * EXCEPT what was returned under restricted work. A restriction keeps a
#     work's returns to its own line, and a Quick Ask is on nobody's line, so
#     no exemption applies to it.
#
# DELETED MATERIAL STAYS REACHABLE, AND IS SAID TO BE (owner ruling on
# opr-b234b23b6ba5: "Quick Ask/Scratch may read material from deleted Turns
# and Conversations, for completeness. Whenever deleted material was included
# it must be very clearly marked, whether or not the answer used it."). So
# reach is unchanged, and `deleted_from` says, from the record, when what
# this serves came in on a Turn or Conversation that has since been deleted;
# the door marks the answer with it (`mentis.worker._deleted_marking`).
# Dispatched agents are unchanged: `in_conversation` refuses them it.
#
# Missing, corrupt and purged answer exactly as they do for any reader. And
# nothing is recorded: there is no SUPPLIED act for a Quick Ask (see
# `mentis.worker._operate`).


def quick_ask_reach(corpus, cv, ref) -> tuple[dict | None, str]:
    """Whether a Quick Ask may read `ref`: `(reason, "")` or `(None, why_not)`."""
    acquired = acquired_reach(corpus, ref)
    if acquired is not None:
        return acquired
    st = describe(corpus, ref, verify=False)["state"]
    if st not in ("held", "held-but-missing", "held-but-corrupt"):
        return None, f"it is {st}"
    made = producing_act(corpus, cv, ref)
    if made is None or made["act"] not in (RETURNED, SUBMITTED):
        return None, ("it is not an artifact returned by a run or attached "
                      "by a person")
    if made["act"] == RETURNED and made.get("caused_by"):
        barred = restriction_of(cv, made["caused_by"])
        if barred:
            return None, (f"it was returned under restricted work "
                          f"({barred})")
    return {"ref": ref, "because": "held-unrestricted",
            "producer": {"act": made["id"], "kind": made["act"]}}, ""


def _deletion(corpus, ref) -> dict | None:
    """`{what, ref, when, by}` for an entry that now reads as deleted."""
    from mentis.conversation.versions import presented
    got = corpus.read([ref]) if ref else []
    d = presented(corpus, got[0]).get("deleted") if got else None
    if not d:
        return None
    kind = (got[0].get("definition") or {}).get("name")
    return {"what": {"contribution": "turn"}.get(kind, kind or "entry"),
            "ref": ref, "when": d.get("at"), "by": d.get("by")}


def deleted_from(corpus, cv, ref) -> dict | None:
    """The deleted Turn or Conversation these bytes came in on, or None.

    Read off the record the way `in_conversation` reads reach: the
    Conversation the producing act was recorded in, then the Turns that
    carried it -- the attaching Turn, or for a return the asking Turn and the
    result Turns, deleted only when every one of them is."""
    made = producing_act(corpus, cv, ref)
    if made is None or made["act"] not in (RETURNED, SUBMITTED):
        return None
    gone = _deletion(corpus, made.get("conversation"))
    if gone:
        return gone
    carriers = [made.get("turn")]
    if made["act"] == RETURNED:
        carriers += _result_turns(cv, made)
    carriers = [t for t in dict.fromkeys(carriers) if t]
    if carriers and not any(_live(corpus, t) for t in carriers):
        return _deletion(corpus, carriers[0])
    return None


# -- acquired images: what `read_artifact` reaches of a collection -------------
#
# SOURCES B, B1. A Quick Ask about D&D Knowledge found the images and could
# neither look at them nor show them: `read_source` pages bytes as base64,
# which no model looks at, and `read_artifact` refused anything that had not
# crossed one of the two artifact doors. An acquired image is held bytes like
# any other, so `read_artifact` now serves it -- shown to the model, as every
# image it serves is.
#
# REACH IS EXACTLY `read_source`'s, NOT WIDER AND NOT NARROWER. The source
# reads admit every holder of a worker grant over every acquired collection
# (`mentis.sources.reading`, "THE SANCTIONED SOURCE CAPABILITY"), and a Quick
# Ask holds them by owner decision (opr-9fa00d2183a9). So any grant reaches an
# acquired image, with the reason ACQUIRED_SOURCE, which the SUPPLIED act of a
# dispatched run records; a Quick Ask's read is unrecorded, as all of its are.
#
# ONLY IMAGES, judged by the bytes' signature as the serve route judges them,
# never by the file name or the recorded payload type. Text, PDFs and the rest
# keep their bounded, paged path through `read_source`, and are refused here
# with a pointer to it. Nothing here reads the bound folder.

ACQUIRED_SOURCE = "acquired-source"


def _head(corpus, digest, n=16) -> bytes | None:
    try:
        with open(held.path(corpus.root, digest), "rb") as fh:
            return fh.read(n)
    except (OSError, ValueError):
        return None


def sniffed(corpus, digest) -> dict | None:
    """What held bytes are, by their own signature, without reading them
    whole: `{content_type, view}`, or None when no file is there. For an
    interface deciding whether to draw a picture; serving still verifies."""
    head = _head(corpus, digest or "")
    if head is None:
        return None
    ctype = _signature(head)
    if ctype is None:
        return {"content_type": None, "view": "other"}
    return {"content_type": ctype,
            "view": "pdf" if ctype == "application/pdf" else "image"}


def acquired_reach(corpus, ref) -> tuple[dict | None, str] | None:
    """None when `ref` is not a Bulk Source acquisition, so the ordinary
    rules decide. Otherwise `(reason, "")` for an acquired image, or
    `(None, why_not)`."""
    from mentis.sources import Refused, declarations, observation, reading
    try:
        e = reading._bulk_admission(corpus, ref)
    except Refused:
        return None
    o = observation(e)
    if o.get("state") != "present" or e["body"].get("content") != "held":
        return None, (f"it records {o.get('object')!r} as {o.get('state')}; "
                      "there are no bytes for it")
    d = describe(corpus, ref, verify=False)
    if d["state"] == "purged":
        return None, "it is purged"
    head = _head(corpus, d.get("digest") or "")
    ctype = _signature(head) if head is not None else None
    if head is not None and (ctype is None or ctype == "application/pdf"):
        return None, (f"it is acquired material that is not an image "
                      f"({o.get('object')!r}); read_artifact serves acquired "
                      f"images only. Read it with read_source, which pages "
                      f"its exact bytes and cites them")
    col = o.get("collection")
    decl = next((x for x in declarations(corpus) if x["collection"] == col),
                None)
    return {"ref": ref, "because": ACQUIRED_SOURCE, "collection": col,
            "collection_name": decl["name"] if decl else None,
            "key": o.get("object"),
            "reach": "an acquired image: read_artifact reaches it wherever "
                     "read_source would serve it"}, ""


# -- ending possession ---------------------------------------------------------

def purge(corpus, cv, ref: str, *, by, because: str,
          including_shared: bool = False, written_by=None) -> dict:
    """The owner ends Mentis's possession of an artifact's bytes.

    AS DECIDED (ent-def069ccdcc7): an act is appended, and the original
    Admission, its production, every Turn that names it and every earlier
    delivery are left exactly as they were. Afterwards the artifact reads as
    `purged` -- not held, absent, unknown, missing or corrupt. A snapshot taken
    afterwards does not contain the bytes. It does NOT reach copies in earlier
    snapshots or backups, and it is not secure erasure.

    SHARED BYTES ARE NOT PURGED BY ACCIDENT. Identical bytes are stored once,
    so another Admission may hold the same blob. Purging one does not silently
    take the bytes from the others: it is refused, naming them, unless
    `including_shared`, in which case each is purged with its own act.

    OWNER-ONLY BY WHERE IT IS REACHABLE: no worker operation calls this. That
    is a boundary on what Mentis hands out, not a defence against code running
    as the owner.
    """
    d = describe(corpus, ref, verify=False)
    if d["state"] == "purged":
        # COMPLETABLE, AND IDEMPOTENT. The record already says purged; a
        # crash before the delete left the bytes. Finish it -- unless an
        # Admission that is still held names the same bytes, which is a later
        # crossing's possession, not this one's. No second act.
        removed = False
        live = _live_digests(corpus)
        if d["bytes_remain"] and not live & {d["digest"]}:
            removed = held.remove(corpus.root, d["digest"])
        gone = _forget_extractions(corpus, d.get("digest"), live)
        return {"ref": ref, "state": "purged", "already": True,
                "purged_by": d["purged_by"], "bytes_removed": removed,
                "extractions_removed": gone}
    if d["state"] not in ("held", "held-but-missing", "held-but-corrupt"):
        raise ValueError(f"{ref!r} is {d['state']}; there is no possession "
                         "to end")
    if not (because or "").strip():
        raise ValueError("a purge says why")
    digest = d["digest"]
    sharing = [a for a in _held_admissions(corpus)
               if a["digest"] == digest and a["ref"] != ref
               and not _purges(corpus, a["ref"])]
    if sharing and not including_shared:
        raise ValueError(
            f"the bytes behind {ref!r} are also held for "
            f"{[a['ref'] for a in sharing]}; purging would take them from "
            "those too. Purge with including_shared to end all of them.")
    targets = [ref] + [a["ref"] for a in sharing]
    acts = []
    # The record first, then the bytes. A crash in between leaves `purged`
    # with bytes_remain, which the sweep reports and purging again finishes
    # -- never bytes gone with nothing saying why.
    with corpus.atomic():
        for t in targets:
            aid = cv.record_act(actor=by, act=PURGE, about=[t],
                                because=because,
                                detail={"digest": digest,
                                        "shared_with": [x for x in targets
                                                        if x != t]})
            corpus.write(body={"reason": because}, attributed_to=by,
                         written_by=written_by,
                         link={"from": aid, "to": t, "relation": PURGED})
            acts.append(aid)
    removed = held.remove(corpus.root, digest)
    gone = _forget_extractions(corpus, digest)
    return {"ref": ref, "state": "purged", "purged": targets, "acts": acts,
            "bytes_removed": removed, "extractions_removed": gone,
            "note": "possession ended. Earlier snapshots, backups and any "
                    "copy outside this corpus are untouched, and this is not "
                    "secure erasure."}


def _forget_extractions(corpus, digest, live=None) -> bool:
    """EXTRACTIONS GO WITH THE LAST POSSESSION OF THEIR BYTES (Sources C,
    C2). Derived from the bytes, beside the corpus: once no held Admission
    that is not purged names the digest, every extraction under it is
    deleted. While one still does, they stay -- and stay readable only
    through that Admission, since every source read asks its own purge
    state first."""
    if not digest:
        return False
    live = _live_digests(corpus) if live is None else live
    if digest in live:
        return False
    from mentis.sources.extract import store
    return store.forget(corpus.root, digest)


# -- integrity ------------------------------------------------------------------

def _held_admissions(corpus) -> list[dict]:
    out = []
    for e in corpus.all_entries():
        if e["family"] != "admission" or e["body"].get("content") != "held":
            continue
        out.append({"ref": e["id"],
                    "digest": held.digest_of(e["body"].get("locator"))})
    return out


def _live_digests(corpus) -> set:
    """The digests some held Admission that is NOT purged names."""
    return {a["digest"] for a in _held_admissions(corpus)
            if not _purges(corpus, a["ref"])}


def sweep(corpus) -> dict:
    """Every held artifact, checked against the bytes. Reports; changes nothing.

      held / held-but-missing / held-but-corrupt / purged   per Admission
      purged_bytes_remain   purged, but a blob no live Admission needs is
                            still there (a purge interrupted before its delete)
      unnamed_blobs         bytes nothing in the record names
      incomplete_writes     writes that never finished

    `ok` is true only when nothing but `held` and cleanly purged was found.
    """
    admissions = _held_admissions(corpus)
    by_state: dict[str, list[str]] = {s: [] for s in (
        "held", "held-but-missing", "held-but-corrupt", "purged")}
    live_digests, purged_digests = set(), set()
    for a in admissions:
        d = describe(corpus, a["ref"], verify=True)
        by_state[d["state"]].append(a["ref"])
        (purged_digests if d["state"] == "purged" else live_digests).add(
            a["digest"])
    on_disk = set(held.blobs(corpus.root))
    remain = sorted((purged_digests - live_digests) & on_disk)
    named = live_digests | purged_digests
    out = {"admissions": len(admissions),
           **{k.replace("-", "_"): v for k, v in by_state.items()},
           "purged_bytes_remain": remain,
           "unnamed_blobs": sorted(on_disk - named),
           "incomplete_writes": held.incoming(corpus.root)}
    out["ok"] = not (out["held_but_missing"] or out["held_but_corrupt"]
                     or remain)
    return out


def _main(argv) -> int:
    """`python -m mentis.artifacts sweep <corpus> [--discard-unnamed-older-than S]`
    `python -m mentis.artifacts purge <corpus> <ref> --by <participant>
        --because <why> [--including-shared]`

    The owner's two tools. Neither is reachable by a worker.
    """
    import json
    import mentis.api as api
    if len(argv) < 2 or argv[0] not in ("sweep", "purge"):
        print(_main.__doc__)
        return 2
    corpus = api.open_corpus(argv[1], access="write")
    if argv[0] == "sweep":
        out = sweep(corpus)
        if "--discard-unnamed-older-than" in argv:
            secs = float(argv[argv.index("--discard-unnamed-older-than") + 1])
            out["discarded_unnamed"] = discard_unnamed(corpus,
                                                       older_than_s=secs)
        print(json.dumps(out, indent=1))
        return 0 if out["ok"] else 1
    rest = argv[2:]
    if not rest:
        print(_main.__doc__)
        return 2
    ref, opts = rest[0], {}
    i = 1
    while i < len(rest):
        if rest[i] == "--including-shared":
            opts["including_shared"] = True
            i += 1
        elif rest[i] in ("--by", "--because") and i + 1 < len(rest):
            opts[rest[i][2:]] = rest[i + 1]
            i += 2
        else:
            print(_main.__doc__)
            return 2
    if not opts.get("by") or not opts.get("because"):
        print("a purge needs --by <participant> and --because <why>")
        return 2
    cv = api.brain(corpus).conversations
    print(json.dumps(purge(corpus, cv, ref, by=opts["by"],
                           because=opts["because"],
                           including_shared=opts.get("including_shared",
                                                     False)), indent=1))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
