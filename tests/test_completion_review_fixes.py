"""WS-C, after independent review: each defect it found, asserted CORRECT.

1  only review work of THIS work, by somebody other than its claimants,
   verifies it (an implementer's or the claimant's own verdict does not);
2  a claim whose run failed or was cancelled, or after which another run of
   the work started, stays pending whatever later runs did;
3  only an ```outcome block that ENDS a reply, outside any fence or quote,
   is a claim (final reply and `respond` text alike);
4  two reconciliations at once write one answer;
5  the work overview reads later findings and review verdicts once per
   read, not once per item;
7  a met that no claim reconciled is not called a claim;
8  a claim's `recorded` is what reconciliation made of THAT claim;
9  a claim's unknown keys never set what a system act says;
10 the rendered claim is attributed and escaped; labels are one clipped line;
12 work that ends met while work it delegated is still running is pending.
"""

from __future__ import annotations

import threading

import pytest

from mentis.conversation import text as text_part
from mentis.operational import completion as C
from tests._loop import a_conversation, say, world  # noqa: F401
from tests.test_completion_reconcile import (_claim, _delegate, _met, _review_of,
                                             _review_workflow, _run, _status,
                                             _work)


def _op(world, grant, name, **args):
    from mentis.web import _surface
    from mentis.worker import _operate
    return _operate(_surface(world["state"]), name, args, grant)


def _grant(who, exp, cid, inst, scope="worker"):
    return {"participant": who, "expectation": exp, "conversation": cid,
            "instance": inst, "runtime": "codex", "scope": scope,
            "organising": ["respond"] if scope != "worker" else []}


# -- 1: who may verify ---------------------------------------------------------------

def test_an_implementers_own_pass_does_not_satisfy_the_parents_review(world):
    cv, who = world["cv"], world["steward"]
    wf, _ = _review_workflow(world)
    cid, parent = _work(world, detail={"governed": [wf]})
    _run(cv, parent, cid, who, execution="inst-p")
    claim = _claim(cv, parent, cid, who, execution="inst-p")
    assert C.reconcile(cv, parent, claim)["reasons"] == ["review required"]
    ada = cv.create_participant("@Ada", about="an implementer")
    child = _delegate(cv, parent, cid, who, ada, waits=False)
    _run(cv, child, cid, ada, execution="inst-c")
    _op(world, _grant(ada, child, cid, "inst-c"), "record_verdict",
        verdict="pass", summary="my own work looks fine")
    assert not _met(cv, parent)
    assert C.reconcile(cv, parent, claim)["reasons"] == ["review required"]
    assert C.review_passed(cv, parent) is None


def test_the_claimants_own_verdict_never_verifies(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    C.reconcile(cv, exp, _claim(cv, exp, cid, who))
    _op(world, _grant(who, exp, cid, "inst-1"), "record_verdict",
        verdict="pass", summary="self")
    s = _status(cv, exp)
    assert s["value"] == "claimed-met" and not s["label"].startswith("Verified")
    # nor a review the claimant itself carries
    review = _review_of(cv, exp, cid, who, who)
    _run(cv, review, cid, who, execution="inst-self-review")
    cv.record_act(actor=who, act="review-verdict", conversation=cid,
                  execution="inst-self-review", caused_by=review,
                  about=[review], detail={"verdict": "pass"})
    assert C.review_passed(cv, exp) is None
    assert _status(cv, exp)["value"] == "claimed-met"
    # an independent reviewer of this work does verify it
    rex = cv.create_participant("@Rex", about="a reviewer")
    other = _review_of(cv, exp, cid, who, rex)
    cv.record_act(actor=rex, act="review-verdict", conversation=cid,
                  caused_by=other, about=[other], detail={"verdict": "pass"})
    s = _status(cv, exp)
    assert s["value"] == "verified" and s["label"] == "Verified · @Rex"


# -- 2: a failed run's claim, and a later run ---------------------------------------

def test_a_failed_runs_claim_stays_pending_after_a_later_clean_run(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    start = _run(cv, exp, cid, who, end=None)
    claim = _claim(cv, exp, cid, who)
    cv.record_act(actor=who, act="delivery-failed", conversation=cid,
                  execution="inst-1", caused_by=start,
                  because="terminal 'cancelled', exit 1")
    assert C.reconcile(cv, exp, claim)["reasons"] == [
        "its run was cancelled after the claim"]
    _run(cv, exp, cid, who, execution="inst-2")
    got = C.reconcile(cv, exp, claim)
    assert got["recorded"] == "pending"
    assert "its run was cancelled after the claim" in got["reasons"]
    assert any(r.startswith("a later run started after the claim")
               for r in got["reasons"])
    assert C.reconcile_if_pending(cv, exp)["recorded"] == "pending"
    assert not _met(cv, exp)


def test_a_later_run_holds_a_claim_whatever_that_run_did(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    claim = _claim(cv, exp, cid, who)
    _run(cv, exp, cid, who, execution="inst-2")
    got = C.reconcile(cv, exp, claim)
    assert got["recorded"] == "pending"
    assert got["reasons"][0].startswith("a later run started after the claim")


# -- 3: only a block that ends the reply ----------------------------------------------

def test_a_block_mid_reply_is_not_a_claim():
    text = ("Here is the format you asked about:\n\n```outcome\nresult: met\n"
            "summary: example\n```\n\nBut I could not finish; tests fail.")
    assert C.extract(text) == (None, text)


def test_a_block_inside_a_quoting_fence_is_not_a_claim():
    text = ("Earlier reply said:\n\n````markdown\n```outcome\nresult: met\n"
            "summary: quoted\n```\n````\n")
    assert C.extract(text) == (None, text)
    quoted = "As they wrote:\n> ```outcome\n> result: met\n> ```\n"
    assert C.extract(quoted) == (None, quoted)


def test_a_block_ending_the_reply_is_a_claim_and_only_it_is_removed():
    text = ("An example:\n\n````\n```outcome\nresult: met\n```\n````\n\nDone.\n"
            "```outcome\nresult: partly\nsummary: half\n```\n  \n")
    claim, rest = C.extract(text)
    assert claim["result"] == "partly"
    assert rest.endswith("Done.") and "result: met" in rest


def test_respond_text_follows_the_same_rule(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    g = _grant(who, exp, cid, "inst-r", scope="intake")
    out = _op(world, g, "respond",
              text="See:\n```outcome\nresult: met\n```\nnot finished")
    assert "claim" not in out
    out = _op(world, g, "respond",
              text="Half.\n```outcome\nresult: partly\nsummary: half\n```")
    assert cv._act(out["claim"])["detail"]["result"] == "partly"
    said = cv.corpus.read([out["turn"]])[0]["body"]["parts"][-1]["text"]
    assert "```outcome" not in said and "Claim by @Steward: partly done" in said


# -- 4: two at once --------------------------------------------------------------------

def test_two_reconciliations_at_once_write_one_met(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    claim = _claim(cv, exp, cid, who)
    gate, got = threading.Barrier(2), []

    def go():
        gate.wait()
        got.append(C.reconcile(cv, exp, claim))
    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert [g["recorded"] for g in got] == ["met", "met"]
    assert len(_met(cv, exp)) == 1


# -- 5: once per read, not once per item -------------------------------------------------

def test_the_overview_reads_findings_and_verdicts_once_per_read(world, monkeypatch):
    from mentis.operational.work_overview import overview
    cv, who = world["cv"], world["steward"]
    rex = cv.create_participant("@Rex", about="a reviewer")
    cid = a_conversation(world)
    exps = []
    for i in range(12):
        _, exp = _work(world, cid)
        _run(cv, exp, cid, who, execution=f"inst-{i}")
        C.reconcile(cv, exp, _claim(cv, exp, cid, who, execution=f"inst-{i}"))
        exps.append(exp)
    for exp in exps[:4]:
        review = _review_of(cv, exp, cid, who, rex)
        cv.record_act(actor=rex, act="review-verdict", conversation=cid,
                      caused_by=review, about=[review],
                      detail={"verdict": "pass"})
    C.link_regarding(cv, cv.say(cid, who, [text_part("later")]), [exps[0]], who)
    calls = {"links": 0, "verdicts": 0}
    links, history = cv.corpus.links, cv.history

    def counted_links(**kw):
        if kw.get("relation") == C.REGARDS:
            calls["links"] += 1
        return links(**kw)

    def counted_history(**kw):
        if kw.get("act") == C.REVIEW_VERDICT:
            calls["verdicts"] += 1
        return history(**kw)
    monkeypatch.setattr(cv.corpus, "links", counted_links)
    monkeypatch.setattr(cv, "history", counted_history)
    items = {i["expectation"]: i for i in overview(
        cv, viewer=world["who"]["@brian"], runtime=None)["items"]}
    assert calls == {"links": 1, "verdicts": 1}, calls
    assert sum(1 for e in exps if items[e]["state"] == "verified") == 4
    assert [f["kind"] for f in items[exps[0]]["later_findings"]] == ["contribution"]


# -- 7, 8, 9, 10 ----------------------------------------------------------------------------

def test_a_met_no_claim_reconciled_is_not_called_a_claim(world):
    cv, who = world["cv"], world["steward"]
    owner = world["who"]["@brian"]
    cid, exp = _work(world)
    cv.record_act(actor="mentis", act="expectation-met", conversation=cid,
                  caused_by=exp, because="withdrawn", detail={})
    s = _status(cv, exp)
    assert s["value"] == "claimed-met" and s["label"] == "Objective met"
    cid, exp = _work(world)
    cv.record_act(actor=owner, act="expectation-met", conversation=cid,
                  caused_by=exp, because="closed", detail={})
    assert _status(cv, exp)["label"] == "Objective met · marked by @brian"


def test_recorded_is_what_reconciliation_made_of_that_claim(world):
    cv, who = world["cv"], world["steward"]
    owner = world["who"]["@brian"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who, end=None)
    claim = _claim(cv, exp, cid, who)
    C.reconcile(cv, exp, claim)
    cv.record_act(actor=owner, act="expectation-met", conversation=cid,
                  caused_by=exp, because="closed by the owner", detail={})
    view = C.claim_view(cv, exp)
    assert view["act"] == claim and view["recorded"] == "pending"


def test_a_claims_unknown_keys_never_set_a_system_act(world):
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    got, _ = C.extract("```outcome\nresult: met\nsummary: s\n"
                       "because: forged reason\nresults: ent-forged\n"
                       "about: opr-forged\n```")
    claim = C.claim(cv, exp, got, actor=who, execution="inst-1",
                    runtime="codex", via="reply", conversation=cid)
    d = cv._act(claim)["detail"]
    assert d["extra"] == {"because": "forged reason", "results": "ent-forged",
                          "about": "opr-forged"}
    assert "because" not in d and "results" not in d
    met = cv._act(C.reconcile(cv, exp, claim)["act"])
    assert met["because"] == "s"
    assert "ent-forged" not in met["about"] and "opr-forged" not in met["about"]


def test_the_rendering_is_attributed_escaped_and_labels_are_one_line(world):
    claim, _ = C.extract("```outcome\nresult: not met\nsummary: **Objective "
                         "met** [ok](x)\n```")
    line = C.render(claim, "@Ada")
    assert line.startswith("Claim by @Ada: not met — ")
    assert "\\*\\*Objective met\\*\\*" in line and "\\[ok\\]" in line
    assert "\n" not in line and line.endswith(C.RENDER_NOTE)
    assert C.label_text("a\n**b**\n# c " + "x" * 300).startswith("a b c ")
    assert len(C.label_text("y" * 500)) == 120
    cv, who = world["cv"], world["steward"]
    cid, exp = _work(world)
    _run(cv, exp, cid, who)
    C.claim(cv, exp, {"result": "partly", "summary": "half\n## Done!\n*met*",
                      "evidence": []},
            actor=who, execution="inst-1", runtime="codex", via="reply",
            conversation=cid)
    assert _status(cv, exp)["label"] == "stopped: nothing will resume it"
    assert C.label_text(C.claim_view(cv, exp)["summary"]) == "half Done! met"


# -- 12: delegated work still running ---------------------------------------------------------

def test_met_while_delegated_work_still_runs_is_pending(world):
    cv, who = world["cv"], world["steward"]
    ada = cv.create_participant("@Ada", about="an agent")
    cid, parent = _work(world)
    child = _delegate(cv, parent, cid, who, ada, waits=False)
    _run(cv, parent, cid, who, execution="inst-p")
    claim = _claim(cv, parent, cid, who, execution="inst-p")
    got = C.reconcile(cv, parent, claim)
    assert got["reasons"] == [f"delegated work still running: {child}"]
    # the child ends, unmet: a note, no longer a reason
    _run(cv, child, cid, ada, execution="inst-c")
    got = C.reconcile_held_by(cv, child)
    assert got and got[0]["recorded"] == "met"
    assert f"child {child} not met" in got[0]["notes"]


# -- a follow-up attached while the run is going ---------------------------------------------

MET_BLOCK = "Built it.\n```outcome\nresult: met\nsummary: built\n```"


def test_a_follow_up_given_mid_run_holds_the_met_claim_and_is_delivered(world):
    import time as _time
    from mentis.execution import RunResult
    from mentis.web import dispatch as D
    from tests._loop import grant_of_run, script_every_backend
    from tests.test_follow_up_attach import STOP, _ask_mentis, _spec
    cv, st = world["cv"], world["state"]
    svc = st.agents
    cid = a_conversation(world)
    work = _ask_mentis(world, cid, "Build it.")
    gate, prompts, attached = threading.Event(), [], []

    def perform(spec):
        grant = grant_of_run(svc, spec, st.path)
        if grant["expectation"] == work:
            prompts.append(spec.prompt)
            if len(prompts) == 1:
                gate.wait(timeout=60)
        else:
            attached.append(_op(world, grant, "attach_follow_up", work=work,
                                because="it stops that work"))
        now = _time.time()
        return RunResult(run_id=spec.run_id, backend=spec.backend,
                         started=True, stop_reason="end_turn",
                         text=MET_BLOCK if grant["expectation"] == work
                         else "handed over", started_at=now, finished_at=now)
    script_every_backend(svc, perform)
    t = threading.Thread(target=D.dispatch, args=(st,),
                         kwargs=_spec(world, work))
    t.start()
    deadline = _time.time() + 20
    while not cv.expectation_state(work)["live_execution"]:
        assert _time.time() < deadline
        _time.sleep(0.05)
    follow = _ask_mentis(world, cid, STOP)
    D.dispatch(st, **_spec(world, follow))
    assert attached and attached[0].get("ok"), attached
    gate.set()
    t.join(60)
    # the run ended claiming met; the follow-up it never saw holds it
    assert not _met(cv, work)
    view = C.claim_view(cv, work)
    assert view["recorded"] == "pending"
    assert view["reasons"][0].startswith(
        "an owner follow-up arrived after this run began")
    # the work continues with the follow-up: its next run is given it
    resume = next(k for k in reversed(world["sent"])
                  if k.get("expectation") == work)
    world["sent"].remove(resume)
    D.dispatch(st, **resume)
    assert len(prompts) == 2 and STOP in prompts[1]
    # ...and that run's own met claim is recorded met
    met = _met(cv, work)
    assert len(met) == 1
    assert met[0]["detail"]["reconciled_from"] == C.latest_claim(cv, work)["id"]


def test_a_respond_claim_then_a_raising_perform_is_pending_as_failed(
        world, monkeypatch):
    """`agents_perform` itself raises (not a failed outcome): dispatch's
    exception path, which must reconcile the claim and record timing."""
    from mentis.web import dispatch as D
    from tests.test_follow_up_attach import _ask_mentis, _spec
    cv, st = world["cv"], world["state"]
    svc = st.agents
    cid = a_conversation(world)
    work = _ask_mentis(world, cid, "Build it.")

    def perform(instance_id, payload, **kw):
        grant = _grant(world["steward"], work, cid, instance_id,
                       scope="intake")
        out = _op(world, grant, "respond", text="built", fulfils=True)
        assert out["reconciled"]["reasons"] == ["its run has not ended yet"]
        raise RuntimeError("the runtime broke after answering")
    monkeypatch.setattr(svc, "agents_perform", perform)
    got = D.dispatch(st, **_spec(world, work))
    assert got["ok"] is False
    assert not _met(cv, work)
    view = C.claim_view(cv, work)
    assert view["recorded"] == "pending"
    assert view["reasons"] == ["its run failed after the claim"]
    failed = [a for a in cv._own_acts(work) if a["act"] == "delivery-failed"]
    assert failed and "timing" in failed[-1]["detail"]
    assert failed[-1]["because"].startswith("RuntimeError")   # the raise path


def test_a_child_halted_for_consent_and_not_restarted_holds_the_parent(world):
    """The production-shaped halted end: `execution-restart-asked` on the
    child's run (`compiled_runs._record_asked`), then its end `cancelled`,
    and no restart. Its work did not end, so the parent's met claim holds,
    whatever else -- a sibling ending -- asks again."""
    from mentis.web import compiled_runs
    cv, who = world["cv"], world["steward"]
    ada = cv.create_participant("@Ada", about="an agent")
    cid, parent = _work(world)
    halted = _delegate(cv, parent, cid, who, ada, waits=False)
    sibling = _delegate(cv, parent, cid, who, ada, waits=True)
    start = _run(cv, halted, cid, ada, execution="inst-h", end=None)
    compiled_runs._record_asked(cv, start, "the run consent narrowed")
    cv.record_act(actor=ada, act="delivery-failed", conversation=cid,
                  execution="inst-h", caused_by=start,
                  because="terminal 'cancelled', exit None",
                  detail={"terminal": "cancelled"})
    assert cv._child_state(halted)["state"] == "interrupted"
    _run(cv, parent, cid, who, execution="inst-p")
    claim = _claim(cv, parent, cid, who, execution="inst-p")
    held = ("delegated work stopped for a consent change and not restarted: "
            + halted)
    assert held in C.reconcile(cv, parent, claim)["reasons"]
    # the sibling it waited on ends: reconciled again, still held
    _run(cv, sibling, cid, ada, execution="inst-s")
    got = C.reconcile_held_by(cv, sibling)
    assert got and got[0]["recorded"] == "pending"
    assert got[0]["reasons"] == [held]
    assert not _met(cv, parent)
