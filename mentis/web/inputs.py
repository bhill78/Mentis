"""Done and Send back on a filled-in block: what hands answers to an agent.

FORMS BUILD, PACKAGE P4 (plan adm-ba8fea710d8a; design revision 3,
adm-a32b134770fc, owner decisions F4 and F7). Two server operations over a
response set (`mentis.conversation.responses`), kept apart because they mean
different things:

  DONE (F4)       `mark_ready`: "my input is finished". It records the
                  marked-ready, and then asks whether any work DECLARED it was
                  waiting for this set (`request_input`, an expectation
                  `expects: "input"`). That work resumes through the one
                  resumption path (`Conversations.claim_resumption`, then
                  `dispatch._resume`), once, and its `work-resumed` act names
                  the marked-ready and the exact answers it was given. With
                  no declared wait, Done resumes nobody.
  SEND BACK (F7)  `send_back`: "act on this now". It writes the owner's reply
                  on the block's post, asking the post's author to continue,
                  with the answers as they stand -- whether or not that agent
                  declared a wait. It goes through `posting.post`, so it
                  continues the author's existing work exactly where the
                  ordinary continuation rules allow (`continuation`), and
                  otherwise starts new work under the same author. An
                  `answers-sent-back` act names the set and the exact answers.

DONE AND A RUN ENDING DO NOT BOTH RESUME THE SAME WORK. Both ask
`claim_resumption`, whose own act is its guard inside one transaction: work
still running is not resumed (its run's end asks again), and once resumed,
the same Done is not new to it. A Done replayed under its operation key asks
again and finds it already resumed.

BOTH HAND OVER MORE THAN THE ANSWERS (ent-22d86cb14a87). Revision 2 says the
agent continues from "your structured answers and your own words", so each
hands the own words as they now read, quoted in full, every interpretation
of them with its state (pending, confirmed, changed, declined, out of date),
and the passages nobody has interpreted yet (`responses.handover`). The act
(`work-resumed` for Done, `answers-sent-back` for Send back) names the exact
revisions: the own-words entries, and each interpretation with its state and
reply then (`responses.handed`).

NO ROUTE OF ITS OWN BEYOND TWO COMMANDS. Fluid's door (`mentis.fluid.commands`)
answers `POST /fluid/api/response-sets/<id>/ready` and `/send-back` through
these; the rest of the response-set routes are package P3.
"""

from __future__ import annotations

import json
import traceback

from mentis.conversation import ANSWERS_SENT_BACK, INPUT, posting, responses
from mentis.conversation.versions import Refused

#: Longest value quoted in the words handed to an agent; the act keeps all.
QUOTE_MAX = 500


def waits_for(cv, sid) -> list[dict]:
    """Every input expectation that names this response set, oldest first."""
    s = responses._set(cv.corpus, sid)
    root = s["body"]["post"]
    return [a for a in cv.history(turn=root)
            if a["act"] == "expectation-recorded"
            and (a.get("detail") or {}).get("expects") == INPUT
            and a["detail"].get("response_set") == sid]


def resume_on_ready(st, sid) -> list[str]:
    """Resume the work that declared it waits for this set, where its wait
    is now over. Returns the `work-resumed` acts written, usually none."""
    from mentis.web import dispatch
    cv = st.cv
    made = []
    for a in waits_for(cv, sid):
        parent = a.get("caused_by")
        if not parent:
            continue
        try:
            act = cv.claim_resumption(parent, event={
                "kind": "input-ready", "set": sid, "expectation": a["id"]})
        except Exception:                                 # noqa: BLE001
            traceback.print_exc()
            continue
        if act is None:
            continue
        made.append(act)
        dispatch._resume(st, parent, act)
    return made


def mark_ready(st, sid, *, by, seen=None, written_by=None, op=None) -> dict:
    """Done: `responses.mark_ready`, then resume what declared it waits."""
    out = responses.mark_ready(st.cv, sid, by=by, seen=seen,
                               written_by=written_by, op=op)
    return {**out, "resumed": resume_on_ready(st, sid)}


def _quoted(value) -> str:
    said = value if isinstance(value, str) else json.dumps(value,
                                                           ensure_ascii=False)
    return said if len(said) <= QUOTE_MAX else said[:QUOTE_MAX] + "..."


def given_words(cv, answer_ids) -> list[str]:
    """These answers, one line each: field, value, entry. What a resumed run
    is told it was given."""
    got = {e["id"]: e for e in cv.corpus.read(list(answer_ids))}
    return [f"- {got[a]['body'].get('field')}: "
            f"{_quoted(got[a]['body'].get('value'))} ({a})"
            for a in answer_ids if a in got]


def handed_words(state) -> list[str]:
    """The answers of a set as they stand, one line a field, in words."""
    lines = []
    for f in sorted(state["fields"]):
        v = state["fields"][f]
        if v["conflict"]:
            lines.append(f"- {f}: IN CONFLICT, "
                         + "; ".join(f"{_quoted(h['value'])} ({h['answer']}, "
                                     f"by {h['by_alias'] or h['by']})"
                                     for h in v["heads"]))
        else:
            lines.append(f"- {f}: {_quoted(v['value'])} ({v['answer']})")
    return lines


handed = responses.handed


def handover_words(handover) -> list[str]:
    """The own words and the interpretations of them, in words: each person's
    words as they now read, quoted in full, then each interpretation with its
    state, then what of the words no interpretation has cited."""
    lines = []
    for w in handover["words"]:
        lines.append(f"- own words of {w['by_alias'] or w['by']} "
                     f"({w['words']}), exactly as written:")
        lines += ["    > " + line for line in w["text"].splitlines() or [""]]
        for gap in w["not_cited"]:
            lines.append(f"    not yet interpreted: {_quoted(gap['excerpt'])!r} "
                         f"(code points {gap['start']}-{gap['end']})")
    for p in handover["proposals"]:
        what = p["proposes"]
        said = (f"set {what['field']} to {_quoted(what['value'])}"
                if what["type"] == "set-field" else
                f"add row {_quoted(what['row'])}" if what["type"] == "add-row"
                else f"add field {_quoted(what['field'])}")
        lines.append(f"- interpretation {p['interpretation']} by "
                     f"{p['by_alias'] or p['by']} of {_quoted(p['excerpt'])!r}: "
                     f"{said}; {p['state'].upper()}"
                     + (f" (reply {p['reply']})" if p["reply"] else "")
                     + (f", answer {p['answer']}" if p["answer"] else "")
                     + (f", changed to {_quoted(p['changed_to'])}"
                        if p["changed_to"] else "")
                     + ("; read against an earlier wording"
                        if p["on_earlier_wording"] else ""))
    return lines


def resumed_words(cv, given) -> list[str]:
    """`handover_words` for what a `work-resumed` act recorded it handed
    (`given`: its `words` and `proposals`), read from those exact entries,
    which never change, with each interpretation's state as it was then."""
    ids = list(given.get("words") or ()) + [
        x for p in given.get("proposals") or ()
        for x in (p["interpretation"], p.get("reply")) if x]
    got = {e["id"]: e for e in cv.corpus.read(ids)} if ids else {}
    current = set(given.get("words") or ())
    words = []
    for wid in given.get("words") or ():
        w = got.get(wid)
        if w is None:
            continue
        text = w["body"]["text"]
        cited = sorted((got[p["interpretation"]]["body"]["passage"]["start"],
                        got[p["interpretation"]]["body"]["passage"]["end"])
                       for p in given.get("proposals") or ()
                       if p["interpretation"] in got
                       and got[p["interpretation"]]["body"]["words"] == wid)
        words.append({"words": wid, "text": text, "by": w["attributed_to"],
                      "by_alias": cv.alias(w["attributed_to"]),
                      "not_cited": responses._gaps(text, cited)})
    proposals = []
    for p in given.get("proposals") or ():
        i = got.get(p["interpretation"])
        if i is None:
            continue
        b = i["body"]
        src = cv.corpus.read([b["words"]])
        text = src[0]["body"]["text"] if src else ""
        proposals.append({**p, "by": i["attributed_to"],
                          "by_alias": cv.alias(i["attributed_to"]),
                          "excerpt": text[b["passage"]["start"]:
                                          b["passage"]["end"]],
                          "proposes": b["proposes"],
                          "changed_to": (got.get(p.get("reply")) or {}).get(
                              "body", {}).get("changed_to"),
                          "on_earlier_wording": b["words"] not in current})
    return handover_words({"words": words, "proposals": proposals})


def send_back(st, sid, *, by, written_by=None, op=None) -> tuple[dict, list]:
    """Send back: hand the set's answers as they stand to the agent that
    wrote the block's post, asking it to continue. Returns (answer,
    dispatches to start); raises `Refused`."""
    cv, corpus = st.cv, st.corpus
    now = responses.state(cv, sid)
    root = now["post"]
    if now["source_deleted"]:
        raise Refused({"error": "the post this block is in was deleted, so "
                                "there is nothing to send back from",
                       "source_deleted": True, "set": sid})
    author = corpus.read([root])[0].get("attributed_to")
    if not author or author == by:
        raise Refused({"error": "you wrote the post this block is in, so "
                                "there is no agent to send it back to",
                       "set": sid, "post": root})
    answers = sorted(h["answer"] for v in now["fields"].values()
                     for h in v["heads"])
    given = responses.handover(cv, sid)
    if not answers and not given["words"]:
        raise Refused({"error": "nothing in this block has been answered "
                                "yet, so there is nothing to send back",
                       "set": sid})
    ready = now.get("marked_ready")
    words = "\n".join(
        [f"Sent back to you to act on now: the answers in `{now['block']}` "
         f"(response set {sid}) on post {root}, as they stand"
         + (" (marked ready)" if now["ready"] else
            " (changed since it was marked ready)"
            if now["changed_since_ready"] else " (not marked ready)") + ":"]
        + (handed_words(now) or ["- no field answered"])
        + handover_words(given))
    cid = cv.conversation_of(root)
    body = {"author": by, "text": words, "replies_to": root,
            "action": posting.ASK_PARTICIPANT,
            "dispatch": [{"participant": author, "work": words}],
            "because": "the owner sent the answers back to the agent that "
                       "asked for them",
            **({"op": op} if op else {})}
    with corpus.atomic():
        out, later = posting.post(cv, corpus, cid, body, agents=st.agents,
                                  written_by=lambda: written_by)
        if "error" in out:
            raise Refused(out)
        if not out.get("replayed"):
            exps = list(out.get("expectations") or ())
            out["sent_back"] = cv.record_act(
                actor=by, act=ANSWERS_SENT_BACK, conversation=cid,
                turn=out.get("turn"), caused_by=exps[0] if exps else None,
                about=[sid, *answers, *(w["words"] for w in given["words"])],
                because="sent back to the post's author, to act on now",
                detail={"set": sid, "post": root, "block": now["block"],
                        "to": author, "answers": answers,
                        "marked_ready": ready["entry"] if ready else None,
                        "ready": now["ready"],
                        "conflicts": now["conflicts"],
                        **handed(given),
                        "expectation": exps[0] if exps else None})
    return {**out, "set": sid, "to": author, "answers": answers,
            **handed(given)}, later
