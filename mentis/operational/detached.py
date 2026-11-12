"""Request-bound detached verdicts. Nothing here starts or monitors a process."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

ARMED = "detached-armed"
REPORTED = "detached-reported"
RESULTS = ("succeeded", "failed", "rolled_back", "unknown")


def report_path(path):
    match = re.fullmatch(r"/api/detached/(opr-[A-Za-z0-9-]+)/report", path)
    return match.group(1) if match else None


def operations(cv, expectation):
    """Public, read-only projection; the report secret is never projected."""
    own = cv._own_acts(expectation)
    reports = {a["detail"]["operation"]: a for a in own if a["act"] == REPORTED}
    return [{"operation": a["id"], "what": a["detail"]["what"],
             "result_location": a["detail"]["result_location"],
             "pid": a["detail"].get("pid"), "arming_post": a["turn"],
             "armed_at": a["at"], "report": reports.get(a["id"]),
             "status": ("reported: " + reports[a["id"]]["detail"]["result"]
                        if a["id"] in reports else
                        f"armed {a['at']}, no report yet")}
            for a in own if a["act"] == ARMED]


def arm(cv, expectation, *, actor, execution, runtime, what,
        result_location, arming_post, pid=None):
    exp = cv._act(expectation)
    if not exp or exp["act"] != "expectation-recorded":
        raise ValueError("arm_detached needs the request this run carries")
    if not isinstance(what, str) or not what.strip() or not isinstance(
            result_location, str) or not result_location.strip():
        raise ValueError("say what is detached and where its result will appear")
    if pid is not None and (type(pid) is not int or pid <= 0):
        raise ValueError("pid is a positive integer if known")
    posts = cv.corpus.read([arming_post]) if isinstance(arming_post, str) else []
    if (not posts or not cv._is(posts[0], "contribution")
            or cv.conversation_of(arming_post) != exp["conversation"]
            or posts[0].get("attributed_to") != actor):
        raise ValueError("arming_post must be your promise post in this request's conversation")
    token = secrets.token_urlsafe(32)
    with cv.corpus.atomic():
        if cv.expectation_state(expectation)["satisfied_by"]:
            raise ValueError("cannot arm detached work on a met or withdrawn request")
        starts = [a for a in cv._own_acts(expectation)
                  if a["act"] == "execution-started" and a.get("execution") == execution]
        order = cv._write_order([a["id"] for a in starts])
        arming_run = max(starts, key=lambda a: order[a["id"]])["id"] if starts else None
        operation = cv.record_act(
            actor=actor, act=ARMED, conversation=exp["conversation"],
            turn=arming_post, execution=execution, runtime=runtime,
            caused_by=expectation, about=[expectation, arming_post],
            because=what.strip(), detail={"what": what.strip(),
                "result_location": result_location.strip(), "pid": pid,
                "arming_run": arming_run,
                "token_hash": hashlib.sha256(token.encode()).hexdigest()})
    return {"ok": True, "operation": operation, "expectation": expectation,
            "report_token": token, "report_path": f"/api/detached/{operation}/report",
            "note": "Give report_token only to this helper. It can report once. "
                    "Mentis does not start, monitor or check the helper."}


def stopped_by_owner(cv, operation):
    """A token never overrides Stop on the run that armed its helper."""
    arm = cv._act(operation)
    run = ((arm or {}).get("detail") or {}).get("arming_run")
    return bool(run and cv._c.operational(
        act="execution-stop-asked", caused_by=run))


def report(st, operation, body):
    """One token, one verdict, one reply. Resume only via claim_resumption."""
    cv = st.cv
    with cv.corpus.atomic():
        arm = cv._act(operation)
        token = body.get("token")
        if (not arm or arm["act"] != ARMED or not isinstance(token, str)
                or not hmac.compare_digest(
                    arm["detail"]["token_hash"], hashlib.sha256(token.encode()).hexdigest())):
            raise PermissionError("no armed operation with this report token")
        parent = arm["caused_by"]
        if any(a["act"] == REPORTED and a["detail"].get("operation") == operation
               for a in cv._own_acts(parent)):
            raise PermissionError("this operation has already reported; the token is spent")
        result, summary = body.get("result"), body.get("summary")
        evidence = body.get("evidence", [])
        if result not in RESULTS or not isinstance(summary, str) or not summary.strip():
            raise ValueError("report result is succeeded|failed|rolled_back|unknown, with a summary")
        if not isinstance(evidence, list) or not all(isinstance(e, str) for e in evidence):
            raise ValueError("evidence is a list of paths, commits or record ids")
        from mentis.conversation import text
        turn = cv.say(arm["conversation"], arm["actor"], [text(
            f"Detached operation {operation} on request {parent}: {result}\n\n"
            + summary.strip() + "\n\n" + "\n".join(evidence))],
            replies_to=arm["turn"], written_by="detached-report")
        act = cv.record_act(
            actor=arm["actor"], act=REPORTED, conversation=arm["conversation"],
            turn=turn, caused_by=parent, about=[operation, parent, arm["turn"]],
            because=summary.strip(), detail={"operation": operation, "result": result,
                "summary": summary.strip(), "evidence": evidence,
                "arming_post": arm["turn"], "expectation": parent,
                "reported_by": "operation-token"})
    # Outside the report transaction: dispatch observes the durable report.
    resumed = cv.claim_resumption(parent, event={"kind": REPORTED,
        "operation": operation, "report": act, "arming_post": arm["turn"],
        "expectation": parent})
    if resumed:
        from mentis.web.dispatch import _resume
        _resume(st, parent, resumed)
    return {"ok": True, "operation": operation, "report": act, "turn": turn,
            "expectation": parent, "resumed": resumed}
