"""The other side of the moved reads' byte test: what Python's door gives `json.dumps` for each case,
on a changed BRAIN-SEED.

    worker_reads_side.py change <brain>    what `agent_reads_side.py change` writes, and some more
    worker_reads_side.py wire <brain>      print every case as JSON: op, args, then body or raises

The Rust side answers each case with `worker_reads::read` and compares bytes, or shows it forwarded.
Cases in `forward` are ones the door has to hand on whatever Python makes of them.
"""

import json
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "mentis-ops" / "tests" / "support"))

import agent_reads_side  # noqa: E402
from agent_reads_side import AT, _text  # noqa: E402
from mentis import worker  # noqa: E402

import python_side  # noqa: E402

#: Stored as is, by hand: what a body read back has to come out of Python's `json` as. A repeated
#: key, floats written every way, an escaped letter, a lone surrogate, and characters outside ASCII
#: both raw and escaped.
ODD_BODY = ('{"z": 1.10, "a": [1E2, 1e16, 1e-05, -0.0, -0, 12345678901234567890123], '
            '"z": {"again": true}, "\\u0061b": "\\u00E9 caf\\u00e9 über \U0001f600", '
            '"lone": "\\ud800", "ctl": "\\u0001\\u007f\\/", "text": "an odd body"}')


def change(brain):
    agent_reads_side.change(brain)
    corpus, cv = python_side._open(brain)
    owner = cv.resolve_participant("@r1-owner")
    known = python_side._named(corpus, "conversation", "R1 known conversation")
    # Details and bodies holding what `json.dumps` writes in its own way, by the ordinary writers.
    said = cv.say(known, owner, _text("a turn with über \U0001f600 words\nand \"quotes\" \\ too"))
    cv.record_act(actor=owner, act="something-odd", conversation=known, turn=said,
                  because="während", about=[said],
                  detail={"f": 1.5e300, "small": 1e-7, "whole": 3.0, "n": -0.0, "u": "Ü\U0001f600",
                          "big": 123456789012345678901234567890, "nested": {"z": [1, {"y": None}]}})
    note = corpus.write(kind="note", attributed_to=owner, body={"text": "to copy"})
    corpus.close()
    db = sqlite3.connect(f"{brain}/corpus.db")
    with db:
        db.execute(
            "INSERT INTO entry (id, body, hash, family, def_name, def_version, attributed_to, "
            "written_by, recorded_at, origin, link_from, link_to, link_relation, "
            "link_relation_version, prev_hash) "
            "SELECT 'ent-oddbodyoddbody', ?, 'not-checked', family, def_name, def_version, "
            "attributed_to, written_by, recorded_at, origin, link_from, link_to, link_relation, "
            "link_relation_version, prev_hash FROM entry WHERE id = ?", (ODD_BODY, note))
    db.close()


def _sort_of(op, args, value):
    """What an answer is, for the counts: a `resolve` by what it says it is, the rest by branch."""
    if op == "resolve":
        return "not known" if value.get("known") is False else value.get("what", "?")
    if op == "history" and args.get("set"):
        return "set changes: refused" if "refused" in value else "set changes"
    if op in ("history", "owner_decisions", "governed"):
        return "refused" if "refused" in value or "error" in value else "page"
    return "answer"


def wire(brain):
    corpus, cv = python_side._open(brain)
    surface = worker.Surface(brain, corpus=corpus)
    worker.time.time = lambda: AT
    db = sqlite3.connect(f"file:{brain}/corpus.db?mode=ro", uri=True)
    ids = [r[0] for r in db.execute("SELECT id FROM entry ORDER BY seq")]
    conversations = [r[0] for r in db.execute(
        "SELECT id FROM entry WHERE def_name = 'conversation' AND family = 'entry' "
        "AND link_relation IS NULL ORDER BY seq DESC LIMIT 6")]
    participants = [r[0] for r in db.execute(
        "SELECT actor FROM operational GROUP BY actor ORDER BY COUNT(*) DESC LIMIT 4")]
    turns = [r[0] for r in db.execute(
        "SELECT turn FROM operational WHERE turn IS NOT NULL "
        "GROUP BY turn ORDER BY COUNT(*) DESC LIMIT 4")]
    sets = [r[0] for r in db.execute(
        "SELECT id FROM entry WHERE def_name = 'response-set' AND family = 'entry' ORDER BY seq DESC")]
    forms = [r[0] for r in db.execute(
        "SELECT id FROM operational WHERE act = 'decision-form' ORDER BY seq DESC")]
    db.close()
    known = conversations[0]

    cases = []  # (op, args, must the door forward whatever Python says?)
    def answerable(op, *many):
        cases.extend((op, args, False) for args in many)

    def forwarded(op, *many):
        cases.extend((op, args, True) for args in many)

    # -- capabilities, kinds --------------------------------------------------------------------
    answerable("capabilities", {}, {"anything": 1})
    answerable("kinds", {}, {"anything": 1})

    # -- resolve --------------------------------------------------------------------------------
    answerable("resolve", *[{"ref": one} for one in ids])
    answerable("resolve", *[{"ref": one} for one in (
        "ent-nothing-holds-this", "", " ", "it's", "café \U0001f600", "a\nb", "a\"b\\c")])
    forwarded("resolve", {}, {"ref": None}, {"ref": 5}, {"ref": True}, {"ref": ["x"]}, {"ref": {}},
              {"ref": "a\0b"})

    # -- history --------------------------------------------------------------------------------
    filters = [{}, *[{"conversation": c} for c in conversations],
               *[{"turn": t} for t in turns], *[{"participant": p} for p in participants],
               {"conversation": known, "turn": turns[0]},
               {"conversation": known, "participant": participants[0]},
               {"turn": "ent-nothing", "participant": "nobody"},
               {"conversation": ""}, {"turn": ""}, {"participant": ""},
               {"conversation": None, "turn": None, "participant": None}, {"since": ""},
               {"since": None}, {"set": ""}, {"set": None}, {"set": "", "since": ""}]
    for one in filters:
        answerable("history", one, {**one, "limit": None},
                   *[{**one, "limit": n} for n in (1, 3, 40, 1000)])
    # `view` (Workstream R): acts as before; a Conversation alone, or posts, is Python's.
    answerable("history", *[{**one, "view": v} for one in filters[:3]
                            for v in ("acts", " acts ", "", None)],
               {"view": "acts", "turn": turns[0]})
    forwarded("history", {"conversation": known, "view": "posts"}, {"view": "posts"},
              {"view": "nonsense"}, {"view": 5}, {"conversation": known, "view": "  "})
    answerable("history", {"since": "x"}, {"since": "  "}, {"since": "it's", "limit": 3},
               {"since": "x", "conversation": known}, {"set": "", "since": "x"})
    forwarded("history", *[{"limit": n} for n in (0, -1, 1001, 1.5, 2.0, "3", "", True, False, [], {}, 1e3)],
              {"conversation": 5}, {"conversation": 0}, {"turn": ["x"]}, {"participant": True},
              {"since": 1}, {"since": 0}, {"set": 5}, {"set": 0}, {"set": True},
              {"since": "x", "limit": 0})

    # -- history set= ---------------------------------------------------------------------------
    for one in [*sets, *forms, "ent-nothing", known, "  ", " " + (forms or [known])[0] + " ", "it's"]:
        first = surface.set_changes(one.strip())
        mids = [c["entry"] for c in first.get("changes", ())]
        for since in [None, "", one.strip(), "  ", "not-a-member", "it's", *mids[:2], *mids[-1:],
                      " " + (mids or ["x"])[0] + " "]:
            given = {"set": one} if since is None else {"set": one, "since": since}
            answerable("history", given, *[{**given, "limit": n} for n in (1, 2, 40, 200)])
    forwarded("history", *[{"set": (forms or [known])[0], "limit": n}
                           for n in (0, -1, 201, 1.5, "3", True)],
              {"set": (forms or [known])[0], "since": 1})

    # -- owner_decisions ------------------------------------------------------------------------
    for one in [*conversations, "ent-nothing", " " + known + " ", "it's", "café", "", "  ", None]:
        given = {} if one is None else {"conversation": one}
        answerable("owner_decisions", given, {**given, "most": None},
                   *[{**given, "most": n} for n in (1, 2, 5, 40)])
    answerable("owner_decisions", {"conversation": None})
    forwarded("owner_decisions", *[{"conversation": known, "most": n}
                                   for n in (0, -1, 41, 100, 1.5, "3", "", True, [], {})],
              {"conversation": 5}, {"conversation": ["x"]}, {"conversation": True})

    # -- governed -------------------------------------------------------------------------------
    grid = [{}, *[{"kind": k} for k in (
                "rule", "lesson", "persona", " rule ", "contribution", "note", "no-such-kind", "",
                "it's", None)],
            *[{"q": q} for q in ("", None, "replace", "a standing rule", "ZZZZ", "r1-owner",
                                 "Überblick", "reviewer", "proposal number", "the rule")],
            *[{"state": s} for s in ("proposed", "recorded", "standing", "history", "unknown",
                                     "x", " standing ", "", None, "it's")],
            {"kind": "rule", "state": "history", "q": "rule", "limit": 3},
            {"state": "x", "kind": "no-such-kind"}, {"cursor": "g1.1"},
            {"limit": None}, {"kind": "rule", "limit": None}]
    answerable("governed", *grid, *[{"limit": n} for n in (1, 2, 40, 1000)])
    forwarded("governed", *[{"limit": n} for n in (0, -1, 1001, 1.5, "3", "", True, [], {})],
              {"kind": 5}, {"q": 5}, {"state": 5}, {"kind": 0}, {"q": []}, {"state": False})

    out = []
    for op, args, forward in cases:
        case = {"op": op, "args": args, "forward": forward}
        try:
            with surface.cv.reading():
                value = worker._result(surface, op, dict(args))
            case["body"] = json.dumps(value, default=str)
            case["sort"] = _sort_of(op, args, value)
        except Exception as failure:  # noqa: BLE001  what is compared is that it failed
            case["raises"] = type(failure).__name__
            case["sort"] = "Python raised"
        out.append(case)
    # Python's side of the renderer alone, on the raw text.
    print(json.dumps({"at": AT, "cases": out, "odd_body": ODD_BODY,
                      "odd_body_dumped": json.dumps(json.loads(ODD_BODY), default=str)}))
    corpus.close()


if __name__ == "__main__":
    what, where = sys.argv[1], sys.argv[2]
    if what == "change":
        change(where)
    elif what == "wire":
        wire(where)
    else:
        raise SystemExit(f"no {what!r}")
