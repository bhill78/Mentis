"""Shared Rust/Python conformance Brain for the COLLECTION-SCOPED file source.

A `file` source may name one object, every object under a prefix, or a whole declared collection
(`mentis.magnet.activation.file_choice`, `crates/mentis-ops/src/magnet/held_file.rs` `choice`). This
builds one Brain that exercises all three over several connectors, lets Rust read it
(`crates/mentis-ops/tests/magnet_collection_source.rs`), and then checks what Rust produced against
Python's own verifier and the real private activation door.

NO SOURCE FOLDER, NO NETWORK, NO BINDING. Every object here is admitted exactly as a connector admits
one (`mentis.sources._admission`), so the rows are the record's, not a connector's re-run.

WHY A COLLECTION IS DECLARED FOR A CONNECTOR THAT IS NOT AVAILABLE YET (`col-feed`, `rss-atom`): to
prove the reader holds NO LIST of connectors. It reads what the record shows a declared collection
admitted; nothing in the Rust reader names a connector, so Part W's connectors read the moment they
admit their first object.
"""
import json
import pathlib
import sys

from mentis.sources import _admission
from mentis.spine import held
from mentis.web import fixture, _State

ACTIVATION = pathlib.Path(__file__).resolve().parents[1] / "tests/fixtures/magnet-conformance/activation"

#: A filesystem collection with a prefix, a sub-prefix, something outside it, and the three kinds of
#: absence: a latest observation that is absent, a purged one, and one that is not text.
PREFIX_COLLECTION = "col-held-prefix"
#: A git collection: blobs keyed by their tree path, and commits keyed `.git/commits/<sha>`.
GIT_COLLECTION = "col-upstream"
#: A collection declared for a connector this build does not implement yet.
FEED_COLLECTION = "col-feed"
#: Enough objects under three prefixes to reach both the per-source and the per-batch bound.
MANY_COLLECTION = "col-many"
#: Objects per prefix of `col-many`: two past the hundred one source reads.
MANY = 102

SHA_ONE = "4f" * 20
SHA_TWO = "7c" * 20


def _objects():
    """`(collection, connector, [(object, text, media_type, damage, text_flag)])` of every collection."""
    prefix = [
        ("docs/one.md", "# One\nthe first held document\n", "text/markdown", None, True),
        ("docs/two.md", "# Two\nthe second\n", "text/markdown", None, True),
        ("docs/sub/three.md", "# Three\nunder a deeper path\n", "text/markdown", None, True),
        ("notes/four.md", "# Four\noutside the docs prefix\n", "text/markdown", None, True),
        ("docs/gone.md", "once here\n", "text/markdown", "deleted", True),
        ("docs/purged.md", "held then purged\n", "text/markdown", "purged", True),
        ("docs/binary.bin", "not text at all\n", "application/octet-stream", None, False),
    ]
    git = [
        ("schema/schema.json", '{"version":"2.0.0-beta.4"}\n', "application/json", None, True),
        ("docs/overview.md", "# ACP\nwhat the protocol is\n", "text/markdown", None, True),
        (f".git/commits/{SHA_ONE}",
         f"commit {SHA_ONE}\nauthor A <a@example.org>\n\n    docs: announce ACP v2 Preview\n",
         "text/x-git-commit", None, True),
        (f".git/commits/{SHA_TWO}",
         f"commit {SHA_TWO}\nauthor B <b@example.org>\n\n    chore: release schema v2.0.0-beta.4\n",
         "text/x-git-commit", None, True),
    ]
    feed = [
        ("entry/one", "A first feed entry\n", "text/plain", None, True),
        ("entry/two", "A second feed entry\n", "text/plain", None, True),
    ]
    many = [(f"{letter}/{i:03d}.md", f"# {letter} {i}\n", "text/markdown", None, True)
            for letter in ("a", "b") for i in range(MANY)]
    many += [(f"c/{i:03d}.md", f"# c {i}\n", "text/markdown", None, True) for i in range(2)]
    return [(PREFIX_COLLECTION, "filesystem", prefix), (GIT_COLLECTION, "git", git),
            (FEED_COLLECTION, "rss-atom", feed), (MANY_COLLECTION, "filesystem", many)]


def _definition(template, sources):
    value = json.loads(json.dumps(template))
    value["sources"] = sources
    value["selection"] = {"informationTypes": ["post"]}
    return value


def build(root):
    root = pathlib.Path(root)
    fixture.build(str(root))
    st = _State(str(root))
    corpus, cv = st.corpus, st.cv
    actor = corpus.entries_of_kind("participant")[0]["id"]
    rows = {}
    for collection, connector, objects in _objects():
        cv.record_act(actor=actor, act="source-collection-declared", about=[collection],
                      detail={"collection": collection, "name": collection,
                              "connector": connector})
        for obj, text, media_type, damage, text_flag in objects:
            data = text.encode("utf-8")
            digest, _ = held.put(root, data)
            obs = {"object": obj, "state": "present", "retention": "held", "digest": digest,
                   "size": len(data), "payload_type": media_type,
                   "encoding": {"text": text_flag}, "relations": []}

            def admit(observation, _c=collection, _n=connector):
                return corpus.admit(**_admission(
                    source=f"{_n}:{_c}", collection=_c, connector=_n, obs=observation,
                    action="new", tok="fixture", batch="fixture", scope={},
                    observed_at=1700000000.0), attributed_to=actor, written_by="fixture")

            ref = admit(obs)
            if damage == "deleted":
                ref = admit({**obs, "state": "absent"})
            if damage == "purged":
                corpus.link_many([{"from": actor, "to": ref, "relation": held.PURGED}],
                                 body={}, attributed_to=actor)
            rows[f"{collection}/{obj}"] = {
                "collection": collection, "object": obj, "ref": ref, "digest": digest,
                "size": len(data), "readable": damage is None and text_flag,
                "damage": damage, "text": text if text_flag else None}
    template = json.loads((ACTIVATION / "artifacts/complete.bin").read_bytes())["definition"]["value"]
    exact = {"kind": "file", "collection": PREFIX_COLLECTION, "path": "docs/one.md"}
    cases = [
        # (name, sources, whether its page should commit)
        ("whole", [{"kind": "file", "collection": PREFIX_COLLECTION}], True),
        ("prefix", [{"kind": "file", "collection": PREFIX_COLLECTION, "path": "docs/"}], True),
        # THE DONE-WHEN SHAPE: a git collection read whole, beside one exact held file.
        ("git-and-held-file", [{"kind": "file", "collection": GIT_COLLECTION}, exact], True),
        ("unavailable-connector", [{"kind": "file", "collection": FEED_COLLECTION}], True),
        ("bounds", [{"kind": "file", "collection": MANY_COLLECTION, "path": f"{p}/"}
                    for p in ("a", "b", "c")], True),
        ("undeclared", [{"kind": "file", "collection": "col-nothing"}], False),
    ]
    (root / "collection-cases.json").write_text(json.dumps({
        "rows": rows,
        "cases": [{"name": name, "definition": _definition(template, sources), "commits": commits}
                  for name, sources, commits in cases],
        "sha": [SHA_ONE, SHA_TWO], "many": MANY,
    }), encoding="utf-8")
    corpus.close()
    return root


def check(root):
    """Every row Rust produced, through Python's own verifier and the real activation door."""
    import hashlib
    from tests import conftest                                 # noqa: F401  owner session
    from tests.test_magnet_activation import World, artifact_of, ask_preflight, asked_body, ask_commit
    from mentis.magnet import activation as X, checked, collection
    root = pathlib.Path(root)
    plan = json.loads((root / "collection-cases.json").read_text(encoding="utf-8"))
    pages = json.loads((root / "captured-collection-pages.json").read_text(encoding="utf-8"))
    checked_rows = 0
    w = World(root)
    try:
        for index, (case, page) in enumerate(zip(plan["cases"], pages, strict=True)):
            config = case["definition"]
            for one, source in zip(page["sources"], config["sources"], strict=True):
                for row in one["results"]:
                    X._verified_file(row, source, ValueError(f"{case['name']}: bad Rust row"))
                    checked_rows += 1
            op = f"rust-collection-conformance-{index}"
            art = json.loads(artifact_of(w, op=op))
            raw = json.dumps(config)
            art["definition"] = {"sha256": hashlib.sha256(raw.encode()).hexdigest(), "raw": raw,
                                 "value": checked(art["magnet"], config)}
            art["page"] = page
            w.define(raw)
            ready = ask_preflight(w, asked_body(w, op=op))
            assert ready["state"] == "ready", (case["name"], ready)
            answer = ask_commit(w, json.dumps(art).encode())
            if not case["commits"]:
                assert answer["state"] == "refused", (case["name"], answer)
                assert answer["body"]["reason"]["code"] == "no-readable-source", answer
                continue
            assert answer["state"] == "committed", (case["name"], answer)
            retained = collection.read(w.state, art["magnet"])
            assert retained["page"] == art["page"], case["name"]
            assert retained["config"]["sources"] == config["sources"], case["name"]
    finally:
        w.stop()
        w.corpus.close()
    print(f"{checked_rows} collection-scoped rows checked across {len(pages)} pages")


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        check(sys.argv[2])
    else:
        build(sys.argv[1])
