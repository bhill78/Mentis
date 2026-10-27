"""The two ways anything crosses from a Scratch into the record.

  Sidebar               CHOSEN PARTS, AS CONTEXT FOR DELIBERATE WORK. The
                        owner picks one or several messages, writes what they
                        want done or discussed, and it is posted as ONE
                        ordinary Turn through the ordinary Turn route -- a
                        request like any other, owed, carried and governed like
                        any other. The Scratch is untouched and goes on.
  Keep as Conversation  THE WHOLE EXCHANGE, AS IT HAPPENED, ASKING NOBODY
                        ANYTHING. Each message its own Turn, each answer
                        attributed to whoever actually answered it. The
                        Scratch ends.

NEITHER MINTS A KIND OR CONFERS STANDING. What crosses is a Conversation and
its Turns; from there the record's ordinary capture and learning apply. Neither
decides what the material IS.

SIDEBAR, IN DETAIL. `sidebar_parts` is pure: the same inputs give the same
parts, so the preview the owner reads before sending IS what is sent -- the
route calls it once to show and once to send. What it carries:

  * the owner's own words, exactly as written, first;
  * each chosen message, quoted and said for what it is -- the owner's question
    or Mentis's answer, by whom and when -- in the order it was said, whatever
    order it was chosen in. An `excerpt` narrows a message to a passage of it
    and must be found in it word for word (its Markdown formatting aside,
    since it is selected from the rendered answer): a quote attributed to
    Mentis is never words Mentis did not say;
  * structured `turn` references: the items the Scratch was asked about that
    the owner kept ticked, and any Turn a chosen message itself referenced.

Nothing unchosen crosses, and nothing in it names the Scratch: a Scratch can be
deleted at any moment and the request must mean the same afterwards.

KEEP, IN DETAIL. THE OWNER'S EXPLICIT ACT, AND RECORD-ONLY. Keep writes the Scratch exchange as
an ordinary Conversation through the ordinary Conversation model -- one Turn per
message, in order, each answer replying to its question -- and then deletes the
Scratch, all in ONE transaction on the Brain's one database. It replays no
question, dispatches nobody, records no expectation and establishes nothing.

WHAT THE KEPT CONVERSATION CARRIES, so it means the same after the Scratch rows
are gone (they are gone at once):

  * every message's own content parts, unchanged -- Markdown, renderer block
    source, structured references -- so nothing is flattened into a blob;
  * who said each thing: the owner's questions are the owner's; each answer is
    attributed to the Participant that actually answered it, as the Scratch
    observed at the time. `written_by` says who wrote it into the record now;
  * where it was asked from, as STRUCTURED `turn` references in a first Turn,
    so a later run asked in this Conversation is handed what those Turns hold
    by the existing one-hop rule (`artifacts.referenced_by_request`);
  * one `scratch-kept` act naming every Turn written, each message's original
    time and its observed provenance. The Scratch id is in it as history only:
    nothing reads it back except a retried Keep looking for its own result.

WHAT IT DOES NOT CARRY: renderer interaction state (checked boxes, edited form
values). Those live in the renderer's tab memory and are not persisted; the
block's SOURCE is kept and renders as it was written. The interface says so
before the owner confirms.
"""

from __future__ import annotations

import re
import time

from mentis.scratch_store import ScratchGone, ScratchRefused, _text_of

KEPT = "scratch-kept"


def _already_kept(cv, sid, owner) -> dict | None:
    """A retried Keep -- the first one committed and its response was lost --
    finds the Conversation it made instead of making a second."""
    for a in cv.history(act=KEPT, actor=owner, newest_first=True, limit=200):
        if (a.get("detail") or {}).get("scratch") == sid:
            return {"conversation": a["conversation"], "retried": True,
                    "turns": a["about"]}
    return None


def _when(at) -> str:
    return time.strftime("%d %b %Y %H:%M", time.localtime(at)) if at else "?"


def _source_turn(cv, corpus, scratch) -> list | None:
    """The first Turn's parts: where this Scratch was asked from, by reference.

    Only references to Turns the record still holds as live material are
    written as `turn` parts -- a deleted Turn is never new provenance. The
    label the briefing showed is kept as words beside it.
    """
    from mentis.conversation.versions import inert_refusal
    ctx = scratch.get("context") or {}
    refs = []
    # THE ITEM ASKED ABOUT, not everything that was on the page. The whole
    # envelope is kept on the `scratch-kept` act; the first Turn says what
    # started this, which is the one thing a reader of the Conversation needs.
    for r in ctx.get("refs") or ():
        if r.get("role") != "selected":
            continue
        t = r.get("turn")
        if not t or t in (x["ref"] for x in refs):
            continue
        got = corpus.read([t])
        if not got or (got[0].get("definition") or {}).get("name") != \
                "contribution" or inert_refusal(corpus, t):
            continue
        refs.append({"ref": t, "label": r.get("label") or "a Turn"})
    where = ctx.get("label") or ctx.get("surface") or "Mentis"
    at = scratch.get("created_at")
    head = (f"Kept from Scratch. Asked from {where}, at "
            f"{time.strftime('%H:%M', time.localtime(at)) if at else '?'}.")
    if not refs:
        return [{"type": "text", "text": head}]
    parts = [{"type": "text", "text": head + "\n\nIt was about: "}]
    for i, r in enumerate(refs):
        if i:
            parts.append({"type": "text", "text": ", "})
        n = cv.turn_number(r["ref"])
        parts.append({"type": "turn", "ref": r["ref"],
                      "text": f"#{n}" if n else "a Turn"})
        parts.append({"type": "text", "text": f" ({r['label'][:80]})"})
    return parts


_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.M)
_MARKUP = re.compile(r"[*_`~|>#]+")


def _plain(text) -> str:
    """The words, without the Markdown that dresses them. A passage is
    selected from the RENDERED answer -- `**What it is:**` reads as
    `What it is:` -- so it is matched as words, never as formatting."""
    text = _MARKUP.sub("", _BULLET.sub("", _LINK.sub(r"\1", text)))
    return " ".join(text.split())


def _canonical_excerpt(whole, excerpt):
    target = _plain(excerpt)
    if not target:
        return None
    if target == _plain(whole):
        return whole
    chars = [(ch, i, i + 1) for i, ch in enumerate(whole)]
    def remove(pattern, label=False):
        nonlocal chars
        text = "".join(c[0] for c in chars)
        for m in reversed(list(pattern.finditer(text))):
            replacement = chars[m.start(1):m.end(1)] if label else []
            if label and replacement:
                # A selection inside a link carries the canonical whole link,
                # so clipping its label cannot clip or replace its destination.
                replacement = [(ch, chars[m.start()][1], chars[m.end()-1][2])
                               for ch, _, _ in replacement]
            chars[m.start():m.end()] = replacement
    remove(_LINK, True)
    remove(_BULLET)
    remove(_MARKUP)
    normalized = []
    for ch, start, end in chars:
        if ch.isspace():
            if normalized and normalized[-1][0] != ' ':
                normalized.append((' ', start, end))
        else:
            normalized.append((ch, start, end))
    plain = ''.join(c[0] for c in normalized).strip()
    at = plain.find(target)
    if at < 0:
        return None
    return whole[normalized[at][1]:normalized[at + len(target) - 1][2]]


def _quote(m, text) -> str:
    who = ("I asked" if m["role"] == "owner" else
           "Mentis answered" + (f" ({(m['provenance'] or {}).get('alias')})"
                                if (m["provenance"] or {}).get("alias")
                                else ""))
    lines = text.strip().split("\n")
    return f"> {who}, {_when(m['at'])}:\n" + "\n".join("> " + x for x in lines)


def sidebar_parts(scratch, corpus, *, request, carry=(), refs=()) -> dict:
    """The one Turn a Sidebar posts, and what went into it. Writes nothing.

    `carry` is `[{"n": <message>, "excerpt": <optional passage>}]`; `refs` the
    Turn ids, from where the Scratch was asked, the owner kept ticked.
    """
    from mentis.conversation.versions import inert_refusal
    request = (request or "").strip()
    if not request:
        raise ScratchRefused("say what you want done or discussed; the "
                             "chosen context goes with it")
    by_n = {m["n"]: m for m in scratch["messages"]}
    chosen = {}
    for c in carry or ():
        n = c.get("n") if isinstance(c, dict) else c
        m = by_n.get(n)
        if m is None:
            raise ScratchRefused(f"message {n} is not in this Scratch")
        if m["status"] != "done" or not _text_of(m["parts"]).strip():
            raise ScratchRefused(f"message {n} said nothing that can be "
                                 f"carried ({m['status']})")
        whole = _text_of(m["parts"])
        excerpt = (c.get("excerpt") or "").strip() if isinstance(c, dict) \
            else ""
        canonical = _canonical_excerpt(whole, excerpt) if excerpt else whole
        if canonical is None:
            raise ScratchRefused(f"the passage chosen from message {n} is not "
                                 f"in it as written")
        chosen[n] = canonical
    # IN THE ORDER IT WAS SAID, not the order it was ticked.
    quotes = [_quote(by_n[n], chosen[n]) for n in sorted(chosen)]

    where = (scratch.get("context") or {}).get("label") or "Mentis"
    text = request
    if quotes:
        text += (f"\n\n---\nFrom my Scratch (asked from {where}):\n\n"
                 + "\n\n".join(quotes))

    # STRUCTURED REFERENCES: ticked items from where it was asked, then any
    # Turn a chosen message itself named. Only live Turns this Brain holds --
    # a deleted Turn is never new provenance.
    labels = {r["turn"]: r.get("label") or "a Turn"
              for r in (scratch.get("context") or {}).get("refs") or ()
              if r.get("turn")}
    wanted = []
    for t in refs or ():
        if t not in labels:
            raise ScratchRefused(f"{t} is not something this Scratch was "
                                 f"asked about")
        wanted.append((t, labels[t]))
    for n in sorted(chosen):
        for p in by_n[n]["parts"]:
            if p.get("type") == "turn" and p.get("ref"):
                wanted.append((p["ref"], p.get("text") or "a Turn"))
    about, seen = [], set()
    for t, label in wanted:
        if t in seen:
            continue
        got = corpus.read([t])
        if (not got or inert_refusal(corpus, t) or
                (got[0].get("definition") or {}).get("name") != "contribution"):
            raise ScratchRefused(f"referenced Turn {t} is no longer available; refresh the preview")
        seen.add(t)
        about.append({"ref": t, "label": label})

    parts = [{"type": "text", "text": text}]
    if about:
        parts.append({"type": "text", "text": "\n\nAbout: "})
        for i, r in enumerate(about):
            if i:
                parts.append({"type": "text", "text": ", "})
            parts.append({"type": "turn", "ref": r["ref"],
                          "text": r["label"][:60]})
    return {"parts": parts, "text": text, "carried": sorted(chosen),
            "references": about}


def keep(store, cv, corpus, sid, *, by, name=None, written_by=None) -> dict:
    """Write the Scratch as a Conversation and delete it. All or nothing.

    Refused while an answer is still coming: the boundary of what is kept has
    to be clear. Refused for somebody else's Scratch. A retry after a lost
    response returns the same Conversation.
    """
    if not by:
        raise ScratchRefused("keeping needs somebody who keeps it")
    with corpus.atomic():
        try:
            s = store.get(sid)
        except ScratchGone:
            done = _already_kept(cv, sid, by)
            if done:
                return done
            raise
        if s["owner"] != by:
            raise ScratchRefused("this Scratch is somebody else's to keep")
        msgs = s["messages"]
        if any(m["status"] == "pending" for m in msgs):
            raise ScratchRefused("Mentis is still answering; Keep once the "
                                 "answer has arrived")
        if not any(m["role"] == "owner" for m in msgs):
            raise ScratchRefused("there is nothing in this Scratch to keep")
        first_q = next(_text_of(m["parts"]) for m in msgs
                       if m["role"] == "owner").strip()
        title = (name or "").strip() or (first_q.split("\n")[0][:80]
                                         or "Kept Scratch")
        about = f"Kept from Scratch on {_when(time.time())}"
        conv = cv.open_conversation(title, about=about, attributed_to=by,
                                    written_by=written_by)
        cv.join(by, conv, attributed_to=by, written_by=written_by)

        written = []
        head = cv.say(conv, by, _source_turn(cv, corpus, s),
                      written_by=written_by)
        written.append({"turn": head, "n": None, "role": "source"})
        last_question = None
        for m in msgs:
            if m["role"] == "owner":
                t = cv.say(conv, by, m["parts"], written_by=written_by)
                last_question = t
            else:
                if m["status"] != "done" or not m["parts"]:
                    # A failed or interrupted answer said nothing. Saying
                    # that it failed would be a Turn nobody wrote; the act
                    # below records it instead.
                    written.append({"turn": None, "n": m["n"],
                                    "role": "mentis", "status": m["status"],
                                    "at": m["at"],
                                    "provenance": m["provenance"]})
                    continue
                prov = m["provenance"] or {}
                author = prov.get("participant")
                if not author:
                    raise ScratchRefused(
                        f"answer {m['n']} has no observed answerer, so it "
                        f"cannot be attributed truthfully")
                if author not in cv.participants(conv):
                    cv.join(author, conv, attributed_to=by,
                            written_by=written_by)
                t = cv.say(conv, author, m["parts"],
                           replies_to=last_question, written_by=written_by)
            written.append({"turn": t, "n": m["n"], "role": m["role"],
                            "status": m["status"], "at": m["at"],
                            "provenance": m["provenance"]})
        cv.record_act(
            actor=by, act=KEPT, conversation=conv,
            because="the owner kept a Scratch as a Conversation",
            about=[w["turn"] for w in written if w["turn"]],
            detail={"scratch": sid, "asked_from": s["context"],
                    "scratch_started": s["created_at"],
                    "messages": written,
                    "renderer_state": "not carried: interaction state lives "
                                      "in the renderer's tab memory; block "
                                      "source is kept as written"})
        store.dismiss(sid)
    return {"conversation": conv, "name": title, "retried": False,
            "turns": [w["turn"] for w in written if w["turn"]]}
