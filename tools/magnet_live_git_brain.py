"""A LIVE Brain for the collection-scoped file source: a real upstream repository, by address.

Not part of any suite and reached by nothing that runs by itself. It is how the live half of Part C's
done-when is checked by hand, on a Brain built outside the repository:

    python -m tools.magnet_live_git_brain C:\\tmp\\partc-live\\brain
    MENTIS_LIVE_GIT_BRAIN=C:\\tmp\\partc-live\\brain cargo test -p mentis-ops \\
        --test magnet_collection_source -- --ignored --nocapture

It declares a `git` collection bound by ADDRESS (so Git fetches it into Mentis's own bare mirror
using this machine's existing credentials, as `mentis.sources.git` describes), sweeps a bounded
window of recent commits and a bounded scope of paths, declares a filesystem collection holding this
repository's own `AGENTS.md`, and writes the Magnet definition whose two sources are exactly those --
the whole git collection, and that one exact held file.
"""
import json
import pathlib
import sys

from mentis.sources import _admission
from mentis.sources.registry import Sources
from mentis.spine import held
from mentis.web import fixture, _State

UPSTREAM = "https://github.com/zed-industries/agent-client-protocol.git"
GIT_COLLECTION = "col-acp-upstream"
HELD_COLLECTION = "col-mentis-agents"
#: Bounded on purpose: a window of recent commits and a narrow path scope, not a whole repository.
COMMITS = 20
INCLUDE = ["*.md", "schema"]
ACTIVATION = pathlib.Path(__file__).resolve().parents[1] / "tests/fixtures/magnet-conformance/activation"
AGENTS = pathlib.Path(__file__).resolve().parents[1] / "AGENTS.md"


def build(root):
    root = pathlib.Path(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    fixture.build(str(root))
    st = _State(str(root))
    corpus, cv = st.corpus, st.cv
    actor = corpus.entries_of_kind("participant")[0]["id"]
    sources = Sources(corpus, cv)

    out = sources.declare(GIT_COLLECTION, connector="git", include=INCLUDE, exclude=[],
                          declarer="human", written_by="live-check",
                          options={"ref": "main", "commits": COMMITS})
    collection = out["collection"] if isinstance(out, dict) else GIT_COLLECTION
    sources.bind(collection, None, written_by="live-check", remote=UPSTREAM)
    plan = sources.plan(collection)
    print(f"planned {len(plan.get('admit') or [])} objects from {UPSTREAM}")
    swept = sources.sweep(collection, plan["plan"], actor="human", written_by="live-check")
    print(f"swept {len(swept.get('admitted') or [])} objects into {collection}")

    # The held AGENTS.md of this repository, admitted exactly as the folder connector admits one.
    cv.record_act(actor=actor, act="source-collection-declared", about=[HELD_COLLECTION],
                  detail={"collection": HELD_COLLECTION, "name": "Mentis own files",
                          "connector": "filesystem"})
    data = AGENTS.read_bytes()
    digest, _ = held.put(root, data)
    corpus.admit(**_admission(
        source=f"filesystem:{HELD_COLLECTION}", collection=HELD_COLLECTION, connector="filesystem",
        obs={"object": "AGENTS.md", "state": "present", "retention": "held", "digest": digest,
             "size": len(data), "payload_type": "text/markdown", "encoding": {"text": True},
             "relations": []},
        action="new", tok="live", batch="live", scope={}, observed_at=1700000000.0),
        attributed_to=actor, written_by="live-check")

    template = json.loads((ACTIVATION / "artifacts/complete.bin").read_bytes())["definition"]["value"]
    value = json.loads(json.dumps(template))
    # THREE SOURCES, which is how a real Magnet names a repository: the COMMITS by their prefix
    # (`.git/commits/`, where the git connector keeps them), the collection WHOLE -- which is
    # bounded, and says so, because a repository holds far more objects than one batch may carry --
    # and the one exact held file this repository's own boundary is written in.
    value["sources"] = [{"kind": "file", "collection": collection, "path": ".git/commits/"},
                        {"kind": "file", "collection": collection},
                        {"kind": "file", "collection": HELD_COLLECTION, "path": "AGENTS.md"}]
    value["selection"] = {"informationTypes": ["post"]}
    (root / "live-definition.json").write_text(json.dumps(value), encoding="utf-8")
    corpus.close()
    print(f"live Brain at {root}")


if __name__ == "__main__":
    build(sys.argv[1])
