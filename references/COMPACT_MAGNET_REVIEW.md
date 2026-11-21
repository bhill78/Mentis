# The compact Magnet clarification against the completed Gen 1 selection

**Reviewer**: Independent Reviewer (`@Quill`), runtime `claude / claude-opus-5`
**Request**: `opr-0f818ec29009` (Turn `ent-b488901565df`) — rerouted after the first reviewer
(`opr-d83920e07af9`) stopped at its deadline and returned no artifact.
**Assessing**: the owner clarification `ent-93f00e5ef142` against the six completed Gen 1
concepts and the selection recorded in Turn `ent-4a1ae936a75d` (parents C4, C6, C5; C4 frozen as
the strongest Gen 1 design; C1 preserved as the conventional baseline).
**Date**: 2026-11-21. Report directory: `magnet-compact-review-reroute/` (this review owns it).

---

## 0. Verdict in one paragraph

**The clarification does not overturn the Gen 1 selection, and it does not rescue any rejected
concept.** Measured at cold load, **none of the six concepts has a compact resting Magnet object,
none has a hover or keyboard-focus card, and all six open their deep surface by default.** The
criterion therefore separates no candidate from another at level 1 or level 2: there is nothing
to re-rank on. Where it does bite is level 3 and "unobtrusive in a Conversation", and there the
evidence **supports keeping the selected parents**: C4 and C5 are the only two concepts that can
be returned to a Conversation-primary state at both widths by one explicit control, and C4's is
the cleanest (`.c4-desk` goes to `display:none`). C1, preserved as baseline, is the only concept
whose default already keeps the Conversation dominant *and* shows the Magnet as an inline card
with status. The required correction is **a change of default and the addition of levels 1 and 2
to the existing parents** — bounded, and already delegated as the running Gen 2 correction
(`opr-32f29a6cdf42`). I did not touch it.

---

## 1. How independent this review is

**Independent**: every claim in §3–§5 comes from my own headless-Chromium render of the six
concept files at `1440×900` and `390×844`, driven by probes I wrote in this directory
(`outline.py`, `levels.py`, `confirm.py`, plus two inline scripts whose output is quoted in full
below). I did not call the author's `verify_gen1.py`, and I did not take the Gen 2 Builder's
account of anything.

**Not independent, and said plainly**:
- **Shared workspace.** I rendered the concepts from the author's own directory
  `magnet-ui-gen1\concepts`, not from a fresh copy of the `adm-` bytes. The four concept files
  attached to this request (`adm-7792bd18d276`, `adm-1016448ab480`, `adm-97ac18e7aff6`,
  `adm-58f5b7557241`) match their on-disk counterparts by recorded size; that is corroboration,
  not proof of byte identity.
- **I wrote the prior Gen 1 review** (`adm-7f611570e043`, Turn `ent-5aefa1594a60`) whose
  recommendation produced the selection I am now re-testing. This is a re-assessment by the same
  reviewer against a new criterion, not a second opinion on the first review. Weigh it as such.
- **Expert walkthrough, not user testing.** No human used any concept. Occupancy percentages and
  click paths are measurements; words like "unobtrusive" are judgements against the owner's own
  wording.
- **Static mockups.** Nothing here can demonstrate dragging, persistence of placement, or
  touch behaviour, because none of the six contains any code for them (§3.1).

---

## 2. What the two reference screenshots actually show

Both were read as images, not described from the post text.

**`adm-dbd6c1a4a636`** (`Screenshot 2026-10-30 233118.png`) — this is the **older compact yellow
Magnet**. Rendered: a small yellow/amber disc at the top-left of the working area, partly behind
the card, carrying a letter mark and a red **"50"** count badge; the surrounding workspace
(shelf, posts, a second object) continues around it. Opened beside it is a **compact dark card**,
roughly a third of the window: title **"Colony Island Three"**, the status line **"50 new since
you last opened it"**, provenance (**"From a conversation · active 3d ago · 50 new"**), a plain
statement that no synthesis exists, then two labelled collections — **"Posts 235 · All"** with
three previewed items, and **"Files 321 · All"** with two previewed filenames — and a single `×`
to dismiss. That card is, almost item for item, the owner's level 2: *"what it has collected,
such as posts, files, changes, summaries"*.

**`adm-7277383b759d`** (`image.png`) — two Magnets rendered as **small circular cores** (counts
`19` and `41`, the active one ringed in amber) each surrounded by a ring of small satellite
chips, with a caption beneath carrying status (**"Governance · 19 · 5 new"**, **"…MK4: manuals,
diagrams, notes · 41 · 25 new"**, **"4 d ago · 5 new · 1 changed"**). A **detached SUMMARY panel**
floats over the same space with its own small header controls (sort, contrast, `…`, `×`) and a
staleness banner: *"Inputs changed: 1 input it read was superseded or revised, and 29 new. It may
now say something untrue; the next Refresh offers Full."*

**Which is "the second"**: the post attaches `adm-dbd6c1a4a636` first and `adm-7277383b759d`
second, but the "older compact yellow Magnet" the owner names is unambiguously in
`adm-dbd6c1a4a636`. I have taken that image as the primary reference and have not relied on the
ordering.

**Their role.** The owner says the older design is "a reference, not a requirement to copy".
Read that way, the two images supply three things the Gen 1 set does not have: a **resting object
small enough to sit in the work** (a disc, a core with satellites), a **status vocabulary carried
on the object itself** (count, "n new", "1 changed", staleness), and a **dismissible card sized to
a fraction of the window** that lists collections rather than opening a workspace. They do not
dictate yellow, circles, or orbit layout.

---

## 3. Rendered evidence

### 3.1 Level 1 — a compact, movable resting object: absent in all six

Over all six concept files, the complete inventory of event listeners is:

```
30  addEventListener('click'    (tab/theme/viewport/state toggles)
 6  addEventListener('message'  (hub iframe switching)
```

Zero `drag`, `dragstart`, `mousedown`, `pointerdown`, `touchstart`, `hover` or `keydown`
listeners. Zero `draggable="true"` attributes, zero inline `ondrag*`/`onmousedown` attributes,
zero `cursor: grab|grabbing|move` declarations, zero writes to `style.transform|left|top`. The
string `drag` does not occur in any of the six files, in any case. **Nothing in Generation 1 can
be picked up, and nothing is drawn as an object that could be.**

The closest things that exist, measured:

| Concept | Smallest Magnet representation while the Conversation is visible | Size | Interactive? |
|---|---|---|---|
| C1 | inline Magnet card inside post #14 (`◉ Checkout Latency & Cache Watch` + bounded/matched status line) | 394×37 identity line in a ~620×105 attachment card | **no** — plain text, `tabIndex -1`, not a button |
| C3 | same inline card + a `Magnet Chat (9)` pill | 558×53 | pill only |
| C4 | same inline card, after closing the desk | 394×37 | **no** |
| C5 | same inline card, plus a trail crumb `2. Magnet (14)` | crumb 100×30 | crumb is a button |
| C6 | same inline card; sheet header strip carries identity + status | header strip 1440×47 | strip not activatable |
| C2 | none — the originating Conversation is not rendered at all | — | — |

The inline card does carry real status — `Bounded page 1 of 1 (200-entry cap) · 14 matched ·
complete corpus not claimed`, `2 new since P1·S3`, and in C4/C6 also `SRC-09 restricted`. That
is a **status vocabulary already fit for the resting object**; what is missing is an object to
put it on and the ability to place it.

### 3.2 Level 2 — hover / keyboard-focus card: absent in all six

I hovered and then programmatically focused **every** Magnet-bearing control ≤220×72 px in all
six concepts at both widths, comparing the full set of visible elements before and after.

- **No card appeared anywhere.** Every non-zero difference in the visible set corresponded to a
  scroll-into-view (`scrollY` 0 → 21 in C3, 0 → 2484 in C6) or to a hover colour change.
- **No concept contains a popover, tooltip, hover-card, flyout or `role="tooltip"` element at
  all.** The only class-name matches were C5's `c5-peek-edges` / `c5-peek`, which are the 13 px
  slivers of the stacked layers behind the front layer — stack edges, not cards.
- The only `:hover` rule in the six that changes anything beyond colour is C5's
  `:hover { opacity: 1; background: var(--accent-soft); }`.
- **Keyboard**: the inline Magnet card, the one element that carries collected status, is not
  focusable in any concept (`tabIndex -1`, no `role`). Desktop tab stops total 13–20 per concept;
  the Magnet-bearing stops among them are navigation buttons (`Magnet Chat (9)`, crumbs), and
  focusing them reveals nothing. There is therefore **no pointer/keyboard parity question to
  answer yet — neither path exists**.

### 3.3 Level 3 and "unobtrusive in a Conversation" — the one place the criterion discriminates

Cold load, `1440×900`, intersection with the first screen:

| Concept | Magnet surface at cold load | % of first screen | Originating Conversation | % of first screen |
|---|---|---|---|---|
| C3 (rejected) | `aside.c3-margin-col` 330×963 | **20.7 %** | article 1024×963 | **64.2 %** |
| C1 (baseline) | `aside.c1-inspector` 460×2148 | **28.8 %** | origin column 944×2148 | **59.1 %** |
| C5 (parent) | `div.c5-stack-wrap` 724×1833 | **41.7 %** | trail crumbs only, 1440×47 | **5.2 %** |
| C6 (parent) | `section.c6-sheet` 1440×1230 | **56.9 %** | origin band 1440×300 | **33.3 %** |
| C4 (parent) | `div.c4-desk` 1440×1614 | **65.6 %** | return bar only, 1440×49 | **5.4 %** |
| C2 (rejected) | `main.c2-center-wrap` 1404×2081 | **82.7 %** | return bar only, 1440×49 | **5.4 %** |

**Every concept opens its deep surface without being asked.** That is the drift the owner names.

But five of the six do have a closing control, and what it actually does differs sharply:

| Concept | Control | Desktop 1440×900 | Narrow 390×844 |
|---|---|---|---|
| **C4** | `← Return to Release Readiness — Checkout v4.2 (Post #14)` | **works** — `.c4-desk` → `display:none`; the Conversation renders at full measure with the inline Magnet card and an explicit **`Re-open Evidence & Inquiry Desk →`** | **works** — desk `display:none` |
| **C5** | trail crumb `1. Origin #14 (draft)` | **works** — layer 1 is the originating Conversation; the Magnet is reduced to the crumb `2. Magnet (14)` and the inline card offers **`Step into Layer 2: Magnet →`** | **works** — stack 2662 → 1535 px |
| **C6** | `Minimize / Return to Origin #14` | **no rendered change** — sheet 1440×1230 and `.c6-sheet-grid` `display:grid` before *and* after; the class `peek-origin` is applied but its three CSS rules exist only inside `@media (max-width:720px)` (lines 897–899) and `body.sim-narrow` (915–917) | **works** — sheet 3165 → 443 px, `.c6-sheet-grid` → `display:none`, origin band restored to 390×300 |
| **C1** | `← Origin` (`title`: "Toggle originating view on narrow screen") | no rendered change — `.show-origin` rules are likewise narrow-only (830–831, 837–838). By design: at desktop the Conversation is already beside the inspector | **works** — inspector `display:none`, origin column returns |
| **C2** | `← Return to Release Readiness…` | centre column 2081 → 926 px but still **82.7 %** of the first screen; the Conversation never returns | — |
| **C3** | none found | — | — |

So **level 3 exists in rendered form in C4 and C5 at both widths**, and in C1 and C6 only below
720 px. In C4 and C5 the returned state is close to what the owner describes at levels 1 and 3
minus the object: Conversation primary, Magnet reduced to a card inside the post that collected
it, with status chips and one explicit control that re-opens the deep surface.

---

## 4. The six, candidate by candidate, at the three levels

`✗` absent in rendered form · `~` partially present · `✓` present.

| | L1 resting compact movable object | L1 status | L2 hover / keyboard card | L3 explicit open | Unobtrusive in Conversation |
|---|---|---|---|---|---|
| **C4** parent, frozen yardstick | ✗ no object, no drag | `~` rich status, but on an inert inline card | ✗ | **✓ both widths, cleanest (`display:none`)** | ✗ at default (5.4 %) · ✓ after closing |
| **C5** parent | ✗ crumb is a breadcrumb, not a placeable object | `~` count only (`2. Magnet (14)`) + inline card | ✗ | **✓ both widths** (layer grammar identical at 390 px) | ✗ at default (5.2 %) · ✓ at layer 1 |
| **C6** parent | ✗ header strip is full-width chrome | `~` identity + `2 new since S3` + `SRC-09 restricted` on the strip | ✗ | `~` **narrow only — inert at desktop** | `~` best default of the parents (33.3 %) |
| **C1** baseline | ✗ | `~` inline card only | ✗ | `~` narrow only (by design) | **✓ best of the six in practice (59.1 %) with the Magnet visible as a card** |
| **C3** rejected | ✗ | `~` inline card + chat pill | ✗ | ✗ no close control | ✓ smallest magnet footprint of the six (20.7 %) |
| **C2** rejected | ✗ | ✗ | ✗ | ✗ close control does not restore the Conversation | ✗ worst (82.7 %); Conversation never rendered |

---

## 5. How the clarified criteria change the selection

**They do not change which concepts are parents.** Four points, each from §3:

1. **No candidate passes levels 1 or 2, so neither level can re-rank anything.** All six were
   authored before the clarification; a criterion that every candidate fails equally discriminates
   between none of them.
2. **The parents are where the lawful fix lives.** C4 and C5 are the only concepts in which the
   deep surface is already *dismissible at both widths*, leaving a Conversation-primary state with
   an inline Magnet card and an explicit re-open. Adding a resting object and a card to C4 or C5
   is a change of default state plus two new components — a correction. Doing the same to C2
   (whose close control leaves the Magnet at 82.7 %) would be a redesign.
3. **C1's preservation is now worth more than when it was recorded.** It is the one concept whose
   *default* already satisfies "unobtrusive while I am working in a Conversation" at desktop
   (59.1 % conversation, Magnet present as a card in the post that collected it). It is the right
   yardstick for the corrected candidates, not merely the conventional control.
4. **C3 and C2 stay rejected, and the clarification must not be read as reviving C3.** C3 has the
   smallest Magnet footprint of the six (20.7 %) and will look superficially like "the compact
   answer". It is not: it has **no** resting object, **no** card, **no** close control, and at
   390 px `aside.c3-margin-col` measures 0×0 — the margin collapses into an inline disclosure, so
   the structure that names the concept is not present where it is most needed (corroborating
   §3.5 of `adm-7f611570e043`). Its one virtue — never interrupting
   the originating article — is already recorded as hypothesis **H-4** for testing *inside a C6
   derivative*. That remains the lawful route.

**What does change is the yardstick.** The Gen 1 selection ranked concepts largely on the quality
of the opened surface (evidence clarity, composer continuity, width parity). The clarification
says the opened surface is the *exception*, not the default. Three consequences for the record:

- **C4's frozen-yardstick status should be read as "strongest deep surface", not "strongest
  design".** Against the clarified criteria C4's *default* is the second-worst of the six.
  Gen 3's comparison against C4 must therefore be stated as a comparison of opened surfaces.
- **C6's claim as the conversation-continuity parent is weaker at desktop than the Gen 1 review
  recorded.** It keeps the Conversation at 33.3 % — best of the three parents — but its minimize
  control, the only "put the Magnet away" affordance in the whole Gen 1 set, does nothing at
  1440 px. Its continuity result stands; its *resting* result does not.
- **C5's admission for width parity is reinforced.** Its layer grammar is the only one that
  behaves identically at both widths, and that is exactly the property the three-level grammar
  will need at 390 px, where a free-floating object is least workable.

---

## 6. Findings

All findings are **non-blocking against Generation 1**: the six were built and reviewed before
the clarification existed, so none of them "leaves out something the request required". F-1 to
F-3 would be **blocking against the running Gen 2 correction** (`opr-32f29a6cdf42`) if that
correction returned with them unmet, since its request names all three states explicitly.

| | Finding | Evidence | Blocking |
|---|---|---|---|
| **F-1** | No compact, movable resting Magnet object exists in any of the six; no drag machinery of any kind is present. | §3.1 — zero drag/pointer/mouse listeners, attributes, cursors or positional style writes across all six files; `drag` absent from every file. | not blocking (Gen 1) |
| **F-2** | No hover or keyboard-focus card exists in any of the six; the one element carrying collected status is not focusable. | §3.2 — no popover/tooltip component in any file; hover and focus over every Magnet control at both widths revealed nothing; inline card `tabIndex -1`. | not blocking (Gen 1) |
| **F-3** | All six render the deep surface at cold load, occupying 20.7 %–82.7 % of the first screen. | §3.3 table. | not blocking (Gen 1) |
| **F-4** | C6's `Minimize / Return to Origin #14` — the only minimize control in Gen 1 — has no rendered effect at 1440×900; its CSS is scoped to `max-width:720px`. | §3.3 — sheet and `.c6-sheet-grid` identical before/after; c6 lines 897–899, 915–917; no console error. | not blocking (cosmetic/scoped defect in a static mockup) |
| **F-5** | C2's return control leaves the Magnet at 82.7 % of the first screen and never restores the Conversation; its rejection is strengthened, not reopened. | §3.3. | not blocking |
| **F-6** | The status vocabulary the clarified level 1 needs already exists as rendered text (`14 matched`, `2 new since P1·S3`, `1 restricted item (SRC-09)`, `Bounded page 1 of 1`), but only inside an inert text block. This is reusable, not missing. | §3.1 table. | not blocking (observation) |

**Not checked, and not repaired**: I did not inspect, run or modify any Gen 2 artifact, the Gen 2
correction, the lineage experiment or any application source. I did not re-verify the Gen 1
review's T1–T8 results (they are unaffected by this criterion). I ran no assistive technology. I
made no Brain, activation or deployment change, and I asked no owner decision.

---

## 7. Required bounded corrections

These belong to the **already-running** Gen 2 correction (`opr-32f29a6cdf42`, Turn
`ent-d6220fe96fde`), whose brief already names the three states. I did not re-issue it. What this
review adds is what its **re-review must check**, and two items its brief does not yet name:

1. **The default must be the resting state.** Cold load of each corrected candidate shows the
   Magnet at rest and the deep surface absent from the DOM or `display:none` — not merely
   scrolled below the fold.
2. **Reuse the existing status vocabulary** (F-6) on the resting object rather than inventing a
   new one; it is already the shared scenario's own wording.
3. **Both levels of reveal, with parity.** The card must be reachable by pointer *and* by `Tab` +
   focus, with the same content; the resting object must be a real control (`button` or
   `role="button"`, in the tab order), which today's inline card is not.
4. **Keep the deep surface that was already earned.** C4's provenance columns, C6's destination-
   switching composer and C5's width-parity grammar are the reason these are the parents; the
   correction moves them behind an explicit open, it does not thin them.
5. **Placement shown, not claimed.** A static mockup cannot implement dragging; render the same
   candidate at three distinct resting placements and say in the artifact that drag, persistence
   and touch are unimplemented. A mockup that asserts "draggable" without rendering it should be
   marked as an unmet gap, not a demonstration.
6. **Fix or declare C6's narrow-only collapse (F-4).** Either extend `peek-origin` to desktop or
   state in the artifact that C6's resting state is narrow-only — otherwise the corrected C6 will
   look as though it already had level 3 at desktop.
7. **No revival.** C3's margin and C2's hub are not sources for the compact object; the source is
   the owner clarification `ent-93f00e5ef142`, and its lineage must be recorded as such.

---

## 8. Concrete evaluation criteria

Proposed for the Gen 2 re-evaluation and for Gen 3, so that "compact" is measured rather than
asserted. Each is checkable by a script over the rendered mockup; the Gen 1 column shows what
the current best does, so the bar is known to be reachable or known to be new.

| | Criterion | Measure | Pass | Best in Gen 1 |
|---|---|---|---|---|
| **E1** | Resting footprint | Rendered area of the Magnet's resting representation ÷ viewport area, cold load | ≤ 2 % at 1440×900 and ≤ 4 % at 390×844 | none — lowest is C3 at 20.7 % |
| **E2** | Resting status | Count of distinct status facts legible on the resting object without opening anything: collected total, new-since, restricted/attention, staleness | ≥ 3 of 4 | 3 (C4/C6 inline card + chips) — but on an inert block |
| **E3** | Conversation undisturbed | Reflow of the originating Conversation's column when the Magnet is at rest vs. absent | 0 px change in column width; no content displaced | C1 and closed-C4 render the card inside post #14 rather than in a column of its own (judged from the render; no Magnet-absent variant exists to difference against) |
| **E4** | Card on pointer | Hover the resting object → a card becomes visible within 400 ms, ≤ 25 % of viewport area, dismissible | yes | none |
| **E5** | Card on keyboard | Resting object reachable by `Tab`, has a visible focus ring, `Enter`/focus reveals the **same** card content as E4, `Esc` dismisses and returns focus | yes | none (object not focusable) |
| **E6** | Card content | Card names what was collected, by kind, with counts and ≥ 2 item previews per kind, plus available actions | ≥ 2 kinds with counts | none — but `adm-dbd6c1a4a636` shows the target exactly |
| **E7** | Explicit open only | Deep surface absent at cold load; reachable in exactly 1 action from the resting object; returns to rest in exactly 1 action | yes | C4 (1 action each way, both widths) |
| **E8** | Round-trip fidelity | After open → close, the Conversation's scroll position, anchor and unsent draft are unchanged | yes | C6 (verified draft round trip, §3.7 of `adm-7f611570e043`) |
| **E9** | Placement | Resting object rendered at ≥ 3 distinct placements in the working area; its coordinates survive an open/close cycle | demonstrated statically, drag declared unimplemented | none |
| **E10** | Width parity | All three levels exist at 390×844 with the same grammar, or the deviation is stated and justified | yes | C5 (identical grammar at both widths) |
| **E11** | Lineage honesty | Each corrected candidate names its Gen 1 parent, the inherited patterns, and cites `ent-93f00e5ef142` — not a rejected concept — as the source of the compact object | yes | n/a |

E1's threshold is set from the reference images, where the resting Magnet reads as a small disc
or ringed core with a badge — of the order of a post avatar, not a panel. It is a measurement
target, not a requirement to draw a yellow circle; the owner said the older design is a reference,
not a template.

---

## 9. Recommendation

1. **Keep the Gen 1 selection as recorded**: parents C4, C6, C5; C4 frozen; C1 preserved. The
   clarification gives no evidence for changing it and would not be served by changing it.
2. **Re-state C4's frozen role** in the record as *strongest Gen 1 deep surface*, so Gen 3's
   comparison against it is not read as a comparison of default experiences.
3. **Let the running Gen 2 correction stand**, and review its return against §8 E1–E11, with
   §7 items 1, 5 and 6 added to its checklist.
4. **Do not revive C2 or C3.** If the corrected candidates still fail E1–E6, the answer is
   another bounded correction of the same parents or an owner decision — not a new parent.
5. **Nothing is required from the owner on this report.** It is evidence for the carrier's next
   step, and the owner's decision boundary remains the one the experiment already defines.

---

## 10. Reproducing this review

From `C:\Work\Mentis-workspace\day-to-day\magnet-compact-review-reroute`, with the repository's
Python and Playwright Chromium:

```
python -I outline.py    # default-state layout outline  -> outline.json / outline.txt
python -I levels.py     # three-level probe, both widths -> levels.json / levels.txt, shots/
python -I confirm.py    # scroll-artefact, popover, C6 minimize checks -> confirm.json
```

Screenshots of every state quoted above are in `shots/`. The C6 minimize result is in
`shots/C6-desktop-after-minimize.png` (unchanged) and `shots/C6-narrow-after-minimize.png`
(collapsed); the C4 and C5 Conversation-primary states are in `shots/C4-desktop-after-return.png`
and `shots/C5-desktop-after-return.png`.
