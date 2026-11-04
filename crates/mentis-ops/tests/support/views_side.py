"""Build the ordinary web fixture once and say R4.2's Python answers from that exact Brain."""
import json
import sys
from types import SimpleNamespace

from mentis.web.fixture import build
from mentis.web import _routes

root = sys.argv[1]
w = build(root)
st = SimpleNamespace(corpus=w["corpus"], cv=w["cv"], brain=w["brain"])
cid = w["design"]
turn = w["cv"].turns(cid)[0]["turn"]
expectation = next(a["id"] for a in w["corpus"].operational(turn=turn)
                   if a["act"] == "expectation-recorded")
# The record already says one instance is open, while the machine-local registry contributes its
# boundary reference.  Raw state therefore has two refs; every R4.2 GET below may expose only bool.
w["cv"].record_act(actor=w["who"]["@Nadia"], act="execution-started",
                   conversation=cid, turn=turn, caused_by=expectation,
                   execution="instance-durable", runtime="codex")
# An unassigned intake request is resumable until a machine-local execution carries it.  This
# exercises intake's liveness branch with an overlay-only reference, not merely its JSON shape.
intake_turn = w["cv"].say(cid, w["who"]["@Nadia"],
                          [{"type": "text", "text": "Please carry this request."}])
intake_expectation = w["cv"].record_act(
    actor=w["who"]["@Nadia"], act="expectation-recorded",
    conversation=cid, turn=intake_turn, detail={"expects": "result"})
w["cv"].record_act(actor=w["who"]["@Nadia"], act="assignment-unresolved",
                   conversation=cid, turn=intake_turn, caused_by=intake_expectation,
                   because="nobody designated")
intake_without_live = _routes(st, "/api/intake", {}, {}, "GET")
w["cv"].begin_execution(participant=w["who"]["@Nadia"], conversation=cid,
                         for_expectation=intake_expectation, runtime="codex")
# What Python's writers don't make, and its readers answer: a blank alias shows the reference, and a
# blank runtime is `auto`. These come from R4.1's rules in `lists`, which the views share.
blank = w["corpus"].write(kind="participant", body={"alias": ""}, attributed_to=w["who"]["@Nadia"])
w["cv"].join(blank, cid, attributed_to=w["who"]["@Nadia"])
blank_runtime = w["corpus"].write(kind="runtime-default", body={"participant": blank, "runtime": ""},
                                  attributed_to=w["who"]["@Nadia"])
w["corpus"].establish(blank_runtime, attributed_to=w["who"]["@Nadia"], reason="blank")
form_expectation = next((a["id"] for a in w["corpus"].operational()
                         if a["act"] == "expectation-recorded"
                         and (a.get("detail") or {}).get("form")), None)
answers = {
    "conversation": cid,
    "turn": turn,
    "expectation": expectation,
    "active": w["cv"].active_execution_rows(),
    "raw_live": w["cv"].expectation_state(expectation)["live_execution"],
    "personas": _routes(st, "/api/personas", {}, {}, "GET"),
    "fields": _routes(st, f"/api/conversations/{cid}",
                      {"fields": ["name,about,participants,topics"]}, {}, "GET"),
    "intake": _routes(st, "/api/intake", {}, {}, "GET"),
    "intake_without_live": intake_without_live,
    "intake_expectation": intake_expectation,
    "turn_view": _routes(st, f"/api/turns/{turn}", {}, {}, "GET"),
    "turns": _routes(st, "/api/turns", {"ids": [turn]}, {}, "GET"),
    "thread": _routes(st, f"/api/conversations/{cid}/thread/{turn}", {}, {}, "GET"),
    "decisions": __import__("mentis.fluid", fromlist=["route"]).route(
        st, "/fluid/api/decisions", {"ids": [expectation]}),
    "form_expectation": form_expectation,
}
if form_expectation:
    answers["form_decisions"] = __import__("mentis.fluid", fromlist=["route"]).route(
        st, "/fluid/api/decisions", {"ids": [form_expectation]})
# Exercise every ordinary fixture Turn, not only the first one.  Held image/file and anchor parts
# deliberately stay on Python because annotating them reaches held files (and, for anchors, the
# immutable source version); the Rust operation must identify that boundary before answering.
answers["text_turns"] = []
answers["held_turns"] = []
for conversation in w["cv"].all_conversations():
    for item in w["cv"].turns(conversation["id"]):
        tid = item["turn"]
        part_types = [part.get("type") for part in item["entry"]["body"].get("parts", [])]
        if all(kind == "text" for kind in part_types):
            answers["text_turns"].append({
                "id": tid,
                "answer": _routes(st, f"/api/turns/{tid}", {}, {}, "GET"),
            })
        else:
            answers["held_turns"].append(tid)
print(json.dumps(answers))
w["corpus"].close()
