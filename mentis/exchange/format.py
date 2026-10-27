"""The export file: one self-describing zip (design §2). SHARED CONTRACT.

    MANIFEST.json    format, version; origin {corpus_id, marker_corpus_id,
                     fork_id}; schema ledger (ids + checksums); exporter
                     release; exported_at; by; marks [{id, kind}]; counts;
                     sha256 of every other member (`members`)
    entries.jsonl    one row per entry exactly as the origin holds it, plus
                     origin_seq and origin_hash (evidence only)
    acts.jsonl       the meaning-giving operational rows, verbatim, plus
                     origin_seq and origin_hash
    definitions.json every Kind/Relation version the rows name: name,
                     version, canonical body, body sha256
    evidence.json    standing on the origin. Never imported as links
    stubs.json       referenced, not carried
    blobs/sha256/<2>/<hex>   held bytes, named by digest

IDENTITY ACROSS BRAINS IS (id, fingerprint). The chain hash covers
`prev_hash`, so it names a row's place on ONE chain and cannot identify it on
another. `fingerprint` is sha256 of the row's canonical form -- the spine's
own `Store._canonical`, field by field in the chained column order -- WITHOUT
`prev_hash` and `hash`. JSON columns are put in the store's own dump form
first, so a row read from either Brain, or from the file, fingerprints the
same.

THE MEMBER HASHES DETECT DAMAGE, NOT MALICE. Nothing signs the manifest, so
somebody who rewrites a member and its hash in the manifest is not caught
here. `read` refuses any member whose bytes do not match the manifest, any
member the manifest does not name, and any blob whose bytes are not its name.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import zipfile

from mentis.spine import store as _store

from . import ExchangeRefused

FORMAT = "mentis-export"
VERSION = 1

MANIFEST = "MANIFEST.json"
ENTRIES = "entries.jsonl"
ACTS = "acts.jsonl"
DEFINITIONS = "definitions.json"
EVIDENCE = "evidence.json"
STUBS = "stubs.json"
BLOBS = "blobs/sha256/"
MEMBERS = (ENTRIES, ACTS, DEFINITIONS, EVIDENCE, STUBS)

#: what a row carries beside the record itself, and is not part of it
EVIDENCE_FIELDS = ("origin_seq", "origin_hash")


def _dump(value) -> str:
    return _store._dump(value)


def _json_value(v, empty):
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return v
    return v if v else empty


def is_act(row: dict) -> bool:
    return "act" in row and "family" not in row


def fingerprint(row: dict) -> str:
    """sha256 hex of a row's canonical form, without prev_hash and hash.

    `row` is an entry or an operational act, as a database row (JSON columns
    as text) or as a record (`definition`/`link` objects, parsed JSON)."""
    if is_act(row):
        table = "operational"
        values = {c: row.get(c) for c in _store.Store.CHAINED[table]}
        values["about"] = _dump(_json_value(row.get("about"), []))
        values["detail"] = _dump(_json_value(row.get("detail"), {}))
    else:
        table = "entry"
        rec = dict(row)
        if "def_name" in rec or isinstance(rec.get("body"), str):
            rec = _store._inflate({**{c: rec.get(c) for c in (
                "id", "family", "def_name", "def_version", "attributed_to",
                "written_by", "recorded_at", "origin", "link_from", "link_to",
                "link_relation", "link_relation_version")},
                "body": rec.get("body") if isinstance(rec.get("body"), str)
                else _dump(rec.get("body"))})
        values = _store._flatten(rec)
    material = _store.Store._canonical(table, _store.Store.CHAINED[table],
                                       values)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def body_sha256(body) -> str:
    """The sha256 of a definition body in its canonical (store dump) form."""
    return hashlib.sha256(_dump(body).encode("utf-8")).hexdigest()


def blob_member(digest: str) -> str:
    return f"{BLOBS}{digest[:2]}/{digest}"


@dataclasses.dataclass
class Export:
    """One export file, read and verified."""
    path: str
    manifest: dict
    manifest_sha256: str
    entries: list
    acts: list
    definitions: list
    evidence: list
    stubs: list
    blob_digests: list

    @property
    def origin(self) -> dict:
        return self.manifest.get("origin") or {}

    def blob(self, digest: str) -> bytes:
        with zipfile.ZipFile(self.path) as z:
            return z.read(blob_member(digest))


def _jsonl(rows) -> bytes:
    return "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n"
                   for r in rows).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write(path: str, *, manifest: dict, entries, acts, definitions,
          evidence, stubs, blobs: dict) -> dict:
    """Write the zip at `path`: as `<path>.partial`, then renamed into place,
    so a reader never meets half a file. `blobs` is digest -> bytes. Returns
    the manifest as written (with `members` and `counts`)."""
    members = {
        ENTRIES: _jsonl(entries),
        ACTS: _jsonl(acts),
        DEFINITIONS: json.dumps(definitions, sort_keys=True, indent=1,
                                ensure_ascii=False).encode("utf-8"),
        EVIDENCE: json.dumps(evidence, sort_keys=True, indent=1,
                             ensure_ascii=False).encode("utf-8"),
        STUBS: json.dumps(stubs, sort_keys=True, indent=1,
                          ensure_ascii=False).encode("utf-8"),
    }
    for digest, data in sorted(blobs.items()):
        if _sha(data) != digest:
            raise ExchangeRefused(f"held bytes {digest[:12]} do not match "
                                  f"their digest; nothing was written")
        members[blob_member(digest)] = data
    out = dict(manifest)
    out["format"], out["version"] = FORMAT, VERSION
    out["counts"] = {"entries": len(entries), "acts": len(acts),
                     "definitions": len(definitions),
                     "evidence": len(evidence), "stubs": len(stubs),
                     "blobs": len(blobs)}
    out["members"] = {name: _sha(data) for name, data in members.items()}
    partial = path + ".partial"
    try:
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(MANIFEST, json.dumps(out, sort_keys=True, indent=1,
                                            ensure_ascii=False))
            for name, data in members.items():
                z.writestr(name, data)
        os.replace(partial, path)
    finally:
        if os.path.exists(partial):
            os.remove(partial)
    return out


def read(zip_path: str) -> Export:
    """Read and verify an export. Refused (`ExchangeRefused`) in words when
    it is not one, is of another format version, or any member does not
    match the manifest."""
    try:
        z = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ExchangeRefused(f"{zip_path} is not a readable export: {exc}")
    with z:
        names = set(z.namelist())
        if MANIFEST not in names:
            raise ExchangeRefused(f"{zip_path} has no {MANIFEST}, so it is "
                                  f"not a Mentis export")
        raw = z.read(MANIFEST)
        try:
            manifest = json.loads(raw)
        except ValueError as exc:
            raise ExchangeRefused(f"{MANIFEST} is not JSON: {exc}")
        if manifest.get("format") != FORMAT:
            raise ExchangeRefused(f"{zip_path} is not a {FORMAT} file")
        if manifest.get("version") != VERSION:
            raise ExchangeRefused(
                f"{zip_path} is format version {manifest.get('version')}; "
                f"this Mentis reads version {VERSION}")
        listed = manifest.get("members") or {}
        missing = [n for n in MEMBERS if n not in listed]
        if missing:
            raise ExchangeRefused(f"the manifest names no hash for {missing}")
        extra = sorted(names - set(listed) - {MANIFEST})
        if extra:
            raise ExchangeRefused(
                f"the file holds members its manifest does not name: "
                f"{extra[:5]}; it was changed after it was written")
        data = {}
        for name, want in listed.items():
            if name not in names:
                raise ExchangeRefused(f"the manifest names {name}, which "
                                      f"the file does not hold")
            got = z.read(name)
            if _sha(got) != want:
                raise ExchangeRefused(
                    f"{name} does not match the hash its manifest records "
                    f"({_sha(got)[:12]} is not {str(want)[:12]}); the file "
                    f"was damaged or changed after it was written")
            if name.startswith(BLOBS):
                digest = name.rsplit("/", 1)[-1]
                if _sha(got) != digest or name != blob_member(digest):
                    raise ExchangeRefused(f"{name} is not named by its "
                                          f"own digest")
            else:
                data[name] = got

    def lines(b):
        return [json.loads(x) for x in b.decode("utf-8").splitlines()
                if x.strip()]

    return Export(
        path=os.path.abspath(zip_path), manifest=manifest,
        manifest_sha256=_sha(raw),
        entries=lines(data[ENTRIES]), acts=lines(data[ACTS]),
        definitions=json.loads(data[DEFINITIONS]),
        evidence=json.loads(data[EVIDENCE]),
        stubs=json.loads(data[STUBS]),
        blob_digests=sorted(n.rsplit("/", 1)[-1] for n in listed
                            if n.startswith(BLOBS)))

