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

## The files

| file | state it shows |
|---|---|
| `composer-normal.html` | the composer at rest with somebody marked for work: the four decisions readable at a glance |
| `composer-operations.html` | the Operations panel open on its index — the four decisions, each stating its own answer |
| `composer-ops-who.html` | Who does it: Persona, runtime, model, effort, instance — with the picking-relevant capacity reading only |
| `composer-ops-responsibility.html` | What responsibility they take: carry, or carry and coordinate |
| `composer-ops-independence.html` | How independently: Permission Mode and side work (Task Gravity), stated as two separate choices |
| `composer-ops-where.html` | Where it runs: Execution Mode, with the Unrestricted Host notice and Accept / Cancel |
| `capacity-default.html` | Activity › Capacity, default: availability, allowances, resets, freshness. No prose |
| `capacity-expanded.html` | one runtime's details in ordinary language; diagnostics present and closed |
| `capacity-diagnostics.html` | the same, with technical diagnostics opened |

`shots/` holds the rendered PNGs; `shoot.sh` makes them.

## Rendering the screenshots

```sh
cd apps/fluid-web
python -m http.server 8911 --bind 127.0.0.1 &
bash mockups/quiet-mk2/shoot.sh      # Windows Chrome, headless, 1× device pixels
```

## What the sample data is

Representative, and shaped exactly like the contracts
(`src/composer/execution.ts`): `RuntimeCapacity.windows` with `used_fraction`
and `resets_at`, `observed_at`, `plan`, `model_groups`, `local`; and
`RuntimeChoice.present` / `execution_modes` with the four states
`supported | unsupported | temporarily-unavailable | unverified`.

Two strings in the mockup are the product's own, copied rather than invented:

- the Unrestricted Host notice — `mentis/execution/mode.py` `NOTICE`
  (`id: unrestricted-host/v1`), shown verbatim;
- Container's "not available yet" — `fluid/composer/execmode.ts` `CONTAINER_WHY`.

The per-mode `permission_enforcement` sentence comes from MARS's contract, not
from this repository, so the diagnostics block shows a representative one
(`forwarded-to-client`).

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
