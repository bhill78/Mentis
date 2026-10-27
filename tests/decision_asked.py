"""A decision asked as its own Turn, recorded exactly as `request_decision`
recorded every decision before forms build P9.

Since P9 `request_decision` makes a decision form for one question too, on
the run's answer post (or the post `on` names). The decisions the record
already holds were asked as their own Turn and keep the rule they always
had -- any reply of the owner's to that Turn answers them, a choice or a
withdrawal answers that Turn -- so the tests of that rule ask through this
helper instead: the same Turn, expectation and `decision-requested` act the
old path wrote, under the same grant.
"""

from __future__ import annotations

from mentis.conversation import text


def asked_as_own_turn(world, grant, question, options=None, because=None):
    from mentis.conversation.owner import _owner
    from mentis.worker import decision_options
    cv = world["cv"]
    actor, parent = grant["participant"], grant["expectation"]
    here, execution = grant["conversation"], grant.get("instance")
    runtime = grant.get("runtime")
    opts = decision_options(options)
    asked_by = cv.expectation_state(parent)["requested_by"]
    of = _owner(cv) or asked_by
    wrote = f"{runtime}/{(execution or '')[:8]}" if runtime else None
    turn = cv.say(here, actor, [text(question)], addressed_to=[of],
                  written_by=wrote)
    exp = cv.expect(turn, of=of, kind="decision", by=actor,
                    because=because or "a decision only the owner can make",
                    caused_by=parent,
                    detail={**({"options": opts} if opts else {}),
                            "requester": asked_by})
    cv.record_act(actor=actor, act="decision-requested", execution=execution,
                  runtime=runtime, conversation=here, turn=turn, about=[exp],
                  caused_by=parent)
    return {"ok": True, "turn": turn, "expectation": exp, "of": of,
            "requester": asked_by, **({"options": opts} if opts else {})}
