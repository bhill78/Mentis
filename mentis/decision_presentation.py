"""Author-supplied decision presentation. These fields confer no authority.

Validation belongs at agent authoring boundaries, never at the shared form
constructor (which also serves trusted permission and historical producers).
Reads preserve stored metadata, including unknown versions, without backfill.
"""
from __future__ import annotations

import copy
import json
import re
from urllib.parse import urlsplit

TYPES = ("artifact_approval", "action_approval", "choice", "free_response")
STAGES = ("design", "implementation", "integration", "deployment", "other")
PRESENTATION_KEYS = {"version", "type", "scope", "stages", "primary",
                     "primary_reason", "supporting", "applies_when"}


class InvalidDecision(ValueError):
    def __init__(self, problems):
        self.problems = problems
        super().__init__("; ".join(f"{p['path']}: {p['code']}" for p in problems))


def validate_question(raw, *, because=None, path="question"):
    problems = []

    def bad(p, code):
        problems.append({"path": p, "code": code})

    def text(v, p, limit, required=True):
        if not isinstance(v, str) or not v.strip():
            if required or v is not None:
                bad(p, "required" if v is None else "nonblank_string")
            return None
        v = v.strip()
        if len(v) > limit:
            bad(p, f"max_length_{limit}")
        return v

    def reference(v, p):
        if not isinstance(v, dict):
            bad(p, "reference_object")
            return v
        kind = v.get("kind")
        keys = {"kind", "label"}
        text(v.get("label"), p + ".label", 160)
        if kind == "record":
            keys |= {"id"}
            if not isinstance(v.get("id"), str) or not re.fullmatch(
                    r"(?:ent|opr|adm)-[0-9a-fA-F]+", v["id"]):
                bad(p + ".id", "record_identity")
        elif kind == "commit":
            keys |= {"repository", "sha"}
            text(v.get("repository"), p + ".repository", 2000)
            if not isinstance(v.get("sha"), str) or not re.fullmatch(r"[0-9a-fA-F]{40}", v["sha"]):
                bad(p + ".sha", "full_commit_hash")
        elif kind == "url":
            keys |= {"url"}
            try:
                u = urlsplit(v.get("url") if isinstance(v.get("url"), str) else "")
                if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password:
                    raise ValueError()
            except ValueError:
                bad(p + ".url", "http_url")
        else:
            bad(p + ".kind", "unsupported_reference_kind")
        for k in v.keys() - keys:
            bad(p + "." + str(k), "unknown_key")
        return copy.deepcopy(v)

    if not isinstance(raw, dict):
        raise InvalidDecision([{"path": path, "code": "question_object"}])
    out = {"question": text(raw.get("question"), path + ".question", 1000),
           "because": text(raw.get("because", because), path + ".because", 2000)}
    opts = raw.get("options")
    if isinstance(opts, str):
        try:
            opts = json.loads(opts)
        except ValueError:
            pass
    if opts is not None:
        if not isinstance(opts, list) or len(opts) < 2:
            bad(path + ".options", "at_least_two")
        else:
            normalized, seen = [], set()
            for i, o in enumerate(opts):
                p = f"{path}.options[{i}]"
                o = o if isinstance(o, dict) else {}
                label = text(o.get("label"), p + ".label", 200)
                consequence = text(o.get("consequence"), p + ".consequence", 2000)
                if label and label.casefold() in seen:
                    bad(p + ".label", "duplicate_label")
                seen.add(label.casefold() if label else None)
                normalized.append({"label": label, "consequence": consequence})
            out["options"] = normalized
    meta = raw.get("presentation")
    p = path + ".presentation"
    if not isinstance(meta, dict):
        bad(p, "required" if meta is None else "object")
    else:
        for k in meta.keys() - PRESENTATION_KEYS:
            bad(p + "." + str(k), "unknown_key")
        if type(meta.get("version")) is not int or meta["version"] != 1:
            bad(p + ".version", "unsupported_version")
        typ = meta.get("type")
        if typ not in TYPES:
            bad(p + ".type", "unsupported_type")
        text(meta.get("scope"), p + ".scope", 2000)
        stages = meta.get("stages")
        if not isinstance(stages, list) or any(s not in STAGES for s in stages):
            bad(p + ".stages", "stage_array")
        elif typ in ("artifact_approval", "action_approval") and not stages:
            bad(p + ".stages", "approval_stage_required")
        if "primary" not in meta:
            bad(p + ".primary", "required")
        elif meta["primary"] is None:
            text(meta.get("primary_reason"), p + ".primary_reason", 2000)
        else:
            reference(meta["primary"], p + ".primary")
        if typ == "artifact_approval" and (
                not isinstance(meta.get("primary"), dict)
                or meta["primary"].get("kind") == "url"):
            bad(p + ".primary", "exact_artifact_required")
        if "supporting" in meta:
            refs = meta["supporting"]
            if not isinstance(refs, list) or len(refs) > 24:
                bad(p + ".supporting", "reference_array_max_24")
            else:
                for i, ref in enumerate(refs):
                    reference(ref, f"{p}.supporting[{i}]")
        for k, limit in (("applies_when", 1000), ("primary_reason", 2000)):
            if k in meta:
                text(meta[k], p + "." + k, limit)
        if typ == "free_response" and "options" in raw:
            bad(path + ".options", "omit_for_free_response")
        if typ == "choice" and opts is None:
            bad(path + ".options", "choice_options_required")
        if typ in ("artifact_approval", "action_approval") and re.fullmatch(
                r"approve (?:this|the) work[?.! ]*", out["question"] or "", re.I):
            bad(path + ".question", "specific_approval_question_required")
        out["presentation"] = copy.deepcopy(meta)
        for k in ("scope", "primary_reason", "applies_when"):
            if isinstance(out["presentation"].get(k), str):
                out["presentation"][k] = out["presentation"][k].strip()
        supporting = out["presentation"].get("supporting")
        refs = [out["presentation"].get("primary")]
        if isinstance(supporting, list):
            refs.extend(supporting)
        for ref in refs:
            if isinstance(ref, dict):
                for k in ("label", "repository"):
                    if isinstance(ref.get(k), str):
                        ref[k] = ref[k].strip()
    if problems:
        raise InvalidDecision(problems)
    return out


def validate_batch(args):
    raw = args.get("questions")
    if raw is None:
        raw = [{k: args[k] for k in ("question", "because", "options", "presentation") if k in args}]
    elif any(k in args for k in ("question", "options", "presentation")):
        raise InvalidDecision([{"path": "questions", "code": "use_shorthand_or_batch"}])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            pass
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
        raise InvalidDecision([{"path": "questions", "code": "array_length_1_to_20"}])
    out, problems = [], []
    for i, q in enumerate(raw):
        try:
            out.append(validate_question(q, because=args.get("because"), path=f"questions[{i}]"))
        except InvalidDecision as exc:
            problems.extend(exc.problems)
    if problems:
        raise InvalidDecision(problems)
    return out


def fields(detail, because=None, *, generated=False):
    """Additive read fields; unsupported data is returned byte-for-value."""
    d = detail or {}
    meta = d.get("presentation")
    if "presentation" not in d:
        problems = []
        if not d.get("question"):
            problems.append({"path": "question", "code": "required"})
        if not because:
            problems.append({"path": "because", "code": "required"})
        elif isinstance(because, str) and because.strip() == "a decision only the owner can make":
            # This was also the constructor's fallback. Its presence cannot
            # establish context or tell us whether an author supplied it.
            # Preserve the stored words; report only what cannot be known.
            problems.append({"path": "because", "code": "unavailable_or_uncertain"})
        opts = d.get("options")
        if isinstance(opts, list):
            for i, o in enumerate(opts):
                if not isinstance(o, dict) or not o.get("consequence"):
                    problems.append({"path": f"options[{i}].consequence", "code": "required"})
        if generated or re.match(r"approve this work\?", str(d.get("question") or ""), re.I):
            problems.extend({"path": "presentation." + k, "code": "not_recorded"}
                            for k in ("scope", "stages"))
        state = "incomplete" if problems else "legacy"
    elif isinstance(meta, dict) and "version" in meta and (
            type(meta["version"]) is not int or meta["version"] != 1):
        state, problems = "unsupported", [{"path": "presentation.version", "code": "unsupported_version"}]
    else:
        try:
            validate_question({**d, "because": because}, path="question")
            state, problems = "complete", []
        except InvalidDecision as exc:
            state = "incomplete"
            problems = [{"path": p["path"].removeprefix("question."), "code": p["code"]}
                        for p in exc.problems]
    return {**({"presentation": copy.deepcopy(meta)} if "presentation" in d else {}),
            "presentation_status": {"state": state, "problems": problems}}


# MCP exposes the object and documents exact constraints; validation above is
# authoritative for shorthand, batch and completion paths alike.
REFERENCE_SCHEMA = {"oneOf": [
    {"type": "object", "properties": {
        "kind": {"const": "record"},
        "id": {"type": "string", "pattern": "^(ent|opr|adm)-[0-9a-fA-F]+$"},
        "label": {"type": "string", "minLength": 1, "maxLength": 160}},
     "required": ["kind", "id", "label"], "additionalProperties": False},
    {"type": "object", "properties": {
        "kind": {"const": "commit"}, "repository": {"type": "string"},
        "sha": {"type": "string", "pattern": "^[0-9a-fA-F]{40}$"},
        "label": {"type": "string", "minLength": 1, "maxLength": 160}},
     "required": ["kind", "repository", "sha", "label"], "additionalProperties": False},
    {"type": "object", "properties": {
        "kind": {"const": "url"}, "url": {"type": "string", "pattern": "^https?://"},
        "label": {"type": "string", "minLength": 1, "maxLength": 160}},
     "required": ["kind", "url", "label"], "additionalProperties": False}]}

SCHEMA = {"type": "object", "description": "Version 1 author-supplied decision presentation; confers no authority.",
          "properties": {"version": {"type": "integer", "enum": [1]},
                         "type": {"type": "string", "enum": list(TYPES)},
                         "scope": {"type": "string", "minLength": 1, "maxLength": 2000},
                         "stages": {"type": "array", "items": {"type": "string", "enum": list(STAGES)}},
                         "primary": {"anyOf": [REFERENCE_SCHEMA, {"type": "null"}]},
                         "primary_reason": {"type": "string", "maxLength": 2000},
                         "supporting": {"type": "array", "maxItems": 24, "items": REFERENCE_SCHEMA},
                         "applies_when": {"type": "string", "maxLength": 1000}},
          "required": ["version", "type", "scope", "stages", "primary"], "additionalProperties": False}

QUESTION_SCHEMA = {"type": "object", "properties": {
    "question": {"type": "string", "minLength": 1, "maxLength": 1000},
    "because": {"type": "string", "minLength": 1, "maxLength": 2000},
    "options": {"type": "array", "minItems": 2, "items": {"type": "object", "properties": {
        "label": {"type": "string", "minLength": 1, "maxLength": 200},
        "consequence": {"type": "string", "minLength": 1, "maxLength": 2000}},
        "required": ["label", "consequence"]}},
    "presentation": SCHEMA}, "required": ["question", "presentation"]}

APPROVAL_SCHEMA = {"oneOf": [
    {"type": "object", "properties": {
        "mode": {"const": "existing"}, "form": {"type": "string"},
        "questions": {"type": "array", "minItems": 1, "maxItems": 20,
                      "items": {"type": "string"}}},
     "required": ["mode", "form", "questions"], "additionalProperties": False},
    {"type": "object", "properties": {
        "mode": {"const": "create"}, "because": {"type": "string"},
        "questions": {"type": "array", "minItems": 1, "maxItems": 20,
                      "items": QUESTION_SCHEMA}},
     "required": ["mode", "questions"], "additionalProperties": False}]}
