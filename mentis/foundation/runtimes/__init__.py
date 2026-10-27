"""The runtimes Mentis knows, in ONE place.

`Foundation` builds its adapters from `adapter_classes`. The names each runtime
goes by -- the names a Participant may never take -- are declared as data in
`mentis.runtime_names`, which imports nothing, so the Conversation layer can
read them without loading any adapter. Every adapter here must be declared
there (`tests/test_participant_rename.py`), so a runtime is never selectable
without its names being reserved.

The adapters are imported when asked for, not when this package is: they
import the worker, which imports the conversation layer.
"""
from __future__ import annotations


def adapter_classes() -> tuple:
    """Every runtime adapter Mentis registers, in selection order."""
    from .antigravity import AntigravityAdapter
    from .claude import ClaudeAdapter
    from .codex import CodexAdapter
    return (ClaudeAdapter, CodexAdapter, AntigravityAdapter)
