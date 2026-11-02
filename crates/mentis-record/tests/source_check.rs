//! `corpus.db*` is opened only through SQLite (`contracts/record.md`): closing any other handle on
//! it drops SQLite's POSIX locks. One check, shared with row I, so the two can't drift:
//! `tests/front/test_wrote_nothing.py` says what it looks at and what it can't see.

mod support;

use support::run_python;

#[test]
fn corpus_db_is_opened_only_through_sqlite() {
    run_python(
        "from tests.front import test_wrote_nothing as row_i\n\
         row_i.test_corpus_db_is_opened_read_only_and_only_through_sqlite()",
        &[],
    );
}
