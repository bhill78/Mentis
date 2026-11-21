# N-C → N-I: mounting the result opener in the shared hosts

For the sole integrator of `quiet2/Quiet2.tsx`, `quiet2/GlobalDock.tsx`, `work/api.ts`,
`api.ts` and `mentis/web/__init__.py` (handoff `adm-cf4f48b67620`, ownership table; focused
review `adm-9e2b5e85d81b` M1).

**Branch** `result-target-opener`, based on cumulative TEST `71b064703ffe8094cc391555ac1695e0dca60996`.
Nothing here edits a shared host: this is what the hosts must call, written as diffs against the
baseline's own lines so they can be applied by hand on top of whatever the Needs You carrier and
the activity package have changed in the same files. No line-based patch file is supplied
deliberately: `origin/needs-decision-ui` is still moving `GlobalDock.tsx` (it was `e4b54a8d`
when this work began and `adbbf825` an hour later), so a diff against this baseline would be
stale before it was applied.

## What this part provides

| Module | What it decides |
| --- | --- |
| `quiet2/results/targets.ts` | what a result points at; the server's availability/`opens` words; whether a thing can be opened at all; the commit identity; the external-URL policy; source as against launch; `destinationOfRef` for a reference `fluid/inspect.py` already resolved |
| `quiet2/results/launch.ts` | where the reader was (any Place, not only a conversation); Brain identity including instance; one opening at a time; focus per opening; what a stored launch may still restore |
| `quiet2/results/history.ts` | which transitions enter the centre's history (only maximised); one entry per displacement; what a close does; what landing on a result entry again does |
| `quiet2/results/opener.ts` | `openResultTarget(destination, launch, host)`: the one host operation, and what actually happened |
| `quiet2/viewer/viewableOfItem.ts` | which renderer a file opens in, from the server's verified word |
| `quiet/media/view.ts` | `ViewerItem.treatment` (additive), `DRAWN_BYTES`, `cutWords`, `FRAME_REFUSES` |
| `quiet/media/MediaLayer.tsx` | the bounded-reading and frame-refusal disclosure, beside the existing download |
| `quiet2/address.ts` | `CentreAt` gains the optional `result` arm; a result is addressed as the Place it is over |

Tests: `tests/quiet2_result_targets_unit.{ts,mjs}`, `tests/quiet2_result_opener_unit.{ts,mjs}`,
`tests/quiet2_result_viewable_unit.{ts,mjs}`, and the three `.ts` added to
`tsconfig.test.json`'s `include` (the one line in that file another part is also likely to
touch).

## 1. `Quiet2.tsx` — one opening, with a launch

The baseline keeps `openedBy` as a module-global and captures it inside `onView`:

```tsx
  const onView = (content: Viewable, source: ViewerSource) => {
    openedBy = document.activeElement as HTMLElement | null
    ...
```

Give `onView` the launch instead, and keep that launch per opening
(`launch.ts` `beginOpening`, `holdLaunch`), so two things opened from different places return
to different controls and a read that finishes late cannot steal focus (H6):

```tsx
  /** WHERE THE READER IS NOW, as a launch: identity and position only. */
  const launchNow = (focus: LaunchFocus, decision?: DecisionLaunch | null): LaunchContext => holdLaunch({
    opening: beginOpening(),
    brainKey: brain.key ?? null,
    place: { conversation: realId, centre: centreAt.current },
    thread: entered ? { root: entered, at: enteredAt } : null,
    reading: { scroll: document.querySelector<HTMLElement>('.q2-conv')?.scrollTop ?? 0, offset: left.current?.offset ?? null },
    reply: replyTo?.id ?? null,
    draft: composerKey,                 // THE KEY, never the text
    focus, decision: decision ?? null,
  })
  const onView = (content: Viewable, source: ViewerSource, launch = launchNow({ control: null, fallback: { kind: 'conversation' } })) => {
    opened.set(launch.opening, document.activeElement as HTMLElement | null)
    if (!surfacePanes.length) { return openedMax(openViewer(content, source, 'max'), launch) }
    const free = surfacePanes.find((s) => !surfaces[s] && !inColumn(s) && !dockPanels[s])
    if (free) { openViewer(content, source, free); return 's1' }   // a column: no history entry (H1)
    setChoosing({ content, source, launch }); return 'choosing'
  }
```

`openedMax(id, launch)` is the one place an entry is pushed, through the existing `centre`:

```tsx
  const openedMax = (id: string, launch: LaunchContext) => {
    viewerLaunch.set(id, launch)
    centre.go(resultIntent(brain.key ?? null, launch.opening, targetOfViewer(id), launch.place))
    return 'max'
  }
```

and every move / maximise / restore / close asks `historyStep(from, to)` rather than deciding
for itself: `push` → `centre.go(resultIntent(...))`, `consume` → the close plan below, `none` →
nothing at all. `placeIn` and the column paths are `none`, which is the H1 fix: opening or
moving a side viewer must not touch `CentreAt`, push an entry, or run `guarded`.

### Close, and Go to source, are different actions (B3, H2, H3)

Baseline:

```tsx
      close: () => { closeViewer(v.id); if (v.place === 'max' && post) requestAnimationFrame(() => revealPost(post.post)) },
      toSource: post ? () => {
        if (v.place === 'max' && v.from && surfacePanes.includes(v.from)) moveViewer(v.id, v.from)
        else if (v.place === 'max') { setNotice('Close the viewer to return to the post it came from; it stays open until then.'); return }
        requestAnimationFrame(() => revealPost(post.post))
      } : null,
```

Replace with:

```tsx
      close: () => {
        const l = viewerLaunch.get(v.id)
        closeViewer(v.id); viewerLaunch.delete(v.id)
        if (historyStep(v.place === 'max' ? 'max' : 's1', 'none') !== 'consume' || !l) return restoreFocus(l)
        const owns = !!centreAt.current?.result && centreAt.current.result.opening === l.opening
        switch (closePlan(owns, isBehindPlace(l.place))) {
          case 'back': centre.back(l.place.centre, () => restoreLaunch(l)); break
          case 'replace': centre.replace(l.place.centre); restoreLaunch(l); break
          case 'frame-only': restoreFocus(l); break      // keepsReturnBar: the return bar stays
        }
      },
      /* GO TO SOURCE IS NOT CLOSE. The exact conversation and post, loaded if
         they are not drawn -- `goToPost` already does that -- so `max` with no
         previous column is no longer a dead end (H3). */
      toSource: post ? () => {
        if (v.place === 'max' && v.from && surfacePanes.includes(v.from)) moveViewer(v.id, v.from)
        now.current.goToPost(post.conversation ?? realId!, post.post)
      } : null,
```

`restoreLaunch(l)` puts back the thread, the reading offset and the reply target from the live
launch, and `restoreFocus(l)` applies `focusChoice(l, opened.get(l.opening), has)`. Neither
calls `revealPost(v.source.post)`: closing returns to where the reader WAS.

### Landing on a result entry again (H2, H8, B3 item 7)

In the `centre` `apply` callback, beside the existing `brain` / `source` / `space` arms:

```tsx
    if (to?.result) {
      const r = resumeResult({ result: to.result }, { brainKey: brain.key ?? null, live: (o) => !!launchOf(o), words: BRAIN_MOVED })
      if (r.how === 'other-brain') { setNotice(r.words); centre.replace(r.place.centre); return }
      if (r.how === 'resolve') { /* after a reload: resolve the target again, offer r.place as the way back */ }
      /* 'live': the viewer is still open; nothing to recreate */
    }
```

A Forward into another Brain instance's entry is refused here, which is the H5/`brainBinding`
rule applied to history rather than a second one.

### The dock's file open stops hardcoding the Brain (B4)

Baseline:

```tsx
  const fileFromDock = isReal && brain.key ? (entry: string, about: Parameters<typeof heldItem>[1]) => {
    const item = heldItem(entry, about)
    if (item) onView({ kind: 'file', item }, { kind: 'brain', brainKey: brain.key! })
    else setNotice('That file cannot be opened: Mentis does not hold its contents.')
  } : undefined
```

Replace the body with the shared opener, which chooses the renderer from the server's own word
(so a PDF opened from Needs you reaches pdf.js, and a picture its collection) and keeps the
post as the source where the reference names one:

```tsx
  const resultHost: OpenerHost = {
    brainKey: brain.key ?? null,
    origin: location.origin,
    file: ({ item, file, source }) => {
      const read = item ?? heldItem(/* ref */ '', file as never)
      return read ? onView(viewableOfItem(read, picturesOf(postOf(postSource(source!)?.post ?? '') ?? undefined)), source!) : null
    },
    post: (c, p) => { now.current.goToPost(c, p); return true },
    record: (entry) => { enterBrain({ page: 'record', entry }, { from: 'link' }); return true },
    conversation: (c) => !!pickConversation(c),
    external: (href) => !!window.open(href, EXTERNAL_LINK.target, EXTERNAL_LINK.rel),
    say: setNotice,
  }
  /** what the dock, the chooser and Needs you all press. */
  const openResult = (d: ResultDestination, launch: LaunchContext) => openResultTarget(d, launch, resultHost)
  const fileFromDock = isReal && brain.key
    ? (entry: string, about: Parameters<typeof heldItem>[1], launch?: LaunchContext) =>
        openResult(destinationOfRef({ id: entry, type: 'file', available: !!about && about.state === 'held', state: about?.state ?? 'not-held', opens: 'file', file: about ?? null }),
          launch ?? launchNow({ control: `needs-ref:${entry}`, fallback: { kind: 'conversation' } }))
    : undefined
```

`leaves(result)` is what tells the dock whether the reader actually left; `displaces(result)`
whether the history is owed an entry. A `placing`, `unavailable`, `identity` or `refused` answer
is none of those, which is the "no false left transition" rule: the draft and the open form stay.

## 2. `GlobalDock.tsx` — the dock's own reference opening

Baseline, in `NeedsItemRow` (lines ~267–280), decides openability and routes by hand:

```tsx
  const can: CanOpen = useCallback((r) => (r.opens === 'record' ? !!openers.record : r.opens === 'file' ? !!openers.file && !!r.file : !!r.conversation), [openers])
  const open: OpenRefFn = useCallback((r: Ref) => {
    if (!r.available || !r.opens || !can(r)) return false
    leaving(r.id, refName(r, 60))
    if (r.opens === 'record') openers.record!(r.id)
    ...
```

Route it through the one operation instead, so the dock no longer has its own opinion of what
opens and `ok`-with-no-route is said rather than pressed (M2.2):

```tsx
  const open: OpenRefFn = useCallback((r: Ref) => {
    const d = destinationOfRef(r)
    if (!openable(d).can) return false
    const launch = openers.launch({ control: `needs-ref:${r.id}`, fallback: { kind: 'decision', item: it.key } },
      { form: about?.form ?? null, question: askOf(it), item: it.key, ref: r.id, role: r.relation ?? null })
    const done = openers.open(d, launch)
    /* THE WAY BACK IS ARMED ONLY WHERE THE READER ACTUALLY LEFT: a new tab, a
       cancelled placement or a failed read leaves this panel and this draft
       exactly as they are. */
    if (leaves(done)) leaving(r.id, refName(r, 60), launch)
    return done.what !== 'unavailable' && done.what !== 'refused'
  }, [it, about, openers])
```

`can` becomes `(r) => openable(destinationOfRef(r)).can && openers.has(destinationOfRef(r))`, and
`NeedsAbout.tsx`'s `if (!r.opens || !r.available || !can(r))` can keep its shape — it already
shows `r.why` for the unopenable case, which is the behaviour this contract wants.

Two things the dock must NOT do, both already true of the baseline and worth keeping:

- it must not listen to `popstate`: browser Back never reopens Needs you (H4). The explicit
  pill is the only way back, and it now restores the Place as well as the row — the host
  restores `left.launch.place`, the adapter restores the row and its form.
- the external arm must not close the panel. `openers.open` returns `{ what: 'external' }`, for
  which `leaves` is false, so `close(false)` must not be called on that path. In the baseline
  `openers.record`/`openers.file` call `close(false)` before the outward call; that stays right
  for a real open and must not be extended to the URL arm.

## 3. Dependencies on other parts

1. **S-D / the Needs You adapter owns `needs/about.ts`.** `Leave` must gain the launch and the
   question identity for the pill to restore the Place and the pending item together
   (focused review M2.3): `leaveFor({ ..., launch: LaunchContext })`, with
   `DecisionLaunch` as this contract defines it. Until it does, `leaveFor` keeps its present
   shape and the pill restores the panel only — which is the sibling baseline's behaviour, not
   this round's property. **This is the one part of H4 that cannot be met inside N-C's files.**
2. **N-B owns `Post.tsx`.** `viewableOf(i, post)` should become
   `viewableOfItem(i, picturesOf(post))`; the local PDF test (`/pdf/i.test(i.mediaType)`) is
   what `isPdf` replaces, and dropping it is what stops a file named `.pdf` reaching pdf.js
   against the server's own classification. The behaviour for a post's attachments is otherwise
   unchanged, and `tests/quiet_post_unit.mjs` still passes against the baseline's own call site.
3. **N-A owns `work/contract.ts`.** A `ResultDestination` is built from its wire shape by the
   chooser (N-B), not by this module: `targets.ts` names no HTTP field.
4. `tsconfig.test.json`'s `include` is one line that several parts will add to; expect a
   trivial conflict there and keep every part's entries.

## 4. What is not done here, and why

- **No rendered or browser check of any of this.** The modules are not mounted: the two files
  that would mount them are the integrator's, so nothing in a browser exercises them yet. V1–V5
  and H1–H8 are checked as decisions (the pure rules above), not as rendered behaviour. N-D's
  acceptance on the combined candidate is where they become observed.
- **`Presented.Primary` anchors.** The focus contract covers them (`focusChoice` takes any
  control identity, and a `fallback` of `{ kind: 'decision' }`), but the markup is S-D's.
- **No permission, renderer-security, Magnet or Presets change.** `HtmlFrame`'s sandbox, CSP,
  `prose.tsx`'s `safeHref` and `/api/worker` are untouched; the only new words about the frame
  say what it already refuses.
