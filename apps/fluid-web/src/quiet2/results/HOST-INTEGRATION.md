# N-C → N-I: mounting the result opener in the shared hosts

For the sole integrator of `quiet2/Quiet2.tsx`, `quiet2/GlobalDock.tsx`, `work/api.ts`,
`api.ts` and `mentis/web/__init__.py` (handoff `adm-cf4f48b67620`, ownership table; focused
review `adm-9e2b5e85d81b` M1).

**Branch** `result-target-opener`, based on cumulative TEST `71b064703ffe8094cc391555ac1695e0dca60996`.
Nothing here edits a shared host. Every snippet below is written against the baseline's own
lines and names, so it can be applied by hand on top of whatever the Needs You carrier and the
activity package have changed in the same files. No line-based patch file is supplied
deliberately: `origin/needs-decision-ui` is still moving `GlobalDock.tsx`, so a diff against
this baseline would be stale before it was applied.

## This is the second version of this hand-off

Independent review `adm-f3244dbc4bae` blocked the first one, and was right to: its snippets did
not compose into the behaviour they described. **What the integrator was being asked to design,
this part now implements and tests.** The host supplies only what it alone has -- its viewer
store, its history hook, its readers -- and `results/hostOpen.ts` says what to do with them, in
order, as checked decisions (`tests/quiet2_result_host_unit.ts`, 59 checks).

| Review finding | What was wrong in the first hand-off | Where it is answered now |
| --- | --- | --- |
| **B1** | `heldItem(/* ref */ '', file as never)` threw the Admission away, so the viewer read `/api/artifacts/`; and `picturesOf(postOf(…) ?? undefined)` reads `post.blocks` for every file whose source is not a drawn post | `hostOpen.ts` `fileContent` / `siblingsOf`, called in §1.6 |
| **B2** | `onView` was given no launch, so the viewer returned to a launch the host made for itself; and `holdLaunch` deleted every other live launch, so the first of two viewers lost its live return | `FileOpen.launch` (`opener.ts`), `launch.ts` retention + `placedLaunch`, `hostOpen.ts` `resultViewers`, called in §1.3–§1.5 |
| **B3** | `post:`/`record:`/`conversation:` answered `true` the moment they were *asked*, so a pending guard, a Stay and a failed thread read were all reported as departures | `Navigation` and `settled` (`opener.ts`), the adapters in §1.5, `dockStep` in §2 |
| **B4** | required lifecycles (close order, zero-column source, Back/Forward, cross-conversation restore, fresh read, dock type) were prose, placeholders or names that do not exist | §1 and §2 in full; `closeSteps`, `sourceSteps`, `resumeSteps`, `restoreSteps`, `OpenerHost.read` |
| N1 (nonblocking) | a free column was reported as the literal `'s1'` | §1.3 returns the column it actually used; also recorded as discovered work |

Three names the first hand-off used **do not exist in the baseline** and are gone from this one:
`composerKey` (the draft key is `mainPlace`, line 1156), `targetOfViewer` and `openedMax` (the
registry in §1.2 answers both), and `isBehindPlace` (§1.7 explains why nothing needs it).
`opened` is already taken at line 758 (`addressOf(…, opened, …)`), so the focus map here is
part of the registry rather than a second binding of that name.

## 0. What this part provides

| Module | What it decides |
| --- | --- |
| `quiet2/results/targets.ts` | what a result points at; the server's availability/`opens` words; whether a thing can be opened at all; the commit identity; the external-URL policy; source as against launch; `destinationOfRef` for a reference `fluid/inspect.py` already resolved |
| `quiet2/results/launch.ts` | where the reader was (any Place); Brain identity including instance; which read may still act; **which launches are still live** — a placed viewer's way back outlives every later press (B2) |
| `quiet2/results/history.ts` | which transitions enter the centre's history (only maximised); one entry per displacement; what a close does; what landing on a result entry again does |
| `quiet2/results/opener.ts` | `openResultTarget(destination, launch, host, now?)`: the one host operation, what actually happened, and **what happened later** (`settled`) |
| `quiet2/results/hostOpen.ts` | **the host's own moves, as decisions**: the file adapter's reading, the placed-viewer registry, the close sequence, go-to-source, landing on an entry again, restoring a Place, and what the dock does with each answer |
| `quiet2/viewer/viewableOfItem.ts` | which renderer a file opens in, from the server's verified word |
| `quiet/media/view.ts` | `ViewerItem.treatment` (additive), `DRAWN_BYTES`, `cutWords`, `FRAME_REFUSES` |
| `quiet/media/MediaLayer.tsx` | the bounded-reading and frame-refusal disclosure, beside the existing download |
| `quiet2/address.ts` | `CentreAt` gains the optional `result` arm; a result is addressed as the Place it is over |
| `quiet2/places.ts` | **`centre.backTo(place, then)`** — one step back to a whole Place, the conversation included. Added by this part (it is not one of the five host files): `back` moves within `c.current`, which cannot return to a result opened in another conversation. Four lines, using the hook's own `h.back`. |

Tests: `tests/quiet2_result_targets_unit.{ts,mjs}`, `tests/quiet2_result_opener_unit.{ts,mjs}`,
`tests/quiet2_result_viewable_unit.{ts,mjs}`, `tests/quiet2_result_host_unit.{ts,mjs}`, and the
four `.ts` added to `tsconfig.test.json`'s `include` (the one line in that file another part is
also likely to touch).

## 1. `Quiet2.tsx`

### 1.1 Imports

```tsx
import { EXTERNAL_LINK, actionOf, destinationOfRef, openable, type ResultDestination } from './results/targets'
import {
  BRAIN_MOVED, beginOpening, holdLaunch, launchOf,
  type DecisionLaunch, type FocusChoice, type LaunchContext, type LaunchFocus,
} from './results/launch'
import { historyStep, resultIntent, resumeResult, type Shown } from './results/history'
import { openResultTarget, type Navigation, type Opened, type OpenerHost, type Placed } from './results/opener'
import {
  closeSteps, dockStep, fileContent, pressed, resultViewers, resumeSteps, sourceSteps,
  type CloseStep, type PlaceStep,
} from './results/hostOpen'
import { parkViewer, parkedPlaceOf, returnViewer } from './viewer/viewers'   // already exported
import { postSource } from './viewer/types'
import { picturesOf } from './Post'                                          // N-B owns it; §3.2
```

`heldItem` (line 51), `postOf` (line 78), `moveViewer`, `closeViewer`, `openViewer` and
`inColumn` (line 35) are already imported by the baseline.

### 1.2 The registry, beside the existing module store (B2)

The baseline keeps one module-global for who opened the last thing:

```tsx
let openedBy: HTMLElement | null = null        // line 470
```

It stays — `SpaceStage` takes it at line 2062 — and the results get a store of their own, in
the same place and the same style as `viewer/viewers.ts`:

```tsx
/** EVERY RESULT VIEWER THE PAGE PLACED, and the launch each one owes its
 *  reader. A later press never takes an open viewer's way back (B2). */
const results = resultViewers()
```

That is the whole of `opened`, `viewerLaunch`, `targetOfViewer` and `has` from the first
hand-off: `results.place/moved/launchOf/targetOf/whereOf/invokerOf/viewerOf/forget`.

### 1.3 One opening, with a launch (H6, B2, N1)

```tsx
  /** WHERE THE READER IS NOW, as a launch: identity and position only. */
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
```

and `onView` (line 1392) gains the launch, returns where it went, and **registers every
successful placement**:

```tsx
  const onView = (content: Viewable, source: ViewerSource,
                  launch = launchNow({ control: null, fallback: { kind: 'conversation' } }),
                  settled?: (p: Placed) => void): Shown | 'choosing' => {
    openedBy = document.activeElement as HTMLElement | null
    if (!surfacePanes.length) {
      const id = openViewer(content, source, 'max')
      results.place(id, launch, targetOf(source), 'max', openedBy)
      centre.go(resultIntent(brain.key ?? null, launch.opening, results.targetOf(id)!, launch.place))
      return 'max'
    }
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s])
    if (free) {
      const id = openViewer(content, source, free)
      results.place(id, launch, targetOf(source), free, openedBy)
      return free                      // THE COLUMN IT WENT IN, not the literal 's1' (N1)
    }
    setChoosing({ content, source, launch, settled })
    return 'choosing'
  }
```

`targetOf(source)` is the host's one line for the result's identity, from the source it already
has: `(s: ViewerSource) => (postSource(s) ? { kind: 'post', conversation: postSource(s)!.conversation ?? realId!, post: postSource(s)!.post } : null)`.
A null target is fine: the registry keeps the launch either way, and only a maximised result
needs a target for its history entry.

A column is `historyStep(…) === 'none'`: no `CentreAt`, no entry, no `guarded` (H1).

### 1.4 The chooser reports the column the reader picked (B3, B4 last item)

`choosing` (line 594) carries the launch and the opener's callback:

```tsx
  const [choosing, setChoosing] = useState<{ content: Viewable; source: ViewerSource; launch: LaunchContext; settled?: (p: Placed) => void } | null>(null)
```

and each of its three buttons (lines 2071–2078) says what became of it — this is the only path
that arms the dock's way back on a placement that succeeded *after* the press:

```tsx
  onClick={() => { const id = openViewer(choosing.content, choosing.source, 'max'); placeIn(id, s)
                   results.place(id, choosing.launch, targetOf(choosing.source), s, openedBy)
                   choosing.settled?.({ how: 'completed', where: s }); setChoosing(null) }}
  /* maximise */
  onClick={() => { const id = openViewer(choosing.content, choosing.source, 'max')
                   results.place(id, choosing.launch, targetOf(choosing.source), 'max', openedBy)
                   centre.go(resultIntent(brain.key ?? null, choosing.launch.opening, results.targetOf(id)!, choosing.launch.place))
                   choosing.settled?.({ how: 'completed', where: 'max' }); setChoosing(null) }}
  /* Cancel, the veil and Escape */
  onClick={() => { choosing.settled?.({ how: 'cancelled' }); setChoosing(null) }}
```

### 1.5 The one host, with honest answers (B1, B2, B3)

```tsx
  /** THE PAGE'S OWN READERS, and nothing new. Each navigation says whether it
   *  has only BEGUN, and reports what became of it when it knows (B3). */
  const resultHost: OpenerHost = {
    brainKey: brain.key ?? null,
    origin: location.origin,
    /* B1: the exact Admission, and a post's pictures only where there is a post */
    file: (o) => {
      const read = fileContent(o, { item: heldItem, post: postOf, pictures: picturesOf })
      if ('why' in read) { setNotice(read.why); return null }
      return onView(read.content, read.source ?? { kind: 'brain', brainKey: brain.key! }, o.launch, o.settled)
    },
    /* B3: guarded, asynchronous, and reported when it is actually done */
    post: (c, p, settled) => { openFromDock(c, p, settled); return 'requested' },
    conversation: (c, settled) => {
      if (!pickConversation(c, () => settled('completed'), () => settled({ how: 'cancelled' }))) return 'failed'
      return 'requested'
    },
    /* the record page is a state change, and is finished on the press */
    record: (entry) => { enterBrain({ page: 'record', entry }, { from: 'link' }); return 'completed' },
    external: (href) => !!window.open(href, EXTERNAL_LINK.target, EXTERNAL_LINK.rel),
    /* A4/P4: read again on the explicit open, through the page's existing
       bound reader. Nothing here reaches bytes: it is the inspector's own
       availability answer, for this Brain, under the existing grant. */
    read: (ref, settled) => {
      void inspectRef(ref).then((r) => settled(r ? { how: 'fresh', destination: destinationOfRef(r) } : { how: 'gone', why: 'Mentis does not hold its contents now.' }))
        .catch(() => settled({ how: 'gone', why: 'It could not be read now.' }))
      return { how: 'reading' }
    },
    say: setNotice,
  }
  /** what the dock, the chooser and Needs you all press. */
  const openResult = (d: ResultDestination, launch: LaunchContext, settled?: (o: Opened) => void) =>
    openResultTarget(d, launch, resultHost, { settled })
```

`inspectRef` is the page's existing single-reference inspection read (`needs/inspect.ts`); where
the integrator prefers not to add a second read on the press, **omit `read:` entirely** — the
opener then behaves exactly as it did before (`unchecked`), and A4/P4 stays open rather than
being claimed.

Three small patches the adapters above need, each with its own reason:

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
and its effect (1844–1849) passes `want.done` into `showPost`.

### 1.6 The dock's file open (B1)

Baseline (line 1814) hardcodes the Brain as the source and wraps every item as a plain file:

```tsx
  const fileFromDock = isReal && brain.key ? (entry: string, about: Parameters<typeof heldItem>[1]) => {
    const item = heldItem(entry, about)
    if (item) onView({ kind: 'file', item }, { kind: 'brain', brainKey: brain.key! })
    else setNotice('That file cannot be opened: Mentis does not hold its contents.')
  } : undefined
```

Replace with the shared opener, which chooses the renderer from the server's own word (so a PDF
opened from Needs you reaches pdf.js, and a picture its collection) and keeps the post as the
source where the reference names one:

```tsx
  const fileFromDock = isReal && brain.key
    ? (entry: string, about: Parameters<typeof heldItem>[1], launch?: LaunchContext, settled?: (o: Opened) => void) =>
        openResult(
          destinationOfRef({ id: entry, type: 'file', available: !!about && about.state === 'held', state: about?.state ?? 'not-held', opens: 'file', file: about ?? null }),
          launch ?? launchNow({ control: `needs-ref:${entry}`, fallback: { kind: 'conversation' } }),
          settled)
    : undefined
```

### 1.7 Close, and Go to source, are different actions (B3, B4, H2, H3, H7)

Baseline (lines 1424–1430) closes first and jumps to the post the bytes came from:

```tsx
      close: () => { closeViewer(v.id); if (v.place === 'max' && post) requestAnimationFrame(() => revealPost(post.post)) },
      toSource: post ? () => {
        if (v.place === 'max' && v.from && surfacePanes.includes(v.from)) moveViewer(v.id, v.from)
        else if (v.place === 'max') { setNotice('Close the viewer to return to the post it came from; it stays open until then.'); return }
        requestAnimationFrame(() => revealPost(post.post))
      } : null,
```

Replace with the two sequences. **The order is the point**: nothing is given up before the
restore that depends on it has run, so a reader who answers the unsaved-work guard with Stay
keeps the viewer, its draft and its way back (H7).

```tsx
      close: () => {
        const plan = closeSteps({ viewer: v.id, where: v.place === 'max' ? 'max' : (v.place as Shown), launch: results.launchOf(v.id) },
          { owns: !!centreAt.current?.result && centreAt.current.result.opening === results.openingOf(v.id),
            conversation: realId, invoker: results.invokerOf(v.id), has: hasControl })
        const run = () => { for (const step of plan.then) runClose(step) }
        if (plan.history) centre.backTo({ c: plan.history.to.conversation, at: plan.history.to.centre }, run)
        else run()
        if (plan.bar) setResultReturn(results.launchOf(v.id))     // the explicit return bar
      },
      /* GO TO SOURCE IS NOT CLOSE, and with no column it is no longer a dead
         end: the viewer PARKS -- kept, with its renderer's state -- so the
         post is actually on screen (H3). */
      toSource: post ? () => {
        for (const step of sourceSteps({ where: v.place === 'max' ? 'max' : (v.place as Shown), from: v.from },
                                       { conversation: post.conversation ?? realId!, post: post.post },
                                       { columns: surfacePanes })) {
          if (step.do === 'to-column') moveViewer(v.id, step.column)
          else if (step.do === 'park') { parkViewer(v.id); results.moved(v.id, 'none') }
          else now.current.goToPost(step.conversation, step.post)
        }
      } : null,
```

with the two small helpers the steps name:

```tsx
  /** whether a control with this stable identity is drawn now (focusChoice) */
  const hasControl = (control: string) => !!document.querySelector(`[data-control="${CSS.escape(control)}"]`)
  const runClose = (step: CloseStep) => {
    if (step.do === 'forget') { closeViewer(step.viewer); results.forget(step.viewer); return }
    if (step.do === 'focus') { applyFocus(step.choice); return }
    for (const p of step.place) runPlace(p)                   // the launch's own Place
  }
  /** PUTS THE READER BACK, and restores a draft BY ITS KEY, never its text. */
  const runPlace = (p: PlaceStep) => {
    if (p.do === 'conversation') { pickConversation(p.conversation); return }
    if (p.do === 'centre') { centre.replace(p.at); return }
    if (p.do === 'thread') { setEntered(p.root); setEnteredAt(p.at); return }
    if (p.do === 'reading') { const pane = document.querySelector<HTMLElement>('.q2-conv'); if (pane) pane.scrollTop = p.scroll; return }
    if (p.do === 'reply') { setReplyTo(p.post ? postOf(p.post) ?? null : null); return }
    /* 'draft': the composer is pointed at this place again; the draft store
       (experimental/draftKeep.ts) already holds what was typed under it. */
  }
  const applyFocus = (c: FocusChoice) => {
    if (c.how === 'invoker') { openedBy?.focus(); return }
    if (c.how === 'control') { document.querySelector<HTMLElement>(`[data-control="${CSS.escape(c.control)}"]`)?.focus(); return }
    focusFallback(c.fallback)        // 'latest' | 'decision' | 'item' | 'conversation'
  }
```

**Nothing needs `isBehindPlace`.** `centreHistory`'s `back` is already both of `closePlan`'s
moves: it steps back where the Place is the entry directly behind (`isBehind`, line 62) and
otherwise this entry *becomes* the Place. So the host asks for one move it cannot get wrong, and
`closeSteps` reports `bar: true` only for the third case — navigation has since left this entry,
and the explicit return bar is what owes the reader their way back.

### 1.8 Landing on a result entry again (H2, H8, B4)

In the `centre` `apply` callback (line 718 onward), beside the existing `brain` / `source` /
`space` arms:

```tsx
    if (to?.result) {
      const resume = resumeResult({ result: to.result }, { brainKey: brain.key ?? null, live: (o) => !!launchOf(o), words: BRAIN_MOVED })
      for (const step of resumeSteps(resume, results)) {
        if (step.do === 'show-viewer') {
          /* THE SAME VIEWER, SHOWN AGAIN -- never a second one. A parked
             viewer comes back through `returnViewer`, which is what the
             viewer store already does for the graph. */
          const was = parkedPlaceOf(step.viewer)
          if (was) returnViewer(step.viewer, was.place, was.from)
          else if (step.where !== 'max') moveViewer(step.viewer, 'max')
          results.moved(step.viewer, 'max')
        } else if (step.do === 'resolve') {
          /* after a reload, or after it was closed: the target is resolved
             again through the one operation, with that Place as the way back */
          openResult(destinationOfTarget(step.target), launchNow({ control: null, fallback: { kind: 'conversation' } }))
        } else if (step.do === 'say') setNotice(step.words)
        else centre.replace(step.place.centre)
      }
      return
    }
```

`destinationOfTarget` is the chooser's own adapter (N-B) for turning a stored `ResultTarget`
back into a destination; until it exists, the `resolve` arm may show the Place and the return
bar alone — which is honest, and is what `resumeSteps` asks for. A Forward into another Brain
instance's entry is refused here, which is the H5 `brainBinding` rule applied to history rather
than a second one.

## 2. `GlobalDock.tsx` — the dock's own reference opening

The `Openers` type (line 76) gains the two operations the dock now presses, in full:

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

Both `useMemo<Openers>` blocks (lines 886 and 969) add `launch: launchNow`, `open: openResult`
and `has: (d) => hasRoute(d)` — where `hasRoute` is one line in the host: `actionOf(d) === 'file' ? !!fileFromDock : actionOf(d) === 'post' ? true : …`.

`NeedsItemRow` (lines 266–280) then routes through the one operation, and **arms its way back
only where the reader actually left**:

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

`NeedsAbout.tsx`'s `if (!r.opens || !r.available || !can(r))` keeps its shape — it already shows
`r.why` for the unopenable case, which is the behaviour this contract wants. A form's row still
lands at its exact block (`landAtBlock`), which the post arm of `openers.open` does not replace:
keep that call where it is, after `dockStep(done) === 'arm'`.

Two things the dock must NOT do, both already true of the baseline and worth keeping:

- it must not listen to `popstate`: browser Back never reopens Needs you (H4). The explicit
  pill is the only way back.
- the external arm must not close the panel. `openers.open` answers `{ what: 'external' }`, for
  which `dockStep` is `keep`, so `close(false)` must not be called on that path. In the baseline
  `openers.record`/`openers.file` call `close(false)` before the outward call; that stays right
  for a real open and must not be extended to the URL arm.

## 3. Dependencies on other parts

1. **S-D / the Needs You adapter owns `needs/about.ts`.** `Leave` must gain the launch and the
   question identity for the pill to restore the Place and the pending item together (focused
   review M2.3): `leaveFor({ …, launch: LaunchContext })`, with `DecisionLaunch` as this
   contract defines it. The call site above already has the launch in hand and passes it as a
   third argument that is currently dropped — one line changes in §2 when S-D lands. Until
   then the pill restores the panel only, which is the sibling baseline's behaviour, not this
   round's property. **This is the one part of H4 that cannot be met inside N-C's files.**
2. **N-B owns `Post.tsx`.** `viewableOf(i, post)` should become
   `viewableOfItem(i, picturesOf(post))`; the local PDF test (`/pdf/i.test(i.mediaType)`) is
   what `isPdf` replaces. `picturesOf` is imported unchanged by §1.5 and is only ever called
   with a post that exists (`hostOpen.ts` `siblingsOf`), so nothing of N-B has to change for
   this part to mount. N-B also owns `destinationOfTarget` for §1.8's `resolve` arm.
3. **N-A owns `work/contract.ts`.** A `ResultDestination` is built from its wire shape by the
   chooser (N-B), not by this module: `targets.ts` names no HTTP field.
4. `tsconfig.test.json`'s `include` is one line that several parts will add to; expect a
   trivial conflict there and keep every part's entries.

## 4. What is not done here, and why

- **No rendered or browser check of any of this.** The modules are not mounted: the two files
  that would mount them are the integrator's, so nothing in a browser exercises them yet.
  V1–V5 and H1–H8 are checked as decisions (the pure rules above and
  `tests/quiet2_result_host_unit.ts`), not as rendered behaviour. N-D's acceptance on the
  combined candidate is where they become observed, and the review's own words stand: a final
  combined rendered review remains mandatory after mounting.
- **A4/P4 is supplied, not claimed.** `OpenerHost.read` is the fresh bound read, with a tested
  `gone`/`fresh`/`reading`/`unchecked` decision; whether the host wires `inspectRef` to it is
  the integrator's call, and the opener says plainly which of the two it is doing.
- **`Presented.Primary` anchors.** The focus contract covers them (`focusChoice` takes any
  control identity, and a `fallback` of `{ kind: 'decision' }`), but the markup is S-D's. The
  `data-control` attribute `hasControl` looks for is the one thing each of those controls needs.
- **No permission, renderer-security, Magnet or Presets change.** `HtmlFrame`'s sandbox, the
  CSP, `prose.tsx`'s `safeHref` and `/api/worker` are untouched; the only new words about the
  frame say what it already refuses. Nothing here reads bytes: `heldItem` and the page's own
  inspection read are the only readers, under the grant they already have.
