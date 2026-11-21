# Generation 1 — Independent Review and Selection Recommendation

**Reviewer**: Independent Reviewer (`@Quill`), runtime `claude / claude-opus-5`
**Reviewing**: six Gen 1 static Quiet Magnet concepts returned by `@Builder-QuietNavigation`
(`antigravity` / Gemini 4 Neon High), Turn `ent-fb00b4be9308`, request `opr-4c3317411da1`
**Against**: owner request `ent-8bcfb7953748`; shared scenario and tasks `T1`–`T8` (`adm-8993100871be`)
**Date**: 2026-11-21
**This review's request**: `opr-677635953426` (`ent-3472781bf72c`)

---

## 0. Verdict

**The declared property holds.** Six materially distinct, self-contained, inspectable static
concepts exist over one shared realistic scenario; all ten owner criteria are represented in
rendered form in every concept; tasks `T1`–`T7` complete at desktop and at `390px` in all six;
the two comparison hubs load and switch cleanly. I reproduced this from my own rendering, not
from the Builder's report.

**No blocking findings.** Nothing here loses or corrupts data, breaks essential navigation,
prevents normal use or a working build, breaches authority or security, or leaves out something
the owner's request required of Generation 1.

**Eight non-blocking findings** are recorded in §6, four of which correct ratings or verification
claims in the author's own evaluation (`adm-3673c41c0c90`) and evidence (`adm-587604544c36`).

**Recommended Gen 2 parents: C4, C6, C5.** **Rejected: C2, C3.** **Preserved baselines: C1**
(the conventional contextual inspector the request required) and **C4 frozen unmodified** as the
strongest Gen 1 design against which Gen 2 and Gen 3 are measured. Reasoning and evidence: §5.

---

## 1. How independent this review actually is

Independence comes from how a review was set up, not from wearing the Persona. Stated plainly:

**Independent:**
- Different runtime and model from the author. Concepts were authored on `antigravity` /
  Gemini 4 Neon High; this review ran on `claude` / `claude-opus-5`.
- I did not read the author's verification results before forming my measurements. I wrote my
  own harness (`inventory.py`, `taskwalk.py`, `t4fix.py`, `probes.py`, `probes2.py`,
  `composer.py`, `composer2.py`, `destswitch.py`, `a11y.py`, `lists.py` in this directory) and
  did not import, call or reuse `magnet-ui-gen1/scripts/verify_gen1.py`.
- Every claim below about what a concept does comes from my own headless-Chromium render at
  real viewports `1440×900` and `390×844`, with per-state screenshots in `shots/`.
- I measured things the author's harness did not measure at all: per-element horizontal
  overflow, rendered-text fact visibility per task state, clicks-per-task, composer count and
  destination labelling per state, ARIA tab semantics, and focus styling.

**Not independent, or limited:**
- **Shared workspace, not a fresh copy.** I read and ran the concepts from the author's own
  directory `C:\Work\Mentis-workspace\day-to-day\magnet-ui-gen1`, not from a clone of the
  returned `adm-` bytes. Corroboration: `SCENARIO_AND_TASKS.md` on disk hashes to
  `a98380ebaa24ee62b102db3e26b4859b4944af9074cf2e25ae4646a31c9ace77`, exactly the digest Mentis
  returns for `adm-8993100871be`; and all six concept files' on-disk byte counts match the sizes
  Mentis records for `adm-58f5b7557241`, `adm-a77179395e85`, `adm-f90c54e01b56`,
  `adm-7792bd18d276`, `adm-1016448ab480`, `adm-97ac18e7aff6` exactly. That is strong
  corroboration, not proof of byte-identity for the HTML.
- **Expert walkthrough, not user testing.** Everything in §3–§5 is a scripted expert walkthrough
  plus automated measurement. **No human user was observed using any concept.** No task time, no
  error rate, no comprehension check, no preference data exists for any of the six. Where I say
  a concept is "clearer" or "faster", that is a prediction from measured step counts and measured
  legibility, not an observed result. §4 separates these three evidence classes explicitly.
- **No live assistive technology.** §3.6 reports static ARIA/semantics and focus-style
  measurements. No NVDA, JAWS or VoiceOver session was run, and none of my findings should be
  read as a screen-reader verdict.
- **Not checked.** I did not verify the author's claim that C3 has the highest exposure to Quiet
  2's `q2:`/`q2s:`/`q2v:` inline block-identity seam, and I did not read Quiet 2's source to
  test any of the eight implementation-feasibility ratings. Those ratings are the author's and I
  pass them through as the author's, marked as such.
- **Single-runtime authorship stands.** The owner asked that concepts be distributed across
  agents "where practical"; all six came from one Builder run. The author disclosed this. It
  means the six share one designer's habits — and indeed they share an identical component
  vocabulary, identical copy, identical composer markup and an identical 7-item evidence list.
  The "six independent explorations" premise is weaker than the count suggests. I weigh this in
  §5.

---

## 2. What I verified about the author's own evidence

I re-ran the owner-relevant parts of the author's claims rather than accepting them.

| Author claim (`EVIDENCE.md`, `verification-report.json`) | My finding |
|---|---|
| 6/6 concepts, `0px` horizontal overflow at `1440×900` | **Confirmed.** `document.scrollWidth == 1440` in all six, and I found **zero** concept-level elements painted past the viewport edge at desktop. |
| 6/6 concepts, `0px` horizontal overflow at `390×844` | **True as stated, but the metric hides a real effect.** Document-level scrollWidth is `390` in all six. At element level, C1, C4 and C6 push primary navigation controls outside the viewport into horizontal scrollers (§3.5). The author's own narrow contact sheet visibly shows the clipping. |
| 0 console / page errors, all six, both widths | **Confirmed independently**, both widths, in every state I drove. |
| 16/16 required scenario tokens in all six | **True but a weak test.** It is a case-insensitive substring grep of the raw HTML source (`verify_gen1.py:113`). Tokens such as `P1`, `P2`, `P3` and `Interpretation` match almost anything. It does not test that a fact is rendered, reachable, or in the right state. My §3 fact matrix replaces it with rendered-`innerText` visibility per task state. |
| "Static Tab & Theme Controls — Verified", `tab_clicks_ok: true` ×6 | **Not substantiated.** `tab_clicks_ok` is a literal constant set at `verify_gen1.py:122` and never assigned `False`. The tab exercise clicks at most the first 8 `[data-tab-target]` controls, desktop only, after the screenshot, and asserts nothing about the result. I did not rely on it; I drove every control myself (§3). |
| Both hubs load and switch cleanly | **Confirmed independently.** `index.html` and `gen1-standalone-bundle.html` both expose 7 views (`c1`–`c6`, `matrix`), switch without error, and each concept view mounts one live iframe. |
| "No functional application features, Brain mutations, schema or deployment changes" | **Consistent with what I saw.** All controls are local class toggles; no network, storage or backend code in any concept. I did not audit the whole repository for unrelated changes; that was outside this review. |

**Net**: the author's package is honest about its limits and its headline results reproduce. Two
specific evidence claims are overstated (`tab_clicks_ok`, and "zero overflow" read as "narrow
screens work"), and one rating that follows from them is wrong (§6, F-5).

---

## 3. Observed results — the same scenario applied to each concept

Method: cold load at the stated viewport, then the click path a user would take. "Clicks" counts
only user actions, never scrolling. "Visible" means the string appears in the rendered
`innerText` of the non-hidden DOM with the mockup inspection ribbon excluded — i.e. a user could
read it, possibly after scrolling.

### 3.1 Interaction cost — clicks to complete T1–T7 (desktop)

```
C4  Dual-Column Evidence & Inquiry Desk ........  7
C2  Magnet Conversation Hub .....................  8
C6  Resizable Bottom Workbench ..................  9
C3  Margin Lens .................................. 10
C1  Contextual Side Inspector (baseline) ......... 11
C5  Progressive Focus Stack ...................... 14
```

Per task (desktop / narrow where they differ):

| Task | C1 | C2 | C3 | C4 | C5 | C6 |
|---|---|---|---|---|---|---|
| T1 Magnet identity | 0 | 0 | 0 | 0 | 1 | 0 / **1** |
| T1 Curated inspection | 1 | 1 | 1 | **0** / 1 | 1 | 1 |
| T2 Switch to P2 | 2 | 1 | 1 | 1 | 2 | 1 |
| T2 Switch to P3 | 2 | 1 | 1 | 1 | 2 | 1 |
| T2 New Perspective | 2 | 1 | 2 | 1 | 2 | 1 |
| T3 Questions & synthesis history | 2 | 1 | 1 | 1 | 2 | 1 |
| T4 Full lineage manifest | 2 | 2 | 1 | **1** | 2 | 2 |
| T5 Explicit continuation | 1 | 1 | 1 | 1 | 1 | 1 |
| T6 Magnet Conversation | 1 | **0** | 1 | 1 | 1 | 1 |
| T7 Return to origin | **0** / 1 | 1 | 2 | 1 | 2 | 1 |

C5's cost is structural: its depth trail forces a layer hop before any perspective action. C1's
cost is its nested tab-within-tab inspector. C4 is cheapest because its left ledger and right
inquiry column are both already open.

### 3.2 T1 — Magnet identity and curated inspection

All six show the stable id `mag-checkout-latency`, the frozen digest `sha256:9f4b8e21…c218` and
the bounded-capture notice `Bounded page 1 of 1 (200-entry cap) · 14 matched · complete corpus
not claimed` — **except C6 at `390px`**, where the bottom sheet opens on the P1 synthesis pane
and neither the stable id nor the bounded notice is on screen until the user clicks `Curated`
(F-4). T1's bar is "immediately legible"; C6 narrow misses it by one click.

**All six render 7 of the 14 bounded items** (`SRC-01, 02, 04, 07, 09, 13, 14`) while labelling
the collection "Curated (14)" / "14 matched". All six *disclose* this honestly ("representative
of 14 bounded items"), so it is not a defect — but it is a hard limit on the evidence: **no
concept has been tested at the list length it claims**, let alone at the 200-entry cap. Every
"best for evidence inspection" judgement, including mine, is extrapolation from a 7-item list
(F-7).

C4 is the only concept that separates the viewer's personal filter from the shared Magnet scope
in a form I could read at a glance — `Personal filter (@brian): All 14` beside
`MAGNET COLLECTION · CONSTANT ACROSS PERSPECTIVES`. At `390px` that tag costs one click
(`Evidence` segment).

### 3.3 T2 — Magnet identity invariance across Perspectives

This is the claim the whole Magnet/Perspective distinction rests on, so I tested it directly
rather than reading it: in each concept I drove `P1 → P2 → P3 → + New` and re-read the rendered
text in every resulting state.

**The config digest `sha256:9f4b8e21…c218` remains visible and unchanged in all four Perspective
states, in all six concepts, at both viewports.** No concept lets a Perspective switch alter,
hide, or appear to alter the Magnet configuration. This property holds universally and does not
discriminate between concepts.

What does discriminate is *how* it is shown:
- **C4** makes it spatial and explicit: the collection is a physically separate, labelled,
  locked left column; switching the right column visibly leaves it untouched.
- **C2, C5** make it textual: a "Magnet independence & visibility: Reads Magnet sha256:… 
  (unchanged)" banner inside the Perspective.
- **C1, C3, C6** put the digest in a header above the Perspective switcher, which reads as
  "context", not as "invariant".

Two concepts show the stable id *only* in states I did not always reach: C5 never shows
`mag-checkout-latency` on Layer 3, and C6 at `390px` does not show it in the default pane. The
digest is always there; the human-readable identity is not (F-4).

### 3.4 T4 — Provenance and lineage audit

I initially recorded four concepts as failing to show the current version `#v2` of the edited
source. **That was an artifact of my own harness**, which clicked every `<details>` summary and
so *closed* the manifests that C1, C3, C4 and C5 ship already open. Corrected (`t4fix.py`,
clicking only closed manifests):

**All six concepts expose all five audit edge cases, at both viewports, in 1–2 clicks**:
edited-after-citation (`ent-88a1c04#v1 pinned; Turn now #v2`), deleted source
(`SRC-07 … deleted after S1; retained in lineage only`), shared de-duplicated original
(`SRC-02 … shared, counted once`), mutual dependency (`P1·S3 ↔ P2·S1 … MUTUAL DEPENDENCY flagged
for human audit`), and the restricted input with an honest pending-enforcement warning
(`SRC-09 … enforcement pending`). Captured scope and uncovered new items are present in all six.

Two differences are real and matter for selection:
- **C4 is the only concept where the audit is legible without opening anything.** Its left
  ledger carries a per-item badge (`Edited after citation (#v1 pinned)`, `Shared original ·
  de-duplicated`, `Deleted / unavailable (edge kept)`, `Restricted · all-input gate`) **and**
  a `Referenced by: P1·S1, P1·S2, P1·S3` back-reference on every item, side by side with the
  synthesis that cites it. That is the strongest provenance surface of the six, and I confirm
  the author's "Strongest" rating from my own render.
- **C4 loses exactly that advantage at `390px`**, where the ledger is hidden in inquiry mode and
  the current version `#v2` is no longer readable beside the pinned `#v1` without switching
  segments.

### 3.5 T8 — Narrow screen (`390×844`), measured per element

Document-level overflow is `0px` in all six, as the author reported. Measuring every painted
element instead, and excluding the mockup's own inspection ribbon (not part of any concept) and
the shared `.q2-top-title` ellipsis (present in all six):

| Concept | Concept-level narrow overflow conditions | What is actually off-screen |
|---|---|---|
| **C5** | 0 | — |
| **C2** | 0 | — |
| **C3** | 2 (after opening the drawer) | drawer tab rail scrolls horizontally |
| **C1** | 2 | inspector tab bar is a `447px` scroller inside `390px`; `Magnet Chat (9)` sits at `x=443`, off-screen |
| **C4** | 4 | Right Desk tab bar is a `602px` scroller; `Continue Agent` (`x=480`) and `Magnet Chat (9)` (`x=598`) are both off-screen |
| **C6** | 9 | Perspective rail is a `910px` scroller inside `390px`; **4 of 7** primary controls (`Curated Evidence`, `Continue Agent`, `Magnet Chat`, `+ New Perspective`) are off-screen at load |

These are `overflow-x: auto` scrollers, so the controls are reachable by horizontal swipe — this
degrades narrow-screen discoverability, it does not break navigation. But it is invisible to the
author's metric, and it contradicts the author's narrow-screen rating for C6 ("works cleanly",
F-5). **C5 and C2 are the only two concepts with genuinely clean `390px` structure**, and C5's
claim of identical desktop/narrow grammar is the one width claim that fully survives measurement.

Page length at `390px` (total scroll height): C3 `1676` · C1 `2636` · C5 `2883` · C4 `2945` ·
C2 `3219` · C6 `3328`.

### 3.6 Accessibility — measured, not asserted

Uniform across all six concepts, both viewports:

- **`0` of the tab-like controls carry `role="tab"`.** `0` carry `aria-selected`. `0` of the
  switched panels carry `role="tabpanel"` or `aria-hidden`. C1 and C4 *do* declare
  `role="tablist"` — with no `role="tab"` children, which is invalid ARIA and exposes the group
  worse than no role at all. The author's omission note cites `role="tablist"` as evidence of
  semantic landmarks; that specific citation does not hold up (F-6).
- **No `:focus`, `:focus-visible` or `outline` rule exists in any of the six.** Every concept
  draws custom dark surfaces and relies entirely on the Chromium default focus ring over them.
  No concept has defined a keyboard focus indicator for Quiet's dark palette.
- **No `aria-live` region in any concept**, though every concept displays changing status
  (`2 new since S3`, `Behind`, `enforcement pending`).
- Landmarks are uneven: **C4 and C6 have no `<main>` at all**; C2 has two `<h1>`s.
- Smallest hit targets: **C5's two `13px`-wide full-height stack-edge "peek" buttons**. They are
  named only by `title=` (a tooltip), which is weak but not absent. All other focusable controls
  in all six concepts have accessible names; `summary` elements are `19px` tall at desktop,
  `38px` at narrow.

None of this discriminates strongly between concepts — it is a shared Gen 1 gap and a Gen 2
requirement (H-5).

### 3.7 Composer continuity and separate Conversation contexts — the sharpest result

I drove each concept into the Magnet Conversation state and counted visible composers and
destination labels. This produced the clearest separation of the six.

| Concept | Composers visible in the Magnet-Chat state | Destination model | Origin draft |
|---|---|---|---|
| **C6** | **1** | explicit two-way switch: `Destination: Origin (…· draft saved)` ↔ `Destination: Magnet Chat (P1 Continuation)` in one dock | **visible, and verified to survive a round trip** |
| **C5** | 2 surfaces, 1 destination | explicit two-way switch on Layer 4 | restored by the switch; **not shown on Layer 1** |
| **C4** | **1** | single, `Posting to · Magnet: Checkout Latency & Cache Watch` | not painted (origin hidden); protection asserted by a label only |
| **C2** | **1** | single, `Posting to · Magnet: …` | not painted (navigated away) |
| **C1** | **2** | **two live `Posting to` targets on one screen** — origin composer (left column) and Magnet composer (right column), `98px` apart vertically | visible in the origin composer |
| **C3** | **2** | **two live `Posting to` targets on one screen** — drawer composer at `y=769` overlaying the article composer at `y=885`, `116px` apart | visible, under the drawer |

I verified the switches actually work rather than reading the labels:
- **C6**: `Origin → Magnet → Origin` round trip. Draft text painted → hidden → **painted again**,
  with `Posting to` tracking correctly at each step.
- **C5**: selecting `Composer: Origin #14` restores both the draft text and
  `Posting to · Release Readiness — Checkout v4.2`.

**C1 and C3 are the two concepts that place two simultaneous, live "Posting to" destinations in
one viewport.** The author listed this as an open *question* for C1 and did not list it for C3
at all. On measurement it is C3's most serious problem and a material one for C1 (F-1).

A shared limitation that bounds all of the above: **in all six concepts the composer is
`position: static` and scrolls with the page.** Quiet 2's composer is a fixed bottom dock. At
cold load, no concept's composer is inside the first viewport except C3's (partially), and
**C1 at `390px` renders no composer at all** until the user returns to the origin. So every
composer claim in this package — C6's unified dock, C5's switch, C1's dual-composer risk — is a
*drawing* of composer behaviour, not a demonstration of it (F-2, H-1).

### 3.8 Multi-participant and agent attribution (T6)

All six distinguish humans from agents and name the runtime. **C6 is the clearest**:
`maya — Human · Staff Eng`, `Atlas — Agent · codex/gpt-6.1-sol`,
`Louie — Agent · claude/claude-opus-5`, with `Human + Agent stream` and
`Personal filters stay separate` chips on the thread. C1, C2, C4 and C5 carry the same
attribution with slightly less prominence. T5's continuation summary (perspective ref,
destination, incremental inputs `SRC-13`/`SRC-14`, runtime, estimated cost, read-only /
artifact-until-Keep authority) is present and complete in **all six**, reachable in 1 click
everywhere; this criterion does not discriminate.

**Where the Magnet Conversation actually sits** — distance from the top of the page to its first
post (`#6`), at a `900px` / `844px` viewport:

| | C3 | C4 | C6 | C1 | C5 | C2 |
|---|---|---|---|---|---|---|
| desktop | **263** | 430 | 516 | 624 | 703 | **1550** |
| narrow | **280** | 790 | 454 | 778 | 1140 | **2215** |

**C2 is named for the Magnet Conversation and buries it.** At `1440×900`, in its *default*
state with nothing expanded, zero Magnet Conversation posts are above the fold — the Dossier
Shelf consumes the whole first screen. At `390px` the first post is 2.6 screens down. The author
flagged this as happening "when expanding full manifests"; it happens without expanding anything
(F-3). This is the single most consequential measured result for selection.

---

## 4. Which claims are what kind of evidence

The owner asked that predictions be separated from observations. Everything above falls into one
of three classes and nothing in this review belongs to a fourth:

**(a) Automated measurement — reproducible, strongest.** Per-element overflow and off-screen
controls (§3.5); rendered-text fact visibility per state (§3.2–3.4); clicks per task (§3.1);
composer count, destination labels and verified round-trip behaviour (§3.7); distance to the
Magnet Conversation (§3.8); ARIA/focus/landmark counts and hit-target sizes (§3.6); console and
page errors; hub load and switching; digest and byte-size corroboration (§1). Re-run with the
scripts in this directory.

**(b) Expert walkthrough prediction — reasoned, falsifiable, not observed.** Every statement
that a structure will be *clearer*, *calmer*, *faster to learn*, *more confusing*, or *more
error-prone for a real person*. In particular: that C4's spatial lock teaches Magnet-vs-Perspective
invariance better than C2's and C5's textual banner; that two simultaneous `Posting to` targets
will cause mis-sends; that a `910px` rail inside `390px` will go undiscovered rather than
swiped; that C5's layer hops will feel calm rather than slow. These are the hypotheses Gen 2
should test (§7), not results.

**(c) The author's own unverified ratings, passed through as the author's.** All eight
implementation-feasibility judgements, including C3's `q2:`/`q2s:`/`q2v:` block-identity seam
exposure and C1's "directly mounts inside existing `Quiet2.tsx`". I did not read Quiet 2 source
and did not test any of them.

**Absent entirely**: observed user testing. No human used any concept. No task time, error rate,
comprehension measure or preference was collected for any of the six, at either width. Any Gen 2
or Gen 3 claim of "improved usability" that rests on Gen 1 therefore rests on (a) and (b) only.

---

## 5. Selection recommendation

The owner's rule: select only the best two or three for derivation; preserve the strongest
original design as a baseline; exclude the rest explicitly from Gen 2.

### 5.1 Parents — C4, C6, C5

**C4 — Dual-Column Evidence & Inquiry Desk. Parent 1.**
Earns it on the two hardest criteria, measured: provenance (the only concept where all five
audit edge cases, the per-item badges and the `Referenced by` back-references read without
opening anything — §3.4) and Magnet-vs-Perspective clarity (the only concept that proves
invariance *spatially* rather than asserting it in a banner — §3.3). Also cheapest overall
(7 clicks, §3.1), the only concept to distinguish the personal filter from shared Magnet scope
on sight, and a single unambiguous composer destination. Its weaknesses are equally clear and
are precisely what Gen 2 must fix: the originating Conversation is entirely hidden behind a
return bar (worst conversation continuity of the six), the origin draft is never painted, and
its signature side-by-side advantage collapses at `390px` where two of six Right Desk tabs sit
off-screen.

**C6 — Resizable Bottom Workbench + Origin Canvas. Parent 2.**
The only concept that *demonstrates* — not merely labels — a single composer whose destination
switches between the originating Conversation and the Magnet Conversation while preserving and
restoring the unsent draft (verified round trip, §3.7). It is also the only concept that keeps
the originating Conversation at full `680px` measure while a working surface is open, and it has
the clearest human-vs-agent runtime attribution of the six (§3.8). It is the structural answer
to C4's worst weakness, which is why the pair is worth more than either alone. Its own weakness
is the worst `390px` result measured (9 overflow conditions, 4 of 7 rail controls off-screen,
Magnet identity not legible on arrival).

**C5 — Progressive Focus Stack. Parent 3.**
Admitted for one measured property neither C4 nor C6 has: **genuinely clean structure at
`390px`** — zero concept-level overflow, no clipped navigation, and an interaction grammar that
is actually identical at both widths (§3.5). It also carries a working destination switch. If
Gen 2 derives only from C4 and C6, it inherits two concepts with the worst narrow-screen results
of the six and no parent from which to inherit a fix — and reviving a rejected concept to supply
one is forbidden. C5 is admitted deliberately so that the narrow-screen correction has a lawful
parent. Its costs are known and must not be inherited uncritically: highest interaction cost of
the six (14 clicks), no side-by-side comparison of any kind, and a stale orientation cue (F-8).

### 5.2 Baselines preserved

The request is open to two readings and both are honoured, at no cost:

- **C1 — Contextual Side Inspector** is preserved unmodified as the **conventional baseline**
  the request required ("include one conventional contextual-inspector baseline"). It is the
  smallest architectural delta from Quiet 2 and the only concept that keeps the originating
  Conversation, its anchor and its draft composer alive beside the work at desktop with zero
  clicks (T7 = 0). Gen 3 must beat it, not quietly replace it.
- **C4 is additionally frozen as the strongest Gen 1 design** — the yardstick Gen 3 is measured
  against per the owner's Gen 3 criteria. Freezing C4 and deriving from C4 are compatible: the
  frozen copy is the measuring stick, the derivative is the candidate.

### 5.3 Rejected, explicitly, from Gen 2 derivation

**C2 — Magnet Conversation Hub + Dossier Shelf. Rejected.**
Not on taste — on its own premise, measured. A concept whose thesis is "the Magnet's own
Conversation is the centre" places that Conversation's first post **650px below the fold at
`1440×900` in its default state, and 1,371px below the fold at `390px`** (§3.8), behind a
Dossier Shelf that fills the entire first screen. Every other concept surfaces the Magnet
Conversation faster, three of them twice as fast. Its genuinely good properties — clean `390px`
structure, one native composer — are each held by an admitted parent (C5, C6). Its distinctive
idea is worth keeping as a *hypothesis*, not as a parent: see H-3.

**C3 — Margin Lens & Inline Post Anchors. Rejected.**
Three independent reasons, two of them mine:
1. **Measured**: it is one of the two concepts that put two live `Posting to` destinations on one
   screen, and the worse of the two — the drawer composer overlays the article composer `116px`
   away, where C1 at least separates them into different columns (§3.7). The author did not list
   this among C3's weaknesses.
2. **Measured**: the structure that names the concept does not exist at the width where it is
   most needed. At `390px` the scholarly margin collapses into a single inline `<details>`; the
   margin lens becomes a disclosure triangle. The concept's distinguishing interaction survives
   only at desktop.
3. **The author's rating, passed through unverified**: lowest near-term implementation
   feasibility, highest exposure to Quiet 2's unresolved inline block-identity seam. I did not
   check this and it is not load-bearing for the rejection — (1) and (2) are sufficient.

C3's one real strength — it is the only concept that never interrupts the originating article,
and it surfaces the Magnet Conversation fastest of all six (§3.8) — is preserved as H-4 for
testing inside a C6 derivative, not as a parent.

### 5.4 Why not four, and why not two

Three parents is the owner's ceiling and this selection uses it for a structural reason, not to
avoid choosing: C4 supplies evidence clarity, C6 supplies conversation and composer continuity,
C5 supplies width parity. Each covers a named weakness of another, and dropping any one leaves
Gen 2 without a lawful source for a measured Gen 1 defect. Adding a fourth would reintroduce a
concept that lost on its own evidence.

---

## 6. Findings

All findings are **non-blocking**. None loses or corrupts data, breaks essential navigation,
prevents normal use or a working build, breaches authority or security, or leaves out something
the owner's request required of Generation 1. Attribution: all findings belong to the single
Gen 1 Builder package; there are no integration seams in this work.

**F-1 — Two live composer destinations on one screen (C1, C3).** Non-blocking.
*Evidence*: in the Magnet-Chat state, `composer2.py` finds two visible `.q2-composer` elements
each labelled `Posting to`, one targeting `Release Readiness — Checkout v4.2` (holding the unsent
draft) and one targeting `Magnet: Checkout Latency & Cache Watch`. C1: `y=1223` and `y=1321`
(different columns). C3: `y=769` (drawer, overlaying) and `y=885` (article). *Why it matters*:
the scenario's whole T7 premise is that the unsent draft must not be lost or mis-sent.
*Not corrected here* — Gen 2 must resolve it or inherit from a single-composer parent.

**F-2 — No concept's composer is docked; C1 at `390px` has no composer at all.** Non-blocking.
*Evidence*: every `.q2-composer` / `.c6-composer-dock` / `.c5-composer-bar` in all six resolves
to `position: static`. At cold load no composer is inside the first viewport except C3's
(partially). At `390×844` C1 paints no composer element at all until the user returns to origin.
*Why it matters*: the owner required that the existing composer be preserved; Quiet 2's is a
fixed bottom dock. Every composer-continuity judgement in this package, mine included, is
therefore drawn rather than demonstrated.

**F-3 — C2 buries the Magnet Conversation it exists to present.** Non-blocking.
*Evidence*: default state, nothing expanded. First Magnet Conversation post `#6` at `y=1550`
(viewport `900`) desktop; `y=2215` (viewport `844`) narrow. Compare C3 `263`/`280`, C4
`430`/`790`, C6 `516`/`454`. *Correction to the author's evaluation*: this is recorded as
occurring only "when expanding full manifests"; it occurs at load.

**F-4 — Magnet identity not legible on arrival on narrow C6; stable id absent on C5 Layer 3.**
Non-blocking. *Evidence*: C6 at `390×844`, cold load — `mag-checkout-latency` and `200-entry cap`
both absent from rendered text; one click on `Curated` reveals both. C5 Layer 3 shows the digest
but never the human-readable id. *Why it matters*: T1's bar is "immediately legible".

**F-5 — "Zero horizontal overflow" certifies less than it appears to, and one rating is wrong.**
Non-blocking (test-only in origin, but it changed a published rating). *Evidence*:
`verify_gen1.py:134` measures only `document.documentElement.scrollWidth`. Per-element
measurement at `390px` finds C6's `nav.c6-rail` is a `910px` horizontal scroller with 4 of 7
primary controls off-screen (`x = 504, 660, 770, 900`), C4's Right Desk tab bar `602px` with 2 of
6 off-screen, C1's inspector tab bar `447px` with 1 off-screen. *Correction*: the author's
criterion-9 rating of C6 ("Moderate — works cleanly") is not supported; C5 and C2 are the only
two concepts with clean narrow structure. The author's own narrow contact sheet visibly shows the
clipping.

**F-6 — Accessibility is asserted beyond what was verified.** Non-blocking.
*Evidence*: across all six, `0/9`, `0/6`, `0/6`, `0/6`, `0/16`, `0/9` tab controls carry
`role="tab"`; `0` carry `aria-selected`; `0` panels carry `role="tabpanel"` or `aria-hidden`;
no `aria-live` anywhere; no `:focus`, `:focus-visible` or `outline` rule in any file; C4 and C6
have no `<main>`. C1 and C4 declare `role="tablist"` with no `role="tab"` children — invalid
ARIA. *Correction*: `EVIDENCE.md` omission 4 cites `role="tablist"` as verified semantic
evidence; that citation does not hold.

**F-7 — Evidence-density claims are extrapolated from 7 of 14 items.** Non-blocking.
*Evidence*: all six render exactly `SRC-01, 02, 04, 07, 09, 13, 14` while labelling the
collection `14 matched` / `Curated (14)`. All six disclose the subset honestly. *Why it matters*:
the concepts selected for their evidence-inspection strength (C4, C6) have never been rendered
at the stated list length, let alone near the 200-entry cap. This is an uncertainty, not a
defect.

**F-8 — C5's depth cue is static and contradicts the selected layer.** Non-blocking, cosmetic.
*Evidence*: the top bar reads `Focus Stack · Depth 3 of 4` while Layer 1, 2, 3 and 4 are each
selected; the in-page label (`LAYER n OF 4`) updates correctly. *Why it matters*: the orientation
cue is the concept's signature claim.

**F-9 — `tab_clicks_ok` is a constant, not a check.** Non-blocking, test-only.
*Evidence*: `verify_gen1.py:122` sets `"tab_clicks_ok": True` and never reassigns it;
`EVIDENCE.md` reports "Static Tab & Theme Controls — Verified" for all six on that basis. I did
not rely on it and drove every control independently.

### Not checked, and not repaired

- I did not verify any implementation-feasibility rating, including C3's block-identity seam
  exposure. No Quiet 2 source was read.
- I did not run live assistive technology, a real touch device, or any browser other than
  headless Chromium.
- I did not test light theme beyond confirming the toggle fires without error.
- I observed no human using any concept; there is no user-testing evidence for any finding.
- I repaired nothing. No file in `magnet-ui-gen1` or in any application source was modified by
  this review; everything I wrote is in `magnet-gen1-independent-review`.

---

## 7. Checkable hypotheses and weaknesses for Generation 2

Each is phrased so a Gen 2 derivative can be judged to have passed or failed it, by measurement
where possible and by observed user testing where measurement cannot settle it.

**H-1 — Composer docking (requirement, not hypothesis; applies to every Gen 2 derivative).**
Gen 2 mockups must render Quiet 2's composer as a fixed bottom dock, present in the first
viewport at both widths, in every state. *Checkable*: `getComputedStyle(composer).position` is
`fixed` or `sticky`, and the composer's bounding box is inside the first viewport at
`1440×900` and `390×844` in all states. Until this holds, no composer-continuity claim from any
generation is evidence.

**H-2 — One destination, always (from C6; corrects F-1).**
*Hypothesis*: a single composer with an explicit destination switch produces fewer wrong-target
sends than two simultaneous composers. *Checkable now*: exactly one element matching
`/Posting to|Destination:/` is visible in any state. *Checkable only by user testing*: the
mis-send rate itself. A derivative that keeps two composers must say why.

**H-3 — Magnet Conversation above the fold (from C2's idea, not from C2).**
*Hypothesis*: the Magnet's own Conversation can be a first-class destination rather than a pane
without the dossier burying it. *Checkable*: the Magnet Conversation's first post is painted
within the first viewport at `1440×900` **and** `390×844` in the state that presents it — the
test C2 fails at `y=1550`/`y=2215` and C3 passes at `y=263`/`y=280`.

**H-4 — Uninterrupted origin article (from C3's idea, not from C3).**
*Hypothesis*: the originating Conversation can keep its full `680px` measure and never be
occluded while Magnet work is in progress. *Checkable*: the origin article's rendered width is
≥ `680px` and no working surface overlaps its bounding box, in every state, at desktop.

**H-5 — Narrow screens without hidden navigation (from C5; corrects F-5).**
*Hypothesis*: a working surface with C4's evidence density can reach `390px` without pushing any
primary control outside the viewport. *Checkable, strictly*: at `390×844`, in every state, no
element that is a primary navigation control has `getBoundingClientRect().right > 390`, and no
nav container has `scrollWidth > clientWidth`. C6 currently fails at `910 > 390`; C4 at
`602 > 390`; C1 at `447 > 390`. Wrapping, a segmented control, or an overflow menu all satisfy
it; a horizontal scroller does not.

**H-6 — Spatial invariance beats asserted invariance (from C4).**
*Hypothesis*: showing the Magnet collection as a physically separate, persistently visible,
labelled region teaches that a Perspective cannot change the Magnet better than a banner saying
so. *Measurable part*: the collection region stays painted, with the digest visible, through
`P1 → P2 → P3 → + New`, at both widths — which C4 satisfies at desktop and fails at `390px`.
*The comprehension claim needs user testing and currently has none.*

**H-7 — Evidence density at the stated scale (closes F-7).**
*Requirement*: Gen 2 must render the full 14-item collection and show how the 200-entry cap
behaves. *Checkable*: 14 distinct `SRC-nn` codes painted in the curated view; a stated and
visible behaviour (scroll, paginate, filter, or virtualise) for the cap. All six Gen 1 concepts
render 7.

**H-8 — Accessible switching (closes F-6).**
*Requirement*: `role="tablist"` / `role="tab"` / `aria-selected` / `role="tabpanel"` used
consistently or not at all; a defined `:focus-visible` indicator with adequate contrast on
Quiet's dark and light surfaces; `aria-live` on the staleness and enforcement notices; a `<main>`
landmark; no focusable control below `24×24`. *Checkable*: the measurements in §3.6, re-run.

**H-9 — Return restores the draft visibly (strengthens T7 for every derivative).**
*Observation*: after the return action, the unsent draft is below the fold in five of six
concepts (C6 at `390px` is the exception at `y=766` of `844`); in C5 it is not painted at all
until the composer destination is switched. *Checkable*: after one return action, the draft text
is painted inside the first viewport at both widths. **No Gen 1 concept satisfies this at
desktop.** Combined with H-1 it is the clearest single improvement available to Gen 2.

**H-10 — Does derivation beat the baseline at all?**
The experiment's own question. Gen 3 must be measured against frozen C1 **and** frozen C4 on the
measurable set — clicks per task (§3.1), facts visible per state (§3.2–3.4), narrow-screen
off-screen controls (§3.5), composer count and draft restoration (§3.7, H-9), accessibility
counts (§3.6) — and, if any usability claim is to be made at all, against observed users, which
Gen 1 wholly lacks. If the derived designs do not beat the baselines on these, that result should
be reported as the experiment's finding.

---

## 8. Reproducing this review

From `C:\Work\Mentis-workspace\day-to-day\magnet-gen1-independent-review`, with Playwright's
Chromium installed:

```
python -I inventory.py     # control inventory + per-element overflow, both viewports
python -I taskwalk.py      # T1-T7 walk, both viewports, screenshots to shots/
python -I t4fix.py         # T4 manifest, correct open/closed handling (supersedes taskwalk's T4)
python -I probes.py        # C3 narrow reachability, C6 narrow identity, C5 T7, C6 attribution, C4 narrow filter
python -I probes2.py       # T7 draft position in all six; C5 depth cue across layers
python -I composer.py      # composer destinations and Magnet-Conversation distance, both viewports
python -I composer2.py     # composer count per concept in the Magnet-Chat state
python -I destswitch.py    # C5 and C6 destination-switch round trip
python -I a11y.py          # ARIA, landmarks, focusables, hit-target sizes
python -I lists.py         # rendered curated item count vs claimed count
```

Outputs: `inventory.json`, `taskwalk.json`, `t4.json`, `controls.txt`, and `shots/` (151
screenshots: every task end-state per concept per viewport, plus targeted probes and both hubs).
`dbg.py` and `dbg2.py` are the scratch diagnostics that found the `<details>` open/closed
artifact; they are kept so the correction in §3.4 can be re-derived.

> **Note on `taskwalk.json`'s T4 rows**: that harness clicked every visible `<details>` summary,
> which closes the manifests C1, C3, C4 and C5 ship already open. Its `T4-manifest` facts are
> therefore wrong and are superseded by `t4.json`. The error and its correction are reported here
> rather than quietly dropped.
