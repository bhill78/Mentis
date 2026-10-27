"""Closed SQLite rules. Values are bound separately; identifiers are quoted.

SQLite applies column affinity to bound values (text '42' can match INTEGER
42). Date comparisons use stored ISO text, without epoch conversion.

The closed structure and its compiler are `relational`'s, shared by every
relational dialect; this module binds them to SQLite's spelling.
"""
from mentis.sources import relational
from mentis.sources.relational import (NO_VALUE, OPS, SECRET, _column, _name,
                                       checked_rules, checked_value, sentence,
                                       untyped)


def checked_options(options, *, base=None):
    return relational.checked_options(options, base=base, label='SQLite')


def _q(name):
    return '"' + _name(name).replace('"', '""') + '"'


def _dialect():
    from mentis.sources import sqlite
    return sqlite


def compile_select(table, columns, rows):
    return relational.compile_select(_dialect(), table, columns, rows)


def explain(table, columns, rows):
    return relational.explain(_dialect(), table, columns, rows)
