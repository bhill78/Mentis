"""The user's portable corpus.

The user points Mentis at a directory. Mentis operates there. Nothing is copied
into a hidden application directory.

The storage technology is deliberately unremarkable -- a marker file and JSON
lines -- because the boundary is what matters at this stage and picking a
database now would decide something evidence has not settled.

The invariant this module exists to protect:

    A corpus records OBSERVATIONS about machines. It never records machine state
    as current truth.

So a live instance is written with a `machine_id`, and reading the corpus on a
different machine yields history with an empty live set. That is checked in
tests/test_corpus_portability.py, which moves a corpus to a new path under a new
machine id and fails if any handle comes back live.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict
from typing import Any, Iterator

from mentis.api.errors import CorpusInvalid, CorpusNotAttached

MARKER = "mentis-corpus.json"

#: THE ONLY TWO ROLES, and the distinction is a boundary rather than a
#: feature: fixtures, demo activity and stress material refuse to run
#: against DAY_TO_DAY, so the real Brain cannot be seeded by something that
#: was pointed at it by mistake.
DAY_TO_DAY = "day-to-day"
DEVELOPMENT = "development"
CORPUS_VERSION = 1


def machine_id() -> str:
    """Identity of THIS machine. Never durable corpus meaning, only attribution."""
    import platform

    return f"{platform.node()}"


class Corpus:
    """An attached corpus directory.

    `path` is location, not identity. The corpus's own id lives in the marker
    file and travels with it, so moving the directory changes nothing durable.
    """

    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(path)
        self._marker = os.path.join(self.path, MARKER)

    # -- attachment ---------------------------------------------------------

    @property
    def is_corpus(self) -> bool:
        return os.path.isfile(self._marker)

    def create(self, name: str | None = None, *,
               role: str = DEVELOPMENT) -> dict:
        os.makedirs(self.path, exist_ok=True)
        if self.is_corpus:
            return self.identity()
        doc = {
            "corpus_version": CORPUS_VERSION,
            "corpus_id": str(uuid.uuid4()),
            "name": name or os.path.basename(self.path) or "mentis",
            "created_at": time.time(),
            # WHAT THIS CORPUS IS FOR, and it defaults to the safe
            # answer. Only a corpus deliberately created as
            # DAY_TO_DAY is the owner's real Brain; everything else
            # -- a test directory, a demo, a stress corpus, anything
            # attached by accident -- is development. Absent means
            # development too, so nothing becomes real by omission.
            "role": role,
            # Deliberately absent: the path it was created at, the machine that
            # created it, and anything else that would make a move meaningful.
        }
        with open(self._marker, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        return doc

    @property
    def role(self) -> str:
        """What this corpus is for. Unmarked corpora are development."""
        # Read raw, NOT through `identity()`: a marker from a newer Mentis is
        # refused there, and a refused day-to-day Brain must still read as
        # day-to-day to every guard that asks.
        try:
            with open(self._marker, encoding="utf-8") as fh:
                return json.load(fh).get("role") or DEVELOPMENT
        except (OSError, ValueError, AttributeError):
            return DEVELOPMENT

    def identity(self) -> dict:
        if not self.is_corpus:
            raise CorpusInvalid(f"{self.path} is not a Mentis corpus")
        with open(self._marker, encoding="utf-8") as fh:
            doc = json.load(fh)
        # THIS STORE'S OWN SCHEMA AUTHORITY: guarded code refuses a marker
        # from a newer Mentis rather than reading a layout it does not know.
        # It has no migrations; changes to it must be additive.
        v = doc.get("corpus_version", CORPUS_VERSION)
        if isinstance(v, int) and v > CORPUS_VERSION:
            raise CorpusInvalid(
                f"{self.path} is corpus_version {v}; this Mentis knows "
                f"{CORPUS_VERSION}. It needs a newer Mentis")
        return doc

    # -- records ------------------------------------------------------------

    def _records_path(self, kind: str) -> str:
        return os.path.join(self.path, f"{kind}.jsonl")

    def append(self, kind: str, record: dict) -> None:
        if not self.is_corpus:
            raise CorpusInvalid(f"{self.path} is not a Mentis corpus")
        with open(self._records_path(kind), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

    def read(self, kind: str) -> Iterator[dict]:
        p = self._records_path(kind)
        if not os.path.exists(p):
            return iter(())
        def _gen() -> Iterator[dict]:
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
        return _gen()

    # -- the portability rule ----------------------------------------------

    def record_instance(self, instance: Any) -> None:
        """Write an instance as an OBSERVATION, stamped with the machine.

        `pid`, `workspace` and `session_ref` go in because they are useful
        history. They are meaningless on another machine, and `live_instances`
        below is what keeps them from being read as current truth.
        """
        rec = asdict(instance) if hasattr(instance, "__dataclass_fields__") else dict(instance)
        rec["_kind"] = "instance_observation"
        rec["_observed_on"] = machine_id()
        rec["_observed_at"] = time.time()
        self.append("instances", rec)

    def instance_history(self) -> list[dict]:
        """Everything ever recorded, from any machine. All of it historical."""
        return list(self.read("instances"))

    def live_candidates(self, this_machine: str) -> list[dict]:
        """Records that MIGHT still be live -- only ones from this machine.

        This is the whole portability guarantee in one method. A record observed
        elsewhere can never be a live candidate here, so attaching a corpus on a
        new machine cannot resurrect a handle. Even for this machine these are
        only *candidates*: Foundation still checks the OS before calling one live.
        """
        latest: dict[str, dict] = {}
        for rec in self.read("instances"):
            if rec.get("_observed_on") != this_machine:
                continue
            latest[rec.get("instance_id", "")] = rec
        return [r for r in latest.values() if r.get("liveness") in ("alive", "starting")]

    def resumable_candidates(self, this_machine: str) -> list[dict]:
        """Records that name a runtime session, from THIS machine only.

        NOT live candidates. These are instances whose invocation ENDED,
        which is exactly the case `live_candidates` excludes and exactly
        the case a resumable session is in. Whether the session still
        exists is not decided here and cannot be: this says which
        references are worth asking a runtime about.

        The machine rule is the same one and for the same reason -- a
        record observed elsewhere is never a candidate here.
        """
        latest: dict[str, dict] = {}
        for rec in self.read("instances"):
            if rec.get("_observed_on") != this_machine:
                continue
            latest[rec.get("instance_id", "")] = rec
        return [r for r in latest.values()
                if r.get("session_ref")
                and r.get("liveness") not in ("gone",)]

    def record_capacity(self, reading: Any) -> None:
        rec = asdict(reading) if hasattr(reading, "__dataclass_fields__") else dict(reading)
        rec["_kind"] = "capacity_observation"
        rec["_observed_on"] = machine_id()
        self.append("capacity", rec)


def require(corpus: Corpus | None) -> Corpus:
    if corpus is None:
        raise CorpusNotAttached(
            "no corpus attached; point Mentis at a directory with `mentis attach <dir>`"
        )
    return corpus


def role_at(path: str) -> str:
    """The role of the corpus at a path, without attaching to it.

    Answers DEVELOPMENT for a path that is not a corpus at all, which is what
    lets a guard be written as `refuse if day-to-day` rather than as a list of
    everything that is allowed.
    """
    return Corpus(path).role
