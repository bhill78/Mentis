"""Literal post search bounded to one Fluid Conversation.

The result page contains record references and excerpts only.  It never
writes, and its candidate set comes from ``read.conversation_scope`` -- the
same visibility rule as ``collections/conversation``.
"""
from __future__ import annotations

import re

from mentis.conversation import CONTRIBUTION, IN_CONVERSATION, REPLIES_TO
from mentis.conversation.versions import flow_text, presented

from . import read

QUERY_MAX = 500
SNIPPET = 240


def _query(raw: str | None) -> str:
    q = (raw or "").strip()
    if not q:
        raise read.BadRequest("name what to search for: ?q=<text>")
    if len(q) > QUERY_MAX:
        raise read.BadRequest(
            f"search text is at most {QUERY_MAX} characters, not {len(q)}")
    return q


def _snippet(text: str, match: re.Match[str]) -> str:
    """A compact excerpt around a literal match, without breaking words."""
    clean = " ".join(text.split())
    found = re.search(re.escape(match.group(0)), clean, re.IGNORECASE)
    if found is None or len(clean) <= SNIPPET:
        return clean
    room = SNIPPET - (found.end() - found.start())
    start = max(0, found.start() - room // 2)
    end = min(len(clean), found.end() + room - room // 2)
    if start:
        cut = clean.find(" ", start)
        start = cut + 1 if cut >= 0 and cut < found.start() else start
    if end < len(clean):
        cut = clean.rfind(" ", found.end(), end)
        end = cut if cut > found.end() else end
    return ("..." if start else "") + clean[start:end] + ("..." if end < len(clean) else "")


def conversation(corpus, cid: str, q: str | None, *, before: str | None,
                 limit: int) -> dict:
    """Search visible posts newest-first, paging older with ``before``.

    ``before`` accepts the same opaque position (or post id) as the existing
    Conversation collection.  The caller can pass the last returned hit's
    ``post`` to request the next page.
    """
    needle = _query(q)
    also = list(read.conversation_scope(corpus, cid))
    before_key = read._page_key(corpus, before)
    hits = []
    pattern = re.compile(re.escape(needle), re.IGNORECASE)

    while len(hits) <= limit:
        page = corpus.members_page(
            cid, home=IN_CONVERSATION, kind=CONTRIBUTION,
            replies=REPLIES_TO, also=also, roots=False,
            before=before_key, limit=read.PAGE_MAX)
        rows = page["rows"]
        if not rows:
            break
        entries = {e["id"]: e for e in corpus.read([r[0] for r in rows])}
        for pid, _seq, at, number, _parent, _pos in reversed(rows):
            entry = entries.get(pid)
            if entry is None:
                continue
            current = presented(corpus, entry)
            text = flow_text((current.get("body") or {}).get("parts"))
            match = pattern.search(text)
            if match is not None:
                hits.append({"post": pid, "number": number,
                             "snippet": _snippet(text, match), "at": at})
                if len(hits) > limit:
                    break
        if len(hits) > limit or len(rows) < read.PAGE_MAX:
            break
        before_key = (rows[0][2], rows[0][1])

    return {"hits": hits[:limit], "more": len(hits) > limit}
