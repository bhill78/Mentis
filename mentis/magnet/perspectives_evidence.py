"""Bounded, complete immutable input closure. No worker authority is minted here."""
from __future__ import annotations

import hashlib
import json
import re

from mentis import artifacts
from mentis.fluid.inspect import brain_key
from mentis.spine import held

from . import activation as X
from . import perspectives as P

MAX_REFS = 32
MAX_BYTES = 8 * 1024 * 1024
REF = re.compile(r"adm-[A-Za-z0-9]{6,40}\Z")


def refs(value, label):
    if not isinstance(value, list) or len(value) > MAX_REFS + 1 or not all(
            isinstance(r, str) and REF.fullmatch(r) for r in value):
        P.refuse("invalid-references", f"{label} is a list of at most 33 immutable Admission references")
    return list(dict.fromkeys(value))


def descriptor(st, ref):
    if not isinstance(ref, str) or not REF.fullmatch(ref):
        P.refuse("invalid-reference", "an input must name an immutable artifact Admission", ref=ref)
    got = artifacts.describe(st.corpus, ref, verify=False)
    if got.get("state") != "held" or type(got.get("size")) is not int or got["size"] < 0:
        P.refuse("input-unreadable", "a required immutable input is missing, purged or unreadable",
                 ref=ref, state=got.get("state"))
    return {"ref": ref, "digest": got["digest"], "size": got["size"],
            "media_type": got.get("claimed_media_type") or "application/octet-stream"}


def bounded_read(st, desc, remaining):
    """Refuse before opening over-budget bytes. Never describe(verify=True),
    which would read a whole 25 MiB artifact before enforcing this 8 MiB bound."""
    if desc["size"] > remaining:
        P.refuse("byte-limit", "the complete input package exceeds the 8 MiB (8388608 byte) limit",
                 ref=desc["ref"], size=desc["size"], limit=MAX_BYTES)
    path = held.path(st.corpus.root, desc["digest"])
    try:
        if path.stat().st_size != desc["size"]:
            raise ValueError("size mismatch")
        with path.open("rb") as stream:
            raw = stream.read(desc["size"])
        if len(raw) != desc["size"] or hashlib.sha256(raw).hexdigest() != desc["digest"]:
            raise ValueError("digest mismatch")
    except (OSError, ValueError):
        P.refuse("input-unreadable", "a required immutable input's bytes could not be verified",
                 ref=desc["ref"])
    return raw


def _json(raw):
    try:
        return json.loads(raw)
    except (UnicodeError, ValueError, RecursionError):
        return None


def native(st, mid, ref, raw, kind=None):
    got = artifacts.describe(st.corpus, ref, verify=False)
    obj = _json(raw)
    if (not isinstance(obj, dict) or obj.get("format") != P.FORMAT or obj.get("version") != 1
            or got.get("door") != P.DOOR or got.get("source") != f"magnet-perspective:{mid}"
            or obj.get("brain") != brain_key(st.corpus) or obj.get("magnet") != mid
            or (kind is not None and obj.get("kind") != kind)):
        P.refuse("wrong-package", "this is not an immutable Perspective package for this Brain and Magnet",
                 ref=ref)
    return obj


def batch(st, mid, desc, raw):
    acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, about=desc["ref"],
                                 detail_is={"magnet": mid}, limit=2)
    if len(acts) != 1:
        P.refuse("unrecorded-batch", "this batch is not a recorded collection of this Magnet", ref=desc["ref"])
    act = acts[0]
    recorded = (act.get("detail") or {}).get("artifact") or {}
    got = artifacts.describe(st.corpus, desc["ref"], verify=False)
    if (any(recorded.get(k) != desc[k] for k in ("ref", "digest", "size"))
            or got.get("door") != "magnet-extract" or got.get("source") != f"magnet:{mid}"):
        P.refuse("invalid-batch", "the batch identity disagrees with its activation record", ref=desc["ref"])
    try:
        verified = X._verified(st, mid, raw, desc["digest"], X.MEDIA_TYPE)
        if (verified["by"] != act["actor"] or verified["op"] is None
                or verified["definition_sha256"] != act["detail"]["definition_sha256"]
                or verified["state"] != act["detail"]["page"]["state"]):
            raise ValueError()
    except (X._Stop, KeyError, TypeError, ValueError):
        P.refuse("invalid-batch", "the retained batch's captured definition, operation or ranges are invalid",
                 ref=desc["ref"])
    return json.loads(raw)


def attachments(value):
    """Only structured attachments, never incidental tokens inside captured
    original prose. Full batches are counted whole, including their attachments."""
    out = []
    def walk(node):
        if isinstance(node, dict):
            if node.get("type") in ("file", "image", "artifact") and REF.fullmatch(str(node.get("ref", ""))):
                out.append(node["ref"])
            # A held-source row is inline captured text pinned to read_source;
            # it is not a file part promising read_artifact access.
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(value)
    return list(dict.fromkeys(out))


class Closure:
    """At most 33 inspected nodes, one active stack, no depth shortcut.

    A manifest is a root counted once, not a recursive self-reference. Its
    stored bytes name dependencies; the outer package descriptor identifies it.
    """
    def __init__(self, st, mid, *, reserve_refs=0, reserve_bytes=0):
        self.st, self.mid = st, mid
        self.nodes, self.active, self.raw, self.objects = {}, set(), {}, {}
        self.edges = []
        self.bytes = reserve_bytes
        self.reserve_refs = reserve_refs
        self.inspected = 0

    def add(self, ref, expected=None, parent=None):
        if ref in self.active:
            P.refuse("dependency-cycle", "the input dependency graph has an active-stack cycle", ref=ref,
                     parent=parent)
        if parent is not None:
            self.edges.append({"from": parent, "to": ref})
        if ref in self.nodes:
            if expected and any(expected.get(k) != self.nodes[ref][k] for k in ("digest", "size")):
                P.refuse("dependency-mismatch", "two dependency edges disagree about the immutable input", ref=ref)
            return
        self.inspected += 1
        if len(self.nodes) + self.reserve_refs >= MAX_REFS:
            P.refuse("reference-limit", "the complete input package exceeds 32 distinct artifact Admissions",
                     inspected=self.inspected, limit=MAX_REFS)
        desc = descriptor(self.st, ref)
        if expected and any(expected.get(k) != desc[k] for k in ("digest", "size")):
            P.refuse("dependency-mismatch", "a dependency no longer matches its immutable descriptor", ref=ref)
        if desc["size"] > MAX_BYTES - self.bytes:
            got = artifacts.describe(self.st.corpus, ref, verify=False)
            if got.get("door") == "magnet-extract":
                P.refuse("batch-too-large", f"The retained batch is {desc['size']} bytes; the complete package "
                    "must fit the 8 MiB (8388608 byte) limit. Narrow sources, types or dates and Collect a "
                    "new smaller batch before asking. Selecting fewer rows cannot shrink this batch.",
                    ref=ref, size=desc["size"], limit=MAX_BYTES)
        raw = bounded_read(self.st, desc, MAX_BYTES - self.bytes)
        self.bytes += len(raw)
        self.nodes[ref], self.raw[ref] = desc, raw
        self.active.add(ref)
        got = artifacts.describe(self.st.corpus, ref, verify=False)
        obj = _json(raw)
        deps = []
        if got.get("door") == P.DOOR:
            obj = native(self.st, self.mid, ref, raw)
            deps = obj.get("dependencies", [])
            if not isinstance(deps, list) or len(deps) > MAX_REFS:
                P.refuse("invalid-dependencies", "a Perspective package has invalid dependency edges", ref=ref)
        elif got.get("door") == "magnet-extract":
            obj = batch(self.st, self.mid, desc, raw)
            deps = [{"ref": r} for r in attachments(obj.get("page"))]
        self.objects[ref] = obj
        for dep in deps:
            if not isinstance(dep, dict) or not isinstance(dep.get("ref"), str):
                P.refuse("invalid-dependency", "an immutable package contains an unresolved dependency", ref=ref)
            self.add(dep["ref"], dep if "digest" in dep else None, parent=ref)
        self.active.remove(ref)

    def summary(self):
        return {"count": len(self.nodes) + self.reserve_refs, "bytes": self.bytes}


def _post_text(result, part):
    value = result.get("value") or {}
    parts = value.get("parts")
    if not isinstance(parts, list):
        # M1 captured text may itself be the bounded text value.
        if part == 0 and isinstance(value.get("text"), str):
            return value["text"]
        P.refuse("invalid-range", "the captured post has no such text part")
    if type(part) is not int or not 0 <= part < len(parts) or parts[part].get("type") != "text":
        P.refuse("invalid-range", "the captured post has no such text part")
    words = parts[part].get("text")
    if not isinstance(words, str):
        P.refuse("invalid-range", "the captured text part is unreadable")
    return words


def originals(batches, selections):
    """Return exact selected ranges with deduplicated original identities.
    The same version/range in two interpretations stays one original."""
    if not isinstance(selections, list) or len(selections) > 1000:
        P.refuse("invalid-selection", "selections is a bounded list of captured ranges")
    choices = selections or []
    if not choices:
        for ref, obj in batches.items():
            for source in obj["page"]["sources"]:
                for row in source.get("results", []):
                    if row.get("kind") == "file" and row.get("via") == "held-source":
                        value = row["value"]
                        choices.append({"batch": ref, "source": source["key"], "item": row["id"],
                            "version": row["version"], "start": value["offset"], "end": value["end"],
                            "stance": "supporting"})
                    else:
                        value = row.get("value") or {}
                        parts = value.get("parts") or ([{"type": "text", "text": value["text"]}]
                                                       if isinstance(value.get("text"), str) else [])
                        for i, part in enumerate(parts):
                            if part.get("type") == "text" and isinstance(part.get("text"), str):
                                choices.append({"batch": ref, "source": source["key"], "item": row["id"],
                                    "version": row["version"], "part": i, "start": 0,
                                    "end": len(part["text"]), "stance": "supporting"})
    found = {}
    for sel in choices:
        if not isinstance(sel, dict) or set(sel) - {
                "batch", "source", "item", "version", "part", "start", "end", "stance"}:
            P.refuse("invalid-selection", "a selection must name an exact captured original range")
        obj = batches.get(sel.get("batch"))
        if obj is None:
            P.refuse("invalid-range", "the selection names a batch outside this question")
        source = next((s for s in obj["page"]["sources"] if s.get("key") == sel.get("source")), None)
        row = next((r for r in (source or {}).get("results", []) if r.get("id") == sel.get("item")
                    and r.get("version") == sel.get("version")), None)
        if row is None:
            P.refuse("invalid-range", "the selected original version is not in the retained batch")
        start, end = sel.get("start"), sel.get("end")
        stance = sel.get("stance")
        if (type(start) is not int or type(end) is not int or not 0 <= start <= end
                or stance not in ("supporting", "contradicting", "context")):
            P.refuse("invalid-range", "the selection has an invalid range or evidence stance")
        if row.get("kind") == "file" and row.get("via") == "held-source":
            v = row["value"]
            raw = v["text"].encode("utf-8")
            if start < v["offset"] or end > v["end"]:
                P.refuse("invalid-range", "the selected bytes exceed the captured file range")
            try:
                raw[:start-v["offset"]].decode("utf-8")
                raw[:end-v["offset"]].decode("utf-8")
            except UnicodeDecodeError:
                P.refuse("invalid-range", "the selected file range splits a UTF-8 character")
            digest, part, unit = v["digest"], None, "byte"
        else:
            part = sel.get("part", 0)
            words = _post_text(row, part)
            if end > len(words):
                P.refuse("invalid-range", "the selected text exceeds its captured original")
            digest, unit = hashlib.sha256(words.encode()).hexdigest(), "codepoint"
        key = (row["version"], digest, part, start, end, unit)
        if key not in found:
            found[key] = {"version": row["version"], "digest": digest, "part": part,
                "start": start, "end": end, "unit": unit, "stances": [], "citations": []}
        if stance not in found[key]["stances"]:
            found[key]["stances"].append(stance)
        found[key]["citations"].append({"batch": sel["batch"], "source": sel["source"], "item": sel["item"]})
    return list(found.values())


def deduplicate(originals):
    out = {}
    for item in originals:
        key = tuple(item.get(k) for k in ("version", "digest", "part", "start", "end", "unit"))
        if key not in out:
            out[key] = {**item, "stances": list(item["stances"]), "citations": list(item["citations"])}
        else:
            for field in ("stances", "citations"):
                for value in item[field]:
                    if value not in out[key][field]:
                        out[key][field].append(value)
    return list(out.values())
