"""The real Python side of the R4.1 seam: a running `_State`, its two snapshot producers and its own
`expectation_state`, on a BRAIN-SEED, answering one command per line so a test can move the record
and the registries between reads. `tests/live_seam.rs` is the other side.

    live_seam_side.py serve <brain>      read commands from stdin, answer each on one `@@ ` line
    live_seam_side.py copy <brain> <n>   a Brain copy's states, every expectation up to n, sampled
    live_seam_side.py digest <brain>     corpus.db's SHA-256, opening nothing but the file

What a real command can't write without a run in progress is written as those commands write it:
the shapes are `dispatch.py`'s, `worker.py`'s and `responses.py`'s, and Python's read is the judge.
"""

import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "crates" / "mentis-rules" / "tests" / "support"))

import python_side  # noqa: E402

import mentis.web as web  # noqa: E402
from mentis.execution import FakeExecution  # noqa: E402


def _text(words):
    return [{"type": "text", "text": words}]


class World:
    def __init__(self, brain):
        self.st = web._State(str(brain), execution=FakeExecution())
        self.cv = self.st.cv
        self.corpus = self.st.corpus
        self.owner = self.cv.resolve_participant("@r1-owner")
        self.agent = self.cv.resolve_participant("@r1-agent")
        self.known = python_side._named(self.corpus, "conversation", "R1 known conversation")
        self.second = python_side._named(self.corpus, "conversation", "R1 second conversation")
        self.ids = {}
        self.snapshots = web._LiveSnapshots()

    def asked(self, name, *, of=None, where=None, kind="result", **kw):
        where = where or self.known
        post = self.cv.say(where, self.owner, _text(f"asking: {name}"))
        made = self.cv.expect(post, of=self.agent if of is None else of, kind=kind, by=self.owner,
                              because=f"because {name}", conversation=where, **kw)
        self.ids[name] = made
        return made, post

    def act(self, act, *, under, execution=None, by=None, where=None, **kw):
        return self.cv.record_act(actor=by or self.agent, act=act, conversation=where or self.known,
                                  execution=execution, caused_by=under, **kw)

    def build(self):
        cv, agent, owner, known = self.cv, self.agent, self.owner, self.known
        self.asked("plain", requires=("code",), material=("ent-000000000000",),
                   detail={"options": [{"label": "one"}]})

        # Runs, by the rule in `closed_starts`.
        running, _ = self.asked("running")
        self.act("execution-started", under=running, execution="inst-running")
        cv.begin_execution(participant=agent, conversation=known, for_expectation=running)

        returned, _ = self.asked("returned")
        start = self.act("execution-started", under=returned, execution="inst-returned")
        self.act("result-returned", under=start, execution="inst-returned")

        reused, _ = self.asked("an earlier end doesn't close a later run")
        start = self.act("execution-started", under=reused, execution="inst-reused")
        self.act("result-recovered", under=start, execution="inst-reused")
        self.act("execution-started", under=reused, execution="inst-reused")

        later, _ = self.asked("a later end closes an earlier run")
        self.act("execution-started", under=later, execution="inst-later")
        start = self.act("execution-started", under=later, execution="inst-later")
        self.act("delivery-failed", under=start, execution="inst-later", because="it fell over")

        loose, _ = self.asked("an end under no start is placed by itself")
        self.act("execution-started", under=loose, execution="inst-loose-before")
        self.act("result-returned", under=loose, execution="inst-loose-before")
        self.act("result-returned", under=loose, execution="inst-loose-after")
        self.act("execution-started", under=loose, execution="inst-loose-after")

        nameless, _ = self.asked("a start naming no execution")
        self.act("execution-started", under=nameless)

        # What only the registry knows, and what it must not be mistaken for.
        unrecorded, _ = self.asked("unrecorded")
        cv.begin_execution(participant=owner, conversation=known, for_expectation=unrecorded)

        self.asked("fallback", of=owner)
        cv.begin_execution(participant=owner, conversation=known)

        self.asked("carrier busy in another conversation", of=owner, where=self.second)

        ended, _ = self.asked("ended handle")
        gone = cv.begin_execution(participant=agent, conversation=known, for_expectation=ended)
        cv.end_execution(gone.reference)

        # The rest of the state's width.
        replied, post = self.asked("replied")
        cv.say(known, agent, _text("a reply"), replies_to=post)

        met, _ = self.asked("met")
        self.act("expectation-met", under=met)

        unassigned = cv.expect(cv.say(known, owner, _text("nobody yet")), of=None, kind="result",
                               by=owner, conversation=known)
        self.ids["unassigned"] = unassigned

        reassigned, _ = self.asked("reassigned")
        self.act("expectation-assigned", under=reassigned, by=owner, about=[owner])
        self.act("expectation-assigned", under=reassigned, by=owner, about=[agent])
        self.act("expectation-assigned", under=reassigned, by=owner, about=[owner])

        parent, post = self.asked("delegated")
        child = cv.expect(post, of=owner, kind="result", by=agent, caused_by=parent, conversation=known)
        self.ids["delegated child"] = child
        self.act("work-delegated", under=parent, about=[child])
        self.act("expectation-met", under=child, by=owner)

        withdrawn, _ = self.asked("withdrawn", of=owner)
        self.act("expectation-met", under=withdrawn, by=owner, because="not wanted",
                 detail={"withdrawn": True, "reply": "ent-reply"})

        lapsed, _ = self.asked("lapsed")
        self.act("expectation-met", under=lapsed, because="the run ended",
                 detail={"lapsed": {"reason": "run-ended", "run": "opr-run"}})

        considered, _ = self.asked("reconsideration", of=owner, detail={"reconsideration": True})
        self.act("expectation-met", under=considered, by=owner, detail={"selections": []})
        unconsidered, post = self.asked("reconsideration replied", of=owner,
                                        detail={"reconsideration": True})
        cv.say(known, owner, _text("words that select nothing"), replies_to=post)

        # An input, answered by a marked-ready, as `responses.py` writes them.
        response_set = self.corpus.write(kind="response-set", attributed_to=owner, body={
            "post": post, "part": 0, "block": "c", "mode": "shared", "holder": None})
        ready = []
        for words in ("before the wait", "after the wait", "by somebody else"):
            by = agent if words == "by somebody else" else owner
            mark = self.corpus.write(kind="marked-ready", attributed_to=by, body={
                "set": response_set, "answers": [words]})
            self.corpus.write(body={"reason": "in the set"}, attributed_to=by, link={
                "from": mark, "to": response_set, "relation": "in-response-set"})
            ready.append(mark)
        self.asked("input", of=owner, kind="input",
                   detail={"response_set": response_set, "ready_before": ready[:1]})
        self.asked("input with nothing yet", of=owner, kind="input",
                   detail={"response_set": response_set, "ready_before": ready})
        self.asked("input with no set", of=owner, kind="input")

        # Decision forms: on a post, answered, attached later, and on no post yet.
        post = cv.say(known, agent, _text("a post asking things"))
        parent = cv.expect(post, of=agent, kind="request", by=owner, conversation=known)
        form = self.act("decision-form", under=parent, turn=post, detail={"questions": 2, "on": post})
        first = cv.expect(post, of=owner, kind="decision", by=agent, caused_by=parent, conversation=known,
                          detail={"options": [{"label": "Yes"}], "form": form, "index": 0,
                                  "question": "Which one?"})
        second = cv.expect(post, of=owner, kind="decision", by=agent, caused_by=parent, conversation=known,
                           detail={"form": form, "index": 1, "question": "And this?"})
        reply = cv.say(known, owner, _text("Yes"), replies_to=post)
        self.act("decision-answered", under=first, by=owner, detail={
            "reply": reply, "option": 0, "label": "Yes"})
        self.ids.update({"question answered": first, "question open": second})

        pending = self.act("decision-form", under=parent, detail={"questions": 1})
        unattached = cv.expect(post, of=owner, kind="decision", by=agent, caused_by=parent, conversation=known,
                               detail={"form": pending, "index": 0, "question": "On no post?"})
        self.ids["question on no post"] = unattached
        moved = self.act("decision-form", under=parent, detail={"questions": 1})
        attached = cv.expect(post, of=owner, kind="decision", by=agent, caused_by=parent, conversation=known,
                             detail={"form": moved, "index": 0, "question": "Attached later?"})
        self.act("decision-form-attached", under=moved, turn=post)
        self.ids["question attached later"] = attached

        self.ids["not an expectation"] = form

        # Runs the service holds: one going, with a question waiting, and one ended as a run ends.
        agents = self.st.agents
        agents.agents_open_run("inst-going", "opr-going")
        agents.execution._running.add("inst-going")
        agents._runs["opr-going"]["permissions"]["form-1"] = {"form": "form-1", "asked_at": 1.5}
        agents._runs["opr-going"]["feed"].activity = "Run npm test"
        agents.agents_open_run("inst-ended", "opr-ended")
        agents._runs["opr-ended"].update(
            performing_since=1.5, consent_applied=None, tooling={"mcp": ["mentis"], "n": 1.10},
            last_event={"kind": "k", "at": 2.5, "what": "w"},
            outcome={"stop_reason": "end_turn", "error_kind": None, "error": None,
                     "stopped": False, "session_ended": False})
        agents.agents_end_run("opr-ended")
        return {"ids": self.ids, "known": known, "owner": owner, "agent": agent}

    def states(self):
        out = {}
        for name, made in self.ids.items():
            if name == "not an expectation":
                continue
            state = self.cv.expectation_state(made)
            out[name] = {"state": state,
                         "view": web._expectation_view(self.st, state)["live_execution"]}
        held, self.cv._executions = self.cv._executions, {}
        try:
            for name, row in out.items():
                row["durable"] = self.cv.expectation_state(self.ids[name])
        finally:
            self.cv._executions = held
        return out

    def run(self, command, args):
        if command == "build":
            return self.build()
        if command == "states":
            return self.states()
        if command == "envelope":
            return json.loads(json.dumps({"text": web._live_answer(
                self.snapshots, self.st.agents, self.cv).decode()}))
        if command == "fields":
            return json.loads(web._live_answer(self.snapshots, self.st.agents, self.cv))["fields"]
        if command == "expect-running":
            made, _ = self.asked(args["name"])
            start = self.act("execution-started", under=made, execution=args["name"])
            handle = self.cv.begin_execution(participant=self.agent, conversation=self.known,
                                             for_expectation=made)
            return {"expectation": made, "start": start, "handle": handle.reference,
                    "execution": args["name"]}
        if command == "end-handle":
            self.cv.end_execution(args["handle"])
            return {"active": len(self.cv.active_executions())}
        if command == "end-durably":
            self.act("result-returned", under=args["start"], execution=args["execution"])
            return {}
        if command == "post":
            return {"post": self.cv.say(self.known, self.owner, _text("the record moves"))}
        if command == "state":
            return self.cv.expectation_state(args["expectation"])
        if command == "active-count":
            return {"count": len(self.cv.active_executions())}
        if command == "conversation-counts":
            out = {self.known: 0, self.second: 0}
            for execution in self.cv.active_executions():
                if execution.conversation in out:
                    out[execution.conversation] += 1
            return out
        if command == "field-sizes":
            return dict((name, len(text))
                        for name, text in web._added_live_fields(self.st.agents, self.cv))
        if command == "cap":
            web._LIVE_FIELDS_MOST = args["most"]
            return {}
        raise SystemExit(f"no {command!r}")


def serve(brain):
    world = World(brain)
    for line in sys.stdin:
        asked = json.loads(line)
        if asked["command"] == "quit":
            break
        print("@@ " + json.dumps(world.run(asked["command"], asked)), flush=True)


def copy(brain, most):
    corpus, cv = python_side._open(brain)
    ids = [a["id"] for a in corpus.operational(act="expectation-recorded")]
    step = max(1, len(ids) // int(most))
    answers = {}
    for made in ids[::step]:
        try:
            answers[made] = cv.expectation_state(made)
        except Exception as exc:                          # noqa: BLE001
            answers[made] = {"python_raised": f"{type(exc).__name__}: {exc}"}
    print(json.dumps({"total": len(ids), "answers": answers}))


def main():
    what, where = sys.argv[1], pathlib.Path(sys.argv[2])
    sys.stdout.reconfigure(encoding="utf-8")
    if what == "serve":
        serve(where)
    elif what == "copy":
        copy(where, sys.argv[3])
    elif what == "digest":
        print(hashlib.sha256((where / "corpus.db").read_bytes()).hexdigest())
    else:
        raise SystemExit(f"no {what!r}")


if __name__ == "__main__":
    main()
