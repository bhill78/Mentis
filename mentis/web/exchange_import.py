"""Exchange import endpoints: preview and staging for Mentis archives.

Accepts an uploaded `.zip` archive, parses manifest and classifies items
using `mentis.exchange.preview.classify(store, archive)` under shared read
lock without mutating state.
"""

from __future__ import annotations

import base64
import email
from email.policy import default
import json
import os
import shutil
import tempfile

from mentis.exchange import ExchangeRefused, format as fmt
from mentis.exchange.identity import identity_from
from mentis.exchange.preview import DIVERGED, IDENTICAL, NEW, classify
from mentis.spine.backup import LOCAL, _default_dir, _now, _stamp

STAGED_FILENAME = ".import-staged.zip"


def extract_archive_bytes(headers: dict, raw_body: bytes) -> bytes:
    """Extract the raw zip archive bytes from various request formats:
    raw binary zip, multipart/form-data, or JSON with base64/path."""
    if not raw_body:
        raise ValueError("empty request body; an uploaded .zip Mentis archive is required")

    # 1. Direct zip binary
    if raw_body.startswith(b"PK\x03\x04"):
        return raw_body

    ctype_header = headers.get("Content-Type") or headers.get("content-type") or ""
    ctype = ctype_header.split(";")[0].strip().lower()

    if ctype in ("application/zip", "application/x-zip-compressed", "application/octet-stream"):
        return raw_body

    # 2. Multipart form data
    if "multipart/form-data" in ctype:
        msg = email.message_from_bytes(
            b"Content-Type: " + ctype_header.encode("latin-1") + b"\r\n\r\n" + raw_body,
            policy=default,
        )
        for part in msg.iter_parts():
            payload = part.get_payload(decode=True)
            if payload and (payload.startswith(b"PK\x03\x04") or (part.get_filename() or "").endswith(".zip")):
                return payload
        raise ValueError("multipart upload did not contain a valid .zip archive part")

    # 3. JSON body
    if ctype == "application/json" or raw_body.strip().startswith((b"{", b"[")):
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"malformed JSON body: {exc}") from exc

        if isinstance(data, dict):
            if "archive" in data and isinstance(data["archive"], str):
                return base64.b64decode(data["archive"])
            if "data" in data and isinstance(data["data"], str):
                return base64.b64decode(data["data"])
            if "path" in data or "archive_path" in data:
                p = data.get("path") or data.get("archive_path")
                if not os.path.isfile(p):
                    raise ValueError(f"archive file not found at {p}")
                with open(p, "rb") as f:
                    return f.read()

        raise ValueError("JSON request must supply 'archive' (base64 string) or 'path'")

    raise ValueError("unrecognized content type; send the .zip archive as application/zip or multipart/form-data")


def _backup_dest_for(corpus) -> str:
    root = os.path.abspath(corpus.root)
    corpus_id = getattr(corpus, "corpus_id", "")
    if not corpus_id:
        try:
            ident = identity_from(corpus)
            corpus_id = ident.get("corpus_id", "corpus")
        except Exception:
            corpus_id = "corpus"
    return os.path.join(_default_dir(root, corpus_id), f"{_stamp(_now())}-{LOCAL}")


def preview_archive(corpus, archive_bytes: bytes) -> dict:
    """Classify the items in the archive against `corpus` without mutating state."""
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(archive_bytes)
        tmp_path = tmp.name

    try:
        export = fmt.read(tmp_path)
        plan = classify(corpus, export)

        rows = plan.rows
        new_items = [
            {"id": r.id, "kind": r.kind, "table": r.table, "reason": r.reason, "fingerprint": r.fingerprint}
            for r in rows if r.state == NEW
        ]
        diverged_items = [
            {"id": r.id, "kind": r.kind, "table": r.table, "reason": r.reason, "blocked_by": r.blocked_by}
            for r in rows if r.state == DIVERGED
        ]
        skipped_items = [
            {"id": r.id, "kind": r.kind, "table": r.table, "reason": r.reason, "blocked_by": r.blocked_by}
            for r in rows if r.state == IDENTICAL or r.blocked_by
        ]

        conflicts_list = [
            {"id": c.id, "type": c.type, "subject": c.subject, "words": c.words, "detail": c.detail, "blocks": c.blocks}
            for c in plan.conflicts
        ]

        # Map entry id -> entry dict from export.entries to give friendly details
        entry_map = {e["id"]: e for e in export.entries if isinstance(e, dict) and "id" in e}
        incoming_convs = []
        incoming_turns = []

        for r in rows:
            if r.kind == "conversation":
                e = entry_map.get(r.id, {})
                incoming_convs.append({
                    "id": r.id,
                    "name": (e.get("body") or {}).get("name") or (e.get("link") or {}).get("name") or r.id,
                    "state": r.state,
                    "reason": r.reason,
                })
            elif r.kind in ("turn", "contribution"):
                e = entry_map.get(r.id, {})
                body = e.get("body") or {}
                text_snip = body.get("text", "")
                if len(text_snip) > 80:
                    text_snip = text_snip[:77] + "..."
                incoming_turns.append({
                    "id": r.id,
                    "text": text_snip,
                    "state": r.state,
                    "reason": r.reason,
                })

        counts = dict(plan.counts)
        counts["new"] = len(new_items)
        counts["skipped"] = len(skipped_items)
        counts["diverged"] = len(diverged_items)
        counts["conversations"] = len(incoming_convs)
        counts["turns"] = len(incoming_turns)

        backup_dest = _backup_dest_for(corpus)

        return {
            "ok": not bool(plan.refused),
            "manifest_sha256": export.manifest_sha256,
            "origin": plan.origin,
            "receiver": plan.receiver,
            "ledger_identical": plan.ledger_identical,
            "counts": counts,
            "new": new_items,
            "skipped": skipped_items,
            "diverged": diverged_items,
            "conversations": incoming_convs,
            "turns": incoming_turns,
            "conflicts": conflicts_list,
            "refused": plan.refused,
            "backup_dest": backup_dest,
            "evidence": plan.evidence,
            "stubs": plan.stubs,
        }
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def stage_archive(corpus, archive_bytes: bytes) -> dict:
    """Verify archive and stage it to `.import-staged.zip` in brain root."""
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp.write(archive_bytes)
        tmp_path = tmp.name

    try:
        export = fmt.read(tmp_path)
        plan = classify(corpus, export)

        if plan.refused:
            raise ExchangeRefused("; ".join(plan.refused))

        staged_path = os.path.join(corpus.root, STAGED_FILENAME)
        tmp_staged = staged_path + ".tmp"
        with open(tmp_staged, "wb") as f:
            f.write(archive_bytes)
        os.replace(tmp_staged, staged_path)

        counts = dict(plan.counts)
        backup_dest = _backup_dest_for(corpus)

        return {
            "ok": True,
            "staged": True,
            "staged_path": staged_path,
            "filename": STAGED_FILENAME,
            "manifest_sha256": export.manifest_sha256,
            "counts": counts,
            "backup_dest": backup_dest,
            "message": "Archive verified and staged for application on next restart.",
        }
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def staging_status(corpus) -> dict:
    """Read status of any staged import in `.import-staged.zip`."""
    staged_path = os.path.join(corpus.root, STAGED_FILENAME)
    if not os.path.isfile(staged_path):
        return {"staged": False}

    try:
        export = fmt.read(staged_path)
        return {
            "staged": True,
            "staged_path": staged_path,
            "size": os.path.getsize(staged_path),
            "manifest_sha256": export.manifest_sha256,
            "origin": export.origin,
            "counts": {
                "entries": len(export.entries),
                "acts": len(export.acts),
                "blobs": len(export.blob_digests),
            },
        }
    except Exception as exc:
        return {
            "staged": True,
            "staged_path": staged_path,
            "size": os.path.getsize(staged_path),
            "error": f"corrupt staged archive: {exc}",
        }


def delete_staged(corpus) -> dict:
    """Remove `.import-staged.zip` if present."""
    staged_path = os.path.join(corpus.root, STAGED_FILENAME)
    if os.path.isfile(staged_path):
        os.remove(staged_path)
        return {"staged": False, "deleted": True}
    return {"staged": False, "deleted": False}


def handle_import_request(st, path: str, headers: dict, raw_body: bytes) -> tuple[int, dict]:
    """Handler for import requests with binary/multipart or custom payloads."""
    corpus = st.corpus
    try:
        if path == "/api/exchange/import/preview":
            archive_bytes = extract_archive_bytes(headers, raw_body)
            result = preview_archive(corpus, archive_bytes)
            code = 200 if result.get("ok", True) else 400
            return code, result

        if path == "/api/exchange/import/stage":
            archive_bytes = extract_archive_bytes(headers, raw_body)
            result = stage_archive(corpus, archive_bytes)
            return 200, result

        return 404, {"error": f"unknown import path: {path}"}
    except ExchangeRefused as exc:
        return 400, {"error": str(exc), "kind": "ExchangeRefused"}
    except ValueError as exc:
        return 400, {"error": str(exc), "kind": "ValueError"}
    except Exception as exc:
        return 500, {"error": f"internal error during exchange import: {exc}"}


def routes(st, path: str, query: dict, body: dict | None, method: str, presented=None):
    """Route handler for JSON / GET / DELETE requests routed through Mentis _routes."""
    corpus = st.corpus
    if path == "/api/exchange/import/stage" and method == "GET":
        return staging_status(corpus)

    if path == "/api/exchange/import/stage" and method == "DELETE":
        return delete_staged(corpus)

    if path == "/api/exchange/import/preview" and method == "POST":
        try:
            raw_body = json.dumps(body).encode("utf-8") if isinstance(body, dict) else (body or b"")
            headers = {"Content-Type": "application/json"}
            archive_bytes = extract_archive_bytes(headers, raw_body)
            result = preview_archive(corpus, archive_bytes)
            return result
        except ExchangeRefused as exc:
            return {"error": str(exc), "kind": "ExchangeRefused"}

    if path == "/api/exchange/import/stage" and method == "POST":
        try:
            raw_body = json.dumps(body).encode("utf-8") if isinstance(body, dict) else (body or b"")
            headers = {"Content-Type": "application/json"}
            archive_bytes = extract_archive_bytes(headers, raw_body)
            result = stage_archive(corpus, archive_bytes)
            return result
        except ExchangeRefused as exc:
            return {"error": str(exc), "kind": "ExchangeRefused"}

    raise ValueError(f"unknown method or path: {method} {path}")
