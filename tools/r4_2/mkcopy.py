"""A disposable Brain copy: SQLite's backup API from a read-only connection, plus the files beside it.

    python tools/r4_2/mkcopy.py <master> <dest>
"""
import os
import pathlib
import shutil
import sqlite3
import sys

master, dest = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
live = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Mentis" / "Mark-IV" / "brain"
if master.resolve() == live.resolve():
    raise SystemExit("never the live Brain")
dest.mkdir(parents=True)
source = sqlite3.connect(f"file:{(master / 'corpus.db').as_posix()}?mode=ro", uri=True)
target = sqlite3.connect(dest / "corpus.db")
with target:
    source.backup(target)
source.close()
target.close()
for name in ("mentis-corpus.json",):
    if (master / name).exists():
        shutil.copy2(master / name, dest / name)
for name in ("presentation", "derived"):
    if (master / name).is_dir():
        shutil.copytree(master / name, dest / name)
print("copied", dest)
