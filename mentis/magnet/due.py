"""Scheduled collection: one bounded due pass, and nothing else (AGENTS.md, "Background work").

`collection.mode = "scheduled"` and its cadence have been stored since M1 (`schema.py`,
`_schedule`/`_when`) and activation refused to run one. This module is what reads that cadence and
runs the Magnet's collection when it comes due, through the ONE activation path there is.

THE BOUND, which is this module's whole subject. Each limit is a named constant with a test of it
in `tests/test_magnet_due_runner.py`:

  what starts it   ONE keeper per served Brain, started once by `mentis.web.serve` after the port
                   is bound and before a request is served (`start`). Nothing else starts a pass:
                   not a request, not a write, not a run ending, not a failure. There is no
                   watchdog, no wake check and nothing that looks for work.
  when it stops    `stop()`, called when the server closes. The thread is a daemon and never
                   outlives the process. `start` twice gives the same keeper and no second thread.
  at most how      one pass per `PASS_EVERY_S`, and a cadence shorter than `CADENCE_LEAST_S` is
  often            read as `CADENCE_LEAST_S`, so no configuration can ask for a faster pass.
  at most how      `MAGNETS_MOST` Magnets per pass; exactly one activation per Magnet per cadence
  many             slot, which the append-only record enforces and not a timer (`DUE_OP_PREFIX`
                   keys the slot, so a second attempt replays and records nothing); at most
                   `COLLECTIONS_MOST` bound collections refreshed per pass and
                   `REFRESH_PER_COLLECTION_MOST` refresh of each.
  a failed pass    changes nothing and is NOT retried. Every failure is caught, named in the
                   pass's own result, and dropped. There is no queue, no backoff, no attempt
                   counter and no second try: the next interval reads the record again.
  an idle server   with no scheduled Magnet reads the definition catalogue and stops. No network,
                   no acquisition, no record read of a Magnet, no write, no activation.

WHO AUTHORS AN UNATTENDED COLLECTION, and why it is not a side route (Part D2's design question).
It is not the owner acting: nothing here mints, presents, forges or checks an owner session, and
the request it makes carries no credential at all. It is not a worker: no grant is minted, read or
presented, `/api/worker` is never touched, and no capability is asked for. The author is read out
of the Magnet's OWN RECORD -- the Participant the latest recorded `magnet-extracted` act of this
Magnet already names as the author of its collections (`author_of`). So the runner cannot name any
Participant this Magnet's record does not already carry for exactly this operation, and a Magnet
nobody has ever collected is not collected unattended either. What the schedule decides is WHEN,
never WHO and never WHAT may be read. Authority is unchanged in both directions: the activation
goes through the only activation path there is (the public door, then Python's preflight and
commit), every check on that path runs exactly as it does for a press, and the record keeps
`because` saying the collection was due rather than asked for (`activation.DUE_OP_PREFIX`).

AND THE OWNER'S AUTHENTICATION IS NOT WEAKENED FOR IT, which is the plainest thing to say about
this runner. Activating writes the record, so the door asks for a live owner session
(`_Handler._owner_refused`, and the private steps again behind the front). The unattended request
presents none, so it is admitted on exactly one footing: where the installation trusts its local
owner, which the owner set explicitly and recorded (`owner_auth trust-local`, owner decision
2026-11-11, "every owner request this server admits is the owner's"). Where the owner keeps a
passphrase instead, an unattended collection is refused 401 and said in the pass's result -- it is
NOT worked around, and nothing here mints, reads, caches or asks for a session to get past it. If
unattended collection should also happen on a passphrase installation, that is an owner decision
about authentication, and it belongs to the owner and not to this file.

WHAT REACHES THE NETWORK WITHOUT THE OWNER PRESENT (Part D1). One loopback request per due
Magnet, to this installation's own front; and, for a bound collection a due Magnet reads, the
fetch its connector already makes for an owner's sweep -- `git fetch` over the transports
`mentis.sources.git` already allows, with its existing timeouts, and whatever Part W's connectors
fetch under their own bounds. Nothing new reaches anywhere: there is no new acquisition path, no
new transport, no new address and no credential of any kind. A collection whose binding is new or
changed, whose connector is unavailable, that is unbound, or whose plan needs a decision about
sensitive or categorised material is left alone and reported: those stay the owner's.
"""
from __future__ import annotations

import datetime
import http.client
import ipaddress
import json
import re
import threading
import time
import urllib.parse

from . import definitions
from . import activation as X

# -- the bound ------------------------------------------------------------------------------------

#: AT MOST ONE PASS PER INTERVAL. The keeper does one pass, then waits this long.
PASS_EVERY_S = 300.0
#: THE SHORTEST CADENCE ANY CONFIGURATION CAN ASK FOR. A stored `PT1S` is read as this, so a
#: definition cannot make the runner collect faster than the pass itself.
CADENCE_LEAST_S = 300.0
#: AT MOST THIS MANY MAGNETS PER PASS. The rest wait for the next pass; nothing is queued.
MAGNETS_MOST = 5
#: AT MOST THIS MANY BOUND COLLECTIONS REFRESHED PER PASS, over all the due Magnets together.
COLLECTIONS_MOST = 5
#: AT MOST THIS MANY REFRESHES OF ONE COLLECTION PER PASS. One plan and the one sweep that
#: confirms it: the fetch an owner's sweep already makes, once.
REFRESH_PER_COLLECTION_MOST = 1
#: HOW LONG ONE UNATTENDED ACTIVATION MAY TAKE on the loopback connection, whole.
ACTIVATE_WITHIN_S = 120.0
#: HOW FAR BACK A CRON CADENCE IS READ for the slot it is in: a bounded scan of minutes, never a
#: search forward and never unbounded.
CRON_BACK_MINUTES = 60 * 24 * 7

#: THE OPERATION KEY OF AN UNATTENDED COLLECTION, which makes the record itself the thing that
#: holds "once per cadence slot": the same slot is the same key, and a keyed activation is
#: recorded once however often it arrives (`anchors.prior_outcome`).
DUE_OP_PREFIX = X.DUE_OP_PREFIX

#: WHAT THE SERVER OBSERVED of an unattended acquisition: no request and no grant, this server's
#: own due pass. Not `unattributed-local-request`, which is a request that presented nothing.
DUE_WRITER = "scheduled:magnet-due"

#: The client header every JSON route needs. It says a JSON client, and authorises nothing.
_CLIENT_HEADER = ("X-Mentis-Client", "1")

_ISO = re.compile(r"P(?=\d|T\d)(?:(\d+)W)?(?:(\d+)D)?(?:T(?=\d)(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_CRON_FIELD = re.compile(r"[0-9*/,-]+$")


# -- the cadence ----------------------------------------------------------------------------------

def _iso_seconds(said: str) -> float | None:
    """What an ISO 8601 duration comes to in seconds, or None if it is not one."""
    found = _ISO.fullmatch(said)
    if not found:
        return None
    weeks, days, hours, minutes, seconds = (int(g or 0) for g in found.groups())
    total = ((weeks * 7 + days) * 86400.0 + hours * 3600.0 + minutes * 60.0 + seconds)
    return total or None


def _cron_field(said: str, low: int, high: int) -> set[int] | None:
    """The values one cron field names, or None if it names none this build reads."""
    if not _CRON_FIELD.fullmatch(said):
        return None
    out: set[int] = set()
    for part in said.split(","):
        step, _, after = part.partition("/")
        if after:
            try:
                every = int(after)
            except ValueError:
                return None
            if every < 1:
                return None
        else:
            every = 1
        if step == "*":
            first, last = low, high
        else:
            start, dash, end = step.partition("-")
            try:
                first = int(start)
                last = int(end) if dash else first
            except ValueError:
                return None
        if not (low <= first <= high and low <= last <= high and first <= last):
            return None
        out.update(range(first, last + 1, every))
    return out or None


def _cron(said: str) -> tuple[set[int], ...] | None:
    """A five-field cron expression read as its five value sets, or None."""
    fields = said.split(" ")
    if len(fields) != 5:
        return None
    bounds = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
    got = []
    for text, (low, high) in zip(fields, bounds):
        one = _cron_field(text, low, high)
        if one is None:
            return None
        got.append(one)
    if 7 in got[4]:                      # both 0 and 7 are Sunday, as cron has it
        got[4] = (got[4] - {7}) | {0}
    return tuple(got)


def _cron_matches(fields, when: datetime.datetime) -> bool:
    minute, hour, dom, month, dow = fields
    day = when.day in dom
    weekday = ((when.weekday() + 1) % 7) in dow
    both_said = len(dom) != 31 and len(dow) != 7
    return (when.minute in minute and when.hour in hour and when.month in month
            and ((day or weekday) if both_said else (day and weekday)))


def slot_of(schedule, now: float) -> str | None:
    """THE CADENCE SLOT `now` FALLS IN, as text, or None where the cadence cannot be read.

    One slot is one collection. An ISO duration gives epoch-aligned slots of at least
    `CADENCE_LEAST_S`; a cron expression gives the most recent minute it names at or before
    `now`, found by a scan bounded to `CRON_BACK_MINUTES`. The slot is the whole of what decides
    whether a collection is due, and it is derived -- never kept, never written, so a restart
    reads the same answer from the same configuration and the same record.
    """
    if not isinstance(schedule, str) or not schedule.strip():
        return None
    said = schedule.strip()
    seconds = _iso_seconds(said)
    if seconds is not None:
        period = max(seconds, CADENCE_LEAST_S)
        return f"every{int(period)}s@{int(now // period)}"
    fields = _cron(said)
    if fields is None:
        return None
    at = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).replace(second=0, microsecond=0)
    for _ in range(CRON_BACK_MINUTES + 1):
        if _cron_matches(fields, at):
            return f"cron@{at.strftime('%Y-%m-%dT%H:%MZ')}"
        at -= datetime.timedelta(minutes=1)
    return None


def op_for(mid: str, slot: str) -> str:
    return f"{DUE_OP_PREFIX}{mid}:{slot}"


# -- who authors ----------------------------------------------------------------------------------

def author_of(st, mid: str) -> str | None:
    """THE PARTICIPANT THIS MAGNET'S OWN RECORD ALREADY NAMES as the author of its collections,
    or None. Read, never chosen: the actor of the latest recorded `magnet-extracted` act of this
    Magnet. A Magnet nobody has collected has no author here and is not collected unattended."""
    acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is={"magnet": mid},
                                 newest_first=True, limit=1)
    who = acts[0].get("actor") if acts else None
    return who if isinstance(who, str) and who.strip() else None


def already_collected(st, mid: str, by: str, op: str) -> bool:
    """Whether this cadence slot's collection is already in the record. A read: the slot's key
    is the record's, so this asks the record rather than keeping state of its own."""
    from mentis.conversation import anchors
    try:
        return anchors.prior_outcome(st.cv, by, op, X.identity(mid)) is not None
    except anchors.Refused:
        # That key came to something else. Not this runner's to resolve, and never a second try.
        return True


# -- what is due ----------------------------------------------------------------------------------

def scheduled(root) -> list[dict]:
    """Every readable definition whose collection is scheduled. A catalogue read of files, and
    the whole of what an idle server does."""
    rows, _bad = definitions(root)
    return [c for c in rows if (c.get("collection") or {}).get("mode") == "scheduled"]


def due(st, *, now=None) -> list[dict]:
    """At most `MAGNETS_MOST` Magnets whose collection is due now and not yet recorded for this
    slot, in id order. A read: nothing is written and nothing is started here."""
    now = time.time() if now is None else now
    out = []
    for config in scheduled(st.corpus.root):
        mid = config["id"]
        slot = slot_of((config.get("collection") or {}).get("schedule"), now)
        if slot is None:
            continue
        by = author_of(st, mid)
        if by is None:
            continue
        op = op_for(mid, slot)
        if already_collected(st, mid, by, op):
            continue
        out.append({"magnet": mid, "config": config, "slot": slot, "author": by, "op": op})
        if len(out) >= MAGNETS_MOST:
            break
    return out


# -- the one activation path ----------------------------------------------------------------------

def _loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def front_door(st):
    """THE ONLY ACTIVATION PATH THERE IS, asked for unattended: one POST of the public body to
    `POST /fluid/api/magnets/<id>/activate` on this installation's own address, which is the
    front where there is one (`answers_at`) and this process where there is not.

    It is the same door a press goes through, byte for byte: the same path, the same body of
    `author` and `op`, the same checks, the same preflight and the same commit. Nothing is
    carried that a press does not carry, and nothing a press carries is left out except a
    credential, which an unattended request has none of and claims none of: no cookie, no bearer
    session, no boot secret, no worker grant. Loopback only -- an `answers_at` that is not this
    machine is refused here rather than asked.
    """
    split = urllib.parse.urlsplit(st.answers_at or "")
    host, port = split.hostname or "", split.port or 80
    if split.scheme != "http" or not _loopback(host):
        raise RuntimeError("an unattended collection is asked for over loopback only; "
                           f"this server answers at {st.answers_at!r}")

    def ask(mid: str, body: dict) -> tuple[int, dict]:
        raw = json.dumps(body).encode("utf-8")
        conn = http.client.HTTPConnection(host, port, timeout=ACTIVATE_WITHIN_S)
        try:
            conn.request("POST", f"/fluid/api/magnets/{urllib.parse.quote(mid)}/activate", raw,
                         {"Content-Type": "application/json",
                          "Content-Length": str(len(raw)),
                          _CLIENT_HEADER[0]: _CLIENT_HEADER[1]})
            answer = conn.getresponse()
            said = answer.read(X.ANSWER_MOST + 1)
            try:
                out = json.loads(said.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                out = {"error": "that is not an activation's answer"}
            return answer.status, out if isinstance(out, dict) else {"answer": out}
        finally:
            conn.close()

    return ask


# -- the acquisition half (Part D1) ---------------------------------------------------------------

def _bound_collections(config) -> list[str]:
    """The collections a Magnet's sources name, each once, in the order the sources give them.
    Connector-agnostic: what a collection's connector is and whether it can be refreshed is the
    registry's to say, so a connector that lands later refreshes with no change here."""
    out = []
    for source in config.get("sources") or ():
        key = source.get("collection")
        if isinstance(key, str) and key.strip() and key not in out:
            out.append(key)
    return out


def refresh(st, collection: str, *, by: str, sources=None) -> dict:
    """ONE REFRESH of one bound collection, with nobody present: the plan the owner's sweep
    makes, and the sweep that confirms exactly that plan. Not a new acquisition path -- it is
    `mentis.sources.registry.Sources`, the one door, with the connector the collection declares,
    so whatever the registry reports available refreshes and nothing else does.

    Left alone, and said, rather than decided here: an unavailable or unimplemented connector, a
    collection that is not bound, a binding that is new or changed (which certifies nothing about
    the material and is the owner's to acknowledge), and a plan that needs a decision about
    sensitive or categorised material. No decision of any kind is supplied: not
    `acknowledge_binding_change`, not `sensitive_decisions`, not `category_decisions`.
    """
    try:
        if sources is None:
            from mentis.sources.registry import Sources
            sources = Sources(st.corpus, st.cv)
        state = sources.binding_state(collection)
    except Exception as exc:                                          # noqa: BLE001
        return {"collection": collection, "refreshed": False, "why": f"{type(exc).__name__}: {exc}"}
    src = sources
    if not (state or {}).get("bound"):
        return {"collection": collection, "refreshed": False, "why": "not bound on this machine"}
    try:
        planned = src.plan(collection)
    except Exception as exc:                                          # noqa: BLE001
        return {"collection": collection, "refreshed": False, "why": f"{type(exc).__name__}: {exc}"}
    confirm = (planned or {}).get("confirm") or {}
    if confirm.get("acknowledge_binding_change"):
        return {"collection": collection, "refreshed": False,
                "why": "its binding is new or changed, which only the owner acknowledges"}
    if not confirm.get("plan"):
        return {"collection": collection, "refreshed": False, "why": "that plan cannot be confirmed"}
    try:
        swept = src.sweep(collection, confirm["plan"], actor=by, written_by=DUE_WRITER,
                          because="its Magnet's collection was due on the schedule its "
                                  "configuration sets")
    except Exception as exc:                                          # noqa: BLE001
        return {"collection": collection, "refreshed": False, "why": f"{type(exc).__name__}: {exc}"}
    return {"collection": collection, "refreshed": True,
            "sweep": (swept or {}).get("act") or (swept or {}).get("sweep")}


# -- one pass -------------------------------------------------------------------------------------

def one_pass(st, *, now=None, activate=None, sources=None, acquire=True) -> dict:
    """ONE BOUNDED DUE PASS. Synchronous, and the whole of what the keeper does.

    Every failure is caught and named in the result. Nothing is retried, here or later: the next
    pass reads the record again and sees what this one recorded, or did not.
    """
    now = time.time() if now is None else now
    found = due(st, now=now)
    out = {"at": now, "due": [one["magnet"] for one in found], "collected": [],
           "refreshed": [], "not_collected": [], "magnets_most": MAGNETS_MOST}
    if not found:
        return out                       # AN IDLE SERVER DOES NOTHING AT ALL beyond this read.
    try:
        ask = activate if activate is not None else front_door(st)
    except Exception as exc:                                          # noqa: BLE001
        out["not_collected"] = [{"magnet": one["magnet"], "why": f"{type(exc).__name__}: {exc}"}
                                for one in found]
        return out
    fetched = 0
    for one in found:
        mid, by, op = one["magnet"], one["author"], one["op"]
        if acquire:
            for collection in _bound_collections(one["config"]):
                if fetched >= COLLECTIONS_MOST:
                    out["refreshed"].append({"collection": collection, "refreshed": False,
                                             "why": f"this pass has refreshed {COLLECTIONS_MOST}"})
                    continue
                fetched += REFRESH_PER_COLLECTION_MOST
                out["refreshed"].append(refresh(st, collection, by=by, sources=sources))
        try:
            status, answer = ask(mid, {"author": by, "op": op})
        except Exception as exc:                                      # noqa: BLE001
            out["not_collected"].append({"magnet": mid, "why": f"{type(exc).__name__}: {exc}"})
            continue
        if status in (200, 201) and not answer.get("refused") and not answer.get("error"):
            out["collected"].append({"magnet": mid, "slot": one["slot"], "status": status,
                                     "post": answer.get("post"),
                                     "batch": (answer.get("artifact") or {}).get("ref")})
        else:
            out["not_collected"].append({"magnet": mid, "status": status,
                                         "why": answer.get("error") or f"answered {status}"})
    return out


# -- the keeper -----------------------------------------------------------------------------------

class Keeper:
    """ONE DUE PASS PER INTERVAL, on a thread of its own, for as long as this server serves.

    Modelled on the approved bounded keepers (`mentis.operational.current_work.CurrentWork`): it
    is started once, it waits on an Event it owns, and `stop()` ends it. It observes nothing, it
    watches nothing, and nothing wakes it: it does a pass, waits `every_s`, and does another.
    """

    def __init__(self, st, *, every_s: float = PASS_EVERY_S, activate=None):
        self.st, self.every_s, self.activate = st, every_s, activate
        self.passes = 0
        self.last: dict | None = None
        self.failed: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> "Keeper":
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._keep, daemon=True, name="magnet-due")
        self._thread.start()
        return self

    def stop(self, *, within: float = 5.0) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(within)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _keep(self) -> None:
        import traceback
        while not self._stop.is_set():
            try:
                self.last = one_pass(self.st, activate=self.activate)
                self.failed = None
            except BaseException as exc:                              # noqa: BLE001
                # A FAILED PASS CHANGES NOTHING AND IS NOT RETRIED. It is kept in `failed` and
                # printed where there is somewhere to print it; the next interval looks again.
                self.failed = f"{type(exc).__name__}: {exc}"
                try:
                    traceback.print_exc()
                except Exception:                                     # noqa: BLE001
                    pass
            self.passes += 1
            self._stop.wait(self.every_s)


_KEEPERS: dict[int, Keeper] = {}
_KEEPERS_LOCK = threading.Lock()


def start(st, *, every_s: float = PASS_EVERY_S, activate=None) -> Keeper:
    """The one due keeper of the Brain this process serves, started. Called once, by
    `mentis.web.serve`, after the port is bound and before a request is served. Called again it
    gives back the keeper that is already running and starts no second thread."""
    key = id(st.corpus)
    with _KEEPERS_LOCK:
        got = _KEEPERS.get(key)
        if got is None:
            got = _KEEPERS[key] = Keeper(st, every_s=every_s, activate=activate)
        return got.start()


def stop(st=None) -> None:
    """End the keeper, or every keeper. Called when the server stops."""
    with _KEEPERS_LOCK:
        keys = [id(st.corpus)] if st is not None else list(_KEEPERS)
        for key in keys:
            got = _KEEPERS.pop(key, None)
            if got is not None:
                got.stop()


__all__ = ["CADENCE_LEAST_S", "COLLECTIONS_MOST", "DUE_OP_PREFIX", "DUE_WRITER", "Keeper",
           "MAGNETS_MOST", "PASS_EVERY_S", "REFRESH_PER_COLLECTION_MOST", "author_of", "due",
           "front_door", "one_pass", "op_for", "refresh", "scheduled", "slot_of", "start", "stop"]
