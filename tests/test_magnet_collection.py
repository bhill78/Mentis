"""Retained collection reads and the Brain binding at both private write phases."""
import hashlib
import json
import shutil

import pytest

from mentis.fluid.inspect import brain_key
from mentis.magnet import activation as X
from mentis.spine import held
from tests.test_magnet_activation import (
    COMMIT, JSON_HEADERS, MAGNET, PREFLIGHT,
    artifact_of, ask_commit, asked_body, built, define_from, preflight_wire,
    private, record_size, send, world,
)


def get(w, headers=()):
    return send(w.alone, f"/fluid/api/magnets/{MAGNET}/collection",
                [*JSON_HEADERS, *headers], b"", method="GET")


def test_missing_definition_and_legacy_no_collection_are_honest(world):
    assert get(world)["status"] == 404
    define_from(world, artifact_of(world))
    before = record_size(world)
    got = get(world)
    assert got["status"] == 200
    assert json.loads(got["body"]) == {"magnet": MAGNET,
        "config": json.loads(artifact_of(world))["definition"]["value"],
        "activation": None, "page": None}
    assert record_size(world) == before


@pytest.mark.parametrize("name", ["complete", "partial-non-ascii", "linked-and-objects"])
def test_entire_retained_page_and_latest_activation_survive_config_changes(world, name):
    first = artifact_of(world, op="first")
    define_from(world, first)
    first_answer = ask_commit(world, first)["body"]
    raw = artifact_of(world, name, op="second")
    define_from(world, raw)
    second = ask_commit(world, raw)["body"]
    # A changed source/config must not be consulted to recreate retained evidence.
    config = json.loads(raw)["definition"]["value"]
    world.define({**config, "sources": [{"kind": "conversation", "conversation": "ent-gone"}]})
    before = record_size(world)
    got = get(world)
    assert got["status"] == 200, got
    body = json.loads(got["body"])
    assert set(body) == {"magnet", "config", "activation", "page"}
    assert body["page"] == json.loads(raw)["page"]
    assert body["config"]["sources"][0]["conversation"] == "ent-gone"
    assert body["activation"] == {"post": second["post"], "artifact": second["artifact"],
        "at": world.corpus.operational(act=X.MAGNET_EXTRACTED, newest_first=True)[0]["at"],
        "state": second["state"]}
    assert held.read(world.root, first_answer["artifact"]["digest"]) == first
    assert record_size(world) == before


@pytest.mark.parametrize("damage", ["missing", "corrupt", "invalid-format", "wrong-magnet"])
def test_missing_corrupt_or_wrong_identity_collection_refuses_without_live_fallback(world, damage, monkeypatch):
    raw = artifact_of(world)
    define_from(world, raw)
    result = ask_commit(world, raw)["body"]
    digest = result["artifact"]["digest"]
    if damage in ("missing", "corrupt"):
        path = held.path(world.root, digest)  # fixture bytes only
        if damage == "missing":
            path.unlink()
        else:
            path.write_bytes(b"spoiled")
    else:
        from mentis import artifacts
        original = artifacts.describe
        def describe(corpus, ref, **kwargs):
            got = original(corpus, ref, **kwargs)
            art = json.loads(raw)
            art["format" if damage == "invalid-format" else "magnet"] = "wrong"
            changed = json.dumps(art).encode()
            # A self-consistent held blob and record still must have the right format/identity.
            got.update(_bytes=changed, size=len(changed), digest=hashlib.sha256(changed).hexdigest())
            return got
        monkeypatch.setattr(artifacts, "describe", describe)
        operational = world.corpus.operational
        def acts(**kwargs):
            rows = operational(**kwargs)
            if kwargs.get("act") == X.MAGNET_EXTRACTED:
                got = describe(world.corpus, result["artifact"]["ref"])
                rows = [{**r, "detail": {**r["detail"], "artifact": {
                    **r["detail"]["artifact"], "digest": got["digest"], "size": got["size"]}}}
                    for r in rows]
            return rows
        monkeypatch.setattr(world.corpus, "operational", acts)
    before = record_size(world)
    got = get(world)
    assert got["status"] == 422, got
    assert json.loads(got["body"])["refused"] is True
    assert record_size(world) == before


def test_worker_grant_cannot_use_owner_collection_surface(world):
    assert get(world, [["X-Mentis-Worker", "forged"]])["status"] == 403


@pytest.mark.parametrize("step", ["preflight", "commit"])
@pytest.mark.parametrize("binding", ["match", "changed", "unconfirmed"])
def test_both_private_phases_enforce_the_existing_brain_guard(world, step, binding, monkeypatch):
    from mentis.fluid import inspect
    raw = artifact_of(world)
    define_from(world, raw)
    key = brain_key(world.corpus)
    assert key
    if binding == "unconfirmed":
        def failed(_):
            raise OSError("fixture cannot confirm")
        monkeypatch.setattr(inspect, "brain_key", failed)
    headers = [["X-Mentis-Brain", key if binding != "changed" else "another-brain"]]
    if step == "commit":
        headers.append([X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()])
    before = record_size(world)
    got = private(world, PREFLIGHT if step == "preflight" else COMMIT,
                  preflight_wire(asked_body(world)) if step == "preflight" else raw,
                  headers=headers)
    answer = json.loads(got["body"])
    if binding == "match":
        assert answer["state"] == ("ready" if step == "preflight" else "committed"), answer
    else:
        assert answer["status"] == 409, answer
        assert answer["body"]["kind"] == ("BrainChanged" if binding == "changed" else "BrainUnconfirmed")
        assert record_size(world) == before
        assert held.blobs(world.root) == []


def test_switch_between_private_phases_refuses_before_any_commit(world, built, tmp_path):
    from mentis.web import _State
    raw = artifact_of(world)
    define_from(world, raw)
    key = brain_key(world.corpus)
    headers = [["X-Mentis-Brain", key]]
    ready = json.loads(private(world, PREFLIGHT, preflight_wire(asked_body(world)), headers=headers)["body"])
    assert ready["state"] == "ready"
    # The same private listener now serves another fixture Brain, as an address reused
    # after a switch would. It has no Magnet definition, so an accidental lift/commit
    # there would be visible as well as a record write.
    other_root = tmp_path / "switched-brain"
    shutil.copytree(built, other_root)
    other = _State(str(other_root))
    assert brain_key(other.corpus) != key
    other_before = other.corpus.advance()
    world.servers[-1].RequestHandlerClass.state = other
    before = record_size(world)
    refused = json.loads(private(world, COMMIT, raw, headers=[*headers,
        [X.DIGEST_HEADER, hashlib.sha256(raw).hexdigest()]])["body"])
    assert refused["status"] == 409 and refused["body"]["kind"] == "BrainChanged"
    assert record_size(world) == before and held.blobs(world.root) == []
    assert other.corpus.advance() == other_before and held.blobs(other_root) == []
    assert not (other_root / "presentation" / "magnets").exists()
    other.corpus.close()
