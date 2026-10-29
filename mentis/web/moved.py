"""WHAT MOVED, said beside the pulse that says something did.

`/api/pulse` answers with a token to compare, and every reader in the
interface used to reread its own path whenever the durable half changed. One
post in one Conversation therefore reread everything on screen: Brain-wide
lists, governed material, participants, every run's execution sheet and every
other Conversation's material -- 40 to 60 requests on the live Brain, through
one server, for a single Turn.

So a pulse asked `?since=<the durable half last seen>` also says WHERE the
record moved: the Conversations whose material was written, the executions
acts or deliveries named, and whether anything written was governed material
or a participant. Each reader decides from that whether it is concerned.

IT ONLY EVER NARROWS WHAT IS CERTAIN. Anything written that cannot be placed in
a Conversation sets `loose`, and a loose move rereads every reader exactly as
before. So does a gap too long to read (`CAP`), or a token this record is not
at or past. A reader the interface has not taught what it shows rereads on
every move, as it always did.

Nothing here is a diff or a second model of the record: it is where, never
what.
"""
from __future__ import annotations

#: MORE THAN THIS MANY OF ANY ONE KIND SINCE THE TOKEN, and it is not worth
#: placing them: everything moved. Asked about every 1.2 s per open page, so
#: a gap this long is a page that was asleep.
CAP = 200

#: WHAT A CONVERSATION IS MADE OF. A kind written outside this set is taken as
#: governed material (or anything else Brain-wide), which is the conservative
#: answer: readers of governed material reread.
CONVERSATION_MATERIAL = frozenset({
    "contribution", "in-conversation", "replies-to", "about-topic", "topic",
    "topic-of", "participates-in", "conversation", "produced", "admission",
    "anchor", "anchors-in", "reaction", "reacts-to", "linked-into",
    "opened-from", "pictured-by", "deletion", "carries-intake",
})

#: WHO IS IN THE BRAIN, and who is in which Conversation.
PEOPLE = frozenset({"participant", "persona", "participates-in"})

#: ACTS ABOUT A RUN, NOT ABOUT ITS CONVERSATION: how a run's permission
#: request was answered, and the owner's consent changes. They are written as
#: fast as an agent works -- 124 of one run's 153 acts in 21 minutes
#: (profiling, 2026-10-29) -- and nothing a Conversation shows reads them; the
#: run panel does, through the run's execution. Placing them in the
#: Conversation made every open view of it reread about every 8 s.
RUN_ONLY_ACTS = frozenset({"operation-answered", "consent-set"})

#: LINKS WHOSE `to` IS THE CONVERSATION ITSELF. A participant or a linked post
#: belongs to many, so these are read off the link, never searched from an end.
_TO_CONVERSATION = frozenset({"in-conversation", "topic-of", "participates-in",
                              "linked-into"})


def _parse(token: str):
    try:
        a, b, c = (int(x) for x in token.split("."))
    except (AttributeError, ValueError):
        return None
    return (a, b, c)


class _Placer:
    """Which Conversation an id is material of, read from the record's own
    links and acts, remembered for one answer."""

    def __init__(self, corpus):
        self.corpus, self.known = corpus, {}

    def of(self, x, depth=3):
        if not x or depth <= 0:
            return None
        if x in self.known:
            return self.known[x]
        self.known[x] = None              # a cycle answers nothing
        found = self._find(x, depth)
        self.known[x] = found
        return found

    def _find(self, x, depth):
        c = self.corpus
        if not x.startswith(("ent-", "adm-")):
            # An act (`opr-`), or an execution's reference: the acts say where.
            acts = (c.operational(id=x) if x.startswith("opr-") else []) \
                or c.operational(execution=x, limit=1)
            for a in acts:
                if a.get("conversation"):
                    return a["conversation"]
            return None
        rows = c.read([x])
        if rows and (rows[0].get("definition") or {}).get("name") == "conversation":
            return x
        for ln in c.links(frm=x):
            rel, to = ln["link"]["relation"], ln["link"]["to"]
            if rel in ("in-conversation", "topic-of"):
                return to
            if rel in ("participates-in", "linked-into"):
                continue
            got = self.of(to, depth - 1)
            if got:
                return got
        for ln in c.links(relation="produced", to=x):
            got = self.of(ln["link"]["from"], depth - 1)
            if got:
                return got
        return None


def moved(corpus, since: str | None) -> dict | None:
    """Where the record moved after `since` (the durable half of a pulse
    token), or None where that cannot be said and everything is to reread."""
    advance = _parse(since) if since else None
    if advance is None:
        return None
    rows = corpus.since(advance, CAP)
    if rows is None:
        return None
    entries, acts, delivered = rows
    place = _Placer(corpus)
    conversations, executions = set(), set()
    governed = people = loose = False
    for eid, kind, frm, to, rel in entries:
        kind = kind or rel
        if kind not in CONVERSATION_MATERIAL:
            governed = True
        if kind in PEOPLE:
            people = True
        if rel in _TO_CONVERSATION:
            conversations.add(to)
            if rel == "linked-into":
                home = place.of(frm)
                if home:
                    conversations.add(home)
            continue
        where = (place.of(frm) or place.of(to)) if rel else place.of(eid)
        if where:
            conversations.add(where)
        elif kind != "admission":
            # An Admission is placed by the act that brought it in, which is
            # read below; anything else unplaced could be anywhere.
            loose = True
    for act, conversation, execution, turn in acts:
        if act in RUN_ONLY_ACTS:
            if execution:
                executions.add(execution)
            else:
                loose = True
            continue
        if conversation:
            conversations.add(conversation)
        else:
            loose = True
        # AND WHERE ITS TURN LIVES, which is not always where the act was
        # done: linking or filing a post into another Conversation is recorded
        # there, and the post's own Conversation shows it too.
        home = place.of(turn) if turn else None
        if home:
            conversations.add(home)
        if execution:
            executions.add(execution)
        if act.startswith(("material-", "governance-")):
            governed = True
    for conversation, execution in delivered:
        if conversation:
            conversations.add(conversation)
        else:
            loose = True
        executions.add(execution)
    return {"conversations": sorted(conversations),
            "executions": sorted(executions),
            "governed": governed, "people": people, "loose": loose}
