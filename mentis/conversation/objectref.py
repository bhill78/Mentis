"""An object inside a post, referenced from another post (Fluid final, W4).

THE OWNER'S DECISIONS (2026-10-28, fluid-arrange DROP.md). An object inside a
post -- a chart, a table, a form, an attachment -- is referenceable on its own
WITHOUT BECOMING A BRAIN RECORD. Its identity is its originating post and its
stable object key: the server's own `live:<root>:<key>` address, with
`exact:<version>:<part>:<key>` pinning the version the author saw
(`mentis.fluid.objects`). A post refers to one by carrying a content part:

    {"type": "object", "ref": "<root post id>", "key": "<object key>",
     "exact": "exact:<version>:<part>:<key>", "text": "<what the author sees>",
     "about": {"kind", "title", "home", "home_name", "number", "by"}}

No new Kind, no new link relation and no entry for the object: the part
travels inside an ordinary contribution, so the record stays append-only and
Mark IV reads it as a part it shows by its `text`. `about` is a caption, so
the reference still reads when the original is gone -- never a copy of it.

THREE QUESTIONS ARE ANSWERED HERE, and nothing else:

  * `refusal`        whether a post may carry these parts, asked where every
                     post is written (`posting.post`, the worker's `respond`)
                     before anything is: the post is a contribution that was
                     not deleted, `exact` resolves at that version with the
                     same key, `about` is bounded. Refused in words.
  * `resolve`        what a part names NOW: it resolves (with the current
                     live object), or why it does not. Never a nearby
                     substitute.
  * `for_request`    what an addressed agent is given (the owner's second
                     decision): that one object, from the asking post only,
                     one hop -- a held artifact offered through the existing
                     mechanism (`artifacts.available`), or a Markdown object's
                     extracted source, description and provenance read at
                     `exact`, with `live` for navigation. Unresolved is said
                     in words. It grants nothing: what a run may open is still
                     decided by `artifacts.reachable` and its grant.
"""
from __future__ import annotations

import json

#: The part's type.
PART = "object"
#: The fields a part may carry; anything else is refused, not stored.
FIELDS = ("type", "ref", "key", "exact", "text", "about")
#: The description's fields and their types (`number` may be null).
ABOUT = {"kind": str, "title": str, "home": str, "home_name": str,
         "number": int, "by": str}
#: Bounds: what the author sees inline, each word of `about`, all of `about`.
TEXT_MAX = 300
ABOUT_WORD_MAX = 200
ABOUT_MAX = 1200
#: The longest key a live address can carry (lab_workspaces `MAX_KEY`).
KEY_MAX = 300
#: The most of one object's Markdown an agent is given in its context.
SOURCE_MAX = 20_000
#: Kinds that are read through their artifact, not their Markdown.
_HELD_KINDS = ("media", "figure")


def object_parts(parts) -> list[dict]:
    """The object reference parts among these, in order."""
    return [p for p in parts or () if isinstance(p, dict)
            and p.get("type") == PART]


def live_of(part) -> str:
    return f"live:{part.get('ref')}:{part.get('key')}"


# -- the rule where every post is written ------------------------------------

def _shape(part) -> str | None:
    """What is wrong with the part's shape, in words, or None."""
    extra = sorted(set(part) - set(FIELDS))
    if extra:
        return ("an object reference carries only " + ", ".join(FIELDS)
                + "; it also had " + ", ".join(extra))
    for f in ("ref", "key", "exact"):
        if not isinstance(part.get(f), str) or not part[f].strip():
            return f"an object reference names its {f}"
    if len(part["key"]) > KEY_MAX:
        return f"an object key is at most {KEY_MAX} characters"
    text = part.get("text")
    if not isinstance(text, str) or not text.strip():
        return "an object reference says what the author sees (its text)"
    if len(text) > TEXT_MAX:
        return f"an object reference's text is at most {TEXT_MAX} characters"
    about = part.get("about")
    if not isinstance(about, dict):
        return ("an object reference describes what it names (about: kind, "
                "title, home, home_name, number, by)")
    for k, v in about.items():
        if k not in ABOUT:
            return (f"an object reference's about holds only "
                    f"{', '.join(ABOUT)}; not {k!r}")
        if v is None:
            continue
        want = ABOUT[k]
        if want is int:
            if not isinstance(v, int) or isinstance(v, bool):
                return f"about.{k} is a number"
        elif not isinstance(v, str):
            return f"about.{k} is words"
        elif len(v) > ABOUT_WORD_MAX:
            return f"about.{k} is at most {ABOUT_WORD_MAX} characters"
    if len(json.dumps(about, ensure_ascii=False)) > ABOUT_MAX:
        return (f"an object reference's about is a caption, at most "
                f"{ABOUT_MAX} characters, never a copy of the object")
    return None


def _refused(i, why, **more) -> dict:
    return {"error": why, "field": "parts", "part": i, **more}


def refusal(corpus, parts, *, bundle=None) -> dict | None:
    """Why these parts may not be carried by a new post, or None.

    Asked before anything is written. Every object part is checked: its
    shape, that `ref` is a post (a contribution, named by its own id, not a
    later version) that was not deleted, and that `exact` is an exact
    address of a version of that post naming the same key and resolving
    there. When the server cannot read objects at all (no render engine,
    `objects.extract`), the key cannot be checked here; the structure still
    is, and every reader of the part says, as the server does, that it was
    not extracted -- a reference is never accepted as resolving when it
    demonstrably does not."""
    from mentis.conversation.versions import inert_refusal, CONTRIBUTION
    from mentis.fluid import objects as _objects
    from mentis.fluid import read as _read
    for i, p in enumerate(parts or ()):
        if not isinstance(p, dict) or p.get("type") != PART:
            continue
        why = _shape(p)
        if why:
            return _refused(i, why)
        ref, key, exact = p["ref"], p["key"], p["exact"]
        got = corpus.read([ref])
        if not got:
            return _refused(i, f"the record holds no post {ref}", ref=ref)
        if (got[0].get("definition") or {}).get("name") != CONTRIBUTION:
            return _refused(i, f"{ref} is not a post; an object reference "
                               "names the post the object is in", ref=ref)
        inert = inert_refusal(corpus, ref)
        if inert:
            return _refused(i, "an object reference names a post that was "
                               "deleted, so it is not new provenance: "
                               + inert["error"], ref=ref,
                            deletion=inert.get("deletion"))
        chain = corpus.history(ref)
        if chain and chain[0] != ref:
            return _refused(i, f"{ref} is a later version of the post "
                               f"{chain[0]}; an object reference names the "
                               "post itself", ref=ref, post=chain[0])
        try:
            a = _objects.parse_address(exact)
        except _read.BadRequest as exc:
            return _refused(i, str(exc), exact=exact)
        if a["form"] != "exact":
            return _refused(i, "an object reference pins the version the "
                               "author saw: its exact is an exact: address",
                            exact=exact)
        if a["key"] != key:
            return _refused(i, f"the exact address names the object "
                               f"{a['key']!r}, not {key!r}", exact=exact)
        try:
            seen = _objects.one_object(corpus, exact, bundle=bundle)
        except _objects.Unresolved as exc:
            return _refused(i, "that object does not resolve: "
                               + exc.payload["why"], exact=exact)
        except _read.BadRequest as exc:
            return _refused(i, str(exc), exact=exact)
        if seen["post"] != ref:
            return _refused(i, f"{a['version']} is a version of the post "
                               f"{seen['post']}, not of {ref}", exact=exact)
    return None


# -- what a part names now -----------------------------------------------------

def resolve(corpus, part, *, bundle=None) -> dict:
    """What one part names now: `{"resolves": True, "object", "version",
    "current_version", "home", "home_name", "number"}` for the current
    (live) object, `{"resolves": False, "why"}` when it no longer resolves,
    or `{"resolves": None, "why_not"}` when the server cannot read objects.
    `exact_resolves` says the same of the version the author saw. Never a
    substitute: a key the current version lacks is said, not guessed at."""
    from mentis.fluid import objects as _objects
    from mentis.fluid import read as _read
    ref, key, exact = part.get("ref"), part.get("key"), part.get("exact")
    out = {"ref": ref, "key": key, "exact": exact,
           "live": live_of(part), "text": part.get("text"),
           "about": part.get("about")}
    if not ref or not key:
        return {**out, "resolves": False,
                "why": "the reference names no post and key"}
    try:
        got = _objects.one_object(corpus, out["live"], bundle=bundle)
    except _objects.Unresolved as exc:
        out.update(resolves=False, why=exc.payload["why"],
                   **({"deleted": True} if exc.payload.get("deleted") else {}))
    except _read.BadRequest as exc:
        out.update(resolves=False, why=str(exc))
    else:
        if not got["extracted"]:
            out.update(resolves=None, why_not=got["why_not"])
        else:
            out.update(resolves=True, object=got["object"],
                       **{k: got[k] for k in ("version", "current_version",
                                              "home", "home_name", "number")})
    if isinstance(exact, str) and exact:
        try:
            pinned = _objects.one_object(corpus, exact, bundle=bundle)
            out["exact_resolves"] = (True if pinned["extracted"] else None)
        except (_objects.Unresolved, _read.BadRequest) as exc:
            out["exact_resolves"] = False
            out["exact_why"] = getattr(exc, "payload", {}).get("why") \
                or str(exc)
    return out


def resolve_post(corpus, post, *, bundle=None) -> dict:
    """`GET /fluid/api/object-refs?post=<id>`: each object part of the post
    as it now reads, resolved, in order."""
    from mentis.conversation.versions import presented
    from mentis.fluid import read as _read
    got = corpus.read([post])
    if not got or not _read._is_post(got[0]):
        raise _read.BadRequest(f"not a post: {post!r}")
    now = presented(corpus, got[0])
    parts = (now.get("body") or {}).get("parts") or []
    return {"post": post, "deleted": bool(now.get("deleted")),
            "references": [{"part": i, **resolve(corpus, p, bundle=bundle)}
                           for i, p in enumerate(parts)
                           if isinstance(p, dict) and p.get("type") == PART]}


# -- what an addressed agent is given -----------------------------------------

def _by(corpus, cv, root) -> str | None:
    got = corpus.read([root])
    who = got[0].get("attributed_to") if got else None
    if not who:
        return None
    try:
        return cv.alias(who) or who
    except Exception:                                     # noqa: BLE001
        return who


def _one(corpus, cv, turn, i, part, *, content, bundle) -> dict:
    """One object part of an asking Turn, read for its run."""
    from mentis.fluid import objects as _objects
    from mentis.fluid import read as _read
    about = part.get("about") if isinstance(part.get("about"), dict) else {}
    out = {"turn": turn, "part": i, "ref": part.get("ref"),
           "key": part.get("key"), "exact": part.get("exact"),
           "live": live_of(part), "text": part.get("text"), "about": about}
    if _shape(part):
        return {**out, "resolves": False,
                "why": "the reference is malformed: " + _shape(part)}
    try:
        seen = _objects.one_object(corpus, part["exact"], bundle=bundle)
    except (_objects.Unresolved, _read.BadRequest) as exc:
        return {**out, "resolves": False,
                "why": getattr(exc, "payload", {}).get("why") or str(exc)}
    if seen["post"] != part["ref"]:
        return {**out, "resolves": False,
                "why": f"its exact address is a version of {seen['post']}, "
                       f"not of {part['ref']}"}
    out.update(version=seen["version"], current=seen["current"],
               home=seen.get("home"), home_name=seen.get("home_name"),
               number=seen.get("number"), by=_by(corpus, cv, part["ref"]))
    if not seen["extracted"]:
        return {**out, "resolves": None, "why": seen["why_not"]}
    o = seen["object"]
    out.update(resolves=True, kind=o.get("kind"), type=o.get("type"),
               title=o.get("title"))
    # THE LIVE ADDRESS IS FOR NAVIGATION: whether it still names an object
    # now, said beside what was selected, never read instead of it.
    if not seen["current"]:
        try:
            now = _objects.one_object(corpus, out["live"], bundle=bundle)
            out["live_resolves"] = True if now["extracted"] else None
        except (_objects.Unresolved, _read.BadRequest) as exc:
            out["live_resolves"] = False
            out["live_why"] = getattr(exc, "payload", {}).get("why") or str(exc)
    if o.get("ref") and o.get("kind") in _HELD_KINDS:
        out["artifact"] = o["ref"]
    elif content and "md" in (o.get("formats") or ()):
        md = _objects.one_object(corpus, part["exact"], "md",
                                 bundle=bundle).get("content") or ""
        out["source"] = md[:SOURCE_MAX]
        out["cut"] = len(md) > SOURCE_MAX
    return out


def for_request(corpus, cv, expectation, *, content=True, bundle=None
                ) -> list[dict]:
    """The object references on the Turns that ASKED for this work, each
    read at its `exact` version: what the run is given. One hop -- an object
    part inside the referenced post is not followed -- and only the object
    named, never the originating post's other objects or artifacts."""
    from mentis import artifacts as _artifacts
    out = []
    for t in _artifacts._asking_turns(cv, expectation):
        for i, p in enumerate(_artifacts._parts_of(corpus, t)):
            if isinstance(p, dict) and p.get("type") == PART:
                out.append(_one(corpus, cv, t, i, p, content=content,
                                bundle=bundle))
    return out


def _where_words(c) -> str:
    about = c.get("about") or {}
    home = c.get("home_name") or about.get("home_name") or "its conversation"
    num = c.get("number", about.get("number"))
    by = c.get("by") or about.get("by")
    return (f"from {home}{f' #{num}' if num is not None else ''}"
            f"{f' by {by}' if by else ''}")


def context_lines(refs, offered=()) -> str:
    """What a run is told about the objects its request references, or ''.
    An artifact is named here and offered by reference with the others
    (`offered`, from `artifacts.available`); a Markdown object's source is
    given here."""
    if not refs:
        return ""
    lines = ["", "", "---",
             "OBJECTS THIS REQUEST REFERENCES. Each is one object inside "
             "another post, given as the author selected it (its exact "
             "address); nothing else from that post is given. Its live "
             "address names the object in the post's current version, for "
             "navigation."]
    for c in refs:
        about = c.get("about") or {}
        title = c.get("title") or about.get("title") or c.get("text") \
            or c.get("key")
        kind = c.get("type") or about.get("kind") or "object"
        head = f"- {title!s} ({kind}) {_where_words(c)}"
        ids = f"  exact: {c.get('exact')}  live: {c.get('live')}"
        if c.get("resolves") is False:
            lines += [head, ids,
                      f"  NOT AVAILABLE: {c.get('why')}. Nothing was "
                      "substituted for it."]
            continue
        if c.get("resolves") is None:
            lines += [head, ids,
                      f"  Its content could not be read here: {c.get('why')}."]
            continue
        if c.get("live_resolves") is False:
            ids += f"  (live no longer resolves: {c.get('live_why')})"
        elif not c.get("current", True):
            ids += "  (the post has been edited since; live is its current one)"
        lines += [head, ids]
        if c.get("artifact") and c["artifact"] in offered:
            lines.append(f"  It is the held artifact {c['artifact']}, offered "
                         "below with the artifacts you may read.")
        elif c.get("artifact"):
            lines.append(f"  It is the artifact {c['artifact']}, which is not "
                         "offered to this run: Mentis does not hold its bytes "
                         "now, or this run may not read it.")
        elif c.get("source") is not None:
            cut = (f" (the first {SOURCE_MAX} characters)" if c.get("cut")
                   else "")
            lines += [f"  Its source, as written in that version{cut}:",
                      "  ~~~~", *("  " + x for x in c["source"].split("\n")),
                      "  ~~~~"]
    return "\n".join(lines)
