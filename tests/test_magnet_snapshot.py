"""The one validated definition snapshot and the boundary it is read under.

Revised security contract adm-c5c73679ac1e §3 and §6 (Part B's amendment). What
these prove, in the contract's own terms:

  * `configuration_digest` covers the ENTIRE validated durable definition, and
    nothing of the arrangement, the derived collection or the nonauthoritative
    own-Conversation mirror.
  * One read, under the same serialization boundary definition mutation is made
    under, retained through the caller's commit or refusal, so a concurrent save
    cannot validate one definition and persist another.
  * An explicit stale revision refuses; a definition replaced by a writer that
    did not take the boundary refuses rather than being published as atomic.
  * Zero-source definitions are included, like any other.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import threading

import pytest

import mentis.magnet as M
from mentis.fluid import _checks as W
from mentis.fluid import arrangements as A
from mentis.magnet import schema as S
from mentis.magnet import snapshot as SNAP

VECTORS = (pathlib.Path(__file__).parent / "fixtures"
           / "magnet-definition-digest" / "vectors.json")
KEY = "ent-a"


@pytest.fixture()
def root(tmp_path):
    return str(tmp_path)


def seed(**over):
    return {"sources": [], "selection": {}, "collection": {"mode": "one-time"},
            "synthesis": {"mode": "manual"},
            "notifications": {"newItems": False, "changes": False,
                              "failures": False},
            "presentation": {"renderer": "disc"}, **over}


def layout():
    return {"format": A.FORMAT, "version": 3,
            "tree": {"type": "zone", "id": "stage", "show": "objects"}}


def made(root, **over):
    W._atomic(pathlib.Path(root) / "presentation" / A.FOLDER / f"{KEY}.json",
              {"key": KEY, "layout": A.check(layout()), "saved": 1.0, "ops": []})
    got = A.create_magnet(root, KEY, {
        "seed": seed(**over),
        "attach": {"zone": {"type": "zone", "show": "magnet", "name": "Board"}}})
    return got["magnet"]["id"]


def definition_path(root, mid):
    return pathlib.Path(root) / "presentation" / M.FOLDER / f"{mid}.json"


# -- the digest and its canonical bytes -------------------------------------------------

def test_the_golden_vectors_are_what_this_half_writes():
    """The one file both halves are held to. Neither generates it from the
    other: the client's `canonicalDefinition`/`configurationDigest` are checked
    against these same bytes in `quiet_magnet_configuration_unit.ts`."""
    book = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert len(book["vectors"]) >= 9 and book["refused"]
    for v in book["vectors"]:
        got = SNAP.canonical(v["definition"])
        assert got.decode("utf-8") == v["canonical"], v["name"]
        assert SNAP.digest(v["definition"]) == v["digest"], v["name"]
        assert len(v["digest"]) == 64 and v["digest"] == v["digest"].lower()
        # Canonical: sorted keys, no whitespace, no BOM, literal Unicode.
        assert b"\xef\xbb\xbf" not in got and b": " not in got and b", " not in got
        assert json.loads(got.decode("utf-8")) == SNAP.durable(v["definition"])
    for r in book["refused"]:
        with pytest.raises(SNAP.NotCanonical) as exc:
            SNAP.canonical(r["definition"])
        assert str(exc.value) == r["wording"], r["name"]


def test_the_digest_covers_the_whole_definition_and_not_the_mirror():
    base = S.magnet_config({"id": "mag-cover", **seed()}, "definition")
    first = SNAP.digest(base)
    # Every facet, optional or not, moves it.
    for change in ({"sources": [{"kind": "conversation",
                                 "conversation": "ent-src1"}]},
                   {"selection": {"criteria": "tides"}},
                   {"selection": {"filters": {"a": 1}}},
                   {"selection": {"filters": {"a": 2}}},
                   {"collection": {"mode": "paused"}},
                   {"synthesis": {"mode": "scheduled", "schedule": "PT1H"}},
                   {"notifications": {"newItems": True, "changes": False,
                                      "failures": False}},
                   {"presentation": {"renderer": "list"}},
                   {"presentation": {"renderer": "disc", "theme": "glass"}},
                   {"activation": {"mode": "event", "event": "x"}},
                   {"processing": {"operations": [{"op": "extract"}]}},
                   {"ai": {"mode": "selective"}},
                   {"outputs": ["records"]},
                   {"destinations": [{"kind": "brain"}]},
                   {"identity": {"name": "Tide study"}}):
        other = S.magnet_config({**base, **change}, "definition")
        assert SNAP.digest(other) != first, change
    # The mirror and the file's own version are carried beside it, not in it.
    for beside in ({"conversation": "ent-mirror1"}, {"schema_version": 1},
                   {"conversation": None}):
        assert SNAP.digest(S.magnet_config({**base, **beside},
                                           "definition")) == first, beside
    assert SNAP.durable({**base, "conversation": "ent-m", "schema_version": 1}) == base
    # A facet a later schema adds is covered without this module being told:
    # the coverage is everything but those two fields.
    assert SNAP.canonical({**base, "whatever": {"a": 1}}) != SNAP.canonical(base)


def test_a_source_free_definition_is_snapshotted_like_any_other():
    none = S.magnet_config({"id": "mag-free", **seed()}, "definition")
    one = S.magnet_config({"id": "mag-free", **seed(sources=[
        {"kind": "conversation", "conversation": "ent-src1"}])}, "definition")
    assert b'"sources":[]' in SNAP.canonical(none)
    assert SNAP.digest(none) != SNAP.digest(one)


def test_what_cannot_be_digested_the_same_in_both_halves_is_refused():
    base = {"id": "mag-x", **seed()}
    with pytest.raises(SNAP.NotCanonical, match="not an integer"):
        SNAP.canonical({**base, "selection": {"filters": {"n": 1.5}}})
    with pytest.raises(SNAP.NotCanonical, match="lone surrogate"):
        SNAP.canonical({**base, "identity": {"name": "a\ud800b"}})
    with pytest.raises(SNAP.NotCanonical, match="not a key"):
        SNAP.canonical({**base, "0": 1})
    with pytest.raises(SNAP.NotCanonical, match="not a value"):
        SNAP.canonical({**base, "identity": {"name": object()}})


# -- one read, under the boundary ------------------------------------------------------

def test_a_snapshot_is_one_validated_read_with_the_mirror_recorded_beside_it(root):
    mid = made(root, identity={"name": "Tide study"})
    M.set_conversation(root, mid, "ent-own11111")
    with SNAP.holding(root, mid) as snap:
        assert snap.magnet == mid and snap.digest == snap.revision
        assert snap.conversation == "ent-own11111", "beside the digest"
        assert snap.schema_version == M.SCHEMA_VERSION
        assert snap.definition["identity"] == {"name": "Tide study"}
        assert "conversation" not in snap.value
        raw = definition_path(root, mid).read_bytes()
        assert snap.file_sha256 == hashlib.sha256(raw).hexdigest()
        assert snap.digest != snap.file_sha256, "canonical, not the file's bytes"
        assert SNAP.digest(snap.definition) == snap.digest
    assert SNAP.unchanged(root, snap)
    # The mirror changing does not move the digest, and the file's bytes do.
    M.correct_conversation(root, mid, "ent-other1111")
    assert SNAP.take(root, mid).digest == snap.digest
    assert not SNAP.unchanged(root, snap), "the file is not the same file"


def test_a_definition_there_is_none_of_is_declined_and_an_unreadable_one_refuses(root):
    made(root)
    with pytest.raises(M.Declined) as exc:
        with SNAP.holding(root, "mag-nothing"):
            pass
    assert exc.value.reason["message"] == M.MISSING
    mid = made(root)
    definition_path(root, mid).write_text("{not json", encoding="utf-8")
    with pytest.raises(M.Unreadable):
        with SNAP.holding(root, mid):
            pass
    with pytest.raises(SNAP.TooLarge):
        SNAP.raw_bytes(root, mid, most=4)


def test_the_boundary_is_the_one_every_definition_write_is_made_under(root):
    assert M.boundary(root) is W._lock(root)
    # Re-entrant, so a writer that reads what it replaces holds it once.
    with M.boundary(root):
        with M.boundary(root):
            pass


def test_an_explicit_stale_revision_refuses_and_substitutes_nothing(root):
    mid = made(root)
    with SNAP.holding(root, mid) as snap:
        first = snap.revision
    A.reconfigure_magnet(root, KEY, mid, {"change": {"identity": {"name": "New"}}})
    with pytest.raises(SNAP.Stale, match="another revision"):
        with SNAP.holding(root, mid, expect=first):
            pytest.fail("nothing is yielded for a stale revision")
    # The revision it is now is readable, and is a different one.
    with SNAP.holding(root, mid, expect=SNAP.take(root, mid).revision) as now:
        assert now.revision != first


def test_a_concurrent_save_cannot_validate_one_definition_and_persist_another(root):
    """§3's linearization: a concurrent update is either before the read, or
    after the commit, and never between the validation and the commit."""
    mid = made(root)
    asked, done = threading.Event(), threading.Event()
    outcome = {}

    def save():
        asked.wait(10)
        outcome["magnet"] = A.reconfigure_magnet(
            root, KEY, mid, {"change": {"identity": {"name": "Renamed"}}})["magnet"]
        done.set()

    writer = threading.Thread(target=save, name="definition-save")
    writer.start()
    try:
        with SNAP.holding(root, mid) as snap:
            before, bytes_before = snap.revision, snap.canonical
            disk_before = definition_path(root, mid).read_bytes()
            asked.set()
            # The write waits for this boundary: nothing lands between the
            # snapshot's validation and the caller's commit.
            assert not done.wait(1.0), "a definition write waits for the hold"
            assert SNAP.take(root, mid).revision == before, "still one revision"
            assert definition_path(root, mid).read_bytes() == disk_before
    finally:
        writer.join(10)
    assert done.is_set() and outcome["magnet"]["identity"] == {"name": "Renamed"}
    # The snapshot taken before the commit stays frozen; the definition moved on.
    assert snap.canonical == bytes_before and snap.revision == before
    assert SNAP.take(root, mid).revision != before
    assert not SNAP.unchanged(root, snap)


def test_a_write_that_did_not_take_the_boundary_refuses_rather_than_publish(root):
    """§3: if the seam cannot serialize these operations, refuse rather than
    publish a falsely atomic snapshot."""
    mid = made(root)
    with pytest.raises(SNAP.NotSerialized, match="not serialized"):
        with SNAP.holding(root, mid) as snap:
            W._atomic(definition_path(root, mid),
                      {**snap.definition, "schema_version": 1,
                       "presentation": {"renderer": "list"}})
    # A caller that IS the writer says so, and is not accused of racing itself.
    with SNAP.holding(root, mid, writes=True) as snap:
        M.write(root, mid, {**snap.definition,
                            "presentation": {"renderer": "cards"}})
    assert SNAP.take(root, mid).definition["presentation"] == {"renderer": "cards"}


def test_the_activation_protocols_own_digest_is_unchanged_by_this_seam(root):
    """The protocol hashes the definition's exact file bytes, which Rust
    verifies. That number is not the canonical one and neither stands in for
    the other."""
    mid = made(root)
    raw = SNAP.raw_bytes(root, mid)
    assert raw == definition_path(root, mid).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SNAP.take(root, mid).file_sha256
    assert SNAP.raw_bytes(root, "mag-nothing1") == b"", "no definition, no bytes"
