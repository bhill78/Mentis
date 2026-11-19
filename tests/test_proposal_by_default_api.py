"""Leaving `establish` out records a proposal, at the owner-facing create doors.

OWNER DECISION, 2026-11-18. "Record as proposal; the user decides whether to
establish it. At the server/API boundary, omission of an establishment option
must not silently establish a record."

WHAT CHANGED, AND ONLY THAT. `POST /api/entries` read an absent `establish` as
true, and `POST /api/personas` established unless the caller volunteered
`propose`. Both now establish only when the request says `establish: true` --
for material that has standing to gain.

WHAT DID NOT. A Kind whose current definition says standing is not meaningful
(a note, a finding, a problem, an outcome) is still established on write when
nothing is said: for those Kinds that approves nothing and only records that
this is the current version, and withholding it would change what the reads
that look for evidence find. A Kind that has not said either way is likewise
untouched. An explicit `establish`, true or false, is honoured for every Kind
exactly as before, and the instruction door already defaulted to a proposal.
"""

from __future__ import annotations

import pytest

from mentis.conversation.governance import _walks
from mentis.web import _State, _routes, fixture


@pytest.fixture
def world(tmp_path):
    root = tmp_path / "corpus"
    fixture.build(str(root))
    st = _State(str(root), str(tmp_path))
    cv = st.cv
    conv = cv.open_conversation("Cells", about="acceptance")
    owner = cv.resolve_participant("@brian")
    agent = cv.resolve_participant("@Ada")
    for p in (owner, agent):
        cv.join(p, conv)
    return {"st": st, "cv": cv, "corpus": st.corpus, "conv": conv,
            "owner": owner, "agent": agent}


def post(world, path, payload):
    return _routes(world["st"], path, {}, payload, "POST")


def get(world, path, query=None):
    return _routes(world["st"], path, query or {}, None, "GET")


def entry(world, kind, body, **more):
    return post(world, "/api/entries",
                {"kind": kind, "body": body,
                 "attributed_to": world["owner"], **more})


#: Material that has standing to gain, with a body its Kind accepts.
GOVERNING = [
    ("rule", {"text": "Measure before claiming a regression."}),
    ("decision", {"text": "Releases go out on Tuesdays."}),
    ("discipline", {"name": "Review", "text": "Read the diff first."}),
    ("workflow", {"name": "Ship", "text": "Build, review, release."}),
    ("conversation-instruction", {"text": "Cite the Turn you answer."}),
]

#: Material for which standing is not meaningful: evidence, not governance.
EVIDENCE = [
    ("note", {"text": "Seen on the build machine."}),
    ("problem", {"text": "The export stalls on large files."}),
    ("source-material", None),
]


# -- the generic door --------------------------------------------------------

@pytest.mark.parametrize("kind,body", GOVERNING)
def test_omission_records_a_proposal_for_material_that_could_govern(
        world, kind, body):
    assert _walks(world["corpus"], kind) is True
    said = entry(world, kind, body)
    assert "error" not in said, said
    assert said["standing"]["stands"] is False
    assert said["standing"]["established_by"] == []
    # Recorded and addressable: a proposal, not a refusal.
    assert world["corpus"].read([said["entry"]])
    assert world["corpus"].stands(said["entry"])["stands"] is False


@pytest.mark.parametrize("kind,body", GOVERNING)
def test_an_explicit_establish_still_establishes(world, kind, body):
    said = entry(world, kind, body, establish=True)
    assert "error" not in said, said
    assert said["standing"]["stands"] is True
    assert len(said["standing"]["established_by"]) == 1


@pytest.mark.parametrize("kind,body", GOVERNING)
def test_an_explicit_false_is_a_proposal_as_it_always_was(world, kind, body):
    said = entry(world, kind, body, establish=False)
    assert "error" not in said, said
    assert said["standing"]["stands"] is False


def test_a_lesson_with_its_basis_is_a_proposal_by_omission(world):
    """A lesson is knowledge standing is meaningful for (`standing_apt` true),
    so it is held to the same default as material that directs work."""
    note = entry(world, "note", {"text": "It failed unmeasured."})["entry"]
    said = entry(world, "lesson", {"text": "Measure first."}, basis=[note])
    assert "error" not in said, said
    assert said["standing"]["stands"] is False
    assert said["basis"]  # the basis is written with the proposal

    stood = entry(world, "lesson", {"text": "Measure first, again."},
                  basis=[note], establish=True)
    assert stood["standing"]["stands"] is True


def test_a_lesson_still_owes_its_basis_whichever_way_it_is_recorded(world):
    for more in ({}, {"establish": True}, {"establish": False}):
        refused = entry(world, "lesson", {"text": "No basis given."}, **more)
        assert "requires_basis" in refused["error"], (more, refused)


def test_a_hypothesis_by_omission_is_a_candidate_and_owes_no_falsifier_yet(world):
    """The falsifier is owed by the act that ESTABLISHES, as before. Omission
    used to establish, so it used to be refused for the lack of one; it is now
    the candidate the door has always allowed `establish: false` to write."""
    note = entry(world, "note", {"text": "Two slow runs."})["entry"]
    body = {"text": "The cache is cold after deploy."}
    said = entry(world, "hypothesis", body, basis=[note])
    assert "error" not in said, said
    assert said["standing"]["stands"] is False

    refused = entry(world, "hypothesis", body, basis=[note], establish=True)
    assert "error" in refused and "falsifier" in refused["error"]


@pytest.mark.parametrize("kind,body", [e for e in EVIDENCE if e[1] is not None])
def test_evidence_kinds_are_exactly_as_they_were_by_omission(world, kind, body):
    """UNCHANGED. Before this change omission meant `create_and_establish` for
    every Kind, so a note or a problem written with nothing said carried one
    establishing act and `stands` answered True. It still does."""
    assert _walks(world["corpus"], kind) is False
    said = entry(world, kind, body)
    assert "error" not in said, said
    assert said["standing"]["stands"] is True
    assert len(said["standing"]["established_by"]) == 1
    # ...and saying so explicitly is the same act, not a different one.
    same = entry(world, kind, body, establish=True)
    assert same["standing"]["stands"] is True
    # ...while an explicit false is still honoured.
    held = entry(world, kind, body, establish=False)
    assert held["standing"]["stands"] is False


def test_a_finding_with_its_basis_is_exactly_as_it_was_by_omission(world):
    note = entry(world, "note", {"text": "Run 14 took 9s."})["entry"]
    assert _walks(world["corpus"], "finding") is False
    said = entry(world, "finding", {"text": "Cold starts cost 9s."},
                 basis=[note])
    assert "error" not in said, said
    assert said["standing"]["stands"] is True
    assert said["basis"]


def test_a_kind_that_has_not_said_whether_standing_applies_is_unchanged(world):
    """`standing_apt` absent and no `knowing` is UNKNOWN, which is not converted
    to "governing": the fixture's `constraint` Kind is written as before."""
    cur = world["corpus"].current_definition("constraint")["body"]
    assert "standing_apt" not in cur and not cur.get("knowing")
    said = entry(world, "constraint", {"limit": "No deploys on Friday."})
    assert "error" not in said, said
    assert said["standing"]["stands"] is True


def test_a_proposal_made_by_omission_can_then_be_established(world):
    """Nothing is lost by the default: the owner's establish act is the door
    it always was, and the record it acts on is the one written."""
    said = entry(world, "rule", {"text": "Name every migration."})
    assert said["standing"]["stands"] is False
    done = post(world, "/api/entries/" + said["entry"] + "/establish",
                {"attributed_to": world["owner"], "because": "agreed"})
    assert "error" not in done, done
    assert world["corpus"].stands(said["entry"])["stands"] is True


def test_what_was_already_established_is_not_touched(world):
    stood = entry(world, "rule", {"text": "Stands."}, establish=True)["entry"]
    before = world["corpus"].stands(stood)
    entry(world, "rule", {"text": "Proposed beside it."})
    assert world["corpus"].stands(stood) == before
    assert before["stands"] is True


# -- the Persona door --------------------------------------------------------

def persona(world, **more):
    return post(world, "/api/personas",
                {"name": "Reviewer", "behaviour": "challenge the claim",
                 "attributed_to": world["owner"], **more})


def test_a_persona_is_a_proposal_when_nothing_is_said(world):
    said = persona(world)
    assert "error" not in said, said
    assert said["standing"]["stands"] is False
    # Recorded, and not offered: the picker lists only Personas that stand.
    assert world["corpus"].read([said["persona"]])
    offered = [p["persona"] for p in get(world, "/api/personas")["personas"]]
    assert said["persona"] not in offered


def test_a_persona_is_established_only_when_the_request_says_so(world):
    said = persona(world, establish=True)
    assert said["standing"]["stands"] is True
    offered = [p["persona"] for p in get(world, "/api/personas")["personas"]]
    assert said["persona"] in offered


def test_propose_still_means_do_not_establish(world):
    assert persona(world, propose=True)["standing"]["stands"] is False
    assert persona(world, propose=True,
                   establish=False)["standing"]["stands"] is False
    # `propose: false` is not `establish: true`: saying only what is NOT
    # wanted asks for nothing, and nothing is established by omission.
    assert persona(world, propose=False)["standing"]["stands"] is False
    # ...and the two agreeing on establishing is not a contradiction.
    assert persona(world, propose=False,
                   establish=True)["standing"]["stands"] is True


@pytest.mark.parametrize("flags", [{"establish": True, "propose": True},
                                   {"establish": False, "propose": False}])
def test_contradictory_persona_flags_are_refused_and_nothing_is_written(
        world, flags):
    before = len(world["corpus"].entries_of_kind("persona"))
    refused = persona(world, **flags)
    assert "contradict" in refused["error"]
    assert "persona" not in refused
    assert len(world["corpus"].entries_of_kind("persona")) == before


def test_a_persona_still_needs_its_fields_and_an_attribution(world):
    assert "error" in post(world, "/api/personas",
                           {"name": "Empty", "establish": True})
    assert "error" in post(world, "/api/personas",
                           {"name": "Nobody", "behaviour": "x",
                            "establish": True})


# -- the instruction door, which already answered this way --------------------

def test_the_instruction_door_is_unchanged(world):
    path = "/api/conversations/" + world["conv"] + "/instructions"
    proposed = post(world, path, {"text": "Merely proposed.",
                                  "attributed_to": world["owner"]})
    assert proposed["standing"]["stands"] is False
    stood = post(world, path, {"text": "Holds here.", "establish": True,
                               "attributed_to": world["owner"]})
    assert stood["standing"]["stands"] is True and stood["governs"] is True
    refused = post(world, path, {"text": "Not mine to establish.",
                                 "establish": True,
                                 "attributed_to": world["agent"]})
    assert "only the owner may establish" in refused["error"]


# -- establishing is said with true or false, and nothing else ----------------
#
# The doors took `establish` by truthiness, so the string "false" established
# governing material (independent review, 2026-11-18). A value that is neither
# true nor false is refused and nothing is written.

NOT_BOOLEANS = ["false", "true", "no", 1, 0, None, [], {}]


@pytest.mark.parametrize("said", NOT_BOOLEANS)
def test_a_rule_is_not_written_for_an_establish_that_is_not_true_or_false(world, said):
    before = len(world["corpus"].entries_of_kind("rule"))
    r = entry(world, "rule", {"text": "Measure first."}, establish=said)
    assert "error" in r and r["field"] == "establish", r
    assert len(world["corpus"].entries_of_kind("rule")) == before


@pytest.mark.parametrize("said", NOT_BOOLEANS)
def test_a_persona_is_not_written_for_an_establish_that_is_not_true_or_false(world, said):
    before = len(world["corpus"].entries_of_kind("persona"))
    r = post(world, "/api/personas", {"name": "Reviewer", "behaviour": "Reads the diff.",
                                      "attributed_to": world["owner"], "establish": said})
    assert "error" in r and r["field"] == "establish", r
    assert len(world["corpus"].entries_of_kind("persona")) == before


@pytest.mark.parametrize("said", ["false", 1, None])
def test_a_persona_propose_that_is_not_true_or_false_is_refused(world, said):
    r = post(world, "/api/personas", {"name": "Reviewer", "behaviour": "Reads the diff.",
                                      "attributed_to": world["owner"], "propose": said})
    assert "error" in r and r["field"] == "propose", r


@pytest.mark.parametrize("said", NOT_BOOLEANS)
def test_an_instruction_is_not_written_for_an_establish_that_is_not_true_or_false(world, said):
    before = len(world["corpus"].entries_of_kind("conversation-instruction"))
    r = post(world, f"/api/conversations/{world['conv']}/instructions",
             {"text": "Keep answers short.", "attributed_to": world["owner"], "establish": said})
    assert "error" in r and r["field"] == "establish", r
    assert len(world["corpus"].entries_of_kind("conversation-instruction")) == before


def test_the_authoring_read_says_which_kind_is_placed_only_by_reference(world):
    kinds = {k["kind"]: k for k in get(world, "/api/governance/authoring")["kinds"]}
    assert kinds["workflow"]["authoring"]["by_reference"] is True
    assert kinds["discipline"]["authoring"]["by_reference"] is False
