"""Raw reads over ONE read transaction, shared by export and preview.

Both sides read rows exactly as the store holds them -- with `seq` and the
chain hash, which an export carries as evidence -- and never through a layer
that might write (opening `Conversations` defines missing vocabulary). The
transaction is a pooled `query_only` connection taken inside
`reading_beside_writer()`, so every statement answers about one committed
moment and nothing can be appended through it.
"""

from __future__ import annotations

import contextlib
import json

from mentis.spine import migrations, seed
from mentis.spine import store as _store


@contextlib.contextmanager
def one_read(st):
    """A `Reader` over one read transaction of the Store `st`."""
    with _store.reading_beside_writer():
        with st._reading() as conn:
            yield Reader(conn)


def store_of(handle):
    """The spine Store behind a Store or a Corpus (`seam.Corpus`)."""
    return getattr(handle, "_store", handle)


def record(row) -> dict:
    """An entry row as the record holds it, plus its place on its own chain
    (`origin_seq`, `origin_hash`), which is evidence and never identity."""
    out = _store._inflate(row)
    out["origin_seq"] = row["seq"]
    out["origin_hash"] = row["hash"]
    return out


def act_record(row) -> dict:
    d = dict(row)
    seq, h = d.get("seq"), d.get("hash")
    _, act = _store._act_of(row)
    act["origin_seq"] = seq
    act["origin_hash"] = h
    return act


class Reader:
    """Reads by SQL on one connection. Read-only by construction: the
    connection is `query_only`."""

    def __init__(self, conn):
        self.conn = conn
        self._roles: dict = {}

    def _q(self, sql, args=()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, args)]

    # -- identity and schema ------------------------------------------------

    def corpus_id(self) -> str:
        return self.conn.execute("SELECT corpus_id FROM corpus").fetchone()[0]

    def ledger(self) -> list[dict]:
        """The schema ledger, row for row: what both Brains must share."""
        if "schema_migration" not in migrations._tables(self.conn):
            return []
        return self._q("SELECT seq, id, from_version, to_version, checksum "
                       "FROM schema_migration ORDER BY seq")

    def heads(self) -> dict:
        return migrations._heads(self.conn)

    # -- entries ------------------------------------------------------------

    def entries(self, ids) -> dict:
        ids = [i for i in dict.fromkeys(ids) if isinstance(i, str) and i]
        if not ids:
            return {}
        return {r["id"]: r for r in self._q(
            "SELECT * FROM entry WHERE id IN (SELECT value FROM json_each(?)) "
            "ORDER BY seq", (json.dumps(ids),))}

    def links(self, *, relations=None, to_any=None, frm_any=None) -> list:
        where, args = ["link_relation IS NOT NULL"], []
        if relations is not None:
            relations = list(dict.fromkeys(relations))
            if not relations:
                return []
            where.append("link_relation IN (SELECT value FROM json_each(?))")
            args.append(json.dumps(relations))
        for column, wanted in (("link_to", to_any), ("link_from", frm_any)):
            if wanted is None:
                continue
            wanted = list(dict.fromkeys(wanted))
            if not wanted:
                return []
            where.append(f"{column} IN (SELECT value FROM json_each(?))")
            args.append(json.dumps(wanted))
        return self._q("SELECT * FROM entry WHERE " + " AND ".join(where)
                       + " ORDER BY seq", tuple(args))

    def nodes_of(self, kind) -> list:
        return self._q("SELECT * FROM entry WHERE def_name = ? AND "
                       "family = 'entry' AND link_relation IS NULL "
                       "ORDER BY seq", (kind,))

    # -- definitions --------------------------------------------------------

    def role(self, role) -> str | None:
        """Which relation carries this substrate role, read from the data."""
        if role not in self._roles:
            got = self.conn.execute(
                "SELECT json_extract(body, '$.relation') FROM entry "
                "WHERE family = 'definition' "
                "AND json_extract(body, '$.substrate_role') = ? "
                "ORDER BY seq LIMIT 1", (role,)).fetchone()
            self._roles[role] = got[0] if got else None
        return self._roles[role]

    def supersedes(self) -> str:
        return self.role(seed.SUPERSEDES) or seed.SUPERSEDES

    def establishes(self) -> str:
        return self.role(seed.ESTABLISHES) or seed.ESTABLISHES

    def definitions_named(self, name) -> list:
        return self._q("SELECT * FROM entry WHERE family = 'definition' AND "
                       "def_name = ? ORDER BY seq", (name,))

    # -- acts ---------------------------------------------------------------

    def acts(self, where: str, args=()) -> list:
        return self._q(f"SELECT * FROM operational WHERE {where} ORDER BY seq",
                       tuple(args))

    def acts_by_ids(self, ids) -> dict:
        ids = [i for i in dict.fromkeys(ids) if isinstance(i, str) and i]
        if not ids:
            return {}
        return {r["id"]: r for r in self.acts(
            "id IN (SELECT value FROM json_each(?))", (json.dumps(ids),))}
