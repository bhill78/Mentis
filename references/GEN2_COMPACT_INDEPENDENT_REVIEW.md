# Corrected Generation 2 — independent review and Gen 3 parent recommendation

**Reviewer**: Independent Reviewer, runtime `claude / claude-opus-5`
**Reviewing**: the corrected Gen 2 compact-Magnet return by `@Builder-P5` (`codex`), Turn
`ent-fb373f0ab3c3`, request `opr-8df94334b1ab`
**Against**: the owner clarification `ent-93f00e5ef142` and its two reference images, the
experiment requirements `ent-8bcfb7953748`, the canonical `T1`–`T8` scenario, the Gen 1
selection `ent-4a1ae936a75d`, and the compact assessment `adm-a1dfa1b8252b` (`E1`–`E11`)
**Date**: 2026-11-21 · this review owns `magnet-gen2-independent-review/`

---

## 0. Verdict

**The declared property holds.** All three corrected candidates render the owner's three
interaction levels from their own controls, at 1440×900 and 390×844: a compact resting
object at **0.71 % / 0.76 %** of the viewport with the Conversation keeping **74.6 % / 73.7 %**
of the first screen; an intermediate card on hover, keyboard focus and touch tap; and a deep
surface that is absent at cold load, reachable in one action and dismissed in one. The
originating draft survives every round trip byte-exact, the composer destination resets to
Origin #14, all fourteen evidence items and all five provenance hazards are reachable at both
widths, and lineage runs only through the selected parents C4/C5/C6 with the compact object
sourced to the owner's clarification, not to rejected C2 or C3.

**No finding is blocking.** Seven findings are recorded, all non-blocking: nothing loses data,
breaks navigation, prevents use, or omits something the correction's request required.

**Recommended parents for Gen 3: `G2A-c` and `G2B-c`. `G2C-c` is not recommended**, with two
of its patterns harvested. The reason is given in §6 and it is **not** the ranking the author
predicted.

---

## 1. How independent this review is

**Independent.** I re-extracted the held ZIP (`adm-52c810a4f8b5`, digest
`b835f6be…5dddc6`, confirmed on download) into my own directory and rendered only those bytes.
I confirmed by digest, from Mentis rather than from the author's report, that the three
candidate files in the package are byte-identical to the separately returned artifacts:

| candidate | package digest | Mentis artifact | match |
|---|---|---|---|
| G2A-c | `9bee386174596de0…` | `adm-b6ed9a6294df` | yes |
| G2B-c | `9bb67c090868c62f…` | `adm-056b159ba696` | yes |
| G2C-c | `2a6ffc37d9fd789d…` | `adm-38b81a63edcd` | yes |

Every number below is from probes I wrote (`probes/`), driven by **each candidate's own
controls** — the resting button, hover, `Tab`/`Enter`/`Escape`, the card's actions, the deep
surface's own return. I deliberately did **not** use the review ribbon's `L1 / L2 / L3`
buttons, because those are review tooling and would have demonstrated the author's states
rather than the candidate's. I did not run `measure_gen2_correction.py`,
`audit_correction_contract.py` or `smoke_windows_chrome.py`. I re-measured every load-bearing
figure in a **second engine** — installed Windows Chrome 157.0.8103.39 as well as bundled
Chromium 149.0.7827.55 — and the numbers were identical in both.

**Not independent, and said plainly.**

- **I read the author's evaluation before measuring.** My probes were therefore shaped by the
  claims they make. I mitigated this by re-deriving their figures rather than adopting them,
  and by measuring four things they did not: a Magnet-removed differencing test for reflow,
  pointer-events hit-testing of the floating layer, a normalised cross-candidate diff of the
  compact layer, and first-screen evidence density of each deep surface. Three of those four
  produced findings.
- **Shared machine and workspace root** with the author, though not shared files: I rendered
  from my own extraction, and the author's directories are untouched (`magnet-ui-gen2`
  last written 10:55, before this review began).
- **Different runtime from the author** (`claude` vs `codex`), which is the respect in which
  this review is structurally independent.
- **`E1`–`E11` are another reviewer's criteria**, not the owner's words. I used them as a
  yardstick because the correction was briefed against them, but I judged against
  `ent-93f00e5ef142` itself, and I say where the two differ.
- **Expert walkthrough and geometry, not user evidence.** No person used any candidate. Words
  like "unobtrusive" and "compact" are my judgement against the owner's wording; percentages
  and pixel counts are measurements.

---

## 2. What the owner actually asked for, and where it came from

The compact requirement is **owner-sourced**, and this matters for lineage. In
`ent-93f00e5ef142` the owner said the mockups were "drifting toward treating Magnets as their
own large sub-workspaces", that this "is not my preferred primary interaction", and named
three levels to preserve:

1. **Resting** — "a small, movable Magnet object that can be dragged and dropped anywhere in
   the working area", with "useful status indicators".
2. **Hover/focus** — "a compact information card showing what it has collected, such as posts,
   files, changes, summaries, and potentially Perspectives".
3. **Explicit open** — "a larger inspector or working surface … acceptable when explicitly
   opened", but "should not be the default representation".

I read both attached images as images. `adm-dbd6c1a4a636` — the "older compact yellow Magnet"
the owner names — is a small amber disc with a count badge beside a dark card carrying a title,
"50 new since you last opened it", a provenance line, a plain statement that no synthesis
exists, and two labelled collections (**Posts 235 · All**, **Files 321 · All**) with item
previews. `adm-7277383b759d` shows two small ringed cores with orbiting item chips and status
captions, plus a detached SUMMARY panel with a changed-inputs warning.

**This lineage is lawful.** The compact object does not come from rejected C3's margin column
or rejected C2's hub: each corrected file cites `ent-93f00e5ef142` twice in its own header
comment, names both reference images by `adm-` id, and contains **zero** `c2-` or `c3-` class
prefixes, no `margin-col`, no dossier structure and no dual composer. The declared ancestry in
each ribbon uses only selected parents — G2A-c `C6 × C4 × C5`, G2B-c `C4 × C6 × C5`,
G2C-c `C5 × C4 × C6`.

---

## 3. The three levels, measured

### Level 1 — resting

| | G2A-c | G2B-c | G2C-c |
|---|---|---|---|
| Resting button | 60×60 desktop · 50×50 narrow | same | same |
| Whole resting footprint (button + caption) | **0.71 %** desktop · **0.76 %** narrow | same | same |
| Deep surface visible at cold load | **no** | no | no |
| Conversation share of first screen | **74.57 %** desktop · **73.73 %** narrow | same | same |
| Originating article width | 680 px · 366 px | same | same |
| Article reflow caused by the Magnet | **0 px** | 0 px | 0 px |
| Floating layer blocks the Conversation | **no** — `pointer-events: none`, 0/20 probe points intercepted | no | no |
| Status facts on the object | 4 of 4 — count `14`, `+2` new, `!` restricted, `3P` Perspectives | same | same |

For scale, the same measurement on the frozen baselines at desktop, rendered here: **C4 gives
its desk 65.56 %** of the first screen and **C1 its inspector 28.82 %** — figures that
reproduce `adm-a1dfa1b8252b` §3.3 exactly (65.6 %, 28.8 %) from an independent render. **None**
of the three original Gen 2 designs, and none of C1/C4/C5/C6, contains a resting object or a
card at all.

The reflow and pointer-events results are mine; neither had been tested. They matter because a
floating layer spanning 74 % of the viewport would be a blocking defect if it swallowed clicks.
It does not.

### Level 2 — the card

| | desktop | narrow |
|---|---|---|
| Opens on hover | yes, within 50 ms | no — opens on **tap** (correct for touch) |
| Opens on keyboard focus alone | **yes** | yes |
| Reachable by `Tab` | stop 10 overall, of which 7 are the review ribbon → **3rd product stop** | stop 8, 5 ribbon → 3rd product stop |
| Visible focus ring | `outline: solid 2px` + 3 px amber ring | same |
| `Enter` opens, `Escape` dismisses, focus returns to the object | yes / yes / **yes** | yes / yes / yes |
| Tab stops inside the card | 10 | 9, then exits to the composer (not a focus trap; `aria-modal="false"`) |
| Card size | **348×560 = 15.04 %** of viewport | **374×560 = 63.63 %** of viewport |
| Overlaps the composer | **0 px** | 0 px |
| Overlaps the article | 16.2 % of it | ~100 % of it |
| Content | 3 kinds, each with a count: Posts & Changes (8 of 14), Files & Traces (6 of 14), Perspectives & Syntheses (3); 3 item previews per evidence kind; 3 Perspective chips; staleness box; 4 actions | same |

The card carries, inside the artifact itself, the sentence *"These keyboard/touch-accessible
presets illustrate positions; no real drag physics, arbitrary-coordinate drag, or saved
coordinates are implemented."* That is `E9`'s honesty requirement met **in the mockup**, not
merely in the report, and it is the right way to handle the boundary.

### Level 3 — explicit open, and back

Hidden at cold load in all three; one action from the card to open; one action back. Return
controls are visible in the first screen at both widths. After open → Magnet Chat → return:
the composer destination switches to `Magnet Chat (P1)` and **resets to `Origin #14 (Draft
saved)`**, Post #14 is available again, and the protected draft is preserved **character for
character** — `Before we freeze v4.2, @maya can you confirm whether the Redis warmup patch
also covers the cold-start spike seen in SRC-04?` — in all three candidates at both widths.

### `T1`–`T8`

Walking every panel each candidate's own controls can reach, at both widths, all three
candidates make reachable: the full 14-item ledger, the 200-entry cap disclosure, the
unchanged configuration digest `sha256:9f4b8e21…c218` across `P1 → P2 → P3 → + New`, the
personal-vs-shared filter distinction, `Q1 → Q1.1`, retired `Q3` with its reason, `S1 → S2 →
S3`, the *Interpretation / not established Brain knowledge* labelling, all five audit hazards
(edited `SRC-01`, deleted `SRC-07`, de-duplicated `SRC-02`, mutual dependency `P1·S3 ↔ P2·S1`,
restricted `SRC-09`), the continuation pre-run facts (`SRC-13`/`SRC-14`, `@Atlas · codex`
distinct from `S3` author `@Louie · claude`, destination, estimate, artifact-until-Keep
authority), and Magnet Conversation `ent-conv-mag-8841` posts #6–#9 with human-versus-agent
runtime attribution. Zero horizontal overflow and zero page or console errors throughout.

### `E1`–`E11`

| | criterion | G2A-c | G2B-c | G2C-c |
|---|---|---|---|---|
| E1 | resting footprint ≤2 % / ≤4 % | **pass** 0.71 / 0.76 | pass | pass |
| E2 | ≥3 of 4 status facts at rest | **pass** 4 of 4 | pass | pass |
| E3 | Conversation undisturbed | **pass** 0 px reflow, click-through | pass | pass |
| E4 | card on pointer, ≤25 % of viewport | pass desktop 15.04 % · **fail narrow 63.63 %** | same | same |
| E5 | card on keyboard, parity, `Esc` returns focus | **pass** | pass | pass |
| E6 | card names kinds with counts and ≥2 previews each | **pass** 3 kinds, 3 previews | pass | pass |
| E7 | explicit open only, 1 action each way | **pass** | pass | pass |
| E8 | round-trip fidelity | **pass** | pass | pass |
| E9 | ≥3 placements, survives open/close, drag declared | **pass** 4 desktop / 3 narrow | pass | pass |
| E10 | width parity or stated deviation | pass, deviation stated (tap for hover; card density) | pass | pass |
| E11 | lineage honesty | **pass** | pass | pass |

**Ten of eleven pass; `E4` fails at 390 px only, and the author disclosed it.**

---

## 4. Challenging the author's measurements

**Where they are right.** Every figure I could re-derive reproduced exactly: resting button
60×60 / 50×50, footprint 0.71 % / 0.76 %, origin width 680 / 366, deep surface closed at load,
card 348×560 at (950,152) desktop and 374×560 at (8,134) narrow, four placement slots all in
viewport, focus-reveals / `Esc`-dismisses / `Esc`-returns-focus / `Tab`-enters all true. 127 of
127 locatable delivery-manifest digests match the extracted bytes; the eight frozen-original
digests match the files I rendered. The measurements are reproducible and honest, and the
report's own limitations section is unusually candid.

**Four places where the account overstates or under-reports.**

**C-1 — the compact layer is one shared component, so two of the three candidates are not
differentiated at the owner's default levels.** I extracted the rendered float layer from each
candidate, neutralised only the per-candidate id prefix, and diffed them. Between **G2A-c and
G2B-c the entire difference** is: the default slot (`mid-right` vs `top-right`), one subtitle
phrase ("Opens as Origin-Anchored Workbench" vs "Opens as Full-Height Split Desk"), the primary
button label, and the puck caption wording. The card's sections, counts, previews, staleness
box, chips and actions are identical markup in identical order; rendered card text similarity
is **0.981**. The evaluation nevertheless describes G2A-c as having a "grouped Posts/Files
quick card" and G2B-c an "evidence-first quick card". **There is no rendered difference
answering to that description.** Only G2C-c genuinely differs at these levels: it moves the
Perspectives section first (similarity 0.817) and applies a `variant-orbital` dashed ring to
the resting object.

**C-2 — the predicted ranking is not supported by measurement.** The evaluation predicts
"G2B-c gains most in default continuity … a plausible primary candidate", reasoning that
G2B-c's one disadvantage — hiding the Conversation on arrival — is now gone. That reasoning is
sound as far as it goes, but it was never checked against what G2A-c's advantage now costs. I
measured the first screen of each deep surface, opened and unscrolled:

| deep surface, first screen | G2A-c | G2B-c | G2C-c |
|---|---|---|---|
| evidence items present | **5** (4 fully visible) | 4 (3 fully) | 1 (0 fully) |
| provenance/standing chips of 9 | **8** | 8 | 5 |
| originating Conversation still visible | **23.89 %** | 0 % | 0 % |
| height given to tab strips | 71 px | 71 px | 102 px |

G2A-c is **at least as dense as G2B-c on every measured axis and keeps a quarter of the screen
as the Conversation**. The predicted primary is not the stronger candidate on this evidence.

**C-3 — `invalid_tablist_count: 0` under-reports a real defect.** G2C-c's "Focus Stack Layers"
tablist contains a `role="tab"` — *"1. Origin #14 (Resting Magnet)"* — with **no
`aria-controls` at all**. The author's own measurement file records `tab_count: 10` against
`tabpanel_count: 9` for G2C-c at both widths, so their data contains the discrepancy their
predicate did not test. G2A-c and G2B-c have no such tab.

**C-4 — `undersized_controls_lt24: []` misses a collapsed control.** In **G2B-c at 390×844**
the in-surface *"Close to Resting Magnet"* button renders **0×0** (`display:flex`,
`visibility:visible`, `opacity:1` — collapsed, not deliberately hidden) and cannot take focus.
It measures 155×30 at desktop. The author's filter evidently excludes zero-size elements, so a
control that disappeared was counted as compliant. Navigation is unaffected: the primary
`← Return to Origin #14` renders 146×30 and works.

**Static simulation versus user evidence.** Nothing here is user evidence, and the author says
so. Three further distinctions the carrier should hold: the action counts are *demonstrated
transitions*, not task times; the "compact" and "unobtrusive" judgements are geometry plus my
reading of the owner's words; and both engines tested are Blink, so "cross-browser" means
Chromium 149 and Chrome 157, not Gecko or WebKit.

---

## 5. Findings

| | finding | evidence | blocking |
|---|---|---|---|
| **F-1** | The L1 + L2 compact layer is a single shared component. G2A-c and G2B-c differ only in default slot, one subtitle, one button label and the puck caption; their cards are identical markup (text similarity 0.981). The owner's *default* experience therefore does not distinguish them. | §4 C-1, normalised layer diff | **not blocking** — the correction's brief asked for the three levels on all three, not for the levels to differ |
| **F-2** | The card at 390×844 is 374×560 = **63.63 %** of the viewport and obscures essentially the whole article; its collected list is confined to a 198 px scroller, so Files & Traces previews are below the fold. `E4`'s ≤25 % is missed at narrow. | §3 level 2, `shots/task_card_G2A-c_narrow.png` | **not blocking** — deliberate, disclosed, and the Conversation and composer remain present |
| **F-3** | At 390×844 the deep surface opens with **zero evidence items** and 1–2 of 9 provenance chips on the first screen in all three, with 106–172 px given to tab strips. | §4 C-2 table (narrow row), `density.json` | **not blocking** — the ledger is one labelled tap away (`Evidence (14)`) |
| **F-4** | The evaluation attributes distinct card characters ("grouped Posts/Files" vs "evidence-first") to G2A-c and G2B-c that do not exist in the render, and predicts G2B-c as primary on reasoning that measurement does not support. | §4 C-1, C-2 | **not blocking** — a report-accuracy defect, but it must not be carried into selection unchallenged |
| **F-5** | G2C-c has a `role="tab"` with no `aria-controls`; the author's own counts show 10 tabs against 9 panels, reported as `invalid_tablist_count: 0`. | §4 C-3 | **not blocking** — minor ARIA deviation in a static mockup |
| **F-6** | G2B-c's redundant *"Close to Resting Magnet"* control renders 0×0 and is unfocusable at 390 px, and was reported as no undersized control. | §4 C-4 | **not blocking** — the primary return control works at both widths |
| **F-7** | Placement is four desktop / three narrow **preset slots**; there is no drag machinery of any kind in any file (zero `draggable`, `pointerdown`, `mousedown`, `cursor: grab`, positional style writes). The owner asked for an object "dragged and dropped anywhere in the working area". | source scan, §3 level 2 | **not blocking** — the experiment's own boundary forbids building functional features, and the gap is disclosed inside the artifact |

**Not checked, and not repaired.** I ran no screen reader and no physical touch device; I tested
no Gecko or WebKit engine and no virtual keyboard; I did not evaluate the standalone comparison
bundle's hub navigation, the workspace `index.html`, the preserved timed-out partial beyond its
digests, the Gen 1 or original Gen 2 evaluations as documents, or the lineage experiment. I
repaired nothing — I modified no candidate, no script, no application source and no Brain
record, and I asked no owner decision.

---

## 6. Gen 3 parents

Because the compact layer is shared (F-1), levels 1 and 2 cannot rank these candidates. The
selection rests on the deep surfaces, where the measured differences in §4 C-2 are real.

### Recommended: `G2A-c` — Compact Magnet → Origin-Anchored Workbench Desk · **best Gen 2**

Ancestry `C6 primary × C4 interior × C5 narrow` + `ent-93f00e5ef142`. On the first screen of
deep work at desktop it puts **5 evidence items and 8 of 9 provenance chips on screen while
still showing 23.89 % of the originating Conversation** — at least matching G2B-c on audit
density and adding continuity for free. It is the only candidate in which the owner's concern
("remain unobtrusive while I'm working in a Conversation") is answered *inside* level 3 and not
only by leaving it. It carries no defect of its own. **Strengths**: highest measured first-screen
evidence density; only candidate keeping Origin literally visible during deep work; cleanest
tab chrome (71 px); 2 of 9 chips at narrow, best of the three. **Weaknesses**: the Origin band
costs roughly 210 px of vertical workbench; the band truncates post #14 rather than scrolling
it; shares F-2, F-3 and F-7.

### Recommended: `G2B-c` — Compact Magnet → Pinned-Evidence Split Desk

Ancestry `C4 primary × C6 composer × C5 narrow` + `ent-93f00e5ef142`. Kept not because the
author predicted it, but because its margin behind G2A-c is one evidence row while its
**first-screen priority is genuinely different**: it leads with the Magnet's identity card —
scope, filter, retention, all-input-visibility warning and the five participants with their
runtimes — above the ledger, where G2A-c leads with evidence. Which of those a person wants
first is exactly the question Gen 3 can answer. It also has the cleanest return grammar at
desktop. **Weaknesses**: no Conversation during deep work; F-6; shares F-2, F-3, F-7.

### Not recommended: `G2C-c` — Compact Magnet → Adaptive Evidence-Pinned Focus Stack

Measured weakest where it matters: **1 evidence item and 5 of 9 provenance chips** on the first
screen of deep work at desktop, against 5 and 8 — the ledger is pushed below the fold by a
~300 px summary column, and it spends the most height on chrome (102 px desktop, 172 px narrow,
three bands). It also carries the only ARIA defect in the set (F-5). Its two genuine
contributions live entirely in the shared compact layer and are one-line patterns:
**the Perspectives-first card ordering** (which echoes the owner's second reference image, a
summary panel with a staleness warning) and **the dashed orbital resting cue**. Gen 3 should
inherit both as variables without inheriting the focus-stack structure.

**Nothing lawful is lost by this rejection.** C5 entered the lineage as the narrow-screen
parent, and both recommended candidates already declare `× C5 narrow`; the C5 grammar survives.

**The alternative, stated so it can be overruled**: admit G2C-c as a third parent purely for
its card ordering. I do not recommend it, because that contribution transfers as a pattern and
carrying the whole candidate would preserve the weakest deep surface in the set. The choice is
the carrier's and the owner's, not mine.

### Implementation feasibility

Judged from the rendered structure, not from any implementation plan.

What F-1 records as a selection problem is a **feasibility advantage**: the resting object and
card are one component with a stable contract — a `button` carrying
`aria-haspopup="dialog"` / `aria-expanded` / `aria-controls`, a non-modal `role="dialog"`
card, a `pointer-events: none` floating layer, and a position expressed as a named slot on a
data attribute. That is an ordinary popover over the existing Quiet article and docked
composer, not a new layout system; it is reusable across Magnets as drawn, and it already
behaves identically under two engines.

Three things are drawn but not implemented and would carry real cost: **placement anywhere**
(hit-testing, collision with the composer and article, and per-Magnet persisted coordinates —
none of which exists here, F-7); **the all-input visibility gate**, which every candidate
honestly marks "enforcement pending" and which is a backend question, not a UI one; and
**scale**, since the 200-entry cap and pagination are disclosures over a 14-item fixture, so
the card's "8 of 14 / 6 of 14" grouping says nothing about how it behaves at 200. The deep
surfaces themselves are conventional two- and three-column compositions and the tab machinery
is already correct in G2A-c and G2B-c; G2C-c's layer trail is the only structure needing an
ARIA repair (F-5). None of this bears on a static design experiment, but it is what a first
implementation slice would meet.

---

## 7. Testable weaknesses for Gen 3

Each is measurable by re-running the probes in `probes/`; each states a target so that
"improved" is not asserted.

| | weakness | target |
|---|---|---|
| **W-1** | Card at 390 px covers 63.63 % of the viewport (F-2) | ≤40 % of viewport at 390×844, **or** an explicitly different narrow grammar, with ≥2 previews per kind visible without scrolling inside the card |
| **W-2** | Deep surface at 390 px opens with no evidence item (F-3) | ≥1 fully-visible evidence item and ≥4 of 9 provenance chips on the first screen at 390 px, with tab-strip chrome ≤72 px |
| **W-3** | The compact layer does not differentiate candidates (F-1) | either make the resting object and card an explicit variable across Gen 3 candidates — status vocabulary, section order, resting cue — or state plainly that levels 1–2 are settled and Gen 3 varies only level 3. Checkable by the same normalised layer diff |
| **W-4** | Placement is four preset slots, not placement anywhere (F-7) | render the resting object at ≥3 **arbitrary coordinates** not drawn from a preset enum, keep the existing in-artifact disclosure, and state the intended persistence model |
| **W-5** | The resting object carries six marks (`MAG`, `14`, `3P`, `+2`, `!`, `3P`) in a 60 px circle, with `3P` duplicated; the owner's reference carries one count and one badge | ≤4 distinct marks, no duplication, with `E2` still ≥3 of 4 status facts legible |
| **W-6** | G2A-c's Origin band truncates post #14 | the band either scrolls to the reading anchor or states that it is a fixed excerpt |

---

## 8. Remaining uncertainty

No human has used any of this; every usability statement in the correction, in the Gen 1
review and in this review is an expert walkthrough over a static mockup. Specifically unknown:
whether a 60 px puck with four badges reads as calm or as clutter; whether a card covering two
thirds of a phone screen feels compact; whether hover-reveal is welcome or intrusive during
reading; whether the wrong-destination risk is real when the composer switches to Magnet Chat;
whether 14 items predicts anything about 200. Untested: screen readers, physical touch,
virtual keyboards, Gecko and WebKit, persistence, backend enforcement of the `SRC-09`
visibility gate, and real source capture. The experiment can answer `W-1` through `W-6` by
measurement; it cannot answer the preference questions without putting a candidate in front of
the owner.

---

## 9. Reproducing this review

From `magnet-gen2-independent-review/probes`, with the repository's Python and Playwright:

```
python -I cold.py           # cold-load outline, all 10 documents, both widths
python -I recon.py          # open each card by hover and dump it
python -I diff_compact.py   # normalised cross-candidate diff of the compact layer
python -I levels.py         # E1-E9 walk via the candidates' own controls
python -I keyboard.py       # Tab reachability from a fresh load
python -I tasks.py          # T1-T8 plus overlap and accessibility
python -I deepwalk.py       # every reachable panel; facts a person can actually reach
python -I spotcheck.py      # card previews, Magnet Chat, return controls, tablists
python -I verify_defects.py # confirms F-5 and F-6
python -I density.py        # first-screen evidence density -- the selection measurement
python -I hittest.py        # pointer-events hit test + re-measure in Chrome 157
python -I baselines.py      # corrected vs originals vs frozen C4/C1/C5/C6
python -I integrity.py      # manifest and frozen-original digests
```

Results are the `*.json` files in the review directory; every state quoted above is in
`shots/`. The rendered bytes are in `held/pkg/`, extracted from `adm-52c810a4f8b5`.
