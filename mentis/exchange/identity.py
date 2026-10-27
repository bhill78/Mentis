"""Which Brain this is: {corpus_id, fork_id}. READ ONLY. SHARED CONTRACT.

A copy of a Brain keeps the original's `corpus_id` (the `corpus` row is
immutable by trigger), so `corpus_id` names the shared LINEAGE and cannot say
which machine an export came from. The fork identity does (O1): when a copy
is adopted the owner writes one `brain-forked` act, detail
{"fork_id": <uuid4 hex>, "heads": <migrations._heads output>}. That write is
the receiving side's (slice 2); this module only reads it.

A Brain's fork id is the `fork_id` of its NEWEST `brain-forked` act, or else
its `corpus_id` -- the original Brain, never forked, is its own fork.
"""

from __future__ import annotations

import json

from ._rows import Reader, one_read, store_of

BRAIN_FORKED = "brain-forked"


def identity_from(reader: Reader) -> dict:
    corpus_id = reader.corpus_id()
    fork_id = None
    for row in reversed(reader.acts("act = ?", (BRAIN_FORKED,))):
        try:
            detail = json.loads(row["detail"] or "{}")
        except ValueError:
            continue
        if isinstance(detail, dict) and isinstance(detail.get("fork_id"), str) \
                and detail["fork_id"]:
            fork_id = detail["fork_id"]
            break
    return {"corpus_id": corpus_id, "fork_id": fork_id or corpus_id}


def identity(store) -> dict:
    """{corpus_id, fork_id} of the Brain behind a Store or a Corpus."""
    with one_read(store_of(store)) as r:
        return identity_from(r)
