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
        "activation": None, "page": None, "references": {}}
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
    assert set(body) == {"magnet", "config", "activation", "page", "references"}
    # The recorded page is served exactly as recorded; what each row can be
    # referred to by is derived beside it, never written into it.
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


def _rows(page):
    return [r for one in page["sources"] for r in one["results"]]


def test_each_collected_row_is_served_the_exact_identity_it_can_be_referred_to_by(world):
    """The owner's §§1/6 requirement: a supporting record is something a
    message can be about. The identity is the row's captured version -- the
    recorded batch and that row's own digest -- and it carries no content."""
    from mentis.magnet.collection import row_digest
    raw = artifact_of(world, "linked-and-objects")
    define_from(world, raw)
    result = ask_commit(world, raw)["body"]
    body = json.loads(get(world)["body"])
    rows = _rows(body["page"])
    assert rows, "the fixture page must actually hold collected rows"
    assert set(body["references"]) == {r["id"] for r in rows}
    for row in rows:
        got = body["references"][row["id"]]
        assert got == {"kind": "collected_item", "ref": row["id"],
                       "version": result["artifact"]["ref"], "digest": row_digest(row)}
        # Identity, not content: no text, parts, title, label or bytes.
        assert set(got) == {"kind", "ref", "version", "digest"}
    # Recomputed from the row as recorded, so a different row is a different
    # digest and nothing is derived from captured text alone.
    assert len({v["digest"] for v in body["references"].values()}) == len(rows)
    assert row_digest(rows[0]) != row_digest({**rows[0], "id": "ent-elsewhere11"})


def test_a_collected_row_is_referable_only_against_this_magnets_own_recorded_batch(world):
    """The send boundary's membership check: forged, foreign, stale and
    unreadable selections all refuse, and none of them reads a live source."""
    from mentis.fluid.inspect import brain_key  # noqa: F401  (fixture parity)
    from mentis.conversation.versions import Refused
    from mentis.magnet.collection import member
    raw = artifact_of(world, "linked-and-objects")
    define_from(world, raw)
    result = ask_commit(world, raw)["body"]
    body = json.loads(get(world)["body"])
    row = _rows(body["page"])[0]
    good = body["references"][row["id"]]
    before = record_size(world)
    assert member(world, MAGNET, good) == good

    def refused(selected):
        with pytest.raises(Refused) as caught:
            member(world, MAGNET, selected)
        return caught.value.refusal

    assert refused({**good, "digest": "f" * 64})["code"] == "stale-reference"
    assert refused({**good, "ref": "ent-neverthere1"})["code"] == "stale-reference"
    assert refused({**good, "version": "adm-000000000000"})["code"] == "stale-reference"
    assert refused({**good, "version": result["artifact"]["ref"].upper()})["code"] == "invalid-reference"
    assert refused({**good, "version": None})["code"] == "invalid-reference"
    # Another Magnet's id cannot reach this Magnet's recorded batch.
    with pytest.raises(Refused) as foreign:
        member(world, "mag-somebody-else", good)
    assert foreign.value.refusal["code"] == "stale-reference"
    # A batch whose bytes no longer verify is stale, never substituted.
    held.path(world.root, result["artifact"]["digest"]).write_bytes(b"spoiled")
    assert refused(good)["code"] == "stale-reference"
    assert record_size(world) == before, "checking membership writes nothing"


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
