"""The contract the result opener's fresh read depends on.

`apps/fluid-web/src/quiet2/results/refRead.ts` (`artifactNow`) reads
`GET /api/artifacts/<ref>?describe=1` before it opens any result, and fails
closed on anything that is not "this exact reference is held here now"
(independent re-review adm-d84456fd4c3c, B4.1). Nothing on the server changed
for that: the route, its 200-for-every-state answer and its worker refusal
already existed, and the Composer already consumes it. These checks pin exactly
what that client is entitled to assume, so a later change to the route breaks a
test here rather than silently making a purged result open again.

Disposable fixture Brain, built per test class. No HTTP listener, no browser,
no production Brain and no credentials: the handler method is called directly,
as the other handler tests here do.
"""

from __future__ import annotations

import pathlib
import types

import pytest

from mentis import artifacts as _artifacts
from mentis.spine import held
from mentis.web import _Handler, fixture
from mentis.worker import CAPABILITY_HEADER


@pytest.fixture()
def world(tmp_path: pathlib.Path):
    built = fixture.build(str(tmp_path / "brain"))
    return types.SimpleNamespace(
        root=pathlib.Path(built["corpus"].root),
        corpus=built["corpus"],
        cv=built["cv"],
        actor=built["who"]["@brian"],
    )


def _hold(world, data: bytes, *, name="claimed.png", claimed="image/png"):
    return _artifacts.hold(
        world.corpus, world.cv, data, act=_artifacts.SUBMITTED, actor=world.actor,
        source="artifact describe contract test", door="human",
        claimed_name=name, claimed_media_type=claimed)


def _describe(world, ref, headers=None):
    """`?describe=1` for one ref, as `do_GET` dispatches it."""
    out = []
    handler = types.SimpleNamespace(
        headers=headers or {},
        state=types.SimpleNamespace(corpus=world.corpus),
        _artifact_send=lambda status, body: out.append((status, body)))
    _Handler._artifact(handler, ref, describe=True)
    assert len(out) == 1
    return out[0]


def test_held_answers_exact_identity_verified_treatment_and_no_bytes(world):
    """The one answer that lets an open through, with what the client reads."""
    a = _hold(world, b"An actual text report, not an image.\n")
    status, d = _describe(world, a["admission"])
    assert status == 200
    assert d["ref"] == a["admission"]
    assert d["state"] == "held"
    # the VERIFIED word, read from the bytes and not from the claim
    assert d["treatment"]["view"] == "text"
    assert d["url"] == "/api/artifacts/" + a["admission"]
    # a description is not bytes, and carries no source
    assert "_bytes" not in d
    assert "source" not in d


@pytest.mark.parametrize("state", ["unknown", "purged",
                                   "held-but-missing", "held-but-corrupt"])
def test_every_unavailable_state_is_its_own_word_at_200(world, state):
    """`?describe=1` ANSWERS 200 FOR EVERY STATE, so the state is the check.

    This is the fact B4.1 turned on: a client that reads only the status code
    places a purged or corrupt result as though it were there.
    """
    if state == "unknown":
        ref = "adm-111111111111"
    else:
        a = _hold(world, f"fixture bytes for {state}\n".encode())
        ref = a["admission"]
        if state == "purged":
            _artifacts.purge(world.corpus, world.cv, ref, by=world.actor,
                             because="artifact describe contract test")
        else:
            path = held.path(world.corpus.root, a["digest"])
            if state == "held-but-missing":
                pathlib.Path(path).unlink()
            else:
                pathlib.Path(path).write_bytes(b"changed fixture content\n")
    status, d = _describe(world, ref)
    assert status == 200
    assert d["state"] == state
    assert d["state"] != "held"
    assert "_bytes" not in d
    # AND IT SAYS WHICH REFERENCE IT IS ABOUT, on every state it answers
    # (re-review adm-efb406a34e7a, N5). The client requires the identity
    # rather than checking it only when present, so this is the fact that
    # lets it fail closed on a body that names none without refusing answers
    # the real route gives.
    assert d["ref"] == ref


def test_worker_grant_is_still_refused(world):
    """A description is no more for any reader than the bytes are."""
    status, d = _describe(world, "adm-111111111111",
                          {CAPABILITY_HEADER: "not-a-grant"})
    assert status == 403
    assert "/api/worker" in d["error"]


def test_a_claim_does_not_decide_what_the_bytes_are(world):
    """Text claimed as an image is described as text: the claim is not read."""
    a = _hold(world, b"plain text, claimed as a picture\n",
              name="claimed.png", claimed="image/png")
    _, d = _describe(world, a["admission"])
    assert d["state"] == "held"
    assert d["treatment"]["view"] == "text"
