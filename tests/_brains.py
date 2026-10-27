"""Tests create their Brains explicitly (D2 applies to tests too).

Opening a Brain never creates one and never changes its schema
(`mentis.spine.migrations`). A test that wants a fresh Brain says so, here, at
the point it makes one; a test that reopens a Brain it already made opens it.
"""

from __future__ import annotations

import os


def new_brain(path) -> str:
    """Create an empty Brain at `path` and return the path as a string.

    The Brain is created through the migration runner, exactly as
    `mentis.api.create_corpus` creates the owner's, and closed again so the
    caller opens it however the test needs (`api.open_corpus`, `_State`,
    `Surface`, a server process)."""
    import mentis.api as api
    path = os.fspath(path)
    api.create_corpus(path).close()
    return path
