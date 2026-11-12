# Findings U: the `@Caretaker` pill and the `Caretaker · local ›` summary (before any change)

Read from `composer-pills` at 62a67e4 (`apps/fluid-web/src/fluid/Composer.tsx`, `composer/Operations.tsx`,
`composer/drafts.ts`, `composer/choose.ts`, `composer/words.ts`) and driven headless in Chromium against
this clone's own build on :8797 over the rehearsal Brain copy (`C:\Work\Mentis-Test-Server\r2-release\brain`),
conversation `ent-0a1a163beb3a` (Mentis UI/UX, where @Caretaker and @Builder both take part). Script:
`C:\Work\Mentis-workspace\composer-local\u-run\pw\explore2.py`; screenshots `evidence-U\before-*.png`.
Nothing was sent.

## What each control is

Both live on the composer's one header line in Quiet Chat Mark 2 (`Composer` mounted with `operations`).

**The pill (`.fc-chip`)**, one per addressee in `draft.to`, drawn after "Posting to …":
- Its name button opens (or closes, if already open) Operations for **that** participant
  (`setOpened(a.participant)`), and makes it the summary's subject (`setLead`). Verified: clicking
  `@Builder` opened "Operations · @Builder".
- Its `×` removes only that addressee from `draft.to` (and closes Operations if it was theirs). The
  addressee object carries all its settings, so they go with it. The `@Caretaker` text stays in the
  words (unchanged behaviour; `retextualise` only drops addressees whose name left the text, it never
  re-adds one).
- Visible text is only the alias; the settings are in its `aria-label` (`tokenOf`: runtime, model,
  effort, Persona, new, coordinates, side work, permission · execution). Warnings are not visible on it.
- Accent background when asked to work (`.working`).

**The summary (`.fc-sum`, `margin-left: auto`)**, exactly one, at the right end:
- Speaks for ONE addressee: the last one opened (`opened ?? lead`), else the first asked to work, else
  the first addressed. With @Caretaker and @Builder addressed it said "Caretaker · any runtime" (for
  @Caretaker) until @Builder's pill was clicked, then switched to @Builder. After a reload `lead` is
  forgotten and it went back to @Caretaker.
- Click opens Operations for that one participant: the same panel the pill opens (verified: same
  "Operations · @Builder" header).
- Shows Persona (bold), runtime, model, effort, and in attention colour only non-defaults: "coordinates",
  Permission Mode short ("routine", "allow all", "never waits"), Execution Mode short ("host", "sandboxed")
  when chosen. Verified: Caretaker set to routine -> "Caretaker, any runtime, routine".
- Carries the **Alt+O** shortcut (composer `onKeyDown`): opens Operations for whoever the summary speaks
  for. Verified from the text box: Alt+O opened "Operations · @Caretaker".

## Same participant? Same state?

Yes. Both read and write the same object: `draft.to[i]` (an `Addressee`). Operations' `onChange`
replaces that participant's entry in `draft.to`. Neither control holds settings of its own; the only
extra state is the component's `opened` (which panel is open) and `lead` (whom the summary describes),
both in memory only.

## Two addressees

The data model already keeps per-participant settings: each `Addressee` holds runtime, model, effort,
persona, newInstance, coordinate, consent (mode, workspaces, extra), followUp, executionMode and its
acknowledgement. Verified: @Builder set to codex and @Caretaker to Permission "routine" stayed separate
(sessionStorage draft: Caretaker `consent:{mode:task}`, Builder `runtime:codex`). The summary can show only
one of the two; the other's warnings were visible nowhere except in its pill's aria-label.

## Draft persistence

`drafts.ts` keeps the whole draft (text and `to` with every per-participant setting) in an in-memory map
and in `sessionStorage` (`mentis:fluid:draft:conversation:<id>`) for the tab. Verified: after reload both
pills, Caretaker's "routine" and Builder's "codex" were back. `lead`/`opened` are not kept.

## Keyboard (before)

- Tab order on the header line: pill name -> its x -> next pill -> its x -> summary -> text box.
- Enter/Space on a pill or the summary opens Operations (native button); focus goes to the first row.
- Esc closes a pull-out first (back to its row), then the panel; **focus then went to the text box, not to
  the pill that opened it** (verified: `document.activeElement` = "write a post").
- `@` in the words opens the address palette; Enter picks.

## Compactness (before)

Header line 24px tall at 1440x900 (composer 146px); at 390x844 the line was 37.7px because "Posting to
this conversation" wrapped, and the summary was cut to "co... >" with only one pill fitting.

## Does the summary do anything the pills cannot?

Three things, all preservable through the pills:
1. **Visible warnings** (coordinates / Permission / Execution non-defaults): move onto each pill, in the
   attention colour, compactly. Each addressee's warnings then show, not only one's.
2. **Alt+O**: keep. It opens Operations for the last-opened pill, else the first asked to work, else the
   first addressed (the same rule), now without a summary.
3. **A visible reading of Persona/runtime/model** for one addressee: the one thing removed as a visible
   label. It remains one Enter away (the pill opens Operations, whose rows say it), and in each pill's
   title/accessible name (`tokenOf`). Nothing else depends on it.

The summary configures nothing the pill's Operations does not, so it can go.

## After (composer-pills 2abcdfe + 294a8bf), verified in Chromium

`evidence-U\after-results.json` (37/37 checks, 0 page errors; script `evidence-U\verify.py`):
pills on the right of the line, each opens its own participant's Operations; @Caretaker
(antigravity, as themselves, may coordinate, routine, Sandboxed) and @Builder (codex, Reviewer, does
this work only, never waits, Unrestricted Host accepted) kept apart on reopen and after reload;
removing @Caretaker by keyboard left @Builder's settings exactly as they were and moved focus to
@Builder's pill; Esc returns focus to the pill; Enter/Space open; Alt+O opens the pill last opened;
@ addressing by keyboard still works and a re-addressed participant starts with no settings; split
send unchanged ("Ask 2 people" + caret, same four menu rows as before). Warnings on pills:
@Caretaker "coordinates · routine", @Builder "never waits · host" in the attention colour.
Header line: desktop 24 -> 22px (composer 146 -> 144); phone, two pills, 75.4 -> 56.5px (composer
231.4 -> 212.6). Model pull-out against a stubbed /api/execution: every model listed by exact id,
loaded / installed / "can't use tools" / unavailable (dimmed) / "refused: <why>" (dimmed), nothing for
unknown, the partial-list line; the real (older) catalogue shows none of it; choosing stored the exact slug.
