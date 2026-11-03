"""Magnet definitions, one file per `mag-` id: `<brain>/presentation/magnets/<id>.json`.
Contract: `docs/magnets/M1-contract.md`.

A definition belongs to no arrangement and no Conversation. Arrangements hold zones
naming an id (`mentis.fluid.arrangements`, which keeps `magnets` on its wire as a
projection of what is here), so one Magnet can sit in several and a reconfigure is
seen in all of them. Not in the record, and no new Kind. Writers hold the lock
arrangements are written under (`W._lock`), and each write is atomic. Python is the
only writer; the Rust front reads these files for `magnet_read` and never writes one.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading

from mentis.fluid import _checks as W

from . import schema
from .schema import MAGNET_ID, MISSING, SCHEMA_VERSION, Declined, Refused

FOLDER = "magnets"
Unreadable = W.Unreadable


def _path(root, mid) -> pathlib.Path:
    W._match(MAGNET_ID, mid, "magnet")
    return W._dir(root) / FOLDER / f"{mid}.json"


def wire(definition) -> dict:
    """A definition as an arrangement's `magnets` shows it: the version is the
    file's, and a client round-tripping a config never carries one."""
    return {k: v for k, v in definition.items() if k != "schema_version"}


def read(root, mid) -> dict | None:
    """The definition `mid` names as a config, None if there is none, or
    `Unreadable`: a file that is not wholly a definition is not used, and a
    write refuses rather than replace it."""
    with W._lock(root):
        try:
            data = json.loads(_path(root, mid).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, RecursionError) as exc:
            raise Unreadable(f"the Magnet definition {mid} could not be read: "
                             f"{type(exc).__name__}") from None
        try:
            got = schema.magnet_config(data, f"definition {mid}")
        except Refused as exc:
            raise Unreadable(f"the Magnet definition {mid} is not one: "
                             f"{exc}") from None
        if got["id"] != mid:
            raise Unreadable(f"the Magnet definition {mid} names {got['id']!r}")
        return wire(got)


def exists(root, mid) -> bool:
    return _path(root, mid).exists()


def write(root, mid, config) -> dict:
    """Keep `config` as `mid`'s, under the lock the caller holds. A checked config."""
    W._atomic(_path(root, mid), {**wire(config), "schema_version": SCHEMA_VERSION})
    return wire(config)


def lift(root, key, mid, config, said=None) -> bool:
    """Keep an arrangement's embedded config as its definition, under the lock the
    caller holds, and whether that wrote one. Idempotent, and never over a
    definition already kept: that one is what every arrangement sees. An embedded
    copy that disagrees with it is kept beside it (`<id>.from-<key>.json`), and so
    is `said`, the entry as its file has it, where reading it merged different
    sources (`schema.sources_merged`): nothing lifted is ever lost."""
    wrote = not exists(root, mid)
    if wrote:
        write(root, mid, config)
        same = True
    else:
        try:
            same = read(root, mid) == wire(config)
        except Unreadable:
            same = False
    merged = said is not None and schema.sources_merged(said)
    if merged or not same:
        beside = _path(root, mid).with_name(f"{mid}.from-{key}.json")
        if not beside.exists():
            W._atomic(beside, said if merged else wire(config))
    return wrote


def delete(root, mid) -> bool:
    """Forget the file, under the lock the caller holds. Whether anything still
    refers to it is the caller's (`arrangements.delete_definition`)."""
    try:
        os.unlink(_path(root, mid))
    except FileNotFoundError:
        return False
    return True


def references(root, magnet_id) -> list[dict]:
    """What refers to a Magnet, one item per arrangement:
    `{"arrangement": key, "placed": bool, "held": bool}`. The one place that
    answers this: anything that comes to refer to a Magnet extends it, and
    `arrangements.delete_definition` is refused while anything at all is here."""
    from mentis.fluid import arrangements
    return arrangements.references(root, magnet_id)


def asking_for_conversation(root, mid) -> threading.Lock:
    """Held across creating a Magnet's Conversation, so two first requests make
    one. Not the arrangements' lock: a record write happens under it."""
    return W.asking(root, mid)


def set_conversation(root, mid, conversation) -> dict:
    """Name the Magnet's own Conversation, once. The field is distinct from any
    source, and only this and `correct_conversation` write it: a reconfigure cannot."""
    with W._lock(root):
        config = read(root, mid)
        if config is None:
            raise Declined("state", MISSING)
        if config.get("conversation"):
            return config
        return write(root, mid, {**config, "conversation": conversation})


def correct_conversation(root, mid, conversation) -> dict:
    """Say which Conversation the record holds as this Magnet's own, over whatever
    the file names (`mentis.fluid.commands`): the record is right. Asked with what it
    already says, nothing is written."""
    with W._lock(root):
        config = read(root, mid)
        if config is None:
            raise Declined("state", MISSING)
        if config.get("conversation") == conversation:
            return config
        return write(root, mid, {**config, "conversation": conversation})


__all__ = ["FOLDER", "MISSING", "SCHEMA_VERSION", "Declined", "Refused",
           "Unreadable", "asking_for_conversation", "correct_conversation", "delete",
           "exists", "lift", "read", "references", "schema", "set_conversation",
           "wire", "write"]
