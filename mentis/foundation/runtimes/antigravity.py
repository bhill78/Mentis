"""Antigravity adapter. Measured against agy 1.2.8 on Windows.

This runtime is why several proposed abstractions had to change:

* Model and effort are FUSED. `gemini-3.8-flash-low` already carries the effort,
  and passing `--effort high` alongside it is a hard error:
  "invalid model selection ... conflicts with --effort=high". So a Foundation
  that assumed model and effort are independent request fields is simply wrong
  for a third of the measured runtimes.
* It does NOT honour process cwd. Asked to write a file "in the current working
  directory", it reported SUCCESS, exited 0, and wrote the file into its own
  scratch directory. `--add-dir` is required to make the workspace real.
* Its capacity is NOT in the run's stream: turn events carry token counts
  only. It is answered by the CLI itself, without a turn, as
  `agy --print /usage --output-format json` (measured against 1.2.14: zero
  turns, zero tokens, an empty conversation id). Quota belongs to GROUPS of
  models, not to a model -- see `observe_capacity`. An earlier reading of
  "no capacity anywhere" was a test artifact: Git Bash rewrote the bare
  `/usage` argument into a Windows path, so agy received a path and sent it
  to the model as a prompt. Arguments go here as a list, never through a shell.
* Its on-disk `presence/<uuid>.lock` files look like liveness markers and are
  not: 308 of them were present, going back weeks. They are not used here.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from mentis.worker import boot_command as _boot_command
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

from .base import Invocation, RunResult, RuntimeAdapter

# Effort suffixes observed in the catalogue. Used ONLY to tell whether a slug
# already carries an effort, never to invent one.
_FUSED_EFFORTS = ("low", "medium", "high")

# HOW LONG A /usage READING IS REUSED. Each reading makes agy fetch the quota
# over the network, and the picker asks every time it opens the runtime
# level. Two minutes is short against a five-hour window and long against a
# person opening and closing a menu. The reading keeps its own `observed_at`,
# so whoever shows it can say how old it is.
USAGE_FRESH_SECONDS = 120

#: THIS RUNTIME'S OWN WEB TOOLS, WITHHELD FROM EVERY RUN GIVEN A HOME: its
#: hosted `search_web`, `read_url_content` and every browser tool. The web is
#: a Mentis capability -- `web_search` and `web_fetch`, offered through the
#: grant and recorded by the server -- so a run keeps no private, unrecorded
#: path beside them. Matched against the tool name, which agy derives from
#: the step type (`CORTEX_STEP_TYPE_SEARCH_WEB` -> `search_web`).
#:
#: A HOOK, BECAUSE NOTHING ELSE HOLDS. MEASURED 2026-10-22 on agy 1.4.4,
#: Windows, a fresh home and `gemini-3.8-flash-low`: there is no flag for
#: it, and `permissions.deny` -- `search_web(*)`, `search_web`,
#: `read_url(*)`, `execute_url(*)` -- left `search_web` answering under
#: both `--dangerously-skip-permissions` and `--sandbox --mode
#: accept-edits`. A `PreToolUse` hook in the home's `.gemini/config/
#: hooks.json` answering `"decision": "deny"` refused it under both ("tool
#: call denied by pre-tool hook: ..."), and refused it to a sub-agent the
#: run invoked as well. The tools stay LISTED in the run's `init`; it is the
#: call that is refused, with the reason below.
#:
#: The command is named through `~`, which agy expands to the home, because
#: its `cmd /c` mangles a quoted path and does not find a bare name beside
#: `hooks.json` (both measured). A home whose path has a space would break
#: the command -- and a hook that fails also refuses the call (measured: a
#: command `cmd` could not find failed the step), so it fails closed.
WEB_WITHHELD_MATCHER = "search_web|read_url_content|.*browser.*"
WEB_WITHHELD_REASON = (
    "This runtime's own web tools are withheld in a Mentis-dispatched run. "
    "Web access is through the Mentis tools web_search and web_fetch, which "
    "are recorded. If they are not among your tools, this run has no web "
    "access.")


def _web_withheld_hook(cfg: str) -> None:
    """Write the hook that refuses `WEB_WITHHELD_MATCHER` into `cfg`."""
    answer = json.dumps({"decision": "deny", "reason": WEB_WITHHELD_REASON})
    if os.name == "nt":
        # `echo` prints the rest of its line as it is, so the reason holds
        # none of cmd's special characters (tested).
        script, body = "deny_web.cmd", f"@echo {answer}\r\n"
    else:
        script = "deny_web.sh"
        body = "#!/bin/sh\ncat >/dev/null\nprintf '%s\\n' " + \
            "'" + answer.replace("'", "'\\''") + "'\n"
    path = os.path.join(cfg, script)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(body)
    if os.name != "nt":
        os.chmod(path, 0o755)
    with open(os.path.join(cfg, "hooks.json"), "w", encoding="utf-8") as fh:
        json.dump({"mentis-web-withheld": {"PreToolUse": [{
            "matcher": WEB_WITHHELD_MATCHER,
            "hooks": [{"type": "command",
                       "command": f"~/.gemini/config/{script}"}]}]}}, fh)

# How agy introduces a group's members. The ONLY source for which model draws
# on which group: a model is never placed by its slug.
_MEMBERS_PREFIX = "Models within this group:"


def _words(s: str) -> list[str]:
    return [w for w in re.split(r"[\s()]+", s.lower()) if w]


def group_members(group: dict) -> tuple[str, ...]:
    """The families agy says draw on this group, e.g. `Gemini Flash`."""
    desc = str(group.get("description") or "")
    if not desc.startswith(_MEMBERS_PREFIX):
        return ()
    return tuple(m.strip() for m in desc[len(_MEMBERS_PREFIX):].split(",") if m.strip())


def group_for(display_name: str | None, groups: list[dict]) -> tuple[str | None, str]:
    """Which of agy's groups a model draws on, judged from its DISPLAY name.

    A member such as `Gemini Flash` names a model when each of its words is a
    word of the display name (`Gemini 3.8 Flash (High)`). Exactly one group
    must claim the model. None, or more than one, places it nowhere, and the
    reason says which -- a model with no group gets no meter, never a
    neighbour's. Where no member list names it, a group that lists no members
    claims it by the group's own name (`Gemini 4 Argon`), the same way.
    """
    if not display_name:
        return None, "agy gave this model no display name to match"
    have = set(_words(display_name))
    # An empty word set is a subset of everything, so a member that reduces to
    # no words (agy emitting `()` as a member) would claim EVERY model. A
    # member that names nothing names nothing.
    claimed = [g["name"] for g in groups
               if any(mw and mw <= have
                      for mw in (set(_words(m)) for m in group_members(g)))]
    if len(claimed) == 1:
        return claimed[0], f"named in agy's description of {claimed[0]!r}"
    if claimed:
        return None, f"named by more than one group agy reported: {', '.join(claimed)}"
    # A GROUP THAT LISTS NO MEMBERS IS NAMED FOR WHAT IT METERS. agy 1.2.x
    # reports `Gemini 4 Argon` with a plan note for its description instead
    # of a member list, so the Argon models matched nothing, had no meter,
    # and kept being picked while that group stood at 100% (measured
    # 2026-10-20). Asked only when no member list names the model, and only
    # of groups with no member list: agy's own name for the group, every word
    # of it in the display name, exactly one group -- still never the slug.
    by_name = [g["name"] for g in groups if not group_members(g)
               and (nw := set(_words(str(g["name"])))) and nw <= have]
    if len(by_name) == 1:
        return by_name[0], (f"named by agy's group {by_name[0]!r}, which lists "
                            f"no members")
    if by_name:
        return None, (f"named by more than one group agy reported: "
                      f"{', '.join(by_name)}")
    return None, "not named in any group agy reported"


#: The window lengths agy's own words state, and no others.
_WINDOW_SECONDS = {"weekly": 7 * 86400, "5h": 5 * 3600}


def _instant(s) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def capacity_from_usage(payload, *, machine_id: str, observed_at: float,
                        models: list[ModelInfo] | None = None) -> CapacityReading:
    """A reading from agy's own `/usage` answer, or why there is none.

    `remaining_fraction` is agy's figure and is kept verbatim in `raw`;
    `used_fraction` is its complement, the same conversion the other runtimes
    get. A bucket that states no fraction stays a window with no figure --
    never zero. A payload with no groups establishes nothing.
    """
    def nothing(why: str) -> CapacityReading:
        return CapacityReading(runtime="antigravity", machine_id=machine_id,
                               observed_at=observed_at, notes=(why,))

    if not isinstance(payload, dict):
        return nothing("agy's /usage answer was not a JSON object")
    if payload.get("status") != "SUCCESS":
        return nothing(f"agy's /usage answer had status {payload.get('status')!r}: "
                       f"{payload.get('error') or 'no error given'}")
    command = payload.get("command") or {}
    if command.get("name") != "usage":
        # The bare-word failure: agy took `/usage` as a prompt and ran a turn.
        return nothing("agy did not answer /usage itself (no `command` payload); "
                       "it may have been sent to the model as a prompt")
    groups = [g for g in ((command.get("data") or {}).get("groups") or [])
              if isinstance(g, dict) and g.get("name")]
    if not groups:
        return nothing("agy's /usage answer carried no quota groups")

    windows = []
    for g in groups:
        for b in g.get("buckets") or []:
            rem = b.get("remaining_fraction")
            used = (1.0 - float(rem)
                    if isinstance(rem, (int, float)) and not isinstance(rem, bool)
                    and math.isfinite(rem) and 0 <= rem <= 1 else None)
            windows.append(UsageWindow(
                label=str(b.get("window") or b.get("name") or b.get("id") or "window"),
                used_fraction=used,
                # agy names its two windows `weekly` and `5h`, and its own
                # description says so ("models share a weekly limit and a
                # 5-hour limit"). Those two words are given their lengths so
                # selection can tell the budget window from the pacing one;
                # any other word stays unstated rather than guessed.
                window_seconds=_WINDOW_SECONDS.get(str(b.get("window") or "")),
                resets_at=_instant(b.get("reset_time")),
                provenance=Provenance.PROVIDER_REPORTED,
                raw=dict(b),
                group=str(g["name"]),
            ))
    if not windows:
        return nothing("agy's /usage answer named quota groups but no windows")

    notes = ["read from `agy --print /usage`, which the CLI answers itself: "
             "no agent turn ran and no quota was spent"]
    placed: tuple[tuple[str, str | None], ...] = ()
    if models is None:
        notes.append("models were not listed, so no model is tied to a group")
    else:
        pairs = []
        for m in models:
            grp, why = group_for(m.display_name, groups)
            pairs.append((m.slug, grp))
            if grp is None:
                notes.append(f"{m.slug}: {why}")
        placed = tuple(pairs)
    return CapacityReading(
        runtime="antigravity", machine_id=machine_id, observed_at=observed_at,
        windows=tuple(windows), notes=tuple(notes), model_groups=placed,
    )


#: How many lines of the runtime's own log an empty run keeps, and how many
#: characters of its stderr. Bounded so the record stays readable.
_LOG_TAIL_LINES = 40
_STDERR_TAIL_CHARS = 800


def _log_tail(path: str | None) -> list[str]:
    """The last lines of agy's own log, or nothing. Never raises: the log is
    evidence for a run that said nothing, and failing to read it must not
    fail the run."""
    if not path:
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    return [ln.rstrip() for ln in lines[-_LOG_TAIL_LINES:] if ln.strip()]


def parse_events(events: list[dict]) -> dict:
    """What agy's stream-json events say, read once: the conversation, the
    model the init event named, the final `result` (response, usage, error)
    and every `agent_response` step's text, in order.

    MEASURED on agy 1.4.7 (2026-10-26), `--output-format stream-json`: the
    text the model writes arrives as `step_update` events of
    `step_type: "agent_response"` carrying `text_delta`, and the `result`
    event repeats it whole as `response`. A step may also carry only usage
    (`thinking_tokens` and no `text_delta`: the model reasoned and wrote
    nothing), and a `step_type: "error_message"` step is emitted with no
    text at all. `reported` is `result.response`; where that is blank and
    the steps carried text, the steps' text stands in for it (`assembled`),
    since it is the same words by the same runtime -- never anything else, and only from a stream whose `result` said
    SUCCESS: a cut-off stream's partial words are not an answer.
    """
    conv = None
    actual_model = Observed.unknown("no init event observed")
    reported = None
    usage: dict = {}
    error = None
    status = None
    result_seen = False
    spoken: list[str] = []
    steps: dict[str, int] = {}
    kinds: dict[str, int] = {}
    for ev in events:
        kind = str(ev.get("event"))
        kinds[kind] = kinds.get(kind, 0) + 1
        if kind == "init":
            init = ev.get("init") or {}
            conv = ev.get("conversation_id") or conv
            if init.get("model"):
                actual_model = Observed(init["model"], Provenance.PROVIDER_REPORTED)
        elif kind == "step_update":
            su = ev.get("step_update") or {}
            st = str(su.get("step_type") or "unknown")
            # one step is many events while ACTIVE; count it once, at DONE
            if su.get("state") == "DONE":
                steps[st] = steps.get(st, 0) + 1
            if st == "agent_response" and su.get("text_delta"):
                spoken.append(str(su["text_delta"]))
        elif kind == "result":
            result_seen = True
            r = ev.get("result") or {}
            conv = r.get("conversation_id") or conv
            reported = r.get("response")
            usage = r.get("usage") or {}
            status = r.get("status")
            if status != "SUCCESS":
                error = r.get("error") or status
    assembled = False
    # ONLY WHEN THE RUN FINISHED: a stream cut off before its `result` has
    # partial words, and partial words are not an answer (found by review).
    if not (reported or "").strip() and spoken and status == "SUCCESS":
        reported = "".join(spoken)
        assembled = True
    return {"conversation": conv, "actual_model": actual_model,
            "reported": reported, "usage": usage, "error": error,
            "status": status, "result_seen": result_seen,
            "spoken_chars": sum(len(s) for s in spoken),
            "assembled": assembled, "steps": steps, "events": kinds}


def empty_run_evidence(events: list[dict], parsed: dict, *, stderr=None,
                       log_tail=()) -> dict:
    """What the runtime emitted for a run that reported nothing, bounded and
    verbatim where it is the runtime's own words: event and step counts,
    whether a `result` arrived and with what status, the usage it stated,
    the last few events, agy's log tail and its stderr tail. Nothing here is
    an interpretation; `error` stays what Mentis says went wrong."""
    def trim(ev):
        s = json.dumps(ev, ensure_ascii=False)
        return s if len(s) <= 600 else s[:600] + "…"
    out = {"events": parsed["events"], "steps": parsed["steps"],
           "result_seen": parsed["result_seen"],
           "result_status": parsed["status"],
           "response_chars": len(parsed["reported"] or ""),
           "spoken_chars": parsed["spoken_chars"],
           "usage": parsed["usage"],
           "last_events": [trim(e) for e in events[-4:]]}
    tail = (stderr or "")[-_STDERR_TAIL_CHARS:].strip()
    if tail:
        out["stderr_tail"] = tail
    if log_tail:
        out["log_tail"] = list(log_tail)
    return out


def _linked_worktree(folder: str) -> bool:
    """Whether `folder` is a linked git worktree: its `.git` is a file naming
    the admin directory elsewhere, not the repository itself."""
    return os.path.isfile(os.path.join(folder, ".git"))


class AntigravityAdapter(RuntimeAdapter):
    kind = "antigravity"
    names = RUNTIMES["antigravity"]
    #: THE QUOTA GROUPS MENTIS MAY DRAW ON HERE, IN ORDER OF PREFERENCE, by
    #: the names agy reports them under. OWNER RULING (2026-10-26, from the
    #: CLI): only Antigravity's Gemini quota -- Argon while its group has
    #: headroom, Flash otherwise -- and never its Claude or GPT capacity.
    #: Read by `Foundation._models_in_owners_groups`; a model is placed in a
    #: group by agy's own `/usage` report, never by its slug.
    groups_in_order = ("Gemini 4 Argon", "Gemini Models")
    #: THE SAME RULE BY SLUG FAMILY, in the same order, used ONLY when agy's
    #: report places no model in any group (no `/usage` read yet): a model
    #: whose slug starts with none of these is not picked. Said in the
    #: selection account whenever it decides, so the slug-based placement is
    #: never mistaken for the report's.
    families_in_order = ("gemini-4-argon", "gemini-3.8-flash")
    # Reports its own total_tokens, and it was measured to equal input+output,
    # with thinking_tokens counted inside output_tokens.
    accounting = "antigravity.usage.v1"
    # Conversations are stored as protobuf BLOBs in per-conversation SQLite; no
    # usage was read back from them, so re-observation is not claimed.
    reobservable = False
    # NOT FOLDER-BOUNDED, and not offered it: every run is launched with
    # `--dangerously-skip-permissions`, which nothing narrows to a folder.
    # By owner decision (2026-10-10) Scratch file work is refused here.
    folder_bounds_why = (
        "Antigravity runs with --dangerously-skip-permissions and cannot "
        "confine file access to the selected folders, so it is not given "
        "Scratch file work")

    def capabilities(self) -> frozenset[Capability]:
        return frozenset(
            {
                Capability.DISCOVER,
                Capability.INVOKE_HEADLESS,
                Capability.LIST_MODELS,
                Capability.REQUEST_MODEL,
                Capability.OBSERVE_ACTUAL_MODEL,
                Capability.REQUEST_EFFORT,
                Capability.SESSION_IDENTITY,
                Capability.DELIVER_AT_START,
                # The four reads reach a worker here through a PROVISIONED
                # HOME carrying Mark IV's own server. Measured on a real
                # dispatch: it reported exactly `orient, resolve, history,
                # find` -- see the note at `_provision`.
                Capability.CALL_MENTIS_TOOLS,
                # `--dangerously-skip-permissions`, which is what a dispatch
                # runs with. The flag's name is the runtime's, not a
                # description of what Mentis asked for.
                Capability.WRITE_UNATTENDED,
                # `agy --print /usage`, answered by the CLI without a turn.
                # Per model GROUP, not per model -- see `observe_capacity`.
                Capability.OBSERVE_CAPACITY,
                # It runs with permissions skipped and ran the browser tests
                # of earlier UI reviews itself.
                Capability.BUILD_UI,
                Capability.DRIVE_BROWSER,
                # NOT declared:
                #   RESUME                - WITHDRAWN ON MEASUREMENT. It has
                #     `--conversation <id>`, and it was claimed on the
                #     strength of the flag existing. Measured on the path
                #     this adapter actually uses -- a record is set, so the
                #     home is redirected -- two performs on one instance
                #     came back with DIFFERENT conversation ids and the
                #     second did not know a word given only to the first.
                #     It did not refuse; it silently began a new
                #     conversation, which is worse than refusing. Without
                #     the redirection it does continue, so the capability is
                #     real in the runtime and unreachable from here.
                #   OBSERVE_ACTUAL_EFFORT - only readable by parsing the slug,
                #                           which is inference, not observation
                #   DELIVER_TO_LIVE       - an agentapi exists but needs an
                #                           in-session LS address; not exercised
            }
        )

    def discover(self, machine_id: str) -> RuntimeInfo:
        exe = self._which("agy")
        if not exe:
            return RuntimeInfo(
                kind=self.kind, present=False,
                version=Observed.unknown("agy not on PATH"),
                executable=Observed.unknown("agy not on PATH"),
                capabilities=frozenset(), machine_id=machine_id,
                notes=("the Antigravity IDE launcher is NOT this runtime; its "
                       "`chat` subcommand opens a GUI window",),
            )
        version = Observed.unknown("could not read version")
        try:
            out = self._run([exe, "--version"], timeout=60)
            if out.returncode == 0 and out.stdout.strip():
                version = Observed(out.stdout.strip(), Provenance.LOCALLY_OBSERVED)
        except Exception as exc:  # noqa: BLE001
            version = Observed.unknown(f"version probe failed: {exc}")
        return RuntimeInfo(
            kind=self.kind, present=True, version=version,
            executable=Observed(exe, Provenance.LOCALLY_OBSERVED),
            capabilities=self.capabilities(), machine_id=machine_id,
            notes=(
                "model slug and effort are fused; passing both is an error",
                "does not honour process cwd -- workspace requires --add-dir",
                "capacity is per model group, read from `agy --print /usage`",
            ),
        )

    def list_models(self) -> list[ModelInfo]:
        exe = self._which("agy")
        if not exe:
            return []
        try:
            out = self._run([exe, "models"], timeout=120)
        except Exception:  # noqa: BLE001
            return []
        models = []
        for line in (out.stdout or "").splitlines():
            if "\t" not in line:
                continue
            slug, _, display = line.partition("\t")
            slug = slug.strip()
            if not slug:
                continue
            fused = next((e for e in _FUSED_EFFORTS if slug.endswith(f"-{e}")), None)
            models.append(
                ModelInfo(
                    slug=slug, runtime=self.kind,
                    # The effort this slug already carries. Not a menu of choices
                    # -- choosing a different effort means choosing another slug.
                    efforts=(fused,) if fused else (),
                    default_effort=fused,
                    display_name=display.strip() or None,
                    # Everything this runtime lists is served remotely. No local
                    # provider surface was found for it, so none is claimed.
                    locality="hosted",
                    provider="antigravity",
                )
            )
        return models

    def delivery_opportunities(self) -> list[DeliveryOpportunity]:
        return [
            DeliveryOpportunity(
                runtime=self.kind, moment="invocation",
                mechanism="prepended to the prompt",
                verified=True,
                note="the only delivery path exercised here",
            ),
            DeliveryOpportunity(
                runtime=self.kind, moment="session_start",
                mechanism="hooks block with a SessionStart matcher in "
                          "~/.gemini/antigravity-cli/settings.json",
                verified=False,
                note="the settings file carries a hooks block of the same shape as "
                     "Claude's; Mark IV has not exercised it, and it is machine-wide "
                     "rather than per-invocation, which is the wrong scope for us",
            ),
            DeliveryOpportunity(
                runtime=self.kind, moment="live_session",
                mechanism="`agy agentapi send-message <recipient_id> <content>`",
                verified=False,
                note="hidden subcommand; requires ANTIGRAVITY_LS_ADDRESS, i.e. it is "
                     "reachable from inside a session, not from a cold shell",
            ),
        ]

    def _provision_home(self, record: str | None, *, via: str | None = None,
                        capability: str | None = None, permits=None,
                        scratch: str | None = None,
                        project: str | None = None,
                        confined: bool = False) -> str:
        """A home holding exactly the MCP registry this invocation should see.

        WHY A HOME AND NOT A FLAG. This runtime has no per-invocation MCP
        option at all -- no `--mcp-config`, no strict variant, no settings
        override. Its registry is `~/.gemini/config/mcp_config.json` and
        `agy mcp add` writes there machine-wide, which is the wrong scope for
        us in both directions.

        MEASURED, AND IT MATTERS MORE HERE THAN ANYWHERE. Before this, a
        worker dispatched to Antigravity inherited that machine-wide registry
        -- which on this machine holds a DIFFERENT system's brain under the
        same name `mentis`, with write tools in it. Asked to list what it
        could see, a real worker came back with `start_here`, `recall`,
        `propose_operational` and the rest. That is not a configuration
        worry; it was measured from inside the worker.

        Redirecting the home moves the registry, so exclusion and injection
        are again the same act: a fresh home containing our four reads and
        nothing else. Verified from inside a fresh worker, which then
        reported exactly `orient, resolve, history, find`.
        """
        home = tempfile.mkdtemp(prefix="mk4-agy-home-")
        cfg = os.path.join(home, ".gemini", "config")
        os.makedirs(cfg, exist_ok=True)
        servers = {}
        if record:
            boot = _boot_command(record, via=via, capability=capability,
                                 permits=permits, scratch=scratch,
                                 project=project)
            servers["mentis"] = {"type": "stdio", "command": sys.executable,
                                 "args": ["-I", "-c", boot]}
        with open(os.path.join(cfg, "mcp_config.json"), "w", encoding="utf-8") as fh:
            json.dump({"mcpServers": servers}, fh)
        # NO WEB BUT MENTIS'S, confined or not: `WEB_WITHHELD_MATCHER`.
        _web_withheld_hook(cfg)
        if confined:
            # WHAT A SANDBOXED RUN MAY DO WITHOUT ASKING, since headless mode
            # cannot ask and refuses instead: its shell (which the sandbox
            # confines) and its Mentis tools. File writes are not listed --
            # `--mode accept-edits` allows them in the added directories only.
            own = os.path.join(home, ".gemini", "antigravity-cli")
            os.makedirs(own, exist_ok=True)
            with open(os.path.join(own, "settings.json"), "w",
                      encoding="utf-8") as fh:
                json.dump({"permissions": {"allow": [
                    "command(*)", "mcp(mentis/*)"]}}, fh)
        return home

    def run(self, inv: Invocation) -> RunResult:
        exe = self._which("agy")
        if not exe:
            return RunResult(None, 127, None, Observed.unknown("runtime absent"),
                             Observed.unknown("runtime absent"), error="agy not found")

        prompt = f"{inv.deliver}\n\n---\n\n{inv.prompt}" if inv.deliver else inv.prompt

        # WRITABLE ROOTS PUT THIS RUNTIME IN ITS OWN SANDBOX instead of
        # skipping every permission. Measured on agy 1.3.4: `--sandbox --mode
        # accept-edits` with the roots added wrote inside them and refused
        # outside -- the file tool ("write_file ... auto-denied") and the
        # shell alike ("Access to the path ... is denied"). Shell commands
        # and Mentis tools are allowed in this run's own settings
        # (`_provision_home`), since headless mode cannot ask.
        #
        # EXCEPT WHERE THE WORK IS A LINKED GIT WORKTREE, which this sandbox
        # cannot enter. Measured on agy 1.3.4 (2026-10-14), with the worktree
        # added by `--add-dir` beside the scratch the run starts in -- the
        # shape of every request that declares a repository: its shell runs,
        # but `git -C <worktree> status` fails "cannot change to ...:
        # Permission denied" (and .NET `SetCurrentDirectory` likewise), with
        # or without its parent, its common git dir or the roots added and in
        # either order; a plain repository and plain folders added the same
        # way are entered normally. The same run under
        # `--dangerously-skip-permissions` works. So such a run launches as
        # it did before writable roots existed: a dispatched agent that cannot
        # run `git status` in the worktree it was given cannot do the work.
        confined = bool(inv.writable) and not any(
            _linked_worktree(d) for d in (inv.cwd, inv.project) if d)
        # THE PROMPT GOES ON STDIN, NEVER IN ARGV, at every length. It used
        # to follow `--print` as an argument, and once governance and
        # orientation were delivered ahead of the work the command line went
        # past what Windows CreateProcess allows (~32K chars): every such
        # launch died "[WinError 206] The filename or extension is too long"
        # before agy started, while Claude and Codex, which read stdin, ran
        # the same work. MEASURED on agy 1.4.7 (2026-10-24): bare `--print`
        # reads nothing from stdin ("empty prompt"); `--input-format
        # stream-json` without `--print` reads one NDJSON message per line and
        # runs a turn for each, and the message it accepts is exactly
        # `{"event": "user", "message": {"content": <text>}}` (a string
        # `message`, or one without `event`, is refused by name). One message
        # is one line because `json.dumps` escapes every newline, so the
        # prompt is one turn, unchanged. `--print-timeout` and the permission
        # flags still apply in this mode. No threshold: a single route means
        # short prompts cannot behave differently from long ones.
        stdin = json.dumps({"event": "user", "message": {"content": prompt}}) + "\n"
        cmd = [exe, "--input-format", "stream-json",
               "--output-format", "stream-json",
               *(["--sandbox", "--mode", "accept-edits"] if confined
                 else ["--dangerously-skip-permissions"]),
               # Measured necessity: without this the runtime ignores the
               # workspace entirely and writes into its own scratch directory.
               # So the private scratch is ADDED like the project is -- this
               # runtime does not honour process cwd, so naming it is the
               # only way it becomes where the work is.
               "--add-dir", inv.cwd]
        if inv.project:
            cmd += ["--add-dir", inv.project]
        for w in inv.writable:
            if w not in (inv.project, inv.cwd):
                cmd += ["--add-dir", w]
        if inv.model:
            cmd += ["--model", inv.model]
        # Effort is only passed when the chosen slug does NOT already carry one.
        # Passing both is a hard error in this runtime.
        if inv.effort and not self._slug_carries_effort(inv.model):
            cmd += ["--effort", inv.effort]
        if inv.resume_ref:
            cmd += ["--conversation", inv.resume_ref]

        # THIS RUNTIME STOPS ITSELF, so the deadline has to be told to it and
        # not only to the wait below. Passed ONLY when somebody set one:
        # interpolating `None` here produced the literal `--print-timeout
        # Nones`, and the `+ 60` below raised TypeError before the process
        # started -- caught by the generic handler and reported as an
        # ordinary runtime failure, so EVERY antigravity dispatch failed with
        # an opaque error the moment the default deadline became None.
        # Found by review, reproduced, and it is why the wait is separate.
        if inv.timeout_s is not None:
            cmd += ["--print-timeout", f"{inv.timeout_s}s"]

        # The registry this worker may see, and nothing else. Without a
        # record there is nothing to offer, and the machine's own
        # configuration applies -- which is the old behaviour, and is why a
        # record is what makes the difference.
        env = None
        log_path = None
        if inv.record or confined:
            home = self._provision_home(inv.record, via=inv.answers_at,
                                        capability=inv.capability,
                                        permits=inv.permits,
                                        scratch=inv.scratch,
                                        project=inv.project,
                                        confined=confined)
            env = {"USERPROFILE": home, "HOME": home}
            # THE RUNTIME'S OWN LOG, IN THE HOME THAT GOES WITH THE RUN. Its
            # default log lands in the real profile's `antigravity-cli/log`
            # and says nothing about which run wrote it; this one is read
            # back (`_log_tail`) before the home is discarded, and only kept
            # when the run came back with nothing to say (`evidence`).
            # MEASURED 2026-10-26: seven Gemini Flash runs ended `exit 0,
            # nothing reported` and nothing of what the runtime saw survived.
            log_path = os.path.join(home, "agy.log")
            cmd += ["--log-file", log_path]

        log_tail: list[str] = []
        try:
            # Grace over the runtime's own stop, so its self-termination is
            # what we see rather than our wait racing it. No deadline means
            # no wait: a long run is long, not broken.
            wait = None if inv.timeout_s is None else inv.timeout_s + 60
            out = self._run(cmd, cwd=inv.cwd, timeout=wait, env=env,
                            stdin=stdin, observer=inv.observer,
                            parse=self.observe_event)
        except subprocess.TimeoutExpired as exc:
            # A DEADLINE THE CALLER ASKED FOR, NOT A RUNTIME FAILURE. Said
            # as itself so nothing downstream has to read it out of an
            # error string, and so what had already been delivered to a
            # running process is not mistaken for never having crossed.
            return RunResult(None, -1, None,
                             Observed.unknown("deadline reached"),
                             Observed.unknown("deadline reached"),
                             error=str(exc), timed_out=True)
        except Exception as exc:  # noqa: BLE001
            # THE TYPE IS HALF THE REASON. `str(exc)` alone on an OSError can
            # be a bare Windows message with nothing saying what raised it,
            # and this branch is the one that fires when a launch dies before
            # the runtime ever speaks. Traced from a real failure whose whole
            # recorded explanation was `exit -1, nothing reported`.
            return RunResult(None, -1, None, Observed.unknown("run failed"),
                             Observed.unknown("run failed"),
                             error=f"{type(exc).__name__}: {exc}")
        finally:
            # ONE INVOCATION, ONE HOME, AND IT GOES WITH THE RUN.
            #
            # MEASURED, AND IT IS THE INTERESTING CASE. Held STABLE across
            # two performs, this runtime DID carry context: a word given
            # only to the first run came back from the second. But the
            # conversation id differed, so it had not continued the session
            # it was asked to continue -- it began a new one that happened to
            # remember, out of its own memory store inside the home.
            #
            # That is continuity nobody can address, verify or scope, which
            # is the kind this system must not have: two unrelated
            # Conversations sharing a home would quietly inherit each
            # other's context while the record said they were separate. So
            # the home is per invocation and removed with it, and RESUME
            # stays undeclared. The cost is paid honestly: whatever this
            # runtime sets up inside a home it sets up again each time.
            #
            # Also why removing it is safe: 201MB across 7 abandoned homes
            # had built up in %TEMP%, holding conversation databases, logs
            # and caches that nothing could ever continue from.
            if env:
                log_tail = _log_tail(log_path)
                self._discard_scratch(env.get("HOME"))

        events = []
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        parsed = parse_events(events)
        reported = parsed["reported"]
        return RunResult(
            session_ref=parsed["conversation"],
            exit_code=out.returncode,
            reported=reported,
            actual_model=parsed["actual_model"],
            actual_effort=self._effort_from_model(parsed["actual_model"]),
            usage=parsed["usage"],
            capacity=None,
            error=parsed["error"],
            raw_events=events,
            transport_ok=getattr(out, "transport_ok", True),
            transport_note=getattr(out, "transport_note", None),
            # WHAT THE RUNTIME SAID WHEN IT SAID NOTHING. Only for a run that
            # came back with no words: what the stream carried, step by step,
            # and the tail of the runtime's own log. Empty otherwise.
            evidence=(empty_run_evidence(events, parsed,
                                         stderr=getattr(out, "stderr", None),
                                         log_tail=log_tail)
                      if not (reported or "").strip() else {}),
        )

    # -- while it runs ---------------------------------------------------------
    #
    # MEASURED on agy 1.2.8, `--print ... --output-format stream-json` (the
    # launch before the prompt moved to stdin under `--input-format
    # stream-json`, which emits the same output stream), with the
    # arrival time of every line (tests/fixtures/runtime_streams/
    # antigravity_two_commands.jsonl): `init{conversation_id, init{model}}`,
    # then `step_update{step_index, step_type, state}` per step, then
    # `result{status, response}`. A TOOL step arrives as ACTIVE when it starts
    # (with `tool_name` and its parameters) and again as DONE when it finishes,
    # under the same `step_index` -- so a tool is open from one to the other.
    #
    # NARROWER THAN CLAUDE, AND SAID SO. An `agent_response` step was observed
    # only as it produced text or finished; nothing on this stream reports
    # thinking while it happens (its thinking tokens arrive in the usage of a
    # finished step), and nothing reports a helper. Neither is claimed.
    observes = ("session", "tools", "model-turns")

    def observe_event(self, ev: dict, obs) -> None:
        kind = ev.get("event")
        if kind == "init":
            obs.saw("session started")
            obs.session(ev.get("conversation_id"))
            obs.model_reported((ev.get("init") or {}).get("model"))
            obs.awaiting_model()
            return
        if kind == "step_update":
            su = ev.get("step_update") or {}
            stype, state = su.get("step_type"), su.get("state")
            obs.saw(f"step {stype or '?'} {str(state or '?').lower()}")
            # A step after a result is a new turn (`settle_due`).
            obs.turn_resumed()
            key = f"step:{su.get('step_index')}"
            if stype == "tool":
                if state == "ACTIVE":
                    info = su.get("tool_info") or {}
                    params = info.get("parameters") or {}
                    what = next((v for v in params.values()
                                 if isinstance(v, str) and v.strip()), None)
                    obs.tool_started(key, su.get("tool_name") or info.get("name"),
                                     what)
                else:
                    # Anything but ACTIVE ends that step: DONE was measured;
                    # a step that errored is not left open forever.
                    obs.tool_ended(key)
                    if not obs.snapshot()["tools"]:
                        obs.awaiting_model()
            elif stype == "user_input" and state == "DONE":
                obs.awaiting_model()
            elif stype == "agent_response" and state == "DONE":
                obs.model_answered()
            return
        if kind == "result":
            r = ev.get("result") or {}
            obs.saw("result")
            obs.runtime_terminal(r.get("status") == "SUCCESS",
                                 r.get("error") or r.get("status"))
            return
        obs.saw(str(kind or "event"))

    @staticmethod
    def _slug_carries_effort(slug: str | None) -> bool:
        return bool(slug) and any(slug.endswith(f"-{e}") for e in _FUSED_EFFORTS)

    @staticmethod
    def _effort_from_model(actual_model: Observed) -> Observed:
        """Effort is inside the model name. Reading it out is INFERENCE.

        The runtime never reports effort as its own field. Parsing a naming
        convention is a guess about a convention, so it is labelled
        LOCALLY_INFERRED and never promoted to observed.
        """
        if not actual_model.is_established:
            return Observed.unknown("actual model unknown, so effort is too")
        slug = str(actual_model.value)
        for e in _FUSED_EFFORTS:
            if slug.endswith(f"-{e}"):
                return Observed(
                    e, Provenance.LOCALLY_INFERRED,
                    note="parsed from the model slug; this runtime reports no "
                         "effort field of its own",
                )
        return Observed.unknown("model slug carries no effort suffix")

    def resume_eligibility(self, *, session_ref, workspace=None,
                           runtime_home=None):
        """Nothing here can be checked, so nothing is claimed.

        MEASURED RATHER THAN ASSUMED FROM PARITY. Claude and Codex both
        keep a session artifact on disk that can be looked for. This
        runtime exposes none, and `--conversation <id>` against a
        redirected home does not continue the conversation -- it quietly
        starts another one with a new id. So there is nothing to verify
        and no observation that would justify saying `eligible`.

        UNKNOWN is the answer, and because nothing is adopted on an
        UNKNOWN this runtime reconstructs from the durable record instead.
        That costs continuity and keeps the record honest.
        """
        from mentis.api.types import ResumeEligibility
        return ResumeEligibility.unknown(
            "antigravity exposes no session artifact to check, and its "
            "--conversation flag was measured starting a NEW conversation "
            "rather than continuing the named one")

    _usage_cache: tuple[float, CapacityReading] | None = None

    def passive_capacity(self, machine_id: str) -> CapacityReading:
        """Free of quota: agy answers `/usage` itself, no turn runs (measured,
        see `observe_capacity`), and an established answer is reused."""
        return self.observe_capacity(machine_id)

    def observe_capacity(self, machine_id: str) -> CapacityReading:
        """What agy says is left, per model GROUP, from its own `/usage`.

        MEASURED AGAINST 1.2.14. `agy --print /usage --output-format json` is
        answered by the CLI itself -- `num_turns: 0`, zero tokens, an empty
        conversation id -- with a `command.data.groups` payload: each group
        (today "Gemini Models" and "Claude and GPT models") has a weekly and a
        5h bucket with `remaining_fraction` and `reset_time`. The command must
        sit directly after `--print`, which takes the next argument as its
        prompt, and goes as a list element so no shell can rewrite it.

        GROUPS, NOT MODELS. Every model in a group shares its windows, so the
        reading carries which model is in which group, decided only by agy's
        own "Models within this group: ..." -- see `group_for`.

        REUSED FOR `USAGE_FRESH_SECONDS`. Only an established reading is kept:
        a failure is asked again next time rather than repeated from memory.
        The reused reading keeps its original `observed_at`.
        """
        cached = self._usage_cache
        if cached and cached[1].machine_id == machine_id \
                and time.monotonic() - cached[0] < USAGE_FRESH_SECONDS:
            return cached[1]

        observed_at = time.time()

        def nothing(why: str) -> CapacityReading:
            return CapacityReading(runtime=self.kind, machine_id=machine_id,
                                   observed_at=observed_at, notes=(why,))

        exe = self._which("agy")
        if not exe:
            return nothing("agy not on PATH, so its quota could not be asked for")
        try:
            out = self._run([exe, "--print", "/usage", "--output-format", "json"],
                            timeout=60)
        except subprocess.TimeoutExpired:
            return nothing("agy did not answer /usage within 60s")
        except Exception as exc:  # noqa: BLE001
            return nothing(f"asking agy for /usage failed: {type(exc).__name__}: {exc}")
        if out.returncode != 0:
            said = (out.stderr or out.stdout or "").strip().splitlines()
            return nothing(f"agy /usage exited {out.returncode}"
                           + (f": {said[0][:200]}" if said else ""))
        try:
            payload = json.loads(out.stdout or "")
        except json.JSONDecodeError:
            return nothing("agy's /usage answer was not JSON")

        reading = capacity_from_usage(payload, machine_id=machine_id,
                                      observed_at=observed_at)
        if not reading.established:
            return reading
        try:
            models = self.list_models()
        except Exception:  # noqa: BLE001
            models = []
        reading = capacity_from_usage(payload, machine_id=machine_id,
                                      observed_at=observed_at,
                                      models=models or None)
        self._usage_cache = (time.monotonic(), reading)
        return reading
