"""One reply-syntax contract shared by Conversation dispatch and Scratch.

The eight approved capabilities follow the UI parsers at 9ac921e. The ninth,
timer, was added deliberately by the timer build (plan adm-4fc92741cf96, A1),
with the owner's constraint on agents said in its own syntax line.
"""

EXAMPLES = {
    "checklist": '```checklist version=1 name=checks\n- [ ] Check the result\n```',
    "chart": '```chart version=1 form=bar x=item y=value x_label="Item" y_label="Value"\nitem,value\nA,1\n```',
    "table": '```table version=1\nitem,value\nA,1\n```',
    "timeline": '```timeline version=1\ndate,event\n2026-01-01,Start\n```',
    "diagram": '```diagram version=1\na: "Start"\nb: "Finish"\na -> b\n```',
    "pad": '```pad version=1 name=draft\nDraft text\n```',
    # Illustrative syntax, not an entry an agent may cite without looking it up.
    "ref": '```ref version=1 id=ent-123456789abc\n```',
    "panel": '````panel version=1\n```checklist version=1 name=panel-checks\n- [ ] Check the result\n```\n````',
    "timer": '```timer version=1 name=focus title="Deep work" box=25m break=5m\n```',
}

_SYNTAX = {
    "checklist": 'Optional title, name=<a name unique in the post: a lowercase letter, then up to 39 lowercase letters, digits or hyphens; without it ticks are not saved>. Body: nonempty - [ ] text or - [x] text per line (also * and X).',
    "chart": 'Required form=bar|line|scatter|pie|venn, x=<column>, y=<comma-separated columns>, x_label, y_label. Optional title, x_unit, y_unit; Venn: sets="A,B" (2 or 3 distinct names, no &), counts=exclusive|total; bar: stack=true|false, orient=vertical|horizontal, max=<positive number>. Body: CSV header and data rows; named columns must exist; y values finite numbers or blank gaps, scatter x numeric. Pie/Venn require one y series of present nonnegative values; pie total positive. Venn x holds distinct membership keys (A, B, A&B); counts=total intersections require member totals and cannot exceed them. Stacked bars forbid negatives; max bounds values or stacked totals to 0..max. Bar options on other forms and sets/counts outside Venn are ignored with warnings.',
    "table": 'Optional title, key=<unique nonempty column>, select=none|one|many, editable=<comma-separated columns>. Body: CSV header and rows. Editable columns must exist and cannot include the key column. Without key, selection/edits use row positions with a warning; declare key to keep them attached when rows move. Edits are saved only with both key= and name=<a name unique in the post: a lowercase letter, then up to 39 lowercase letters, digits or hyphens>.',
    "timeline": 'Optional title, when=<date column> (default date), what=<event column> (default event), until=<end date column>, group=<lane column>, detail=<detail column>, id=<unique key column>, parents=<dependency column>. Body: CSV header and events with nonempty dates/labels; dates YYYY-MM-DD, YYYY-MM, YYYY or YYYY-MM-DDTHH:MM. End cannot precede start. parents requires id; prerequisite ids separated by semicolons or CSV-quoted commas must resolve, cannot name the event itself, and cannot form cycles.',
    "diagram": 'Optional title, direction=down|right, groups=<comma-separated lane order>, view=flow|git. Body: unique nodes id: "Label" followed by optional kind=start|step|decision|end|note|commit, group, detail, date, author, tag; edges a -> b "optional label" must name declared nodes; # comments allowed. Git view forbids cycles.',
    "pad": 'Optional title, name=<a name unique in the post: a lowercase letter, then up to 39 lowercase letters, digits or hyphens; without it the text typed is not saved>, source=none|conversation|refs, refs=<items>. Body: starting text, possibly empty. source=refs requires refs; refs allowed only with source=refs. Source scope is displayed, never resolved or enforced.',
    "ref": 'Optional id=<reference>, presentation=compact|expanded, title, via=<helper session written by Mentis>. Body: one reference per line, optional leading - or *; at least one id/body reference required. Use real ent-/def- references found with tools; never invent ids. The example id below illustrates syntax only: replace it with an existing reference. Scheme references need a registered provider to resolve.',
    "timer": 'Optional title, name=<a name unique in the post: a lowercase letter, then up to 39 lowercase letters, digits or hyphens; without it no runs are kept>, box=<a time box: 25m, 2h or 1h30m, 1m to 12h>, break=<the break after each box, written like box=; requires box=>, about="<one or more Topic, Conversation or post ids, comma-separated: ent-..., ent-...; what the time is spent on>". Body: empty. A malformed about= id is an error; one Mentis does not hold is a warning and is shown as unresolved. Each person\'s starts and stops are kept by Mentis in their own ledger. A timer is named exactly as ent-<post>#<name> (its post id, #, its name=). You may start or stop a timer only when the owner explicitly asked you to, never by yourself: the request your run carries must be the owner\'s, still open, and name that timer exactly as ent-<post>#<name>; a bare word such as its name does not count, and the permission ends with your run. The timer tool refuses anything less, and it reads time spent on a Topic, Conversation or post (about=) without marking anything.',
    "panel": 'Optional title, arrange=stack|side-by-side. Body: ordinary Markdown and nested renderable fences. Use four backticks outside three-backtick children (or an outer fence longer than every inner run).',
}

#: WHAT THE GUIDE SAYS ABOUT CHOICES. A choice only the owner can make is
#: asked with the tool, never in prose; everything else is settled by the run
#: (owner, 2026-10-27: "Reduce unnecessary owner decisions ... allowing agents
#: to complete work within their existing authority. Preserve genuine owner
#: decisions"). The tool's own description says which choices are the owner's.
ASK_LINE = ('Ask the owner a choice only they can make with request_decision, '
            'never as text or a checklist; a choice already settled, or '
            'reversible and within the work, is yours: make it and say so. ')

RENDERER_GUIDE = (
    'Answer in Markdown. Use these blocks only where they genuinely help, not by default: '
    + ', '.join(EXAMPLES)
    + '. A checklist the owner can tick is a fenced ```checklist version=1 block; '
    'a plain - [ ] list renders as static text. '
    + ASK_LINE +
    'Every block requires version=1. '
    'Attributes are key=value or key="text with spaces"; do not repeat keys. '
    'Unknown attributes are retained but ignored with a warning. Close every fence. '
    'The check_rendering tool lists what will not render in a draft, without posting it. '
    'An image artifact written ![caption](adm-...) as a paragraph of its own '
    '(blank lines around it) is drawn there as a figure; place it where it belongs in the text.\n\n'
    + '\n\n'.join(_SYNTAX[k] + '\n' + example for k, example in EXAMPLES.items())
)


#: THE SAME CONTRACT, CUT TO WHAT A DISPATCHED RUN NEEDS ON EVERY TURN: which
#: blocks exist, the rules every block shares, one minimal example of each,
#: and the owner's constraint on timers in full. Each block's attribute rules
#: (`_SYNTAX`) are delivered by reference: `check_rendering` with
#: `syntax=<block>` returns them, and a draft checked with it is told exactly
#: what will not render. `RENDERER_GUIDE` stays the whole contract.
RENDERER_BRIEF = (
    'Answer in Markdown. Use these blocks only where they genuinely help, not by default: '
    + ', '.join(EXAMPLES)
    + '. A checklist the owner can tick is a fenced ```checklist version=1 block; '
    'a plain - [ ] list renders as static text. '
    + ASK_LINE +
    'Every block requires version=1. '
    'Attributes are key=value or key="text with spaces"; do not repeat keys. Close every fence. '
    'name= is a lowercase letter, then up to 39 lowercase letters, digits or hyphens. '
    'In ref blocks use real ent-/def- references found with tools; never invent ids. '
    'An image artifact written ![caption](adm-...) as a paragraph of its own '
    '(blank lines around it) is drawn there as a figure. '
    "Each block's full attribute rules: check_rendering with syntax=<block> (or all); "
    'check_rendering with text=<draft> lists what will not render, without posting it. '
    'Timers: you may start or stop a timer only when the owner explicitly asked you to, '
    "never by yourself: the request your run carries must be the owner's, still open, and "
    'name that timer exactly as ent-<post>#<name>; a bare word such as its name does not '
    'count, and the permission ends with your run.\n\n'
    + '\n'.join(EXAMPLES.values())
)


def syntax(block=None) -> dict:
    """Each block's full attribute rules and example, for `block` or every
    block (None, "" or "all"). An unknown block names the ones there are."""
    b = str(block or "").strip().lower()
    if b in ("", "all"):
        return {k: _SYNTAX[k] + "\n" + EXAMPLES[k] for k in EXAMPLES}
    if b not in EXAMPLES:
        raise KeyError(f"{block!r} is not a block; there are: {', '.join(EXAMPLES)}")
    return {b: _SYNTAX[b] + "\n" + EXAMPLES[b]}
