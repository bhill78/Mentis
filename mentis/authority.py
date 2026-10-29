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
import uuid
from typing import Any


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
        with self._lock:
            if authority is None:
                self._authority.pop(instance_id, None)
                return
            self._authority[instance_id] = dict(authority)
            token = self._granted_to.get(instance_id)
            if token and token in self._grants:
                self._grants[token].update(self._shape(instance_id))

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
        with self._lock:
            # WHAT THE WORK IS, TRAVELLING WITH THE PERMISSION TO DO IT: why
            # the execution was dispatched -- its scope, the expectation it is
            # carrying, and where -- so the server derives an actor, a cause
            # and a provenance instead of believing a worker's claim.
            self._grants[token] = {"instance": instance_id, "corpus": corpus,
                                   **self._shape(instance_id)}
            self._granted_to[instance_id] = token
        return token

    def revoke(self, instance_id: str) -> None:
        """The run this execution's grant authorised has ended: the grant goes,
        and so does the reason, so a reused session does not carry the
        previous run's scope into the next one."""
        with self._lock:
            spent = self._granted_to.pop(instance_id, None)
            if spent:
                self._grants.pop(spent, None)
            self._authority.pop(instance_id, None)

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
        with self._lock:
            self._grants[token] = {"instance": execution, "corpus": corpus,
                                   "scope": SESSION_SCOPE,
                                   # WHAT A REQUEST ADDRESSED TO NOBODY -- the
                                   # one @Caretaker carries -- is granted.
                                   "operations": list(AUTHORITY),
                                   "expectation": None, "conversation": None,
                                   "participant": participant,
                                   "runtime": runtime, "delivered": []}
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
        with self._lock:
            grant = self._grants.get(token or "")
            if (grant is None or grant["corpus"] != corpus
                    or grant.get("scope") != SESSION_SCOPE):
                return None
            self._grants.pop(token, None)
            return dict(grant)

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
