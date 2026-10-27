"""Every name a runtime Mentis registers goes by, AS DATA, IMPORTING NOTHING.

The Conversation layer reads the names a Participant may never take from here
(`conversation.participant_names`). Mark IV's runtime adapters read it too;
they are gone (agents now run through MARS, `mentis.execution`), and this
data module stays, importing nothing at all.

`kind` -> the other names that runtime goes by (its executable, its product
name).
"""

RUNTIMES = {
    "claude": ("claude code",),
    "codex": ("codex cli",),
    "antigravity": ("agy",),
}

#: Model families, reserved beside the runtimes for the same reason: a
#: Participant called @GPT reads as a choice of model.
MODEL_FAMILIES = ("claude", "gemini", "gpt")


def runtime_names():
    """Every name a registered runtime goes by: its `kind`, then its names."""
    out = []
    for kind, names in RUNTIMES.items():
        for n in (kind, *names):
            if n and n not in out:
                out.append(n)
    return tuple(out)
