"""Fluid Latest: the newest conversation activity, replies included.

  GET /fluid/api/latest                    the newest posts, every Conversation
  GET /fluid/api/latest?conversation=<id>  the newest posts at home in one
  GET /fluid/api/latest?limit=<n>          how many (10 by default, 50 at most)

THE OWNER'S QUESTION (2026-10): "Provide a clear way in Fluid to reach the
latest conversation activity, including a new reply to an older post, and
open that exact reply." A Conversation's page is ordered by thread, so a new
reply under an old post is drawn far up the page; the Stream lists posts but
not which thread each one is in. This answers both in one list: each of the
newest posts with where it lives, what it answers, and the top of its thread
(`root`) -- what a client opens so the thread is drawn with that exact reply
as the post read.

NEWEST BY RECORD POSITION. Posts are appended in the order they are recorded,
so the newest are the last rows of the record: the page is read walking the
primary key down from the end, stopping at `limit` posts, as the Stream's page
is (`store.stream_page`) -- never a sort of every post. Filtered to one
Conversation it is read through `idx_entry_link_to` from that Conversation's
home links. Each row's parent and home are read through `idx_entry_link_from`,
and its thread's top by following its first `replies-to` link up (first link
wins, as `read._ancestors` reads the chain), all in that SAME statement. So
the page is ONE statement; what is said of its posts -- current words, names,
numbers -- is a few batched reads over at most `limit` posts. (Leaving out
agent work, below, reads a few such pages, each one statement.)

AGENT WORK IS LEFT OUT BY DEFAULT (owner, 2026-10: "Apply the existing
agent-chatter filtering to Latest as well. Preserve the exceptions for
anything addressed to me, answering me, or waiting on me, and retain the
control to reveal hidden work posts."). Which posts are agent work is
`agent_work.classify`'s answer -- its never-hidden rules come first and are
not restated here. The page is read in chunks (`CHUNK` x limit candidates,
at least `CHUNK_MIN`), each classified as one batch, until `limit` posts are
kept, `ROUNDS` chunks were read, or `SCAN_MAX` candidates were: so the list
fills where it can and the cost stays bounded. `scanned` says how many
candidates were read, `hidden` how many of them were left out above the last
post listed. `?agent_work=1` keeps them, each saying its `agent_work`
{kind, why}; `agent_work_count` says how many of the items are.

READ-ONLY. Nothing here writes, and nothing is kept server-side about what a
reader has seen: "new since you looked" is the browser's own marker.
"""
from __future__ import annotations

from mentis.conversation import CONTRIBUTION, IN_CONVERSATION, REPLIES_TO
from mentis.conversation.versions import flow_text

from . import read as _read

#: The page, by default and at most.
LIMIT, LIMIT_MAX = 10, 50
#: The most characters of an excerpt.
EXCERPT = 160
#: Candidates read a chunk: this many times the limit, at least CHUNK_MIN;
#: at most ROUNDS chunks and SCAN_MAX candidates in all.
CHUNK, CHUNK_MIN, ROUNDS, SCAN_MAX = 4, 40, 4, 400
#: Before every seq: the whole record.
_END = 2 ** 62
#: How far a reply's chain is followed up to the top of its thread.
DEPTH = 64

_PAGE = """
WITH RECURSIVE page(id, seq, at, author, home, parent) AS (
    SELECT e.id, e.seq, e.recorded_at, e.attributed_to,
           (SELECT h.link_to FROM entry h WHERE h.link_from = e.id
              AND h.link_relation = :home ORDER BY h.seq LIMIT 1),
           (SELECT r.link_to FROM entry r WHERE r.link_from = e.id
              AND r.link_relation = :replies ORDER BY r.seq LIMIT 1)
    FROM {source}
    WHERE +e.def_name = :kind AND +e.family = 'entry'
      AND e.link_relation IS NULL AND e.seq < :before {where}
    ORDER BY e.seq DESC
    LIMIT :limit),
up(start, node, depth) AS (
    SELECT id, parent, 1 FROM page WHERE parent IS NOT NULL
    UNION
    SELECT up.start,
           (SELECT r.link_to FROM entry r WHERE r.link_from = up.node
              AND r.link_relation = :replies ORDER BY r.seq LIMIT 1),
           up.depth + 1
    FROM up WHERE up.node IS NOT NULL AND up.depth < :depth),
top(start, root, depth) AS (
    -- the farthest node each chain reached: the bare column is the one on
    -- the MAX row, as SQLite answers it
    SELECT start, node, MAX(depth) FROM up
    WHERE node IS NOT NULL GROUP BY start)
SELECT p.id, p.seq, p.at, p.author, p.home, p.parent, t.root
FROM page p LEFT JOIN top t ON t.start = p.id
ORDER BY p.seq DESC"""

#: Every Conversation: the primary key walked down from the end, keeping a
#: post with a home (a later version of a post has none and is never a row).
_EVERYWHERE = _PAGE.format(
    source="entry e",
    where="AND EXISTS (SELECT 1 FROM entry h WHERE h.link_from = e.id "
          "AND h.link_relation = :home)")
#: One Conversation: its home links, through `idx_entry_link_to`.
_ONE = _PAGE.format(
    source="entry l JOIN entry e ON e.id = l.link_from",
    where="AND l.link_to = :conversation AND l.link_relation = :home "
          "AND l.seq = (SELECT MIN(x.seq) FROM entry x WHERE x.link_from = "
          "e.id AND x.link_relation = :home)")


def page_rows(corpus, *, conversation=None, limit=LIMIT,
              before=None) -> list[tuple]:
    """The newest posts, newest first: (id, seq, recorded_at, author, home,
    parent, root). `root` is None for a post that answers nothing. `before`:
    only posts recorded before that seq. ONE statement."""
    args = {"kind": CONTRIBUTION, "home": IN_CONVERSATION,
            "replies": REPLIES_TO, "limit": max(1, int(limit)),
            "depth": DEPTH, "before": _END if before is None else before}
    sql = _EVERYWHERE
    if conversation is not None:
        args["conversation"] = conversation
        sql = _ONE
    return [tuple(r) for r in corpus._store._rows(sql, args)]


def _excerpt(entry) -> str:
    text = " ".join(flow_text((entry.get("body") or {}).get("parts")).split())
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1].rstrip() + "…"


def _sifted(corpus, cv, *, conversation, limit, keep_work):
    """The rows listed, what is agent work among them, how many candidates
    were read and how many were left out. Without `cv` nothing is
    classified: the newest `limit`, one statement."""
    if cv is None:
        return page_rows(corpus, conversation=conversation,
                         limit=limit), {}, None, 0
    from mentis.conversation import agent_work
    from mentis.operational.work_overview import owner_of
    owner = owner_of(cv)
    if keep_work:
        rows = page_rows(corpus, conversation=conversation, limit=limit)
        work = agent_work.classify(cv, [r[0] for r in rows], owner)
        return rows, work, len(rows), 0
    chunk = min(SCAN_MAX, max(CHUNK_MIN, limit * CHUNK))
    kept, hidden, scanned, before = [], 0, 0, None
    for _ in range(ROUNDS):
        want = min(chunk, SCAN_MAX - scanned)
        if want <= 0:
            break
        rows = page_rows(corpus, conversation=conversation, limit=want,
                         before=before)
        if not rows:
            break
        work = agent_work.classify(cv, [r[0] for r in rows], owner)
        for r in rows:
            scanned += 1
            if work.get(r[0]):
                hidden += 1
                continue
            kept.append(r)
            if len(kept) >= limit:
                break
        if len(kept) >= limit or len(rows) < want:
            break
        before = rows[-1][1]
    return kept, {}, scanned, hidden


def latest(corpus, *, conversation=None, limit=LIMIT, cv=None,
           agent_work=False) -> dict:
    """`GET /fluid/api/latest`: the newest posts, replies included, each with
    where it lives, what it answers and the top of its thread. With `cv`,
    agent work is left out unless `agent_work` asks for it."""
    if conversation is not None:
        got = corpus.read([conversation])
        if not got or not _read._is_conversation(got[0]):
            raise _read.BadRequest(f"not a conversation: {conversation!r}")
    rows, work, scanned, hidden = _sifted(
        corpus, cv, conversation=conversation, limit=limit,
        keep_work=agent_work)
    ids = [r[0] for r in rows]
    entries = {e["id"]: e for e in corpus.read(ids)} if ids else {}
    now = _read._now_reads(corpus, list(entries.values())) if entries else {}
    homes = {r[0]: r[4] for r in rows if r[4]}
    parents = {r[0]: r[5] for r in rows if r[5]}
    parent_homes = _read.homes_of(corpus, list(set(parents.values()))) \
        if parents else {}
    numbers = _read.numbers_of(corpus, {**parent_homes, **homes})
    names = _read._names(corpus, list(homes.values())
                         + [r[3] for r in rows]) if rows else {}
    items = []
    for pid, _seq, at, author, home, parent, root in rows:
        cur = now.get(pid) or entries.get(pid) or {}
        deleted = bool(cur.get("deleted"))
        items.append({
            "id": pid,
            "conversation": home,
            "conversation_name": names.get(home, home),
            "number": numbers.get(pid),
            "reply_to": parent,
            "reply_to_number": numbers.get(parent) if parent else None,
            "root": root or pid,
            "author": author,
            "author_alias": names.get(author, author),
            "at": at,
            "excerpt": None if deleted else _excerpt(cur),
            "deleted": deleted,
            **({"agent_work": _why(work.get(pid))} if agent_work else {}),
        })
    out = {"key": "latest" if conversation is None
           else f"latest:{conversation}",
           "conversation": conversation, "items": items, "limit": limit}
    if cv is not None:
        out.update(agent_work=bool(agent_work), scanned=scanned,
                   hidden=hidden,
                   agent_work_count=sum(1 for i in items
                                        if i.get("agent_work")))
    return out


def _why(k):
    return {"kind": k["kind"], "why": k["why"]} if k else None
