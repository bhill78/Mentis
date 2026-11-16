"""Record summaries: one human-readable sentence per Brain record, for lists.
Kept BESIDE the record, never in it (`<corpus>/presentation/record-summaries.json`).

WHY (owner, 2026-11-16). A list of Brain records showed each record's own
words, cut off. A rule of 1,600 characters and an outcome that opens with a
commit hash do not say what they are in their first eighty characters, so the
lists could not be scanned.

WHAT A SUMMARY IS. Presentation metadata: one sentence saying what the record
means or requires, shown as a list row's words. It is NOT an Entry, not
knowledge, not governance and not a source of authority:

  * nothing that forms context, retrieves, delivers or governs reads this
    file -- only the Ladder's list and item reads do, to draw a row;
  * the record's own wording is untouched, and is what a record's own view
    shows and what agents are given;
  * a summary changes no standing: a hypothesis summarised stays a hypothesis.

So it lives where the canvas's looks live (`mentis/presentation.py`), for the
same reason: an Entry ESTABLISHES, and a paraphrase must not become something
retrieval returns.

WHERE ONE COMES FROM, said with it (`source`):

  written     somebody wrote or corrected it by hand (the owner). It is never
              overwritten by a generated one.
  generated   a model wrote it, once, in a bounded batch somebody ran
              (`tools/brain_summaries.py`); `by` names who ran it, `model`
              what wrote it. It is kept, not re-made each time a list loads.
  derived     NOT STORED: computed from the record's own first sentence when
              nothing is kept (`derive`). Never invents: it is the record's
              own words, shortened.

BOUND TO THE WORDS IT SUMMARISES. `of` is the sha256 of the record's words
when the summary was made. Entries are never rewritten, so it should always
match; if it ever does not, the summary is not shown (the derived one is),
rather than describing words it was not written for.

A MISSING OR UNREADABLE FILE IS NO SUMMARIES, NEVER AN ERROR.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import tempfile
import threading
import time

DIR = "presentation"
FILE = "record-summaries.json"
VERSION = 1

#: one sentence a row can show whole
MAX_LEN = 200
#: a bound on one batch, and on how many corrections of one record are kept
MAX_BATCH = 500
KEEP_EARLIER = 5
SOURCES = ("written", "generated")

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class Refused(ValueError):
    """A summary that cannot be kept, said in words for whoever sent it."""


def _lock(root: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(os.path.abspath(root), threading.Lock())


def _path(root: str) -> pathlib.Path:
    return pathlib.Path(root) / DIR / FILE


def words_digest(words: str) -> str:
    return hashlib.sha256((words or "").encode("utf-8")).hexdigest()


def read(root: str) -> dict:
    """Every kept summary, `{entry id: row}`. Never raises: no file, or one
    that cannot be read, is no summaries."""
    try:
        data = json.loads(_path(root).read_text("utf-8"))
        rows = data.get("summaries") if isinstance(data, dict) else None
        return rows if isinstance(rows, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(root: str, rows: dict):
    """All or nothing: a temporary file, then a rename over the old one."""
    d = _path(root).parent
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".incoming-", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"version": VERSION, "summaries": rows}, f, ensure_ascii=False,
                      indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, d / FILE)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def check(summary) -> str:
    """The summary as it is kept: one line, trimmed, at most `MAX_LEN`."""
    if not isinstance(summary, str):
        raise Refused("a summary is a sentence of text")
    said = " ".join(summary.split())
    if not said:
        raise Refused("a summary needs words")
    if len(said) > MAX_LEN:
        raise Refused(f"a summary is one sentence of at most {MAX_LEN} characters "
                      f"(this is {len(said)})")
    return said


def kept_for(rows: dict, entry: str, words: str) -> dict | None:
    """The kept summary of this record, if it was written for these words."""
    row = rows.get(entry)
    if not isinstance(row, dict) or not isinstance(row.get("summary"), str):
        return None
    # BOUND OR NOT SHOWN: a row that does not say which words it was written
    # for (no `of`, or a malformed one) is bound to nothing, and is treated as
    # no kept summary -- never shown on trust.
    if row.get("of") != words_digest(words):
        return None
    return row


_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9@#])")


def derive(words: str, *, name: str | None = None, limit: int = 140) -> str:
    """The record's own first sentence, shortened at a word: what a row shows
    when no summary is kept. Nothing is added and nothing reworded. A Kind
    that names its records (a Persona, a Workflow) leads with the name."""
    text = " ".join((words or "").split())
    lead = " ".join((name or "").split())
    if lead and text.lower().startswith(lead.lower()):
        lead = ""
    first = _SENTENCE_END.split(text, maxsplit=1)[0] if text else ""
    # a first "sentence" of a few characters ("Met.") says nothing alone
    if 0 < len(first) < 24 and len(text) > len(first):
        rest = _SENTENCE_END.split(text[len(first):].lstrip(), maxsplit=1)[0]
        first = f"{first} {rest}".strip()
    said = f"{lead}: {first}" if lead and first else (lead or first)
    if len(said) <= limit:
        return said
    cut = said[:limit].rsplit(" ", 1)[0].rstrip(",;:—-")
    return (cut or said[:limit]) + "…"


def put(root: str, entry: str, summary, *, words: str, source: str, by: str,
        model: str | None = None, at: float | None = None) -> dict:
    """Keep one summary. A written one replaces anything; a generated one
    never replaces a written one (`Refused`). What it replaces is kept beside
    it (`earlier`, newest first, at most `KEEP_EARLIER`), so a correction can
    be seen and undone."""
    if source not in SOURCES:
        raise Refused("a summary is `written` or `generated`")
    said = check(summary)
    with _lock(root):
        rows = dict(read(root))
        was = rows.get(entry) if isinstance(rows.get(entry), dict) else None
        if was and was.get("source") == "written" and source == "generated":
            raise Refused("this record has a summary somebody wrote; a generated "
                          "one does not replace it")
        row = {"summary": said, "source": source, "by": by,
               "at": time.time() if at is None else at, "of": words_digest(words)}
        if model:
            row["model"] = str(model)[:120]
        if was:
            earlier = [{k: was[k] for k in ("summary", "source", "by", "at", "model") if k in was},
                       *(was.get("earlier") or [])]
            row["earlier"] = earlier[:KEEP_EARLIER]
        rows[entry] = row
        _write(root, rows)
        return row


def remove(root: str, entry: str) -> bool:
    """Forget the kept summary of one record: its row shows the derived one."""
    with _lock(root):
        rows = dict(read(root))
        if entry not in rows:
            return False
        del rows[entry]
        _write(root, rows)
        return True
