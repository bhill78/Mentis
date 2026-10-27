"""Scratch: a Brain's recoverable, TEMPORARY conversational working state.

Approved by the owner in "Mentis UI/UX" (proposal adm-4bca90212dc3, authorised
2026-10-03). Not to be confused with `mentis.foundation.scratch`, which is an
execution's private working DIRECTORY and has nothing to do with this.

TEMPORARY DESCRIBES STATUS AND LIFECYCLE, NOT WHETHER THE BYTES SURVIVE. A
Scratch lives in this Brain's own `corpus.db`, so it survives a refresh, a
closed tab, a restart, another machine using the same Brain, and a normal Brain
snapshot -- and it is still not Brain material:

  * it is not an Entry and not a Kind, has no standing, and is not in the hash
    chain (`Store.CHAINED` names the three chained tables and these are not
    among them);
  * its tables carry no append-only triggers, because Dismiss and expiry must
    DELETE it -- an Entry can never be deleted, which is exactly why it is not
    one;
  * nothing that reads the record reads these tables. `find`, `compose`,
    `orientation`, governance and every worker tool query `entry` and
    `operational` by name; this module is the only code that names `scratch`,
    `scratch_message` or `scratch_setting`, and it is reached only by the
    `/api/scratch` routes, on which `_api` refuses a worker grant.

WHAT CROSSES INTO THE RECORD crosses only by the owner's explicit act (Sidebar,
or Keep as Conversation), through the record's normal paths,
carrying the content it needs -- never a reference back to a row here, because
these rows can be deleted at any moment.

THE THREE TABLES, and why each field is needed, are argued in the proposal.
Briefly: `scratch` is one session (its address, who asked, the references it
was asked from, and the retention clock); `scratch_message` is one thing said
(order, who, the content parts in the same shape a Turn takes, when, whether an
answer is still coming, and what actually answered); `scratch_setting` is the
Brain's one retention choice. Nothing here copies a Turn, a Conversation or a
briefing: `context` holds references.
"""

from __future__ import annotations

import json
import time
import uuid

#: The retention choices offered, in days. `None` is Never.
RETENTION_CHOICES = (1, 7, 30, 90, None)
DEFAULT_RETAIN_DAYS = 7
DAY_S = 24 * 60 * 60

STATUSES = ("pending", "done", "failed", "interrupted")

#: THE TABLES ARE DEFINED BY MIGRATION 0001-adopt (`mentis.spine.migrations`),
#: the one place a Brain's schema is declared.

#: Exactly the tables this module owns. Tests name them from here.
TABLES = ("scratch", "scratch_message", "scratch_setting")


class ScratchRefused(ValueError):
    """Said in words; the route turns it into an error the owner reads."""


class ScratchGone(LookupError):
    """No such Scratch -- dismissed, kept, expired, or never here."""


def _now() -> float:
    return time.time()


def _loads(s, default=None):
    if s is None:
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


def _text_of(parts) -> str:
    return "".join(p.get("text", "") for p in parts or ()
                   if isinstance(p, dict) and p.get("type") == "text")


class ScratchStore:
    """The Scratch tables in ONE Brain's database, on that Brain's connection.

    It uses the spine's own connection and lock, so a Scratch write and a
    record write can share one transaction -- which is what lets Keep write
    the Conversation and delete the Scratch all-or-nothing.
    """

    def __init__(self, corpus, *, now=_now):
        self._corpus = corpus
        self._store = corpus._store
        self._now = now
        with self._store._lock:
            conn = self._store._conn
            # Overwrite deleted Scratch cells in the current database. Earlier
            # snapshots remain independent copies, as with every Brain snapshot.
            conn.execute("PRAGMA secure_delete = ON")
        # NO DDL HERE ANY MORE (D2): the three tables and the retention
        # default are made by migration 0001-adopt, with the rest of the
        # schema, and opening a Brain never creates anything.

    # -- plumbing ------------------------------------------------------------

    def _q(self, sql, args=()):
        # the spine's read path: committed state on a pooled connection, or
        # this thread's own open transaction when it is inside one
        return self._store._rows(sql, args)

    def write(self):
        """The Brain's own transaction. Nested use joins the outer one."""
        return self._store.write()

    def _x(self, sql, args=()):
        return self._store._conn.execute(sql, args)

    # -- the retention setting -------------------------------------------------

    def retain_days(self) -> int | None:
        row = self._q("SELECT retain_days FROM scratch_setting WHERE one = 1")
        return row[0][0] if row else DEFAULT_RETAIN_DAYS

    def _cutoff(self, days) -> float | None:
        return None if days is None else self._now() - days * DAY_S

    def would_expire(self, days) -> int:
        """How many Scratches a change to `days` would delete at once."""
        cut = self._cutoff(days)
        if cut is None:
            return 0
        return self._q("SELECT COUNT(*) FROM scratch WHERE touched_at < ?",
                       (cut,))[0][0]

    def set_retain_days(self, days, *, confirm_deleting=None) -> dict:
        """Change the retention. Shortening it so that Scratches expire now is
        refused unless the caller says how many it was told would go -- so the
        owner is never surprised by a deletion the interface did not show."""
        if days not in RETENTION_CHOICES:
            raise ScratchRefused(
                f"retention is one of 1, 7, 30, 90 days or never, not {days!r}")
        going = self.would_expire(days)
        if going and confirm_deleting != going:
            return {"applied": False, "would_delete": going,
                    "why": f"{going} Scratch{'es' if going != 1 else ''} "
                           f"would be deleted now; confirm to apply"}
        with self.write():
            self._x("UPDATE scratch_setting SET retain_days = ? WHERE one = 1",
                    (days,))
        swept = self.sweep()
        return {"applied": True, "retain_days": days, "deleted": swept}

    # -- expiry ------------------------------------------------------------------

    def sweep(self) -> int:
        """Delete every Scratch whose last activity is older than retention.

        Not a scheduler: called when the server starts, when the list is read
        and when a Scratch is opened. Expiry DELETES. It archives nothing,
        establishes nothing and promotes nothing.
        """
        cut = self._cutoff(self.retain_days())
        if cut is None:
            return 0
        with self.write():
            return self._x("DELETE FROM scratch WHERE touched_at < ?",
                           (cut,)).rowcount

    def interrupt_orphans(self, live=()) -> int:
        """A `pending` answer no run in THIS process is producing will never
        arrive: Mentis restarted under it. Say so. Nothing is re-sent."""
        live = set(live)
        rows = self._q("SELECT scratch, n FROM scratch_message "
                       "WHERE status = 'pending'")
        gone = [(s, n) for s, n in rows if (s, n) not in live]
        if not gone:
            return 0
        now = self._now()
        with self.write():
            for s, n in gone:
                self._x("UPDATE scratch_message SET status = 'interrupted', "
                        "provenance = ? WHERE scratch = ? AND n = ? "
                        "AND status = 'pending'",
                        (json.dumps({"interrupted": "Mentis stopped before "
                                     "this answer arrived; nothing was "
                                     "re-sent", "at": now}), s, n))
                self._x("UPDATE scratch SET touched_at = ? WHERE id = ?",
                        (now, s))
        return len(gone)

    # -- sessions ------------------------------------------------------------------

    def create(self, *, owner, context) -> str:
        if not owner:
            raise ScratchRefused("a Scratch belongs to somebody; no owner given")
        sid = f"scr-{uuid.uuid4().hex[:12]}"
        now = self._now()
        with self.write():
            self._x("INSERT INTO scratch (id, owner, context, created_at, "
                    "touched_at) VALUES (?, ?, ?, ?, ?)",
                    (sid, owner, json.dumps(context or {}), now, now))
        return sid

    def _row(self, sid):
        got = self._q("SELECT id, owner, context, created_at, touched_at "
                      "FROM scratch WHERE id = ?", (sid,))
        if not got:
            raise ScratchGone(f"no Scratch {sid!r}: dismissed, kept, expired, "
                              f"or never in this Brain")
        r = got[0]
        return {"id": r[0], "owner": r[1], "context": _loads(r[2], {}),
                "created_at": r[3], "touched_at": r[4]}

    def messages(self, sid) -> list[dict]:
        rows = self._q("SELECT n, role, parts, at, status, provenance "
                       "FROM scratch_message WHERE scratch = ? ORDER BY n",
                       (sid,))
        return [{"n": r[0], "role": r[1], "parts": _loads(r[2], []),
                 "at": r[3], "status": r[4],
                 "provenance": _loads(r[5])} for r in rows]

    def get(self, sid) -> dict:
        self.sweep()
        out = self._row(sid)
        out["messages"] = self.messages(sid)
        out["expires_at"] = self._expires(out["touched_at"])
        return out

    def _expires(self, touched):
        days = self.retain_days()
        return None if days is None else touched + days * DAY_S

    def recent(self, *, owner=None, limit=20) -> list[dict]:
        self.sweep()
        where, args = ("WHERE s.owner = ?", (owner,)) if owner else ("", ())
        rows = self._q(
            "SELECT s.id, s.created_at, s.touched_at, s.context, "
            "  (SELECT COUNT(*) FROM scratch_message m WHERE m.scratch = s.id),"
            "  (SELECT parts FROM scratch_message m WHERE m.scratch = s.id "
            "     AND m.role = 'owner' ORDER BY n LIMIT 1),"
            "  (SELECT COUNT(*) FROM scratch_message m WHERE m.scratch = s.id "
            "     AND m.status = 'pending') "
            f"FROM scratch s {where} ORDER BY s.touched_at DESC LIMIT ?",
            (*args, limit))
        out = []
        for r in rows:
            ctx = _loads(r[3], {})
            first = _text_of(_loads(r[5], [])).strip()
            out.append({"id": r[0], "created_at": r[1], "touched_at": r[2],
                        "messages": r[4], "pending": bool(r[6]),
                        "first": first[:140],
                        "from": ctx.get("label"),
                        "expires_at": self._expires(r[2])})
        return out

    def usage(self) -> dict:
        """What Scratch costs this Brain's database, in the bytes it holds."""
        n, m, size = self._q(
            "SELECT (SELECT COUNT(*) FROM scratch),"
            " (SELECT COUNT(*) FROM scratch_message),"
            " (SELECT COALESCE(SUM(LENGTH(context)), 0) FROM scratch) +"
            " (SELECT COALESCE(SUM(LENGTH(parts) + COALESCE(LENGTH(provenance),"
            "  0)), 0) FROM scratch_message)")[0]
        return {"scratches": n, "messages": m, "bytes": size}

    def advance(self) -> tuple:
        """Something to COMPARE, for `/api/pulse`: counts and the latest
        activity. Every mutation here moves `touched_at` or a count."""
        return tuple(self._q(
            "SELECT (SELECT COUNT(*) FROM scratch),"
            " (SELECT COUNT(*) FROM scratch_message),"
            " (SELECT COALESCE(MAX(touched_at), 0) FROM scratch)")[0])

    # -- saying things -----------------------------------------------------------

    def ask(self, sid, parts, *, execution=None, access=None, refs=None) -> int:
        """The owner's message and a `pending` answer, in one transaction.

        ONE ANSWER AT A TIME. A second question while one is coming is refused
        rather than queued: a queue would be the start of a workflow engine,
        and two devices asking at once would otherwise interleave answers.
        Returns the pending answer's `n`.

        `access` is the folders the owner SELECTED for this question, kept
        beside its execution choice. Each question records exactly the
        folders it was sent with, and its answer -- and Ask again -- uses
        those and no others: nothing here adds a folder or widens one from
        an earlier question. Within one Scratch the interface pre-fills the
        last question's folders as visible, removable chips (owner rule,
        2026-10-10: continuity of the owner's selection, not a new or
        broader authorisation); a new Scratch starts with none.

        `refs` is the same selection as PathRefs (`mentis.web.scratch_paths`):
        each file or folder, to read or to write. `access` stays beside it as
        the folders the runtime is given, for what already reads that.
        """
        if not isinstance(parts, list) or not _text_of(parts).strip():
            raise ScratchRefused("a question needs words")
        now = self._now()
        with self.write():
            self._row(sid)
            if self._q("SELECT 1 FROM scratch_message WHERE scratch = ? AND "
                       "status = 'pending'", (sid,)):
                raise ScratchRefused("Mentis is still answering this Scratch; "
                                     "wait for it, or ask in a new Scratch")
            top = self._q("SELECT COALESCE(MAX(n), 0) FROM scratch_message "
                          "WHERE scratch = ?", (sid,))[0][0]
            self._x("INSERT INTO scratch_message (scratch, n, role, parts, at, "
                    "status, provenance) VALUES (?, ?, 'owner', ?, ?, 'done', ?)",
                    (sid, top + 1, json.dumps(parts), now,
                     json.dumps({"execution": execution or {},
                                 **({"access": list(access)} if access
                                    else {}),
                                 **({"refs": list(refs)} if refs
                                    else {})})))
            self._x("INSERT INTO scratch_message (scratch, n, role, parts, at, "
                    "status) VALUES (?, ?, 'mentis', '[]', ?, 'pending')",
                    (sid, top + 2, now))
            self._x("UPDATE scratch SET touched_at = ? WHERE id = ?", (now, sid))
        return top + 2

    def pending_provenance(self, sid, n, provenance):
        """Tell the owner how a pending answer is being carried."""
        with self.write():
            return bool(self._x(
                "UPDATE scratch_message SET provenance = ? WHERE scratch = ? "
                "AND n = ? AND status = 'pending'",
                (json.dumps(provenance), sid, n)).rowcount)

    def settle(self, sid, n, *, status, parts=None, provenance=None) -> bool:
        """The answer arrived, or failed. Only a PENDING answer is settled: an
        answer that was already interrupted, or whose Scratch was dismissed or
        kept meanwhile, stays as it is and the late result is dropped."""
        if status not in ("done", "failed"):
            raise ScratchRefused(f"an answer settles as done or failed, "
                                 f"not {status!r}")
        now = self._now()
        with self.write():
            cur = self._x("UPDATE scratch_message SET status = ?, parts = ?, "
                          "at = ?, provenance = ? WHERE scratch = ? AND n = ? "
                          "AND status = 'pending'",
                          (status, json.dumps(parts or []), now,
                           json.dumps(provenance) if provenance else None,
                           sid, n))
            if cur.rowcount:
                self._x("UPDATE scratch SET touched_at = ? WHERE id = ?",
                        (now, sid))
        return bool(cur.rowcount)

    def touch(self, sid):
        with self.write():
            self._x("UPDATE scratch SET touched_at = ? WHERE id = ?",
                    (self._now(), sid))

    # -- ending ----------------------------------------------------------------

    def dismiss(self, sid) -> bool:
        """Delete it now. Its messages go with it (ON DELETE CASCADE)."""
        with self.write():
            return bool(self._x("DELETE FROM scratch WHERE id = ?",
                                (sid,)).rowcount)

    def pending(self, sid) -> list[int]:
        return [r[0] for r in self._q(
            "SELECT n FROM scratch_message WHERE scratch = ? AND "
            "status = 'pending'", (sid,))]
