# N-C → N-I: mounting the result opener in the shared hosts

For the sole integrator of `quiet2/Quiet2.tsx`, `quiet2/GlobalDock.tsx`, `work/api.ts`,
`api.ts` and `mentis/web/__init__.py` (handoff `adm-cf4f48b67620`, ownership table; focused
review `adm-9e2b5e85d81b` M1).

**Branch** `result-target-opener`, based on cumulative TEST `71b064703ffe8094cc391555ac1695e0dca60996`.
Nothing here edits a shared host.

## This is the third version of this hand-off, and the adapters are now code

Independent review `adm-f3244dbc4bae` blocked the first version: its snippets did not compose.
The second version moved the host's **decisions** into `results/hostOpen.ts`, where they could be
checked, and left the **adapters** -- the code that calls those decisions against the page's own
viewer store, history hook and readers -- as TSX in this Markdown file. Re-review
`adm-263df1ccb512` executed those exact declarations and seven of them did not compose
(F09, F10, F12-F16, F19). Prose cannot fail a test, which is why it failed a review instead.

**So the adapters are code now**: `results/mount.ts`. It calls the real
`viewer/viewers.ts`, the real `results/*` decisions, the real `openResultTarget` and the real
bound read (`results/refRead.ts`). What is left for the shared hosts is the one thing they alone
have -- their React state -- which they hand over as one object, `ResultPage`.

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
`tests/quiet2_result_mount_unit.{ts,mjs}` (95 checks), and each correction has been checked by
undoing it and watching its own case fail.

## 0. What this part provides

| Module | What it decides |
| --- | --- |
| `quiet2/results/targets.ts` | what a result points at; the server's availability/`opens` words; whether a thing can be opened at all; the commit identity; the external-URL policy; source as against launch; `destinationOfRef` |
| `quiet2/results/launch.ts` | where the reader was (any Place); Brain identity including instance; which read may still act; which launches are still live |
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
import { refNow } from './results/refRead'
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
    brainKey: brain.key ?? null,
    place: { conversation: realId, centre: centreAt.current },
    thread: entered ? { root: entered, at: enteredAt } : null,
    reading: { scroll: document.querySelector<HTMLElement>('.q2-conv')?.scrollTop ?? 0, offset: left.current?.offset ?? null },
    reply: replyTo?.id ?? null,
    draft: mainPlace,                  // THE KEY (line 1156), never the text
    focus, decision: decision ?? null,
  })

  const resultPage: ResultPage = {
    brainKey: () => brain.key ?? null,
    origin: () => location.origin,
    conversation: () => realId,
    centreAt: () => centreAt.current,
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
    backTo: (place, then) => centre.backTo({ c: place.conversation, at: place.centre }, then),
    pickConversation: (k, then, stay) => pickConversation(k, then, stay),
    openPost: (c, p, done) => openFromDock(c, p, done),
    /* GUARDED LIKE EVERY OTHER CENTRE MOVE (F09): `go` only once the record
       page is actually shown, `stay` where the reader kept what they had. */
    record: (entry, go, stay) => guarded(() => {
      setBrainReturn(null)
      centre.go({ brain: { stack: [{ page: 'record', entry }], origin: { from: 'link' } } }, go)
    }, CENTRE, stay),
    goToPost: (c, p) => now.current.goToPost(c, p),
    heldItem: (ref, about) => heldItem(ref, about),
    postOf: (post) => postOf(post) ?? null,
    pictures: (post) => picturesOf(post as Parameters<typeof picturesOf>[0]),
    /* A4/P4: the read that exists, by the request the row was drawn from. Omit
       this line and the opener is `unchecked`, exactly as before the contract. */
    refNow: (ask, ref) => refNow(ask, ref),
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
| the viewer frame's `close` (1424) | `closeViewer` then `revealPost(post)` | `R.closeResult(v.id)` |
| the viewer frame's `toSource` (1426-1430) | move-or-refuse, then `revealPost` | `post ? () => R.goToSource(v.id, { conversation: post.conversation ?? realId!, post: post.post }) : null` |
| the centre's `apply` (718) | `brain` / `source` / `space` arms | `if (R.applyCentre(to)) return` as the FIRST line of the callback: it handles a result entry, and -- on every other entry -- takes a maximised result off the centre (F16) before the page's own arms run |

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

**The launch's `question` is what the fresh read reads by** (`askOf(it)`, above): with it, the
press re-reads that request through `refNow`; without it the opener is `unchecked`. So this is
the line that makes A4/P4 real for Needs you, and the only place it is real.

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
  representative host: a complete `ResultPage` with a real guard), not as rendered behaviour.
  **A final combined rendered review remains mandatory after mounting.**
- **A4/P4 is supplied for the dock's own presses, and said plainly elsewhere.** There is no
  single-reference read route in this build: `refNow` re-reads the REQUEST a row was drawn from.
  A press with no request behind it (the chooser, a Brain record, the Latest list) answers
  `unchecked`, which is the behaviour before this contract existed, and A4/P4 stays open there.
- **`Presented.Primary` anchors.** The focus contract covers them; the markup is S-D's. The
  `data-control` attribute is the one thing each of those controls needs.
- **No permission, renderer-security, Magnet or Presets change.** `HtmlFrame`'s sandbox, the CSP,
  `prose.tsx`'s `safeHref` and `/api/worker` are untouched. Nothing here reads bytes: `heldItem`
  and the page's own inspection read are the only readers, under the grant they already have.
