"""Latest or explicitly selected collections, read only from immutable Admissions.

No lift, activation, live-source lookup or repair is performed by this read.
Older activations remain in the append-only record.
"""
from __future__ import annotations

import json
import re

from mentis import artifacts
from mentis.fluid import read as fluid

from . import MAGNET_ID, Unreadable, read as definition
from . import activation as X


class UnreadableCollection(ValueError):
    """A recorded collection cannot be served as the evidence it claims."""


def _config(st, mid):
    if not MAGNET_ID.fullmatch(mid):
        raise fluid.BadRequest("that is not a Magnet id")
    try:
        config = definition(st.corpus.root, mid)
    except Unreadable as exc:
        raise UnreadableCollection(str(exc)) from None
    if config is None:
        raise fluid.NotFound(mid)
    return config


def _retained(st, mid, act):
    bad = UnreadableCollection("this Magnet's latest retained collection is missing or invalid; "
                               "no live source was substituted")
    try:
        detail = act["detail"]
        recorded = detail["artifact"]
        ref = recorded["ref"]
        if ref not in act["about"] or detail["mode"] != X.MODE or not act["turn"]:
            raise bad
        got = artifacts.describe(st.corpus, ref, verify=True)
        if (got["state"] != "held" or got["source"] != f"magnet:{mid}"
                or got["door"] != "magnet-extract" or got["claimed_media_type"] != X.MEDIA_TYPE
                or got["digest"] != recorded["digest"] or got["size"] != recorded["size"]):
            raise bad
        raw = got["_bytes"]
        if len(raw) != recorded["size"] or len(raw) > X.ARTIFACT_MOST:
            raise bad
        # Reuse the activation format, identity and provenance verifier, which is read-only.
        verified = X._verified(st, mid, raw, recorded["digest"], X.MEDIA_TYPE)
        if (verified["by"] != act["actor"]
                or verified["operation"]["index"] != detail["operation"]["index"]
                or verified["operation"]["name"] != detail["operation"]["name"]
                or verified["definition_sha256"] != detail["definition_sha256"]
                or verified["state"] != detail["page"]["state"]):
            raise bad
        page = json.loads(raw)["page"]
        activation = {"post": act["turn"],
                      "artifact": {"ref": ref, "digest": recorded["digest"],
                                   "size": recorded["size"], "media_type": X.MEDIA_TYPE},
                      "at": act["at"], "state": verified["state"]}
        return activation, page
    except (KeyError, TypeError, ValueError, OSError, X._Stop):
        raise bad from None


def read(st, mid, *, batch=None, digest=None):
    config = _config(st, mid)
    if (batch is None) != (digest is None) or (batch is not None and (
            not isinstance(batch, str) or not re.fullmatch(r"adm-[0-9a-f]{12}", batch)
            or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest))):
        raise fluid.BadRequest("historical collection needs batch=<adm-ref> and digest=<SHA-256>")
    filters = {"magnet": mid}
    if batch is None:
        acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is=filters,
                                     newest_first=True, limit=1)
    else:
        acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is=filters,
                                     about=batch, newest_first=True, limit=1)
        if not acts or acts[0]["detail"].get("artifact", {}).get("ref") != batch:
            raise fluid.NotFound(batch)
        if acts[0]["detail"]["artifact"]["digest"] != digest:
            raise UnreadableCollection("the requested digest does not match this recorded collection")
    activation, page = _retained(st, mid, acts[0]) if acts else (None, None)
    return {"magnet": mid, "config": config, "activation": activation, "page": page}


def history(st, mid, *, limit=20, cursor=None):
    _config(st, mid)
    if isinstance(limit, str) and re.fullmatch(r"[0-9]{1,2}", limit):
        limit = int(limit)
    if type(limit) is not int or not 1 <= limit <= 20:
        raise fluid.BadRequest("history limit is 1..20")
    if cursor is None:
        upper = st.corpus.advance()[1]
        before = upper + 1
    else:
        match = re.fullmatch(r"mc1\.([A-Za-z0-9_-]+)\.([0-9]{1,20})\.([0-9]{1,20})", str(cursor))
        if not match or match[1] != mid:
            raise fluid.BadRequest("that is not this Magnet's collection history cursor")
        upper, before = int(match[2]), int(match[3])
        if not 0 < before <= upper + 1 <= 2**63 - 1:
            raise fluid.BadRequest("that collection history cursor is out of range")
    rows = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is={"magnet": mid},
        newest_first=True, through_seq=upper, before_seq=before, limit=limit + 1)
    batches = [_retained(st, mid, act)[0] for act in rows[:limit]]
    boundary = st.corpus.operational_order([rows[limit-1]["id"]]) if len(rows) > limit else {}
    next_cursor = f"mc1.{mid}.{upper}.{boundary[rows[limit-1]['id']]}" if boundary else None
    return {"magnet": mid, "batches": batches, "next": next_cursor}
