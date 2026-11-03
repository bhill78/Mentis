"""What a dispatched worker, or a session started by hand, is authorised to ask.

Foundation's grant table, moved here unchanged in behaviour when Foundation was
removed (agent execution is now MARS, `mentis.execution`). `/api/worker`,
`/api/worker/session` and `mentis.worker.permitted` read it exactly as they
read Foundation's: a grant is an opaque token naming one execution, one corpus
and why the execution was dispatched, and holding it is the whole claim.

Live, this process, never durable. An execution is a machine-local fact, and a
runtime's authorisation is not something the record should ever be asked to
carry.
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from typing import Any

from mentis import mirror as _mirror


class Authority:
    def __init__(self) -> None:
        #: WHAT A DISPATCHED WORKER IS AUTHORISED TO ASK: token -> grant.
        self._grants: dict[str, dict[str, Any]] = {}
        self._granted_to: dict[str, str] = {}
        #: WHY AN EXECUTION WAS DISPATCHED, which is what decides how much it
        #: may do. Set at summon by the caller that knows -- dispatch -- and
        #: read when the grant is minted, so authority rides on the grant
        #: rather than on who the Participant is or what it is called. An
        #: execution nobody set this for gets the ordinary worker scope.
        self._authority: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        #: ONE MIRRORED CHANGE AT A TIME, so pushes go in table order. Taken
        #: before `_lock`, and the pull takes only `_lock` (`docs/rust/
        #: R3-mirror.md`, section 3). None without a boot secret: Python alone
        #: pushes nothing and fences nothing.
        self._changes = threading.Lock()
        self.mirror: _mirror.Mirror | None = None

    def _view(self, grant: dict) -> dict | None:
        return _mirror.mirrored(grant) if self.mirror is not None else None

    def _pushed(self, change: tuple | None) -> tuple[bool, float | None]:
        """Say this change to the front, inside `_changes` and outside `_lock`.
        `change` is `_view_moved`'s. Every mirrored change is pushed once, `down`
        or not, and a failed one sets `down`, which plays no part in the fence."""
        if change is None:
            return False, None
        generation, deadline, key, view = change
        if self.mirror.push(generation, key, view):
            return False, deadline
        with self._lock:
            self.mirror.down = True
        return True, deadline

    def _view_moved(self, token: str, before: dict | None,
                    after: dict | None) -> tuple | None:
        """Under `_lock`, right after the table changed: what the mirror has to
        be told, or None if what it holds of this grant is unchanged."""
        if self.mirror is None or before == after:
            return None
        generation, deadline = self.mirror.moved()
        return generation, deadline, _mirror.key_of(token), after

    @staticmethod
    def _fence(failed: bool, deadline: float | None) -> None:
        """A change that removed or narrowed a grant, whose push failed, doesn't
        return until any lease that could predate it has run out. Holding no
        lock. Never later than the change's time plus `FENCE`."""
        if failed and deadline is not None:
            left = deadline - time.perf_counter()
            if left > 0:
                time.sleep(left)

    def authorise_for(self, instance_id: str, authority: dict | None) -> None:
        """Say why this execution was dispatched, before it is performed.

        The grant is minted at perform and this is what it reads. Kept apart
        from summoning because an instance may be REUSED, and a reused instance
        carries the previous run's reason until this replaces it: authority
        belongs to the run, not to the session.

        A grant already minted for this execution (a run in flight) is
        updated in place, so what dispatch learns while composing -- what the
        run was `delivered` -- reaches the grant the run is holding.
        """
        with self._changes:
            with self._lock:
                if authority is None:
                    self._authority.pop(instance_id, None)
                    return
                self._authority[instance_id] = dict(authority)
                token = self._granted_to.get(instance_id)
                change = None
                if token and token in self._grants:
                    before = self._view(self._grants[token])
                    self._grants[token].update(self._shape(instance_id))
                    change = self._view_moved(
                        token, before, self._view(self._grants[token]))
            failed, deadline = self._pushed(change)
        self._fence(failed, deadline)

    def delivered_for(self, instance_id: str) -> list[str]:
        """What this execution's run was told, by source id (`_shape`)."""
        with self._lock:
            return list((self._authority.get(instance_id) or {}).get("delivered") or ())

    def _shape(self, instance_id: str) -> dict:
        authority = dict(self._authority.get(instance_id) or {})
        return {"scope": authority.get("scope") or "worker",
                "operations": authority.get("operations"),
                "expectation": authority.get("expectation"),
                "conversation": authority.get("conversation"),
                "participant": authority.get("participant"),
                "runtime": authority.get("runtime"),
                # THE PERSONA IT WEARS, for what it records.
                "persona": authority.get("persona"),
                # WHAT THIS RUN WAS TOLD, by source id, as composed for it
                # (`dispatch._dispatch`).
                "delivered": list(authority.get("delivered") or ())}

    def _grant(self, instance_id: str, corpus: str) -> str:
        """Authorise one execution to ask the four reads about one corpus.

        AN OPAQUE STRING AND NOT AN IDENTITY. There are no users here, no
        roles and nothing to look anybody up in. A grant says one thing --
        this execution may ask these questions about this corpus -- and
        holding it is the whole of the claim. A worker must not be authorised
        by WHERE it is calling from.

        LIFETIME IS AN OBSERVED FACT, NOT A CLOCK: the run it authorises.
        Minted when a perform begins and revoked when it ends (`revoke`).
        """
        token = secrets.token_urlsafe(32)
        with self._changes:
            with self._lock:
                # WHAT THE WORK IS, TRAVELLING WITH THE PERMISSION TO DO IT: why
                # the execution was dispatched -- its scope, the expectation it
                # is carrying, and where -- so the server derives an actor, a
                # cause and a provenance instead of believing a worker's claim.
                self._grants[token] = {"instance": instance_id, "corpus": corpus,
                                       **self._shape(instance_id)}
                self._granted_to[instance_id] = token
                change = self._view_moved(
                    token, None, self._view(self._grants[token]))
            # Not fenced: a token the front lacks forwards.
            self._pushed(change)
        return token

    def revoke(self, instance_id: str) -> None:
        """The run this execution's grant authorised has ended: the grant goes,
        and so does the reason, so a reused session does not carry the
        previous run's scope into the next one."""
        with self._changes:
            with self._lock:
                spent = self._granted_to.pop(instance_id, None)
                change = None
                if spent:
                    gone = self._grants.pop(spent, None)
                    change = self._view_moved(
                        spent, self._view(gone) if gone else None, None)
                self._authority.pop(instance_id, None)
            failed, deadline = self._pushed(change)
        self._fence(failed, deadline)

    def grant_session(self, corpus: str, *, runtime: str,
                      participant: str,
                      execution: str | None = None) -> tuple[str, str]:
        """A grant for a session somebody started by hand: (token, execution).

        THE SAME TABLE, THE SAME DOOR. A dispatched run's grant is minted at
        perform from why it was dispatched; a hand-started session has no
        dispatch, so its grant names its own new execution, the runtime it was
        registered for and `SESSION_SCOPE`, and carries no expectation and no
        Conversation. `/api/worker` reads it exactly as it reads any other.

        LIFETIME: until `end_session` or this process ends. A restart drops it
        and the session asks again -- naming `execution`, the one it already
        is, so what it opened stays its own. Whether it may name that
        execution is decided by the caller, from the record.
        """
        from mentis.worker import AUTHORITY, SESSION_SCOPE
        token = secrets.token_urlsafe(32)
        # A uuid like every instance id, because provenance keeps only its
        # first eight characters (`written_by`).
        execution = execution or str(uuid.uuid4())
        with self._changes:
            with self._lock:
                self._grants[token] = {"instance": execution, "corpus": corpus,
                                       "scope": SESSION_SCOPE,
                                       # WHAT A REQUEST ADDRESSED TO NOBODY --
                                       # the one @Caretaker carries -- is granted.
                                       "operations": list(AUTHORITY),
                                       "expectation": None, "conversation": None,
                                       "participant": participant,
                                       "runtime": runtime, "delivered": []}
                change = self._view_moved(
                    token, None, self._view(self._grants[token]))
            self._pushed(change)
        return token, execution

    def session_held(self, execution: str, corpus: str) -> bool:
        """Whether a live session grant already names this execution."""
        from mentis.worker import SESSION_SCOPE
        with self._lock:
            return any(g["instance"] == execution and g["corpus"] == corpus
                       and g.get("scope") == SESSION_SCOPE
                       for g in self._grants.values())

    def end_session(self, token: str | None, corpus: str) -> dict | None:
        """Revoke a hand-started session's grant. The grant it was, or None.

        Only a session grant: a dispatched run's grant ends with its run.
        """
        from mentis.worker import SESSION_SCOPE
        with self._changes:
            with self._lock:
                grant = self._grants.get(token or "")
                if (grant is None or grant["corpus"] != corpus
                        or grant.get("scope") != SESSION_SCOPE):
                    return None
                self._grants.pop(token, None)
                change = self._view_moved(token, self._view(grant), None)
            failed, deadline = self._pushed(change)
        self._fence(failed, deadline)
        return dict(grant)

    def mirror_pull(self) -> dict:
        """`GET /private/grants`: the whole mirrored table, at one generation."""
        with self._lock:
            return self.mirror.pull(self._grants)

    def mirror_position(self, pid: int) -> dict:
        """`GET /private/grants/position`."""
        with self._lock:
            return self.mirror.position(pid)

    def grant_of(self, instance_id: str) -> str | None:
        """The grant this execution was started with, if it has one."""
        return self._granted_to.get(instance_id)

    def permits_for(self, instance_id: str) -> tuple[str, ...]:
        """The operations this run may perform, from why it was dispatched.

        ONE DECISION, READ IN TWO PLACES. `worker.permitted` maps a scope to a
        set of operation names; the HTTP door uses it to ADMIT a call and this
        uses it to decide what the run is SHOWN.
        """
        from mentis.worker import permitted
        authority = self._authority.get(instance_id) or {}
        return tuple(permitted(authority.get("scope"),
                               authority.get("operations")))

    def authorises(self, token: str | None, corpus: str) -> str | None:
        """The execution this token authorises FOR THIS CORPUS, or None."""
        grant = self.grant_for(token, corpus)
        return grant["instance"] if grant else None

    def grant_for(self, token: str | None, corpus: str) -> dict | None:
        """The whole grant this token carries for this corpus, or None.

        A copy, so nothing a caller does to it can reach the live bookkeeping.
        """
        grant = self._grants.get(token or "")
        if grant is None or grant["corpus"] != corpus:
            return None
        return dict(grant)
