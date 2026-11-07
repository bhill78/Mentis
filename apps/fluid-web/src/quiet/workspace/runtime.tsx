/* THE ONE HOLDER AND NAV ADAPTER. Round 5, package W2.
 *
 * R MOUNTS THIS HOOK AND NOTHING ELSE. One entrance into the Holder, one
 * history path: this validates S's envelope through W1's seams, restores the
 * travelling floats BEFORE the first `enter`, enters with
 * `localLayout`/`touched` under F9's precedence, and hydrates the Pages before
 * anything captures or decides. R adds no second entrance effect beside it.
 *
 * WHY THE ENTRANCE IS HERE AND THE STAGE WAITS FOR IT (`place.ts:969`). A
 * second `enter` for the same key and kind returns immediately, so whoever
 * enters first decides which arrangement is drawn. Fluid's own Workspace
 * enters in an effect, and a child's effect runs before its parent's -- so if
 * the stage mounted Workspace while this was still deciding, Workspace would
 * enter the place bare and the browser copy would arrive too late to be seen.
 * `ready` is therefore BOTH the answer R's unknown-Page gate waits for and the
 * gate the stage itself waits on (`WorkingArea.tsx`): nothing mounts Fluid's
 * Workspace for this place until the Holder holds it.
 *
 * HOW LONG THAT TAKES. The Page list is hydrated SYNCHRONOUSLY with the
 * entrance -- `place.ts`'s `onArr` calls `nav.setPages` inside `enter`'s own
 * `emit` -- so `ready` is true in the same tick as the entrance. The entrance
 * itself is synchronous on a same-tab reload, where the session copy needs no
 * Brain to be named; a NEW session waits for `brainIdentity()` to settle
 * (F10), because the durable envelope's key is the Brain's, and an envelope
 * read under an unknown Brain would be a different place's.
 *
 * WHAT IS PERSISTED, AND WHAT `touched` IS. The envelope keeps the Holder's
 * own device-inclusive tab representation (`exportLocalLayout`) and the
 * SEMANTIC unsaved-edits flag -- which is NOT `changed()`: after a differing
 * Brain response `changed()` is true while nothing of the reader's has been
 * touched, and persisting that would mark every resumed place as edited. The
 * Holder's own marker is read instead, with an in-memory fallback for a
 * browser that refuses sessionStorage altogether (below).
 *
 * Quiet's destination history is the browser hash (F8), so the scoped
 * external-history adapter lives here -- `fluid/nav.ts`'s
 * `hostExternalNavigation` -- and is removed again when this unmounts, which
 * is what keeps /fluid out of that scope.
 */
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { Id } from '../../api'
import {
  closePage,
  hostExternalNavigation,
  newPage,
  openDetail,
  replayExternal,
  showPage,
  snapshot,
  subscribe,
  type Detail,
  type ExternalNavigation,
} from '../../fluid/nav'
import { workspace, type PlaceKind } from '../../fluid/workspace/place'
import { isWorkspaceId } from '../../fluid/workspaces/client'
import type { WorkspaceRuntimeHook } from '../contract'
import { CONVERSATION_PAGE, readQuietLocation, resumeLocation } from '../pages/location'
import {
  chooseSnapshot,
  readTravelBookmark,
  settleBrainIdentity,
  useWorkspaceBookmark,
  writeTravelBookmark,
} from './bookmarks'
import type { BrowserSnapshot, QuietNavigate, QuietSequencePage } from './types'

/* -- the one way out of the working area ----------------------------------- */

/** WHERE A CROSS-CONVERSATION INTENT GOES. `WorkingArea` is given
 *  `onNavigate` by the shell and registers it here, because the adapter below
 *  is told about such an intent by `fluid/nav.ts` -- which reports it and does
 *  NOT apply it -- and the hook itself has no `onNavigate` of its own. One
 *  registration at a time, removed on unmount. */
let outward: QuietNavigate | null = null
export function hostWorkingNavigation(fn: QuietNavigate | null): () => void {
  outward = fn
  return () => {
    if (outward === fn) outward = null
  }
}

/** A DETAIL ASKED FOR IN ANOTHER CONVERSATION IS NOT LOST. `nav.openDetail`
 *  reports the whole target -- conversation, post, Page and the detail itself
 *  -- and applies none of it when the conversation changes. The conversation
 *  is routed out through `onNavigate`; the detail is held here and applied
 *  once that arrival has actually settled, inside `replayExternal` so it
 *  reports no second intent. Held for one arrival only. */
let awaiting: { conversation: Id; detail: Detail } | null = null

/** What `read`/`openDetail` asked for, for the stage's own report. */
export const awaitingDetail = (): { conversation: Id; detail: Detail } | null => awaiting

/* -- the semantic touched flag --------------------------------------------- */

/** The Holder's own same-tab copy and its touched marker (`place.ts`). */
const SESSION = 'mentis.fluid.arr:'
const TOUCHED = ':changed'

/** THE HOLDER'S OWN FLAG, where it can be read: `place.ts`'s `writeSession`
 *  keeps it beside the tab copy on every change and removes it on a Save, so
 *  it is the semantic answer and not a layout comparison. `null` means the
 *  question cannot be asked at all -- sessionStorage refused (private mode, a
 *  policy, a quota) -- which is a real browser state and not an error. */
function marked(key: string): boolean | null {
  try {
    if (typeof sessionStorage === 'undefined') return null
    return sessionStorage.getItem(SESSION + key + TOUCHED) === '1'
  } catch {
    return null
  }
}

/** WHAT TO PERSIST WHERE THE MARKER CANNOT BE READ. Watching the Holder is
 *  enough to tell an edit from a replacement: a reader's change moves the
 *  arrangement and leaves `from` where it was, while every replacement --
 *  what the Brain keeps, a default layout, a Save -- moves `from` as it moves
 *  the arrangement. It starts from the touched state entered with, so a
 *  resumed place that was already edited stays edited.
 *
 *  It is deliberately one-directional: it can over-report after a Save in a
 *  browser that refuses sessionStorage (where nothing durable is written
 *  either), and it never under-reports. Where the marker CAN be read, the
 *  marker alone is used. */
const watch = {
  key: null as string | null,
  edited: false,
  arr: null as unknown,
  from: null as string | null,
  entered(key: string, touched: boolean) {
    this.key = key
    this.edited = touched
    this.arr = workspace.arr
    this.from = workspace.from
  },
  observe() {
    if (this.key === null) return
    const arr: unknown = workspace.arr
    const from: string = workspace.from
    if (arr !== this.arr && from === this.from) this.edited = true
    this.arr = arr
    this.from = from
  },
  /** The semantic flag for `key`, as the envelope must keep it. */
  value(key: string): boolean {
    const m = marked(key)
    return m === null ? this.key === key && this.edited : m
  },
}

/** Exported for the unit suite: the flag as it would be persisted now. */
export const touchedNow = (key: string): boolean => watch.value(key)

/* -- the place ------------------------------------------------------------- */

/** WHICH KIND OF PLACE THE ORIGIN IS, worked out exactly as Fluid's own
 *  `usePlace` does, and then SUPPLIED to Workspace -- so the two cannot
 *  disagree and re-enter the place under a second kind, which would throw the
 *  entered copy away (`place.ts:969` compares the kind too). A Quiet origin is
 *  a conversation; the two other spellings are kept because the same address
 *  can name them. */
export function placeKindOf(key: string): PlaceKind {
  return key === 'stream' ? 'stream' : isWorkspaceId(key) ? 'workspace' : 'conversation'
}

/** The Pages of the sequence, as the controls draw them. Conversation keeps
 *  its own name; everything else is the arrangement's own title. */
export const sequenceOf = (
  pages: readonly { id: string; title?: string }[],
): QuietSequencePage[] =>
  pages.map((p) => ({
    id: p.id,
    title: p.id === CONVERSATION_PAGE ? 'Conversation' : 'title' in p && p.title ? p.title : p.id,
  }))

/** THE ENTRANCE ITSELF, in one place so it can be checked without a renderer.
 *  The order is the whole point: what travelled is restored BEFORE the first
 *  `enter` (W1), so the Holder's own `carry` brings it over the place arrived
 *  at; then the place is entered with the chosen copy under F9's precedence,
 *  which hydrates the Page list synchronously (`place.ts`'s `onArr` calls
 *  `nav.setPages` inside `enter`'s own `emit`). `travel` omitted restores
 *  nothing, which is what a pending or unavailable Brain has. */
export function enterPlace(
  key: string,
  kind: PlaceKind,
  chosen: BrowserSnapshot | null,
  travel?: unknown,
): void {
  if (travel !== undefined) workspace.restoreLocalTravel(travel)
  if (chosen) workspace.enter(key, kind, { localLayout: chosen.layout, touched: chosen.touched })
  else workspace.enter(key, kind)
  watch.entered(key, chosen ? chosen.touched : false)
}

/** WHAT THE SCOPED ADAPTER DOES WITH WHAT NAV REPORTS (F7/F8), built apart
 *  from the hook so every branch of it is checkable.
 *
 *  `at` reads the destination the hash already carries, because the Page
 *  callbacks fire while nav still names the OUTGOING Page and the argument
 *  names the DESTINATION (S's correction): the topic and post in the address
 *  belong to the reading, and a Page change must not quietly clear them.
 *  `here` is the conversation nav is at, and `outward` the way out of the
 *  working area. */
export function externalNavigation(args: {
  originConversation: Id
  intend: (at: { originConversation: Id; topic: Id | null; turn: Id | null; page: string }) => void
  here: () => Id | null
  at: () => { topic: Id | null; turn: Id | null } | null
  outward: () => QuietNavigate | null
}): ExternalNavigation {
  const { originConversation, intend, here, at, outward } = args
  return {
    page: (id) => {
      const was = at()
      intend({ originConversation, topic: was?.topic ?? null, turn: was?.turn ?? null, page: id })
    },
    /* THE WHOLE TARGET, NEVER A PIECE OF IT (S review finding 6). A read in
       the conversation being read is already applied by nav and only needs the
       hash to say so. A read in ANOTHER conversation was reported and NOT
       applied: it leaves through the working area's `onNavigate` with its
       conversation and its post, and a detail that came with it is held and
       applied after that arrival rather than dropped. With no way out
       registered the destination conversation is still named -- never the
       origin's address with somebody else's post in it. */
    read: (conversation, post, page, detail) => {
      if (conversation === here()) {
        intend({ originConversation, topic: at()?.topic ?? null, turn: post, page })
        return
      }
      awaiting = detail ? { conversation, detail } : null
      const out = outward()
      if (out) out({ conversation, turn: post })
      else
        intend({
          originConversation: conversation,
          topic: null,
          turn: post,
          page: CONVERSATION_PAGE,
        })
    },
  }
}

/* -- the runtime ----------------------------------------------------------- */

/** The runtime, as R reads it. */
export const useWorkspaceRuntime: WorkspaceRuntimeHook = ({ originConversation }) => {
  const nav = useSyncExternalStore(subscribe, snapshot, snapshot)
  const arr = useSyncExternalStore(workspace.subscribe, workspace.snapshot)
  const bookmark = useWorkspaceBookmark()
  const envelope = bookmark?.envelope ?? null
  const patch = bookmark?.patch
  const restoring = bookmark?.restoring ?? false
  const [, setArea] = useState<HTMLElement | null>(null)
  const kind = useMemo(() => placeKindOf(originConversation), [originConversation])

  /* -- THE ENTRANCE, ONCE PER PLACE ---------------------------------------
     The decision needs the Brain only where there is no tab copy to prefer,
     so a same-tab reload enters on the first effect and a new session enters
     when identity has settled -- 'unavailable' as firmly as 'resolved' (F10),
     because a memory-only session must not wait forever to be drawn. */
  const [entered, setEntered] = useState<string | null>(null)
  /* WHICH BRAIN, READ HERE RATHER THAN TAKEN FROM THE PROVIDER, which reports
     whether identity settled but not what it settled on. The underlying read
     is memoised in the store, so this is the same answer the provider got and
     not a second question to the server -- and gating the entrance on THIS
     promise rather than on the provider's state means the Brain is known by
     the time a durable envelope is looked for, whichever settles first. */
  const brain = useRef<string | null>(null)
  const [settled, setSettled] = useState(false)
  useEffect(() => {
    let live = true
    void settleBrainIdentity().then((got) => {
      if (!live) return
      brain.current = got.brain
      setSettled(true)
    })
    return () => {
      live = false
    }
  }, [])

  useEffect(() => {
    if (entered === originConversation) return
    const chosen = chooseSnapshot(
      { brain: brain.current, conversation: originConversation },
      { placeKey: originConversation },
    )
    /* No tab copy and no answer about the Brain yet: wait. Once identity has
       settled there is nothing left to wait for -- a durable copy if there is
       one, and otherwise Fluid's own saved/default order. */
    if (!chosen && !settled) return
    enterPlace(
      originConversation,
      kind,
      chosen,
      brain.current === null ? undefined : readTravelBookmark(brain.current),
    )
    setEntered(originConversation)
  }, [entered, settled, kind, originConversation])

  /* The Pages are hydrated by the entrance itself (`place.ts`'s `onArr` calls
     `nav.setPages` inside `enter`'s `emit`), so this is the one answer: the
     Holder holds this place, and its sequence is what nav now reports. */
  const ready = entered === originConversation && workspace.key === originConversation

  /* -- WHAT IS REMEMBERED, ONCE THE PLACE IS ITS OWN ----------------------
     Capture is suppressed while a bookmark is being restored and before the
     entrance, so initialisation defaults are never written over a restored
     copy (F9's last sentence). The layout is coalesced -- a drag is one
     arrangement, not sixty -- and the Holder's own marker says whether it was
     touched. */
  const written = useRef<string>('')
  useEffect(() => {
    if (!ready || restoring || !patch) return
    watch.observe()
    const layout = workspace.exportLocalLayout()
    const touched = watch.value(originConversation)
    /* ONLY A CHANGE IS WRITTEN. The Holder emits several times as a place
       settles -- the entrance, what the Brain keeps, the shared geometry --
       and most of those leave the arrangement exactly as it was. Writing it
       again each time tells every reader of the envelope that it moved, and
       the reading being restored beside this one is one of those readers. */
    const now = JSON.stringify([layout, touched])
    if (now === written.current) return
    written.current = now
    patch({ layout, touched }, { coalesce: true })
    if (brain.current !== null) writeTravelBookmark(brain.current, workspace.exportLocalTravel())
  }, [arr, ready, restoring, patch, originConversation])

  /* Which Page the place is on, remembered as soon as it is this place's. */
  useEffect(() => {
    if (!ready || restoring || !patch) return
    if (envelope?.selectedPage === nav.page) return
    patch({ selectedPage: nav.page })
  }, [nav.page, ready, restoring, patch, envelope?.selectedPage])

  /* -- THE SCOPED EXTERNAL HISTORY (F7/F8) --------------------------------
     One intent per transition, and the location controller alone writes the
     hash. The Page callbacks fire while `nav.snapshot().page` still names the
     OUTGOING Page and the argument names the DESTINATION (S's correction), so
     the topic and post the hash already carries are read here and carried
     over rather than being silently cleared by a Page change. */
  const intend = bookmark?.intend
  useEffect(() => {
    if (!intend) return
    return hostExternalNavigation(
      externalNavigation({
        originConversation,
        intend,
        here: () => snapshot().conversation,
        at: () => readQuietLocation(),
        outward: () => outward,
      }),
    )
  }, [intend, originConversation])

  /* -- THE PAGE A RESUMED ARRIVAL OPENS ----------------------------------
     A bare `#/c/<id>` is a resume entry: it says nothing itself, so the Page
     somebody left is what opens (S's `resumeLocation`, which also refuses one
     this place does not have). Anything explicit in the address is deliberate
     and is not touched. Asked ONCE per place, and only once the Pages are
     hydrated -- before that, an absence from the list is not an answer -- and
     reported as an intent like everything else, so the shell is still the one
     writer of the address. */
  const resumedPage = useRef<string | null>(null)
  useEffect(() => {
    if (!ready) return
    const at = readQuietLocation()
    if (!at || at.originConversation !== originConversation) return
    const ids = nav.pages.map((p) => p.id)
    /* AN EXPLICIT PAGE IS APPLIED ONCE THE PLACE HAS IT. The shell applies the
       address as soon as it is read, which on a new session is BEFORE the
       Holder has been entered -- and a Page that does not exist yet cannot be
       selected (`pageFor`), so the address would be dropped and never asked
       again. Applying it here, inside `replayExternal`, reports no intent and
       pushes no step: one guarded direction, as F8 requires. */
    if (at.page !== CONVERSATION_PAGE && ids.includes(at.page) && nav.page !== at.page) {
      replayExternal(() => {
        showPage(at.page)
      })
      return
    }
    if (!intend || resumedPage.current === originConversation) return
    resumedPage.current = originConversation
    const want = resumeLocation(at, envelope, ids)
    if (want.location.page === at.page) return
    intend(want.location)
  }, [ready, intend, originConversation, envelope, nav.pages, nav.page])

  /* A held detail is applied once its arrival has settled -- the conversation
     is the one asked for and its post is being read -- and never twice. */
  useEffect(() => {
    const held = awaiting
    if (!held || !ready) return
    if (nav.conversation !== held.conversation) return
    awaiting = null
    replayExternal(() => {
      openDetail(held.detail)
    })
  }, [nav.conversation, nav.reading, ready])

  /* Leaving the place writes what is still coalesced: an arrangement changed
     in the last moment before a Page or a conversation change is not lost. */
  const flush = bookmark?.flush
  useEffect(() => () => flush?.(), [flush])

  const selectPage = useCallback((id: string) => {
    showPage(id)
  }, [])
  const addPage = useCallback(() => {
    newPage()
  }, [])
  const close = useCallback((id: string) => {
    closePage(id)
  }, [])

  return {
    ready,
    pages: sequenceOf(nav.pages),
    page: nav.page,
    selectPage,
    addPage,
    closePage: close,
    setArea,
  }
}
