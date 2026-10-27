"""A choice for the owner written into a reply is ASKED, not left in prose.

Agents are told to ask every choice through `request_decision`, and some
still write it into the reply: a ```checklist titled "Your call before
deployment", "Which should I do first? A) ... B) ...", or a closing "Should I
merge it now?". Nothing waited for those answers and the owner could only
find them by reading reports. So when a run's reply carries one and the run
raised no decision itself, Mentis raises it: a real decision form on that
reply, through the same machinery `request_decision` uses
(`worker._decision_form`), owed by the owner, marked `from_prose: true`.
The reply stands exactly as written.

ONLY THE OWNER'S CHOICES. Raised only where the work was asked for by the
owner or the reply is addressed to them. A specialist reporting to the agent
that delegated to it writes for that agent, and its choices are that
agent's to take or to ask.

WHAT COUNTS is `mentis.conversation.choices` (lists and checklists that ask
for a choice) WHOSE LEAD-IN ASKS THE READER -- a question, "Choose ...",
"Pick one ...", "your call" (`asks_reader`); a report's list ("What I
decided:", "Steps taken: A) ... B) ...") is at most warned of, never raised
-- plus one narrow rule here: the reply's FINAL paragraph is a
question asking leave -- "Should I ...?", "Want me to ...?", "Do you want me
to ...?", "OK to ...?", "Shall I ...?" -- which becomes a yes/no question.
"""

from __future__ import annotations

import re

#: A closing paragraph that asks the owner's leave, as a yes/no question.
ASKS_LEAVE = re.compile(
    r"(?:^|[.!:?]\s+|\n)(?P<q>(?:should\s+i|shall\s+i|do\s+you\s+want\s+me\s+to"
    r"|want\s+me\s+to|would\s+you\s+like\s+me\s+to|ok(?:ay)?\s+to|"
    r"is\s+it\s+ok(?:ay)?\s+(?:if\s+i|to))\b[^?\n]{2,300}\?)\s*$",
    re.IGNORECASE)
_MARKUP = re.compile(r"[*_`]+")
#: A lead-in that ASKS THE READER: an imperative to choose, or the owner's
#: call named as theirs. (A lead-in ending in "?" asks too.) Anything else --
#: "What I decided:", "Steps taken:", "Options: I went with the second." --
#: is a report, and a report's list is never raised as a decision.
ASKS_READER = re.compile(
    # a question put to the reader, however it is punctuated
    r"^(?:which|would\s+you|do\s+you|should\s+(?:i|we)|shall\s+(?:i|we)"
    r"|i\s+need\s+you\s+to)\b"
    # an imperative to choose -- WITH what to choose, so "Select files were
    # changed:" is not one
    r"|^(?:please\s+)?(?:choose|pick|select|decide)"
    r"(?:\s*$|\s+(?:one|which|whether|between|from|among|an?\s+option"
    r"|the\s+one|one\s+of|what)\b)"
    r"|^(?:please\s+)?(?:tell\s+me|let\s+me\s+know)\s+(?:which|whether)\b"
    # the owner's call, named as theirs
    r"|\b(?:your\s+(?:call|decision|choice|pick)|for\s+you\s+to\s+decide"
    r"|needs?\s+your\s+(?:decision|call|choice))\b",
    re.IGNORECASE)


def asks_reader(lead) -> bool:
    """Whether a choice's lead-in is a question or an ask put to the reader,
    rather than a report of what was done."""
    words = _clean(lead).rstrip(" :")
    return bool(words) and (words.endswith("?")
                            or bool(ASKS_READER.search(words)))
LABEL_MAX = 200


def _clean(words: str) -> str:
    return " ".join(_MARKUP.sub("", words or "").split())


def leave_asked(text) -> str | None:
    """The yes/no question a reply ENDS on, or None."""
    if not isinstance(text, str):
        return None
    paragraphs = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if not paragraphs:
        return None
    last = paragraphs[-1].strip()
    if last.startswith(("```", "~~~", "-", "*", "|", ">")):
        return None
    m = ASKS_LEAVE.search(last)
    return _clean(m.group("q")) if m else None


def questions_in(texts) -> list[dict]:
    """The questions a reply's text parts ask the owner, as decision-form
    questions: `[{question, options, because}]`."""
    from mentis.conversation import choices
    out, seen = [], set()
    for _i, text in texts:
        for c in choices.find(text):
            labels, keys = [], set()
            for item in c["items"]:
                label = _clean(item)[:LABEL_MAX]
                if label and label.casefold() not in keys:
                    keys.add(label.casefold())
                    labels.append({"label": label})
            if len(labels) < 2 or not asks_reader(c.get("lead") or ""):
                continue
            q = _clean(c.get("lead") or "")
            if q.casefold() in seen:
                q = f"{q} (line {c['line']})"
            seen.add(q.casefold())
            out.append({"question": q, "options": labels,
                        "because": "written as a choice in the reply; "
                                   "asked here so it can be answered"})
    if texts:
        q = leave_asked(texts[-1][1])
        if q and q.casefold() not in seen:
            out.append({"question": q,
                        "options": [{"label": "Yes"}, {"label": "No"}],
                        "because": "the reply ends asking this; asked here "
                                   "so it can be answered"})
    return out


def for_the_owner(cv, expectation, reply) -> bool:
    """Whether a choice in this reply is the owner's to make: the work was
    asked for by the owner, or the reply is addressed to them."""
    from mentis.conversation.owner import _owner
    owner = _owner(cv)
    if not owner:
        return False
    try:
        if cv.expectation_state(expectation)["requested_by"] == owner:
            return True
    except Exception:                                     # noqa: BLE001
        pass
    try:
        return owner in cv.addressees_of(reply)["all"]
    except Exception:                                     # noqa: BLE001
        return False


def raise_from_reply(cv, execution, reply, expectation, *, actor,
                     runtime=None) -> dict | None:
    """Raise the owner's choices written in `reply` as ONE decision form on
    it, or None when there is nothing to raise. Never raises: a failure here
    leaves the reply and its warning as they would have been."""
    from mentis.conversation import render_check
    from mentis.worker import NotPermitted, _decision_form
    if not (execution and reply and expectation and actor):
        return None
    try:
        if render_check.raised_decision(cv.corpus, execution):
            return None
        questions = questions_in(render_check.texts_of_turn(cv.corpus, reply))
        if not questions or not for_the_owner(cv, expectation, reply):
            return None
        conversation = cv.conversation_of(reply)

        def act(name, **kw):
            kw.setdefault("caused_by", expectation)
            return cv.record_act(actor=actor, act=name, execution=execution,
                                 runtime=runtime, **kw)

        got = _decision_form(
            cv, {"questions": questions, "on": reply,
                 "because": "choices written in the reply instead of asked"},
            actor=actor, parent=expectation, here=conversation, wrote=None,
            act=act, where=lambda c: c, form_detail={"from_prose": True})
    except NotPermitted:
        return None
    except Exception:                                     # noqa: BLE001
        import traceback
        traceback.print_exc()
        return None
    return {"form": got["form"], "questions": len(questions),
            "of": got["of"]}
