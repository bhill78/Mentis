"""Apply vocabulary revision `operating-model-1` to an existing Brain.

    python tools/operating_vocabulary.py <brain> [--check] [--json]
        [--attributed-to <owner reference>] [--live]

WHAT IT CHANGES (docs/operating-model.md §1). A new definition version of two
Kinds, and nothing else:

  Discipline  gains `tools` (named, not granted), `inputs`, `outputs` and
              `limits` (known limitations and dependencies); `requires` is
              labelled as runtime capabilities.
  Workflow    gains `evidence` (what supports completion), `interrupted` (what
              remains and how it continues) and `projects` (which repositories
              it applies to; none means any); `placeable` becomes "reference",
              so it is placed only conditionally or by reference and reaches
              work in full only by being named for it.

A new Brain already gets these from `_KINDS`; this is the same definition for
a Brain made before them. Append-only: a definition is versioned, the old one
stays in the record, and every entry written under it still reads.

IT CARRIES THE OLD DEFINITION FORWARD WHOLE and changes only that delta.
`define_kind` replaces rather than merges (`mentis.spine.seam`), so whatever
the Brain's definition says beyond the delta -- `knowing`, `standing_apt`, an
owner's own form labels -- is restated, never dropped.

IT REFUSES RATHER THAN GUESSES. It recognises the definitions this repository
shipped before the revision (by their fields) and the revised one. A Kind
whose current definition is neither -- somebody changed its fields by hand --
is reported and nothing is written for any Kind: what that definition should
become is the owner's decision.

IDEMPOTENT: a Brain already at the revision is reported unchanged and nothing
is written. `--check` plans and reports without writing; it opens the Brain
read-only.

NOT THE LIVE BRAIN BY ACCIDENT. Rehearse on a copy (AGENTS.md "Brains"). A
path inside the day-to-day Brain's directory is refused without `--live`, and
applying needs the owner's Participant reference (`--attributed-to`).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

REVISION = "operating-model-1"

#: THE DEFINITIONS SHIPPED BEFORE THE REVISION, by their fields: the only
#: prior states this tool knows how to carry forward.
PRIOR_FIELDS = {
    "discipline": ["name", "about", "text", "tool_use", "verification",
                   "requires"],
    "workflow": ["name", "about", "text", "activities", "decisions",
                 "done_when", "carrier", "persona", "requires"],
}

#: THE APPROVED DELTA, per Kind: which `form` declarations the revision adds
#: or rewords, and which `authoring` keys it sets. Fields are taken whole
#: from the revised definition (`_KINDS`), in its order, so a Brain revised
#: here renders its fields in the same order as a new one.
DELTA = {
    "discipline": {"form": ("tools", "requires", "inputs", "outputs",
                            "limits"),
                   "authoring": ()},
    "workflow": {"form": ("projects", "evidence", "interrupted"),
                 "authoring": ("placeable",)},
}


def target(kind) -> dict:
    """The revised definition of `kind`, as `_KINDS` gives a new Brain."""
    from mentis.conversation import _KINDS, ABSENT
    for name, fields, meaning, standing_apt, *extra in _KINDS:
        if name == kind:
            body = {"meaning": meaning, "capturable": True,
                    "truth_apt": False, **(extra[0] if extra else {})}
            if standing_apt is not ABSENT:
                body["standing_apt"] = standing_apt
            return {"kind": kind, "fields": list(fields), **body}
    raise KeyError(kind)


def _revised(before, want, kind) -> dict:
    """`before` carried forward whole, with only the delta changed."""
    after = json.loads(json.dumps(before))
    after["fields"] = list(want["fields"])
    after["meaning"] = want["meaning"]
    form = dict(after.get("form") or {})
    for name in DELTA[kind]["form"]:
        form[name] = want["form"][name]
    after["form"] = form
    if DELTA[kind]["authoring"]:
        authoring = dict(after.get("authoring") or {})
        for key in DELTA[kind]["authoring"]:
            authoring[key] = want["authoring"][key]
        after["authoring"] = authoring
    return after


def _at_revision(body, want, kind) -> bool:
    """Does this definition already say everything the revision says?"""
    if list(body.get("fields") or ()) != want["fields"]:
        return False
    form = body.get("form") or {}
    if any(form.get(n) != want["form"][n] for n in DELTA[kind]["form"]):
        return False
    authoring = body.get("authoring") or {}
    return all(authoring.get(k) == want["authoring"][k]
               for k in DELTA[kind]["authoring"])


def plan(corpus) -> dict:
    """What the revision would write here. Reads only.

    {"changes": [...], "unchanged": [...], "refused": [...]}; a change holds
    the Kind, `before` (None when the Kind is not defined here) and `after`.
    """
    changes, unchanged, refused = [], [], []
    for kind in ("discipline", "workflow"):
        want = target(kind)
        current = corpus.current_definition(kind)
        if current is None:
            changes.append({"name": kind, "family": "kind", "before": None,
                            "after": want})
            continue
        before = current["body"]
        if "kind" not in before:
            refused.append({"name": kind,
                            "why": f"{kind!r} is defined here as a relation, "
                                   f"not a Kind"})
        elif _at_revision(before, want, kind):
            unchanged.append({"name": kind,
                              "version": current["definition"]["version"]})
        elif list(before.get("fields") or ()) == PRIOR_FIELDS[kind]:
            changes.append({"name": kind, "family": "kind", "before": before,
                            "after": _revised(before, want, kind),
                            "version": current["definition"]["version"]})
        else:
            refused.append({
                "name": kind,
                "version": current["definition"]["version"],
                "fields": list(before.get("fields") or ()),
                "why": f"its fields are neither the definition shipped "
                       f"before {REVISION} {PRIOR_FIELDS[kind]} nor the "
                       f"revised one {want['fields']}; what it should become "
                       f"is the owner's decision"})
    return {"revision": REVISION, "changes": changes, "unchanged": unchanged,
            "refused": refused}


def apply(corpus, planned, *, by) -> int:
    """Write the planned definitions in one transaction. Refuses if any Kind
    was refused, so a Brain is never left half-revised."""
    if planned["refused"]:
        raise ValueError("refused: " + "; ".join(
            f"{r['name']}: {r['why']}" for r in planned["refused"]))
    with corpus.atomic():
        for change in planned["changes"]:
            props = dict(change["after"])
            props.pop("kind", None)
            fields = props.pop("fields")
            corpus.define_kind(change["name"], fields=fields,
                               properties=props, attributed_to=by)
    return len(planned["changes"])


def format_report(result: dict, *, brain: str | None = None) -> str:
    """The plan or what was written, as the owner reads it."""
    lines = []
    written = result.get("written")
    mode = ("CHECK (nothing written)" if written is None
            else f"APPLIED ({written} definition(s) written)")
    lines.append(f"=== Mentis vocabulary revision {result['revision']}: "
                 f"{mode} ===")
    if brain:
        lines.append(f"Brain: {brain}")
    lines.append("")
    for r in result["refused"]:
        lines.append(f"REFUSED  {r['name']}: {r['why']}")
        if r.get("fields") is not None:
            lines.append(f"         its fields now: {r['fields']}")
    for u in result["unchanged"]:
        lines.append(f"UNCHANGED  {u['name']}: already at the revision "
                     f"(definition version {u['version']})")
    for c in result["changes"]:
        after = c["after"]
        if c["before"] is None:
            lines.append(f"NEW  {c['name']}: not defined here; defined as a "
                         f"new Brain defines it")
            lines.append(f"     fields: {after['fields']}")
            continue
        before = c["before"]
        added = [f for f in after["fields"] if f not in before["fields"]]
        lines.append(f"REVISED  {c['name']}: definition version "
                     f"{c['version']} -> {c['version'] + 1}")
        lines.append(f"     fields added: {added}")
        lines.append(f"     fields now:   {after['fields']}")
        for name in DELTA[c["name"]]["form"]:
            f = after["form"][name]
            said = f.get("delivered_label") or f.get("label")
            was = (before.get("form") or {}).get(name)
            lines.append(f"     {'reworded' if was else 'labelled'} "
                         f"{name}: {said!r}")
        for key in DELTA[c["name"]]["authoring"]:
            lines.append(f"     authoring {key}: "
                         f"{(before.get('authoring') or {}).get(key)!r} -> "
                         f"{after['authoring'][key]!r}")
        kept = sorted(k for k in before
                      if k not in ("fields", "form", "authoring", "meaning",
                                   "kind"))
        lines.append(f"     carried unchanged: {kept}")
    lines.append("")
    if result["refused"]:
        lines.append("Nothing was written: a refused Kind needs the owner's "
                     "decision first.")
    elif not result["changes"]:
        lines.append("Nothing to do: this Brain is at the revision.")
    elif written is None:
        lines.append("Run again without --check (with --attributed-to) to "
                     "write these.")
    return "\n".join(lines)


def _live_brain() -> pathlib.Path:
    home = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    return pathlib.Path(home, "Mentis", "Mark-IV", "brain").resolve()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("brain", help="the Brain directory (rehearse on a copy)")
    ap.add_argument("--check", action="store_true",
                    help="plan and report; write nothing")
    ap.add_argument("--json", action="store_true",
                    help="print the result as JSON")
    ap.add_argument("--attributed-to",
                    help="the owner's Participant reference; needed to write")
    ap.add_argument("--live", action="store_true",
                    help="the path is the day-to-day Brain, deliberately")
    a = ap.parse_args(argv)
    path = pathlib.Path(a.brain).resolve()
    live = _live_brain()
    if (path == live or live in path.parents) and not a.live:
        ap.error(f"{path} is the day-to-day Brain; rehearse on a copy, or "
                 f"say --live")
    if not a.check and not a.attributed_to:
        ap.error("writing needs --attributed-to with the owner's Participant "
                 "reference (or --check)")
    import mentis.api as api
    corpus = api.open_corpus(str(path), access="read" if a.check else "write")
    try:
        result = plan(corpus)
        if not a.check and not result["refused"]:
            # Planned again inside the write, so nothing between the read and
            # the write can be carried forward stale.
            with corpus.atomic():
                result = plan(corpus)
                result["written"] = apply(corpus, result,
                                          by=a.attributed_to)
    finally:
        corpus.close()
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_report(result, brain=str(path)))
    return 1 if result["refused"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
