"""Row J's allowed messages, read from `restart_messages.json`, decided whole.

`decide` says which entries a message matches, and row J's test fails on none. The cases a test
names are those it can truly be in: a B-sent reply isn't allowed to read as case A, because that
message says nothing was done.
"""

from __future__ import annotations

import json
import pathlib
import re

LIST = json.loads(pathlib.Path(__file__).with_name("restart_messages.json")
                  .read_text(encoding="utf-8"))

#: What a placeholder may hold. Nothing else in a message varies.
PLACEHOLDERS = {
    "{via}": r"https?://[^\s/]+(?::\d+)?/?",
    "{name}": r"'[a-z_]+'",
    "{record}": r"'[^']+'",
    "{urlopen_error}": r"<urlopen error [^>]*>",
    "{exception}": r".+",
}


def _pattern(template: str) -> re.Pattern:
    parts = re.split("(" + "|".join(re.escape(p) for p in PLACEHOLDERS) + ")", template)
    return re.compile("".join(PLACEHOLDERS.get(p, re.escape(p)) for p in parts), re.DOTALL)


def decide(message: str, cases=None) -> list[str]:
    """The agent-tool-error entries, of `cases` or of all, this whole message matches."""
    entries = LIST["agent_tool_errors"]
    return [case for case in (cases or entries)
            if _pattern(entries[case]["message"]).fullmatch(message)]


def is_bridge_exit(stderr: str) -> bool:
    return bool(_pattern(LIST["bridge_exit"]["C"]["stderr"]).fullmatch(stderr.strip()))
