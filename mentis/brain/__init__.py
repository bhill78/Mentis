"""Brain scope: a durable Participant operating outside any Conversation.

A Brain is the working environment a Participant orients to. Today that is one
writable corpus; the SQLite pressure test at `715f680` deliberately left room
for attached operational, reference and gold corpora, so this class takes a
PRIMARY corpus and a (currently empty) set of attached ones rather than being
named after the single file it happens to have.

Brain is NOT a Conversation, a Participant, a corpus or an agent. It has no
durable representation of its own: there is no brain table, no brain Entry and
no brain id beyond the identity the corpus already carries. Everything this
module returns is COMPUTED from durable records and machine-local execution
state, and deleting it loses nothing.

There is no privileged participant type here. An assisting behavioural mode is
a Persona -- ordinary behavioural material, ordinary data -- and any durable
Participant can be invoked at Brain scope. This module names no Persona and no
alias, which a test checks by looking for exactly those literals.

Like the Conversation layer, this imports nothing from `mentis`: it is handed
the seams it works through.
"""

from __future__ import annotations


class Brain:
    """The environment a Brain-scoped Participant orients to and acts in."""

    def __init__(self, primary, conversations, attached=()):
        if attached:
            raise NotImplementedError(
                "multi-corpus attachment is not implemented; the shape is here "
                "so that adding it later does not redefine Participant or "
                "Conversation identity")
        self._primary = primary
        self._attached = tuple(attached)
        #: the drill-down seam. Brain scope sees that Conversations exist;
        #: their contents come from asking this, per Conversation.
        self.conversations = conversations

    # -- what this Brain is made of -----------------------------------------

    @property
    def primary(self):
        """The one writable corpus. Not the Brain, and not its identity."""
        return self._primary

    @property
    def corpus(self):
        return self._primary

    @property
    def corpora(self) -> tuple:
        return (self._primary,) + self._attached

    # -- invocation, one operation shared with Conversation scope -----------

    def begin_execution(self, *, participant, persona=None, material=(),
                        runtime=None):
        """Invoke a Participant at Brain scope. No Conversation is involved.

        The same call the Conversation layer uses, with no Conversation. There
        is deliberately not a second execution API for Brain scope.
        """
        return self.conversations.begin_execution(
            participant=participant, conversation=None, persona=persona,
            material=material, runtime=runtime)

    def end_execution(self, reference):
        return self.conversations.end_execution(reference)

    def active_executions(self):
        return self.conversations.active_executions()

    def compose(self, *, participant, persona=None, material=(), request="",
                behavioural=(), recent=3, question=None):
        """Compose for a Brain-scoped invocation.

        `behavioural` names durable behavioural material explicitly. Brain scope
        is NOT wildcard scope: material reaches it because an owner placed it
        on the whole Brain -- an explicit `scoped-to` link to the whole-Brain
        destination, which `compose` reads -- or because the caller named it
        here. Material placed at a Conversation does not reach Brain scope,
        and nothing is inferred from material having no Conversation.

        `question` is the work, as it is at Conversation scope: what is being
        asked is what propositional material is matched against. Absent, as
        there, means nobody asked.
        """
        return self.conversations.compose(
            conversation=None, participant=participant, persona=persona,
            material=material, request=request, behavioural=behavioural,
            brain=self, recent=recent, question=question)

    # -- orientation: computed, bounded, never stored -----------------------

    def orientation(self, *, participant=None, recent=3, conversations=12,
                    participants=20, attention=10) -> dict:
        """Enough to decide where attention may be useful. Not the contents.

        Deliberately carries NO contribution text, from any Conversation. A
        Brain-scoped participant learns that Conversations exist, how busy they
        are and what looks unanswered; to learn what was said it must ask the
        Conversation seam for that Conversation. That is what keeps two
        Conversations from leaking into one another at Brain scope.
        """
        cv = self.conversations
        conv_rows, found = [], []

        for conv in cv.all_conversations():
            cid = conv["id"]
            contributions = sorted(cv.contributions(cid),
                                   key=lambda e: e["recorded_at"])
            awaiting = cv.awaiting_response(cid)
            found.extend(awaiting)
            found.extend(cv.failures_in(cid))
            conv_rows.append({
                "conversation": cid,
                "name": conv["body"]["name"],
                "about": conv["body"]["about"],
                "participants": len(cv.participants(cid)),
                "contributions": len(contributions),
                "topics": len(cv.topics(cid)),
                "last_activity": (contributions[-1]["recorded_at"]
                                  if contributions else None),
                "awaiting_response": len(awaiting),
                # that media exists, never the media
                "recent_media": sorted({
                    p.get("type") or "untyped" for c in contributions[-recent:]
                    for p in c["body"]["parts"] if p.get("type") != "text"}),
            })

        part_rows = []
        for p in cv.all_participants():
            part_rows.append({
                "participant": p["id"],
                "alias": p["body"]["alias"],
                "conversations": len(cv.conversations_of(p["id"])),
            })

        live = []
        for ex in cv.active_executions():
            live.append({
                "execution": ex.reference,
                "participant": ex.participant,
                "alias": cv.alias(ex.participant),
                "conversation": ex.conversation,
                "scope": "conversation" if ex.conversation else "brain",
                "runtime": ex.runtime,
                "persona": ex.persona,
            })

        if participant is not None:
            found = [a for a in found
                     if a.get("participant") == participant] or found

        # bounded, and never silently. A Brain with four hundred Conversations
        # must not produce a four-hundred-line orientation, and must not
        # pretend the ones it left out do not exist.
        by_recency = sorted(conv_rows, key=lambda c: -(c["last_activity"] or 0))
        by_alias = sorted(part_rows, key=lambda p: p["alias"])
        return {
            "brain": {"primary": self._primary.corpus_id,
                      "attached": [c.corpus_id for c in self._attached]},
            "conversations": by_recency[:conversations],
            "conversations_total": len(by_recency),
            "conversations_omitted": max(0, len(by_recency) - conversations),
            "participants": by_alias[:participants],
            "participants_total": len(by_alias),
            "participants_omitted": max(0, len(by_alias) - participants),
            "active_executions": live,
            "attention": found[:attention],
            "attention_total": len(found),
            "attention_omitted": max(0, len(found) - attention),
            # OF THOSE, HOW MANY NEVER REACHED ANYBODY: a delivery observed to
            # fail, or no delivery record at all. Tallied from the rows already
            # in hand -- nothing more is read for it.
            "attention_undelivered": sum(
                1 for a in found
                if a["what"] == "delivery failed" or a.get("delivered") is False),
            "note": ("counts and names only. Ask the Conversation seam for what "
                     "was actually said in any of these."),
        }

    def render(self, orientation: dict) -> str:
        """The compact text form delivered to a runtime."""
        lines = [f"Brain: corpus {orientation['brain']['primary']}"]
        lines.append(f"{len(orientation['conversations'])} conversations, "
                     f"{len(orientation['participants'])} durable participants, "
                     f"{len(orientation['active_executions'])} live executions")
        for c in orientation["conversations"]:
            bits = [f"{c['contributions']} contributions",
                    f"{c['participants']} participants"]
            if c["topics"]:
                bits.append(f"{c['topics']} topics")
            if c["awaiting_response"]:
                bits.append(f"{c['awaiting_response']} awaiting response")
            if c["recent_media"]:
                bits.append("recent " + "/".join(c["recent_media"]))
            lines.append(f"  [{c['conversation']}] {c['name']} - {', '.join(bits)}")
        for p in orientation["participants"]:
            lines.append(f"  {p['alias']}: in {p['conversations']} conversation(s)")
        for e in orientation["active_executions"]:
            where = e["conversation"] or "brain scope"
            lines.append(f"  RUNNING {e['alias']} on {e['runtime']} at {where}")
        for a in orientation["attention"]:
            lines.append(f"  ATTENTION {a['what']}: {a['detail']}")
        if orientation.get("attention_omitted"):
            lines.append(f"  ...and {orientation['attention_omitted']} further "
                         f"items wanting attention, of "
                         f"{orientation['attention_total']} in total")
        if orientation.get("conversations_omitted"):
            lines.append(f"  ...and {orientation['conversations_omitted']} further "
                         f"conversations not listed, of "
                         f"{orientation['conversations_total']} in total")
        if orientation.get("participants_omitted"):
            lines.append(f"  ...and {orientation['participants_omitted']} further "
                         f"participants not listed, of "
                         f"{orientation['participants_total']} in total")
        lines.append("Counts and names only; ask for a conversation's own "
                     "orientation to see what was said there.")
        return "\n".join(lines)


def open_brain(primary, conversations, attached=()) -> Brain:
    return Brain(primary, conversations, attached=attached)
