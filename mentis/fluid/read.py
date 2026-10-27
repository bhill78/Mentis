"""The Fluid read model: entities, collections and the change feed.

FLUID'S OWN, OVER THE DOMAIN AND THE RECORD. Nothing here calls the production
web routes or their view helpers (`_routes`, `_turn_view`, `_threads_of`,
`_scope_units`, `_reply_chain`). It reads the record through the spine seam --
including the bounded reads added for it (`members_page`, `home_numbers`,
`reply_closure`, `heads`) -- and the domain's own definitions and readings
(`mentis.conversation`, `versions.presented`).

THREE SHAPES, KEPT APART (#211):

  entity      one thing as it now reads, by id, in batches: a post, a
              conversation. What a zone draws.
  collection  ordered ids and paging cursors, never bodies: a conversation's
              members, a thread. Where things appear.
  change      what moved after a cursor: entity ids, memberships added or
              ended, collection keys affected. Where to look again.

A POST HAS ONE HOME AND MAY BE INCLUDED ELSEWHERE. Its home is the
Conversation it was written in (`in-conversation`); it is included in others by
`linked-into` links in force. Its number is its home number, the same number
production shows, and it is never renumbered where it is included.
A THREAD IS EVERY REPLY TO A POST, from any Conversation, each marked with its
home -- never only the replies written in one Conversation.
"""
from __future__ import annotations

from mentis.conversation import (CONTRIBUTION, CONVERSATION, IN_CONVERSATION,
                                 LINKED_INTO, PARTICIPATES_IN, REPLIES_TO,
                                 ABOUT_TOPIC, TOPIC_OF)
from mentis.conversation.versions import presented

#: The most entities one batched read may name. Over it is refused whole,
#: never cut short -- the same rule and number as `/api/turns?ids=`.
BATCH = 64
#: A collection page, by default and at most.
PAGE, PAGE_MAX = 30, 200
#: The stream's page by default (F5); at most PAGE_MAX, as every page.
STREAM_PAGE = 50
#: The conversation list, by default and at most.
LIST, LIST_MAX = 100, 500
#: More rows than this of any one stream since a cursor, and the feed says
#: "reread" rather than placing them (the pulse's own bound, web/moved.py).
CAP = 200
#: The acts that say what a run returned with a post (`objects.returned_refs`
#: reads the same two).
RETURNING_ACTS = ("result-returned", "result-recovered")
#: The collection key of every post by record position (F5).
STREAM = "stream"


class BadRequest(ValueError):
    """The question was malformed or too large: answered 400."""


class NotFound(LookupError):
    """The path names nothing Fluid answers: 404."""


# -- cursors ----------------------------------------------------------------
#
# THE CHANGE CURSOR IS OPAQUE TO THE CLIENT and composite underneath: the
# record's own three positions (`advance()`: entry seq, operational count,
# delivery count). A collection's paging cursor is a position in its order:
# (recorded_at, seq) of the member at that edge.

def change_cursor(advance) -> str:
    return "f1.%d.%d.%d" % tuple(advance)


def parse_change_cursor(token: str):
    try:
        tag, a, b, c = token.split(".")
        if tag != "f1":
            raise ValueError
        return (int(a), int(b), int(c))
    except (AttributeError, ValueError):
        raise BadRequest(f"not a Fluid change cursor: {token!r}")


def _page_cursor(at, seq) -> str:
    return f"{at!r}_{seq}"


def _page_key(corpus, raw):
    """A paging position: a cursor this model gave out, or a member's id."""
    if raw is None or raw == "":
        return None
    if raw.startswith(("ent-", "adm-")):
        got = corpus.heads([raw]).get(raw)
        if got is None:
            raise BadRequest(f"no such entry to page from: {raw!r}")
        return (got[6], got[0])
    try:
        at, seq = raw.rsplit("_", 1)
        return (float(at), int(seq))
    except ValueError:
        raise BadRequest(f"not a paging cursor: {raw!r}")


def _window(corpus, before, after, start):
    """(before, after) keys for one page. `start` (`?from=`) is a position
    read FROM, inclusive, oldest first -- `from=start` from the very first -- so a
    client holding several pages can read again exactly what it holds and
    everything newer, page by page (`after`), without being cut to one."""
    if sum(x is not None for x in (before, after, start)) > 1:
        raise BadRequest("page before a position, after it or from it -- one")
    if start is None or start == "":
        return _page_key(corpus, before), _page_key(corpus, after)
    if start == "start":
        return None, (float("-inf"), 0)
    at, seq = _page_key(corpus, start)
    # (at, seq) inclusive is (at, seq - 1) exclusive: seq is a unique integer.
    return None, (at, seq - 1)


def _limit(raw, default, most):
    if raw in (None, ""):
        return default
    try:
        n = int(raw)
    except ValueError:
        raise BadRequest(f"limit is a number, not {raw!r}")
    if n < 1:
        raise BadRequest("limit is at least 1")
    return min(n, most)


def _ids(raw, name="ids") -> list[str]:
    ids = list(dict.fromkeys(t.strip() for t in (raw or "").split(",")
                             if t.strip()))
    if not ids:
        raise BadRequest(f"name what to read: ?{name}=<id>,<id>")
    if len(ids) > BATCH:
        raise BadRequest(f"{len(ids)} asked for in one read; at most {BATCH}"
                         " -- ask again for the rest")
    bad = [i for i in ids if "/" in i]
    if bad:
        raise BadRequest(f"not an id: {bad[0]!r}")
    return ids


# -- shared readings ----------------------------------------------------------

def _in_force(corpus, links) -> list[dict]:
    """The links nothing has ended, in the order given -- the answer
    `Conversations._links_now` gives, asked for a SET of links at once: one
    read for which have a superseding link at all, and `stands` only for
    those (a link that was ended, which is rare)."""
    if not links:
        return []
    sup = corpus.superseding_relation()
    touched = {x["link"]["to"] for x in corpus.links(
        relation=sup, to_any=[x["id"] for x in links])}
    return [x for x in links if x["id"] not in touched
            or not corpus.stands(x["id"])["superseded_by"]]


def _first(links, end="to") -> dict:
    """from -> the first link's `end`, in append order (first link wins, as
    `conversation_of` and the reply chain read it)."""
    out = {}
    for x in links:
        out.setdefault(x["link"]["from"], x["link"][end])
    return out


def homes_of(corpus, ids) -> dict:
    """post -> its home Conversation (its first `in-conversation` link)."""
    return _first(corpus.links(relation=IN_CONVERSATION, frm_any=list(ids)))


def included_in(corpus, ids) -> dict:
    """post -> [linked-into links in force], oldest first."""
    out = {}
    for x in _in_force(corpus, corpus.links(relation=LINKED_INTO,
                                            frm_any=list(ids))):
        out.setdefault(x["link"]["from"], []).append(x)
    return out


def numbers_of(corpus, homes: dict) -> dict:
    """post -> its home number: one statement per distinct home."""
    by_home = {}
    for pid, home in homes.items():
        by_home.setdefault(home, []).append(pid)
    out = {}
    for home, pids in by_home.items():
        out.update(corpus.home_numbers(home, pids, home=IN_CONVERSATION,
                                       kind=CONTRIBUTION))
    return out


def _names(corpus, ids) -> dict:
    """id -> the name a person reads: a Conversation's CURRENT name (a
    renamed one reads as it now does), a Participant's alias. Anything else
    keeps its id."""
    out = {}
    entries = corpus.read(list(dict.fromkeys(i for i in ids if i)))
    convs = _now_reads(corpus, [e for e in entries if _is_conversation(e)
                                or _is_participant(e)])
    for e in entries:
        body = (convs.get(e["id"]) or e).get("body") or {}
        out[e["id"]] = body.get("name") or body.get("alias") or e["id"]
    return out


def _is_participant(entry) -> bool:
    """A renamed Participant reads under its current alias, as a renamed
    Conversation reads under its current name."""
    return (entry.get("family") == "entry" and not entry.get("link")
            and (entry.get("definition") or {}).get("name") == "participant")


def _is_conversation(entry) -> bool:
    return (entry.get("family") == "entry" and not entry.get("link")
            and (entry.get("definition") or {}).get("name") == CONVERSATION)


def _later_versions(corpus, ids) -> set:
    """Which of these are a later version of another -- a rename's version of
    a Conversation, which is that Conversation and never one of its own."""
    if not ids:
        return set()
    return {x["link"]["from"] for x in corpus.links(
        relation=corpus.superseding_relation(), frm_any=list(ids))}


def _is_post(entry) -> bool:
    d = entry.get("definition") or {}
    return (entry.get("family") == "entry" and not entry.get("link")
            and d.get("name") == CONTRIBUTION)


def _now_reads(corpus, entries) -> dict:
    """id -> the entry as it now reads (`versions.presented`), asking which
    were superseded ONCE for the batch."""
    sup = corpus.superseding_relation()
    touched = {x["link"]["to"] for x in corpus.links(
        relation=sup, to_any=[e["id"] for e in entries])}
    return {e["id"]: (presented(corpus, e) if e["id"] in touched else e)
            for e in entries}


def version_of(entry) -> str:
    """Which version of a post this reading is: the current version's id, or
    the deletion that ended it. Changes exactly when what it says changes."""
    if entry.get("deleted"):
        return entry["deleted"]["record"]
    return (entry.get("revision") or {}).get("current") or entry["id"]


# -- entities -----------------------------------------------------------------

def posts(corpus, ids, cv=None) -> dict:
    """`GET /fluid/api/posts?ids=`: each post as it now reads, in the order
    asked, once each. One that is not a post is `{"id", "error"}` and never
    fails the others.

    With `cv`, each post says whether it is AGENT WORK (`agent_work`:
    `{kind, why, to, to_name}` or None) -- the agent-to-agent chatter a
    conversation folds away by default (`conversation.agent_work`), asked
    for every post of the batch together."""
    entries = {e["id"]: e for e in corpus.read(ids)}
    found = [entries[i] for i in ids if i in entries and _is_post(entries[i])]
    pids = [e["id"] for e in found]
    now = _now_reads(corpus, found)
    homes = homes_of(corpus, pids)
    numbers = numbers_of(corpus, homes)
    included = included_in(corpus, pids)
    parents = _first(corpus.links(relation=REPLIES_TO, frm_any=pids))
    # direct replies, from any Conversation, counted by where each lives
    replies = corpus.links(relation=REPLIES_TO, to_any=pids)
    reply_home = homes_of(corpus, [x["link"]["from"] for x in replies])
    parent_home = homes_of(corpus, [p for p in parents.values()])
    parent_number = numbers_of(corpus, parent_home)
    expectations = {}
    for a in (corpus.operational(turn=pids, act="expectation-recorded")
              if pids else ()):
        expectations.setdefault(a["turn"], []).append(a["id"])
    # THE DECISION FORMS EACH POST CARRIES (forms build P7/P9): asked `on`
    # it, or put on it as a run's answer post -- whose questions name no
    # Turn, so `expectations` above does not hold them. A view draws the
    # form under the post from `GET decisions?post=`.
    forms = {}
    for a in (corpus.operational(turn=pids, act="decision-form")
              if pids else ()):
        forms.setdefault(a["turn"], []).append(a["id"])
    for a in (corpus.operational(turn=pids, act="decision-form-attached")
              if pids else ()):
        if a.get("caused_by"):
            forms.setdefault(a["turn"], []).append(a["caused_by"])
    names = _names(corpus, list(homes.values())
                   + [x["link"]["to"] for xs in included.values() for x in xs]
                   + [e["attributed_to"] for e in found]
                   + list(parent_home.values()))
    work = {}
    if cv is not None and pids:
        from mentis.conversation import agent_work
        from mentis.operational.work_overview import owner_of
        work = agent_work.classify(cv, pids, owner_of(cv))
    counted = {}
    for x in replies:
        if x["link"]["from"] in counted.setdefault(x["link"]["to"], {}):
            continue
        counted[x["link"]["to"]][x["link"]["from"]] = \
            reply_home.get(x["link"]["from"])
    out = []
    for i in ids:
        e = entries.get(i)
        if e is None or not _is_post(e):
            out.append({"id": i, "error": "not a post" if e else
                        "the record holds no such entry"})
            continue
        cur = now[i]
        body = cur.get("body") or {}
        home = homes.get(i)
        kids = counted.get(i, {})
        by_home = {}
        for h in kids.values():
            by_home[h] = by_home.get(h, 0) + 1
        parent = parents.get(i)
        out.append({
            "id": i,
            "version": version_of(cur),
            "versions": (cur.get("revision") or {}).get("versions", 1),
            "author": e["attributed_to"],
            "author_name": names.get(e["attributed_to"], e["attributed_to"]),
            "at": e["recorded_at"],
            "edited_at": (cur.get("revision") or {}).get("edited_at"),
            "deleted": cur.get("deleted"),
            "parts": body.get("parts") or [],
            "addressed_to": body.get("addressed_to") or [],
            "home": home,
            "home_name": names.get(home),
            "number": numbers.get(i),
            "reply_to": parent,
            "reply_to_home": parent_home.get(parent) if parent else None,
            "reply_to_home_name": names.get(parent_home.get(parent))
            if parent else None,
            "reply_to_number": parent_number.get(parent) if parent else None,
            "memberships": ([{"conversation": home, "via": "home"}]
                            if home else []) + [
                {"conversation": x["link"]["to"], "via": "linked",
                 "name": names.get(x["link"]["to"]), "link": x["id"],
                 "by": x["attributed_to"], "at": x["recorded_at"]}
                for x in included.get(i, [])],
            "expectations": expectations.get(i, []),
            "decision_forms": list(dict.fromkeys(forms.get(i, []))),
            "replies": {"count": len(kids), "by_home": by_home},
            **({"agent_work": work.get(i)} if cv is not None else {}),
        })
    return {"posts": out, "limit": BATCH}


def _conversation_rows(corpus, cv, entries, live) -> list[dict]:
    """Each Conversation UNDER ITS CURRENT NAME, and whether that name is
    still provisional (`Conversations.provisional`)."""
    out = []
    now = _now_reads(corpus, entries)
    provisional = cv.provisional([c["id"] for c in entries])
    for c in entries:
        cid = c["id"]
        n, last = corpus.linked_node_tally(IN_CONVERSATION, cid, CONTRIBUTION)
        linked = _in_force(corpus, corpus.links(relation=LINKED_INTO, to=cid))
        body = now[cid].get("body") or {}
        out.append({
            "id": cid, "name": body.get("name"), "about": body.get("about"),
            "provisional": provisional.get(cid, False),
            "created": c["recorded_at"],
            "posts": n, "included": len(linked),
            "participants": len({x["link"]["from"] for x in corpus.links(
                relation=PARTICIPATES_IN, to=cid)}),
            "last_activity": max([t for t in (last, *(x["recorded_at"]
                                                      for x in linked)) if t],
                                 default=None),
            "working": live.get(cid, 0),
        })
    return out


def _live(cv) -> dict:
    out = {}
    for e in cv.active_executions():
        out[e.conversation] = out.get(e.conversation, 0) + 1
    return out


def conversations(corpus, cv, ids) -> dict:
    """`GET /fluid/api/conversations?ids=`: each Conversation's current name
    and member counts. Its home posts and the posts included in it are
    counted apart, as they are numbered apart."""
    entries = {e["id"]: e for e in corpus.read(ids)}
    later = _later_versions(corpus, [i for i in ids if i in entries])
    rows = {r["id"]: r for r in _conversation_rows(
        corpus, cv, [entries[i] for i in ids if i in entries
                     and _is_conversation(entries[i]) and i not in later],
        _live(cv))}
    return {"conversations": [rows.get(i) or {"id": i, "error":
                                              "not a conversation"}
                              for i in ids], "limit": BATCH}


def conversation_list(corpus, cv, limit) -> dict:
    """`GET /fluid/api/conversations?activity=1`: the Conversations, most
    recently active first, with the activity facts the record holds now --
    when something last happened there, how many runs are working there in
    this process, and what in it asks the owner (`needs_you`, F5). Nothing
    unread, nothing inferred.

    BOUNDED BY THE PAGE. The order and the limit are one statement
    (`activity_page`); bodies and facts are read for the returned
    Conversations only, so the statements asked grow with `limit`, never with
    how many Conversations there are. The order reads an inclusion as ended
    when any superseding link points at it; the facts read it as
    `_in_force` does."""
    ids, total = corpus.activity_page(
        CONVERSATION, home=IN_CONVERSATION, member=CONTRIBUTION,
        linked=LINKED_INTO, ends=corpus.superseding_relation(), limit=limit)
    entries = {e["id"]: e for e in corpus.read(ids)} if ids else {}
    rows = _conversation_rows(corpus, cv, [entries[i] for i in ids
                                           if i in entries], _live(cv))
    owed = needs_you_in(cv, [r["id"] for r in rows])
    for r in rows:
        r["needs_you"] = owed.get(r["id"])
    return {"conversations": rows, "total": total, "limit": limit}


def needs_you_in(cv, cids) -> dict:
    """Conversation -> how many open expectations recorded in it ask the
    owner: Home's Needs you rule (`home.needs_you`: the current carrier is
    the owner, `Conversations.expectations(of=)`'s rule, and nobody has
    answered), asked of these Conversations' expectations only. None for
    each where the record names no owner -- unknown, never a false zero."""
    from mentis.operational.work_overview import owner_of
    if not cids:
        return {}
    owner = owner_of(cv)
    if owner is None:
        return {c: None for c in cids}
    out = {c: 0 for c in cids}
    acts = cv.corpus.operational(conversation=list(cids),
                                 act="expectation-recorded")
    carriers = cv._carriers(acts) if acts else {}
    mine = [a for a in acts if carriers.get(a["id"]) == owner]
    where = {a["id"]: a["conversation"] for a in mine}
    for s in cv._expectation_states(mine, False) if mine else ():
        if s["expected_of"] == owner and not s["response_present"]:
            out[where[s["expectation"]]] += 1
    return out


def participants(cv, *, q=None, limit) -> dict:
    """`GET /fluid/api/participants[?q=]`: the names a post can be addressed
    to, for the composer's `@` (F2), and who the owner is, as the baseline
    identifies them -- None where the record names nobody. The composer
    writes as the owner, falling back as production's `MeProvider` does.

    Searched, never pruned: `q` matches anywhere in the alias, and `matched`
    says how many it found beside the `limit` returned."""
    from mentis.operational.work_overview import owner_of
    want = (q or "").strip().lower().lstrip("@")
    rows = [{"id": p["id"], "alias": p["body"].get("alias"),
             "about": p["body"].get("about")}
            for p in cv.all_participants()]
    if want:
        rows = [r for r in rows
                if want in (r["alias"] or "").lower().lstrip("@")]
    return {"participants": rows[:limit], "matched": len(rows),
            "limit": limit, "me": owner_of(cv)}


# -- collections --------------------------------------------------------------

def conversation_collection(corpus, cid, *, before, after, limit,
                            shape, start=None, topic=None) -> dict:
    """`GET /fluid/api/collections/conversation`: a Conversation's members --
    its home posts and the posts included in it, once each -- in stream order,
    one bounded page.

    `shape=threads` (the default) pages by what the conversation DRAWS: a
    reply whose parent is a member here is reached through that parent's
    thread, not listed beside it. A reply to a post that is not a member here
    stands on its own, saying what it replies to. `shape=posts` is every
    member, flat.

    `topic` (Fluid A8, ADDITIVE): only the members filed under that Topic of
    this Conversation now -- the scope production's `?topic=` focus reads
    (`topic_contributions`) -- each as its own unit, flat, as production's
    focused flow draws a Topic's Turns. Same cursors, same numbers, under the
    key `topic:<conversation>:<topic>`. A Topic of another Conversation is
    refused by name. Without it the answer is exactly what it was."""
    got = corpus.read([cid])
    if not got or (got[0].get("definition") or {}).get("name") != CONVERSATION:
        raise BadRequest(f"not a conversation: {cid!r}")
    b_key, a_key = _window(corpus, before, after, start)
    if shape not in ("threads", "posts"):
        raise BadRequest("shape is 'threads' or 'posts'")
    linked = _in_force(corpus, corpus.links(relation=LINKED_INTO, to=cid))
    link_of = {}
    for x in linked:
        link_of.setdefault(x["link"]["from"], x)
    if topic is not None:
        page = _topic_page(corpus, cid, topic, list(link_of),
                           before=b_key, after=a_key, limit=limit)
    else:
        page = corpus.members_page(
            cid, home=IN_CONVERSATION, kind=CONTRIBUTION, replies=REPLIES_TO,
            also=list(link_of), roots=shape == "threads",
            before=b_key, after=a_key, limit=limit)
    rows = page["rows"]
    # A RENAME'S VERSION IS THAT CONVERSATION, never a collection of its own.
    # Asked only of an empty page, so a page still costs the same statements:
    # nothing is homed on or included into a version (`Conversations.
    # version_refusal`, asked by `say` and `link_into`), so a version's page
    # is always empty -- only posts written onto one before that refusal
    # existed could fill it.
    if not rows and _later_versions(corpus, [cid]):
        raise BadRequest(f"not a conversation: {cid!r} is a later version of "
                         f"{corpus.history(cid)[0]!r}")
    total = page["total"]
    if total is None:
        total = corpus.member_total(cid, home=IN_CONVERSATION,
                                    kind=CONTRIBUTION, replies=REPLIES_TO,
                                    also=list(link_of),
                                    roots=shape == "threads")
    elsewhere = homes_of(corpus, [r[0] for r in rows if r[3] is None])
    items = []
    for pid, seq, at, number, parent, pos in rows:
        item = {"id": pid, "via": "home" if number is not None else "linked",
                "number": number, "reply_to": parent}
        if number is None:
            item["home"] = elsewhere.get(pid)
            item["link"] = link_of[pid]["id"] if pid in link_of else None
        items.append(item)
    older = rows[0][5] - 1 if rows else (0 if a_key is None else total)
    newer = total - rows[-1][5] if rows else (0 if b_key is None else total)
    return {
        "key": f"conversation:{cid}" if topic is None
        else f"topic:{cid}:{topic}",
        "conversation": cid, "shape": shape if topic is None else "posts",
        **({} if topic is None else {"topic": topic}),
        "items": items, "total": total, "older": older, "newer": newer,
        "before": _page_cursor(rows[0][2], rows[0][1])
        if rows and older else None,
        "after": _page_cursor(rows[-1][2], rows[-1][1])
        if rows and newer else None,
        "limit": limit,
    }


def _topic_page(corpus, cid, topic, also, *, before, after, limit) -> dict:
    """ONE PAGE of the members of `cid` filed under `topic` now, in the
    shape `members_page` answers (rows, total), each member its own unit.

    COST. The Conversation's member rows (one `members_page` statement, no
    bodies) and the Topic's filings; the page is cut from those in memory,
    so it is O(members of the Conversation), as a page of it already is."""
    owner = _first(corpus.links(relation=TOPIC_OF, frm=topic))
    if owner.get(topic) != cid:
        raise BadRequest(f"not a topic of this conversation: {topic!r}")
    filed = {x["link"]["from"] for x in _in_force(
        corpus, corpus.links(relation=ABOUT_TOPIC, to=topic))}
    every = corpus.members_page(
        cid, home=IN_CONVERSATION, kind=CONTRIBUTION, replies=REPLIES_TO,
        also=also, roots=False, limit=max(1, corpus.member_total(
            cid, home=IN_CONVERSATION, kind=CONTRIBUTION, replies=REPLIES_TO,
            also=also, roots=False)))["rows"]
    units = [(pid, seq, at, number, parent, i + 1) for i, (
        pid, seq, at, number, parent, _pos) in enumerate(
            r for r in every if r[0] in filed)]
    if before is not None:
        units = [u for u in units if (u[2], u[1]) < before][-limit:]
    elif after is not None:
        units = [u for u in units if (u[2], u[1]) > after][:limit]
    else:
        units = units[-limit:]
    return {"rows": units, "total": len([r for r in every if r[0] in filed])}


def stream_collection(corpus, *, before, after, limit, start=None) -> dict:
    """`GET /fluid/api/collections/stream`: every current post, from every
    Conversation, newest first by record position, one page -- each once,
    at its home. A later version of a post is never an item (it has no
    home); a deleted post stays one, as a Conversation's page keeps it.

    THE SAME CURSORS AND WINDOW as a Conversation's page (`_window`,
    `_page_cursor`), ordered by the record position each one carries.
    BOUNDED BY THE PAGE: one statement (`stream_page`) beside those a
    cursor given as an id costs, never one per post."""
    b_key, a_key = _window(corpus, before, after, start)
    page = corpus.stream_page(kind=CONTRIBUTION, home=IN_CONVERSATION,
                              before=b_key[1] if b_key else None,
                              after=a_key[1] if a_key else None, limit=limit)
    rows = page["rows"]
    # newest first: rows[0] is the newest of the page, rows[-1] the oldest
    if a_key is not None:
        newer, older = page["more"], page["beyond"]
    else:
        older, newer = page["more"], page["beyond"]
    return {
        "key": "stream",
        "items": [{"id": pid, "home": home, "at": at}
                  for pid, _seq, at, home in rows],
        "before": _page_cursor(rows[-1][2], rows[-1][1])
        if rows and older else None,
        "after": _page_cursor(rows[0][2], rows[0][1])
        if rows and newer else None,
        "limit": limit,
    }


def selection(corpus, ids) -> dict:
    """`GET /fluid/api/collections/selection?ids=`: the posts a client has
    selected, from any Conversation, in record order, each with its home.
    An id that is not a post -- unknown, a link, a Conversation, a later
    version of a post -- is `known: false`, after the known, in the order
    asked. Nothing is written: the selection is the client's."""
    heads = corpus.heads(ids)
    homes = homes_of(corpus, [i for i in ids if i in heads
                              and heads[i][1] == "entry"
                              and heads[i][2] == CONTRIBUTION
                              and not heads[i][5]])
    known = sorted((i for i in ids if i in homes), key=lambda i: heads[i][0])
    return {"key": "selection",
            "items": [{"id": i, "home": homes[i], "known": True}
                      for i in known]
            + [{"id": i, "home": None, "known": False}
               for i in ids if i not in homes]}


def thread_collection(corpus, root, *, before, after, limit,
                      start=None) -> dict:
    """`GET /fluid/api/collections/thread`: every reply under `root`, from
    any Conversation, in stream order, one page -- each marked with its
    parent, its depth and its home. The totals are the whole thread's."""
    head = corpus.read([root])
    if not head or not _is_post(head[0]):
        raise BadRequest(f"not a post: {root!r}")
    b, a = _window(corpus, before, after, start)
    rows = corpus.reply_closure(root, replies=REPLIES_TO, home=IN_CONVERSATION)
    keyed = [((at, seq), r) for r in rows for (_, seq, at) in [r[:3]]]
    if b is not None:
        chosen = [r for k, r in keyed if k < b][-limit:]
    elif a is not None:
        chosen = [r for k, r in keyed if k > a][:limit]
    else:
        chosen = [r for _, r in keyed][-limit:]
    first = rows.index(chosen[0]) if chosen else 0
    older = first if chosen else (0 if a is None else len(rows))
    newer = len(rows) - first - len(chosen) if chosen else \
        (0 if b is None else len(rows))
    by_home = {}
    for r in rows:
        by_home[r[5]] = by_home.get(r[5], 0) + 1
    root_home = homes_of(corpus, [root]).get(root)
    return {
        "key": f"thread:{root}", "root": root, "root_home": root_home,
        "items": [{"id": r[0], "parent": r[3], "depth": r[4], "home": r[5]}
                  for r in chosen],
        "total": len(rows), "older": older, "newer": newer,
        "by_home": by_home,
        "before": _page_cursor(chosen[0][2], chosen[0][1])
        if chosen and older else None,
        "after": _page_cursor(chosen[-1][2], chosen[-1][1])
        if chosen and newer else None,
        "limit": limit,
    }


# -- the change feed ----------------------------------------------------------

def _ancestors(corpus, pid, depth=64) -> list[str]:
    """The posts `pid` answers, nearest first (first link wins)."""
    out, seen, up = [], {pid}, pid
    for _ in range(depth):
        got = corpus.links(relation=REPLIES_TO, frm=up)
        if not got:
            break
        up = got[0]["link"]["to"]
        if up in seen:
            break
        seen.add(up)
        out.append(up)
    return out


def _needs_you_moved(corpus, cv, acts, entries):
    """Only changes to carriers or responses can change the owner's count.

    Home's work invalidation also follows notes and progress under a request.
    An activity-list row has no such fields, so ask its owner rule only about
    new requests, assignments, claims met, and replies to request posts.
    """
    from . import home
    from mentis.operational.work_overview import owner_of
    relevant = [a for a in acts if a["act"] in (
        "expectation-recorded", "expectation-assigned", "expectation-met")]
    up = {a["id"] if a["act"] == "expectation-recorded" else a.get("caused_by")
          for a in relevant}
    replied = {to for _eid, _d, _frm, to, rel in entries if rel == REPLIES_TO}
    if replied:
        up.update(a["id"] for a in corpus.operational(
            turn=sorted(replied), act="expectation-recorded"))
    if not any(up):
        return False
    _, nearest = home._requests_above(corpus, up, ())
    return home._asks_owner_moved(corpus, cv, nearest, relevant, owner_of(cv))


def thread_roots(corpus, out) -> None:
    """ADD `threads` to a change answer (`&threads=1`, F6): every post whose
    WHOLE THREAD may read differently now -- its count of replies, or what
    This post shows for it (`posts?thread=1`). A new reply moves every post
    above it, which `thread:<id>` already names; an edit, a deletion or a run
    returning something moves a reply's objects (`objects:<id>`), and with
    them every post above it, which nothing else names. Nothing else in the
    answer changes."""
    keys = out.get("collections") or []
    roots = {k[len("thread:"):] for k in keys if k.startswith("thread:")}
    for k in keys:
        if k.startswith("objects:"):
            roots.update(_ancestors(corpus, k[len("objects:"):]))
    out["threads"] = sorted(roots)


def changes(corpus, cv, since) -> dict:
    """`GET /fluid/api/changes?since=<cursor>`: what moved after the cursor.

    WHERE, NEVER WHAT: changed entity ids with the version they now read
    at, memberships added and ended, the collection keys whose ids or order
    may have changed, the runs' handles named (`work`, as F0 gave it), and
    the runs and pieces of work that may read differently (`entities`:
    `run:<id>`, `work:<id>`, F4a). Bodies are fetched by the client,
    for only those ids. A post's change names EVERY Conversation it belongs
    to -- its home and every one it is included in -- so a zone showing it
    anywhere hears it.

    No cursor: only the cursor to start from. A gap over CAP rows, or a
    cursor this record is not at or past: `reread`, and the cursor to go on
    from -- the client rereads what it shows, as the pulse's readers do."""
    now = corpus.advance()
    if not since:
        return {"cursor": change_cursor(now), "since": None, "start": True}
    adv = parse_change_cursor(since)
    empty = {"since": since, "posts": [], "conversations": [],
             "memberships": {"added": [], "ended": []}, "collections": [],
             "entities": [], "work": [], "other": 0}
    if adv == tuple(now):
        return {"cursor": change_cursor(now), **empty}
    rows = corpus.since(adv, CAP, acts_in_full=True)
    if rows is None:
        return {"cursor": change_cursor(now), "since": since, "reread": True,
                "why": ("more than %d rows were written since that cursor, or "
                        "this record is not at or past it" % CAP)}
    entries, full_acts, delivered = rows
    acts = [(a["act"], a["conversation"], a["execution"], a["turn"])
            for a in full_acts]
    heads = corpus.heads([e[0] for e in entries]
                         + [x for e in entries for x in e[2:4] if x])
    # THE NEXT CURSOR IS WHAT WAS READ, not a second look at `advance`: a row
    # committed between the two is reported next time, never skipped.
    top = max([heads[e[0]][0] for e in entries if e[0] in heads],
              default=adv[0])
    cursor = change_cursor((max(top, adv[0]), adv[1] + len(acts),
                            adv[2] + len(delivered)))
    sup = corpus.superseding_relation()
    touched, convs, keys, work = set(), set(), set(), set()
    added, ended, versions, superseded = [], [], set(), set()
    renames, renamed = set(), set()
    other = 0

    def kind(x):
        h = heads.get(x)
        return h[2] if h else None

    for eid, def_name, frm, to, rel in entries:
        if not rel:
            if def_name == CONTRIBUTION:
                versions.add(eid)            # a post, or a version of one
            elif def_name == CONVERSATION:
                convs.add(eid)
                keys.add("conversations")
            elif def_name != "deletion":
                other += 1
            continue
        if rel == IN_CONVERSATION:
            added.append({"post": frm, "conversation": to, "via": "home",
                          "link": eid})
            touched.add(frm)
            convs.add(to)
            keys.update((f"conversation:{to}", STREAM, "conversations"))
        elif rel == LINKED_INTO:
            added.append({"post": frm, "conversation": to, "via": "linked",
                          "link": eid})
            touched.add(frm)
            convs.add(to)
            keys.update((f"conversation:{to}", "conversations"))
        elif rel == REPLIES_TO:
            touched.update((frm, to))
            for up in [to] + _ancestors(corpus, to):
                keys.add(f"thread:{up}")
        elif rel == sup:
            h = heads.get(to)
            if h and h[5] == LINKED_INTO:
                ended.append({"post": h[3], "conversation": h[4],
                              "via": "linked", "link": to})
                touched.add(h[3])
                convs.add(h[4])
                keys.update((f"conversation:{h[4]}", "conversations"))
            elif kind(to) == CONTRIBUTION:
                versions.add(to)
                superseded.add(to)
            elif kind(to) == CONVERSATION:
                # A RENAME: the new version is the Conversation it renames,
                # so the change names that Conversation -- by its own id, in
                # the list and as its collection -- and never the version.
                root = corpus.history(to)[0]
                renames.add(frm)
                renamed.add(root)
                convs.add(root)
                keys.update(("conversations", f"conversation:{root}"))
            elif not (h and h[5]):
                other += 1
        elif rel == PARTICIPATES_IN:
            convs.add(to)
        elif rel == ABOUT_TOPIC:
            touched.add(frm)
        elif kind(frm) == CONTRIBUTION or kind(to) == CONTRIBUTION:
            touched.update(x for x in (frm, to) if kind(x) == CONTRIBUTION)
        else:
            other += 1
    joined = [(eid, frm, to) for eid, _d, frm, to, rel in entries
              if rel == PARTICIPATES_IN]
    if joined:
        new = {eid for eid, _frm, _to in joined}
        previous = {(e["link"]["from"], e["link"]["to"])
                    for e in corpus.links(relation=PARTICIPATES_IN,
                                          to_any=sorted({to for _, _, to in joined}))
                    if e["id"] not in new}
        if any((frm, to) not in previous for _, frm, to in joined):
            keys.add("conversations")        # the row counts distinct people
    convs -= renames
    returned = set()
    for act, conversation, execution, turn in acts:
        if turn:
            touched.add(turn)
            if act in RETURNING_ACTS:
                returned.add(turn)
        if conversation:
            convs.add(conversation)
        if execution:
            work.add(execution)
    for conversation, execution in delivered:
        if conversation:
            convs.add(conversation)
        if execution:
            work.add(execution)
    # A NEW CONTRIBUTION ROW IS A POST OR A VERSION OF ONE. A post has a home;
    # a version is read back to the post it is a version of.
    # A POST THAT GOT A NEW VERSION (an edit, or a deletion ending it) has new
    # objects: `objects:<root>` says so (F1), so what a zone keeps of them is
    # read again. A new post's objects are new with it.
    homes = homes_of(corpus, versions | touched)
    for v in versions:
        if v in homes:
            touched.add(v)
            if v in superseded:
                keys.add(f"objects:{v}")
        else:
            chain = corpus.history(v)
            if chain and chain[0] in homes_of(corpus, [chain[0]]):
                touched.add(chain[0])
                keys.add(f"objects:{chain[0]}")
    homes = homes_of(corpus, touched)
    # WHAT A RUN RETURNED WITH A POST is among its objects, and an act can add
    # to it (`result-recovered`) without a new version: `objects:<root>` says
    # so, though the version the post reads at is the same.
    keys.update(f"objects:{p}" for p in returned if p in homes)
    pids = sorted(p for p in touched if p in homes)
    # HOME AND WORK (F4a): which runs and pieces of work may read
    # differently now, as `work:<id>` and `run:<id>`, and which of the
    # Home's collections may have changed (`home.changes_of`).
    from . import home as _home
    entities, home_keys = _home.changes_of(
        corpus, cv, acts=full_acts, entries=entries, heads=heads,
        edited=superseded, renamed=renamed)
    keys.update(home_keys)
    # ANNOTATIONS, ADDITIVE: `anchors:<post>` for each post whose anchors,
    # reactions, anchored replies or deep dives may read differently now
    # (`anchored.changes_of`). A client holding none ignores the key.
    from . import anchored as _annotations
    keys.update(_annotations.changes_of(corpus, full_acts))
    # THE STREAM (F5) is every post by record position: a new post, or a
    # new version of one, says so. THE ACTIVITY LIST'S ROWS say what asks
    # the owner and which runs are working there, so a change to Needs you
    # or a run starting or ending moves them too.
    if versions:
        keys.add(STREAM)
    if _home.ACTIVITY in home_keys or (
            "conversations" not in keys and _home.NEEDS_YOU in home_keys
            and _needs_you_moved(corpus, cv, full_acts, entries)):
        keys.add("conversations")
    included = included_in(corpus, pids)
    now_read = _now_reads(corpus, corpus.read(pids))
    posts_out = []
    for p in pids:
        where = [homes[p]] + [x["link"]["to"] for x in included.get(p, [])]
        where += [m["conversation"] for m in ended
                  if m["post"] == p and m["conversation"] not in where]
        posts_out.append({"id": p, "version": version_of(now_read[p])
                          if p in now_read else None,
                          "conversations": where})
    return {"cursor": cursor, "since": since, "posts": posts_out,
            "conversations": sorted(convs),
            "memberships": {"added": added, "ended": ended},
            "collections": sorted(keys), "entities": sorted(entities),
            "work": sorted(work), "other": other}
