"""Who owns this Brain, read from the participant rows and nothing else.

Moved verbatim from `mentis.wakecheck`, which no longer exists: every reader
of it wanted only this, and it reads participant rows only.
"""

from __future__ import annotations


def _owner(cv) -> str | None:
    """This Brain's owner Participant, identified as the baseline identifies
    them; None where the record names none."""
    from mentis.bootstrap.baseline import OWNER_ABOUT
    # THE ROWS OF THE KIND, NOT `all_participants`: a rename's version is a
    # row of the Kind carrying the same `about`, but it is written after the
    # Participant it renames, so the first row that says so is the owner
    # itself -- the answer `all_participants` gives, without asking which rows
    # are versions on every read that wants only the owner (opr-15cd9eb266f9).
    owners = [p["id"] for p in cv.corpus.entries_of_kind("participant")
              if (p.get("body") or {}).get("about") == OWNER_ABOUT]
    return owners[0] if owners else None
