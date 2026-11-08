"""Seed the existing Quiet fixtures for a browser comparison; never opens a live Brain.

Run from the repository root with `python -m tools.preview_quiet_floating_nav`.
The printed URLs use the server's built dist, not a shared development server.
No browser is started. The SAME fixture shape Track A seeds (same sources,
same generated layout), so the two previews are comparable; fixture IDs are
generated, so seeding a second time creates different IDs than Track A's own
seeded Brain -- open each track's own Brain, not the other's.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from mentis import artifacts
from mentis.conversation import text
from mentis.web import fixture
from tests.test_quiet_layout_correction_browser import reading
from tests.test_quiet_media_browser import PNG, hold
from tests.test_quiet_r4_margin_browser import carried


def seed(root: Path, base: str) -> dict:
    # A fresh directory is mandatory: reruns must never append duplicate demo
    # conversations to any existing Brain, even one with a misleading name.
    if root.exists():
        raise FileExistsError(f"{root} already exists; reuse its manifest or choose a fresh --root")
    built = fixture.build(str(root))
    world = {**built, "state": SimpleNamespace(corpus=built["corpus"])}
    try:
        # Reuse the fixture bodies without asking pytest to run browser tests.
        long_id = reading.__wrapped__(world)
        mixed = carried.__wrapped__(world)
        cid = mixed["conversation"]
        topic = world["cv"].open_topic(cid, "Reading", about="Mixed working material")
        world["cv"].assign_topic(mixed["blocks"], topic)
        image = hold(world, PNG, "cat.png", "image/png", cid)
        image_post = world["cv"].say(cid, world["who"]["@brian"], [
            text("An image from the existing Quiet media fixture."),
            artifacts.part(image, corpus=world["corpus"]),
        ])
        manifest = {
            "viewport": {"width": 1440, "height": 1000},
            "brain": str(root.resolve()),
            "long": {"name": "Quiet layout correction", "conversation": long_id,
                     "url": f"{base}/quiet#/c/{long_id}",
                     "source": "tests/test_quiet_layout_correction_browser.py::reading"},
            "mixed": {"name": "Quiet carried", **mixed, "image_post": image_post,
                      "url": f"{base}/quiet#/c/{cid}",
                      "source": "tests/test_quiet_r4_margin_browser.py::carried",
                      "image_source": "tests/test_quiet_media_browser.py::PNG"},
        }
        (root.parent / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest
    finally:
        world["corpus"].close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("scratch/quiet-floating-nav/brain"))
    parser.add_argument("--base", default="http://127.0.0.1:19872")
    args = parser.parse_args()
    print(json.dumps(seed(args.root, args.base.rstrip("/")), indent=2))


if __name__ == "__main__":
    main()
