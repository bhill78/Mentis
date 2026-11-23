"""Shared Rust/Python retained-source conformance Brain. No source folder is bound."""
import json
import pathlib
import sys

from mentis.sources import _admission
from mentis.spine import held
from mentis.web import fixture, _State

CASES = pathlib.Path(__file__).resolve().parents[1] / "tests/fixtures/magnet-conformance/held-files.json"
COLLECTION = "col-held-conformance"


def build(root):
    root = pathlib.Path(root)
    fixture.build(str(root))
    st = _State(str(root))
    corpus, cv = st.corpus, st.cv
    actor = corpus.entries_of_kind("participant")[0]["id"]
    cv.record_act(actor=actor, act="source-collection-declared", about=[COLLECTION],
        detail={"collection": COLLECTION, "name": "Held conformance", "connector": "filesystem"})
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    for case in cases:
        case["path"] = case["name"] + ".txt"
        if case.get("damage") == "unobserved":
            continue
        data = (bytes.fromhex(case["hex"]) if "hex" in case else
            (case.get("text", case.get("repeat", "") * case.get("count", 0)) + case.get("tail", "")).encode())
        digest, _ = held.put(root, data)
        obs = {"object": case["path"], "state": "present", "retention": "held", "digest": digest,
               "size": len(data), "payload_type": "text/plain", "encoding": {"text": case.get("text_flag", True)},
               "relations": []}
        def admit(observation):
            return corpus.admit(**_admission(source=f"filesystem:{COLLECTION}", collection=COLLECTION,
                connector="filesystem", obs=observation, action="new", tok="fixture", batch="fixture",
                scope={}, observed_at=1700000000.0), attributed_to=actor, written_by="fixture")
        ref = admit(obs)
        if case.get("damage") == "deleted":
            ref = admit({**obs, "state": "absent"})
        if case.get("damage") == "purged":
            corpus.link_many([{"from": actor, "to": ref, "relation": held.PURGED}],
                             body={}, attributed_to=actor)
        if case.get("damage") == "missing":
            held.path(root, digest).unlink()
        if case.get("damage") == "corrupt":
            held.path(root, digest).write_bytes(b"spoiled")
        case.update(ref=ref, digest=digest, size=len(data))
    (root / "held-cases.json").write_text(json.dumps(cases), encoding="utf-8")
    template = json.loads((CASES.parent / "activation/artifacts/complete.bin").read_bytes())
    definition = template["definition"]["value"]
    definition["sources"] = [{"kind": "conversation", "conversation": corpus.entries_of_kind("conversation")[0]["id"]}]
    definition["sources"] += [{"kind": "file", "collection": COLLECTION, "path": c["path"]} for c in cases]
    definition["selection"] = {"informationTypes": ["post"], "dates": {"after": "2099-01-01"}}
    (root / "held-definition.json").write_text(json.dumps(definition), encoding="utf-8")
    corpus.close()
    return root


def check(root):
    """Compare Rust's captured rows with the existing Python retained-byte reader."""
    from mentis.sources import reading, Refused
    from mentis.magnet import activation as X
    root = pathlib.Path(root)
    st = _State(str(root))
    cases = json.loads((root / "held-cases.json").read_text(encoding="utf-8"))
    pages = json.loads((root / "captured-pages.json").read_text(encoding="utf-8"))
    for case, page in zip(cases, pages, strict=True):
        source = page["sources"][0]
        try:
            python = reading.read(st.corpus, collection=COLLECTION, path=case["path"])
        except (Refused, UnicodeDecodeError):
            assert not case["available"], case
            continue
        if case["available"]:
            row = source["results"][0]
            value = row["value"]
            for key in ("ref", "digest", "collection", "path", "text", "offset", "end", "size", "next_offset"):
                assert value[key] == python[key], (case, key, value, python)
            assert value["citation"] == python["cite"]
            X._verified_file(row, source["source"], ValueError("invalid Rust file result"))
        else:
            assert "bytes_b64" in python and not source["results"], (case, python)
    st.corpus.close()
    # The combined M1 output must pass the real new-activation preflight/commit and
    # historical read. This exercises the whole Python verifier, Admission and act.
    from tests import conftest  # isolated owner session for fixture HTTP
    from tests.test_magnet_activation import World, artifact_of, ask_preflight, asked_body, ask_commit
    from mentis.magnet import checked, collection
    import hashlib
    w = World(root)
    try:
        config = json.loads((root / "held-definition.json").read_text(encoding="utf-8"))
        batches = [{"definition": config, "page": json.loads(
            (root / "captured-batch-page.json").read_text(encoding="utf-8"))}]
        batches += json.loads((root / "captured-file-only-batches.json").read_text(encoding="utf-8"))
        for index, batch in enumerate(batches):
            op = f"rust-held-conformance-{index}"
            art = json.loads(artifact_of(w, op=op))
            config = batch["definition"]
            raw_definition = json.dumps(config)
            art["definition"] = {"sha256": hashlib.sha256(raw_definition.encode()).hexdigest(),
                "raw": raw_definition, "value": checked(art["magnet"], config)}
            art["page"] = batch["page"]
            w.define(raw_definition)
            ready = ask_preflight(w, asked_body(w, op=op))
            assert ready["state"] == "ready", ready
            answer = ask_commit(w, json.dumps(art).encode())
            assert answer["state"] == "committed", answer
            assert answer["body"]["state"] == ("complete" if index == 1 else "partial")
            result = collection.read(w.state, art["magnet"])
            assert result["page"] == art["page"]
            assert result["config"]["sources"] == config["sources"]
    finally:
        w.stop()
        w.corpus.close()
    print(f"{len(cases)} shared Python/Rust retained-source cases checked")


if __name__ == "__main__":
    if sys.argv[1] == "--check":
        check(sys.argv[2])
    else:
        build(sys.argv[1])
