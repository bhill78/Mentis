"""A choice written into a reply instead of asked (forms build P8; design
revision 3, section 9D).

Agents are to ask the owner every choice through `request_decision`, which
makes it a decision form the owner answers where it was asked. A choice
written as prose -- "Which should I do? A) ... B) ..." -- or as a checklist to
pick from is owed by nobody and answers nothing. This finds those in a
reply's Markdown, so the check of that reply can warn the run that wrote it
when the run raised no decision (`render_check.choice_warning`). It warns;
it never refuses, and nothing is changed in what was written.

WHAT COUNTS, deliberately narrow, because a false warning teaches an agent
to ignore the check:

  * a list of two or more items (bullets, numbers or ticks) whose lead-in --
    the nearest line of prose above it, at most two lines up -- asks for a
    choice: "choose", "pick", "select", "which one / of these / would you",
    "options:", "prefer", "would you like / rather", "do you want",
    "should I / we ...?", "let me know which / whether", "your call",
    "either ... or";
  * a list of two or more items lettered or named as options ("A)", "(b)",
    "Option 2", "**Option A**"), whatever leads into it;
  * a ```checklist block whose title asks for a choice in those words, or
    that follows such a lead-in;
  * a lead-in opening with "Which", "Should I", "Shall I" or "I need you
    to", and a list FOLLOWED by "Which ...?" -- that question is its lead.

A list of things done, steps to take or a checklist of tasks says none of
these, and is not a choice. Code fences are skipped.
"""

from __future__ import annotations

import re

#: The words of a lead-in that asks the reader to choose. WHOLE WORDS: a
#: report saying what it "decided", "selected", "picked" or "preferred" is
#: not asking anybody anything.
CUE = re.compile(
    r"\b(?:(?:choose|pick|select|prefer|decide)\b"
    r"|which\s+(?:one|ones|option|options|of\s+(?:these|them|the|those)"
    r"|would\s+you|do\s+you|should\s+(?:i|we))\b"
    r"|options?\s*:|would\s+you\s+(?:like|rather|prefer)\b|do\s+you\s+want\b"
    r"|let\s+me\s+know\s+(?:which|whether)\b|your\s+call\b"
    r"|should\s+(?:i|we)\b[^.\n]*\?"
    r"|either\b[^.\n]*\bor\b"
    r"|^\s*(?:which|(?:should|shall)\s+(?:i|we)|i\s+need\s+you\s+to)\b)",
    re.IGNORECASE)
#: A question AFTER a list that asks which of it: "Which should I do?".
TRAIL = re.compile(r"^\s*which\b[^\n]*\?\s*$", re.IGNORECASE)
#: One list item: a bullet, a number, or a tick box.
ITEM = re.compile(r"^\s{0,3}(?:[-*+]|\d{1,2}[.)])\s+(?:\[[ xX]\]\s+)?(?P<rest>\S.*)$")
TICK = re.compile(r"^\s{0,3}[-*+]\s+\[[ xX]\]\s+\S")
#: An item that is named as an option: "A) ...", "(b) ...", "Option 2: ...".
LETTERED = re.compile(r"^(?:\*\*|__)?(?:\(?[A-Ha-h][.):]\s|option\s+(?:[A-H]|\d)\b)",
                      re.IGNORECASE)
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*(\S*)(.*)$")
TITLE = re.compile(r"""\btitle=(?:"([^"]*)"|(\S+))""")


def _lead_in(lines, start) -> str:
    """The nearest prose line above `start`, at most two lines up."""
    for k in range(start - 1, max(start - 3, -1), -1):
        line = lines[k].strip()
        if line:
            return "" if ITEM.match(lines[k]) else line
    return ""


def _trail(lines, end) -> str:
    """The prose line right after a list (at most one blank line between)
    when it asks which of the list, or ""."""
    for k in range(end, min(end + 2, len(lines))):
        line = lines[k].strip()
        if line:
            return line if TRAIL.match(line) else ""
    return ""


def find(text) -> list[dict]:
    """Every choice written into `text`, each `{line, kind, items, lead}`:
    `line` 1-based where it starts, `kind` "list" or "checklist", `items` its
    entries as written, `lead` the words that ask it (a checklist's title, or
    the lead-in above it; "" when only the items' lettering says so). Empty
    when there are none."""
    if not isinstance(text, str) or not text:
        return []
    lines = text.split("\n")
    out = []
    i, n = 0, len(lines)
    while i < n:
        fence = FENCE.match(lines[i])
        if fence:
            mark, info, rest = fence.group(1), fence.group(2), fence.group(3)
            j = i + 1
            while j < n and not lines[j].strip().startswith(mark[0] * len(mark)):
                j += 1
            if info == "checklist":
                items = [m.group("rest").strip() for m in map(ITEM.match, lines[i + 1:j]) if m]
                title = TITLE.search(rest)
                said = (title.group(1) or title.group(2)) if title else ""
                lead = _lead_in(lines, i)
                if not CUE.search(lead) and _trail(lines, j + 1):
                    lead = _trail(lines, j + 1)
                if len(items) >= 2 and (CUE.search(said) or CUE.search(lead)):
                    out.append({"line": i + 1, "kind": "checklist", "items": items,
                                "lead": said if CUE.search(said) else lead})
            i = j + 1
            continue
        if ITEM.match(lines[i]):
            j = i
            while j < n and ITEM.match(lines[j]):
                j += 1
            items = [ITEM.match(x).group("rest").strip() for x in lines[i:j]]
            named = sum(1 for x in items if LETTERED.match(x))
            lead = _lead_in(lines, i)
            if not CUE.search(lead) and _trail(lines, j):
                lead = _trail(lines, j)
            if len(items) >= 2 and (CUE.search(lead) or named >= 2):
                ticks = all(TICK.match(x) for x in lines[i:j])
                out.append({"line": i + 1, "kind": "checklist" if ticks else "list",
                            "items": items, "lead": lead})
            i = j
            continue
        i += 1
    return out
