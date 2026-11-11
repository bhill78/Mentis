"""What a Brain holds, read-only: python -I counts.py BRAIN. Adapted from r1-deploy-2026-11-02's, with the Brain as an argument and quick_check."""
import json
import os
import sqlite3
import sys
import time

b = sys.argv[1]
c = sqlite3.connect(f"file:{b}/corpus.db?mode=ro", uri=True)
q = lambda s: c.execute(s).fetchone()[0]
art = sum(len(f) for _, _, f in os.walk(os.path.join(b, "artifacts")))
print(json.dumps({"at": time.strftime("%H:%M:%S"), "entry": q("select count(*) from entry"),
                  "operational": q("select count(*) from operational"),
                  "delivery": q("select count(*) from delivery"),
                  "max_entry_rowid": q("select max(rowid) from entry"),
                  "migrations": q("select count(*) from schema_migration"), "artifacts_files": art,
                  "corpus_id": json.load(open(os.path.join(b, "mentis-corpus.json"))).get("corpus_id"),
                  "quick_check": q("pragma quick_check")}))
