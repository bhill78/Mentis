"""Export and import between two independent Brains (design adm-6cebfabd6e9c).

SLICE 1, AND IT WRITES NOTHING. `export` builds the closure of one marked
thing -- a Conversation, a single Turn or an item (O2) -- in one read
transaction on a Brain opened `access="read"`, so it takes only the SHARED
open lock and runs beside a serving server, and writes a self-describing zip
outside every Brain. `import --preview` opens the receiving Brain the same
way and says what an import WOULD do: new, already present, conflicts,
standing that does not travel, and references the export did not carry.

  format.py    the zip, its reader and writer, and the content fingerprint
  identity.py  {corpus_id, fork_id}: read only; `brain-forked` is written
               by the receiving side's slice (O1), never here
  export.py    the closure (design §2) and `export`
  preview.py   `classify(store, export) -> Plan`, the data apply
               consumes, and its plain-language rendering
  apply.py     slice 2: `import --apply` writes the Plan's conflict-free
               part, after a verified backup, in one transaction through the
               import door, and records it in one `import-applied` act

What is never carried, whatever asks: `establishes`, `scoped-to` and
`carries-intake` links (they put things in force); run and dispatch acts;
the delivery table; scratch, presentation and derived data. Standing travels
only as evidence (`evidence.json`).
"""

from __future__ import annotations


class ExchangeRefused(RuntimeError):
    """An export or a preview refused, in words, with nothing written."""
