"""Regenerate the contract vectors from part B's canonical Python classifier.

Usage: python presentation_vectors.py <mentis/decision_presentation.py> <output.json>
This only imports the classifier; it opens no Brain. The committed vectors let part C
test its exact commit independently of the concurrent Python implementation branch.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

source, output = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("canonical_decision_presentation", source)
canonical = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canonical)
base = {
    "question": "Which plan should guide implementation?",
    "options": [{"label": "Plan A", "consequence": "Build plan A after the review."},
                {"label": "Plan B", "consequence": "Build plan B after the review."}],
    "presentation": {"version": 1, "type": "choice", "scope": "Select the plan for implementation.",
                     "stages": ["implementation"],
                     "primary": {"kind": "record", "id": "ent-proposal", "label": "Proposal"},
                     "supporting": [{"kind": "record", "id": "opr-review", "label": "Review"}],
                     "applies_when": "If implementation proceeds."},
}
cases = []

def add(name, detail=None, because="A plan is needed before implementation.", native=True):
    d = copy.deepcopy(base if detail is None else detail)
    cases.append({"name": name, "detail": d, "because": because, "native": native,
                  "fields": canonical.fields(d, because)})

def meta(name, native=True, **changes):
    d = copy.deepcopy(base)
    d["presentation"].update(changes)
    add(name, d, native=native)

add("choice")
add("legacy", {"question": "Which plan?", "options": base["options"]})
add("legacy-no-context", {"question": "Which plan?"}, because=None)
add("legacy-no-question", {})
add("legacy-generic", {"question": "Approve this work? Build the draft.", "options": base["options"]})
add("legacy-missing-consequence", {"question": "Which plan?", "options": [{"label": "A"}, 3]})
add("legacy-whitespace-is-recorded", {"question": " ", "options": []}, because=" ")
add("legacy-nonstring-recorded", {"question": ["historical"], "options": [{"consequence": 2}]})
for version in (2, 0, None, True, 1.0, "1"):
    meta("unsupported-" + repr(version), version=version, preserved={"unknown": [1, None, "x"]})
d = copy.deepcopy(base)
del d["presentation"]["version"]
add("unsupported-missing-version", d)
meta("action", type="action_approval")
meta("artifact", type="artifact_approval")
meta("commit", type="artifact_approval", primary={"kind": "commit", "repository": "Mentis", "sha": "aB" * 20, "label": "Candidate"})
meta("explicit-no-primary", primary=None, primary_reason="The choice concerns a plan, not an artifact.")
meta("choice-no-stage", stages=[])
d = copy.deepcopy(base)
del d["options"]
d["presentation"].update(type="free_response", primary=None, primary_reason="The answer supplies information.", stages=[])
add("free-response", d)
d["presentation"].update(type="action_approval", stages=["design"])
add("action-own-words", d)
d = copy.deepcopy(base)
d["question"] = "Which plan should we build? " + "\U0001f9e0" * 970
add("unicode-codepoints", d)
d = copy.deepcopy(base)
d["options"] = json.dumps(d["options"])
add("encoded-options", d)
for key, value in (("type", "unknown"), ("scope", ""), ("stages", None),
                   ("primary", None), ("supporting", None), ("applies_when", ""),
                   ("unknown", True)):
    meta("forward-" + key, native=False, **{key: value})
meta("forward-url", native=False, primary={"kind": "url", "url": "https://example.org/plan", "label": "Plan"})
meta("forward-artifact-no-stage", native=False, type="artifact_approval", stages=[])
meta("forward-bad-record", native=False, primary={"kind": "record", "id": "wrong", "label": "Plan"})
for value in (None, [], "unknown"):
    d = copy.deepcopy(base)
    d["presentation"] = value
    add("forward-meta-" + repr(value), d, native=False)
for options in ([], [{"label": "A"}], [{"label": "A"}, {"label": "B"}],
                [{"label": "A", "consequence": "x"}, {"label": "a", "consequence": "y"}],
                [{"label": "Stra\u00dfe", "consequence": "x"}, {"label": "STRASSE", "consequence": "y"}],
                [{"label": "\u00c9lan", "consequence": "x"}, {"label": "Other", "consequence": "y"}]):
    d = copy.deepcopy(base)
    d["options"] = options
    add("forward-options-" + str(len(cases)), d, native=False)
for question in ("Approve this work?", "Approve the work!", "\U0001f9e0" * 1001):
    d = copy.deepcopy(base)
    d["question"] = question
    d["presentation"]["type"] = "action_approval"
    add("forward-question-" + str(len(cases)), d, native=False)

output.write_text(json.dumps({"contract": "ent-40166218c575", "canonical_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                             "cases": cases}, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
print(f"{len(cases)} vectors; canonical SHA-256 {hashlib.sha256(source.read_bytes()).hexdigest()}")
