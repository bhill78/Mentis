"""Every name a runtime Mentis registers goes by, AS DATA, IMPORTING NOTHING.

ONE LIST, READ FROM BOTH SIDES OF A BOUNDARY. The runtime adapters
(`mentis.foundation.runtimes`) take their `names` from here, and the
Conversation layer reads the names a Participant may never take from here
(`conversation.participant_names`). Neither side imports the other: the
Conversation layer must not load the concrete adapters (they import the
worker, which imports the Conversation layer), so the registry it needs is
this module, which imports nothing at all and so drags nothing in.

`kind` -> the other names that runtime goes by (its executable, its product
name). A runtime added to `foundation.runtimes.adapter_classes` must be
declared here as well; `tests/test_participant_rename.py` fails until it is,
so a runtime can never be selectable without its names being reserved.
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
