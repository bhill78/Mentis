"""WHAT A SQLITE SOURCE SAYS IT HOLDS (Manage Sources, defect D-11).

A relational source records a SCHEMA object per table beside the row objects,
so "records" (Admissions) and "rows" are different numbers for the same
acquisition: 5 rows of 2 tables are 7 records. The plan already tells them
apart (`counts.new` is rows, `counts.schema_new` the schemas). The collection
view did not: it said only `present`, so the page could say "7 records" beside
"5 rows" with nothing to reconcile them, and after a revise that took nothing
new the result said "0 rows are now in Mentis". `counts.kinds` is the present
objects by what they are, read from the record."""
import sqlite3

import pytest

from mentis import api
from mentis.sources import reading
from mentis.web import _State, fixture


def _db(path):
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer INTEGER REFERENCES customers(id),
                             qty INTEGER, total REAL);
        INSERT INTO customers VALUES (1,'Ada'),(2,'Bo'),(3,'Cy');
        INSERT INTO orders VALUES (1,1,1,9.5),(2,2,1,3.0),(3,3,4,20.0);
        CREATE TABLE log (line TEXT);
        INSERT INTO log VALUES ('a'),('b'),('c'),('d');
    """)
    db.commit()
    db.close()


def _scope(omit, tables=("customers", "orders")):
    return {"include": list(tables), "exclude": [],
            "options": {"tables": {"orders": {"omit": omit, "rows": [
                {"column": "qty", "op": "equals", "value": ["integer", "1"]}]}}}}




@pytest.fixture
def shop(tmp_path):
    built = fixture.build(str(tmp_path / "brain"))
    st = _State(str(tmp_path / "brain"))
    path = str(tmp_path / "shop.sqlite")
    _db(path)
    return {"st": st, "src": api.sources(st.corpus), "me": built["who"]["@brian"], "path": path}


def _acquire(shop, scope):
    src = shop["src"]
    plan = src.preview_new(connector="sqlite", name="Shop", root=shop["path"], include=scope["include"],
                           exclude=scope["exclude"], options=scope["options"])
    out = src.acquire_new(plan["draft"], plan["plan"], connector="sqlite", actor=shop["me"], written_by="test")
    return plan, out


def _counts(shop, col):
    return reading.overview(shop["st"].corpus, col)["counts"]


def test_one_acquisition_reconciles_rows_schemas_and_records(shop):
    """The numbers one acquisition is described by: rows planned, Admissions
    recorded, and what the collection then holds, all from the backend."""
    plan, out = _acquire(shop, _scope(["total"]))
    # two orders match qty = 1, three customers: 5 rows, and a schema per table
    assert plan["counts"]["new"] == 5 and plan["counts"]["schema_new"] == 2
    assert len(plan["admit"]) == 7 == len(out["admitted"])
    counts = _counts(shop, out["collection"])
    assert counts["present"] == 7
    assert counts["kinds"] == {"row": 5, "schema": 2}
    assert sum(counts["kinds"].values()) == counts["present"]


def test_a_revise_that_takes_no_new_row_still_holds_its_rows(shop):
    """Taking a left-out column again WIDENS the rows it touches and adds
    none: `new` is 0 in the plan and in the sweep. What is held is not 0 --
    and that, not `new`, is what "are now in Mentis" must be read from."""
    _, out = _acquire(shop, _scope(["total"]))
    col, src = out["collection"], shop["src"]
    wider = _scope([])
    plan = src.plan(col, scope=wider)
    assert plan["counts"]["new"] == 0 and plan["counts"]["widened"] == 2
    swept = src.sweep(col, plan["plan"], scope=wider, because="take total again", actor=shop["me"],
                      written_by="test")
    assert swept["admitted_by_action"]["new"] == [] and len(swept["admitted_by_action"]["widened"]) == 2
    view = reading.overview(shop["st"].corpus, col)
    assert view["last_sweep"]["act"] == swept["act"]
    assert view["last_sweep"]["counts"]["widened"] == 2 and view["last_sweep"]["counts"]["unchanged"] == 5
    assert view["counts"]["kinds"] == {"row": 5, "schema": 2}, "the rows held after the revise, not 0"


def test_a_keyless_table_is_one_snapshot_record_not_rows(shop):
    """A table with no key is held whole, as ONE object: it is counted as a
    snapshot, never as a row, so "rows" is not claimed for it."""
    plan, out = _acquire(shop, {"include": ["log"], "exclude": [], "options": {}})
    assert plan["counts"]["new"] == 4, "the plan counts the rows inside the snapshot"
    assert _counts(shop, out["collection"])["kinds"] == {"schema": 1, "snapshot": 1}


def test_a_folder_source_names_no_kinds(shop, tmp_path):
    """Only a connector whose objects say what they are gets the breakdown."""
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "a.md").write_text("one", encoding="utf-8")
    src = shop["src"]
    plan = src.preview_new(connector="filesystem", name="Notes", root=str(folder), include=["**"], exclude=[])
    out = src.acquire_new(plan["draft"], plan["plan"], connector="filesystem", actor=shop["me"], written_by="test")
    counts = _counts(shop, out["collection"])
    assert counts["present"] == 1 and "kinds" not in counts
