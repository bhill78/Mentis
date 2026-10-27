"""Relational Sources: what every SQL database connector shares.

A relational connector is a dialect module, passed here as `dialect`, the
way `lifecycle` takes its connector module: its globals are read at call
time, so stores, tunables and test seams stay owned by the dialect. The core
holds what is not specific to one database: table scope selection, the closed
per-table rules and their compilation to parameterised SQL, row identity, row
and table key encoding, foreign-key links, sensitive-column detection and
consent, typed values, the survey that emits schema, row and keyless-snapshot
observations, field digests, compare, and the plan/preview/sweep glue.

What every dialect, and so every relational Source, guarantees:

- No SQL supplied by the caller is executed. Per-table rules are a closed
  structure compiled here to parameterised SQL: identifiers are quoted by the
  dialect, and values are always bound, never written into the statement.
- Every value, including keys, samples and acquired rows, is read from the
  private consistent capture the dialect takes (`_capture`), never from the
  live source. Before column consent, only the catalog, row counts and sizes
  are read from the live source.
- No value of a flagged (secret-looking) column is selected until each flagged
  column has been answered include or exclude.
- A reason (why a table was not examined) never quotes a value. It is shown in
  the preview, hashed into the plan and recorded on the sweep act. A dialect's
  `_reason` keeps only its database's own messages, which name schema, syntax
  or state, and for anything raised on the client side says only the kind of
  failure (`value_free`).

The dialect contract is `DIALECT`. The catalog a dialect returns uses the row
shapes of SQLite's catalog PRAGMAs, which the schema observation records as
they are: a column is (cid, name, type, not_null, default, pk_position,
hidden); a foreign key is (id, seq, table, from, to, on_update, on_delete,
match); an index is {name, unique, partial, parts}, each part (seqno, cid,
name, desc, collation, key).
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import pathlib
import re
import time
import uuid
from fnmatch import fnmatchcase
from urllib.parse import quote

from mentis.sources import (PlanChanged, Refused, bindings, canonical, diff,
                            effective_scope, latest, prepare, OVER_HELD_LIMIT)
from mentis.spine import held

#: What a dialect module provides. The core reaches each through the module,
#: so a dialect (or a test) can substitute any of them.
DIALECT = {
    # Identity and words.
    "CONNECTOR": "the connector name in declarations and plan bases",
    "LABEL": "the database's name as refusals say it",
    "PAYLOAD_TYPE": "the observations' payload type",
    "FK_SYNTAX": "the syntax named on a foreign-key relation",
    "CAPTURE": "what the consistent capture is, as previews and sweeps say it",
    "VIRTUAL_REASON": "why a virtual or internal table is not read",
    "BIND_KIND": "the binding kind",
    # Database access.
    "DB_ERROR": "the driver's base error class",
    "QUERY_ERROR": "the driver's error for a failed or interrupted statement",
    "_open": "a read-only connection to a source or its capture",
    "_capture": "take, or re-verify, the consistent private capture",
    "_catalog": "tables, columns, keys, unique indexes, foreign keys; virtual and internal tables marked",
    "_on_progress": "install, or with None clear, a callback run while a statement executes",
    "_interrupted": "whether an error is a statement the callback interrupted",
    "_reason": "an error as a reason that never quotes a value",
    # SQL spelling.
    "_q": "quote an identifier",
    "_param": "the placeholder for bound parameter n, from 1",
    "_limit": "a statement limited to n rows",
    "_subquery": "a statement as a FROM-clause subquery",
    "_fold": "identifier case folding, as the database resolves names",
    "NOT_EQUAL": "null-safe inequality",
    "LIKE_ESCAPE": "the clause naming backslash as LIKE's escape",
    "typed": "a driver value as a typed value",
    # Seams the core calls back through.
    "_identity": "the identity columns of a table, or none",
    "row_key": "an object key for a row",
    "declaration": "this connector's declaration of a collection",
    "source_of": "the source id of a collection",
    "checked_options": "the checked per-table rules",
    "_patterns": "checked scope patterns",
    "_plan_id": "a plan id",
    "_basis": "a collection plan's basis",
    "_draft_basis": "a draft plan's basis",
    "_consent": "column and partial decisions checked against their preview",
    "_ready": "a collection's declaration and binding",
    "_abandon_stage": "drop a stage and its private bytes",
    "_forget_superseded": "drop earlier stages once a new one is staged",
    "_STAGES": "the dialect's stages",
    "STAGE_TTL": "how long a stage lives, in seconds",
    "STAGE_MEMORY_BYTES": "staged bytes kept in memory rather than on disk",
    "INSPECT_SECONDS": "the counting budget of an inspection",
    "SAMPLE_SECONDS": "the budget of a sample",
}


def missing(dialect):
    """The contract names a dialect module does not provide."""
    return sorted(n for n in DIALECT if not hasattr(dialect, n))


def _life():
    from mentis.sources import lifecycle
    return lifecycle


# -- names, keys and values ---------------------------------------------------

SECRET = re.compile(r"password|passwd|secret|token|credential|api[_-]?key|private[_-]?key|ssn|social[_-]?security", re.I)


def selected(scope, key):
    table = key.split("/", 1)[0]
    return (any(fnmatchcase(table, p) for p in scope["include"])
            and not any(fnmatchcase(table, p) for p in scope["exclude"]))


def table_key(name):
    # Preserve Unicode exactly: NFC folding merges distinct table names.
    return quote(name, safe="") if name else "%00"


def typed(value):
    if value is None:
        return ["null"]
    if isinstance(value, int):
        return ["integer", str(value)]
    if isinstance(value, float):
        return ["real", value.hex()]
    if isinstance(value, bytes):
        return ["blob", base64.b64encode(value).decode("ascii")]
    return ["text", value]


def row_key(table, values, typed=typed):
    return table_key(table) + "/k-" + quote(canonical([typed(v) for v in values]), safe="")


def consent_key(key, column):
    return key + "/" + quote(column, safe="")


def key_hash(key):
    return hashlib.blake2b(key.encode("utf-8"), digest_size=12).digest()


def field_digests(fields):
    return {c: hashlib.sha256(canonical(v).encode("utf-8")).hexdigest()[:16] for c, v in fields.items()}


def value_free(exc):
    """A client-side error, whose message can quote what was read, said only
    by its kind."""
    return ("text that is not valid UTF-8" if isinstance(exc, UnicodeError)
            else f"the row could not be read ({type(exc).__name__})")


# -- closed per-table rules ---------------------------------------------------
# Values are bound separately; identifiers are quoted by the dialect.

OPS = ('equals', 'not_equals', 'contains', 'starts_with', 'after', 'before',
       'is_empty', 'not_empty')
NO_VALUE = ('is_empty', 'not_empty')


def _name(value):
    if not isinstance(value, str) or '\0' in value:
        raise Refused('table and column names must be text without NUL')
    return value


def _column(value):
    _name(value)
    if SECRET.search(value):
        raise Refused('secret-looking columns must be decided through column consent')
    return value


def checked_value(value):
    if not isinstance(value, list) or len(value) != 2 or not isinstance(value[1], str):
        raise Refused('a rule value must be typed text, integer or real')
    kind, raw = value
    try:
        if kind == 'text' and len(raw) <= 1000:
            return [kind, raw]
        if kind == 'integer' and re.fullmatch(r'[+-]?[0-9]+', raw):
            number = int(raw)
            if -(2**63) <= number < 2**63:
                return [kind, str(number)]
        if kind == 'real':
            number = float.fromhex(raw) if '0x' in raw.lower() else float(raw)
            if math.isfinite(number):
                return [kind, number.hex()]
    except (ValueError, OverflowError):
        pass
    raise Refused('invalid or oversized rule value')


def checked_rules(rules):
    if not isinstance(rules, dict) or set(rules) - {'omit', 'rows'}:
        raise Refused('table rules take only omit and rows')
    omit, rows = rules.get('omit', []), rules.get('rows', [])
    if not isinstance(omit, list) or len(omit) > 500:
        raise Refused('omit must list at most 500 unique columns')
    omit = [_column(c) for c in omit]
    if len(set(omit)) != len(omit):
        raise Refused('omit must list unique columns')
    if not isinstance(rows, list) or len(rows) > 20:
        raise Refused('rows must list at most 20 rules')
    clean = []
    for rule in rows:
        if not isinstance(rule, dict) or set(rule) - {'column', 'op', 'value'}:
            raise Refused('a row rule takes only column, op and value')
        column, op = _column(rule.get('column')), rule.get('op')
        if op not in OPS:
            raise Refused('unknown row operator')
        r = {'column': column, 'op': op}
        if op in NO_VALUE:
            if 'value' in rule:
                raise Refused('this operator takes no value')
        else:
            r['value'] = checked_value(rule.get('value'))
            if op in ('contains', 'starts_with') and r['value'][0] != 'text':
                raise Refused('contains and starts with need text')
        clean.append(r)
    return {'omit': sorted(omit), 'rows': clean}


def checked_options(options, *, base=None, label):
    if options is None:
        options = base or {}
    if not isinstance(options, dict) or set(options) - {'tables'}:
        raise Refused(f'{label} takes table rules, not SQL or mapping options')
    tables = options.get('tables', {})
    if not isinstance(tables, dict) or len(tables) > 200:
        raise Refused('tables must map at most 200 table names to rules')
    clean = {}
    for name, rules in tables.items():
        _name(name)
        r = checked_rules(rules)
        if r['omit'] or r['rows']:
            clean[name] = r
    return {'tables': clean} if clean else {}


def untyped(value):
    kind, raw = value
    return int(raw) if kind == 'integer' else float.fromhex(raw) if kind == 'real' else raw


def compile_select(dialect, table, columns, rows):
    rows = checked_rules({'rows': rows})['rows']
    if not columns:
        raise Refused('at least one column must be taken')
    q = lambda name: dialect._q(_name(name))
    sql = 'SELECT ' + ','.join(map(q, columns)) + ' FROM ' + q(table)
    clauses, params = [], []
    for r in rows:
        c, op = q(r['column']), r['op']
        if op in NO_VALUE:
            clauses.append(f'({c} IS NULL OR {c} = \'\')' if op == 'is_empty'
                           else f'({c} IS NOT NULL AND {c} <> \'\')')
            continue
        value = untyped(r['value'])
        if op in ('contains', 'starts_with'):
            value = value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            value = ('%' if op == 'contains' else '') + value + '%'
        params.append(value)
        operator = {'equals': '=', 'not_equals': dialect.NOT_EQUAL, 'after': '>', 'before': '<',
                    'contains': 'LIKE', 'starts_with': 'LIKE'}[op]
        clauses.append(f'{c} {operator} {dialect._param(len(params))}'
                       + (dialect.LIKE_ESCAPE if operator == 'LIKE' else ''))
    if clauses:
        sql += ' WHERE ' + ' AND '.join('(' + c + ')' for c in clauses)
    return sql, params


def explain(dialect, table, columns, rows):
    sql, params = compile_select(dialect, table, columns, rows)
    # The parameter display describes actual bound values, including LIKE escaping.
    return {'sql': sql, 'params': [{'n': n, 'value': dialect.typed(v)} for n, v in enumerate(params, 1)]}


def sentence(table, rule):
    op = rule['op']
    labels = {'equals': 'is', 'not_equals': 'is not', 'contains': 'contains',
              'starts_with': 'starts with', 'is_empty': 'is empty', 'not_empty': 'is not empty',
              'after': 'after', 'before': 'before'}
    label = labels[op]
    if op in ('after', 'before') and rule['value'][0] in ('integer', 'real'):
        label = 'more than' if op == 'after' else 'less than'
    return rule['column'] + ' ' + label + ('' if op in NO_VALUE else ' ' + repr(untyped(rule['value'])))


# -- inspection ---------------------------------------------------------------

def overview(dialect, db, catalog, sizes, progress):
    """The tables of an inspection, read from the live source's catalog:
    counts within `INSPECT_SECONDS`, keys, links and the dialect's sizes.
    No value is read."""
    end = time.monotonic() + dialect.INSPECT_SECONDS
    def check():
        progress.check()
        return int(time.monotonic() > end)
    dialect._on_progress(db, check, 1000)
    tables = []
    for name, table in catalog.items():
        progress.check()
        rows, state = None, 'virtual' if table['virtual'] else 'counted'
        if not table['virtual'] and not table.get('error'):
            try:
                if time.monotonic() <= end:
                    rows = db.execute('SELECT count(*) FROM ' + dialect._q(name)).fetchone()[0]
            except dialect.DB_ERROR:
                pass
            if rows is None:
                progress.check()
                state = 'too slow to count'
        columns = table.get('columns', [])
        parents = []
        for fk in table.get('foreign_keys', []):
            parent = next((n for n in catalog if dialect._fold(n) == dialect._fold(fk[2])), fk[2])
            parents.append({'table': parent, 'column': fk[3], 'target': fk[4]})
        pk = [c[1] for c in sorted(columns, key=lambda c: c[5]) if c[5]]
        candidates = ([pk] if pk else []) + [[p[2] for p in idx['parts'] if p[5]]
            for idx in table.get('indexes', []) if idx['unique'] and not idx['partial'] and all(p[2] is not None for p in idx['parts'] if p[5])]
        amount, basis = sizes.get(name, (None, 'unavailable'))
        tables.append({'name': name, 'key': table_key(name), 'internal': table['virtual'],
            'virtual': table['virtual'], 'rows': rows, 'rows_state': state, 'bytes': amount, 'bytes_basis': basis,
            'columns': [{'name': c[1], 'type': c[2], 'pk': c[5], 'secret': bool(SECRET.search(c[1])), 'hidden': c[6]} for c in columns],
            'parents': parents, 'children': [], 'key_candidates': candidates})
    dialect._on_progress(db, None, 0)
    for table in tables:
        table['children'] = [t['name'] for t in tables if any(p['table'] == table['name'] for p in t['parents'])]
    return tables


# -- identity and links -------------------------------------------------------

def identity(dialect, db, table, allowed):
    """The primary key, else the first unique index (by name) whose columns
    hold no NULL and no duplicate on this capture. Secret-looking or
    unconsented columns never name rows."""
    q = dialect._q
    name = table["name"]
    pk = [c[1] for c in sorted(table["columns"], key=lambda c: c[5]) if c[5]]
    candidates = [pk] if pk else []
    if not pk:
        candidates += [[p[2] for p in idx["parts"] if p[5]]
                       for idx in sorted(table["indexes"], key=lambda i: i["name"])
                       if idx["unique"] and not idx["partial"]]
    for cols in candidates:
        if not cols or any(c is None or c not in allowed or SECRET.search(c) for c in cols):
            continue
        fields = ",".join(q(c) for c in cols)
        # A UNIQUE index can allow multiple NULLs; those indexes cannot name rows.
        if db.execute(dialect._limit("SELECT 1 FROM " + q(name) + " WHERE " + " OR ".join(q(c) + " IS NULL" for c in cols), 1)).fetchone():
            continue
        if db.execute(dialect._limit("SELECT 1 FROM " + q(name) + " GROUP BY " + fields + " HAVING count(*)>1", 1)).fetchone():
            continue
        return cols
    return []


def foreign_links(dialect, db, table, row, catalog, identities, allowed):
    q = dialect._q
    def spelling(authored, names):
        # Prefer the exact spelling, then the database's own folding: a wider
        # (Unicode) fold would merge distinct tables whose keys are exact.
        return next((n for n in names if n == authored),
                    next((n for n in names if dialect._fold(n) == dialect._fold(authored)), authored))
    groups = {}
    for fk in table["foreign_keys"]:
        groups.setdefault(fk[0], []).append(fk)
    out = []
    for fks in groups.values():
        fks.sort(key=lambda f: f[1])
        target = fks[0][2]
        # Identifiers may resolve case-insensitively; keys keep true spelling.
        target = spelling(target, catalog)
        src = [spelling(f[3], row) for f in fks]
        if any(c not in row or row[c] is None for c in src):
            continue
        rel = {"rel": "links-to", "syntax": dialect.FK_SYNTAX, "authored": ",".join(src),
               "resolved": None, "resolution": "unresolved"}
        identity = identities.get(target)
        if identity:
            dst = [spelling(f[4], allowed[target]) if f[4] is not None else None for f in fks]
            if any(c is None for c in dst):
                dst = [c[1] for c in sorted(catalog[target]["columns"], key=lambda c: c[5]) if c[5]]
            if len(dst) == len(src) and all(c in allowed[target] and not SECRET.search(c) for c in dst):
                hits = db.execute("SELECT " + ",".join(q(c) for c in identity) + " FROM " + q(target) +
                                  " WHERE " + " AND ".join(q(c) + "=" + dialect._param(n) for n, c in enumerate(dst, 1)),
                                  [row[c] for c in src]).fetchmany(2)
                if len(hits) == 1:
                    rel.update(resolved=dialect.row_key(target, hits[0]), resolution="in-collection")
        out.append(rel)
    return out


# -- survey -------------------------------------------------------------------

def survey(dialect, corpus, scope, root, *, stage_dir, budget, progress=None,
           decisions=None, partial=False, snapshot=None):
    progress = progress or _life()._Quiet()
    q = dialect._q
    path, captured = dialect._capture(root, stage_dir, budget, progress, snapshot)
    s = {"within": "", "observations": [], "withheld": {}, "refused": [],
         "unexamined": [], "visible": [], "staged": set(), "in_memory": {},
         "newly_written_digests": set(), "stage_dir": str(stage_dir),
         "snapshot": (str(path), captured), "capture_semantics": dialect.CAPTURE,
         "coverage": {}, "sensitive_columns": [], "sensitive_decisions": decisions or {},
         "partial_confirmed": partial, "source_keys": {}}
    used = path.stat().st_size
    memory = budget.get("memory", 0)
    def emit(key, payload, relations, native):
        nonlocal used, memory
        data = canonical(payload).encode("utf-8")
        if len(data) > held.MAX_BYTES:
            s["withheld"][key] = OVER_HELD_LIMIT
            return
        digest = hashlib.sha256(data).hexdigest()
        if not held.has(corpus.root, digest) and digest not in s["staged"]:
            used += len(data)
            if used > budget["room"]:
                raise Refused(_life()._over_budget(dialect, budget, used))
            if memory + len(data) <= dialect.STAGE_MEMORY_BYTES:
                s["in_memory"][digest] = data
                memory += len(data)
            else:
                (stage_dir / digest).write_bytes(data)
            s["staged"].add(digest)
        s["observations"].append({"object": key, "state": "present", "retention": "held",
                                  "digest": digest, "size": len(data),
                                  "payload_type": dialect.PAYLOAD_TYPE,
                                  "encoding": {"text": True, "encoding": "utf-8"},
                                  "relations": relations, "native": native})
    db = dialect._open(path)
    dialect._on_progress(db, lambda: progress.check() or 0, 10000)
    try:
        try:
            catalog = dialect._catalog(db)
        except dialect.DB_ERROR:
            progress.check()
            raise
        if any(t.get("error") for t in catalog.values()):
            # A cancel during any table's catalog read, selected or not, came
            # back as that table's "interrupted": it is the owner's cancel.
            progress.check()
        identities, allowed = {}, {}
        for name, t in catalog.items():
            key = table_key(name)
            if not selected(scope, key):
                s["visible"].append(key)
                continue
            if t["virtual"] or t.get("error"):
                s["unexamined"].append({"path": key, "reason": t.get("error") or dialect.VIRTUAL_REASON})
                s["coverage"][key] = "not_examined"
                continue
            columns = [c[1] for c in t["columns"] if c[6] != 1]
            flagged = [c for c in columns if SECRET.search(c)]
            for col in flagged:
                s["sensitive_columns"].append({"path": consent_key(key, col), "table": name,
                                                "column": col, "decision": (decisions or {}).get(consent_key(key, col))})
            allowed[name] = [c for c in columns if c not in flagged or
                             (decisions or {}).get(consent_key(key, c)) == "include"]
            # No flagged values are selected until each decision is answered.
            if any((decisions or {}).get(consent_key(key, c)) is None for c in flagged):
                s["coverage"][key] = "consent_pending"
                continue
            try:
                identities[name] = dialect._identity(db, t, allowed[name])
            except (dialect.DB_ERROR, UnicodeError) as exc:
                progress.check()  # an owner's cancel arrives as "interrupted"
                s["unexamined"].append({"path": key, "reason": dialect._reason(exc)})
                s["coverage"][key] = "not_examined"
        for name, identity in identities.items():
            t, key = catalog[name], table_key(name)
            progress.check()
            progress.folder(key)
            rules = scope.get("options", {}).get("tables", {}).get(name, {})
            omit, filters = rules.get("omit", []), rules.get("rows", [])
            names = {c[1] for c in t["columns"]}
            absent = next((c for c in [*omit, *(r["column"] for r in filters)] if c not in names), None)
            reason = (f"a rule names column {absent}, which the table no longer has" if absent else
                      "this table has no key, so it is taken whole; columns and rows can't be narrowed" if not identity and (omit or filters) else None)
            if reason:
                s["unexamined"].append({"path": key, "reason": reason})
                s["coverage"][key] = "not_examined"
                continue
            for c in identity:
                if c in omit:
                    raise Refused(f"{c} is the key Mentis uses to recognise each row of {name}; it can't be left out")
            cols = [c for c in allowed[name] if c not in omit]
            excluded = [c[1] for c in t["columns"] if c[1] not in cols and c[6] != 1]
            table_observations = len(s["observations"])
            try:
                schema = {"table": name, "columns": [
                    {"name": c[1], "type": c[2], "not_null": bool(c[3]),
                     "default": None if SECRET.search(c[1]) else c[4],
                     "pk": c[5], "hidden": c[6]} for c in t["columns"]],
                    "indexes": t["indexes"], "foreign_keys": t["foreign_keys"],
                    "identity": identity, "identity_semantics": "source-key slot; lifetime continuity not claimed"}
                emit(key + "/@schema", schema, [], {"kind": "schema", "table": name})
                if filters and identity:
                    s["source_keys"][key] = {key_hash(dialect.row_key(name, values)) for values in
                        db.execute("SELECT " + ",".join(q(c) for c in identity) + " FROM " + q(name))}
                sql, params = compile_select(dialect, name, cols, filters) if cols else ("SELECT 1 FROM " + q(name), [])
                rows = db.execute(sql, params)
                snapshots = []
                count = 0
                oversized = False
                for values in rows:
                    progress.check()
                    row = dict(zip(cols, values))
                    payload = {"fields": {c: dialect.typed(v) for c, v in row.items() if v is not None},
                               "withheld_fields": excluded}
                    if not identity:
                        snapshots.append(payload)
                        count += len(canonical(payload).encode("utf-8"))
                        if count > held.MAX_BYTES:
                            s["withheld"][key + "/snapshot"] = OVER_HELD_LIMIT
                            oversized = True
                            break
                        continue
                    relations = foreign_links(dialect, db, t, row, catalog, identities, allowed)
                    emit(dialect.row_key(name, [row[c] for c in identity]), payload, relations,
                         {"kind": "row", "table": name, "identity": identity,
                          "withheld_fields": excluded, "field_digests": field_digests(payload["fields"])})
                    progress.read(1)
                if not identity and not oversized:
                    # Stable ordering without assigning content identity; duplicates remain.
                    snapshots.sort(key=canonical)
                    emit(key + "/snapshot", {"rows": snapshots, "withheld_fields": excluded}, [],
                         {"kind": "snapshot", "table": name, "identity": []})
                s["coverage"][key] = "complete"
            except (dialect.DB_ERROR, UnicodeError) as exc:
                # A cancel raised in the progress callback reaches here as the
                # driver's "interrupted": it is the owner's cancellation, not
                # a table that could not be read.
                progress.check()
                del s["observations"][table_observations:]
                s["unexamined"].append({"path": key, "reason": dialect._reason(exc)})
                s["coverage"][key] = "not_examined"
        s["can_confirm"] = (all(c["decision"] in ("include", "exclude") for c in s["sensitive_columns"])
                            and (not s["unexamined"] or partial))
        known = {table_key(n) for n in catalog}
        def examined(obj):
            if not selected(scope, obj):
                return False
            top = obj.split("/", 1)[0]
            if top in known and s["coverage"].get(top) != "complete":
                return False
            keys = s["source_keys"].get(top)
            return key_hash(obj) not in keys if keys is not None and "/k-" in obj else True
        s["examined"] = examined
        s["compare"] = compare_for(corpus)
        return s
    finally:
        db.close()


def compare_for(corpus):
    def compare_(was, new):
        return compare(was, new, corpus=corpus)
    return compare_


def compare(was, new, *, corpus=None):
    """A row whose withheld columns changed and whose other fields did not:
    "kept" when more is now withheld, "widened" when less is."""
    wn, nn = was.get("native") or {}, new.get("native") or {}
    if wn.get("kind") != "row" or nn.get("kind") != "row" or was.get("relations") != new.get("relations"):
        return None
    ww, nw = set(wn.get("withheld_fields") or ()), set(nn.get("withheld_fields") or ())
    if ww == nw:
        return None
    wd, nd = wn.get("field_digests"), nn.get("field_digests")
    if nd is None:
        return None
    if wd is None:
        if corpus is None:
            return None
        try:
            wd = field_digests(json.loads(held.read(corpus.root, was["digest"]))["fields"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
    both = (set(wd) | set(nd) | ww | nw) - ww - nw
    if any(wd.get(c) != nd.get(c) for c in both):
        return None
    return "kept" if nw > ww else "widened"


# -- sample -------------------------------------------------------------------

def sample(dialect, corpus, plan, table, rules=None):
    """Twenty rows of one table, from the preview's private capture, with the
    acquisition SELECT that would run. Secret values are always masked."""
    q = dialect._q
    stage = dialect._STAGES.get((corpus.corpus_id, plan))
    if not stage or time.time() - stage["at"] > dialect.STAGE_TTL:
        raise PlanChanged("preview again")
    path = stage["survey"]["snapshot"][0]
    if not pathlib.Path(path).is_file():
        raise PlanChanged("preview again")
    rules = checked_rules({} if rules is None else rules)
    db = dialect._open(path)
    try:
        end = time.monotonic() + dialect.SAMPLE_SECONDS
        catalog = dialect._catalog(db)
        if table not in catalog or not selected(stage['scope'], table_key(table)):
            raise Refused('choose a table in this preview')
        t = catalog[table]
        if t['virtual'] or t.get('error'):
            raise Refused('virtual or unreadable table cannot be sampled')
        columns = [c for c in t['columns'] if c[6] != 1]
        names = [c[1] for c in columns]
        for name in [*rules['omit'], *(r['column'] for r in rules['rows'])]:
            if name not in names:
                raise Refused(f'a rule names column {name}, which the table no longer has')
        ordinary = [c for c in names if not SECRET.search(c)]
        # Identity validation also scans rows. Include it in the sample's
        # budget rather than spending an unbounded interval before counting.
        dialect._on_progress(db, lambda: int(time.monotonic() > end), 1000)
        try:
            identity = dialect._identity(db, t, ordinary)
        except dialect.QUERY_ERROR as exc:
            raise Refused('too slow to identify rows on this snapshot; preview again' if dialect._interrupted(exc) else dialect._reason(exc)) from None
        if not identity and (rules['omit'] or rules['rows']):
            raise Refused("this table has no key, so it is taken whole; columns and rows can't be narrowed")
        for name in identity:
            if name in rules['omit']:
                raise Refused(f"{name} is the key Mentis uses to recognise each row of {table}; it can't be left out")
        decisions = stage['survey']['sensitive_decisions']
        taken = [c for c in names if (c not in rules['omit'] and
                 (not SECRET.search(c) or decisions.get(consent_key(table_key(table), c)) == 'include'))]
        # Secret values are never needed to render a sample, but run.sql is
        # the actual acquisition SELECT. Mask them before constructing output.
        run = explain(dialect, table, taken, rules['rows']) if taken else {'sql': 'SELECT 1 FROM '+q(table), 'params': []}
        sql, params = compile_select(dialect, table, taken, rules['rows']) if taken else (run['sql'], [])
        dialect._on_progress(db, lambda: int(time.monotonic() > end), 1000)
        values, matching, total, note = [], None, None, None
        try:
            total = db.execute('SELECT count(*) FROM '+q(table)).fetchone()[0]
            values = db.execute(sql, params).fetchmany(20)
            # Reuse precisely the compiler's WHERE clause and bindings.
            matching = db.execute('SELECT count(*) FROM '+dialect._subquery(sql), params).fetchone()[0]
        except dialect.QUERY_ERROR as exc:
            if not dialect._interrupted(exc):
                raise Refused(dialect._reason(exc)) from None
            note = 'too slow to count on this snapshot'
        def cell(name, value):
            if SECRET.search(name):
                return '•'*8
            if isinstance(value, bytes):
                return f'blob · {len(value)} bytes'
            return value[:200] + ('…' if len(value)>200 else '') if isinstance(value, str) else value
        output = []
        for row in values:
            mapped = dict(zip(taken, row))
            output.append([cell(c, mapped.get(c)) for c in names])
        metadata = []
        for c in columns:
            name = c[1]
            storage = [] if name not in taken or SECRET.search(name) else [row[taken.index(name)] for row in values if row[taken.index(name)] is not None]
            kind = ('blob' if storage and isinstance(storage[0], bytes) else 'integer' if storage and isinstance(storage[0], int) else
                    'real' if storage and isinstance(storage[0], float) else 'text' if storage else 'null')
            metadata.append({'name': name, 'type': c[2], 'typeof': kind, 'key': name in identity,
                             'secret': bool(SECRET.search(name)), 'omitted': name not in taken})
        estimate = int(sum(len(canonical(r).encode('utf-8')) for r in output) / max(1,len(output)) * matching) if matching is not None else None
        return {'columns': metadata, 'rows': output, 'matching': matching, 'total': total,
                'matching_note': note, 'bytes_estimate': estimate, 'run': run}
    finally:
        db.close()


# -- plan, preview and sweep glue ---------------------------------------------
# The hooks `lifecycle.plan` and `lifecycle.sweep` call on a connector.

def scope_view(scope):
    return {"include": scope["include"], "exclude": scope["exclude"], "options": scope["options"]}


def proposed(dialect, eff, scope):
    if scope is None:
        return eff
    return {**eff, "include": dialect._patterns(scope.get("include"), eff["include"]),
            "exclude": dialect._patterns(scope.get("exclude"), eff["exclude"]),
            "options": dialect.checked_options(scope.get("options"), base=eff.get("options", {}))}


def basis(dialect, collection, decl, bnd, s, scope):
    return {"connector": dialect.CONNECTOR, "collection": collection,
            "binding": bnd["binding"], "snapshot": s["snapshot"][1],
            "consent": s["sensitive_decisions"], "partial": s["partial_confirmed"],
            "options": scope["options"]}


def draft_basis(dialect, stage):
    return {"connector": dialect.CONNECTOR, "draft": stage["draft"], "name": stage["name"],
            "snapshot": stage["survey"]["snapshot"][1],
            "consent": stage["survey"]["sensitive_decisions"],
            "partial": stage["survey"]["partial_confirmed"], "options": stage["scope"]["options"]}


def preview_result(dialect, corpus, s, d, pid, changed):
    out = _life()._preview(corpus, s, d, pid=pid, changed=changed)
    # A relational Source admits a schema object per table as well as rows.
    # The wizard's row counters exclude these metadata objects; admissions
    # remain intact.
    out['counts']['schema_new'] = sum(1 for o, a, _ in d['admit'] if a == 'new' and o['native']['kind'] == 'schema')
    new_rows = 0
    for o, action, _ in d['admit']:
        if action != 'new':
            continue
        if o['native']['kind'] == 'row':
            new_rows += 1
        elif o['native']['kind'] == 'snapshot':
            data = s['in_memory'].get(o['digest'])
            if data is None:
                candidate = pathlib.Path(s['stage_dir']) / o['digest']
                data = candidate.read_bytes() if candidate.is_file() else held.read(corpus.root, o['digest'])
            new_rows += len(json.loads(data)['rows'])
    out['counts']['new'] = new_rows
    return {**out,
            "sensitive_columns": s["sensitive_columns"], "sensitive_decisions": s["sensitive_decisions"],
            "can_confirm": s["can_confirm"], "coverage": s["coverage"],
            "partial_required": bool(s["unexamined"]), "partial_confirmed": s["partial_confirmed"],
            "capture_semantics": dialect.CAPTURE}


def consent(dialect, corpus, decisions, categories, pid=None):
    if decisions is not None and not isinstance(decisions, dict):
        raise Refused("column decisions must be an object")
    if categories is not None and not isinstance(categories, dict):
        raise Refused("partial acquisition decisions must be an object")
    decisions = dict(decisions or {})
    categories = categories or {}
    if any(v not in ("include", "exclude") for v in decisions.values()) or any(k != "partial" or v != "include" for k, v in categories.items()):
        raise Refused("answer each column include/exclude and partial acquisition include")
    if not decisions and not categories and pid is None:
        return {}, False, None, None
    stage = dialect._STAGES.get((corpus.corpus_id, pid))
    if not stage or time.time() - stage["at"] > dialect.STAGE_TTL:
        raise PlanChanged("column consent needs a current preview plan")
    flagged = {c["path"] for c in stage["survey"]["sensitive_columns"]}
    if decisions and set(decisions) != flagged:
        raise Refused("answer every flagged column in this preview")
    return decisions, categories.get("partial") == "include", stage["survey"]["snapshot"], stage


def ready(dialect, corpus, collection):
    decl = dialect.declaration(corpus, collection)
    bnd = bindings.binding(corpus, collection)
    if not bnd:
        raise Refused(f"{dialect.LABEL} collection is not bound on this machine")
    return decl, bnd


def plan_snapshot(dialect, corpus, cv, collection, *, scope=None, within=None, progress=None,
                  sensitive_decisions=None, category_decisions=None, decision_plan=None):
    if within:
        raise Refused(f"use table scope filters for {dialect.LABEL}")
    decl, bnd = dialect._ready(corpus, collection)
    eff = effective_scope(corpus, collection, decl)
    under = proposed(dialect, eff, scope)
    decisions, partial, snapshot, old = dialect._consent(corpus, sensitive_decisions, category_decisions, decision_plan)
    if old and (old["collection"] != collection or old["binding"] != bnd["binding"] or any(old["scope"][k] != under[k] for k in ("include", "exclude", "act"))):
        raise PlanChanged("consent preview belongs to a different collection, binding or scope")
    prior = latest(corpus, dialect.source_of(collection))
    s = _life()._staged_survey(dialect, corpus, under, bnd["root"], progress=progress,
                               decisions=decisions, partial=partial, snapshot=snapshot,
                               protect={(corpus.corpus_id, decision_plan)})
    d = diff(prior, s["observations"], examined=s["examined"], withheld=set(s["withheld"]), compare=s.get("compare"))
    changed, last = _life()._binding_changed(corpus, collection, bnd["binding"], prior)
    pid = dialect._plan_id(dialect._basis(collection, decl, bnd, s, under), under, s, d, prior)
    if (corpus.corpus_id, pid) in dialect._STAGES:
        dialect._abandon_stage(corpus, (corpus.corpus_id, pid))
    dialect._STAGES[(corpus.corpus_id, pid)] = {"at": time.time(), "survey": s,
        "collection": collection, "binding": bnd["binding"], "scope": under}
    dialect._forget_superseded(corpus, {pid, decision_plan}, collection=collection)
    return decl, bnd, eff, under, s, d, changed, pid


def sweep_snapshot(dialect, corpus, cv, collection, plan_id, *, actor, written_by, scope=None,
                   because=None, progress=None, within=None, acknowledge_binding_change=False,
                   sensitive_decisions=None, category_decisions=None, decision_plan=None):
    if within or sensitive_decisions is not None or category_decisions is not None:
        raise Refused(f"confirm the staged {dialect.LABEL} plan; decisions require a new preview")
    decl, bnd = dialect._ready(corpus, collection)
    eff = effective_scope(corpus, collection, decl)
    under = proposed(dialect, eff, scope)
    stage = dialect._STAGES.get((corpus.corpus_id, plan_id))
    if not stage or time.time() - stage["at"] > dialect.STAGE_TTL:
        if stage:
            dialect._abandon_stage(corpus, (corpus.corpus_id, plan_id))
        raise PlanChanged("captured preview expired or lost; preview again")
    if (stage["collection"], stage["binding"], stage["scope"]) != (collection, bnd["binding"], under):
        raise PlanChanged("binding or scope changed; preview again")
    s = stage["survey"]
    if not s["can_confirm"]:
        raise Refused("column decisions and partial acquisition confirmation are required before acquisition")
    prepared = prepare(corpus, source=dialect.source_of(collection), observations=s["observations"],
                       examined=s["examined"], withheld=set(s["withheld"]), compare=s.get("compare"))
    if dialect._plan_id(dialect._basis(collection, decl, bnd, s, under), under, s, prepared["diff"], prepared["prior"]) != plan_id:
        raise PlanChanged("record changed since preview")
    changed, last = _life()._binding_changed(corpus, collection, bnd["binding"], prepared["prior"])
    if changed and not acknowledge_binding_change:
        raise Refused("acknowledge the changed database binding")
    progress.check()
    _life()._admit_stage(corpus, stage)
    return decl, bnd, eff, under, s, changed, last, scope is not None, prepared


def sweep_detail(dialect, s, pid, bnd, changed, last):
    return {"plan": s.get("confirmed_plan", pid), "binding": bnd["binding"], "binding_changed": changed,
            "previous_binding": last, "capture_semantics": dialect.CAPTURE,
            "snapshot_digest": s["snapshot"][1], "coverage": s["coverage"],
            "sensitive_decisions": s["sensitive_decisions"], "partial_confirmed": s["partial_confirmed"],
            "unexamined": s["unexamined"], "refused": s["refused"],
            "not_acquired": [{"path": k, "reason": v} for k, v in s["withheld"].items()]}


def forget_superseded(dialect, corpus, keep, *, collection=None, root=None):
    """Once a new preview is staged, drop this collection's or source's
    earlier ones, as the folder connector does, so repeated previews do not
    each keep a private copy of the database. Kept: the new preview and the
    one named by `decision_plan`, whose captured snapshot the consent answer
    is about. Run only after success, so a refused preview never costs the
    owner the one they were answering; the stage cap is applied here too,
    sparing what is kept."""
    stages = dialect._STAGES
    for k, st in list(stages.items()):
        if k[0] == corpus.corpus_id and k[1] not in keep and (
                (collection is not None and st.get("collection") == collection)
                or (root is not None and st.get("collection") is None
                    and st.get("root") == root)):
            dialect._abandon_stage(corpus, k)
    # The stage cap, applied after success and never to what was kept.
    spare = {(corpus.corpus_id, k) for k in keep}
    while len(stages) > dialect.STAGE_CAP:
        evictable = [k for k in stages if k not in spare]
        if not evictable:
            break
        dialect._abandon_stage(corpus, min(evictable, key=lambda k: stages[k]["at"]))


def forget_expired(dialect, corpus):
    """Expired previews only. Unlike the shared `_forget_stages`, nothing is
    evicted for the cap before the new preview is known to succeed: the
    oldest stage may be the one a consent answer names."""
    now = time.time()
    for k, st in list(dialect._STAGES.items()):
        if now - st["at"] > dialect.STAGE_TTL:
            dialect._abandon_stage(corpus, k)


def preview_new(dialect, corpus, *, name, root, include=None, exclude=None, options=None,
                sensitive_decisions=None, category_decisions=None, decision_plan=None, progress=None):
    """Draft snapshot policy; acquisition runs the existing shared sweep."""
    forget_expired(dialect, corpus)
    name = (name or "").strip()
    if not name:
        raise Refused("a collection needs a name")
    options = dialect.checked_options(options)
    real = bindings._checked_root(corpus, root, kind=dialect.BIND_KIND)
    scope = {"include": dialect._patterns(include, ["*"]), "exclude": dialect._patterns(exclude, []),
             "options": options, "act": None}
    decisions, partial, snapshot, old = dialect._consent(corpus, sensitive_decisions, category_decisions, decision_plan)
    if old and (old["collection"] is not None or old["root"] != real or old["name"] != name or any(old["scope"][k] != scope[k] for k in ("include", "exclude"))):
        raise PlanChanged("column consent belongs to a different draft or scope")
    draft = old["draft"] if old else "draft-" + uuid.uuid4().hex[:12]
    s = _life()._staged_survey(dialect, corpus, scope, real, progress=progress,
                               decisions=decisions, partial=partial, snapshot=snapshot,
                               protect={(corpus.corpus_id, decision_plan)})
    d = diff({}, s["observations"], examined=s["examined"], withheld=set(s["withheld"]), compare=s.get("compare"))
    stage = {"at": time.time(), "survey": s, "collection": None, "root": real,
             "name": name, "scope": scope, "draft": draft}
    pid = dialect._plan_id(dialect._draft_basis(stage), scope, s, d, {})
    if (corpus.corpus_id, pid) in dialect._STAGES:
        dialect._abandon_stage(corpus, (corpus.corpus_id, pid))
    dialect._STAGES[(corpus.corpus_id, pid)] = stage
    dialect._forget_superseded(corpus, {pid, decision_plan}, root=real)
    return {"draft": draft, "collection": None, "name": name, "scope": scope_view(scope),
            **preview_result(dialect, corpus, s, d, pid, False),
            "confirm": {"draft": draft, "plan": pid}}


def acquire_new(dialect, corpus, cv, draft, plan_id, *, actor="human", written_by=None, progress=None):
    """Convert a verified draft to a collection and use the shared sweep.

    No third apply/transaction/Admission lifecycle: shared declare and sweep
    own those operations. The outer transaction also rolls back declaration.
    """
    stages = dialect._STAGES
    stage = stages.get((corpus.corpus_id, plan_id))
    if not stage or stage.get("draft") != draft or time.time() - stage["at"] > dialect.STAGE_TTL:
        raise PlanChanged("draft capture expired or lost; preview again")
    s, scope = stage["survey"], stage["scope"]
    if not s["can_confirm"]:
        raise Refused("answer every flagged column and confirm partial acquisition before acquiring")
    d = diff({}, s["observations"], examined=s["examined"], withheld=set(s["withheld"]), compare=s.get("compare"))
    if dialect._plan_id(dialect._draft_basis(stage), scope, s, d, {}) != plan_id:
        raise PlanChanged("draft changed; preview again")
    bound, migrated = None, None
    try:
        with corpus.atomic():
            made = _life().declare(dialect, corpus, cv, name=stage["name"],
                                   include=scope["include"], exclude=scope["exclude"],
                                   declarer=actor, written_by=written_by, options=scope["options"])
            collection = made["collection"]
            bound = bindings.bind(corpus, collection, stage["root"], written_by=written_by, kind=dialect.BIND_KIND)
            bnd = bindings.binding(corpus, collection)
            eff = effective_scope(corpus, collection)
            migrated = dialect._plan_id(dialect._basis(collection, made, bnd, s, eff), eff, s, d, {})
            stages[(corpus.corpus_id, migrated)] = {**stage, "collection": collection,
                "binding": bnd["binding"], "scope": eff}
            s["confirmed_plan"] = plan_id
            out = _life().sweep(dialect, corpus, cv, collection, migrated, actor=actor,
                                written_by=written_by, progress=progress)
    except BaseException:
        if migrated:
            stages.pop((corpus.corpus_id, migrated), None)
        if bound:
            bindings.unbind(corpus, bound["collection"], written_by=written_by)
        raise
    stages.pop((corpus.corpus_id, plan_id), None)
    return {**out, "collection": collection, "declaration": made["declaration"],
            "binding": bound["binding"], "name": stage["name"]}
