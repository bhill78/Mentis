"""Fixture-only record writes and Python's unchanged read/closure semantics.

The additive expected fields come from the committed part-B classifier vectors,
not a second implementation of their validation. This works before B is integrated.
No server, runtime, grant, live Brain or real work is opened.
"""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import mentis.api as api
from mentis.conversation import text
from mentis.fluid import home, route
from mentis.web import _routes
from mentis import worker

root = Path(sys.argv[1])
cases = {c["name"]: c for c in json.loads(Path(__file__).with_name("presentation_cases.json").read_text())["cases"]}
fields = {}
scenarios = []
worlds = {}

def enrich(value):
    if isinstance(value, list):
        return [enrich(v) for v in value]
    if isinstance(value, dict):
        out = {k: enrich(v) for k, v in value.items()}
        qid = out.get("expectation") or out.get("id")
        if qid in fields:
            out.update(copy.deepcopy(fields[qid]))
        return out
    return value

for name, names, closure in [
    ("open", ["choice", "commit"], None),
    ("pending", ["explicit-no-primary", "free-response"], None),
    ("closed", ["action", "choice", "legacy"], "close"),
    ("legacy", ["legacy-generic", "legacy-missing-consequence"], None),
    ("unsupported", ["unsupported-2", "unsupported-True"], None),
    ("malformed", ["forward-scope"], None),
    ("url", ["forward-url"], None),
    ("permission", ["legacy"], None),
    ("prose", ["legacy"], None),
]:
    corpus = api.create_corpus(str(root / name))
    brain = api.brain(corpus)
    cv = brain.conversations
    owner = cv.resolve_participant("@owner", about="the owner")
    agent = cv.resolve_participant("@reader", about="asks fixture questions")
    worlds[name] = (corpus, brain, cv)
    cid = cv.open_conversation("Decision parity " + name)
    cv.join(owner, cid)
    cv.join(agent, cid)
    request_post = cv.say(cid, owner, [text("Choose the next plan.")])
    request = cv.expect(request_post, of=agent, kind="result", by=owner, conversation=cid)
    post = None if name == "pending" else cv.say(cid, agent, [text("Please answer the recorded questions.")])
    fd = {"questions": len(names), "on": post}
    if name == "permission":
        fd.update(permission=True, operation={"summary": "Read a fixture", "command": "read fixture"}, run="fixture-run")
    if name == "prose":
        fd["from_prose"] = True
    form = cv.record_act(actor=agent, act="decision-form", conversation=cid, turn=post,
                         caused_by=request, because="Recorded context.", detail=fd)
    ids = []
    for i, case_name in enumerate(names):
        case = copy.deepcopy(cases[case_name])
        detail = {**case["detail"], "form": form, "index": i}
        if name == "permission":
            detail["options"] = [{"label": "Allow once", "consequence": "Allow this operation once."},
                                 {"label": "Deny", "consequence": "Refuse this operation."}]
        qid = cv.expect(post, of=owner, kind="decision", by=agent, conversation=cid,
                        caused_by=request, because=case["because"], detail=detail)
        fields[qid] = case["fields"]
        ids.append(qid)
    if closure:
        cv.record_act(actor=owner, act="decision-answered", conversation=cid, turn=post, caused_by=ids[0],
                      detail={"reply": post, "option": 1, "label": "Plan B"})
        cv.record_act(actor=owner, act="expectation-met", conversation=cid, turn=post, caused_by=ids[0])
        cv.record_act(actor=owner, act="expectation-met", conversation=cid, turn=post, caused_by=ids[1],
                      because="Please clarify the boundary.", detail={"withdrawn": True, "reply": post})
        cv.record_act(actor=agent, act="expectation-met", conversation=cid, turn=post, caused_by=ids[2],
                      because="Permission expired.", detail={"lapsed": {"reason": "expired", "run": "fixture-run"}})
    scenarios.append({"name": name, "brain": str(root / name), "conversation": cid, "post": post, "form": form, "ids": ids,
                      "native": all(cases[n]["native"] for n in names)})

for s in scenarios:
    corpus, brain, cv = worlds[s["name"]]
    st = SimpleNamespace(corpus=corpus, cv=cv, brain=brain)
    s["form_answer"] = enrich(cv.decision_form(s["form"]))
    s["states"] = []
    for qid in s["ids"]:
        row = enrich(cv.expectation_state(qid))
        row["durable_open"] = row.pop("live_execution")
        s["states"].append(row)
    s["decisions"] = enrich(route(st, "/fluid/api/decisions", {"ids": [",".join(s["ids"])]}))
    s["asks"] = enrich(home.asks(st, s["ids"]))
    surface = worker.Surface(s["brain"], corpus=corpus)
    s["worker_answers"] = []
    for ref in [s["form"], *([s["post"]] if s["post"] else [])]:
        s["worker_answers"].append({"args": {"ref": ref},
                                    "answer": enrich(worker._result(surface, "resolve", {"ref": ref}))})
    if s["post"]:
        s["turn_view"] = enrich(_routes(st, f"/api/turns/{s['post']}", {}, {}, "GET"))
        s["thread"] = enrich(_routes(st, f"/api/conversations/{s['conversation']}/thread/{s['post']}", {}, {}, "GET"))
print(json.dumps({"scenarios": scenarios, "owner": owner}))
for corpus, _, _ in worlds.values():
    corpus.close()
