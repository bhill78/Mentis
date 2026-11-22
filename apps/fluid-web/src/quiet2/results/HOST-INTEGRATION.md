# N-C → N-I: mounting the result opener in the shared hosts

For the sole integrator of `quiet2/Quiet2.tsx`, `quiet2/GlobalDock.tsx`, `work/api.ts`,
`api.ts` and `mentis/web/__init__.py` (handoff `adm-cf4f48b67620`, ownership table; focused
review `adm-9e2b5e85d81b` M1).

**Branch** `result-target-opener`, based on cumulative TEST `71b064703ffe8094cc391555ac1695e0dca60996`.
Nothing here edits a shared host.

## This is the fourth version of this hand-off, and what is left for the host is state

Independent review `adm-f3244dbc4bae` blocked the first version: its snippets did not compose.
The second version moved the host's **decisions** into `results/hostOpen.ts`, where they could be
checked, and left the **adapters** -- the code that calls those decisions against the page's own
viewer store, history hook and readers -- as TSX in this Markdown file. Re-review
`adm-263df1ccb512` executed those exact declarations and seven of them did not compose
(F09, F10, F12-F16, F19). Prose cannot fail a test, which is why it failed a review instead.

**So the adapters are code**: `results/mount.ts`. It calls the real
`viewer/viewers.ts`, the real `results/*` decisions, the real `openResultTarget` and the real
fresh read (`results/refRead.ts`). What is left for the shared hosts is the one thing they alone
have -- their React state -- which they hand over as one object, `ResultPage`.

Re-review `adm-d84456fd4c3c` then executed the composition itself, against the REAL `usePlaces`
and a real `popstate`, and blocked four things more. Three of them were still **order and wiring
left to prose in this file**, and the lesson was taken a step further: each is now a call
`mount.ts` makes, not a line the integrator has to put in the right place.

| Re-review finding | What was wrong in version 3 | Where it is answered now |
| --- | --- | --- |
| **B4.1** | the fresh read was optional host wiring, by the REQUEST a Needs you row was drawn from; a chooser, Brain-record or Latest press had no request, so it was `unchecked` and the old descriptor was placed -- and a 401, an offline failure or an answer that no longer named the reference were `unchecked` too. The delayed open also ran only when an optional `settled` observer had been registered | `refRead.ts` `artifactNow` over the existing `GET /api/artifacts/<ref>?describe=1`, on EVERY artifact open and fail-closed; `opener.ts` completes the open and reports separately |
| **B4.2** | `if (R.applyCentre(to)) return` was documented as the apply callback's FIRST line, so `centreAt.current = to` never ran for a result entry and the close could not tell that it owned the entry | `ResultPage.enterCentre`, which `mount.ts` `applyCentre` calls before it decides anything |
| **B4.3** | `backTo` was wired straight to `centre.backTo`, and `centreHistory` marks the pop it makes as already asked -- so a maximised close walked the history, restored the Place and gave up the viewer with no question asked and nothing for Stay to keep | `ResultPage.backTo(place, then, stay)`; `mount.ts` `closeResult` passes a Stay that does nothing, and `hostOpen.ts` drops the second conversation press so one close asks once |
| **B4.4** | resuming a saved result called the ordinary open, which pushed a SECOND entry in front of the one being resumed: Back came straight back and resolved it afresh, for ever | `mount.ts` `hostFor('current')`: the entry the browser is standing on is corrected in place (`centreReplace`), never pushed |
| N3 (nonblocking) | every viewer-frame close was routed through `R.closeResult`, and an ordinary maximised picture -- which registers no result -- lost the baseline's return to its own post | `hostOpen.ts` `closeSteps` emits `{do:'reveal'}` for an unregistered maximised post-sourced viewer; `ResultPage.reveal` |

Re-review `adm-efb406a34e7a` then blocked the B4.4 correction's own timing, and confirmed two
nonblocking defects as reproducible. All three are answered in this part's own modules; **no host
member changed**, so an integrator who has already applied this file's wiring applies nothing new.

| Re-review finding | What was wrong in version 4 | Where it is answered now |
| --- | --- | --- |
| **B4.4-R1** (blocking) | a resume corrected "the entry the browser is standing on" -- read again when its READ answered. Forward onto a saved result, then Back, then the read: the Place Back had reached was replaced and a viewer drawn over it. `acceptsLate` passed, because leaving a result entry begins no opening | `mount.ts` `centreGeneration`/`Resume`/`holds`: a pending resume is bound to the entry, the centre generation and the Brain key it landed with, and is dropped -- silently, placing and replacing nothing -- at its read, its chooser answer and its entry write if any of the three has moved |
| N2 (nonblocking, confirmed) | the registry row was forgotten by the guarded history move's own leave arm (F16) before `runClose` read `results.invokerOf(viewer)`, so `{how:'invoker'}` arrived with `null` and nothing was focused | `mount.ts` `closeResult` reads the invoker ONCE, with the plan, and carries it; the choice is decided at the focus step against the element actually there, so a restore that unmounted the invoker falls through to the control and then the launch's fallback |
| N5 (nonblocking, confirmed) | `refRead.ts` checked a `ref` that was present and accepted a held body carrying none | identity is REQUIRED: `body.ref !== ref` is `gone`. The route answers `ref` on every state it answers (`mentis/artifacts.py` `describe`) |

## This is the sixth version, and it is the one that CHANGES A HOST MEMBER

Re-review `adm-af5263a65134` passed B4.4-R1, N2 and N5 and every earlier named probe, and then
blocked the Brain identity **this file itself supplied**. The modules were asking the right
question; the wiring was answering it with the wrong key, from the wrong place. So the host
member changes -- by being TAKEN AWAY: which Brain the server serves is not one render's state,
and asking a page for it is the defect, not the wiring of the ask.

| Re-review finding | What was wrong in version 5 | Where it is answered now |
| --- | --- | --- |
| **F1** (blocking) | `brainKey: () => brain.key ?? null` is built INSIDE the host component, so it closes over THAT RENDER's `brain`. A pending read and an open chooser belong to the render that began them, and that render's getter went on answering with the Brain that render saw. Construct a new mount for a new Brain WITHOUT moving the centre -- the only thing the generation counts -- and `holds` compared the old key with itself: the old instance's result was placed in a column of a page now showing another Brain | `results/serving.ts` `servingBrainKey()`: one module read of `brainBinding.ts`'s page binding, which is a MODULE store, so the oldest closure and the newest press read the same answer. `mount.ts` calls it itself at every gate -- `holds` for the read, for the chooser and for the entry write, and `OpenerHost.brainKey` as a GETTER so the opener's own re-entry after a fresh read checks it again -- and a page that has moved answers `null`, so nothing late is placed |
| **F2** (blocking) | that same member supplied `brain.key`, the 3D Brain's GRAPH key (`space/registry.ts` `spaceBrainKey`: origin, pinned proxy choice, corpus id). Two serving instances of one corpus at one origin have exactly that key, so a result saved against the instance that was replaced or restored resumed against the new one. `launch.ts` has always documented its `BrainKey` as `<corpus>@<instance>` -- `brainBinding.ts`'s key, which this page already names in every write it makes | the two keys are two members and never one string. `ResultPage.spaceKey` is the graph key and is used for one thing only: the `ViewerSource` of a file that came from the Brain rather than from a post (`OpenerHost.spaceKey`, `targets.ts` `sourceOf`). The serving identity is `serving.ts`'s, and is what every launch, history entry and resume is judged by. **No graph key, key constructor or space contract changes**: the graph key is not wrong, it was being asked the wrong question |

**What an integrator who has already applied version 5 changes**: two lines in §1.2 and one import
(below). Nothing else in this file, and nothing in `GlobalDock.tsx`, moves.

| Re-review finding | What was wrong in version 2 | Where it is answered now |
| --- | --- | --- |
| **B1 / F04** | the delayed branch of the fresh read opened whatever the callback answered, without comparing it with the requested identity | `opener.ts` `sameThing`, applied on BOTH branches |
| **B3 / F09** | `record:` returned `'completed'` while `enterBrain`'s `guarded` question was still open | `mount.ts` `guardedMove`, and `ResultPage.record(entry, go, stay)` |
| **B4 / F10** | `sourceSteps` emitted `park` and `parkViewer` refused anything but the 3D Brain, so a maximised artifact stayed over its own source post | `viewers.ts` `parkViewer(id, 'kept')`; `mount.ts` `goToSource` |
| **B4 / F12** | the history entry's target was derived from the `ViewerSource`, recording the source post as the result | `FileOpen.target` (the opener carries `d.target`); `mount.ts` `identityOf` |
| **B4 / F13** | the `resolve` arm ignored `resumeSteps`' `back` Place and launched from wherever the reader was | `mount.ts` `launchForSaved` |
| **B4 / F14** | frame-only close restored the launch's Place as well as closing, while the return bar claimed to be the way back | `hostOpen.ts` `closeSteps`: frame-only is `[focus, forget]` |
| **B4 / F15** | the close ran `pickConversation` and then closed regardless, so a pending guard lost the viewer and Stay kept neither | `mount.ts` `runRestore`/`runClose`: everything after the move runs inside the move's success |
| **B4 / F16** | the centre's `apply` handled only `to.result`, leaving the old file maximised over the Place just navigated to | `hostOpen.ts` `leaveSteps`; `mount.ts` `applyCentre`'s other arm |
| **B4 / F19** | `read:` was wired to `inspectRef` in `needs/inspect.ts`, which does not exist and has no route | `refRead.ts` `refNow`, over the route that does exist |
| N2 (nonblocking) | `applyFocus` used the module-global `openedBy`, which the newest open overwrites | `ResultPage.focus(choice, invoker)`: the closing viewer's own invoker, from the registry. Recorded as discovered work; it is simply not reachable through the replaced adapter |

Every one of those falsifiers is reproduced against this composition in
`tests/quiet2_result_mount_unit.{ts,mjs}`, and the three about the host's own history are run
against the REAL `usePlaces`/`useCentreHistory` and a synthetic `popstate` in
`tests/quiet2_result_history_unit.{ts,mjs}` -- **including the exact wrappers below, extracted
from this file and executed**, so a wrapper that stops composing fails a test rather than a
review. Each correction has been checked by undoing it and watching its own case fail.

## 0. What this part provides

| Module | What it decides |
| --- | --- |
| `quiet2/results/targets.ts` | what a result points at; the server's availability/`opens` words; whether a thing can be opened at all; the commit identity; the external-URL policy; source as against launch; `destinationOfRef` |
| `quiet2/results/launch.ts` | where the reader was (any Place); Brain identity including instance; which read may still act; which launches are still live |
| `quiet2/results/serving.ts` | which Brain the SERVER is serving this page now (`<corpus>@<instance>`, from `brainBinding.ts`), read when it is asked and `null` once the page has moved |
| `quiet2/results/history.ts` | which transitions enter the centre's history (only maximised); one entry per displacement; what a close does; what landing on a result entry again does |
| `quiet2/results/opener.ts` | `openResultTarget(destination, launch, host, now?)`: the one host operation, what actually happened, and what happened later (`settled`) |
| `quiet2/results/hostOpen.ts` | the host's own moves as decisions: the file adapter's reading, the placed-viewer registry, the close sequence, go-to-source, landing on an entry again, leaving one, restoring a Place, and what the dock does with each answer |
| **`quiet2/results/mount.ts`** | **the adapters themselves**: `mountResults(page)` returns the operations the host calls |
| **`quiet2/results/refRead.ts`** | **the fresh read on the press**, through the route this build serves |
| `quiet2/viewer/viewableOfItem.ts` | which renderer a file opens in, from the server's verified word |
| `quiet2/viewer/viewers.ts` | `parkViewer(id, keeping)` -- additive: `'kept'` parks a viewer the page has kept a way back to. Every existing call means exactly what it meant |
| `quiet/media/view.ts` | `ViewerItem.treatment` (additive), `DRAWN_BYTES`, `cutWords`, `FRAME_REFUSES` |
| `quiet/media/MediaLayer.tsx` | the bounded-reading and frame-refusal disclosure, beside the existing download |
| `quiet2/address.ts` | `CentreAt` gains the optional `result` arm |
| `quiet2/places.ts` | `centre.backTo(place, then)` -- one step back to a whole Place, the conversation included |

Tests: `tests/quiet2_result_{targets,opener,viewable,host,mount}_unit.{ts,mjs}`, each `.ts` in
`tsconfig.test.json`'s `include` (the one line in that file other parts also add to).

## 1. `Quiet2.tsx`

### 1.1 Imports

```tsx
import { EXTERNAL_LINK, actionOf, destinationOfRef, openable, type ResultDestination } from './results/targets'
import { beginOpening, holdLaunch, type DecisionLaunch, type LaunchContext, type LaunchFocus, type LaunchPlace } from './results/launch'
import { mountResults, type ResultPage } from './results/mount'
import { servingBrainKey } from './results/serving'
import type { Opened } from './results/opener'
import { postSource } from './viewer/types'
import { picturesOf } from './Post'                 // N-B owns it; §3.2
```

`heldItem` (line 51), `postOf` (line 78), `moveViewer`, `closeViewer`, `openViewer` and
`inColumn` (line 35) are already imported by the baseline. `parkViewer`, `parkedPlaceOf`,
`returnViewer`, `maximised` and `viewerOf` are called by `mount.ts` itself: the host does not
need them for this.

### 1.2 The page, handed over once (B2, B3, B4)

One object, inside the component, built from the state the page already has. Nothing in it
decides anything: each member is a function the baseline has, with the unsaved-work guard's
three ends made explicit, because reporting a pending guard as an arrival is what B3 was.

```tsx
  /* WHERE THE READER IS NOW, as a launch: identity and position only. */
  const launchNow = (focus: LaunchFocus, decision?: DecisionLaunch | null): LaunchContext => holdLaunch({
    opening: beginOpening(),
    /* WHICH BRAIN THE SERVER SERVES, ASKED NOW -- `<corpus>@<instance>` from
       the binding every write already names (`brainBinding.ts`), NOT
       `brain.key`, which is the 3D Brain's graph key and is the same string
       for two serving instances of one corpus at one origin (F2). */
    brainKey: servingBrainKey(),
    place: { conversation: realId, centre: centreAt.current },
    thread: entered ? { root: entered, at: enteredAt } : null,
    reading: { scroll: document.querySelector<HTMLElement>('.q2-conv')?.scrollTop ?? 0, offset: left.current?.offset ?? null },
    reply: replyTo?.id ?? null,
    draft: mainPlace,                  // THE KEY (line 1156), never the text
    focus, decision: decision ?? null,
  })

  const resultPage: ResultPage = {
    /* THE GRAPH KEY, AND ONLY FOR THE VIEWER'S SOURCE (F2). `brain.key` is
       `spaceBrainKey(origin, proxy, corpus)`; it is what a `ViewerSource`
       holds, and it is the one place a result still needs it. There is NO
       `brainKey` member any more: the Brain this page's results are decided
       against is read from `brainBinding.ts` by `mount.ts` itself, because a
       render's own closure cannot answer for a page that has been rebound
       since (F1). A host literal that still carries `brainKey` stops
       compiling, which is the intended way to find it. */
    spaceKey: () => brain.key ?? null,
    origin: () => location.origin,
    conversation: () => realId,
    centreAt: () => centreAt.current,
    /* THE PAGE'S OWN TRACKER, SET BY WHOEVER APPLIES THE ENTRY (B4.2). The
       baseline's line 721 (`centreAt.current = to`) moves here, and
       `R.applyCentre` calls it before it decides anything -- so the result arm's
       early return cannot leave the tracker on the Place underneath, which is
       what made every maximised result look frame-only to its own close. */
    enterCentre: (to) => { centreAt.current = to },
    columns: () => surfacePanes as ('s1' | 's2')[],
    freeColumn: () => surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s]) ?? null,
    choose: (ask) => setChoosing(ask),
    invoker: () => document.activeElement as HTMLElement | null,
    hasControl: (control) => !!document.querySelector(`[data-control="${CSS.escape(control)}"]`),
    /* THE CLOSING VIEWER'S OWN INVOKER is handed in (N2): never `openedBy`,
       which the most recent open overwrites. */
    focus: (choice, invoker) => {
      if (choice.how === 'invoker') { (invoker as HTMLElement | null)?.focus(); return }
      if (choice.how === 'control') { document.querySelector<HTMLElement>(`[data-control="${CSS.escape(choice.control)}"]`)?.focus(); return }
      focusFallback(choice.fallback)        // 'latest' | 'decision' | 'item' | 'conversation'
    },
    centreGo: (at) => centre.go(at),
    centreReplace: (at) => centre.replace(at),
    /* THE RETURN IS A CENTRE MOVE, SO IT IS ASKED ABOUT FIRST (B4.3).
       `centreHistory` marks the pop this makes as already asked -- correctly,
       because a move the page asked for was guarded by the control that asked
       for it. That control is this one. `then` is the rest of the close and
       runs only once the move has been applied; `stay` keeps the viewer, its
       launch and the reader's place, because nothing has been left. */
    backTo: (place, then, stay) => guarded(() => centre.backTo({ c: place.conversation, at: place.centre }, then), CENTRE, stay),
    pickConversation: (k, then, stay) => pickConversation(k, then, stay),
    openPost: (c, p, done) => openFromDock(c, p, done),
    /* GUARDED LIKE EVERY OTHER CENTRE MOVE (F09): `go` only once the record
       page is actually shown, `stay` where the reader kept what they had. */
    record: (entry, go, stay) => guarded(() => {
      setBrainReturn(null)
      centre.go({ brain: { stack: [{ page: 'record', entry }], origin: { from: 'link' } } }, go)
    }, CENTRE, stay),
    goToPost: (c, p) => now.current.goToPost(c, p),
    /* THE BASELINE VIEWER FRAME'S OWN CLOSE, for the viewers this contract
       never registered (N3): an ordinary maximised picture goes back to the
       post it was drawn in, exactly as line 1424 did. */
    reveal: (post) => requestAnimationFrame(() => revealPost(post)),
    heldItem: (ref, about) => heldItem(ref, about),
    postOf: (post) => postOf(post) ?? null,
    pictures: (post) => picturesOf(post as Parameters<typeof picturesOf>[0]),
    destinationOfTarget,                   // N-B's adapter; omit until it lands
    putBack: (step) => {
      if (step.do === 'thread') { setEntered(step.root); setEnteredAt(step.at); return }
      if (step.do === 'reading') { const pane = document.querySelector<HTMLElement>('.q2-conv'); if (pane) pane.scrollTop = step.scroll; return }
      if (step.do === 'reply') { setReplyTo(step.post ? postOf(step.post) ?? null : null); return }
      /* 'draft': the composer is pointed at this place again; the draft store
         (experimental/draftKeep.ts) already holds what was typed under it. */
    },
    offerReturn: (l) => setResultReturn(l),
    leaveOn: (place) => { if (place.conversation && place.conversation !== realId) pickConversation(place.conversation); else centre.replace(place.centre) },
    external: (href) => !!window.open(href, EXTERNAL_LINK.target, EXTERNAL_LINK.rel),
    say: setNotice,
  }
  const R = mountResults(resultPage)
```

`setResultReturn` is the explicit return bar's own state -- one `useState<LaunchContext | null>`
beside `brainReturn` (line 660), drawn like the existing record-return pill (line 1715) and
dismissed the same way. `focusFallback` is the page's own: four `querySelector().focus()` lines,
one per `FocusFallback` kind.

**There is no Brain identity to wire either** (F1, F2). `mount.ts` reads
`results/serving.ts` `servingBrainKey()` itself, at every gate that names a Brain, exactly as it
calls the fresh read itself: `brainBinding.ts`'s page binding is a module store, so an old
render's pending read or open chooser sees today's answer rather than the one its own render
closed over -- and a page that has moved to another Brain has NO current key (`null`), so a saved
result is not resumed and a late answer is not placed. The one thing the host still supplies is
`spaceKey`, the graph key, for the viewer's source. `launchNow` above is the host's own
`holdLaunch` call and so names the serving key explicitly; a host that would rather not can call
`R.launchNow(…)`, which does it itself.

**There is no read to wire** (B4.1). The fresh read on the press is `results/refRead.ts`'s own
`artifactNow`, over `GET /api/artifacts/<exact ref>?describe=1` through `fluidFetch`: it needs
nothing a page has, so `mount.ts` calls it itself, on every explicit artifact open, from whatever
surface. A press with no request behind it -- the result chooser, a Brain record's file, the
Latest list -- is checked exactly like a Needs you press. That is also why **every artifact open
is now asynchronous**: `R.openResult(…)` answers `{what:'leaving',how:'file'}` on the press and
the outcome reaches `settled` (`dockStep` is `wait` meanwhile, which is the rule §2 already
uses). `ResultPage.artifactNow` exists only so a check can inject its own server.

Three small patches the page members above need, each with its own reason:

```tsx
  /* 1. A GUARD THE READER ANSWERED WITH STAY IS AN ANSWER (B3). `guarded`
        (line 782) already has the shape; `setLeave` already takes `stay`
        (line 673, used at 752). */
  const guarded = (go: () => void, place: Place = CENTRE, stay?: () => void) => {
    const was = leaving(unfinished(place))
    if (was.ask) { setLeave({ ask: was.ask, go, stay }); return }
    if (was.note) setNotice(was.note)
    go()
  }

  /* 2. `pickConversation` (line 1907) passes a cancellation through. */
  const pickConversation = (k: string, then?: () => void, stay?: () => void): boolean => {
    /* … unchanged … */
    guarded(() => arrive(k, then), CENTRE, stay)
    return true
  }

  /* 3. `openFromDock` (line 1819) and `showPost` (line 1852) say which of
        their three ends they reached. `pendingPost` carries the callback. */
  const openFromDock = (conversation: string, post?: string, done?: (n: Navigation) => void) => {
    const here = isReal && content === 'real' && conversation === realId
    if (here) {
      if (brainMain || sourceMain || brainOpen || sourcesOpen) {
        pickConversation(conversation, post ? () => showPost(conversation, post, done) : () => done?.('completed'), () => done?.({ how: 'cancelled' }))
        return
      }
      if (post) { showPost(conversation, post, done); return }
      done?.('completed'); return
    }
    if (!pickConversation(conversation, post ? undefined : () => done?.('completed'), () => done?.({ how: 'cancelled' }))) { done?.('failed'); return }
    if (post) pendingPost.current = { conversation, post, done }
  }
  const showPost = (conversation: string, post: string, done?: (n: Navigation) => void) => {
    if (document.querySelector(`.q2-conv [data-post="${post}"]`)) { revealPost(post); done?.('completed'); return }
    const ask = ++asking.current
    void threadRootOf(conversation, post).then(async (root) => {
      await readThread(conversation, root)
      if (ask !== asking.current || now.current.realId !== conversation) { done?.({ how: 'cancelled' }); return }
      now.current.page.onEnter(root, post)
      done?.('completed')
    }).catch(() => { if (ask === asking.current) setNotice('That post could not be read.'); done?.({ how: 'failed', why: 'That post could not be read.' }) })
  }
```

`pendingPost` (line 1843) becomes `useRef<{ conversation: string; post: string; done?: (n: Navigation) => void } | null>(null)`,
and its effect (1844-1849) passes `want.done` into `showPost`.

### 1.3 What the page then calls

| Where | Baseline | Now |
| --- | --- | --- |
| the chooser's three buttons (2071-2078) | `openViewer` + `placeIn` by hand | `choosing.decide('s1' \| 's2' \| 'max')`, and `choosing.decide('cancelled')` for Cancel, the veil and Escape |
| `fileFromDock` (1814) | `heldItem` + `onView`, Brain hardcoded as the source | `R.openResult(destinationOfRef({ id: entry, type: 'file', available: !!about && about.state === 'held', state: about?.state ?? 'not-held', opens: 'file', file: about ?? null }), launch ?? launchNow({ control: `needs-ref:${entry}`, fallback: { kind: 'conversation' } }), settled)` |
| the viewer frame's `close` (1424) | `closeViewer` then `revealPost(post)` | `R.closeResult(v.id)` -- for a result AND for an ordinary picture: `closeSteps` keeps the baseline's reveal for a viewer nothing registered (N3), through `ResultPage.reveal` |
| the viewer frame's `toSource` (1426-1430) | move-or-refuse, then `revealPost` | `post ? () => R.goToSource(v.id, { conversation: post.conversation ?? realId!, post: post.post }) : null` |
| the centre's `apply` (718) | `brain` / `source` / `space` arms | the callback below: `R.applyCentre(to)` handles a result entry and -- on every other entry -- takes a maximised result off the centre (F16) before the page's own arms run. It records the entry through `enterCentre` before it decides, so its early return skips only the page's *rendering* arms (B4.2) |

The apply callback, whole, because its ORDER is what B4.2 was. Everything after
`R.applyCentre(to)` is the baseline's lines 722-742 unchanged; what moved is line 721, into
`enterCentre`:

```tsx
  const applyCentre = (to: CentreAt, from: CentreAt, how: How, asked: boolean) => {
    /* the page's own capture, before anything else: leaving the conversation,
       where it was read is kept, once (baseline 720) */
    if (!from && to) brainLeft.current = document.querySelector<HTMLElement>('.q2-conv')?.scrollTop ?? null
    /* A RESULT ENTRY IS THIS PART'S. `applyCentre` records the entry through
       `enterCentre` FIRST, whatever it is, so nothing below can leave the
       page's own tracker behind (B4.2); then it either handles the entry, or
       takes a maximised result off the centre and leaves the rest to us. */
    if (R.applyCentre(to)) return
    setUnread(null)
    if (!keepBrainCard.current) setBrainOpen(false)
    setSourcesOpen(!!to?.sources)
    if (to?.sources) { setSourcesWanted(true); if (how !== 'replace') sourcesRead.reload() }
    const fromSpace = spaceRef.current.apply(to?.space, how)
    setBrainMain(to?.brain ?? fromSpace ?? null)
    setSourceMain(to?.source ?? null)
    if (to?.source) { setSourcesWanted(true); if (to.source.view.page === 'source') setSourceLast(to.source.view.col) }
    if (how === 'pop' && !asked && !to && from) {
      if (from.brain && from.brain.stack.length === 1 && from.brain.origin.from === 'browser') setBrainOpen(true)
    }
  }
```

The existing `usePlaces` call (line 718) then takes `apply: applyCentre`, and nothing else about
it changes: its `show`, `ask`, `unask` and `address` are the baseline's.

`choosing` (line 594) becomes the chooser's own state: `useState<ColumnChoice | null>(null)`.
Nothing else about it changes. A result opened in a column is `historyStep(…) === 'none'`: no
`CentreAt`, no entry, no `guarded` (H1), and `mount.ts` is what keeps that true.

The baseline's own `onView` (1392) stays exactly as it is for everything that is not a result
(a picture pressed in a post, a block the renderer drew). A result goes through `R.openResult`,
which places the viewer, registers it and writes its one history entry itself.

## 2. `GlobalDock.tsx` -- the dock's own reference opening

The `Openers` type (line 76) gains the three operations the dock presses:

```tsx
interface Openers {
  record: OpenRecord
  file: OpenFile
  /** where the reader is, as a launch: the dock has the decision identity */
  launch: (focus: LaunchFocus, decision?: DecisionLaunch | null) => LaunchContext
  /** the one operation; `settled` is told if it finishes after the press */
  open: (d: ResultDestination, launch: LaunchContext, settled?: (o: Opened) => void) => Opened
  /** whether this page has a route for it at all */
  has: (d: ResultDestination) => boolean
}
```

Both `useMemo<Openers>` blocks (lines 886 and 969) add `launch: launchNow`, `open: R.openResult`
and `has: R.has`. `NeedsItemRow` (lines 266-280) then routes through the one operation, and arms
its way back only where the reader actually left:

```tsx
  const leaving = useCallback((ref: string, opened: string, launch?: LaunchContext) => {
    if (remember) leaveFor({ item: it.key, ref, what: name, opened, decision: it.kind === 'decision' })   // §3.1: launch, once S-D takes it
  }, [remember, it.key, name, it.kind])
  const can: CanOpen = useCallback((r) => { const d = destinationOfRef(r); return openable(d).can && openers.has(d) }, [openers])
  const open: OpenRefFn = useCallback((r: Ref) => {
    const d = destinationOfRef(r)
    if (!openable(d).can || !openers.has(d)) return false
    const launch = openers.launch({ control: `needs-ref:${r.id}`, fallback: { kind: 'decision', item: it.key } },
      { form: about?.form ?? null, question: askOf(it), item: it.key, ref: r.id, role: r.relation ?? null })
    /* ONE RULE, ONE PLACE: `dockStep` says whether the way back is owed now,
       owed when the answer comes, or not owed at all. A new tab, a cancelled
       placement, a Stay at the guard and a failed read all leave this panel,
       this row and this draft exactly as they are. */
    const act = (o: Opened) => { if (dockStep(o) === 'arm') leaving(r.id, refName(r, 60), launch) }
    const done = openers.open(d, launch, act)
    act(done)
    return pressed(done)
  }, [it, about, openers])
```

The launch's `question` (`askOf(it)`, above) is the dock's own identity for the row, its form and
its draft -- it is **no longer** what the fresh read reads by. The read is the artifact's own
description and happens for every artifact press, here and everywhere else (B4.1), so this row is
checked no more and no less than one pressed from the chooser.

A row pressed here therefore answers `{what:'leaving'}` on the press and `arm`s only when
`settled` says `opened`. `act(done)` above already does exactly that, which is why nothing in
this block changes for it.

`NeedsAbout.tsx`'s `if (!r.opens || !r.available || !can(r))` keeps its shape. A form's row still
lands at its exact block (`landAtBlock`): keep that call where it is, after `dockStep(done) === 'arm'`.

Two things the dock must NOT do, both already true of the baseline:

- it must not listen to `popstate`: browser Back never reopens Needs you (H4). The explicit
  pill is the only way back.
- the external arm must not close the panel. `openers.open` answers `{ what: 'external' }`, for
  which `dockStep` is `keep`, so `close(false)` must not be called on that path.

## 3. Dependencies on other parts

1. **S-D / the Needs You adapter owns `needs/about.ts`.** `Leave` must gain the launch and the
   question identity for the pill to restore the Place and the pending item together (focused
   review M2.3). The call site above already has the launch in hand and passes it as a third
   argument that is currently dropped -- one line changes in §2 when S-D lands. Until then the
   pill restores the panel only. **This is the one part of H4 that cannot be met inside N-C's files.**
2. **N-B owns `Post.tsx`.** `viewableOf(i, post)` should become `viewableOfItem(i, picturesOf(post))`.
   `picturesOf` is imported unchanged and is only ever called with a post that exists
   (`hostOpen.ts` `siblingsOf`). N-B also owns `destinationOfTarget`; until it exists, leave that
   member out and a result entry whose viewer has gone offers its saved Place and says so
   (`mount.ts` `applyCentre`, tested).
3. **N-A owns `work/contract.ts`.** A `ResultDestination` is built from its wire shape by the
   chooser (N-B), not by this module.
4. `tsconfig.test.json`'s `include` is one line several parts add to; keep every part's entries.

## 4. What is not done here, and why

- **No rendered or browser check of any of this.** The modules are not mounted: the two files
  that would mount them are the integrator's. V1-V5, H1-H8 and every falsifier above are
  checked as code against the real stores (`tests/quiet2_result_mount_unit.ts` is a
  representative host: a complete `ResultPage` with a real guard) and against the real history
  hook with a synthetic `popstate` (`tests/quiet2_result_history_unit.ts`), not as rendered
  behaviour. **A final combined rendered review remains mandatory after mounting.**
- **A4/P4 is met for artifacts, and only for artifacts.** Every explicit artifact open is
  described again on the press, from every surface, and fails closed (B4.1). The other routes --
  a post, a record, a conversation -- keep their existing guarded readers and are not read again;
  the record route's own availability is still what the row was drawn with. That part of A4/P4
  stays open, and is recorded rather than claimed.
- **Availability is not authority.** The description says what the server holds for this reader
  now; the bytes are still read, and still refusable, when the viewer asks for them. A renderer
  that fails afterwards does not make the answer wrong, and nothing here adds or changes a
  permission.
- **`Presented.Primary` anchors.** The focus contract covers them; the markup is S-D's. The
  `data-control` attribute is the one thing each of those controls needs.
- **The Brain identity is checked as code, and is still not MOUNTED** (F1, F2). The gates, the
  module read and the two wiring lines above are executed in
  `tests/quiet2_result_{serving,mount,history}_unit.ts` -- the last of those against the exact
  expressions extracted from THIS file, with two render-scoped `ResultPage` objects over one
  real history, as the re-review's own probes did. What is NOT shown: a real `useBrain` rebind,
  a real server switching the Brain it serves, a real 409 `BrainChanged`, or any of it in a
  browser. `brainBinding.ts` itself is unchanged and its own suite still covers it.
- **`servingBrainKey()` is null before the page binds.** Quiet Chat binds on its first
  `confirmBrain`, and a page that has not yet bound (or that could not be told) names no Brain:
  a launch made then carries `null`, which `brainVerdict` reads as `unknown`, so its saved entry
  is not resumed later. That is the same fail-closed direction as everywhere else here, and it
  is a deliberate difference from `brain.key`, which is available immediately. Fluid pages, which
  never bind, open results exactly as they did -- with no Brain named and so none compared.
- **No permission, renderer-security, Magnet or Presets change.** `HtmlFrame`'s sandbox, the CSP,
  `prose.tsx`'s `safeHref` and `/api/worker` are untouched. Nothing here reads bytes: `heldItem`
  and the page's own inspection read are the only readers, under the grant they already have.
