"""What a Magnet definition may say (`docs/magnets/M1-contract.md`).

The universal Magnet's configuration (plan §3.10), every facet checked and every
unknown key refused, moved here from `mentis.fluid.arrangements`, which still
names all of it. Values this build cannot execute (connectors, the web, scheduled
or continuous collection, synthesis, notifications, and the facets M1 added:
activation, processing, ai, outputs, destinations and the theme) are kept as
given: checking them starts nothing.

Everything M1 added is optional, and absent means what it always meant, so a
definition from before reads and behaves exactly as it did.
"""
from __future__ import annotations

import datetime
import re

from mentis.fluid import _checks as W

Refused = W.Refused

#: What a definition file carries; absent reads as 1. A file from a later schema
#: is not read, and so never written over.
SCHEMA_VERSION = 1

MISSING = "This Magnet configuration is missing; use recovery to recreate it."

_SHOW = re.compile(r"[a-z][a-z0-9-]{0,39}")
_OPTION = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,39}")

MAGNET_ID = re.compile(r"mag-[A-Za-z0-9_-]{1,60}")
FACETS = ("sources", "selection", "collection", "synthesis", "notifications",
          "presentation")
#: Added by M1, each optional, each replaced whole by a reconfigure as the six are.
MORE_FACETS = ("activation", "processing", "ai", "outputs", "destinations")
#: A definition's own, which no reconfigure changes: the Conversation is asked
#: for (`mentis.magnet.set_conversation`), and the version is the file's.
OWN_FIELDS = ("conversation", "schema_version")
SOURCE_KINDS = {"brain": ({"brain"}, set()),
                "conversation": ({"conversation"}, set()),
                "connector": ({"connector"}, {"location"}),
                "web": (set(), {"url", "domain"}),
                "other": ({"type", "ref"}, set()),
                "agent-results": (set(), {"conversation", "runtime"}),
                "file": ({"collection"}, {"path"}),
                "database": ({"collection"}, {"table"})}
MAX_SOURCES = 20
MAX_PHRASES = 20
MAX_PHRASE = 500
MAX_TOPICS = 50
MAX_FILTERS = 20
MAX_CRITERIA = 2000
MAX_OPERATIONS = 20
MAX_OUTPUTS = 20
MAX_DESTINATIONS = 20
MAX_NOTE = 2000
INFORMATION_TYPES = ("post", "file", "image", "attachment", "link", "form",
                     "other")
COLLECTION_MODES = ("one-time", "scheduled", "continuous", "paused")
SYNTHESIS_MODES = ("manual", "scheduled", "on-new-information")
RENDERERS = ("disc", "ring", "cards", "list", "gallery")
THEMES = ("minimal", "anchored", "glass", "floating")
NOTIFICATIONS = ("newItems", "changes", "failures")
ACTIVATIONS = ("manual", "scheduled", "event", "source-change", "condition")
OPERATIONS = ("extract", "compare", "correlate", "classify", "transform",
              "change-detect", "other")
AI_MODES = ("none", "selective", "local", "runtime", "agent")
OUTPUTS = ("findings", "structured", "records", "relationships", "proposals",
           "notifications", "work")
DESTINATIONS = ("magnet-conversation", "brain", "workspace", "workflow")
#: A schedule: five cron fields, or an ISO 8601 duration (`PT1H`, `P1D`).
_CRON = re.compile(r"[0-9*/,-]+( [0-9*/,-]+){4}")
_DURATION = re.compile(r"P(?=\d|T\d)(\d+W)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+S)?)?")


class Declined(Refused):
    """Well formed, but the arrangement as it stands forbids it now: 422,
    with a machine-readable reason (CapabilityUnavailable, plan §3.4)."""

    def __init__(self, code, message, retryable=True):
        super().__init__(message)
        self.reason = {"code": code, "message": message,
                       "retryable": retryable}


def exactly(v, keys, where, optional=()) -> dict:
    """A mapping with exactly `keys`, and perhaps `optional`: nothing else."""
    if not isinstance(v, dict):
        raise Refused(f"{where}: a mapping")
    extra = sorted(str(k) for k in set(v) - set(keys) - set(optional))
    if extra:
        raise Refused(f"{where}: {extra[0]!r} is not one of "
                      f"{sorted(set(keys) | set(optional))}")
    missing = [k for k in keys if k not in v]
    if missing:
        raise Refused(f"{where}: {missing[0]!r} is missing")
    return v


def one_of(v, allowed, where):
    if not isinstance(v, str) or v not in allowed:
        raise Refused(f"{where}: {v!r} is not one of {list(allowed)}")
    return v


def _source(s, where) -> dict:
    if not isinstance(s, dict):
        raise Refused(f"{where}: a source is a mapping")
    kind = one_of(s.get("kind"), tuple(SOURCE_KINDS), f"{where}.kind")
    need, may = SOURCE_KINDS[kind]
    exactly(s, ("kind", *need), where, may)
    out = {"kind": kind}
    for k in sorted(need | may):
        if k not in s:
            continue
        if k in ("brain", "conversation", "connector", "collection"):
            out[k] = W._match(W._TURN, s[k], f"{where}.{k}")
        elif k == "type":
            out[k] = W._match(_SHOW, s[k], f"{where}.type")
        elif k == "url":
            out[k] = W._text(s[k], f"{where}.url", most=2000)
            if not re.match(r"https?://", out[k]):
                raise Refused(f"{where}.url: an http or https address")
        elif k == "domain":
            out[k] = W._text(s[k], f"{where}.domain", most=253)
        else:
            out[k] = W._text(s[k], f"{where}.{k}", most=W.MAX_KEY)
    return out


def _date(v, where) -> str:
    v = W._text(v, where, most=40)
    try:
        datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise Refused(f"{where}: {v!r} is not an ISO 8601 date") from None
    return v


def _selection(v, where) -> dict:
    exactly(v, (), where, ("criteria", "phrases", "topics",
                           "informationTypes", "dates", "filters"))
    out = {}
    if v.get("criteria") is not None:
        out["criteria"] = W._text(v["criteria"], f"{where}.criteria",
                                  most=MAX_CRITERIA, blank=True)
    if v.get("phrases") is not None:
        p = v["phrases"]
        if not isinstance(p, list) or len(p) > MAX_PHRASES:
            raise Refused(f"{where}.phrases: a list of at most {MAX_PHRASES}")
        out["phrases"] = [W._text(x, f"{where}.phrases", most=MAX_PHRASE)
                          for x in p]
    if v.get("topics") is not None:
        t = v["topics"]
        if not isinstance(t, list) or len(t) > MAX_TOPICS:
            raise Refused(f"{where}.topics: a list of at most {MAX_TOPICS} ids")
        out["topics"] = [W._match(W._TURN, x, f"{where}.topics") for x in t]
    if v.get("informationTypes") is not None:
        t = v["informationTypes"]
        if not isinstance(t, list) or len(t) > len(INFORMATION_TYPES):
            raise Refused(f"{where}.informationTypes: a list of "
                          f"{list(INFORMATION_TYPES)}")
        got = [one_of(x, INFORMATION_TYPES, f"{where}.informationTypes")
               for x in t]
        if len(set(got)) != len(got):
            raise Refused(f"{where}.informationTypes: each type once")
        out["informationTypes"] = got
    if v.get("dates") is not None:
        d = exactly(v["dates"], (), f"{where}.dates", ("after", "before"))
        out["dates"] = {k: _date(d[k], f"{where}.dates.{k}")
                        for k in ("after", "before") if d.get(k) is not None}
    if v.get("filters") is not None:
        f = v["filters"]
        if not isinstance(f, dict) or len(f) > MAX_FILTERS:
            raise Refused(f"{where}.filters: a mapping of at most "
                          f"{MAX_FILTERS} entries")
        out["filters"] = {}
        for k, x in f.items():
            W._match(_OPTION, k, f"{where}.filters key")
            if isinstance(x, bool):
                out["filters"][k] = x
            elif isinstance(x, (int, float)):
                out["filters"][k] = W._num(x, f"{where}.filters.{k}", -1e15, 1e15)
            elif isinstance(x, str):
                out["filters"][k] = W._text(x, f"{where}.filters.{k}",
                                            most=MAX_PHRASE, blank=True)
            else:
                raise Refused(f"{where}.filters.{k}: text, a number, true "
                              "or false")
    return out


def _when(v, where) -> str:
    """A schedule's words: five cron fields or an ISO 8601 duration."""
    s = W._text(v, where, most=120)
    if not (_CRON.fullmatch(s) or _DURATION.fullmatch(s)):
        raise Refused(f"{where}: {s!r} is neither five cron "
                      "fields nor an ISO 8601 duration")
    return s


def _schedule(v, modes, where) -> dict:
    exactly(v, ("mode",), where, ("schedule",))
    out = {"mode": one_of(v["mode"], modes, f"{where}.mode")}
    if out["mode"] == "scheduled":
        out["schedule"] = _when(v.get("schedule"), f"{where}.schedule")
    elif v.get("schedule") is not None:
        raise Refused(f"{where}.schedule: only a scheduled mode has one")
    return out


def _activation(v, where) -> dict:
    exactly(v, ("mode",), where, ("schedule", "event", "condition"))
    out = {"mode": one_of(v["mode"], ACTIVATIONS, f"{where}.mode")}
    for field, mode in (("schedule", "scheduled"), ("event", "event"),
                        ("condition", "condition")):
        if out["mode"] == mode:
            if field == "schedule":
                out[field] = _when(v.get(field), f"{where}.{field}")
            else:
                out[field] = W._text(v.get(field), f"{where}.{field}",
                                     most=MAX_NOTE)
        elif v.get(field) is not None:
            raise Refused(f"{where}.{field}: only {mode!r} activation has one")
    return out


def _scalars(v, where) -> dict:
    """A small mapping of text, numbers and true or false."""
    if not isinstance(v, dict) or len(v) > MAX_FILTERS:
        raise Refused(f"{where}: a mapping of at most {MAX_FILTERS} entries")
    out = {}
    for k, x in v.items():
        W._match(_OPTION, k, f"{where} key")
        if isinstance(x, bool):
            out[k] = x
        elif isinstance(x, (int, float)):
            out[k] = W._num(x, f"{where}.{k}", -1e15, 1e15)
        elif isinstance(x, str):
            out[k] = W._text(x, f"{where}.{k}", most=MAX_NOTE, blank=True)
        else:
            raise Refused(f"{where}.{k}: text, a number, true or false")
    return out


def _processing(v, where) -> dict:
    exactly(v, ("operations",), where)
    ops = v["operations"]
    if not isinstance(ops, list) or len(ops) > MAX_OPERATIONS:
        raise Refused(f"{where}.operations: a list of at most "
                      f"{MAX_OPERATIONS}, in the order they apply")
    out = []
    for i, o in enumerate(ops):
        at = f"{where}.operations[{i}]"
        exactly(o, ("op",), at, ("name", "options"))
        one = {"op": one_of(o["op"], OPERATIONS, f"{at}.op")}
        if o.get("name") is not None:
            one["name"] = W._text(o["name"], f"{at}.name")
        if o.get("options") is not None:
            one["options"] = _scalars(o["options"], f"{at}.options")
        out.append(one)
    return {"operations": out}


def _ai(v, where) -> dict:
    exactly(v, ("mode",), where, ("runtime", "model", "agent"))
    out = {"mode": one_of(v["mode"], AI_MODES, f"{where}.mode")}
    if out["mode"] == "none" and any(v.get(k) is not None for k in
                                     ("runtime", "model", "agent")):
        raise Refused(f"{where}: no AI names no runtime, model or agent")
    for k in ("runtime", "model", "agent"):
        if v.get(k) is not None:
            out[k] = W._text(v[k], f"{where}.{k}")
    return out


def _outputs(v, where) -> list:
    if not isinstance(v, list) or len(v) > MAX_OUTPUTS:
        raise Refused(f"{where}: a list of at most {MAX_OUTPUTS}")
    got = [one_of(x, OUTPUTS, where) for x in v]
    if len(set(got)) != len(got):
        raise Refused(f"{where}: each output once")
    return got


def _destinations(v, where) -> list:
    if not isinstance(v, list) or len(v) > MAX_DESTINATIONS:
        raise Refused(f"{where}: a list of at most {MAX_DESTINATIONS}")
    out = []
    for i, d in enumerate(v):
        at = f"{where}[{i}]"
        exactly(d, ("kind",), at, ("ref",))
        one = {"kind": one_of(d["kind"], DESTINATIONS, f"{at}.kind")}
        if d.get("ref") is not None:
            one["ref"] = W._text(d["ref"], f"{at}.ref", most=W.MAX_KEY)
        out.append(one)
    return out


def _presentation(v, where) -> dict:
    exactly(v, ("renderer",), where, ("theme",))
    out = {"renderer": one_of(v["renderer"], RENDERERS, f"{where}.renderer")}
    if v.get("theme") is not None:
        out["theme"] = one_of(v["theme"], THEMES, f"{where}.theme")
    return out


def facet(name, v, where):
    if name == "sources":
        if not isinstance(v, list) or not 1 <= len(v) <= MAX_SOURCES:
            raise Refused(f"{where}: a list of 1..{MAX_SOURCES} sources")
        return [_source(s, f"{where}[{i}]") for i, s in enumerate(v)]
    if name == "selection":
        return _selection(v, where)
    if name == "collection":
        return _schedule(v, COLLECTION_MODES, where)
    if name == "synthesis":
        return _schedule(v, SYNTHESIS_MODES, where)
    if name == "notifications":
        exactly(v, NOTIFICATIONS, where)
        for k in NOTIFICATIONS:
            if not isinstance(v[k], bool):
                raise Refused(f"{where}.{k}: true or false")
        return {k: v[k] for k in NOTIFICATIONS}
    if name == "activation":
        return _activation(v, where)
    if name == "processing":
        return _processing(v, where)
    if name == "ai":
        return _ai(v, where)
    if name == "outputs":
        return _outputs(v, where)
    if name == "destinations":
        return _destinations(v, where)
    return _presentation(v, where)


def magnet_config(c, where="magnet") -> dict:
    """A MagnetConfig: the six facets it always had, what M1 added where it is
    given, and a Magnet's own fields. Nothing is defaulted in: what wasn't said
    stays unsaid, so a definition round-trips exactly as it was written."""
    exactly(c, ("id", *FACETS), where, (*MORE_FACETS, *OWN_FIELDS))
    out = {"id": W._match(MAGNET_ID, c["id"], f"{where}.id")}
    for name in FACETS:
        out[name] = facet(name, c[name], f"{where}.{name}")
    for name in MORE_FACETS:
        if c.get(name) is not None:
            out[name] = facet(name, c[name], f"{where}.{name}")
    if "conversation" in c:
        out["conversation"] = None if c["conversation"] is None else W._match(
            W._TURN, c["conversation"], f"{where}.conversation")
    if "schema_version" in c:
        v = c["schema_version"]
        if isinstance(v, bool) or not isinstance(v, int) \
                or not 1 <= v <= SCHEMA_VERSION:
            raise Refused(f"{where}.schema_version: {v!r} is not one this "
                          f"build reads (1..{SCHEMA_VERSION})")
        out["schema_version"] = v
    return out
