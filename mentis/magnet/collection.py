"""The latest recorded collection, read only from its immutable Admission.

No lift, activation, live-source lookup or repair is performed by this read.
Older activations remain in the append-only record.
"""
from __future__ import annotations

import json

from mentis import artifacts
from mentis.fluid import read as fluid

from . import MAGNET_ID, Unreadable, read as definition
from . import activation as X


class UnreadableCollection(ValueError):
    """A recorded collection cannot be served as the evidence it claims."""


def read(st, mid):
    if not MAGNET_ID.fullmatch(mid):
        raise fluid.BadRequest("that is not a Magnet id")
    try:
        config = definition(st.corpus.root, mid)
    except Unreadable as exc:
        raise UnreadableCollection(str(exc)) from None
    if config is None:
        raise fluid.NotFound(mid)
    out = {"magnet": mid, "config": config, "activation": None, "page": None}
    acts = st.corpus.operational(act=X.MAGNET_EXTRACTED, detail_is={"magnet": mid},
                                 newest_first=True, limit=1)
    if not acts:
        return out
    act = acts[0]
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
                or verified["definition_sha256"] != detail["definition_sha256"]
                or verified["state"] != detail["page"]["state"]):
            raise bad
        page = json.loads(raw)["page"]
        out["activation"] = {"post": act["turn"],
                             "artifact": {"ref": ref, "digest": recorded["digest"],
                                          "size": recorded["size"], "media_type": X.MEDIA_TYPE},
                             "at": act["at"], "state": verified["state"]}
        out["page"] = page
    except (KeyError, TypeError, ValueError, OSError, X._Stop):
        raise bad from None
    return out
