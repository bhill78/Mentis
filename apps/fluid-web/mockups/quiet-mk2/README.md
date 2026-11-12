# Quiet Chat Mark 2 — composer and Capacity redesign: MOCKUP ONLY

Static HTML/CSS. **Nothing here is imported by the app and no production
component is touched.** It exists so the owner can approve an interaction design
before any of it is implemented (ent-14616fb08d56 §6, ent-7bfbf3904ca4).

It reuses the real design tokens (`../../src/theme.css`) and the real pixel sizes
measured from the live CSS, so a screenshot of it is the size the surface
actually renders at.

## The real dimensions, and where they come from

| surface | size | measured from |
|---|---|---|
| reading column | 728px wide (680px content) | `quiet2/quiet2.css:6,77` — `--q2-measure: 680px`, `.q2-col { max-width: calc(var(--q2-measure) + 48px); padding: 48px 24px 0 }` |
| composer dock | 700px border-box | `quiet2/quiet2.css:229` — `.q2-dock { margin: 16px -10px 0; padding: 8px 10px }` |
| the composer | **680px** | `.q2-dock .fx-composer { margin: 0 }` (`quiet2/quiet2.css:235`) over `.fx-composer { padding: 9px 11px; border: 1px }` (`fluid/conversation/conversation.css:185`) |
| composer panel ("Operations") | **380 × ≤448** | `fluid/Composer.tsx:838` `<Float … width={380}>`; `.fx-float { max-height: min(60vh, 28rem) }` (`conversation.css:393`) |
| Activity popup | **360 × 520** | `quiet2/dock.css:54-58` — `.q2-gdock-panel { width: min(360px, …); max-height: min(520px, …) }` |

Every mockup panel is drawn inside those caps and, except where a shot says so,
needs no scrolling.

## Round 3 — what this revision is

Round 2 was rejected (`ent-52fe7e96bc11`). It stacked pills in wrapping rows, hid
runtime / model / effort / instance behind a second screen so the settings could
not be seen at once, used a three-model happy path, and added more lines above an
already cluttered writing area. None of that survives.

**Operations is one settings list.** One 380 × 374 panel, every setting on it,
nothing scrolls, no pills anywhere. Each setting is one single-line row: label,
current value, chevron. **Every row opens the same kind of pull-out** beside the
list — a vertical list of that setting's options, the current one check-marked,
one click to choose, which closes the pull-out and updates the row. The settings
list stays visible the whole time. The only second step anywhere is the
Unrestricted Host notice.

**The composer at rest has one line above the writing area**, not four: the
destination, the addressee chips, and a single quiet summary that is itself the
way into Operations.

## The files

| file | state it shows |
|---|---|
| `composer-normal.html` | at rest, defaults — one line above the writing area |
| `composer-normal-changed.html` | at rest with Permission Mode and Execution Mode off their defaults, flagged in the summary |
| `composer-operations.html` | the settings list open: ten rows, every value visible, no scrolling |
| `composer-ops-model.html` | the Model pull-out on claude: its default, then 14 models grouped by family, filter box empty |
| `composer-ops-model-filter.html` | the same with `son` typed — 5 of 14, and nothing ticked, because the model in force is not among them |
| `composer-ops-model-codex.html` | the Model pull-out on codex: a different catalogue of 14 |
| `composer-ops-runtime.html` | the Runtime pull-out: five runtimes and what each has left, one with none |
| `composer-ops-permission.html` | the Permission Mode pull-out, with the two further rows a non-default mode adds to the list (twelve rows, still no scrolling) |
| `composer-ops-execution-confirm.html` | Unrestricted Host: the server's notice verbatim, Accept / Cancel, inside the pull-out |
| `capacity-default.html` | Activity › Capacity, default: availability, allowances, resets, freshness. No prose |
| `capacity-expanded.html` | one runtime's details in ordinary language; diagnostics present and closed |
| `capacity-diagnostics.html` | the same, with technical diagnostics opened |

`shots/` holds the rendered PNGs; `shoot.sh` makes them. The three Capacity
mockups and their PNGs are unchanged from the approved round-2 revision
(`6357352`) and re-render byte-for-byte identically.

## The settings list: every setting, and where each one comes from

Read off the deployed composer — `fluid/composer/Settings.tsx`, with the option
sets in `runs/consent.ts`, `runs/gravity.ts`, `composer/execmode.ts`,
`composer/designation.ts` and `composer/execution.ts`.

| row | the deployed control | its options |
|---|---|---|
| Sending this | `Settings.tsx:111` the dispatch toggle | *Sending this starts work* / *Sending this only addresses them* |
| As | `Row label="persona"` | *as X (designated)* or *as themselves* (`unsetPersonaWords`), *as themselves* (`NO_PERSONA`), then each Persona by name (`personaOptions`) |
| Runtime | `Row label="runtime"` | *let Mentis decide* (or *their default (X)*), then every present runtime (`runnable`) |
| Model | `Row label="model"` | *the runtime's default*, then the runtime's catalogue |
| Effort | `Row label="effort"` | *the model's default*, then the runtime's effort vocabulary |
| Instance | `Settings.tsx:150` toggle | *Reuse the instance already running, if there is one* / *A fresh instance, with no history* |
| Authority | `Settings.tsx:154` toggle | *Does this work only* / *May coordinate this work* |
| Permission Mode | `CONSENT_MODES` | *Ask for permission* / *Allow routine operations* / *Never wait for me (refuses what would be asked)* / *Allow all operations* |
| Within | `fc-srow label="within"`, present only when Permission Mode is not *Ask for permission* | the task's workspaces, absolute directories |
| Also | `fc-srow label="also"`, present only under *Allow routine operations* | `OPTIONAL` — delete, git-remote, network, install |
| Side work | `gravityWords` | *Asks before pursuing side work* / *…1 generation deep* / *…2 generations deep* / *May pursue side work freely* |
| Execution Mode | `EXECUTION_WORDS` | *Sandboxed* / *Unrestricted Host* / *Container* (never offered: `CONTAINER_WHY`) |

Nothing was invented and nothing was dropped. Two settings the brief did not
list are here because the deployed composer has them: **Sending this** (whether
sending starts work at all — the deployed panel's first control, and the one
with a cost) and the pair **Within / Also**, which the deployed composer shows
only when Permission Mode is not *Ask for permission*. They behave the same way
here: they appear under Permission Mode when it changes, which is the twelve-row
case the list is sized for.

### Where the wording is the product's, and where it is shortened

Every **option name** in a pull-out is the deployed composer's own, verbatim,
with two exceptions, both of which split one product sentence between the name
and its dim note rather than rewording it:

- *Reuse the instance already running, if there is one* → name
  *Reuse the instance already running*;
- *Never wait for me (refuses what would be asked)* → name *Never wait for me*,
  note *refuses what would be asked*.

Every **row value** is the option's name, shortened only where that name is a
full sentence (Instance's *Reuse the one running*). A model id too long for the
row is ellipsised there and read whole in the pull-out.

The short dim notes beside an option — *the default*, *nothing is asked*,
*this request only*, *explicitly no Persona* — are condensed from `CONSENT_TIP`,
`APPROVE_ALL_RISK`, the coordinate button's title and `personaOptions`' notes.
They are the one place this mockup writes its own words, and they say nothing
the product does not.

Two strings are copied, not written:

- the Unrestricted Host notice — `mentis/execution/mode.py` `NOTICE`
  (`id: unrestricted-host/v1`), shown verbatim;
- Container's *not available yet* — `fluid/composer/execmode.ts` `CONTAINER_WHY`.

## The pull-out, and its measured geometry

One shape for every setting. 310px wide, drawn to the **left** of the settings
list:

- the panel is `Float width={380} align="end"`, so its right edge sits 10px
  inside the dock's right edge — page-x 704 in the 728px column — and its left
  edge is at page-x **324**;
- the pull-out's right edge is 10px inside that, at page-x **334**, and its left
  edge therefore lands at page-x **24** — exactly the reading column's 24px
  padding edge. It fits the column with nothing to spare and never leaves it;
- the 10px overlap falls on the panel's own 11px left padding, so it covers no
  label, no value and no chevron. The open row stays highlighted (accent wash and
  a 2px accent bar at its left) so it is clear which row the pull-out belongs to;
- vertically it opens at its row's own top, shifted up only as far as it must to
  keep its bottom inside the list's bottom edge. In the Model and Execution Mode
  shots that shift is most of the list's height; the highlighted row is what
  connects them.

Short option sets (As, Effort, Instance, Authority, Permission Mode, Side work,
Execution Mode, Sending this) are a plain list, 30px a row, no filter box.

Long option sets — Model always, Runtime past about seven — get a filter box
(*Filter models…*, with the count at its right) over a list capped at 276px that
scrolls. The cap deliberately cuts a row in half, so it is visible that there is
more below. The Model pull-out is therefore 26 + 39 + 276 = **341px** tall.

## The arithmetic of "the list never scrolls"

Header 30 + footer 22 + two 1px group rules = 54. Rows are **32px**, not the
roomier 36: the worst case is twelve rows (Permission Mode off its default adds
*Within* and *Also*), 12 × 32 + 54 = **438**, which is under Float's real 448px
cap. The ordinary ten-row list is 374.

## The composer's one line, and what had to stay on it

At rest the line is: the destination (`Replying to #17`, with its × to post on
its own instead), the addressee and topic chips, and the summary, right-aligned.
Removed from round 2: the separate identity line, the separate configuration
line and the separate Operations button. **Alt+O still opens the panel**; the
shortcut is in the summary's `title` and `aria-label`, not in a visible button.

The summary reads `Reviewer · claude · opus-5-5 ›` and is itself the control.
Authority, Permission Mode and Execution Mode join it **only when they differ
from their defaults**, in the product's own few words (`modesWords`,
`permissionShort`, `EXECUTION_SHORT` — "allow all · host", "routine") and in the
attention colour.

Things that had to stay, and why:

- **the destination** (`Replying to #17`). It is the only statement of where the
  post goes, and in the deployed composer it also carries the × that cancels the
  reply; there is nowhere else for either. It is first on the line and is the
  part that ellipsises if the line is ever tight.
- **the topic chip** (`under #Quiet Chat`). It is a removable attachment of the
  draft, not a readout.

Things that did not stay:

- the deployed header's `, to @Quill`, which repeats the chip now beside it;
- the enforcement line (`enforcementNote` — the server's sentence about how
  Permission is enforced outside a sandbox), which was its own paragraph under
  the chips. It belongs to Execution Mode and is shown in the Execution Mode
  pull-out, where the deployed panel also shows it.

Nothing else moved: the toolbar row and the split send button are unchanged.
The conditional rows the deployed composer adds above the writing area for other
reasons — attachments, draft references, *With your first post: …* — are not in
these shots and are not changed by this design.

At the widest case shown (`composer-normal-changed`: a reply, an addressee, a
topic and two non-default modes) the line measures inside the 656px of composer
content with nothing clipped. One shortening makes that fit: **the summary names
the model without repeating the runtime it has just named** — `claude ·
opus-5-5`, which is the owner's own shorthand. A slug that does not begin with
its runtime's name (codex's `gpt-6.1-terra`) is left whole. The full slug is in
the settings list's Model row, where it is chosen.

## Where the sample data comes from

**There is no real model catalogue in this repository, and the owner's objection
that the round-2 sample was a happy path is exactly right.** `/api/execution`
builds its model lists at request time from MARS, which is a separate project
(`mentis/web/__init__.py:3442-3500` → `mentis/core/service.py:388-415`
`models_list`, a pass-through of MARS's `_mars/backends`). Every model slug that
exists in this repository is a test fixture of two to five entries:

- `tests/test_model_effort_routing.py:25-72` — claude `haiku, sonnet, opus,
  opus-alias, default`, efforts `low, medium, high, xhigh, max, ultra`; codex
  `mini, code, max`; antigravity `claude-sonnet-5-5-low, gemini-4-argon-low,
  gpt-oss-120b`;
- `tests/test_models_capacity.py:8-16` — claude `default, opus, sonnet` with
  `modelNames` *Opus 5.5* / *Sonnet 5.5*;
- `tests/conformance_runtime/profiles.py:52-100` — codex `gpt-6-luna,
  gpt-6.1-terra`; claude `default, sonnet, opus`; `kimi-k3` with none;
- `apps/fluid-web/tests/quiet_activity_unit.mjs:113-115` — one wire-shaped row,
  `{slug: 'claude-sonnet-5', name: 'Sonnet 5', aliases: ['sonnet']}`;
- measured live: `docs/rust/evidence/j16-probe.json` `claude-haiku-5-5`;
  `docs/modernization/RUNTIME-PARITY.md` codex `gpt-6-luna`, antigravity
  `gemini-3.8-flash-medium`, local `qwen3.5:9b` via Ollama.

So the fourteen claude and fourteen codex ids in these shots are **built from
those real families and extended to a realistic size** — the slug shapes,
the dated and `-mini` / `-fast` / `-1m` variants and the aliases follow what the
fixtures and the live probes show, and the rows are the shape `models_list`
emits. They are representative, not a catalogue read from a server. Two details
of that shape are reflected honestly: `efforts` is per-runtime rather than
per-model, and `default_effort` is never set by this server, so no effort option
is marked "default" and the unset choice is *the model's default*.

The runtime pull-out's dim note is each runtime's **capacity**, not
`RuntimeChoice.version` which the deployed Row uses — the owner asked for the
one picking-relevant reading. `kimi-k3` is shown present with none left; the
deployed Row offers every present runtime, so exhausted capacity is a reading
shown beside it and not a refusal, and the row is dimmed rather than disabled.

`claude`'s Execution Mode default is shown as *Sandboxed*. The conformance
profile (`tests/conformance_runtime/profiles.py:122-161`) declares
`unrestricted-host` as claude's default and `sandboxed` as codex's; the
sandboxed-default case is the one worth drawing, because it is the one where
Unrestricted Host is a deliberate choice that must pass the notice.

The rest of the sample data is shaped exactly like the contracts
(`src/composer/execution.ts`): `RuntimeCapacity.windows` with `used_fraction`
and `resets_at`, `observed_at`, `plan`, `model_groups`, `local`; and
`RuntimeChoice.present` / `execution_modes` with the four states
`supported | unsupported | temporarily-unavailable | unverified`.

The per-mode `permission_enforcement` sentence comes from MARS's contract, not
from this repository, so the diagnostics block shows a representative one
(`forwarded-to-client`).

## Rendering the screenshots

```sh
cd apps/fluid-web
python -m http.server 8911 --bind 127.0.0.1 &
bash mockups/quiet-mk2/shoot.sh      # Windows Chrome, headless, 1× device pixels
```

## One derived presentation, stated plainly

The one-word availability on each Capacity row — *Available / Not available now /
Not installed* — is a **reading of what the server already reports**, not a new
concept:

- `present: false` → "Not installed"
- any Execution Mode in state `temporarily-unavailable` → "Not available now",
  with the server's `why`
- otherwise → "Available"

The four mode states stay distinguishable in the expansion
(*Available / Not verified / Not available*), which is where the owner's own
examples live.
