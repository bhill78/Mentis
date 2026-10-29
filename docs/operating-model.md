# Operating model restoration — shared interfaces (2026-10-28)

This is the contract the parallel packages of the operating-model build agree on
before any of them is written. Each package builds to it; the integrator wires the
pieces together. Anything not named here stays as it is.

What already exists and is **not** rebuilt: the Persona, Discipline and Workflow
Kinds (`mentis/conversation/__init__.py` `_KINDS`), placement (`scoped-to`),
`compose` (`Conversations.compose`) and its delivery record, the ladder, Task
Gravity's server side (`mentis/operational/__init__.py`: `trunk_of`, `discovery`,
`follow_up_of`, `pursuit_permitted`, `ask_about_findings`, reconsideration),
`record_discovered_work`, `delegate(expectation=…)`, `/api/gravity`, the hand-started
bridge tools (`recall`, `work_overview`, `record_request`, `record_outcome`).

The gap this build closes: none of that reaches work started through the fast
CLI/MARS path, the baseline ships no Workflow or Discipline, and there is no
condensation, no shared caching and no MCP isolation.

## Boundaries (from AGENTS.md, restated because every package touches them)

- Mentis never runs agents, manages Git, runs tests or controls MARS.
- Every agent operation goes through `/api/worker` and `mentis.worker.permitted`.
- The record is append-only. New vocabulary is a new definition version; new
  material is a proposal unless the owner establishes it.
- Caches are derived and reconstructable; nothing durable lives only in a cache.
- A Persona, Workflow or Discipline grants nothing: no tools, permissions,
  isolation or authority. Naming a tool is not having it or being allowed it.

## 1. Vocabulary revision `operating-model-1` (package: workflow-discipline)

Applied as new definition versions through a rehearsable tool, like
`tools/ladder_vocabulary.py`: `tools/operating_vocabulary.py <brain> [--check]`,
idempotent, prints an owner-readable report. New Brains get the same definitions from
`_KINDS`.

- **Workflow** gains `evidence` (what supports completion), `interrupted` (what
  remains when the work stops part-way and how a later session continues it) and
  `projects` (list: repository names or paths it applies to; empty = any).
  Authoring `placeable` becomes `"reference"`: a Workflow may be placed at a
  Conversation or the whole Brain **only** with delivery `conditional` or
  `reference` (§3), so a child is handed a reference, never the whole procedure.
  A full delivery still happens only by naming it for a request (`governed`).
- **Discipline** gains `tools` (list: tool or interface names, e.g. `git`,
  `mars run_turn.py`, `mentis bridge`), `inputs`, `outputs`, `limits` (known
  limitations and dependencies). `requires` stays the runtime-capability list.

Rendered, a Discipline keeps four facts apart, in these words:
`Tools it uses (named, not granted; whether installed is the runtime's, whether
permitted is your grant's)`, `Requires (runtime capabilities)`, and nothing that
reads as authority.

## 2. Baseline version 2 (package: workflow-discipline)

`mentis/bootstrap/baseline.json` version 2 adds, as ordinary versioned items with
stable keys (later versions propose, never overwrite):

- one Workflow, key `software-change`: a software change carried through
  CLI/MARS/Git (orient + recall → record_request → delegate independent parts to
  workers on their own branches → integrate with git merge → targeted tests →
  commit + push → record_outcome with remaining → record_material for lessons).
  Activities name the Discipline below and the Personas Builder/Reviewer.
- one Discipline, key `cli-mars-development`: tools `git`, `MARS run_turn.py`,
  `mentis bridge (tools/mcp_bridge.py)`, `pytest`/`npm test` (targeted), with
  `requires` from the real Capability vocabulary.
- core operating material (the *contracts*, not the facts compiled from the running
  build): the rules already shipped plus the Task Gravity rule; nothing that repeats
  tool inventories.

## 3. Governance Condensation (package: condense)

`mentis/conversation/condense.py`, pure, no I/O beyond the corpus reads it is given.

```python
FULL, CONDITIONAL, REFERENCE = "full", "conditional", "reference"

@dataclass(frozen=True)
class Delivery:
    component: Component        # the composed component, unchanged
    level: str                  # FULL | CONDITIONAL | REFERENCE
    condition: str | None       # the applicability text used, verbatim
    why: str                    # why this level (stated, for the record)

def condense(corp, composition, *, known=(), question=None) -> tuple[Delivery, ...]
def render(deliveries) -> str          # what the run reads
```

Rules, in order (the first that decides wins):

1. Supersession and standing are resolved **before** this (compose already does);
   condense never sees a superseded or non-standing governing item.
2. Non-governing components (orientation, request, invocation strings, knowledge,
   experience) pass through as `FULL` and render exactly as `Composition` does.
3. The Persona being worn (`scope == "invocation:persona"`) is always `FULL`.
4. Material named for this work (`invocation:named`) or listed in `known` is `FULL`
   ("a condition known to apply").
5. The placement link's body may carry `"delivery": "full"|"conditional"|"reference"`
   and `"when": "<condition>"` (written by the owner at placement; absent on all
   existing links). Absent → `FULL` (today's behaviour). The condition is the link's
   `when`, else the entry's own applicability field (Discipline/Workflow `about`,
   "When it applies"). No condition, or one longer than 240 characters → `FULL`
   ("cannot be represented safely in shorthand").
6. `CONDITIONAL` becomes `FULL` when `question` meets the condition by the knowledge
   channel's deterministic term overlap (`mentis.conversation.knowledge`), i.e. the
   condition is known to apply to this work.
7. `REFERENCE` renders only in one closing index line (`Also standing, by
   reference: ent-… (title) …`).

Conditional rendering, exactly:
`[governs · <kind> · conditional] <title> — applies when: <condition>. Read it in full with resolve("<id>") before acting under it. (reference: <id>)`

The authoritative text is never rewritten, abbreviated or summarised. `resolve(id)`
of a superseded id answers with the standing successor (already true of named
material in compose; the bridge's `resolve` must say so too).

`Conversations.place(..., delivery=None, when=None)` gains those two optional
arguments (validated: level in the three values, `when` non-empty when conditional).

## 4. Shared context cache (package: cache)

`mentis/core/context_cache.py`.

```python
class ContextCache:
    def __init__(self, *, max_entries=512, max_bytes=64_000_000): ...
    def get(self, key, compute, *, deps: frozenset[str]):  # single-flight
    def stats(self) -> dict  # hits, misses, coalesced, evictions, invalidations,
                             # entries, bytes, by_kind{...}
    def clear(self) -> None

class Revisions:               # per corpus, in the server process
    def token(self, deps) -> tuple   # current revision of each dependency domain
    def note_write(self, entry_or_act) -> set[str]   # domains a write touches
```

- **Keys** are tuples beginning `(kind, corpus_id, revisions.token(deps), …)` then
  conversation, task digest, persona, access scope. The access scope is the grant's
  read scope (`"brain"` or `"conversation:<id>"`, plus the Participant where the
  result depends on who is asking). Two grants with different scopes never share an
  entry.
- **Dependency domains**: `governance` (rule/decision/persona/discipline/workflow
  entries, establishes, supersedes, proposes-to-supersede, scoped-to,
  carries-intake, challenges/withdrawals of governing material), `knowledge`
  (that-Kinds, adoption, challenges of findings), `conversation:<id>` (anything
  written in that Conversation), `work` (expectations, met/assigned/discovered/
  pursued/dismissed acts, decisions answered or withdrawn), `participants`.
  A write the classifier does not recognise bumps **every** domain (safe default).
- Coalescing: concurrent `get` for the same key wait on one computation.
- A value computed while one of its domains moved is returned, never kept
  (the rule `Conversations._recall` already follows).
- Bounded: LRU by entries and by approximate size; never unbounded.
- Exposed read-only at `GET /api/context-cache` (stats) for the verification.
- `MENTIS_CONTEXT_CACHE=0` disables it (the "uncached" comparison mode).

## 5. Prepared orientation (package: cache; wired by integrator)

`mentis/core/orientation.py`.

```python
def foundation(brain, conversation, *, scope) -> dict      # shared, cached
def for_agent(brain, foundation, *, participant, persona=None, work=None,
              workflow=None, follow_up=None, expectation=None) -> dict
```

The **foundation** (identical for every agent in the Conversation with the same
scope): conversation identity and purpose; participants and the Personas worn there;
outstanding work and open owner decisions (ids + titles); applicable Workflows and
Disciplines as condensed references; standing governance (ids, titles, delivery
level); recent-context pointers (last N Turn ids + first lines). Deps:
`governance`, `conversation:<id>`, `work`, `participants`.

The **agent part** (never shared across Personas, tasks or grants): the Persona in
full; the named Workflow in full; Disciplines condensed per §3 with `question=work`;
the Task Gravity in force (§6) with its generation; `recall(work)` tiers. Deps add
`knowledge`.

Both are reachable through the existing tools: `orient(conversation?)` returns the
foundation; `brief(conversation, persona?, work?, workflow?, expectation?,
follow_up?)` returns foundation + agent part. `recall` and `work_overview` are
served from the cache too.

## 6. Task Gravity on the CLI/MARS path (package: gravity)

Values are Mark IV's, unchanged: `"ask"` (absent), `{"depth": N}` (N ≥ 1),
`"unrestricted"`. Labels (Fluid composer, run details): "Asks before pursuing side
work" / "May pursue side work N generation(s) deep" / "May pursue side work freely".

- `record_request` accepts `follow_up`, `persona`, `workflow`, `runtime`
  (all optional) and stores them on the expectation's `detail` exactly as posting
  does (`detail.follow_up` absent for "ask"). A reply continuing earlier work keeps
  the permission it was asked with.
- A hand-started session that recorded a request carries it: it may call
  `record_discovered_work(under=<expectation>)` and `delegate(expectation=<finding>)`
  under it, checked by the same `pursuit_permitted` and generation walk
  (`discovery`) dispatch uses. Nothing new decides permission.
- `record_outcome` on a trunk with deferred findings leaves them deferred and
  reconsideration is offered by the existing `offer_reconsideration` when the trunk
  is complete.
- The setting travels to MARS workers **in their prompt and via `brief`**, never as a
  MARS option: MARS knows nothing of Mentis.
- Fluid: run details show Participant · Persona · runtime · Task Gravity; the
  trunk's findings (`/api/gravity?turn=`) appear in the run/turn inspector; the
  composer tooltip is Mark IV's full wording.

## 7. MCP isolation (package: mcp-isolation, MARS + bridge)

- **MARS** (`src/mars/backends/`): before starting an agent, read the backend's
  machine-wide MCP registrations (Codex `$CODEX_HOME/config.toml [mcp_servers.*]`;
  Claude `~/.claude.json` `mcpServers` and the project's; Antigravity
  `~/.gemini/config/mcp_config.json` / `antigravity-cli/mcp`; Kimi its own config).
  When a client-passed `mcpServers` name clashes, MARS **isolates** (a session-local
  config home containing everything except the clashing registrations; credentials
  linked/copied, deleted when the session ends) where the backend supports it, and
  otherwise **refuses** with error kind `mcp_conflict` naming the server and file.
  Machine-wide files are never modified. Reported in `_mars/backends` as
  `mcp_isolation: "isolate"|"refuse"`.
- **Bridge** (`tools/mcp_bridge.py`): `--brain <corpus_id>` (or env
  `MENTIS_BRIDGE_BRAIN`) makes the bridge refuse to start unless the server's
  `/api/server` reports that Brain. `orient` always reports `corpus_id` and the
  server URL, so each agent can state the Brain it is connected to.

## 8. Ownership

| Package | Runtime | Clone / branch |
|---|---|---|
| workflow-discipline (§1, §2, Persona on the bridge path) | Claude | `Mentis-wt/om-workflow` · `om-workflow` |
| fluid (§6 Fluid, Persona management check) | Claude | `Mentis-wt/om-fluid` · `om-fluid` |
| gravity (§6 server/bridge) | Codex | `Mentis-wt/om-gravity` · `om-gravity` |
| mcp-isolation (§7 MARS) | Codex | `MARS-wt/mcp-isolation` · `mcp-isolation` |
| cache + prepared orientation (§4, §5) | Antigravity | `Mentis-wt/om-cache` · `om-cache` |
| condense (§3) | Kimi K3 | `Mentis-wt/om-condense` · `om-condense` |
| bridge `--brain` (§7), integration, wiring, verification, rehearsal | Claude Code (coordinator) | `operating-model` |

Each package: targeted tests for what it changed, commit on its branch, report what
was done and what was not. No review loops, retries, WIP commits or workspace
services.
