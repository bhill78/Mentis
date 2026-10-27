"""Claude Code adapter. Measured against 2.1.280 on Windows.

Everything here corresponds to something in docs/evidence/runtime-probe-claude.md.

The two facts that shaped it:

* The actual model is reported in `modelUsage` and was measured to differ from
  both the requested alias and the configured default. It is read back, never
  echoed.
* Actual effort is not observable on any headless surface: absent from the
  result envelope, absent from SessionStart hook input, and the statusline
  channel that carries it does not fire under -p. `actual_effort` is UNKNOWN.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from mentis.worker import (boot_command as _boot_command,
                           READS as WORKER_READS)

from mentis.api.errors import CatalogueUnavailable
from mentis.api.types import (
    Capability,
    CapacityReading,
    DeliveryOpportunity,
    ModelInfo,
    Observed,
    Provenance,
    RuntimeInfo,
    UsageWindow,
)
from mentis.runtime_names import RUNTIMES

from .base import (Invocation, RunResult, RuntimeAdapter, _decode,
                   substantive_answer)

# -- the model catalogue ----------------------------------------------------
#
# MEASURED AGAINST 2.1.286. `claude -p /model` is answered by the CLI itself:
# num_turns 0, total_cost_usd 0, and the stream's assistant event has model
# `<synthetic>` -- nothing is sent to a model. Its text names the ALIASES the
# CLI accepts. `claude -p /model --model <alias>` then says what that alias
# resolves to: the `init` event's `model` is the ID the CLI would request, and
# the text says the display name. So the catalogue is exactly what the aliases
# resolve to -- NOT the interactive /model menu, which offers models (Sonnet
# 4.6, measured) that no alias reaches. Nothing else is listed or guessed.
#
# `--no-session-persistence`: without it every call left a session transcript
# in ~/.claude/projects -- eleven per reading, measured.

# How long a catalogue is reused. The aliases move with CLI releases, not by
# the minute, and a reading is about eleven CLI launches.
MODELS_FRESH_SECONDS = 600
# How long a FAILED reading is kept, so a broken CLI is not relaunched on every
# composer mount -- and short, so it is asked again soon.
MODELS_RETRY_SECONDS = 60

# Aliases that select a MODE rather than a model. Measured: `opusplan` answers
# "Opus in plan mode, else Sonnet", and its init model is Sonnet's, so offering
# it as a model would name one model while meaning two. Left out, and the
# catalogue says so.
_MODES = frozenset({"opusplan"})

_AVAILABLE = re.compile(r"Available:\s*(.+?)\s*(?:,\s*or a full model ID)?\.?\s*$", re.M)
_CURRENT = re.compile(r"Current model:\s*`([^`]+)`")


def aliases_from(text: str | None) -> list[str] | None:
    """The aliases `/model` says are available, in its order; None when its
    text does not say."""
    m = _AVAILABLE.search(text or "")
    if not m:
        return None
    names = [a.strip() for a in m.group(1).split(",")]
    names = [a for a in names if a and not a.startswith("or ")]
    return names or None


def resolution_from(stream: str | None) -> tuple[str | None, str | None]:
    """(resolved ID, display name) from one `/model --model <alias>` stream."""
    model = display = None
    for line in (stream or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            model = ev.get("model") or model
        elif ev.get("type") == "result":
            hit = _CURRENT.search(str(ev.get("result") or ""))
            display = hit.group(1) if hit else display
    return model, display


SCOPE = ("what Claude's aliases resolve to, not its full /model menu; the "
         "model a run actually used is read from that run")


def catalogue_from(resolved: list[tuple[str, str | None, str | None]],
                   failed: list[str] = ()) -> list[ModelInfo]:
    """One entry per resolved ID, from (alias, resolved ID, display name).

    Aliases that reach the same ID are one model (`opus` and `default`), and
    the entry says which aliases reach it. The slug is the RESOLVED ID: it is
    what the CLI would request, and it names one model where an alias may move.
    A display name two entries share (`Sonnet 5.5` for both `sonnet` and
    `sonnet[1m]`) is told apart by the CLI's own IDs, never by a label made up
    here: where one ID extends the other, the longer one carries the extra
    (`Sonnet 5.5 [1m]`) and the other keeps the name; otherwise both carry
    their full ID. The extra goes at the end of a short label because a
    phone cuts labels from the right, and two rows that read the same once
    cut are no better than one.
    """
    by_id: dict[str, dict] = {}
    modes = [a for a, _, _ in resolved if a in _MODES]
    for alias, model, display in resolved:
        if alias in _MODES or not model:
            continue
        e = by_id.setdefault(model, {"aliases": [], "display": None})
        e["aliases"].append(alias)
        e["display"] = e["display"] or display
    names = [e["display"] for e in by_id.values() if e["display"]]
    scope = SCOPE
    if modes:
        scope += (f"; {', '.join(modes)} {'is a mode' if len(modes) == 1 else 'are modes'}"
                  f", not a model, and left out")
    if failed:
        scope += f"; these aliases could not be resolved: {', '.join(failed)}"
    out = []
    for model, e in by_id.items():
        d = e["display"]
        twins = [o for o in by_id if o != model and by_id[o]["display"] == d]
        if not d:
            label = model
        elif not twins:
            label = d
        elif any(model.startswith(o) for o in twins):
            base = max((o for o in twins if model.startswith(o)), key=len)
            label = f"{d} {model[len(base):]}"
        elif any(o.startswith(model) for o in twins):
            label = d
        else:
            label = f"{d} ({model})"
        out.append(ModelInfo(
            slug=model, runtime="claude", display_name=label,
            locality="hosted",
            details={"aliases": e["aliases"], "catalogue": scope,
                     "resolved_by": "init.model of `claude -p /model --model "
                                    "<alias>`: what the CLI would request, not "
                                    "proof of what ran"},
        ))
    return out


def _transcripts() -> str:
    """Where this runtime keeps the transcripts `--resume` reads.

    `CLAUDE_CONFIG_DIR` is a supported configuration and the root was hard
    coded to `~/.claude`. With it set, every session came back INELIGIBLE --
    "no transcript ... so there is nothing for --resume to continue" -- for
    sessions that resume perfectly well: a false NO stated as fact, which is
    worse than saying nothing. The same root is read for actual effort, which
    went UNKNOWN forever for the same reason. Found by review.
    """
    return os.path.join(
        os.environ.get("CLAUDE_CONFIG_DIR")
        or os.path.join(os.path.expanduser("~"), ".claude"),
        "projects")


def transcript_folder(path: str) -> str:
    """The folder name this runtime files a directory's sessions under.

    LOSSY, AND THAT IS WHY IT IS NEVER THE PROOF. Measured: separators, `.`,
    `_` and `:` all become `-`, so different directories can share a folder.
    This recomputes the one name a known path maps to; it never matches a
    pattern, and a folder is only ever removed after its CONTENTS prove it
    was recorded from that exact path (`discard_transcripts`).
    """
    import re as _re
    return _re.sub(r"[^A-Za-z0-9-]", "-", path)


#: The built-in tools a Scratch answer with selected folders is given: file
#: tools only, each confined by `--restricted`. No Bash, PowerShell or REPL.
SCRATCH_FILE_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep")
#: ... and the ones a Scratch answer that writes nothing is given.
SCRATCH_READ_TOOLS = ("Read", "Glob", "Grep")


#: THE ONLY CHARACTERS A READ-ONLY FOLDER'S PATH MAY HAVE for a deny rule to
#: be trusted with it. The CLI reads a rule's path as a GLOB, unescaped: found
#: by independent review and measured 2026-10-11 on 2.1.296 -- a READ folder
#: named `rd [x]` was written through its deny rule (`[x]` is a character
#: class, so the rule never matches and is silently ignored). Measured to
#: hold: `rd 'a&b,c$d%e=f;g~h`, `rd+@x`, `rd#1`, `rd-é ü`. Everything else --
#: `[ ] { } ( ) * ? !` and any character not listed here -- is not trusted,
#: and such a folder is never given with a deny rule (`rule_expressible`).
_RULE_SAFE = re.compile(r"[\w \-.#'&,$%=;~+@:\\/]+")


def rule_expressible(folder: str) -> bool:
    """Whether a deny rule can name exactly `folder` (see `_RULE_SAFE`)."""
    return bool(_RULE_SAFE.fullmatch(folder))


def read_only_rules(folder: str) -> list[str]:
    r"""The permission rules that keep the file tools from changing anything
    in `folder`, in the spellings MEASURED TO HOLD.

    MEASURED 2026-10-11 on 2.1.296, Windows, `--restricted --permission-mode
    auto` with the folder given by `--add-dir` (plan `ws-e-scratch-paths`):
    `Edit(//c/Users/.../rd/**)` and `Edit(C:\Users\...\rd\**)` each
    refused every write -- Write, Edit, a `..` path, forward slashes, lower-
    and upper-cased spellings -- in the CLI's own words ("File is in a
    directory that is denied by your permission settings"), while reads
    there and writes in another folder went on working. `Edit(//C:/...)`
    was SILENTLY IGNORED: every write landed. So both measured spellings are
    written, and the third never is. `Edit(...)` covers Write as well
    (measured)."""
    f = folder.rstrip("\\/") or folder
    if os.name == "nt" and len(f) >= 2 and f[1] == ":":
        posix = "//" + f[0].lower() + f[2:].replace("\\", "/")
        return [f"Edit({posix}/**)", "Edit(" + f + "\\**)"]
    return [f"Edit(/{f}/**)"]


_WRITES = ("Write", "Edit", "MultiEdit", "NotebookEdit")

#: WHAT A RUN GIVEN WRITABLE ROOTS MAY STILL DO WITHOUT ASKING. Under
#: `dontAsk` anything not allowed is refused, so every tool `auto` let a run
#: use is named here -- except the file-writing ones, which are allowed only
#: inside the roots (`writable_rules`).
#:
#: THE SHELL IS KEPT, BY OWNER DECISION (2026-10-14), reversing the
#: 2026-10-13 one that denied it: "Restore native command execution for
#: Mentis-dispatched agents across all three supported runtimes." Without it
#: every dispatched Claude run -- whatever participant it served -- had
#: Read/Edit/Write/Grep/Glob/agents and could run nothing, not even
#: `git status`. Claude Code's command sandbox does not run on native
#: Windows, so a command is NOT confined to the roots; only the file tools
#: are. Said, not hidden.
#:
#: NOT THE WEB: see `WEB_WITHHELD`.
_UNCONFINED = ("Bash", "PowerShell", "Read", "Glob", "Grep", "Agent",
               "Task", "TodoWrite", "Skill", "ToolSearch", "Monitor")

#: CLAUDE CODE'S OWN WEB TOOLS, WITHHELD FROM EVERY DISPATCHED RUN. The web
#: is a Mentis capability -- `web_search` and `web_fetch`, offered through
#: the grant and recorded by the server -- so a run keeps no private,
#: unrecorded path beside them. Withheld by `--disallowedTools`, which
#: MEASURED 2026-10-22 on 2.1.302, `-p`: removes WebSearch from the tools a
#: run is given under `auto`, and under `dontAsk` wins over a settings rule
#: allowing it by name (the run said it had no such tool). The same flag
#: also took away the `web-fetch` sub-agent's WebFetch: asked to read a
#: page through that agent, the run's sub-agent found no fetching tool,
#: where without the flag it fetched the page. A Scratch answer already has
#: neither (`--tools`), and is left as it was.
WEB_WITHHELD = ("WebSearch", "WebFetch")


def writable_rules(folder: str) -> list[str]:
    """The allow rules that let the file tools write in `folder` and below:
    the spellings `read_only_rules` measured, as allows."""
    return read_only_rules(folder)


def reported_actions(events) -> tuple[dict, ...]:
    """Each file a write tool named in this run's stream, with whether the
    `tool_result` answering it said done or refused -- as the runtime
    reported it (`RunResult.actions`). No result seen is said as unknown.
    A stream it cannot read is said as nothing reported, never as a failed
    run: the answer matters more than this account of it."""
    try:
        return _reported_actions(events)
    except Exception:                                     # noqa: BLE001
        return ()


def _reported_actions(events) -> tuple[dict, ...]:
    out, by_id = [], {}
    for ev in events or ():
        # NOT EVERY EVENT CARRIES A MESSAGE OBJECT: measured, a real run's
        # stream has events whose `message` is a plain string.
        msg = ev.get("message") if isinstance(ev, dict) else None
        blocks = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(blocks, list):
            continue
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if ev.get("type") == "user" and b.get("type") == "tool_result":
                row = by_id.get(b.get("tool_use_id"))
                if row is not None:
                    row["outcome"] = "refused" if b.get("is_error") else "done"
            elif (ev.get("type") == "assistant" and b.get("type") == "tool_use"
                    and b.get("name") in _WRITES):
                args = b.get("input") or {}
                path = args.get("file_path") or args.get("notebook_path")
                if path:
                    row = {"tool": b["name"], "path": str(path),
                           "outcome": "unknown"}
                    by_id[b.get("id")] = row
                    out.append(row)
    return tuple(out)


def _events_in(stream: str) -> list:
    """The JSON events in a (possibly partial) stream; anything else skipped."""
    out = []
    for line in (stream or "").splitlines():
        try:
            out.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue
    return out


def _session_in(stream: str) -> str | None:
    """The session this run announced, out of a partial stream."""
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("subtype") == "init" and ev.get("session_id"):
            return ev["session_id"]
    return None

def _tool_what(name, args) -> str | None:
    """What a tool call is doing, from the arguments the runtime showed."""
    if not isinstance(args, dict):
        return None
    for key in ("command", "description", "file_path", "path", "pattern",
                "url", "query", "prompt"):
        if isinstance(args.get(key), str) and args[key].strip():
            return args[key]
    return None


def _main_tools_open(obs) -> bool:
    return any(t["within"] is None for t in obs.snapshot()["tools"].values())


def _is_helper(obs, task_id) -> bool:
    return str(task_id) in obs.snapshot()["helpers"]


def _helper_via(obs, tool_use_id) -> str | None:
    return next((k for k, h in obs.snapshot()["helpers"].items()
                 if h.get("via") == tool_use_id), None)


class ClaudeAdapter(RuntimeAdapter):
    kind = "claude"
    names = RUNTIMES["claude"]
    #: Honours `Invocation.transient`: `--tools ""` and no saved session.
    transient_ok = True
    #: MEASURED 2026-10-10 on 2.1.296, real run, `--permission-mode auto`:
    #: with `--restricted --tools Read,Write,Edit,Glob,Grep --add-dir <sel>`
    #: a read and a write inside <sel> succeeded, and a read and a write of
    #: a sibling folder were both refused by the CLI itself ("is outside
    #: <cwd>, <sel>; --restricted confines the file tools to the working
    #: directory") -- not by the model, not by the auto classifier. No shell
    #: is offered, so nothing escapes the confinement. See `run`.
    folder_bounded = True
    # input_tokens EXCLUDES cached tokens here: measured input_tokens=2 beside
    # cache_read=15553 and cache_creation=13537 on one small run.
    accounting = "claude.usage.v1"
    # usage is re-readable from ~/.claude/projects/<cwd>/<session>.jsonl
    reobservable = True

    def capabilities(self) -> frozenset[Capability]:
        return frozenset(
            {
                Capability.DISCOVER,
                Capability.INVOKE_HEADLESS,
                Capability.REQUEST_MODEL,
                Capability.OBSERVE_ACTUAL_MODEL,
                Capability.REQUEST_EFFORT,
                # Observable, but NOT where we first looked. Effort is absent from
                # the result envelope and from SessionStart hook input; it is
                # recorded per assistant record in the session transcript on disk.
                # The first probe concluded it was unobservable; that was only
                # true of the envelope.
                Capability.OBSERVE_ACTUAL_EFFORT,
                Capability.OBSERVE_CAPACITY,
                Capability.SESSION_IDENTITY,
                Capability.RESUME,
                Capability.DELIVER_AT_START,
                # The four reads reach a worker here as MCP tools from a
                # temporary `--mcp-config`, each pre-approved BY NAME in
                # `--allowedTools`. Declared is not callable, and the
                # pre-approval is the half that makes it callable.
                Capability.CALL_MENTIS_TOOLS,
                # `--permission-mode auto`, which is what a dispatch runs with.
                Capability.WRITE_UNATTENDED,
                # Its permission mode runs node/vite and a browser from the
                # workspace; UI builds and Playwright reviews have run here.
                Capability.BUILD_UI,
                Capability.DRIVE_BROWSER,
                # What its aliases resolve to, from `claude -p /model`, which
                # the CLI answers itself at no cost -- see `list_models`.
                Capability.LIST_MODELS,
                # NOT declared, and each absence was measured:
                #   DELIVER_TO_LIVE       - a messaging pipe is advertised in
                #                           system/init, but its protocol was not
                #                           investigated, so we do not claim it
                #   ISOLATE_FROM_MACHINE_CONFIG - --bare exists but breaks auth
            }
        )

    @staticmethod
    def _which(name: str) -> str | None:
        """Prefer PATH, then Claude's native per-user installation."""
        found = RuntimeAdapter._which(name)
        if found or name != "claude":
            return found
        native = os.path.join(os.path.expanduser("~"), ".local", "bin",
                              "claude.exe" if os.name == "nt" else "claude")
        return native if os.path.isfile(native) and os.access(native, os.X_OK) else None

    def discover(self, machine_id: str) -> RuntimeInfo:
        exe = self._which("claude")
        if not exe:
            return RuntimeInfo(
                kind=self.kind,
                present=False,
                version=Observed.unknown("claude not on PATH or at its native install location"),
                executable=Observed.unknown("claude not on PATH or at its native install location"),
                capabilities=frozenset(),
                machine_id=machine_id,
            )
        version = Observed.unknown("could not read version")
        try:
            out = self._run([exe, "--version"], timeout=60)
            if out.returncode == 0 and out.stdout.strip():
                version = Observed(
                    out.stdout.strip().split()[0], Provenance.LOCALLY_OBSERVED
                )
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            version = Observed.unknown(f"version probe failed: {exc}")
        return RuntimeInfo(
            kind=self.kind,
            present=True,
            version=version,
            executable=Observed(exe, Provenance.LOCALLY_OBSERVED),
            capabilities=self.capabilities(),
            machine_id=machine_id,
            notes=(
                "executable resolved from PATH or the native per-user install location",
                "the host machine's settings.json and hooks apply to every "
                "invocation; --bare would isolate but was measured to break auth",
            ),
        )

    def delivery_opportunities(self) -> list[DeliveryOpportunity]:
        return [
            DeliveryOpportunity(
                runtime=self.kind,
                moment="session_start",
                mechanism="SessionStart hook supplied per-invocation via --settings; "
                "hookSpecificOutput.additionalContext reaches the agent",
                verified=True,
                note="proved end to end: an injected marker came back in the result",
            ),
            DeliveryOpportunity(
                runtime=self.kind,
                moment="invocation",
                mechanism="--append-system-prompt",
                verified=False,
                note="flag present in --help; not exercised here",
            ),
            DeliveryOpportunity(
                runtime=self.kind,
                moment="live_session",
                mechanism="messaging_socket_path named pipe advertised in system/init, "
                "with msg_lifecycle_v1 / interrupt_receipt_v1 capabilities",
                verified=False,
                note="advertised by the runtime; protocol not investigated, so "
                "DELIVER_TO_LIVE is not declared as a capability",
            ),
        ]

    def _settings_for_delivery(self, deliver: str | None) -> tuple[str | None, str | None]:
        """Write a per-invocation settings file carrying a SessionStart hook.

        This is the measured delivery seam. It never touches the user's own
        settings.json -- the material reaches one invocation and nothing else.
        """
        if not deliver:
            return None, None
        tmp = tempfile.mkdtemp(prefix="mk4-claude-")
        hook_py = os.path.join(tmp, "deliver.py")
        payload = os.path.join(tmp, "payload.txt")
        with open(payload, "w", encoding="utf-8") as fh:
            fh.write(deliver)
        with open(hook_py, "w", encoding="utf-8") as fh:
            fh.write(
                "import json, os, sys\n"
                "sys.stdin.read()\n"
                f"text = open(r{payload!r}, encoding='utf-8').read()\n"
                "print(json.dumps({'hookSpecificOutput': {"
                "'hookEventName': 'SessionStart', 'additionalContext': text}}))\n"
            )
        settings = os.path.join(tmp, "settings.json")
        with open(settings, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "hooks": {
                        "SessionStart": [
                            {
                                "matcher": "startup",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": f'python "{hook_py}"',
                                    }
                                ],
                            }
                        ]
                    }
                },
                fh,
            )
        return settings, tmp

    @staticmethod
    def _with_rules(settings: str | None, tmp: str | None,
                    deny: list[str], *, allow=()) -> tuple[str, str]:
        """This invocation's settings file, with `deny` permission rules
        added -- the delivery file where there is one, else a new one."""
        data = {}
        if settings:
            with open(settings, encoding="utf-8") as fh:
                data = json.load(fh)
        else:
            tmp = tempfile.mkdtemp(prefix="mk4-claude-")
            settings = os.path.join(tmp, "settings.json")
        perms = data.setdefault("permissions", {})
        if deny:
            perms["deny"] = list(perms.get("deny") or ()) + list(deny)
        if allow:
            perms["allow"] = list(perms.get("allow") or ()) + list(allow)
        # ASCII, WITH \u ESCAPES, AND SAID SO. Measured by review on 2.1.296:
        # the same rules written unescaped in the Windows code page did not
        # protect an accented READ folder (`ÅÉ ñ` was written into); the
        # escaped form did. Pinned here and by a test of the file's bytes.
        with open(settings, "w", encoding="ascii") as fh:
            json.dump(data, fh, ensure_ascii=True)
        return settings, tmp

    def _mcp_for_record(self, record: str | None, *, via: str | None = None,
                        capability: str | None = None, permits=None,
                        scratch: str | None = None,
                        project: str | None = None) -> str | None:
        """Write a per-invocation MCP config naming the Mark IV query surface.

        THE WHOLE POINT IS THE `--strict-mcp-config` THAT GOES WITH IT. A
        worker inherits whatever MCP servers the machine has configured, and
        on this machine that is a different Mentis entirely -- a Mark III
        production brain that has nothing to do with the record the work
        belongs to. Measured: a dispatched agent reached for it. Naming our
        own surface without excluding the others would leave a worker with two
        Mentises and no way to tell which one it was being asked about.

        Per invocation and in a temporary directory, so nothing is installed,
        nothing is shared between runs, and the user's own configuration is
        never touched.
        """
        if not record:
            return None
        tmp = tempfile.mkdtemp(prefix="mk4-tools-")
        cfg = os.path.join(tmp, "mcp.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump(
                {"mcpServers": {"mentis": {
                    "type": "stdio",
                    "command": sys.executable,
                    # -I so the interpreter cannot pick up whatever happens to
                    # be on the machine's PYTHONPATH -- which also means it
                    # ignores one we set. Measured: `-m mentis.worker` with
                    # PYTHONPATH in `env` cannot import `mentis` at all, and
                    # the worker sees only CONNECTION_CLOSED. So the path goes
                    # on `sys.path` explicitly, which is what the isolation
                    # was protecting in the first place.
                    "args": ["-I", "-c", _boot_command(
                        record, via=via, capability=capability,
                        permits=permits, scratch=scratch, project=project)],
                }}},
                fh,
            )
        return cfg

    _models_cache: tuple[float, list[ModelInfo] | None, str | None] | None = None
    # A FALLBACK, not the lock a normal instance uses. Kept so that a subclass
    # which does not run this __init__ -- the test stubs -- still finds one.
    _models_lock = threading.Lock()

    def __init__(self) -> None:
        super().__init__()
        # PER INSTANCE, because the cache it guards is per instance: assigning
        # `self._models_cache` makes an instance attribute, so a class-wide
        # lock was serialising adapters that share no state. `_read_catalogue`
        # runs inside it and can take up to two timeouts, so a hung `claude`
        # held every other caller in the process. It now holds only its own.
        self._models_lock = threading.Lock()

    def list_models(self) -> list[ModelInfo]:
        """What this CLI's aliases resolve to, read from the CLI itself.

        One `claude -p /model` names the aliases; one `claude -p /model --model
        <alias>` per alias says what it resolves to. Every call is answered by
        the CLI with no turn and no cost (measured, 2.1.286), and they run side
        by side: about four seconds for the lot, against thirty one by one.

        REUSED for `MODELS_FRESH_SECONDS`, because `/api/execution` asks on
        every composer mount and selection asks too. A failure is kept for
        `MODELS_RETRY_SECONDS` and raised each time it is asked for, so the
        caller says why there is no list rather than showing an empty one.
        """
        with self._models_lock:
            hit = self._models_cache
            if hit:
                age = time.monotonic() - hit[0]
                if hit[1] is not None and age < MODELS_FRESH_SECONDS:
                    return list(hit[1])
                if hit[1] is None and age < MODELS_RETRY_SECONDS:
                    raise CatalogueUnavailable(hit[2])
            try:
                models = self._read_catalogue()
            except CatalogueUnavailable as exc:
                self._models_cache = (time.monotonic(), None, str(exc))
                raise
            self._models_cache = (time.monotonic(), models, None)
            return list(models)

    def _ask_model(self, exe: str, alias: str | None) -> subprocess.CompletedProcess:
        cmd = [exe, "-p", "/model", "--no-session-persistence"]
        if alias is None:
            cmd += ["--output-format", "json"]
        else:
            cmd += ["--model", alias, "--output-format", "stream-json", "--verbose"]
        return self._run(cmd, timeout=60)

    def _read_catalogue(self) -> list[ModelInfo]:
        exe = self._which("claude")
        if not exe:
            raise CatalogueUnavailable("claude not on PATH or at its native install location")
        try:
            out = self._ask_model(exe, None)
        except subprocess.TimeoutExpired:
            raise CatalogueUnavailable("`claude -p /model` did not answer within 60s")
        except Exception as exc:  # noqa: BLE001
            raise CatalogueUnavailable(f"`claude -p /model` failed: "
                                       f"{type(exc).__name__}: {exc}")
        if out.returncode != 0:
            said = (out.stderr or out.stdout or "").strip().splitlines()
            raise CatalogueUnavailable(
                f"`claude -p /model` exited {out.returncode}"
                + (f": {said[0][:200]}" if said else ""))
        try:
            env = json.loads(out.stdout or "")
        except json.JSONDecodeError:
            raise CatalogueUnavailable("`claude -p /model` did not answer in JSON")
        if env.get("is_error") or env.get("num_turns"):
            # A turn means /model went to a model as a prompt: not an answer.
            raise CatalogueUnavailable(
                "`claude -p /model` was not answered by the CLI itself "
                f"(is_error={env.get('is_error')}, num_turns={env.get('num_turns')})")
        aliases = aliases_from(env.get("result"))
        if not aliases:
            raise CatalogueUnavailable(
                "`claude -p /model` did not say which models are available: "
                + repr(str(env.get("result"))[:160]))

        def resolve(alias: str):
            try:
                o = self._ask_model(exe, alias)
            except Exception:  # noqa: BLE001
                return alias, None, None
            if o.returncode != 0:
                return alias, None, None
            return (alias, *resolution_from(o.stdout))

        with ThreadPoolExecutor(max_workers=len(aliases)) as pool:
            resolved = list(pool.map(resolve, aliases))
        failed = [a for a, m, _ in resolved if not m and a not in _MODES]
        models = catalogue_from(resolved, failed)
        if not models:
            raise CatalogueUnavailable(
                "no alias `claude -p /model` named could be resolved: "
                + ", ".join(aliases))
        return models

    def run(self, inv: Invocation) -> RunResult:
        exe = self._which("claude")
        if not exe:
            return RunResult(None, 127, None, Observed.unknown("runtime absent"),
                             Observed.unknown("runtime absent"), error="claude not found")

        writes = inv.file_mode == "write"
        # NEVER A DENY RULE FOR A PATH IT CANNOT NAME EXACTLY: refused before
        # launch rather than run with a rule the CLI would silently ignore.
        # (Scratch copies such a folder in instead -- `scratch_paths`.)
        loose = [f for f in (inv.read_only if inv.transient and writes else ())
                 if not rule_expressible(f)]
        if loose:
            why = (f"cannot keep {loose[0]} read-only: its path has characters "
                   "a permission rule would read as a pattern")
            return RunResult(None, -1, None, Observed.unknown(why),
                             Observed.unknown(why), error=why)
        settings, _tmp = self._settings_for_delivery(inv.deliver)
        # WRITABLE ROOTS CONFINE THE FILE TOOLS. `auto` sends a write outside
        # the working directories to a classifier, which can allow it --
        # measured: a dispatched run wrote C:\Work\<file> unasked. So a run
        # given roots is `dontAsk`, and its file tools may write only in its
        # scratch, its project and those roots ("Permission to use Write has
        # been denied", measured). ITS SHELL IS NOT CONFINED: Claude Code's
        # command sandbox does not run on native Windows, so a command can
        # still write anywhere. It is kept regardless (`_UNCONFINED`, owner
        # decision 2026-10-14): a dispatched agent must be able to run
        # commands. Said, not hidden.
        confined = bool(inv.writable) and not inv.transient
        if confined:
            where = [inv.cwd] + ([inv.project] if inv.project else []) + [
                w for w in inv.writable]
            if not all(rule_expressible(w) for w in where):
                why = ("cannot confine writes: a writable path has characters "
                       "a permission rule would read as a pattern")
                return RunResult(None, -1, None, Observed.unknown(why),
                                 Observed.unknown(why), error=why)
            settings, _tmp = self._with_rules(
                settings, _tmp, [],
                allow=list(_UNCONFINED) + [r for w in where
                                           for r in writable_rules(w)])
        if inv.transient and writes and inv.read_only:
            # FOLDERS CHOSEN TO READ, IN A RUN THAT WRITES ELSEWHERE: denied
            # to the write tools by a rule in this invocation's own settings
            # file, which `--restricted` still applies. See `read_only_rules`.
            settings, _tmp = self._with_rules(
                settings, _tmp, [r for f in inv.read_only
                                 for r in read_only_rules(f)])
        permits = tuple(inv.permits or WORKER_READS)
        tools = self._mcp_for_record(inv.record, via=inv.answers_at,
                                     capability=inv.capability,
                                     permits=permits, scratch=inv.scratch,
                                     project=inv.project)
        # The prompt goes on stdin, never as an argv element -- see base._run.
        # UNATTENDED, AND THE NARROWEST MODE THAT ACTUALLY IS.
        #
        # `acceptEdits` auto-accepted file edits and still gated commands,
        # and headless has nobody to answer a gate -- measured: a dispatched
        # worker got `This command requires approval` and could run nothing,
        # so it could edit a file but never test what it had written.
        #
        # Of the modes this CLI offers, `auto` is the least permissive one
        # that lets a dispatched agent do the work: measured, it ran a
        # command and `git status` with nothing asked. `dontAsk` blocks both
        # shells outright, and `bypassPermissions` gives up more than is
        # needed. The owner's decision is that a deliberately dispatched
        # agent may do what they would have approved interactively -- which
        # is what this mode is, and no more than it.
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose",
               "--permission-mode", "dontAsk" if confined else "auto"]
        if inv.transient:
            # WITH NO FOLDER SELECTED, A SCRATCH ANSWER READS AND SAYS; IT
            # DOES NOTHING. `--tools ""`
            # removes every built-in tool -- no shell, no file edits, no web
            # -- so what the run has is exactly the Mentis tools allowed
            # below, which for a transient grant are the reads `permitted`
            # gives it, all unrecorded. And no session is saved, because
            # nothing is ever to be resumed: the next question is answered
            # from the persisted Scratch, rebuilt.
            #
            # WITH FOLDERS THE OWNER SELECTED, the file tools and nothing else,
            # confined by the CLI to the working directories: this run's
            # private scratch and exactly those folders (`--restricted`, which
            # also drops every shell and WebFetch unless named, and ignores
            # user/project settings). No shell, because a shell is not
            # confined. Owner ruling 2026-10-10; measured, see
            # `folder_bounded`.
            #
            # A RUN THAT WRITES NOTHING gets the read tools only: what the owner
            # chose to read is read-only because nothing could write it.
            if inv.file_mode:
                given = SCRATCH_FILE_TOOLS if writes else SCRATCH_READ_TOOLS
                cmd += ["--restricted", "--tools", ",".join(given),
                        "--no-session-persistence"]
                for folder in inv.access:
                    cmd += ["--add-dir", folder]
            else:
                cmd += ["--tools", "", "--no-session-persistence"]
        else:
            # NO WEB BUT MENTIS'S, with or without roots: `WEB_WITHHELD`.
            cmd += ["--disallowedTools", ",".join(WEB_WITHHELD)]
        if inv.model:
            cmd += ["--model", inv.model]
        if inv.effort:
            cmd += ["--effort", inv.effort]
        if settings:
            cmd += ["--settings", settings]
        if tools:
            # Ours, and ONLY ours: see `_mcp_for_record`.
            #
            # ALLOWED EXPLICITLY, because a tool a worker may not call is a
            # tool it does not have. Measured: with the server connected but
            # unpermitted, a worker reported every call blocked and could
            # answer nothing -- which is the same outcome as having no query
            # surface, reached by a different route.
            #
            # NAMING EACH TOOL RATHER THAN A WILDCARD, so the list is auditable
            # and a new tool has to be added deliberately. It is a PERMISSION
            # list and not an authority: the four reads plus the operations are
            # pre-approved here because a headless run has nobody to approve
            # anything, and WHETHER ANY OF THEM IS ADMISSIBLE is decided by the
            # grant at `/api/worker`, per run. Pre-approving an operation this
            # execution may not perform costs nothing -- the server refuses it
            # and says what scope would have been needed.
            cmd += ["--mcp-config", tools,
                    "--allowedTools",
                    *[f"mcp__mentis__{n}" for n in permits]]
        # STRICT ON EVERY LAUNCH, not only the ones that got a corpus.
        # FOUND BY REVIEW: this sat inside `if tools:`, so isolation was
        # decided by whether Foundation had been told the record -- not by
        # the launch. Without it the machine-wide registry, the project
        # `.mcp.json` and plugin-supplied servers all load, and the whole
        # reason a home is provisioned at all is to keep another system
        # that registers itself under the name `mentis` out of this run.
        # A capacity probe took that path, and so would any embedder that
        # dispatched work without calling `reads()` first. With no
        # `--mcp-config` this flag means NO servers, which is the correct
        # answer when there is no corpus to offer.
        #
        # `--allowedTools` above is a PERMISSION list, not a tool set, so it
        # is this flag -- not that one -- that bounds what exists. What keeps
        # the surface to four READS is that the server named here serves
        # exactly the four read-only ops and nothing else.
        cmd.append("--strict-mcp-config")
        if inv.project:
            # STARTED IN PRIVATE SCRATCH, GIVEN THE PROJECT BY NAME. The
            # process's own directory is this execution's alone; the shared
            # project is added deliberately rather than being where it lives.
            cmd += ["--add-dir", inv.project]
        if confined:
            for w in inv.writable:
                if w != inv.project:
                    cmd += ["--add-dir", w]
        if inv.resume_ref and not inv.transient:
            cmd += ["--resume", inv.resume_ref]

        try:
            out = self._run(cmd, cwd=inv.cwd, timeout=inv.timeout_s,
                            stdin=inv.prompt, observer=inv.observer,
                            parse=self.observe_event,
                            **({"cancel_event": inv.cancel_event}
                               if inv.cancel_event is not None else {}))
        except subprocess.TimeoutExpired as exc:
            # A DEADLINE THE CALLER ASKED FOR, NOT A RUNTIME FAILURE. Said
            # as itself so nothing downstream has to read it out of an
            # error string, and so what had already been delivered to a
            # running process is not mistaken for never having crossed.
            # The session is taken out of the partial stream: a run stopped
            # at a chosen boundary is exactly the one worth continuing.
            #
            # AND WHAT IT HAD ALREADY DONE TO FILES: a file written before
            # the deadline is written, so it is reported like any other.
            partial = self._partial(exc)
            return RunResult(_session_in(partial), -1, None,
                             Observed.unknown("deadline reached"),
                             Observed.unknown("deadline reached"),
                             error=str(exc), timed_out=True,
                             actions=reported_actions(_events_in(partial)))
        except Exception as exc:  # noqa: BLE001
            # A CANCELLED run carries what it had said (`RunCancelled`), so
            # files it wrote first are reported too; any other failure has
            # nothing to read and reports nothing.
            said = getattr(exc, "output", None)
            return RunResult(None, -1, None, Observed.unknown("run failed"),
                             Observed.unknown("run failed"),
                             error=f"{type(exc).__name__}: {exc}",
                             actions=reported_actions(_events_in(
                                 said if isinstance(said, str)
                                 else _decode(said)[0] if said else "")))
        finally:
            # Scratch, not a session: a settings file and an MCP registry
            # for this one invocation. The transcript this runtime resumes
            # from lives in the user's own home and is not touched.
            self._discard_scratch(_tmp,
                                  os.path.dirname(tools) if tools else None)

        events: list[dict] = []
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        tools_used: list[str] = []
        session_ref = None
        actual_model = Observed.unknown("no modelUsage in result envelope")
        reported = None
        usage: dict = {}
        capacity = None
        reported_cost = None
        answers: list[str] = []
        # Exit 0 with an empty stream is a real failure mode here, not a quiet
        # success. Treating it as success is how a silent no-op gets reported as
        # work done.
        error = None if events else "runtime produced no events despite exiting cleanly"

        for ev in events:
            if ev.get("type") == "assistant":
                # TOOL USE AS THIS RUNTIME REPORTS IT. Its stream names each
                # tool in an assistant content block, so the observation is a
                # read of what happened rather than a claim about the model.
                for block in ((ev.get("message") or {}).get("content") or []):
                    if block.get("type") == "tool_use" and block.get("name"):
                        tools_used.append(str(block["name"]))
            if ev.get("subtype") == "init":
                session_ref = ev.get("session_id") or session_ref
            if ev.get("type") == "rate_limit_event":
                capacity = self._capacity_from_event(ev.get("rate_limit_info") or {})
            if ev.get("type") == "result":
                session_ref = ev.get("session_id") or session_ref
                reported = ev.get("result")
                if isinstance(reported, str) and reported.strip():
                    answers.append(reported)
                usage = ev.get("usage") or {}
                if ev.get("is_error"):
                    error = ev.get("result") or ev.get("terminal_reason")
                if isinstance(ev.get("total_cost_usd"), (int, float)):
                    reported_cost = ev["total_cost_usd"]
                mu = ev.get("modelUsage") or {}
                if mu:
                    # The runtime names the model that actually ran. Read it back;
                    # this is the field that caught a requested alias resolving to
                    # a different model entirely.
                    slug = next(iter(mu))
                    canonical = (mu[slug] or {}).get("canonicalModel") or slug
                    actual_model = Observed(canonical, Provenance.PROVIDER_REPORTED)

        if answers:
            # ONE RESULT PER TURN, and the last is not always the answer.
            reported = substantive_answer(answers)

        return RunResult(
            session_ref=session_ref,
            exit_code=out.returncode,
            reported=reported,
            # Observed, and the flag says this runtime does report it -- so an
            # empty tuple means no tool was called, not that we could not see.
            tool_calls=tuple(tools_used),
            tool_calls_observable=True,
            actions=reported_actions(events),
            actual_model=actual_model,
            actual_effort=self._effort_from_transcript(session_ref),
            usage=usage,
            capacity=capacity,
            error=error,
            raw_events=events,
            reported_cost_usd=reported_cost,
            transport_ok=getattr(out, "transport_ok", True),
            transport_note=getattr(out, "transport_note", None),
        )

    # -- while it runs ---------------------------------------------------------
    #
    # MEASURED on 2.1.280, `-p --output-format stream-json --verbose`, with the
    # arrival time of every line (tests/fixtures/runtime_streams/claude_*):
    #
    #   system/init             session_id, model -- the prompt was accepted
    #   system/thinking_tokens  an explicit, running estimate of thinking tokens
    #   assistant               content blocks: thinking, text, tool_use{id,name,
    #                           input}; `parent_tool_use_id` set when the message
    #                           is a HELPER's (a subagent's), not the main turn's
    #   user                    tool_result{tool_use_id} -- that call finished
    #   system/task_started     task_id, tool_use_id, task_type, is_backgrounded:
    #                           a background `Agent` is `local_agent`, True
    #   system/task_progress    what a task is doing now
    #   system/task_notification  status: the task finished
    #   result                  the turn's result -- and NOT always the last
    #                           event: with a background helper, a first result
    #                           was followed by the helper's completion and a
    #                           second turn, and a second result
    #
    # So this stream establishes tool calls, background helpers and their end,
    # control returning to the model, and explicit thinking. It does not
    # establish what a silent model is doing, and nothing here says.
    observes = ("session", "tools", "helpers", "model-turns", "thinking")

    def observe_event(self, ev: dict, obs) -> None:
        kind, sub = ev.get("type"), ev.get("subtype")
        parent = ev.get("parent_tool_use_id")
        if kind == "system":
            if sub == "init":
                obs.saw("session started")
                obs.session(ev.get("session_id"))
                obs.model_reported(ev.get("model"))
                obs.awaiting_model()
            elif sub == "thinking_tokens":
                obs.saw("thinking tokens reported")
                obs.thinking_reported()
            elif sub == "task_started":
                obs.saw(f"task started: {ev.get('task_type') or 'task'}")
                # A FOREGROUND task is the tool call already open; only a
                # backgrounded one outlives its tool call and is a helper.
                if ev.get("is_backgrounded"):
                    obs.helper_started(ev.get("task_id"), ev.get("task_type"),
                                       ev.get("description"),
                                       via=ev.get("tool_use_id"))
            elif sub == "task_progress":
                obs.saw("task progress")
                obs.helper_event(ev.get("task_id"), ev.get("description"))
            elif sub == "task_notification":
                obs.saw(f"task {ev.get('status') or 'ended'}")
                was_helper = _is_helper(obs, ev.get("task_id"))
                obs.helper_ended(ev.get("task_id"))
                # MEASURED: a background helper's end is handed to the main
                # model, whose next turn follows. Control is with it again.
                if was_helper and not _main_tools_open(obs):
                    obs.model_answered()
                    obs.awaiting_model()
            else:
                obs.saw(f"system {sub or 'event'}")
            return
        if kind == "assistant":
            blocks = [b for b in ((ev.get("message") or {}).get("content") or [])
                      if isinstance(b, dict)]
            kinds = [b.get("type") for b in blocks]
            obs.saw(("helper " if parent else "") + "assistant "
                    + (",".join(k for k in kinds if k) or "message"))
            if not parent:
                # The main model is speaking: a turn it ended is not the
                # run's end (`RunObservation.settle_due`).
                obs.turn_resumed()
            for b in blocks:
                if b.get("type") == "tool_use":
                    obs.tool_started(b.get("id") or b.get("name"),
                                     b.get("name"),
                                     _tool_what(b.get("name"), b.get("input")),
                                     within=parent)
            if parent:
                helper = _helper_via(obs, parent)
                if helper:
                    obs.helper_event(helper, "assistant "
                                     + ",".join(k for k in kinds if k))
            elif "tool_use" not in kinds:
                # The model produced output and has not handed control to a
                # tool or ended its turn (`result`): its response is still
                # outstanding, measured from THIS output.
                obs.model_answered()
                obs.awaiting_model()
                if "thinking" in kinds:
                    obs.thinking_reported()
            return
        if kind == "user":
            results = [b for b in ((ev.get("message") or {}).get("content") or [])
                       if isinstance(b, dict) and b.get("type") == "tool_result"]
            obs.saw(("helper " if parent else "") + "tool result"
                    if results else "user message")
            for b in results:
                obs.tool_ended(b.get("tool_use_id"))
            if results and not parent and not _main_tools_open(obs):
                obs.awaiting_model()
            return
        if kind == "result":
            obs.saw("result")
            obs.runtime_terminal(
                not ev.get("is_error") and ev.get("subtype") in (None, "success"),
                ev.get("terminal_reason") or ev.get("subtype")
                or ("error" if ev.get("is_error") else "result"))
            return
        obs.saw(str(kind or "event"))

    def consumption(self, res):
        """Claude is the only measured runtime that reports its own cost.

        `total_cost_usd` / `modelUsage[m].costUSD` arrive with the runtime's own
        `costBasis: "list"` and `provider: "firstParty"`. It is taken verbatim;
        no pricing table is consulted anywhere in Mark IV.
        """
        c = super().consumption(res)
        if c is None or res.reported_cost_usd is None:
            return c
        from dataclasses import replace

        return replace(
            c,
            reported_cost_usd=Observed(
                res.reported_cost_usd, Provenance.PROVIDER_REPORTED,
                note="reported by the runtime itself (costBasis 'list'); not priced here",
            ),
        )

    def forget_transient(self, scratch: str, *, root: str | None = None) -> str:
        """After a Scratch answer: remove the per-directory folder this CLI
        makes for the run's working directory, ONLY if it holds no file at
        all. `--no-session-persistence` keeps the transcript out of it, but
        the CLI still creates the folder (and sometimes an empty `memory/`),
        one per answer. A folder holding anything is kept and said."""
        import shutil as _shutil
        folder = os.path.join(root or _transcripts(), transcript_folder(scratch))
        if not os.path.isdir(folder):
            return "absent"
        for _, _, files in os.walk(folder):
            if files:
                return "kept: it holds files"
        _shutil.rmtree(folder, ignore_errors=True)
        return "removed"

    def discard_transcripts(self, scratch: str, sessions, *,
                            root: str | None = None) -> dict:
        """Remove the transcript folder a released Mentis scratch left, IF
        Mentis can prove it is exactly that and nothing else. Says why not.

        AS DECIDED (Artifacts & Files #28, rule written up in #29). The caller
        has already established rules 1 and 4 -- the scratch path is one Mentis
        provisioned for an execution the record names, and that execution was
        relinquished. This establishes the rest from the folder itself:

          2. the folder is the ONE name recomputed from that path, directly
             under the projects root -- never a pattern;
          3. every transcript in it records `cwd` equal to that exact path and
             only `sessionId`s the record attributes to that execution; a line
             that does not parse is uncertainty, not noise;
          5. it holds nothing else: `<session>.jsonl`, a `<session>/`
             directory of that session's own files, and an EMPTY `memory/`.

        Anything uncertain is KEPT and reported with the reason. No fallback by
        name, and nothing outside that one folder is ever touched. This is
        lifecycle cleanup for execution state Mentis created, beside
        `discard_session_home`; it is not Claude-history housekeeping.
        """
        import json as _json
        import shutil as _shutil
        base = root or _transcripts()
        name = transcript_folder(scratch)
        folder = os.path.join(base, name)
        out = {"folder": folder, "scratch": scratch}
        if not os.path.isdir(folder):
            return {**out, "state": "absent"}
        sessions = {s for s in (sessions or ()) if s}
        if not sessions:
            return {**out, "state": "kept",
                    "why": "the record attributes no session to this "
                           "execution, so nothing in the folder can be "
                           "shown to be its own"}
        want = os.path.normcase(os.path.normpath(scratch))

        def check_transcript(path) -> str | None:
            cwd_seen = False
            try:
                with open(path, encoding="utf-8") as fh:
                    for n, line in enumerate(fh, 1):
                        if not line.strip():
                            continue
                        try:
                            row = _json.loads(line)
                        except ValueError:
                            return f"{path} line {n} does not parse"
                        if not isinstance(row, dict):
                            return f"{path} line {n} is not a record"
                        cwd = row.get("cwd")
                        if cwd is not None:
                            cwd_seen = True
                            if os.path.normcase(os.path.normpath(str(cwd))) \
                                    != want:
                                return (f"{path} was recorded in {cwd}, not "
                                        f"{scratch}")
                        sid = row.get("sessionId")
                        if sid is not None and sid not in sessions:
                            return (f"{path} holds session {sid}, which the "
                                    "record does not attribute to this "
                                    "execution")
            except (OSError, UnicodeDecodeError) as exc:
                return f"{path} could not be read: {exc}"
            if not cwd_seen:
                return f"{path} records no directory at all"
            return None

        transcripts = 0
        for entry in sorted(os.listdir(folder)):
            path = os.path.join(folder, entry)
            stem, ext = os.path.splitext(entry)
            if os.path.isfile(path) and ext == ".jsonl":
                if stem not in sessions:
                    return {**out, "state": "kept",
                            "why": f"{entry} is not a session the record "
                                   "attributes to this execution"}
                why = check_transcript(path)
                if why:
                    return {**out, "state": "kept", "why": why}
                transcripts += 1
            elif os.path.isdir(path) and entry == "memory":
                if os.listdir(path):
                    return {**out, "state": "kept",
                            "why": "memory/ is not empty; what is in it is "
                                   "not shown to be this execution's"}
            elif os.path.isdir(path) and entry in sessions:
                for dirpath, _dirs, files in os.walk(path):
                    for fname in files:
                        if fname.endswith(".jsonl"):
                            why = check_transcript(os.path.join(dirpath,
                                                                fname))
                            if why:
                                return {**out, "state": "kept", "why": why}
            else:
                return {**out, "state": "kept",
                        "why": f"{entry} is not something this runtime writes "
                               "for these sessions"}
        if not transcripts:
            return {**out, "state": "kept",
                    "why": "no transcript in it names this execution's "
                           "sessions"}
        try:
            _shutil.rmtree(folder)
        except OSError as exc:
            return {**out, "state": "kept",
                    "why": f"proven, but could not be removed: {exc}"}
        return {**out, "state": "removed", "transcripts": transcripts}

    def resume_eligibility(self, *, session_ref, workspace=None,
                           runtime_home=None):
        """Read the transcript `--resume` reads, and check it is that session.

        HOW FAR THIS EVIDENCE ACTUALLY GOES, SAID PRECISELY. `--resume <id>`
        reads a session file under `~/.claude/projects/<mangled-cwd>/`, so
        three things are checked and no more: the file is there, it parses,
        and it names this session. A path existing was the old answer and it
        was too weak -- a directory or a half-written file satisfied it.

        THE WORKSPACE IS PART OF IT. The transcript records its own `cwd`,
        and this runtime looks for sessions under the directory for the cwd
        it is invoked in. A session recorded somewhere else is not resumable
        here, so a mismatch is ineligible rather than hopeful.

        WHAT IT IS NOT. The provider is not asked. Claude offers no
        read-only way to validate a session id -- `--resume` is the only
        one and it costs a model call -- so this is evidence about the
        artifact on this machine, and the reason says so rather than
        implying the provider agreed.
        """
        from mentis.api.types import ResumeEligibility
        if not session_ref:
            return ResumeEligibility.no(
                "no session reference, so there is no session to continue")
        import glob as _glob
        import json as _json
        root = _transcripts()
        found = _glob.glob(os.path.join(root, "*", f"{session_ref}.jsonl"))
        if not found:
            return ResumeEligibility.no(
                f"no transcript for that session id under {_transcripts()}, "
                "so there is nothing for --resume to continue")
        path = found[0]
        named, cwds, lines, bad = False, set(), 0, 0
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        row = _json.loads(line)
                    except ValueError:
                        bad += 1
                        continue
                    lines += 1
                    if row.get("sessionId") == session_ref:
                        named = True
                    if row.get("cwd"):
                        cwds.add(os.path.normcase(str(row["cwd"])))
        except OSError as exc:
            return ResumeEligibility.unknown(
                f"a transcript is there but could not be read: {exc}")
        if not lines:
            return ResumeEligibility.no(
                f"the transcript at {path} holds no readable records")
        if not named:
            return ResumeEligibility.no(
                f"the transcript at {path} does not name session "
                f"{session_ref}")
        if workspace and cwds and os.path.normcase(workspace) not in cwds:
            return ResumeEligibility.no(
                f"that session was recorded in {sorted(cwds)[0]}, not "
                f"{workspace}, and this runtime resumes per directory")
        # FOUND BY REVIEW: BOTH OF THESE USED TO COME BACK `ELIGIBLE`.
        # A transcript with malformed records was accepted because parse
        # failures were skipped in silence, and one that named no directory
        # skipped the workspace check entirely -- so `eligible` was asserted
        # without the evidence the word claims. Neither is a NO: the session
        # may well be resumable. They are simply not established.
        if bad:
            return ResumeEligibility.unknown(
                f"{bad} of {lines + bad} records in {path} did not parse, so "
                "what state that session is in cannot be established here")
        if workspace and not cwds:
            return ResumeEligibility.unknown(
                f"the transcript at {path} names this session but records no "
                "directory, and this runtime resumes per directory, so it "
                "cannot be confirmed as resumable from this workspace")
        return ResumeEligibility.yes(
            f"the transcript --resume reads names this session, holds "
            f"{lines} readable records and was recorded in this workspace: "
            f"{path} (a local artifact check; this runtime offers no "
            f"read-only way to ask the provider)")
    def _effort_from_transcript(self, session_ref: str | None) -> Observed:
        """Read the effort the runtime actually recorded for this session.

        Not in the result envelope and not in hook input -- the first probe
        checked both and wrongly concluded effort was unobservable. It is on
        each assistant record in the session transcript:
        ~/.claude/projects/<mangled-cwd>/<session_id>.jsonl

        The transcript is machine-local and path-keyed, so this is an
        observation about this machine, never durable corpus meaning.
        """
        if not session_ref:
            return Observed.unknown("no session id, so no transcript to read")
        root = _transcripts()
        import glob as _glob

        matches = _glob.glob(os.path.join(root, "*", f"{session_ref}.jsonl"))
        if not matches:
            return Observed.unknown("session transcript not found on this machine")
        try:
            latest = None
            with open(matches[0], encoding="utf-8") as fh:
                for line in fh:
                    if '"effort"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("type") == "assistant" and rec.get("effort"):
                        latest = rec["effort"]
            if latest:
                return Observed(latest, Provenance.PROVIDER_REPORTED,
                                note="from the session transcript, not the result envelope")
        except OSError as exc:
            return Observed.unknown(f"could not read transcript: {exc}")
        return Observed.unknown("no effort recorded on any assistant record")

    def _capacity_from_event(self, info: dict) -> CapacityReading:
        """Translate Claude's unifiedWindows into windows, units made explicit.

        Claude reports utilization already as a 0..1 fraction. No rescaling, no
        blending, and the provider's own object is kept in `raw`.
        """
        now = time.time()
        windows: list[UsageWindow] = []
        for label, seconds in (("five_hour", 5 * 3600), ("seven_day", 7 * 86400)):
            w = (info.get("unifiedWindows") or {}).get(label)
            if not w:
                continue
            windows.append(
                UsageWindow(
                    label=label,
                    used_fraction=w.get("utilization"),
                    window_seconds=seconds,
                    resets_at=w.get("resetsAt"),
                    provenance=Provenance.PROVIDER_REPORTED,
                    raw=dict(w),
                )
            )
        return CapacityReading(
            runtime=self.kind,
            machine_id="",
            observed_at=now,
            windows=tuple(windows),
            plan=Observed(info.get("overageStatus"), Provenance.PROVIDER_REPORTED)
            if info.get("overageStatus")
            else None,
            notes=("from the rate_limit_event on the stream-json stream; "
                   "account-level, not machine-level",),
        )

    def observe_capacity(self, machine_id: str) -> CapacityReading:
        """Capacity arrives in-band, so observing it costs a real invocation.

        There is no cheaper measured path: the statusline channel that community
        tools use does not fire headless.
        """
        res = self.run(
            Invocation(
                workspace=os.getcwd(),
                prompt="Reply with the single word: ok",
                model=None,
                timeout_s=180,
            )
        )
        if res.capacity is None:
            return CapacityReading(
                runtime=self.kind, machine_id=machine_id, observed_at=time.time(),
                notes=("no rate_limit_event arrived on this invocation",),
            )
        c = res.capacity
        return CapacityReading(
            runtime=c.runtime, machine_id=machine_id, observed_at=c.observed_at,
            windows=c.windows, plan=c.plan, notes=c.notes,
        )
