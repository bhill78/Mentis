"""Presentation: how the owner's canvas looks. Kept BESIDE the record, never in it.

Approved by the owner in "Mentis Themes and Backgrounds" (docs/design/presentation-store.md).

WHAT IT IS. A brain's looks -- the ones made from a picture -- and which look the brain and
each Conversation are drawn in. The browser used to hold all of this, so a look chosen on the
laptop was not there on the phone. It is held here instead, beside `corpus.db`:

    <corpus>/presentation/looks.json          the looks, and the choices
    <corpus>/presentation/pictures/<sha256>   the pictures a look uses

WHY NOT THE RECORD. `ui/src/atmosphere.ts` recorded the reasons before this existed: an Entry
ESTABLISHES, so a colour would become knowledge that retrieval returns; the one
Conversation-scoped kind, `conversation-instruction`, is DELIVERED TO AGENTS; and
`tests/test_web.py::test_the_ui_added_no_schema` refuses a table for it. The held byte store
is no answer either -- its bytes are only served and copied when a held ADMISSION names them,
so every picture would be a record entry. So this is a folder, like `artifacts/` and
`instances/`, and nothing in it is an act, an author or a history. It is current state,
overwritten in place: "who changed the colours on Tuesday" is not a question Mentis answers.

WHAT NEVER READS IT: context formation, retrieval, delivery, governance, any worker. Only the
`/api/presentation` routes do, and a worker grant is refused on all of them.

WHAT IT TRUSTS: nothing it is sent. A look's tokens are written into a <style> element by the
interface, so every token name must be one the atmosphere contract defines and every value must
be colours, lengths, numbers and gradients of them -- or a look would be a way to put arbitrary
CSS in the page. Pictures are kept only if their own bytes say they are JPEG, PNG or WebP.

A MISSING OR UNREADABLE FOLDER IS DEFAULTS, NEVER AN ERROR. A brain made before this existed
simply has no looks.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import threading
import time
import uuid

DIR = "presentation"
LIST = "looks.json"
PICTURES = "pictures"
VERSION = 1

#: One picture. The interface sends a re-encoded JPEG of about half a megabyte; this is a
#: bound, not a policy.
MAX_PICTURE = 5 * 1024 * 1024
#: Enough for every look anybody will make, and a bound on the list's size.
MAX_LOOKS = 100
#: Conversations with a choice of their own. A bound, so the list cannot grow without end.
MAX_CHOSEN = 5000
#: A picture younger than this is never swept: another device may have just sent it and be
#: about to name it in a look (the upload and the look are two requests).
GRACE_S = 15 * 60

#: THE ATMOSPHERE CONTRACT (ui/src/atmosphere.css), as the picture looks write it. A name not
#: here is refused rather than passed through.
TOKENS = frozenset({
    "--canvas", "--canvas-ink", "--canvas-image", "--canvas-image-opacity",
    "--canvas-image-position", "--canvas-image-blur", "--canvas-drift", "--canvas-veil",
    "--reading-veil", "--reading-fade", "--reading-blur",
    "--surface", "--surface-sunken", "--surface-deep", "--surface-raised", "--raised",
    "--on-canvas", "--on-canvas-blur",
    "--text", "--text-dim", "--text-faint", "--line", "--line-strong",
    "--wash", "--wash-strong", "--selection",
    "--accent", "--accent-ink", "--accent-soft", "--accent-wash",
    "--attention", "--attention-soft", "--live", "--live-soft", "--ok", "--fail",
    "--edge", "--who-tint",
    "--who-1", "--who-2", "--who-3", "--who-4", "--who-5", "--who-6",
})
#: The only picture references a token may carry. The interface puts the real address in
#: when it draws the look; a stored look never names a URL.
PICTURE_SLOTS = ("url('__wide__')", "url('__tall__')")
#: The only functions a value may call.
FUNCTIONS = frozenset({"rgb", "rgba", "linear-gradient", "radial-gradient", "color-mix"})
_VALUE = re.compile(r"[a-z0-9#%.,()\s\-]*")
_CALL = re.compile(r"([a-z][a-z-]*)\s*\(")
_MAX_VALUE = 2000

_ID = re.compile(r"look-[0-9a-f]{12}")
#: A built-in atmosphere's name. The interface owns that list; the store only checks the shape,
#: and the interface draws a name it does not know as the default.
_BUILT_IN = re.compile(r"[a-z][a-z0-9-]{0,31}")
_CONVERSATION = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
_SHA = re.compile(r"[0-9a-f]{64}")

_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _lock(root: str) -> threading.Lock:
    key = str(pathlib.Path(root).resolve())
    with _locks_lock:
        return _locks.setdefault(key, threading.Lock())


def _dir(root: str) -> pathlib.Path:
    return pathlib.Path(root) / DIR


def empty() -> dict:
    return {"version": VERSION, "looks": [],
            "choices": {"brain": None, "conversations": {}}}


# -- reading ---------------------------------------------------------------------------------

def read(root: str) -> dict:
    """The looks and the choices. Defaults when there is nothing, or nothing readable.

    EVERYTHING READ IS CHECKED AGAIN, as if it had just been sent: the file is on disk, and
    anything that can write a file -- a copy, a hand, a bug -- must not be able to put a
    selector or a URL into the page through it. A look that fails is left out and counted in
    `dropped`; a choice that fails is left out."""
    path = _dir(root) / LIST
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty()
    except (OSError, ValueError):
        out = empty()
        out["unreadable"] = f"{LIST} could not be read; showing the defaults"
        return out
    if not isinstance(data, dict) or data.get("version") != VERSION:
        out = empty()
        out["unreadable"] = f"{LIST} is not a version {VERSION} list; showing the defaults"
        return out
    out = empty()
    raw = data.get("looks")
    looks, dropped = [], 0
    for l in raw if isinstance(raw, list) else []:
        good = _look_or_none(l)
        if good is None:
            dropped += 1
        else:
            looks.append(good)
    if not isinstance(raw, list) and raw is not None:
        dropped += 1
    out["looks"] = looks[:MAX_LOOKS]
    ch = data.get("choices") if isinstance(data.get("choices"), dict) else {}
    brain = ch.get("brain")
    out["choices"]["brain"] = brain if _is_choice(brain) else None
    convs = ch.get("conversations") if isinstance(ch.get("conversations"), dict) else {}
    out["choices"]["conversations"] = {
        c: v for c, v in list(convs.items())[:MAX_CHOSEN]
        if isinstance(c, str) and _CONVERSATION.fullmatch(c) and _is_choice(v)}
    if dropped:
        out["dropped"] = dropped
    return out


def _is_choice(v) -> bool:
    return isinstance(v, str) and bool(_ID.fullmatch(v) or _BUILT_IN.fullmatch(v))


def _look_or_none(l) -> dict | None:
    """One stored look, checked exactly as a new one is, or None."""
    try:
        if not isinstance(l, dict) or not _ID.fullmatch(str(l.get("id", ""))):
            return None
        pics = l.get("pictures") or {}
        if not isinstance(pics, dict) or set(pics) - {"wide", "tall"} or \
                not all(isinstance(v, str) and _SHA.fullmatch(v) for v in pics.values()):
            return None
        created = l.get("created")
        return {"id": l["id"], "name": check_name(l.get("name")),
                "created": float(created) if isinstance(created, (int, float)) else 0.0,
                "theme": check_theme(l.get("theme")), "pictures": dict(pics)}
    except (ValueError, TypeError):
        return None


class Unreadable(RuntimeError):
    """The list on disk could not be read, so nothing is written over it."""


def _for_writing(root: str) -> dict:
    """The list, read to be changed -- refusing when it could not be read, because writing
    the defaults back would throw away every look in it."""
    data = read(root)
    if "unreadable" in data:
        raise Unreadable(f"{data['unreadable']}; it was left exactly as it is")
    data.pop("dropped", None)
    return data


def _write(root: str, data: dict):
    """All or nothing: a temporary file, then a rename over the old list. A crash leaves the
    previous list, never half of one; a stray temporary file is never read."""
    d = _dir(root)
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".incoming-", suffix=".json", dir=d)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, d / LIST)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# -- pictures --------------------------------------------------------------------------------

def picture_type(data: bytes) -> str | None:
    """What the bytes themselves say they are. A claim is never asked."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def add_picture(root: str, data: bytes) -> str:
    """Keep one picture, named by its sha256. The same bytes are kept once."""
    if len(data) > MAX_PICTURE:
        raise ValueError(f"a picture may be at most {MAX_PICTURE} bytes")
    if picture_type(data) is None:
        raise ValueError("that is not a JPEG, PNG or WebP picture")
    sha = hashlib.sha256(data).hexdigest()
    d = _dir(root) / PICTURES
    d.mkdir(parents=True, exist_ok=True)
    target = d / sha
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
        try:
            os.utime(target)        # sent again: the sweep's grace starts again too
        except OSError:
            pass
        return sha
    fd, tmp = tempfile.mkstemp(prefix=".incoming-", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return sha


def picture(root: str, sha: str) -> tuple[bytes, str] | None:
    """The VERIFIED bytes of one picture and the type they say they are, or None."""
    if not _SHA.fullmatch(sha or ""):
        return None
    try:
        data = (_dir(root) / PICTURES / sha).read_bytes()
    except OSError:
        return None
    if hashlib.sha256(data).hexdigest() != sha:
        return None
    kind = picture_type(data)
    return (data, kind) if kind else None


def _has_picture(root: str, sha) -> bool:
    return isinstance(sha, str) and picture(root, sha) is not None


# -- checking what is sent -------------------------------------------------------------------

def check_value(name: str, value) -> str:
    """One token's value, or ValueError. Colours, lengths, numbers and gradients of them."""
    if not isinstance(value, str) or len(value) > _MAX_VALUE:
        raise ValueError(f"{name}: a value must be text of at most {_MAX_VALUE} characters")
    v = value.strip().lower()
    if name == "--canvas-image":
        if v == "none" or v in PICTURE_SLOTS:
            return v
        raise ValueError("--canvas-image may only be none or the look's own picture")
    if not _VALUE.fullmatch(v):
        raise ValueError(f"{name}: {value!r} contains something a look may not carry")
    for fn in _CALL.findall(v):
        if fn not in FUNCTIONS:
            raise ValueError(f"{name}: {fn}() is not something a look may use")
    depth = 0
    for ch in v:
        depth += (ch == "(") - (ch == ")")
        if depth < 0:
            raise ValueError(f"{name}: a bracket closes before it opens")
    if depth:
        raise ValueError(f"{name}: unbalanced brackets")
    return v


def check_tokens(tokens, *, where: str) -> dict:
    if not isinstance(tokens, dict) or len(tokens) > 80:
        raise ValueError(f"{where}: tokens must be a mapping of at most 80 entries")
    out = {}
    for k, v in tokens.items():
        if k not in TOKENS:
            raise ValueError(f"{where}: {k!r} is not a token a look may set")
        out[k] = check_value(k, v)
    return out


def _number(v, lo=0.0, hi=100.0):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not lo <= v <= hi:
        raise ValueError(f"{v!r} is not a number between {lo} and {hi}")
    return float(v)


_HEX = re.compile(r"#[0-9a-f]{6}")


def check_theme(theme) -> dict:
    """The drawable part of a look, as the interface's `PictureTheme` carries it."""
    if not isinstance(theme, dict):
        raise ValueError("a look needs its theme")
    scheme = theme.get("scheme")
    if scheme not in ("dark", "light"):
        raise ValueError("scheme must be dark or light")
    backdrop = theme.get("backdrop", "picture")
    if backdrop not in ("picture", "plain"):
        raise ValueError("backdrop must be picture or plain")
    swatch = theme.get("swatch") or []
    if (not isinstance(swatch, list) or len(swatch) != 3
            or not all(isinstance(s, str) and _HEX.fullmatch(s.lower()) for s in swatch)):
        raise ValueError("swatch must be three #rrggbb colours")
    measured = theme.get("measured") or {}
    return {
        "scheme": scheme,
        "backdrop": backdrop,
        "wide": check_tokens(theme.get("wide"), where="wide"),
        "tall": check_tokens(theme.get("tall"), where="tall"),
        "swatch": [s.lower() for s in swatch],
        "floor": _number(theme.get("floor", 0), 0, 1),
        "veil": _number(theme.get("veil", 0), 0, 1),
        "measured": {k: _number(measured[k], 0, 21)
                     for k in ("wide", "tall", "rail") if k in measured},
    }


def check_name(name) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a look needs a name")
    name = " ".join(name.split())
    if len(name) > 80:
        raise ValueError("a name may be at most 80 characters")
    return name


# -- changing it -----------------------------------------------------------------------------

def add_look(root: str, *, name, theme, pictures) -> tuple[str, dict]:
    """A new look. Its pictures must already be here."""
    name = check_name(name)
    theme = check_theme(theme)
    pics = pictures or {}
    if not isinstance(pics, dict):
        raise ValueError("pictures must name wide and tall")
    kept = {}
    for slot in ("wide", "tall"):
        sha = pics.get(slot)
        if sha is None and theme["backdrop"] == "plain":
            continue
        if not _has_picture(root, sha):
            raise ValueError(f"the {slot} picture was never received here; send it again")
        kept[slot] = sha
    with _lock(root):
        data = _for_writing(root)
        if len(data["looks"]) >= MAX_LOOKS:
            raise ValueError(f"a brain may keep at most {MAX_LOOKS} looks; remove one first")
        # again, under the lock: a removal's sweep may have run since the check above
        if not all(_has_picture(root, sha) for sha in kept.values()):
            raise ValueError("a picture was never received here; send it again")
        look_id = "look-" + uuid.uuid4().hex[:12]
        data["looks"].append({"id": look_id, "name": name, "created": time.time(),
                              "theme": theme, "pictures": kept})
        _write(root, data)
        return look_id, data


def change_look(root: str, look_id: str, *, name=None, remove=False) -> dict:
    """Rename a look, or remove it: its pictures go too unless another look uses them, and
    anything drawn in it goes back to what it inherits."""
    if not _ID.fullmatch(look_id or ""):
        raise ValueError(f"{look_id!r} is not a look")
    with _lock(root):
        data = _for_writing(root)
        look = next((l for l in data["looks"] if l.get("id") == look_id), None)
        if look is None:
            raise LookupError(f"there is no look {look_id}")
        if remove:
            data["looks"] = [l for l in data["looks"] if l is not look]
            ch = data["choices"]
            if ch.get("brain") == look_id:
                ch["brain"] = None
            ch["conversations"] = {c: v for c, v in ch["conversations"].items()
                                   if v != look_id}
        else:
            look["name"] = check_name(name)
        _write(root, data)
        if remove:
            _sweep(root, data)
        return data


def choose(root: str, *, conversation, look) -> dict:
    """What the brain, or one Conversation, is drawn in. `look` None hands a Conversation back
    to what it inherits, or the brain back to the default."""
    if look is not None and not (_ID.fullmatch(look) or _BUILT_IN.fullmatch(look)):
        raise ValueError(f"{look!r} is not a look")
    if conversation is not None and not _CONVERSATION.fullmatch(conversation):
        raise ValueError(f"{conversation!r} is not a Conversation")
    with _lock(root):
        data = _for_writing(root)
        if look is not None and look.startswith("look-") and \
                not any(l.get("id") == look for l in data["looks"]):
            raise LookupError(f"there is no look {look}")
        ch = data["choices"]
        if conversation is not None and look is not None and \
                conversation not in ch["conversations"] and \
                len(ch["conversations"]) >= MAX_CHOSEN:
            raise ValueError(f"at most {MAX_CHOSEN} Conversations may have a look of their own")
        if conversation is None:
            ch["brain"] = look
        elif look is None:
            ch["conversations"].pop(conversation, None)
        else:
            ch["conversations"][conversation] = look
        _write(root, data)
        return data


def _sweep(root: str, data: dict):
    """Delete pictures no look names. Only ever after the list that stopped naming them is
    written, so a crash between the two leaves a spare file, never a look without its picture."""
    named = {sha for l in data["looks"] if isinstance(l, dict)
             for sha in (l.get("pictures") if isinstance(l.get("pictures"), dict)
                         else {}).values()}
    d = _dir(root) / PICTURES
    if not d.is_dir():
        return
    young = time.time() - GRACE_S
    for f in d.iterdir():
        if not _SHA.fullmatch(f.name) or f.name in named:
            continue
        try:
            if f.stat().st_mtime > young:
                continue            # just sent, and perhaps about to be named
            f.unlink()
        except OSError:
            pass


# -- moving a brain --------------------------------------------------------------------------

def copy(src_root: str, dst_root: str) -> bool:
    """Carry a brain's looks to a copy of it. Nothing to carry is not an error.

    `Corpus.snapshot` copies the record and the bytes the record names, and stays that way:
    presentation is not spine. Whatever copies a brain calls this beside it."""
    src = _dir(src_root)
    if not src.is_dir():
        return False
    with _lock(src_root):
        shutil.copytree(src, _dir(dst_root), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".incoming-*"))
    return True
