"""Explicit outcome/question binding, inside completion's write transaction."""
from __future__ import annotations

import hashlib
import json

from mentis.decision_presentation import InvalidDecision, validate_batch


def normalize(raw):
    if not isinstance(raw, dict) or raw.get("mode") not in ("existing", "create"):
        raise InvalidDecision([{"path": "approval.mode", "code": "use_existing_or_create_not_artifact_shorthand"}])
    mode = raw["mode"]
    allowed = {"mode", "questions", "form"} if mode == "existing" else {"mode", "questions", "because"}
    unknown = raw.keys() - allowed
    if unknown:
        raise InvalidDecision([{"path": "approval." + str(k), "code": "unknown_key"} for k in unknown])
    if mode == "create":
        try:
            qs = validate_batch({k: v for k, v in raw.items() if k != "mode"})
        except InvalidDecision as exc:
            raise InvalidDecision([{"path": "approval." + p["path"], "code": p["code"]} for p in exc.problems]) from exc
        return {"mode": mode, "questions": qs}
    qs = raw.get("questions")
    if not isinstance(raw.get("form"), str) or not raw["form"].startswith("opr-"):
        raise InvalidDecision([{"path": "approval.form", "code": "form_identity_required"}])
    if (not isinstance(qs, list) or not 1 <= len(qs) <= 20
            or not all(isinstance(q, str) and q.startswith("opr-") for q in qs)
            or len(set(qs)) != len(qs)):
        raise InvalidDecision([{"path": "approval.questions", "code": "exact_unique_question_ids_required"}])
    return {"mode": mode, "form": raw["form"], "questions": list(qs)}


def _refuse(path, code):
    raise InvalidDecision([{"path": path, "code": code}])


def bind(cv, request, approval, *, actor, execution, reply_turn, conversation, act):
    """Caller holds corpus.atomic; no title matching or answer interpretation."""
    from mentis.conversation import DECISION_FORM, DECISION_FORM_ATTACHED
    from mentis.conversation.owner import _owner
    from mentis.worker import _decision_form

    requested_by = cv.expectation_state(request)["requested_by"]
    owner = _owner(cv) or requested_by

    def check_questions(form, ids=None):
        qs = form["questions"]
        if not qs or any(q["of"] != owner or
                         (cv._act(q["expectation"])["detail"].get("requester") != requested_by)
                         for q in qs):
            _refuse("approval.form", "owner_requester_mismatch")
        if ids is not None:
            selected = {q["expectation"]: q for q in qs}
            for i, qid in enumerate(ids):
                if qid not in selected:
                    _refuse(f"approval.questions[{i}]", "not_in_named_form")
                q = selected[qid]
                if q.get("presentation_status", {}).get("state") != "complete":
                    _refuse(f"approval.questions[{i}]", "complete_presentation_required")

    if approval["mode"] == "existing":
        form = cv.decision_form(approval["form"])
        fa = cv._act(approval["form"]) or {}
        fd = fa.get("detail") or {}
        if not form or form["request"] != request or fd.get("permission") or fd.get("from_prose"):
            _refuse("approval.form", "not_ordinary_form_of_carried_request")
        check_questions(form, approval["questions"])
        return {"form": form["form"], "questions": approval["questions"]}

    digest = hashlib.sha256(json.dumps(approval, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":")).encode()).hexdigest()
    # Only authored approval descriptors participate. Summary/evidence may change.
    if execution and reply_turn:
        for prior in cv._children(request):
            d = prior.get("detail") or {}
            if (prior["act"] == "outcome-claimed" and prior.get("execution") == execution
                    and d.get("reply_turn") == reply_turn and d.get("approval_digest")):
                if d["approval_digest"] != digest:
                    _refuse("approval", "conflicting_create_descriptors")
                return {"form": d["approval"], "questions": d["approval_questions"], "digest": digest}

    # own_post is a privileged placement only when checked record provenance
    # establishes this execution's result. Never take it from agent `on`.
    if not reply_turn or not any(
            a.get("turn") == reply_turn and a.get("actor") == actor
            and a.get("execution") == execution
            and (a["act"] == "manual-session-outcome-recorded"
                 or a["act"] == "turn-said" and (a.get("detail") or {}).get("answers_request") == request)
            for a in cv._children(request)):
        _refuse("approval", "checked_result_post_required")

    ordinary = []
    if execution:
        for a in cv.corpus.operational(caused_by=request, act=DECISION_FORM, execution=execution):
            d = a.get("detail") or {}
            if d.get("permission") or d.get("from_prose"):
                continue
            if not d.get("on") or d.get("approval_request") == request:
                ordinary.append(a)
    target = None
    if ordinary:
        if len(ordinary) != 1:
            _refuse("approval.form", "ambiguous_ordinary_forms")
        fa = ordinary[0]
        target = cv.decision_form(fa["id"])
        if fa["actor"] != actor or not target or target["closed"]:
            _refuse("approval.form", "closed_or_ineligible_ordinary_form")
        if target["post"] not in (None, reply_turn):
            _refuse("approval.form", "attached_to_other_post")
        if target["post"] and not fa.get("turn") and not any(
                a["act"] == DECISION_FORM_ATTACHED and a.get("turn") == reply_turn
                and a.get("execution") == execution for a in cv._children(fa["id"])):
            _refuse("approval.form", "attachment_provenance_required")
        if any(a["act"] == "work-resumed"
               and ((a.get("detail") or {}).get("event") or {}).get("kind") == "decision-form-closed"
               and ((a.get("detail") or {}).get("event") or {}).get("form") == fa["id"]
               for a in cv._children(request)):
            _refuse("approval.form", "closure_already_consumed")
        check_questions(target)
        if len(target["questions"]) + len(approval["questions"]) > 20:
            _refuse("approval.questions", "form_limit_20")
    got = _decision_form(
        cv, {"questions": approval["questions"], "on": reply_turn},
        actor=actor, parent=request, here=conversation, wrote=None, act=act,
        where=lambda cid: cid, execution=execution, own_post=reply_turn,
        append_form=target, form_detail={"approval_request": request})
    return {"form": got["form"], "questions": got["created_questions"], "digest": digest}
