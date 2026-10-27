"""Whether a MODEL behind a runtime can actually make a tool call.

A runtime declaring `call_mentis_tools` says the harness offers Mentis's tools
as a real namespace. It does not say the model behind it will CALL them, and
for a model served by a third-party local provider that turned out to be the
whole question. Measured 2026-09-30 on ollama 0.34, codex's own wire
(`POST /v1/responses`, one function tool, `tool_choice: auto`):

    qwen2.5:14b         -> output item `function_call` find {"q": ...}
    qwen3.5:9b          -> output item `function_call` find {"q": ...}
    qwen2.5-coder:14b   -> output item `message`, text '{"name": "find", ...}'

The third is a tool call written as prose. The provider never parses it, the
harness sees no call, takes the text as the final answer, and Mentis posted it
as the Participant's reply (Local LLM Prelim #196-#202) -- `spawn_agent` and
`web_search` "calls" that nothing performed.

AND THE SECOND WAS NOT ENOUGH EITHER. A structured call to ONE PLAIN FUNCTION
is not a call to the tools a dispatched worker is actually given. See "the
demonstration" below: qwen3.5:9b passed the one-function probe and then failed
every Mentis call it made on the real, namespaced surface.

So for a model a local provider serves, the capability is judged per
runtime + provider + model, from a DEMONSTRATION on the surface that runtime
dispatches with, and never from the runtime's declaration alone. Nothing here
names a model family: every model gets the same probe and the same rule.

Hosted models are left to the runtime's own declaration, which was measured
end to end on each runtime and is not what failed here.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

from . import local_models

#: Capabilities a runtime can declare but a model behind it must DEMONSTRATE
#: when a separate provider serves that model. One today; a set, because the
#: rule is about the shape of the claim and not about this one capability.
MODEL_DEPENDENT = frozenset({"call_mentis_tools"})

#: The local providers a demonstration can be made for. The same bases
#: discovery uses; the runtime is what reaches them.
_BASES = {
    "ollama": local_models.OLLAMA_TAGS.rsplit("/api/", 1)[0],
    "lmstudio": local_models.LMSTUDIO_MODELS.rsplit("/v1/", 1)[0],
}

PROBE_TIMEOUT_S = 900

#: A DISPATCH IS NOT A ONE-LINE PROMPT, AND THE PROBE MUST NOT BE EITHER.
#: Measured 2026-09-30: codex sends a local model ~20k input tokens (tool
#: definitions first), and ollama silently cut qwen2.5:14b and qwen3.5:9b to
#: 2,050 tokens -- their default window -- so the tools the harness offered
#: never reached the model. A short probe passed both. So the probe carries
#: about as much as a dispatch does, ahead of the question, and a provider
#: that reports having taken far less than it was sent has not demonstrated
#: anything usable.
PROBE_FILLER = ("This paragraph is background material for the request "
                "that follows and needs no reply. ") * 1400
PROBE_MIN_INPUT_TOKENS = 16000

#: A demonstration is kept until the model it was made with changes. Ollama
#: reports a digest; where none is reported the result is kept for this long
#: and then asked again, rather than trusted forever.
UNDIGESTED_TTL_S = 24 * 3600

#: How many set-aside verdicts an entry keeps as its history.
HISTORY_KEPT = 20


def _ledger_path() -> str:
    return os.environ.get("MENTIS_TOOL_USE_LEDGER") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
        "Mentis", "Mark-IV", "tool-use-demonstrations.json")


def _digest(provider: str, model: str) -> str | None:
    if provider != "ollama":
        return None
    doc = local_models._get_json(local_models.OLLAMA_TAGS) or {}
    for m in doc.get("models", []):
        if (m.get("name") or m.get("model")) == model:
            return m.get("digest")
    return None


# -- what a tool call written as text looks like -----------------------------

_FENCE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?(.*?)\n?```$", re.DOTALL)
_TAGGED = re.compile(r"<\s*/?\s*(tool_call|function_call|tool_use)\b", re.I)


def _call_shaped(obj) -> bool:
    if isinstance(obj, list):
        return bool(obj) and all(_call_shaped(o) for o in obj)
    if not isinstance(obj, dict):
        return False
    if isinstance(obj.get("function"), dict):
        obj = obj["function"]
    return (isinstance(obj.get("name"), str)
            and any(k in obj for k in ("arguments", "parameters", "args",
                                       "input")))


def textual_tool_call(text: str | None) -> bool:
    """Is this whole answer a tool call written out instead of made?

    STRUCTURAL, NOT A LIST OF NAMES. True when the entire reply -- optionally
    in one code fence -- is a JSON object (or list of them) shaped like a
    call: a string `name` plus `arguments`/`parameters`, or when it carries a
    tool-call tag the provider was meant to parse. An answer that merely
    CONTAINS JSON, or talks about tools, is not this.
    """
    s = (text or "").strip()
    if not s:
        return False
    if _TAGGED.search(s) and len(_TAGGED.sub("", s)) < len(s):
        inner = re.sub(r"<[^>]+>", "", s).strip()
        try:
            if _call_shaped(json.loads(inner)):
                return True
        except ValueError:
            pass
    m = _FENCE.match(s)
    if m:
        s = m.group(1).strip()
    if not s.startswith(("{", "[")):
        return False
    try:
        return _call_shaped(json.loads(s))
    except ValueError:
        return False


# -- the demonstration --------------------------------------------------------
#
# THE PROBE IS A DISPATCH, NOT A REQUEST THAT LOOKS LIKE ONE. It used to be a
# single request straight to the provider offering one plain function
# (`lookup_entry`), and a structured call back to it was taken as the model
# being able to use Mentis's tools. FOUND WRONG in a disposable-Brain
# experiment: codex+ollama+qwen3.5:9b held a `supported` verdict from that
# probe, so it advertised `call_mentis_tools` and was selected for work that
# required it -- and on the real surface, where the tools are the NAMESPACED
# `mcp__mentis` set, every Mentis call it made (`read_artifact`, with no
# namespace) came back from codex as `unsupported call: read_artifact`. A
# plain function is not the interface a dispatched worker is handed.
#
# So the demonstration is now made by the runtime's own adapter, through its
# own `run`, with an Invocation shaped exactly as Foundation shapes an
# ordinary dispatched worker's: a provisioned home, the `mentis` MCP server
# started by the same boot command with an ordinary worker's `permits`, the
# same sandbox and the same withheld surface. Only the owner the server asks
# is a stand-in (`_DemoOwner`), which answers one `read_artifact` and nothing
# else. The model is asked to read that artifact. SUPPORTED means the call
# ARRIVED at the owner through the namespaced Mentis server -- not that the
# model said it called, and not that the runtime reported an item.

#: The identity of THIS way of demonstrating, stored on every probe verdict.
#: A verdict made any other way -- every entry the single-function probe
#: wrote carries none -- grants nothing any more, and is kept as history.
DEMONSTRATION = "dispatch-surface/2"

#: What an entry written by the old one-function probe is called when it is
#: set aside. It never said; this is what it was.
LEGACY_DEMONSTRATION = "single-function/1"

#: How a verdict from a real dispatched run is marked. An observed failure
#: was made ON the dispatch surface, so it counts whatever probe was current.
OBSERVED = "observed in a dispatched run"

#: The record name the demonstration's owner answers for. Not a corpus: the
#: stand-in owner holds no record and refuses any other name.
DEMO_RECORD = "mentis-tool-use-demonstration"

#: The one artifact the demonstration's owner will serve.
DEMO_REF = "adm-7e57c0de0001"


class _DemoOwner:
    """A stand-in for `/api/worker` that serves one artifact and records every
    call that reaches it. Loopback only, one grant, gone when closed."""

    def __init__(self) -> None:
        import base64
        import hashlib
        import secrets
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from mentis.worker import CAPABILITY_HEADER

        self.token = "demo-" + secrets.token_hex(12)
        self.word = "word-" + secrets.token_hex(4)
        self.calls: list[dict] = []
        data = (f"This artifact exists to show that you can read it. "
                f"The code word is {self.word}.\n").encode("utf-8")
        served = {"ref": DEMO_REF, "digest": hashlib.sha256(data).hexdigest(),
                  "size": len(data), "view": "text", "served_as": "text/plain",
                  "name_metadata": "demonstration.txt", "door": "demonstration",
                  "note": "served by a tool-use demonstration, not a record",
                  "ext": ".txt",
                  "bytes_b64": base64.b64encode(data).decode("ascii")}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def _send(self, code, doc):
                body = json.dumps(doc).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):  # noqa: N802 - http.server's name
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    req = json.loads(self.rfile.read(n).decode("utf-8"))
                except ValueError:
                    return self._send(400, {"error": "unreadable request"})
                granted = (self.path.rstrip("/") == "/api/worker"
                           and self.headers.get(CAPABILITY_HEADER) == owner.token
                           and req.get("corpus") == DEMO_RECORD)
                op, args = req.get("op"), req.get("args") or {}
                owner.calls.append({"op": op, "args": args,
                                    "granted": granted})
                if not granted:
                    return self._send(403, {"error": "not this demonstration's grant"})
                if op == "read_artifact" and args.get("ref") == DEMO_REF:
                    return self._send(200, served)
                return self._send(403, {"error": (
                    f"this is a tool-use demonstration: only read_artifact "
                    f"of {DEMO_REF} is answered")})

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def read(self) -> bool:
        """Did the demonstration artifact get asked for, under the grant?"""
        return any(c["granted"] and c["op"] == "read_artifact"
                   and c["args"].get("ref") == DEMO_REF for c in self.calls)

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def demonstration_invocation(model: str, *, workspace: str, answers_at: str,
                             capability: str):
    """The Invocation a demonstration runs: an ORDINARY DISPATCHED WORKER's.

    Every field that decides what the run is offered -- isolation, the record
    it may ask about and where, the grant, `permits`, the private scratch --
    is set the way `Foundation.perform` sets it for a worker dispatched with
    no special scope. `permits` comes from `worker.permitted` exactly as
    `Foundation._permits_for` derives it, so the tools the model is SHOWN are
    the ones an ordinary dispatched worker is shown.
    """
    from mentis.worker import permitted
    from .runtimes.base import Invocation
    return Invocation(
        workspace=workspace, scratch=workspace, model=model,
        prompt=(PROBE_FILLER + "\n\nRead the Mentis artifact " + DEMO_REF
                + " with your read_artifact tool and reply with the code "
                  "word it contains."),
        record=DEMO_RECORD, answers_at=answers_at, capability=capability,
        permits=tuple(permitted(None)), timeout_s=PROBE_TIMEOUT_S)


def probe(adapter, provider: str, model: str) -> dict:
    """Run the adapter's own dispatch with one Mentis read to make.

    SUPPORTED only when the call reached the Mentis server's owner under the
    run's grant -- which is possible only through the namespaced interface a
    dispatched worker is given. UNSUPPORTED when the run went ahead and no
    such call arrived, with what the run did instead. UNKNOWN when nothing
    could be demonstrated at all (no wire measured for this runtime, a run
    that could not start or reached its deadline) -- which satisfies nothing.
    """
    import shutil
    import tempfile
    if (adapter is None or getattr(adapter, "local_tool_wire", None) is None
            or provider not in _BASES):
        return {"verdict": "unknown",
                "evidence": f"no demonstration is possible for provider "
                            f"{provider!r} on "
                            f"{getattr(adapter, 'kind', adapter)!r}"}
    owner = _DemoOwner()
    work = tempfile.mkdtemp(prefix="mk4-tool-demo-")
    res = None
    try:
        res = adapter.run(demonstration_invocation(
            model, workspace=work, answers_at=owner.url,
            capability=owner.token))
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "unknown",
                "evidence": f"the demonstration could not be run: "
                            f"{type(exc).__name__}: {exc}"}
    finally:
        owner.close()
        # A demonstration keeps nothing: not its session, not the copy of
        # the runtime's credential its home holds, not its scratch.
        if res is not None and getattr(res, "runtime_home", None):
            try:
                adapter.discard_session_home(res.runtime_home)
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(work, ignore_errors=True)
    calls = list(res.tool_calls or ())
    said = (res.reported or "").strip()
    if owner.read():
        return {"verdict": "supported",
                "evidence": (f"read_artifact({DEMO_REF}) reached the Mentis "
                             f"server through the dispatch surface (runtime "
                             f"reported calls {calls})")}
    ran = bool(res.session_ref or said or res.raw_events)
    if res.timed_out or not ran:
        return {"verdict": "unknown",
                "evidence": ("the demonstration reached its deadline"
                             if res.timed_out else
                             f"the demonstration run did not start: "
                             f"{res.error or 'no reason given'}")}
    took = (res.usage or {}).get("input_tokens")
    if isinstance(took, int) and took < PROBE_MIN_INPUT_TOKENS:
        return {"verdict": "unsupported",
                "evidence": (f"the provider took only {took} input tokens of "
                             f"a dispatch-sized run (at least "
                             f"{PROBE_MIN_INPUT_TOKENS} expected): it is "
                             f"truncating, so the tools never reach the model")}
    refused = [c["op"] for c in owner.calls
               if not (c["granted"] and c["op"] == "read_artifact"
                       and c["args"].get("ref") == DEMO_REF)]
    return {"verdict": "unsupported",
            "evidence": (f"no Mentis call reached the server through the "
                         f"dispatch surface (runtime reported calls {calls}"
                         + (f"; refused at the owner: {refused}"
                            if refused else "")
                         + ")"
                         + (": the call was written as text instead"
                            if textual_tool_call(said) else "")
                         + (f"; reply began {said[:160]!r}" if said else ""))}


# -- what a verdict was made against -----------------------------------------
#
# OWNER DECISION: results are preserved "against the relevant model, adapter
# and tool configuration, and invalidate[d] when those conditions change."
# The model is the ledger key plus the weights digest; the adapter and tool
# configuration are this fingerprint.

#: The MCP server name dispatch registers Mentis under, which is what makes
#: the namespace `mcp__mentis`.
SERVER_NAME = "mentis"


def surface_fingerprint(adapter) -> dict | None:
    """Everything that decides the Mentis tool surface a dispatched run of
    this adapter is offered, and its hash. None where the adapter cannot say
    (no verdict for it can then be shown to still hold).

    The runtime's version, its withheld flags and catalogue override
    (`dispatch_surface`), the ordinary worker's permitted operation names,
    a hash of exactly those tools' schemas, the server name, and how the
    demonstration is made. A change in any of them is a different surface.
    """
    if adapter is None:
        return None
    try:
        runtime = adapter.dispatch_surface()
    except Exception:  # noqa: BLE001
        return None
    if not runtime:
        return None
    import hashlib
    from mentis.worker import ALL_TOOLS, permitted
    names = sorted(permitted(None))
    schemas = sorted((t for t in ALL_TOOLS if t["name"] in names),
                     key=lambda t: t["name"])
    detail = {
        "runtime": runtime,
        "permitted": names,
        "tool_schemas_sha256": hashlib.sha256(json.dumps(
            schemas, sort_keys=True).encode("utf-8")).hexdigest(),
        "server": SERVER_NAME,
        "demonstration": DEMONSTRATION,
    }
    digest = hashlib.sha256(json.dumps(detail, sort_keys=True).encode(
        "utf-8")).hexdigest()
    return {"sha256": digest, "detail": detail}


class Ledger:
    """Demonstrations, keyed runtime|provider|model, kept on this machine.

    Machine-local like everything else Foundation holds: it is a fact about
    what this machine's provider does with this model's weights, not a fact
    the record should carry. Each verdict says how it was reached, and a
    verdict OBSERVED in a real run overrides a probe's.

    READING NEVER RUNS ANYTHING (owner decision: "Do not automatically launch
    a real local-model capability probe during ordinary dispatch. Unknown
    capability is not confirmed capability."). `judge` answers from what is
    stored, and where nothing current is stored the answer is UNKNOWN --
    which satisfies nothing, so the model is not selected for work needing
    Mentis's tools. Only `verify`, asked for explicitly
    (`python -m mentis.foundation.tool_use verify ...`), runs a probe.

    WHAT IS CURRENT. A verdict -- probed or observed -- holds only while the
    model's weights digest AND the surface fingerprint it was made against
    (`surface_fingerprint`) are unchanged. Every entry the single-function
    probe wrote has no fingerprint, so none of them grants anything. Nothing
    is deleted: a verdict that is replaced is kept under the new entry's
    `superseded`.
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._verifying: dict[str, threading.Lock] = {}

    @property
    def path(self) -> str:
        return self._path or _ledger_path()

    def _load(self) -> dict:
        try:
            with open(self.path, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.path)

    @staticmethod
    def key(runtime: str, provider: str, model: str) -> str:
        return f"{runtime}|{provider}|{model}"

    @staticmethod
    def why_not_current(entry: dict | None, digest: str | None,
                        surface: dict | None) -> str | None:
        """None if this verdict still holds, else why it does not."""
        if not entry:
            return "never verified"
        if surface is None:
            return "the runtime cannot describe its tool surface"
        if entry.get("surface") != surface["sha256"]:
            return ("made against a different tool surface"
                    if entry.get("surface") else
                    "made without a tool-surface fingerprint (an earlier "
                    "probe)")
        if digest or entry.get("digest"):
            if entry.get("digest") != digest:
                return "the model's weights have changed"
            return None
        if time.time() - entry.get("at", 0) >= UNDIGESTED_TTL_S:
            return "older than the undigested lifetime"
        return None

    def _current(self, entry: dict | None, digest: str | None,
                 surface: dict | None) -> bool:
        return self.why_not_current(entry, digest, surface) is None

    @staticmethod
    def _replacing(old: dict | None, new: dict) -> dict:
        """`new`, carrying `old` and its history rather than losing them."""
        if not old:
            return new
        past = list(old.get("superseded") or ())
        was = {k: v for k, v in old.items() if k != "superseded"}
        if was.get("how") != OBSERVED and not was.get("demonstration"):
            was["demonstration"] = LEGACY_DEMONSTRATION
        return {**new, "superseded": (past + [was])[-HISTORY_KEPT:]}

    def judge(self, runtime: str, provider: str, model: str,
              adapter=None) -> dict:
        """The stored verdict for this combination if it still holds, else
        UNKNOWN. Never runs a probe, never writes."""
        k = self.key(runtime, provider, model)
        digest = _digest(provider, model)
        surface = surface_fingerprint(adapter)
        with self._lock:
            entry = self._load().get(k)
        why = self.why_not_current(entry, digest, surface)
        if why is None:
            return entry
        return {"verdict": "unknown", "how": "ledger",
                "evidence": (f"not verified for the Mentis tool surface "
                             f"({runtime}+{provider}+{model}: {why}); run "
                             f"the verification: python -m "
                             f"mentis.foundation.tool_use verify --runtime "
                             f"{runtime} --provider {provider} --model "
                             f"{model}")}

    def verify(self, runtime: str, provider: str, model: str,
               adapter) -> dict:
        """RUN the demonstration and store its verdict. Explicit only.

        One at a time per combination: a second caller waits for the first
        and then runs its own, rather than both launching at once.
        """
        k = self.key(runtime, provider, model)
        with self._lock:
            gate = self._verifying.setdefault(k, threading.Lock())
        with gate:
            digest = _digest(provider, model)
            surface = surface_fingerprint(adapter)
            got = probe(adapter, provider, model)
            entry = {**got, "how": "probe", "demonstration": DEMONSTRATION,
                     "at": time.time(), "digest": digest,
                     "surface": surface["sha256"] if surface else None,
                     "surface_detail": surface["detail"] if surface else None}
            if got["verdict"] != "unknown" and surface is not None:
                with self._lock:
                    data = self._load()
                    data[k] = self._replacing(data.get(k), entry)
                    self._save(data)
            return entry

    def observed(self, runtime: str, provider: str, model: str, *,
                 verdict: str, evidence: str, adapter=None) -> None:
        """Record what a real run showed, overriding any probe. Made on the
        dispatch surface, so it carries that surface's fingerprint."""
        k = self.key(runtime, provider, model)
        digest = _digest(provider, model)
        surface = surface_fingerprint(adapter)
        with self._lock:
            data = self._load()
            data[k] = self._replacing(data.get(k), {
                "verdict": verdict, "evidence": evidence, "how": OBSERVED,
                "at": time.time(), "digest": digest,
                "surface": surface["sha256"] if surface else None})
            self._save(data)


# -- the one door that runs a probe -------------------------------------------

def preflight(runtime: str, provider: str, model: str, adapter) -> dict:
    """What a verification would run, said before it runs. Raises
    ValueError where it must not run at all."""
    if adapter is None:
        raise ValueError(f"no runtime {runtime!r} here")
    if provider not in _BASES:
        raise ValueError(f"{provider!r} is not a local provider; only local "
                         f"compute is verified this way")
    served = adapter.provider_of(model)
    if served != provider:
        raise ValueError(f"{model!r} is not served by {provider!r} here "
                         f"(served by: {served!r}); a model that is not "
                         f"local could incur hosted cost, so it is refused")
    surface = surface_fingerprint(adapter)
    if surface is None:
        raise ValueError(f"{runtime} cannot describe its tool surface")
    from mentis.worker import package_root
    return {"runtime": runtime, "provider": provider, "model": model,
            # THE CODE WHOSE TOOL SCHEMAS ARE HASHED: the verdict holds for
            # dispatches from this code, so run the door from the release
            # folder production runs from.
            "code_path": package_root(),
            "weights_digest": _digest(provider, model),
            "surface_sha256": surface["sha256"],
            "surface": surface["detail"],
            "max_duration_s": PROBE_TIMEOUT_S,
            "cost": ("local compute only, no hosted model cost (under a ChatGPT "
                     "login codex still sends its own analytics events)")}


def main(argv=None, *, adapters=None, ledger=None, out=None) -> int:
    """`python -m mentis.foundation.tool_use verify --runtime R --provider P
    --model M [--yes]` -- the owner's explicit door. Without `--yes` it only
    prints what it WOULD run. Nothing triggers it automatically."""
    import argparse
    import sys
    out = out or sys.stdout
    ap = argparse.ArgumentParser(
        prog="python -m mentis.foundation.tool_use",
        description=("Verify one local model on the Mentis tool surface. Run "
                     "it from the production release folder: the Mentis tool "
                     "schemas are hashed from the code it runs, and a verdict "
                     "made by other code does not count for production."))
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="run one tool-use verification")
    v.add_argument("--runtime", required=True)
    v.add_argument("--provider", required=True)
    v.add_argument("--model", required=True)
    v.add_argument("--yes", action="store_true",
                   help="actually start it (otherwise only the preflight "
                        "is printed)")
    args = ap.parse_args(argv)
    if adapters is None:
        from .service import Foundation
        adapters = Foundation()._adapters
    adapter = adapters.get(args.runtime)
    ledger = ledger or Ledger()
    try:
        pre = preflight(args.runtime, args.provider, args.model, adapter)
    except ValueError as exc:
        print(f"refused: {exc}", file=out)
        return 2
    print("tool-use verification -- preflight", file=out)
    for k in ("runtime", "provider", "model", "weights_digest",
              "surface_sha256"):
        print(f"  {k}: {pre[k]}", file=out)
    print(f"  tool schemas hashed from: {pre['code_path']} (run this from "
          f"the production release folder, or the verdict will not match "
          f"production's surface)", file=out)
    print("  surface: " + json.dumps(pre["surface"], sort_keys=True),
          file=out)
    print(f"  maximum duration: {pre['max_duration_s']} s", file=out)
    print(f"  cost: {pre['cost']}", file=out)
    if not args.yes:
        print("not started: pass --yes to run it", file=out)
        return 1
    got = ledger.verify(args.runtime, args.provider, args.model, adapter)
    print(f"verdict: {got['verdict']}", file=out)
    print(f"evidence: {got['evidence']}", file=out)
    stored = got["verdict"] != "unknown" and got.get("surface")
    print(f"stored: {ledger.path} [{Ledger.key(args.runtime, args.provider, args.model)}]"
          if stored else "stored: nothing (unknown is not a result)", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
