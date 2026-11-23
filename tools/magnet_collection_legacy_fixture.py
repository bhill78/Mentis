"""Produce the immutable pre-change Brain using 12fecc01's actual HTTP write phases.

Run ONLY on that baseline, before changing activation/collection. The zip is a whole
fixture Brain, not a JSON replay. It contains actual Admissions and operational acts.
"""
import hashlib
import json
import pathlib
import shutil
import subprocess
import tempfile

from tests import conftest  # isolated fixture owner session
from tests.test_magnet_activation import (
    World, artifact_of, define_from, ask_preflight, asked_body, ask_commit,
)
from mentis.magnet import checked, schema
from mentis.web import fixture


def main():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    assert commit == "12fecc0172eaca0745fd0eeda3dba9a43d54df54", commit
    destination = pathlib.Path("tests/fixtures/magnet-conformance/legacy")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        root = pathlib.Path(temp) / "brain"
        fixture.build(str(root))
        w = World(root)
        try:
            art = json.loads(artifact_of(w, op="authentic-pre-change"))
            conversations = w.corpus.entries_of_kind("conversation")[:2]
            sources = [{"kind": "conversation", "conversation": c["id"]} for c in conversations]
            sources.append({"kind": "file", "collection": "col-legacy"})
            config = {**art["definition"]["value"], "sources": sources}
            raw_definition = json.dumps(config)
            art["definition"] = {"sha256": hashlib.sha256(raw_definition.encode()).hexdigest(),
                                 "raw": raw_definition, "value": checked(art["magnet"], config)}
            template = art["page"]["sources"][0]
            rows = []
            for source in sources:
                results = []
                if source["kind"] == "conversation":
                    posts = w.corpus.links(relation="in-conversation", to=source["conversation"])
                    for link in posts[:1]:
                        post = w.corpus.read([link["link"]["from"]])[0]
                        results.append({"kind": "post", "id": post["id"], "version": post["id"],
                            "conversation": source["conversation"], "author": post["attributed_to"],
                            "at": post["recorded_at"], "via": "home"})
                rows.append({**template, "source": source, "key": schema.source_key(source),
                    "status": "ok" if results else "unavailable", "results": results,
                    "reason": None if results else "reading a file source is not in this build"})
            art["page"]["sources"] = rows
            data = json.dumps(art).encode()
            define_from(w, data)
            preflight = ask_preflight(w, asked_body(w, op="authentic-pre-change"))
            assert preflight["state"] == "ready", preflight
            answer = ask_commit(w, data)
            assert answer["state"] == "committed", answer
            receipt = {"baseline": commit, "preflight": preflight, "commit": answer,
                       "acts": w.corpus.operational(act="magnet-extracted")}
            (destination / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        finally:
            w.stop()
            w.corpus.close()
        shutil.make_archive(str(destination / "brain-12fecc01"), "zip", root)
    print("Created baseline Brain and real preflight/commit receipt")


if __name__ == "__main__":
    main()
