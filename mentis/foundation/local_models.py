"""Models served locally on this machine, discovered as ordinary capacity.

This is NOT a local-model subsystem. It is one small read that answers a
question the runtimes cannot answer for themselves, and its output is the same
`ModelInfo` every other model uses, returned from the same `models_list`
operation. A caller cannot tell local models apart except by reading a field
that states where compute happens.

Why Foundation has to do this read at all, measured 2026-09-23:

    codex exec --json --oss --local-provider ollama -m llama3.2:latest "..."
      -> exit 0, agent_message "OK"                        # it RUNS them

    codex_models_manager: failed to refresh available models:
      missing field `models` ... body: {"object":"list","data":[...]}
                                                            # it cannot LIST them

So the runtime can execute a local model but cannot enumerate one. Discovery
therefore comes from the provider that is actually serving them, and execution
still goes through the existing runtime seam. No new execution path exists.

Also measured, and the reason `efforts` is empty here:

    "Model metadata for `llama3.2:latest` not found. Defaulting to fallback
     metadata; this can degrade performance and cause issues."

The runtime has no effort vocabulary for a local model. Inventing one would be
exactly the fabrication the rest of this codebase refuses.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from mentis.api.types import UNKNOWN, ModelInfo

# Providers we know how to ask, in the form (name, url, parser key). Adding one
# is a few lines; it is deliberately not a plugin system.
OLLAMA_TAGS = "http://127.0.0.1:11434/api/tags"
LMSTUDIO_MODELS = "http://127.0.0.1:1234/v1/models"

TIMEOUT_S = 3.0


def _get_json(url: str, timeout: float = TIMEOUT_S) -> dict | None:
    """One short local HTTP read. A provider that is not running is not an error."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - localhost only
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def _from_ollama(runtime: str) -> list[ModelInfo]:
    doc = _get_json(OLLAMA_TAGS)
    if not doc:
        return []
    out: list[ModelInfo] = []
    for m in doc.get("models", []):
        name = m.get("name") or m.get("model")
        if not name:
            continue
        det = m.get("details") or {}
        out.append(
            ModelInfo(
                slug=name,
                runtime=runtime,
                # Measured: the runtime reports no metadata for these, so there
                # is no effort vocabulary to offer. Empty, not guessed.
                efforts=(),
                default_effort=None,
                # /api/tags does not report a context window. None means
                # "not established", never "small".
                context_window=None,
                display_name=name,
                locality="local",
                provider="ollama",
                details={
                    k: v
                    for k, v in (
                        ("parameter_size", det.get("parameter_size")),
                        ("quantization", det.get("quantization_level")),
                        ("family", det.get("family")),
                        ("size_bytes", m.get("size")),
                    )
                    if v is not None
                },
            )
        )
    return out


def _from_lmstudio(runtime: str) -> list[ModelInfo]:
    doc = _get_json(LMSTUDIO_MODELS)
    if not doc:
        return []
    return [
        ModelInfo(
            slug=m.get("id"),
            runtime=runtime,
            efforts=(),
            context_window=None,
            display_name=m.get("id"),
            locality="local",
            provider="lmstudio",
        )
        for m in doc.get("data", [])
        if m.get("id")
    ]


def discover(runtime: str) -> list[ModelInfo]:
    """Local models currently being served, as capacity for `runtime`.

    Returns an empty list when nothing local is running. That is an ordinary
    answer, not a failure: it means this machine is offering no local compute
    right now, which is a different thing from local compute being unsuitable.
    """
    models: list[ModelInfo] = []
    seen: set[str] = set()
    for fn in (_from_ollama, _from_lmstudio):
        for m in fn(runtime):
            if m.slug in seen:
                continue
            seen.add(m.slug)
            models.append(m)
    return models


def providers_present() -> dict[str, bool]:
    """Which local providers answered. Used for reporting, never for ranking."""
    return {
        "ollama": _get_json(OLLAMA_TAGS) is not None,
        "lmstudio": _get_json(LMSTUDIO_MODELS) is not None,
    }
