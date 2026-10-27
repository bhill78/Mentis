"""Codex adapter. Measured against codex-cli 0.153.0 on Windows.

Codex is the richest of the three, and it is the runtime that broke the
Claude-shaped abstraction hardest:

* It publishes a model catalogue with per-model `supported_reasoning_levels`
  and a `default_reasoning_level`, with a `fetched_at` stamp. Claude publishes
  nothing comparable.
* It records BOTH the actual model and the actual effort, in `turn_context`.
  It is the only one of the three where `actual_effort` is observable.
* Its capacity shape is its own: `used_percent` 0..100 plus `window_minutes`,
  not Claude's 0..1 utilization keyed by window name.
* Crucially, actual model, actual effort and capacity are NOT on the `--json`
  stdout stream. They are only in the rollout session file on disk. So
  "observe what ran" cannot be "parse stdout" -- that assumption died here.
"""

from __future__ import annotations

import glob
import json
import os
import subprocess
import re
import shutil
import sys
import tempfile
import time
import math
from datetime import datetime
from dataclasses import replace

from mentis.worker import boot_command as _boot_command, package_root as _package_root
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

from .. import local_models
from .base import Invocation, RunResult, RuntimeAdapter


#: ITEM TYPES THIS RUNTIME USES FOR TOOL ACTIVITY. Taken from the installed
#: binary's own vocabulary rather than guessed, and read off the `--json`
#: stream this adapter already parses. Naming them here keeps the parse a
#: list of observed facts instead of a rule about what a model can do.
TOOL_ITEMS = (
    "command_execution", "mcp_tool_call", "custom_tool_call",
    "function_call", "file_change", "web_search",
)


#: THE ELEVATED SANDBOX'S GRANT: the passwords of the two machine-wide
#: sandbox accounts (DPAPI-protected) and the marker saying setup for them
#: is done. One pair, valid only together and only while the accounts still
#: have that password -- which every setup run replaces.
_SANDBOX_GRANT = (os.path.join(".sandbox-secrets", "sandbox_users.json"),
                  os.path.join(".sandbox", "setup_marker.json"))

#: What a provisioned home is given from the machine's own CODEX_HOME.
_SANDBOX_CARRIED = ("auth.json", "cap_sid", ".sandbox-secrets",
                    _SANDBOX_GRANT[1])


#: NOT CODEX'S OWN: anything this adapter itself ever left beside the grant
#: -- the `*.mentis.tmp` and `*.mentis-<pid>.tmp` copies of the write-back it
#: no longer makes. Never carried into a home (a `copytree` ignore).
def _not_codexs(folder: str, names: list[str]) -> list[str]:
    return [n for n in names if ".mentis" in n]


#: WHAT A DISPATCHED RUN IS NOT GIVEN, each with why it is outside what the
#: execution declared. A dispatched worker's capabilities are its grant's
#: Mentis tools (`mcp__mentis`, exactly the operations `permits` names) and
#: the local tools it works with inside its `workspace-write` sandbox: the
#: shell (`exec_command`/`write_stdin`), `apply_patch`, `view_image` and
#: `update_plan`. Those are KEPT. Everything below reaches past that sandbox
#: and past Mentis -- to the owner's hosted account, the web, or the desktop.
#:
#: FOUND IN A DISPOSABLE-BRAIN EXPERIMENT, NOT SUPPOSED. A dispatched run on a
#: local model whose Mentis calls all came back `unsupported call` turned to
#: the tools codex offers by default under the owner's ChatGPT login (copied
#: into every provisioned home as `auth.json`): namespace
#: `mcp__codex_apps__sites` created a real Site on the owner's account and
#: minted a repository write credential for it, and
#: `mcp__codex_apps__search_service` searched the web -- with the sandbox's
#: `network_access: false` in force the whole time, because those calls are
#: made by codex itself, not by a sandboxed command. Scratch already withheld
#: them (`_transient_options`); dispatch did not.
#:
#: Each name is one `codex features list` reports on 0.159.2 (read offline,
#: with an empty CODEX_HOME), or the top-level `web_search` setting whose
#: values the binary itself lists ("live", "indexed", "cached", "disabled").
#: Several are already off by default and are said anyway, so that a default
#: changing in a later codex cannot widen a dispatch in silence.
DISPATCH_WITHHELD: tuple[tuple[str, str, str], ...] = (
    ("web_search", '"disabled"',
     "codex's hosted web search: an unrecorded path to the web on the "
     "owner's account. The web is a Mentis capability -- `web_search` and "
     "`web_fetch`, offered through the grant and recorded by the server -- "
     "and the sandbox denies commands the network so that is the only one"),
    ("features.standalone_web_search", "false",
     "the same hosted web search as a separate tool"),
    ("features.apps", "false",
     "the `codex_apps` MCP server -- ChatGPT apps and connectors on the "
     "owner's account (`sites`: create_site, "
     "create_source_repository_write_credential, ...; `search_service`). "
     "This is the surface that created a Site and a write credential"),
    ("features.enable_mcp_apps", "false",
     "apps exposed through MCP: the same hosted surface by another path"),
    ("features.codex_apps_mcp_2026_07_28", "false",
     "the next revision of the `codex_apps` server: the same surface"),
    ("features.plugins", "false",
     "installed plugins, which bring their own MCP servers and connectors "
     "beyond the grant"),
    ("features.remote_plugin", "false",
     "the remote plugin catalogue (the `recommended_plugins` list of the "
     "owner's connectable services -- Gmail, Drive, GitHub, Slack, ...)"),
    ("features.recommended_plugins", "false",
     "suggesting those plugins for installation"),
    ("features.plugin_sharing", "false",
     "sharing plugins from the owner's account"),
    ("features.tool_suggest", "false",
     "suggesting connectors and tools to install"),
    ("features.skill_mcp_dependency_install", "false",
     "installing MCP servers a skill depends on: a new tool server the grant "
     "never named"),
    ("features.browser_use", "false",
     "driving a browser, outside the sandbox and with the owner's sessions"),
    ("features.browser_use_external", "false",
     "driving the owner's own external browser"),
    ("features.browser_use_full_cdp_access", "false",
     "full DevTools access to a browser"),
    ("features.computer_use", "false",
     "controlling the owner's desktop"),
    ("features.image_generation", "false",
     "hosted image generation on the owner's account"),
    # SUB-AGENTS ARE WITHHELD, BY OWNER DECISION: "Codex sub-agents must be
    # subject to the same hosted-tool restrictions as their parent dispatched
    # execution. Keep sub-agent support only if the restriction is
    # independently verified to propagate. Otherwise disable sub-agent
    # spawning on that path." Propagation cannot be verified without a real
    # run, so spawning is off. This flag removes the `multi_agent_v1` tools
    # (what a local, uncatalogued model is offered); a CATALOGUED model's
    # `collaboration.spawn_agent` survives it -- measured on the wire -- and
    # is removed by the catalogue override instead (`DISPATCH_CATALOG`).
    ("features.multi_agent", "false",
     "codex sub-agents: further executions whose inheritance of these "
     "restrictions cannot be verified, and which can name another model"),
    ("features.multi_agent_v2", "false",
     "the second revision of the same sub-agent tools"),
)

#: The ONE change a dispatched run's model catalogue carries: every model's
#: `multi_agent_version` set to "disabled", which is what removes the
#: catalogue-driven `collaboration.spawn_agent` (it takes a `model`
#: parameter) that `features.multi_agent=false` leaves in place for a
#: catalogued model. Nothing else of Scratch's catalogue rewrite is applied.
#:
#: MEASURED with the real codex-cli 0.159.2 against a loopback provider, no
#: account (tests/realcli_dispatch_surface.py): with these, an uncatalogued
#: model's first request carried no `multi_agent_v1` and no `web_search`,
#: `gpt-6-astra`'s no `collaboration.*`, and -- under a FABRICATED login --
#: codex never contacted the apps MCP endpoint (`/backend-api/ps/mcp`) or the
#: plugin catalogue, both of which it did contact without them.
DISPATCH_CATALOG = ("multi_agent_version", "disabled")
DISPATCH_CATALOG_FILE = "dispatch-models.json"


def dispatch_restrictions() -> list[str]:
    """`-c` overrides withholding `DISPATCH_WITHHELD` from a dispatched run.

    Said on the command line rather than in the provisioned config so the
    fresh and the resumed launch carry them identically (resume accepts
    `-c`), and so the argv a run was started with shows them. The catalogue
    override is added beside these by `CodexAdapter._dispatch_catalog`,
    because it names a file written per run.
    """
    flags: list[str] = []
    for key, value, _why in DISPATCH_WITHHELD:
        flags += ["-c", f"{key}={value}"]
    return flags


def _pytest_addopts() -> str:
    """The owner's own PYTEST_ADDOPTS, with pytest's cache turned off: the
    cache a sandboxed run writes is one the owner cannot read or remove."""
    return " ".join(x for x in (os.environ.get("PYTEST_ADDOPTS"),
                                "-p no:cacheprovider") if x)


#: Where a sandboxed command's pytest makes its `pytest-of-<user>`.
SANDBOX_PYTEST_ROOT = "mk4-codex-pytest"


def _sandbox_pytest_root() -> str:
    """A temp root of the sandbox's own, beside the owner's, never shared.

    MEASURED 2026-10-24, the step before any Playwright test: pytest makes
    `%TEMP%\\pytest-of-<USERNAME>` with mode 0o700, which Python (3.12.4+)
    applies on Windows as an ACL of OWNER RIGHTS, SYSTEM and Administrators
    only. USERNAME is the owner's inside the sandbox too, so whichever of the
    owner and the sandbox user ran pytest first owns the one directory both
    use, and the other gets `PermissionError: [WinError 5] Access is denied:
    ...\\pytest-of-bhill` before a test starts. Under this root the sandbox
    user owns its own; the owner's pytest is untouched. Made here, empty, so
    pytest (which creates only the per-user level) finds it.
    """
    root = os.path.join(tempfile.gettempdir(), SANDBOX_PYTEST_ROOT)
    os.makedirs(root, exist_ok=True)
    return root


def _thread_in(stream: str) -> str | None:
    """The thread this run announced, out of a partial `--json` stream."""
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "thread.started" and ev.get("thread_id"):
            return ev["thread_id"]
    return None

#: A line the runtime itself labels a warning.
_WARNING = re.compile(r"^\s*WARNING\s*:", re.IGNORECASE)


def interpret_stderr(stderr: str | None) -> tuple[tuple[str, ...], str | None]:
    """Split what codex wrote on stderr into what IT called a warning, and the rest.

    MEASURED, NOT SUPPOSED. Every Mark IV codex run prints

        WARNING: proceeding, even though we could not create PATH aliases:
        Refusing to create helper binaries under temporary dir "...\\Temp\\"

    because a provisioned CODEX_HOME lives under %TEMP% and codex refuses to
    write its `arg0` helper shims there. Codex says `proceeding` and proceeds:
    reproduced with no auth, no model and no provider configured, on the hosted
    path, emitted before the session banner and before any request. It appears
    on the runs that SUCCEED too -- it was simply never shown, because `error`
    was only read when the exit code was non-zero.

    Taking the whole of stderr as the error therefore made this line the
    recorded cause of an unrelated exit 1 (`opr-257916a18bd3`: the real fault
    was a resume that dropped its local-model constraints), while the actual
    reason reached the record nowhere at all.

    A warning is returned as a warning. Only what is left becomes a candidate
    for the failure reason, and if nothing is left the answer is None -- which
    is the honest answer for a failure the runtime gave no reason for.
    """
    text = (stderr or "").strip()
    if not text:
        return (), None
    warnings, rest = [], []
    # A warning owns its continuation lines: codex wraps one warning over
    # several lines, and half a warning in `error` would be worse than none.
    bucket = None
    for line in text.splitlines():
        if _WARNING.match(line):
            bucket = warnings
            warnings.append(line.strip())
            continue
        if not line.strip():
            bucket = None
            continue
        if bucket is warnings and line[:1].isspace():
            warnings[-1] += " " + line.strip()
            continue
        bucket = rest
        rest.append(line)
    remainder = "\n".join(rest).strip()
    return tuple(warnings), remainder or None


#: How much of a failed run's own output is worth keeping. Enough to
#: reconstruct what happened, bounded so a runaway run cannot fill the record.
EVIDENCE_CHARS = 4000
EVIDENCE_EVENTS = 40


def runtime_evidence(out, events: list[dict]) -> dict:
    """The runtime's own output for a run that failed, verbatim and bounded.

    FOUND BY A REAL FAILURE. `opr-257916a18bd3` recorded exit code, an error
    and notes -- and nothing of stdout. Codex reports what it was doing as
    events on stdout, so the one account of why it exited was discarded on the
    way to the record and is now unrecoverable for that execution.

    THIS IS EVIDENCE, NOT A DIAGNOSIS. It is kept beside Mentis's `error`
    rather than folded into it, and a key is omitted where the runtime gave
    nothing -- an empty dict says the runtime supplied no account, which is
    itself worth recording honestly.
    """
    stdout = (getattr(out, "stdout", "") or "").strip()
    kept: dict = {}
    if stdout:
        kept["stdout_tail"] = stdout[-EVIDENCE_CHARS:]
        kept["stdout_truncated"] = len(stdout) > EVIDENCE_CHARS
    if events:
        kept["raw_events_tail"] = events[-EVIDENCE_EVENTS:]
        kept["raw_events_total"] = len(events)
    return kept


class CodexAdapter(RuntimeAdapter):
    kind = "codex"
    names = RUNTIMES["codex"]
    transient_ok = True
    # NOT FOLDER-BOUNDED, MEASURED 2026-10-10 with `codex sandbox` (0.159.2,
    # Windows) on disposable folders. Under `workspace-write` a command READ
    # a file in a sibling folder, and wrote under %TEMP%, which the sandbox
    # keeps writable; only a write elsewhere was refused. Confining reads is
    # not available here: a permissions profile without full read failed with
    # "elevated Windows sandbox requires effective `:root` read access", and
    # under the unelevated backend with "Restricted read-only access requires
    # the elevated Windows sandbox backend". So Scratch file work is refused
    # on Codex -- and on every local model, which runs through it -- rather
    # than run wider than the folders the owner selected.
    folder_bounds_why = (
        "Codex's sandbox cannot confine reads to the selected folders on "
        "this platform (measured: it reads anywhere, and its commands can "
        "write to the temp directory), so it is not given Scratch file work")
    # input_tokens INCLUDES cached tokens here: measured cached_input_tokens=12288
    # within input_tokens=14561. NOT the same concept as claude's input_tokens.
    accounting = "codex.usage.v1"
    # Measured false: `run` provisions a temp CODEX_HOME that is not retained, so
    # the rollout holding the usage cannot be found again once run() returns.
    reobservable = False
    # THE WIRE THIS HARNESS SPEAKS TO A LOCAL PROVIDER, measured: Ollama's
    # `/v1/responses` counter moves on every local run. A model's tool use is
    # demonstrated on this same wire -- see `foundation.tool_use`.
    local_tool_wire = "responses"

    def capabilities(self) -> frozenset[Capability]:
        return frozenset(
            {
                Capability.DISCOVER,
                Capability.INVOKE_HEADLESS,
                Capability.LIST_MODELS,
                Capability.REQUEST_MODEL,
                Capability.OBSERVE_ACTUAL_MODEL,
                Capability.REQUEST_EFFORT,
                Capability.OBSERVE_ACTUAL_EFFORT,
                Capability.OBSERVE_CAPACITY,
                Capability.SESSION_IDENTITY,
                Capability.RESUME,
                Capability.DELIVER_AT_START,
                Capability.ISOLATE_FROM_MACHINE_CONFIG,
                # Measured end to end 2026-09-23: `--oss --local-provider ollama
                # -m llama3.2:latest` ran and returned a real answer, exit 0.
                Capability.REACH_LOCAL_MODELS,
                # The four reads reach a worker here as a real tool namespace,
                # pre-approved by `default_tools_approval_mode = "approve"` in
                # the provisioned config -- read off the wire, not assumed.
                #
                # THE HARNESS'S CLAIM, NOT EVERY MODEL'S. For a model a local
                # provider serves, Foundation judges this per model from a
                # demonstrated call (`foundation.tool_use`): the namespace was
                # offered to qwen2.5-coder:14b on every run of Local LLM
                # Prelim #196-#202 and it wrote calls as text instead. The
                # demonstration is a run of THIS adapter on the dispatch
                # surface, judged by whether the call reached the namespaced
                # Mentis server -- not a one-function request to the provider.
                Capability.CALL_MENTIS_TOOLS,
                # A `workspace-write` sandbox, under the machine's OWN Windows
                # sandbox mode, which this adapter carries over and never
                # overrides. Four real dispatches wrote files, ran shell
                # commands and ran git under it.
                #
                # ONE KNOWN RESIDUE, AND IT IS NOT A NARROWER CAPABILITY. The
                # sandbox executes as its own local user, so a pytest temp tree
                # it creates in the workspace is ACL-owned by that user and the
                # owner cannot remove it without elevation. That is recorded in
                # full beside Foundation's other unsettled findings and is a
                # policy decision about where a dispatched test run puts its
                # temp files -- NOT evidence that this runtime cannot write
                # unattended, which it demonstrably can. Withholding the
                # capability would misreport the runtime; the honest place for
                # the limit is where it already is.
                Capability.WRITE_UNATTENDED,
                # NOT declared: BUILD_UI, DRIVE_BROWSER. The Windows sandbox
                # denies vite/render-check reads of ancestor directories and
                # cannot launch a browser; every Codex review of UI work came
                # back "incomplete" for that reason.
                # NOT declared: DELIVER_TO_LIVE. `codex queue --thread` exists and
                # looks exactly right, but was not exercised, so it is not claimed.
            }
        )

    # -- discovery ---------------------------------------------------------

    def discover(self, machine_id: str) -> RuntimeInfo:
        exe = self._which("codex")
        if not exe:
            return RuntimeInfo(
                kind=self.kind, present=False,
                version=Observed.unknown("codex not on PATH"),
                executable=Observed.unknown("codex not on PATH"),
                capabilities=frozenset(), machine_id=machine_id,
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
                "actual model/effort and capacity live in the rollout session "
                "file, not on the --json stream",
                "workspace must be trusted or a git repo, and on Windows "
                "[windows] sandbox must be set, or writes silently fail",
            ),
        )

    # -- model catalogue ---------------------------------------------------

    def _codex_home(self) -> str:
        return os.environ.get("CODEX_HOME") or os.path.join(
            os.path.expanduser("~"), ".codex"
        )

    def list_models(self) -> list[ModelInfo]:
        """Every model this runtime can execute -- hosted and local, one list.

        Local models are capacity like any other. They are not a separate list,
        a separate operation or a separate execution path; they differ only in
        the `locality` field, which says where compute happens and implies
        nothing about capability.

        The two sources differ because the runtime forced them to: Codex
        publishes a catalogue for its hosted models, and cannot enumerate local
        ones at all (its model manager fails to parse the provider's response),
        so those are read from the provider that is serving them.
        """
        return self._catalogue_models() + local_models.discover(self.kind)

    def _catalogue_models(self) -> list[ModelInfo]:
        """The runtime's own cached catalogue of hosted models.

        A locally cached copy of a provider fact, carrying its own `fetched_at`,
        so freshness is knowable rather than assumed.
        """
        path = os.path.join(self._codex_home(), "models_cache.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return []
        models = []
        for m in data.get("models", []):
            if m.get("visibility") == "hide":
                continue
            models.append(
                ModelInfo(
                    slug=m.get("slug", ""),
                    runtime=self.kind,
                    efforts=tuple(
                        lvl.get("effort")
                        for lvl in m.get("supported_reasoning_levels", [])
                        if lvl.get("effort")
                    ),
                    default_effort=m.get("default_reasoning_level"),
                    context_window=m.get("context_window"),
                    display_name=m.get("display_name"),
                    locality="hosted",
                    provider="openai",
                )
            )
        return models

    def delivery_opportunities(self) -> list[DeliveryOpportunity]:
        return [
            DeliveryOpportunity(
                runtime=self.kind, moment="session_start",
                mechanism="SessionStart hook in $CODEX_HOME/hooks.json",
                verified=False,
                note="the hook system is real and in use on this machine (with a "
                     "trust-hash gate), but Mark IV has not exercised it",
            ),
            DeliveryOpportunity(
                runtime=self.kind, moment="invocation",
                mechanism="AGENTS.md in CODEX_HOME, and the prompt itself",
                verified=True,
                note="measured the hard way: the host machine's AGENTS.md reached a "
                     "summoned agent and stopped it doing the work",
            ),
            DeliveryOpportunity(
                runtime=self.kind, moment="live_session",
                mechanism="codex queue --thread <id> --message <text>",
                verified=False,
                note="EXERCISED AND DISPROVED for `codex exec`, 2026-09-23. The command "
                     "accepts the message, exits 0 and prints a message id, and the row "
                     "lands in $CODEX_HOME/queue_1.sqlite -- but a running `codex exec` "
                     "never reads it. Sampled every 2s through a live 50s run: "
                     "queued_items stayed at 1 across all 8 steps and dropped to 0 at "
                     "the instant the process exited, i.e. discarded at teardown rather "
                     "than consumed. No artifact, no mention in the event stream. "
                     "`codex exec resume` does not consume it either. Presumably the "
                     "interactive TUI or app-server daemon is its reader; that was not "
                     "tested. Do not re-run this against `codex exec`.",
            ),
        ]

    # -- isolation ---------------------------------------------------------

    def _provision_home(self, workspace: str, record: str | None = None,
                        answers_at: str | None = None,
                        capability: str | None = None,
                        permits=None,
                        reuse: str | None = None,
                        scratch: str | None = None,
                        project: str | None = None) -> str:
        """Build a CODEX_HOME containing only what this invocation should see.

        Measured necessity, not tidiness: with the user's own CODEX_HOME, a
        summoned agent inherited an AGENTS.md instructing it to consult another
        system, and it refused the work and exited 0. `--ignore-user-config`
        was not enough -- it skips config.toml but still loads AGENTS.md.

        EXCLUSION WORKS HERE AND INJECTION DOES NOT -- MEASURED, BOTH WAYS.
        A fresh home means the machine-wide MCP registry is absent, and on
        this machine that registry holds a different system's write-capable
        server under the name `mentis`. A worker dispatched here was asked
        what it could see and reported neither `start_here` nor any other of
        that system's tools. That part is real protection and it is why this
        home is provisioned at all.

        THE `[mcp_servers.mentis]` BLOCK WORKS, AND THAT IS NOW MEASURED.
        This docstring used to say the opposite -- that `codex exec` appeared
        not to load configured servers and that CODEX WORKERS HAD NO MARK IV
        QUERY SURFACE. Both claims were false, and they were believed for as
        long as the only evidence was a worker's own prose about its own
        tools, which had been wrong here before.

        What settled it was reading the wire instead of asking a model. A
        `codex exec` request against the local provider carried 60 tool
        definitions and `tool_choice: auto`, among them:

            {"type": "namespace", "name": "mcp__mentis", "tools": [
               {"type": "function", "name": "find",    ...},
               {"type": "function", "name": "history", ...},
               {"type": "function", "name": "orient",  ...},
               {"type": "function", "name": "resolve", ...}]}

        So the four reads reach a worker as real, self-describing, callable
        tools, and nothing needs to narrate them. AND THEY NOW READ THROUGH
        THE SAME BOUNDARY AS THE LAUNCHER: this server is started with `via`
        and the grant, so it asks the owner over `/api/worker` and opens no
        corpus of its own. It used to boot as a bare `serve(record)` and read
        corpus.db directly, which gave the same four operations two different
        capability boundaries depending only on which wire carried them.
        """
        # THE SESSION LIVES IN HERE, so continuity needs the same one.
        # Measured: resuming a thread from a freshly provisioned home
        # fails with `no rollout found for thread id`, and with the home
        # held stable the same thread continues and remembers. A reused
        # home is rewritten rather than trusted, so an invocation still
        # gets exactly the configuration this adapter intends.
        # THE HOME STAYS UNDER %TEMP%, AND THAT WAS MEASURED, NOT ASSUMED.
        # codex warns here that it `could not create PATH aliases:
        # Refusing to create helper binaries under temporary dir`, which
        # looks like the cause of everything and is not. Four real
        # dispatches from homes under %TEMP% wrote files, ran shell
        # commands, ran git, ran a focused test and answered a Mark IV
        # query whose answer was not in the prompt. The warning costs
        # PATH aliases nothing here needs.
        #
        # What DID fail once, in one of two runs dispatched at the same
        # time, was a single sandboxed exec:
        #   Failed to create unified exec process: delete
        #   <home>\.sandbox-secrets\sandbox_users.json
        # That reproduces at concurrency 3 and never at concurrency 1, and
        # it reproduces the same way with the home OUTSIDE %TEMP% -- so it
        # is contention over codex's own per-exec sandbox user, not the
        # location of this directory, and relocating would fix nothing.
        # It costs the individual tool call; the run still finished.

        home = reuse or tempfile.mkdtemp(prefix="mk4-codex-home-")
        os.makedirs(home, exist_ok=True)
        # CARRIED OVER FROM THE MACHINE'S OWN HOME, not re-created here.
        #
        # `auth.json` is the credential this runtime already has. `cap_sid`
        # is the artifact the ELEVATED Windows sandbox writes once, when the
        # owner approves its setup helper -- and a fresh home without it
        # sends codex off to run that helper again, which raises a UAC
        # prompt. Measured: a dispatched worker failed with
        # `ShellExecuteExW failed to launch setup helper: 1223`, which is
        # ERROR_CANCELLED, because nobody is there to answer it. The owner
        # approved that setup once; asking again in a headless run is asking
        # somebody who is not present.
        # `.sandbox-secrets` IS THE ONE THE OWNER FEELS. It holds the local
        # sandbox user accounts the elevated backend runs commands as, and
        # codex creates it under $CODEX_HOME -- there is no setting or
        # environment variable that points it elsewhere (checked in the
        # binary: the path is built from CODEX_HOME). A freshly provisioned
        # home therefore has none, so codex runs its ELEVATED SETUP HELPER
        # and Windows raises a UAC prompt -- once per dispatch.
        #
        # REPORTED BY THE OWNER and then counted: of 42 provisioned homes on
        # this machine, 22 had a `.sandbox-secrets` codex had just created,
        # which is 22 prompts. The rest are the runs that stalled or failed
        # with `ShellExecuteExW failed to launch setup helper: 1223` --
        # ERROR_CANCELLED -- because nobody was there to answer. `cap_sid`
        # alone was NOT enough, and the earlier measurement missed this
        # entirely: the probe only looked for that failure string, so a
        # prompt somebody ANSWERED left no trace in what the worker said.
        #
        # Carried, not re-created. This reuses the accounts the owner
        # approved once and asserts no policy of its own: same backend, same
        # restricted token, same writable root. Nothing here bypasses the
        # prompt -- it stops asking for something already granted.
        #
        # AND THE MARKER WITH THEM, because without it carrying the secrets
        # did the opposite of what it says above. Measured 2026-10-24: every
        # provisioned home's sandbox log opens with `sandbox setup required:
        # sandbox setup marker missing or incompatible`, then `ensuring
        # sandbox users` -- and that step SETS A NEW PASSWORD on the two
        # machine-wide accounts (CodexSandboxOffline/Online). Their
        # PasswordLastSet matched, to the second, the sandbox_users.json the
        # last of four concurrent dispatches wrote; the four homes and the
        # owner's own ~/.codex each held a different password (DPAPI
        # fingerprints compared). So concurrent runs reset each other's
        # password and every command failed `CreateProcessWithLogonW failed:
        # 1326`, a single run got away with it, and the owner's own copy has
        # been stale since the first dispatch. The marker is what tells codex
        # the carried users are already set up; the secrets alone are not.
        #
        # READ, NEVER WRITTEN BACK. The pair is copied into a NEW home as it
        # is found in the machine's own; nothing this adapter does ever
        # writes into that home (opr-814d8bbd723f). Where the copy is stale
        # -- the owner's codex set up again since, say -- codex finds the
        # marker does not fit the accounts and sets up once more itself; that
        # one extra setup is the accepted cost of never racing anybody over
        # the owner's own files. A REUSED home keeps its own pair as it is:
        # its codex may have set up in it, and copying over that would put
        # back a password the accounts no longer have -- the 1326 failure
        # again. Nothing that is not codex's own file is carried
        # (`_not_codexs`).
        own = self._codex_home()
        missing = []
        secrets_dir = os.path.dirname(_SANDBOX_GRANT[0])
        keeps_own = any(os.path.lexists(os.path.join(home, rel))
                        for rel in _SANDBOX_GRANT)
        for carried in _SANDBOX_CARRIED:
            src = os.path.join(own, carried)
            dst = os.path.join(home, carried)
            if not os.path.exists(src):
                missing.append(carried)
            elif keeps_own and carried in (secrets_dir, _SANDBOX_GRANT[1]):
                continue
            elif os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True,
                                ignore=_not_codexs)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
        # SAID, NOT SWALLOWED. Review found a missing, renamed or unreadable
        # `cap_sid` skipped in silence -- after which codex does exactly what
        # the comment above says it must not, and the only trace is
        # `ShellExecuteExW failed to launch setup helper: 1223` buried in
        # stderr of a run that failed for no stated reason. Recorded on the
        # adapter so `run` can say it plainly. Not an error: the unelevated
        # backend needs no cap_sid, so this is a fact, not a verdict.
        self._home_gaps[home] = tuple(missing)
        mode = self._windows_sandbox_mode()
        windows = ["[windows]", f'sandbox = "{mode}"', ""] if mode else []
        lines = [
            *windows,
        ]
        # KEYED ON THE MODE, not on a line this method just generated.
        # Where the owner names no mode, codex applies its own default and
        # this cannot know which -- so nothing is assumed, which is the same
        # answer as before and now says why.
        if mode == "unelevated":
            # ONE WRITABLE ROOT, AND ONLY FOR THE BACKEND THAT NEEDS IT.
            # Measured on codex 0.153: the UNELEVATED restricted-token
            # backend derives its writable roots from cwd AND $TMPDIR and
            # refuses two disjoint ones -- `cannot enforce split writable
            # root sets` -- taking the whole shell tool down with it.
            # Dropping the temp root leaves the workspace as the only one.
            #
            # The ELEVATED backend handles split roots, and applying this to
            # it was actively harmful: with %TEMP% unwritable, a worker
            # running the test suite got `unable to open database file`,
            # because pytest builds its fixtures there. Anything that needs
            # a temp directory -- a compiler, git, an installer -- would
            # have failed the same way.
            lines += [
                "[sandbox_workspace_write]",
                "exclude_tmpdir_env_var = true",
                "exclude_slash_tmp = true", "",
            ]
        # NO PYTEST CACHE IN THE WORK, said where codex applies it to every
        # command it spawns, not only inherited (see `PYTEST_ADDOPTS` in
        # `run`): a dispatched run on 2026-10-08 still left an owner-
        # unreadable `.pytest_cache` with the variable set only on the
        # process.
        lines += ["[shell_environment_policy.set]",
                  f"PYTEST_ADDOPTS = {json.dumps(_pytest_addopts())}"]
        # NOT FOR THE UNELEVATED BACKEND: its commands run as the owner, so
        # there is no second user to collide with, and %TEMP% is not one of
        # its writable roots (above).
        if mode != "unelevated":
            lines += ["PYTEST_DEBUG_TEMPROOT = "
                      + json.dumps(_sandbox_pytest_root())]
        lines += [""]
        # WHAT THIS SANDBOX CANNOT BE GIVEN: A LISTING OF THE PROFILE ROOT.
        # Measured 2026-10-24 on codex 0.159.2, elevated: commands run as
        # CodexSandboxOffline, which may traverse but not list C:\Users\<owner>
        # (no ACE of the sandbox's there; codex grants per child of it). Every
        # worktree and scratch lives under that root, and esbuild lists each
        # ancestor of its working directory and treats Windows' access denied
        # as fatal -- so `npm run build` fails in mentis-render-check with
        # `Cannot read directory "../../..": Access is denied`. Codex cannot
        # be told otherwise from here: under `":root" = "read"` an explicit
        # `"<dir>" = "read"` writes no ACE ("read roots delegated") and the
        # directory stays unlistable; a profile without `:root` read is
        # refused by this backend; and a `write` entry would widen writes.
        # The remedy is the owner's to choose (opr-b52c1ed54a85), not a flag.
        # Where the run starts, and the project it is given where that is a
        # separate directory: both are places this invocation works.
        for trusted in dict.fromkeys(x for x in (workspace, project) if x):
            lines += [
                f"[projects.'{trusted.lower()}']", 'trust_level = "trusted"', "",
            ]
        if record:
            # THE SAME BOUNDED BOUNDARY AS THE LAUNCHER BESIDE IT.
            boot = _boot_command(record, via=answers_at,
                                 capability=capability,
                                 permits=permits, scratch=scratch,
                                 project=project)
            lines += [
                "[mcp_servers.mentis]",
                f"command = {json.dumps(sys.executable)}",
                f'args = ["-I", "-c", {json.dumps(boot)}]',
                # DECLARED IS NOT THE SAME AS CALLABLE, and this is the line
                # that makes the difference. Measured on a real dispatch: the
                # four tools were present and the model tried them --
                # `orient`, `orient`, `find`, `find` -- and not one call
                # reached /api/worker. Codex refused each one and said why:
                #   "Tool execution requires approval, but this session's
                #    approval policy is `never`."
                # A headless dispatch has nobody to approve anything, so an
                # unapproved tool is an absent tool -- and the worker,
                # reasonably, reported that it had no Mark IV tools at all.
                #
                # This pre-approves whatever the server OFFERS, which is no
                # longer always the four reads: an execution dispatched to carry
                # an unaddressed request is also offered bounded organising
                # operations. The approval is blanket within this one namespace,
                # so the bound is what `serve` offers -- `permits`, derived by
                # Foundation from the grant's scope -- and every call is checked
                # again against the grant at /api/worker. An ordinary worker is
                # therefore offered, and can call, only the reads and
                # `request_decision`, whatever this line says about approval.
                'default_tools_approval_mode = "approve"',
                "",
            ]
        with open(os.path.join(home, "config.toml"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        return home

    #: Written beside the work, removed after it. Dotted so it sorts out of
    #: the way, and named for what it is.
    #: The stem every per-invocation launcher shares. Kept so a workspace
    #: can be recognised as having had one, and so `.gitignore`-style rules
    #: have something stable to name.
    LAUNCHER = ".mentis-query"

    @staticmethod
    def _launcher_name(capability: str) -> str:
        """One launcher per invocation, not one per workspace.

        FOUND BY REVIEW. Every invocation wrote the same filename, so two
        workers in one workspace overwrote each other's grant and address,
        and whichever finished first deleted the file the other was still
        using. Named from the grant, which is already unique to the run.
        """
        import hashlib
        tag = hashlib.sha256(capability.encode("utf-8")).hexdigest()[:10]
        return f".mentis-query-{tag}.py"

    def _write_launcher(self, workspace: str, record: str,
                        answers_at: str, capability: str) -> str:
        """Put the query launcher where Codex is already allowed to read.

        MEASURED FAILURE THIS EXISTS TO FIX. The launcher used to live in the
        provisioned CODEX_HOME under %TEMP%, and a hosted worker ran exactly
        the right command and got `[Errno 13] Permission denied` opening it.
        The same file, same home, runs fine outside the sandbox -- so this was
        never a filesystem permission, it was scope: Codex does not read
        %TEMP%, and says as much when it refuses to put its own helper
        binaries there.

        The workspace is already an authorised root, so the launcher goes
        beside the work rather than the sandbox being widened to reach it.
        `--add-dir` would have done it too and would have granted WRITE to a
        directory for the sake of one read, which is the wrong trade.

        AND IT OPENS NOTHING. Being able to READ the launcher was only half
        of it: the launcher used to open the corpus itself, and a sandboxed
        worker cannot -- the spine is WAL, SQLite writes `-shm` beside a WAL
        database before it will read one, and the corpus is outside the one
        directory this worker may write. Measured, from inside the sandbox:
        `attempt to write a readonly database`. So it stops opening the
        corpus and asks the process that already has it open instead. The
        worker sends an operation, its arguments and which corpus it means;
        no corpus handle exists on this side of the wire, and no filesystem
        permission the worker holds decides what it may learn of the record.

        Still transport only: `ask` parses the command and hands it across,
        and the far side runs `_result` on the same `Surface` the MCP server
        and the web seam use. One resolver, three wires.
        """
        path = os.path.join(workspace, self._launcher_name(capability))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join([
                "import sys",
                f"sys.path.insert(0, r{_package_root()!r})",
                "from mentis.worker import ask",
                f"raise SystemExit(ask(r{record!r}, sys.argv[1:], "
                f"via=r{answers_at!r}, capability=r{capability!r}))",
                "",
            ]))
        return path

    def project_writable(self) -> bool:
        """Whether a project beside the private scratch can be written.

        NOT UNDER THE UNELEVATED BACKEND, measured on codex 0.153: it refuses
        two disjoint writable roots (`cannot enforce split writable root
        sets`) and takes the shell down with it. There the project stays
        readable and the run is told it is not writable, rather than the
        scratch being given up to make it so.
        """
        return self._windows_sandbox_mode() != "unelevated"

    def _project_root(self, inv) -> list[str]:
        """The project as a second writable root, where there is one and the
        sandbox can hold two. Config rather than a flag, so the fresh and the
        resumed launch say it the same way."""
        if not self.project_writable():
            return []
        # THE SERVER'S WRITABLE ROOTS JOIN THE PROJECT here, in the same
        # sandbox: measured on the elevated backend, a run given
        # `--writable-root C:\Work\Mentis-Test-Server` writes there and is
        # still refused everywhere else ("Access to the path ... is denied").
        roots = ([inv.project] if inv.project else []) + [
            w for w in inv.writable if w != inv.project]
        if not roots:
            return []
        return ["-c", "sandbox_workspace_write.writable_roots="
                + json.dumps(roots)]

    def _where_it_runs(self, inv, *, resuming: bool) -> list[str]:
        """The flags that decide WHICH MODEL runs and WHO SERVES IT.

        ONE BUILDER FOR BOTH PATHS, BECAUSE TWO DRIFTED AND THE DRIFT WAS
        SILENT. The fresh path named the model and, for a local one, pointed
        the runtime at local compute; the resume path named neither. So a
        session created against a local model resumed onto the runtime's own
        hosted default, reporting success the whole way.

        MEASURED ON THE REAL CLI BEFORE ANY OF THIS WAS WRITTEN. Resuming such
        a session with no constraints: exit 0, a reply, and Ollama's
        `/v1/responses` counter DID NOT MOVE. That session's own rollout then
        held `"model":"llama3.2:latest"` six times from the fresh run and
        `"model":"gpt-6-astra"` eleven times from the resumes. Nothing was
        wrong with the record -- the substitution happened beneath it.

        WHAT RESUME WILL AND WILL NOT TAKE, read from `codex exec resume
        --help` on 0.153.0 rather than assumed:

            -m/--model              accepted
            --skip-git-repo-check   accepted
            -c/--config             accepted
            --oss                   NOT ACCEPTED -- no such flag on resume
            --local-provider        NOT ACCEPTED
            -s/--sandbox            NOT ACCEPTED (said as `-c sandbox_mode`)
            -C/--cd                 NOT ACCEPTED (the process cwd carries it)

        So the local provider cannot be a flag here. It is the SAME fact said
        as config: `-c model_provider="<provider>"`. Measured on that same
        session -- with it, Ollama's counter moved 45 -> 46 and the turn
        completed; `model_provider="oss"` failed and the counter stayed put.
        The value is the provider's own name from the catalogue, never a
        literal in this file, so another provider needs no code here.

        `inv.model` IS THE BINDING, not the caller's wish: Foundation builds
        the Invocation with `model=inst.requested_model`. Preserving it is
        therefore preserving what the session is eligible to be resumed under,
        which is the invariant -- and it covers the case an explicit-model
        check cannot, where the caller names no model at all and reuse picks a
        locally-bound session.

        None means no model was ever bound, so there is nothing to preserve and
        nothing is said.
        """
        out: list[str] = []
        if inv.model:
            out += ["-m", inv.model]
            provider = self._local_provider_for(inv.model)
            if provider:
                # A local model is reached through the same runtime and the
                # same operation; it just needs the runtime pointed at local
                # compute. This is the whole of "local models are capacity".
                out += (["-c", f'model_provider="{provider}"'] if resuming
                        else ["--oss", "--local-provider", provider])
        if inv.effort:
            # SENT FOR LOCAL MODELS TOO, because it was measured, not supposed.
            # This used to skip them on the grounds that an effort the runtime
            # "cannot honour" should not be sent. Measured on codex 0.153 with
            # `--oss --local-provider ollama -m ornith:9b` and Ollama 0.34:
            # `model_reasoning_effort="none"` reaches the provider and is
            # honoured -- no reasoning item on the stream, where unset produced
            # one -- while `low` and `minimal` are accepted and ignored. What a
            # local model receives is therefore only ever an explicit request
            # (selection derives none for it), and whether the provider honoured
            # it is observed from the stream, never inferred from having asked.
            out += ["-c", f'model_reasoning_effort="{inv.effort}"']
        return out

    def provider_of(self, model: str | None) -> str | None:
        """Public name for the same question. See `RuntimeAdapter.provider_of`.

        The answer was already computed at launch to decide whether to pass
        `--oss --local-provider`, and then discarded -- so the durable record
        said `runtime: codex` and nothing about who actually served the model.
        This is the same lookup, reachable by the caller that records provenance.
        """
        return self._local_provider_for(model)

    def _local_provider_for(self, model: str | None) -> str | None:
        """Which local provider serves this model, if any.

        Asked of the providers rather than guessed from the slug's shape: an
        `ollama`-style `name:tag` is a naming convention, not evidence.
        """
        if not model:
            return None
        for m in local_models.discover(self.kind):
            if m.slug == model:
                return m.provider
        return None

    def dispatch_surface(self) -> dict:
        """What decides the tools a dispatched run is offered, from this
        side: the codex version, the withheld flags and the catalogue
        override. Part of a tool-use verdict's fingerprint
        (`tool_use.surface_fingerprint`), so a change here invalidates it."""
        return {"runtime": self.kind, "version": self._installed_version(),
                "restrictions": dispatch_restrictions(),
                "catalog_override": list(DISPATCH_CATALOG)}

    #: (executable, its mtime) -> `codex --version`, so the fingerprint asks
    #: the binary once per install rather than once per question.
    _versions: dict = {}

    def _installed_version(self) -> str | None:
        exe = self._which("codex")
        if not exe:
            return None
        try:
            stamp = (exe, os.path.getmtime(exe))
        except OSError:
            stamp = (exe, None)
        if stamp not in self._versions:
            try:
                out = self._run([exe, "--version"], timeout=60)
                self._versions[stamp] = ((out.stdout or "").strip() or None
                                         if out.returncode == 0 else None)
            except Exception:  # noqa: BLE001
                return None
        return self._versions[stamp]

    def _read_catalog(self, why: str) -> list[dict]:
        """The runtime's cached model catalogue, every entry a dict with a
        slug, or ValueError(why). Shared by Scratch and dispatch."""
        path = os.path.join(self._codex_home(), "models_cache.json")
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ValueError(f"{why} ({exc})") from exc
        models = data.get("models") if isinstance(data, dict) else None
        if (not isinstance(models, list) or not models
                or not all(isinstance(info, dict) and isinstance(info.get("slug"), str)
                           for info in models)):
            raise ValueError(why)
        return models

    def _dispatch_catalog(self, home: str, model: str | None) -> list[str]:
        """The catalogue override a dispatched run carries -- see
        `DISPATCH_CATALOG` -- written into its own home.

        A LOCAL model needs none: it is not in the catalogue, codex gives it
        fallback metadata, and `features.multi_agent=false` removes its
        sub-agent tools (measured on the wire). No entry is synthesised for
        it. Any OTHER run -- a named hosted model, or none named, which is
        codex's hosted default -- is REFUSED if the catalogue cannot be read,
        rather than run with sub-agents it was meant not to have.
        """
        try:
            where = os.path.join(self._codex_home(), "models_cache.json")
            models = self._read_catalog(
                f"Codex's cached model catalog was not found or could not be "
                f"read at {where}, and a dispatch needs it to withhold "
                f"sub-agents from a catalogued model. Run `codex` once while "
                f"logged in (it writes models_cache.json there), then retry. "
                f"Local models are unaffected")
        except ValueError:
            if model and self._local_provider_for(model):
                return []
            raise
        key, value = DISPATCH_CATALOG
        for info in models:
            info[key] = value
        path = os.path.join(home, DISPATCH_CATALOG_FILE)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"models": models}, fh)
        return ["-c", "model_catalog_json=" + json.dumps(path)]

    def _transient_options(self, home: str, model: str | None) -> list[str]:
        """Remove native tools using the runtime's model catalog and switches.

        apply_patch_freeform is removed in 0.159.2; the catalog owns patching.
        Missing metadata refuses the answer rather than permitting edits.
        """
        models = self._read_catalog("Scratch needs Codex's cached model "
                                    "catalog to remove native tools")
        if model and not any(m.get("slug") == model for m in models):
            local = next((m for m in local_models.discover(self.kind)
                          if m.slug == model and m.locality == "local"
                          and m.provider in ("ollama", "lmstudio")), None)
            if local is None:
                raise ValueError("Scratch cannot bound native tools for a model absent from the Codex catalog and local discovery")
            # A catalog entry is needed to override Codex's fallback native
            # tools. These are conservative runtime metadata, not a copy of
            # a hosted model's instructions, context size or capabilities.
            # Local tool-call suitability remains Foundation's ledger gate.
            models.append({
                "slug": local.slug, "display_name": local.display_name or local.slug,
                "description": "Discovered local model for read-only Scratch",
                "default_reasoning_level": "none", "supported_reasoning_levels": [],
                "visibility": "list", "supported_in_api": False, "priority": 0,
                "base_instructions": "", "supports_reasoning_summaries": False,
                "support_verbosity": False, "supports_parallel_tool_calls": False,
                "input_modalities": ["text"],
                "truncation_policy": {"mode": "tokens", "limit": 10000},
            })
        for info in models:
            # Models defaulting to code mode otherwise hide their MCP tools
            # when that executable tool is removed for a read-only answer.
            info["tool_mode"] = "direct"
            info["multi_agent_version"] = "disabled"
            info["supports_search_tool"] = False
            info["node_repl_disabled"] = True
            info["shell_type"] = "disabled"
            info["apply_patch_tool_type"] = None
            info["experimental_supported_tools"] = []
        catalog = os.path.join(home, "scratch-models.json")
        with open(catalog, "w", encoding="utf-8") as fh:
            json.dump({"models": models}, fh)
        flags = ["--ephemeral", "-s", "read-only",
                 "-c", 'approval_policy="never"',
                 "-c", "model_catalog_json=" + json.dumps(catalog),
                 "-c", 'web_search="disabled"',
                 "-c", "tools.update_plan.enabled=false",
                 "-c", "tools.experimental_request_user_input.enabled=false"]
        for feature in ("shell_tool", "multi_agent", "view_image", "apps",
                        "browser_use", "computer_use", "image_generation",
                        "goals", "plugins",
                        "code_mode", "code_mode_only", "js_repl", "tool_suggest",
                        "deferred_executor", "exec_permission_approvals", "token_budget",
                        "current_time_reminder", "sleep_tool",
                        "send_message_to_user_async"):
            flags += ["-c", f"features.{feature}=false"]
        return flags

    def run(self, inv: Invocation) -> RunResult:
        exe = self._which("codex")
        if not exe:
            return RunResult(None, 127, None, Observed.unknown("runtime absent"),
                             Observed.unknown("runtime absent"), error="codex not found")

        # A CONSTRAINT THAT CANNOT BE HONOURED IS REFUSED, NEVER SUBSTITUTED.
        #
        # The invariant is that explicit execution constraints survive
        # continuation, or continuation does not happen. Preserving them is
        # possible whenever the catalogue still places the model -- but if a
        # session was bound to a model that neither the local providers nor the
        # runtime's own catalogue now offers, there is nowhere to put it, and
        # launching anyway hands the decision to the runtime's default. That is
        # the exact silent substitution this whole repair exists to end, so it
        # is refused in words instead.
        #
        # The ordinary reason is a local provider that has stopped: the model
        # was real an hour ago and is unplaceable now. Failing here is right --
        # Foundation records it against the expectation, and the work can start
        # fresh once the provider is back, which is the honest outcome.
        if inv.model and not self._local_provider_for(inv.model):
            catalogue = {m.slug for m in self._catalogue_models()}
            if catalogue and inv.model not in catalogue:
                why = (f"{inv.model!r} was explicitly requested, and nothing "
                       f"now offers it: no local provider serves it and it is "
                       f"not in this runtime's catalogue. Refusing rather than "
                       f"letting the runtime choose a different model.")
                return RunResult(None, 1, None,
                                 Observed.unknown("refused before launch"),
                                 Observed.unknown("refused before launch"),
                                 error=why)

        transient_home = (tempfile.mkdtemp(prefix="mk4-scratch-codex-", dir=inv.cwd)
                          if inv.transient else None)
        try:
            home = (self._provision_home(inv.cwd, inv.record,
                                     answers_at=inv.answers_at,
                                     capability=inv.capability,
                                     permits=inv.permits,
                                     reuse=transient_home or inv.runtime_home,
                                     scratch=inv.scratch,
                                     project=None if inv.transient else inv.project)
                    if inv.isolate or inv.transient else self._codex_home())
        except Exception as exc:
            if not inv.transient:
                raise
            self._discard_scratch(transient_home)
            return RunResult(None, -1, None,
                             Observed.unknown("transient setup refused"),
                             Observed.unknown("transient setup refused"),
                             error=f"Scratch read-only setup refused: {exc}")
        env = {"CODEX_HOME": home,
               # NO PYTEST CACHE IN THE WORK. The sandbox runs commands as its
               # own local user, and the `.pytest_cache` pytest makes there is
               # one the owner cannot even read: measured 2026-10-08, all 9
               # unreadable caches in the live Brain's worktrees were Codex
               # runs', and each one kept its worktree from ever being
               # removed. Tests run the same; only the cache is not written.
               "PYTEST_ADDOPTS": _pytest_addopts()}
        transient_flags = []
        if inv.transient:
            try:
                transient_flags = self._transient_options(home, inv.model)
            except (OSError, ValueError, TypeError) as exc:
                self._discard_scratch(home)
                return RunResult(None, -1, None,
                                 Observed.unknown("transient setup refused"),
                                 Observed.unknown("transient setup refused"),
                                 error=f"Scratch read-only setup refused: {exc}")
        # REFUSED HERE RATHER THAN STALLED THERE.
        #
        # The ELEVATED backend runs commands as local sandbox users, and if
        # `.sandbox-secrets` is absent codex creates them through an
        # admin-elevated setup helper -- a UAC prompt. In a dispatched run
        # nobody is at the machine, so the process does not fail: it WAITS,
        # and with no deadline it waits forever. Owner-reported, then seen
        # directly: two `consent.exe` dialogs open on the desktop with runs
        # blocked behind them.
        #
        # So if the grant cannot be carried, say so before launching. This is
        # the honest failure and it is actionable -- the owner approves the
        # sandbox setup once from their own codex, and every dispatch after
        # that reuses it. Nothing here bypasses the prompt or lowers the
        # sandbox; it declines to ask somebody who is not there.
        no_grant = (inv.isolate and not inv.transient
                    and ".sandbox-secrets" in self._home_gaps.get(home, ())
                    and self._windows_sandbox_mode() == "elevated")
        if no_grant:
            return RunResult(
                None, -1, None,
                Observed.unknown("sandbox grant absent"),
                Observed.unknown("sandbox grant absent"),
                error=("the elevated Windows sandbox has no approved user "
                       "grant to carry into this run: no .sandbox-secrets in "
                       f"{self._codex_home()}. Run codex once interactively "
                       "and approve its sandbox setup, then dispatches reuse "
                       "it. Refused rather than launched, because codex would "
                       "raise a UAC prompt with nobody there to answer it."),
                runtime_home=home)

        # A DISPATCH'S CATALOGUE OVERRIDE (see `_dispatch_catalog`), written
        # into its own provisioned home -- never into the machine's own
        # CODEX_HOME, so an unisolated run gets a directory of its own that
        # is removed when it ends.
        catalog_flags: list[str] = []
        catalog_dir = None
        if not inv.transient:
            if not inv.isolate:
                catalog_dir = tempfile.mkdtemp(prefix="mk4-codex-catalog-")
            try:
                catalog_flags = self._dispatch_catalog(catalog_dir or home,
                                                       inv.model)
            except (OSError, ValueError, TypeError) as exc:
                if catalog_dir:
                    shutil.rmtree(catalog_dir, ignore_errors=True)
                return RunResult(
                    None, -1, None,
                    Observed.unknown("dispatch setup refused"),
                    Observed.unknown("dispatch setup refused"),
                    error=(f"dispatch refused before launch: {exc}. Without "
                           "the catalogue override a catalogued model keeps "
                           "codex sub-agents, which this path withholds."),
                    runtime_home=home if inv.isolate else None)

        prompt = inv.prompt
        if inv.deliver:
            # Codex's verified start-of-invocation delivery is the prompt itself.
            prompt = f"{inv.deliver}\n\n---\n\n{prompt}"
        launcher = None
        if inv.record and inv.answers_at and inv.capability and inv.isolate and not inv.transient:
            # The capability, and how to reach it. Ahead of the work, because
            # a worker that has finished deciding how to answer will not go
            # looking for a better way to.
            #
            # No `answers_at` means nothing owning this record is listening,
            # so there is no capability to offer and none is claimed. That is
            # the honest gap, and it is better than a command that can only
            # fail -- but a worker whose owner goes away MID-run is told so
            # explicitly by `ask` rather than quietly reading the corpus.
            launcher = self._write_launcher(inv.cwd, inv.record,
                                            inv.answers_at, inv.capability)
            # NOTHING IS NARRATED. The four Mark IV reads reach this runtime
            # as REAL tools -- measured on the wire: `codex exec` against the
            # local ollama provider sent 60 tool definitions including the
            # namespace `mcp__mentis` with `find`, `history`, `orient` and
            # `resolve`, each self-describing, with `tool_choice: auto`.
            #
            # What used to be prepended here told the worker the opposite --
            # `You have no MCP tools on this runtime` -- and then recited a
            # shell recipe naming the same four operations. That sentence was
            # measured false, and the ~800 characters carrying it were
            # delivered on EVERY dispatch, self-contained or not. A worker
            # reading tool descriptions needs no tutorial about them.
            #
            # The launcher and the grant below are NOT removed. Both wires now
            # end at the same bounded boundary -- `/api/worker` under this
            # invocation's grant -- so neither is the privileged one, and a
            # worker holds no corpus handle whichever it uses. Removing the
            # narration was never a reason to remove a transport.

        # THE BACKSTOP to `resume_eligibility`: a caller that reaches `run`
        # with a thread created with sub-agents gets a NEW thread in the same
        # home -- what Foundation does on an ineligible resume -- and is told.
        resume_ref = inv.resume_ref if not inv.transient else None
        resume_note = None
        if resume_ref:
            rollouts = glob.glob(os.path.join(home, "sessions", "**",
                                              f"*{resume_ref}.jsonl"),
                                 recursive=True)
            resume_note = (self.subagents_at_creation(rollouts[0]) if rollouts
                           else None)
            if resume_note:
                resume_ref = None
        if resume_ref:
            # RESUME TAKES NEITHER `-s` NOR `-C`, so the sandbox the fresh
            # path states on the command line has to be stated as config here
            # instead. Review found the two paths launching differently: with
            # nothing said, a resumed run fell back to whatever codex defaults
            # to, which is the one divergence that could let a resumed agent
            # report success while every write was refused -- or run wider
            # than the fresh path. Said explicitly, they now match.
            #
            # `-C` needs no equivalent: `_run` starts the process with
            # `cwd=inv.workspace`, so the working directory is the same fact
            # by another means.
            #
            # And `-` for the prompt, for the same reason the fresh path uses
            # it: over roughly 32KB an argv prompt fails on Windows with
            # WinError 206, and a resumed dispatch is the one carrying the
            # most accumulated material.
            cmd = ([exe, "exec", "resume", resume_ref, "--json",
                    "-c", 'sandbox_mode="workspace-write"',
                    "--skip-git-repo-check"]
                   + self._project_root(inv)
                   # THE SAME WITHHELD SURFACE AS THE FRESH LAUNCH: a resumed
                   # run must not get back what its first launch was denied.
                   + dispatch_restrictions() + catalog_flags
                   + self._where_it_runs(inv, resuming=True) + ["-"])
        else:
            cmd = ([exe, "exec", "--json", "-C", inv.cwd,
                    "--skip-git-repo-check"]
                   + (transient_flags if inv.transient else
                      ["-s", "workspace-write"] + self._project_root(inv)
                      + dispatch_restrictions() + catalog_flags)
                   + self._where_it_runs(inv, resuming=False))
            # `-` makes codex read the prompt from stdin. Measured: passed as
            # an argv element, a prompt over roughly 32KB fails on Windows with
            # "[WinError 206] The filename or extension is too long", which is
            # well below the size of an ordinary review or context payload.
            cmd += ["-"]

        try:
            # The prompt itself is the stdin that gets closed. Measured: with an
            # inherited pipe and nothing to read, `codex exec` prints "Reading
            # additional input from stdin..." and blocks until killed.
            out = self._run(cmd, cwd=inv.cwd, timeout=inv.timeout_s, env=env,
                            stdin=prompt, observer=inv.observer,
                            parse=self.observe_event,
                            **({"cancel_event": inv.cancel_event}
                               if inv.cancel_event is not None else {}))
        except subprocess.TimeoutExpired as exc:
            # A DEADLINE THE CALLER ASKED FOR, NOT A RUNTIME FAILURE. Said
            # as itself so nothing downstream has to read it out of an
            # error string, and so what had already been delivered to a
            # running process is not mistaken for never having crossed.
            #
            # THE HOME AND THE THREAD SURVIVE THE BOUNDARY. Review found
            # this branch dropping both while the branch below deliberately
            # keeps the home -- so a deadline leaked a home holding a copy
            # of the runtime credential that no sweep could ever name, and
            # discarded the thread id sitting in the partial stream.
            return RunResult(None if inv.transient else _thread_in(self._partial(exc)), -1, None,
                             Observed.unknown("deadline reached"),
                             Observed.unknown("deadline reached"),
                             error=str(exc), timed_out=True,
                             runtime_home=None if inv.transient else home)
        except Exception as exc:  # noqa: BLE001
            # The home is named even here: a launch that failed still
            # provisioned one, and a home nothing names can never be swept.
            return RunResult(None, -1, None, Observed.unknown("run failed"),
                             Observed.unknown("run failed"),
                             error=f"{type(exc).__name__}: {exc}",
                             runtime_home=None if inv.transient else home)
        finally:
            # The launcher belongs to one invocation. It is written beside the
            # work because that is where Codex may read, and taken away again
            # because somebody's workspace is not ours to leave things in.
            if launcher:
                try:
                    os.remove(launcher)
                except OSError:
                    pass

            if inv.transient:
                self._discard_scratch(home)
            elif home != self._codex_home():
                # THE HOME'S OWN MTIME IS WHAT `observe_capacity` WALKS BY,
                # newest first and bounded. A run writes its rollout deep
                # under sessions/, which does not move the home's mtime; that
                # it moved anyway (root-level SQLite -wal/-shm files come and
                # go each run) was observed, not promised -- a resumed old
                # home whose -wal files survived a crash would stay buried.
                # So every run in a provisioned home says it was used.
                try:
                    os.utime(home)
                except OSError:
                    pass
            if catalog_dir:
                shutil.rmtree(catalog_dir, ignore_errors=True)

        events = []
        for line in (out.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        tools_used: list[str] = []
        reasoning_items = 0
        thread_id = None
        reported = None
        usage: dict = {}
        for ev in events:
            if ev.get("type") == "thread.started":
                thread_id = ev.get("thread_id")
            if ev.get("type") == "turn.completed":
                usage = ev.get("usage") or {}
            item = ev.get("item") or {}
            if item.get("type") == "agent_message" and item.get("text"):
                reported = item["text"]
            # Counted once, on completion, like a tool call.
            if (item.get("type") == "reasoning"
                    and ev.get("type") in ("item.completed", "item_completed")):
                reasoning_items += 1
            # ONCE PER CALL, NOT ONCE PER EVENT. This stream announces an item
            # when it starts and again when it finishes, so counting every
            # event reported each tool twice -- four reads came back as eight.
            # The completed one is the call that actually happened.
            if (item.get("type") in TOOL_ITEMS
                    and ev.get("type") in ("item.completed", "item_completed")):
                # The tool as the runtime named it. `name` where there is one,
                # otherwise the item type, which is what this runtime calls a
                # shell or a patch. Never invented, never normalised.
                tools_used.append(str(item.get("name")
                                      or item.get("tool")
                                      or item.get("server")
                                      or item["type"]))

        actual_model, actual_effort, capacity = (
            (Observed.unknown("ephemeral run has no saved rollout"),
             Observed.unknown("ephemeral run has no saved rollout"), None)
            if inv.transient else self._read_rollout(home, thread_id))

        warnings, stderr_rest = interpret_stderr(out.stderr)
        failed = out.returncode != 0
        return RunResult(
            session_ref=None if inv.transient else thread_id,
            exit_code=out.returncode,
            reported=reported,
            actual_model=actual_model,
            actual_effort=actual_effort,
            usage=usage,
            capacity=capacity,
            # WHAT MENTIS WILL SAY WENT WRONG -- and never a line codex
            # itself labelled a warning. See `interpret_stderr`.
            error=stderr_rest if failed else None,
            warnings=((f"resume of {inv.resume_ref} refused: {resume_note}",)
                      if resume_note else ()) + tuple(warnings),
            # KEPT ONLY WHERE SOMETHING FAILED, because that is the case the
            # record could not previously reconstruct. Nothing is synthesised:
            # absent evidence stays absent.
            evidence=runtime_evidence(out, events) if failed else {},
            raw_events=events,
            transport_ok=getattr(out, "transport_ok", True),
            transport_note=getattr(out, "transport_note", None),
            # Said back, because the thread this run created can only be
            # resumed from here and nothing else knows where it is.
            runtime_home=None if inv.transient else home,
            # OBSERVED, NOT INFERRED. What this run actually called, and the
            # fact that this runtime reports such things at all -- so an empty
            # list means `none were called`, not `we could not tell`.
            tool_calls=tuple(tools_used),
            tool_calls_observable=True,
            reasoning_items=reasoning_items,
        )

    # -- while it runs ---------------------------------------------------------
    #
    # WHAT `codex exec --json` IS MEASURED TO EMIT (docs/evidence/
    # runtime-probe-codex.md, and verbatim failure streams kept in the record,
    # e.g. tests/fixtures/runtime_streams/codex_refresh_token_reused.jsonl):
    # `thread.started{thread_id}`, `turn.started`, `item.started` and
    # `item.completed` each carrying `item{id,type,...}`, `turn.completed`,
    # `error{message}`, `turn.failed{error{message}}`. An item is announced
    # when it starts and again when it finishes (see TOOL_ITEMS above), so a
    # tool call is open from the one to the other, keyed by the item's id.
    #
    # NOT ESTABLISHED: helpers. Nothing on this stream reports a runtime-
    # internal helper, so none is claimed -- `observes` does not name them.
    # Reasoning arrives as a completed `reasoning` item, which is an explicit
    # report and is treated like Claude's thinking-token events.
    observes = ("session", "tools", "model-turns", "thinking")

    def observe_event(self, ev: dict, obs) -> None:
        kind = ev.get("type")
        item = ev.get("item") if isinstance(ev.get("item"), dict) else {}
        itype = item.get("type")
        key = item.get("id") or itype
        if kind == "thread.started":
            obs.saw("thread started")
            obs.session(ev.get("thread_id"))
        elif kind == "turn.started":
            obs.saw("turn started")
            obs.turn_resumed()
            obs.awaiting_model()
        elif kind in ("item.started", "item_started"):
            obs.saw(f"{itype or 'item'} started")
            if itype in TOOL_ITEMS:
                obs.tool_started(key, str(item.get("name") or item.get("tool")
                                          or item.get("server") or itype),
                                 item.get("command") or item.get("query")
                                 or item.get("arguments"))
        elif kind in ("item.completed", "item_completed"):
            obs.saw(f"runtime error item: {item.get('message') or ''}"
                    if itype == "error" else f"{itype or 'item'} completed")
            if itype in TOOL_ITEMS:
                obs.tool_ended(key)
                if not obs.snapshot()["tools"]:
                    obs.awaiting_model()
            elif itype == "reasoning":
                obs.thinking_reported()
        elif kind == "turn.completed":
            obs.saw("turn completed")
            obs.runtime_terminal(True, "turn completed")
        elif kind == "turn.failed":
            obs.saw("turn failed")
            obs.runtime_terminal(False, (ev.get("error") or {}).get("message")
                                 or "turn failed")
        elif kind == "error":
            obs.saw(f"error: {ev.get('message') or ''}")
        else:
            obs.saw(str(kind or "event"))

    def _read_rollout(self, home: str, thread_id: str | None):
        """Actual model, actual effort and capacity -- from the session file.

        None of these three appear on the --json stream. This method exists
        because that turned out to be false, and hiding it behind 'observe the
        stream' would have made Foundation report UNKNOWN for facts the runtime
        plainly records.
        """
        unknown_m = Observed.unknown("no rollout file found for this thread")
        unknown_e = Observed.unknown("no rollout file found for this thread")
        if not thread_id:
            return unknown_m, unknown_e, None
        matches = glob.glob(
            os.path.join(home, "sessions", "**", f"*{thread_id}.jsonl"), recursive=True
        )
        if not matches:
            return unknown_m, unknown_e, None

        model = unknown_m
        effort = unknown_e
        capacity = None
        try:
            with open(matches[0], encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    payload = rec.get("payload") or {}
                    if rec.get("type") == "turn_context":
                        if payload.get("model"):
                            model = Observed(payload["model"], Provenance.PROVIDER_REPORTED)
                        if payload.get("effort"):
                            effort = Observed(payload["effort"], Provenance.PROVIDER_REPORTED)
                    if payload.get("type") == "token_count":
                        rl = payload.get("rate_limits")
                        if rl:
                            capacity = self._capacity_from_rate_limits(rl, payload)
                            capacity = replace(capacity, observed_at=
                                self._rate_limit_time(rec.get("timestamp"),
                                                      os.path.getmtime(matches[0])))
        except OSError:
            return unknown_m, unknown_e, None
        return model, effort, capacity

    @staticmethod
    def _rate_limit_time(timestamp, fallback: float) -> float:
        """Use the quota event's clock, not later writes to the rollout file."""
        try:
            dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                return dt.timestamp()
        except (ValueError, TypeError, OverflowError):
            pass
        return fallback

    def _capacity_from_rate_limits(self, rl: dict, payload: dict) -> CapacityReading:
        """Codex's own capacity shape, converted only in units.

        `used_percent` is 0..100; it becomes a 0..1 fraction and the provider's
        original object is preserved in `raw`. Window identity stays whatever
        Codex said it was -- there is no attempt to line it up with Claude's
        five_hour/seven_day naming, because they are not the same measurement.
        """
        windows = []
        for slot in ("primary", "secondary"):
            w = rl.get(slot)
            if not w:
                continue
            pct = w.get("used_percent")
            mins = w.get("window_minutes")
            windows.append(
                UsageWindow(
                    label=f"{slot}:{mins}min" if mins else slot,
                    used_fraction=(pct / 100.0) if (isinstance(pct, (int, float))
                        and not isinstance(pct, bool) and math.isfinite(pct)
                        and 0 <= pct <= 100) else None,
                    window_seconds=int(mins) * 60 if mins else None,
                    resets_at=w.get("resets_at"),
                    provenance=Provenance.PROVIDER_REPORTED,
                    raw=dict(w),
                )
            )
        info = payload.get("info") or {}
        return CapacityReading(
            runtime=self.kind,
            machine_id="",
            observed_at=time.time(),
            windows=tuple(windows),
            plan=Observed(rl.get("plan_type"), Provenance.PROVIDER_REPORTED)
            if rl.get("plan_type") else None,
            context_window=Observed(info.get("model_context_window"),
                                    Provenance.PROVIDER_REPORTED)
            if info.get("model_context_window") else None,
            tokens=Observed(info.get("total_token_usage"), Provenance.PROVIDER_REPORTED)
            if info.get("total_token_usage") else None,
            notes=("from token_count.rate_limits in the rollout session file; "
                   "account-level, and expressed in Codex's own units",),
        )

    #: What codex's own rollout scan reports back, so the numbers are read
    #: rather than guessed at.
    _SCAN = re.compile(
        r"Scanned (?P<n>\d+) rollout\(s\): (?P<eligible>\d+) eligible, "
        r"(?P<paginated>\d+) already paginated, (?P<skipped>\d+) skipped "
        r"\((?P<empty>\d+) empty, (?P<busy>\d+) busy\), (?P<failed>\d+) failed")

    @staticmethod
    def subagents_at_creation(rollout: str) -> str | None:
        """None if this thread was created WITHOUT codex sub-agents, else why
        it must not be resumed.

        MEASURED on codex 0.159.2 (independent review, fake provider): codex
        fixes a thread's sub-agent setting when the thread is created, and
        records it as `turn_context.multi_agent_version`. A thread created
        without the dispatch restrictions (`v1`/`v2`) and resumed WITH every
        withheld flag and the catalogue override still offered
        `multi_agent_v1.*` (local) or `collaboration.spawn_agent` (hosted),
        while web search and apps stayed withheld. Every thread production
        made before those restrictions is such a thread. So only a thread
        whose LAST recorded setting is "disabled" may continue; a missing or
        unreadable one is treated as not disabled.
        """
        seen = None
        try:
            with open(rollout, encoding="utf-8") as fh:
                for line in fh:
                    if '"turn_context"' not in line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("type") == "turn_context":
                        seen = (rec.get("payload") or {}).get(
                            "multi_agent_version")
        except OSError as exc:
            return (f"thread rollout could not be read ({exc}), so whether "
                    "it was created with codex sub-agents is unknown; a new "
                    "thread starts")
        if seen == "disabled":
            return None
        return (f"thread created with codex sub-agents (multi_agent_version="
                f"{seen!r}); restrictions do not remove them on resume, so a "
                "new thread starts")

    def resume_eligibility(self, *, session_ref, workspace=None,
                           runtime_home=None):
        """Ask CODEX whether it can still see that thread. Read-only, no model.

        STRONGER THAN A FILE EXISTING, AND IT IS THE PROVIDER ANSWERING.
        `codex migrate-rollouts --thread <id>` without `--apply` only
        reports: it scans this home's rollouts for that thread and says how
        many it found, how many it could not read, how many are empty and
        how many are busy. Measured: a real thread reports `Scanned 1
        rollout(s) ... 1 already paginated`, and a thread that does not
        exist reports `Scanned 0 rollout(s)`. No model runs and nothing is
        written.

        A GLOB STILL COMES FIRST, because it is free and answers the common
        case -- no rollout at all -- without starting a process.

        A thread whose home was never recorded is UNKNOWN, not ineligible:
        the session may exist somewhere this cannot look, and saying it is
        gone would claim more than is known.
        """
        from mentis.api.types import ResumeEligibility
        if not session_ref:
            return ResumeEligibility.no(
                "no thread reference, so there is no thread to continue")
        if not runtime_home:
            return ResumeEligibility.unknown(
                "the CODEX_HOME this thread was created in is not "
                "recorded, and its rollout is only findable there")
        found = glob.glob(os.path.join(runtime_home, "sessions", "**",
                                       f"*{session_ref}.jsonl"),
                          recursive=True)
        if not found:
            return ResumeEligibility.no(
                f"no rollout for that thread under {runtime_home}, which is "
                "the error codex itself gives for this case")
        # A THREAD THAT WAS GIVEN SUB-AGENTS KEEPS THEM. See
        # `subagents_at_creation`: no flag said on resume removes them, so
        # such a thread is not continued -- a new one starts, restricted.
        why = self.subagents_at_creation(found[0])
        if why:
            return ResumeEligibility.no(why)

        exe = self._which("codex")
        if not exe:
            return ResumeEligibility.unknown(
                "codex is not on PATH, so it cannot be asked")
        try:
            out = self._run([exe, "migrate-rollouts", "--thread", session_ref],
                            timeout=120,
                            env={"CODEX_HOME": runtime_home})
        except Exception as exc:  # noqa: BLE001
            return ResumeEligibility.unknown(
                f"codex could not be asked about that thread: {exc}")
        said = f"{out.stdout or ''}{out.stderr or ''}"
        m = self._SCAN.search(said)
        if not m:
            return ResumeEligibility.unknown(
                "codex did not report a rollout scan, so its own view of "
                "this thread is unknown")
        n = int(m.group("n"))
        if n == 0:
            return ResumeEligibility.no(
                "codex scanned its own rollouts and found none for this "
                "thread, whatever is on disk")
        if int(m.group("failed")):
            return ResumeEligibility.no(
                "codex could not read the rollout for this thread")
        if int(m.group("empty")):
            return ResumeEligibility.no(
                "codex reports the rollout for this thread is empty")
        if int(m.group("busy")):
            # UNKNOWN, NOT NO -- the wording of the old answer gave it away:
            # `right now`. Busy is a state that passes, and NO makes
            # Foundation start a brand-new thread beside a perfectly good
            # one, discarding continuity permanently over something
            # momentary. Found by review.
            return ResumeEligibility.unknown(
                "codex reports that thread busy, so whether it can be "
                "continued cannot be told from here right now")
        return ResumeEligibility.yes(
            f"codex scanned its own rollouts for this thread and read it "
            f"({n} rollout(s), none failed, empty or busy) in {runtime_home}")
    #: How a home provisioned by this adapter is recognised. Nothing
    #: outside this shape is ever removed, which is what keeps the
    #: user's own ~/.codex out of it entirely.
    HOME_PREFIX = "mk4-codex-home-"

    #: What a provisioned home could NOT be given, by home. Keyed by path
    #: rather than held as one value, because dispatches run concurrently
    #: and one adapter instance serves all of them.
    _home_gaps: dict[str, tuple[str, ...]] = {}

    def _windows_sandbox_mode(self) -> str | None:
        """Carry over the machine's own Windows sandbox mode. Never assert one.

        MEASURED FAILURE THIS EXISTS TO FIX. This used to write
        `sandbox = "unelevated"` outright, which was right when that was
        the only mode available and wrong the moment it was not. The owner
        set up the elevated sandbox and proved an ordinary `codex` CLI can
        write under it -- and a dispatched worker still failed with
        `unelevated restricted-token sandbox cannot enforce split writable
        root sets`, because this file was quietly overriding the mode they
        had just chosen. The provisioned home exists to exclude the
        machine's INSTRUCTIONS and MCP registry, not to countermand its
        sandbox decision.

        Read from the user's own config, exactly as `auth.json` is copied
        from it. Absent, nothing is written and codex applies its own
        default, which is a better answer than a guess.
        """
        path = os.path.join(self._codex_home(), "config.toml")
        mode = None
        try:
            with open(path, encoding="utf-8") as fh:
                section = False
                for line in fh:
                    bare = line.strip()
                    if bare.startswith("["):
                        section = bare == "[windows]"
                        continue
                    if section and bare.startswith("sandbox") and "=" in bare:
                        mode = bare.split("=", 1)[1].strip()
                        # A TRAILING COMMENT IS NOT PART OF THE VALUE.
                        # `sandbox = "elevated"  # note` was re-emitted whole
                        # into the provisioned config as malformed TOML.
                        if "#" in mode:
                            mode = mode.split("#", 1)[0].strip()
                        mode = mode.strip(chr(34) + chr(39))
                        break
        except OSError:
            mode = None
        return mode or None

    def _is_ours(self, home: str | None) -> bool:
        if not home:
            return False
        # THE NAME IS NOT PROVENANCE. Checking only the basename accepted a
        # matching directory ANYWHERE -- reproduced: a path such as
        # C:/unrelated/mk4-codex-home-user-owned reached the removal. Where
        # it lives has to match too, and homes are provisioned in one place.
        path = os.path.normpath(os.path.abspath(str(home)))
        if not os.path.basename(path).startswith(self.HOME_PREFIX):
            return False
        parent = os.path.normcase(os.path.dirname(path))
        return parent == os.path.normcase(
            os.path.normpath(tempfile.gettempdir()))

    def discard_session_home(self, runtime_home: str | None) -> str | None:
        """Remove a home this adapter made, once nobody will continue it.

        WHY THIS IS SAFE TO DO AND WHY IT WAITS. The home holds the thread
        rollout AND a copy of the runtime's auth.json, so leaving it is a
        credential sitting in %TEMP% and removing it destroys a resumable
        session. Neither is acceptable as a default, so it happens at
        exactly one moment: when Mentis has said it is relinquishing
        continuity for that session. Before that the session is kept
        because somebody may continue it; after it, nobody will.

        It refuses anything that is not one of ours. `~/.codex` is the
        user's own history and this must never be pointed at it.
        """
        if not self._is_ours(runtime_home):
            return ("left alone: not a home this adapter provisioned"
                    if runtime_home else None)
        if not os.path.isdir(runtime_home):
            return "already gone"
        try:
            shutil.rmtree(runtime_home)
        except OSError as exc:
            return f"could not be removed: {exc}"
        return f"removed, with the session it held and the auth copy in it"

    def abandoned_homes(self, keep: set[str]) -> list[str]:
        """Homes of ours that nothing refers to any more.

        NOT A TIMEOUT. A home is kept for as long as some instance record
        still names it, and swept when none does -- which is a fact about
        the record rather than a guess about age. Written as a query so a
        caller decides what to do with the answer.
        """
        parent = tempfile.gettempdir()
        out = []
        for path in glob.glob(os.path.join(parent, self.HOME_PREFIX + "*")):
            if os.path.isdir(path) and path not in keep:
                out.append(path)
        return sorted(out)

    def passive_capacity(self, machine_id: str) -> CapacityReading:
        """Free: `observe_capacity` reads rollout files and runs nothing."""
        return self.observe_capacity(machine_id)

    #: How far `observe_capacity` looks among provisioned homes: at most this
    #: many, newest first, stopping once this many have held rollouts.
    _CAPACITY_HOMES_SCANNED = 64
    _CAPACITY_HOMES_WITH_ROLLOUTS = 3

    def observe_capacity(self, machine_id: str) -> CapacityReading:
        """Read the most recent capacity the runtime already recorded.

        Capacity is written into a rollout file during any turn, so there is no
        need to spend an invocation asking for it. The reading is stamped with
        the record's own time, so staleness is visible rather than assumed --
        which is the whole reason `observed_at` exists.

        THE USER'S OWN HOME AND OURS, NEWEST FIRST. Reading only ~/.codex
        went silent the moment the owner stopped running codex by hand:
        measured, its newest reading's only window reset on 2026-10-03 while
        dispatched workers had written hundreds of newer rollouts into the
        homes this adapter provisions. Rate limits are the account's, not
        the home's, so a worker's reading is the same capacity. Only homes
        `_is_ours` accepts are read, and only the few newest files are
        opened, as before.

        BOUNDED BY HOME, NOT ONLY BY FILE. Globbing every provisioned home
        took /api/capacity from 14ms to ~440ms -- measured, 5707 homes on
        this machine. Homes are walked newest first by their own mtime and
        the walk stops once a few of them have yielded rollouts, or after a
        fixed number of homes: many recent homes hold none (measured, the
        newest rollout sat in the 15th-newest home), so "the newest N
        homes" alone would have missed it.
        """
        own = self._codex_home()
        ours = []
        try:
            with os.scandir(tempfile.gettempdir()) as it:
                for e in it:
                    if e.name.startswith(self.HOME_PREFIX) and e.is_dir():
                        try:
                            ours.append((e.stat().st_mtime, e.path))
                        except OSError:
                            continue
        except OSError:
            pass
        ours.sort(reverse=True)
        homes = [own] + [h for _m, h in ours[:self._CAPACITY_HOMES_SCANNED]
                         if self._is_ours(h)]
        candidates, seen, yielded = [], set(), 0
        for home in homes:
            key = os.path.normcase(os.path.normpath(os.path.abspath(home)))
            if key in seen:
                continue
            seen.add(key)
            pattern = os.path.join(home, "sessions", "**", "rollout-*.jsonl")
            found = False
            for path in glob.glob(pattern, recursive=True):
                try:
                    candidates.append((os.path.getmtime(path), path, home))
                    found = True
                except OSError:
                    continue
            if found and home != own:
                yielded += 1
                if yielded >= self._CAPACITY_HOMES_WITH_ROLLOUTS:
                    break
        candidates.sort(key=lambda c: c[0], reverse=True)
        files = [(path, home) for _m, path, home in candidates]
        readings = []
        for path, home in files[:5]:
            try:
                latest = None
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        if '"rate_limits"' not in line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        payload = rec.get("payload") or {}
                        if payload.get("type") == "token_count" and payload.get("rate_limits"):
                            latest = (payload, rec.get("timestamp"))
                if latest is None:
                    continue
                payload, _ts = latest
                c = self._capacity_from_rate_limits(payload["rate_limits"], payload)
                observed_at = self._rate_limit_time(_ts, os.path.getmtime(path))
                reading = CapacityReading(
                    runtime=c.runtime, machine_id=machine_id,
                    observed_at=observed_at,
                    windows=c.windows, plan=c.plan, tokens=c.tokens,
                    context_window=c.context_window,
                    notes=c.notes + ("read from an existing rollout file; no "
                                     "invocation was spent to obtain it",
                                     (f"from the user's own CODEX_HOME ({home})"
                                      if home == own else
                                      f"from a home Mentis provisioned for a "
                                      f"dispatched worker ({home}); rate limits "
                                      f"are the account's, so it is the same "
                                      f"capacity")),
                )
                readings.append((observed_at, os.path.getmtime(path), reading))
            except OSError:
                continue
        if readings:
            return max(readings, key=lambda r: r[:2])[2]
        return CapacityReading(
            runtime=self.kind, machine_id=machine_id, observed_at=time.time(),
            notes=("no rate_limits record found in any recent rollout file",),
        )
