/* WHAT THIS BROWSER REMEMBERS ABOUT A CONVERSATION. Round 5, package S.
 *
 * THE OWNER ASKED FOR IT ACROSS SESSIONS IN THIS BROWSER (ent-d159fadca191),
 * so the durable copy is localStorage -- one envelope per origin
 * conversation, per Brain:
 *
 *   mentis:quiet:workspace:v1:<corpus_id>:<originConversation>
 *
 * NOTHING HERE IS A RECORD. Remembering where somebody was reading is not a
 * fact about the corpus: no Brain save is triggered by remembering or
 * resuming, and nothing is sent anywhere.
 *
 * NOTHING IN THIS MODULE HAPPENS AT IMPORT TIME. A module that read storage
 * when it loaded would read it before the Brain is known and before anybody
 * asked for anything; every read and write HERE is made from a call.
 *
 * What its dependencies do at import time is theirs and is unchanged: Fluid's
 * `place.ts` constructs its Holder as a module value (reading this tab's
 * session copy and registering a `storage` listener) and `nav.ts` reads the
 * Follow flag, both exactly as they did before round 5. Validating a layout
 * through the Holder's own `fromLayout` is the plan's instruction, so those
 * effects come with it; what this file promises is that it adds none.
 *
 * WHICH BRAIN (F10). `brainIdentity()` is the existing read and the only one
 * -- no new endpoint. Until it answers, the identity is PENDING: changes are
 * kept in memory and NO key is written, because a key naming an unknown Brain
 * is a key belonging to nobody. What was done while pending is replayed onto
 * the real envelope once the Brain is known. Resolved WITHOUT a `corpus_id`
 * is the literal 'local', matching `place.ts`'s own fallback -- that is the
 * resolved-but-unnamed Brain, never the pending one. Refused or full storage,
 * and a failed identity read, both leave a usable in-memory session.
 *
 * PINNED TRAVELLING FLOATS ARE NOT IN THE ENVELOPE. They travel across
 * conversations with the owner, so they are mirrored once per Brain
 * (`mentis:quiet:travel:v1:<corpus_id>`) and never duplicated into every
 * origin's envelope. `readTravel` is the existing validator; W1's Holder
 * carries them with its existing carry functions, not a new collection.
 *
 * WHO IS WRITING, HOW IT LOOKS, AND WHAT IS HALF TYPED all stay where they
 * already are: `quiet/filter/who.ts`'s own store, the appearance keys, and
 * the in-memory drafts. A second copy of any of them would be a second
 * answer.
 */
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from 'react'
import type { Id } from '../../api'
import type { Place } from '../../fluid/actions'
import type { Float } from '../../fluid/focus/types'
import { READABLE } from '../../fluid/nav'
import { brainIdentity } from '../../fluid/store'
import { fromLayout, readTravel } from '../../fluid/workspace/place'
import { CONVERSATION_PAGE } from '../pages/location'
import type {
  BrowserSnapshot,
  PatchOptions,
  QuietDestination,
  QuietLocation,
  ReadingBookmark,
  RoomBookmark,
  WorkspaceBookmarkValue,
  WorkspaceEnvelope,
  WorkspaceIdentity,
  WorkspacePatch,
} from './types'

export const ENVELOPE_VERSION = 1

/** The resolved-but-unnamed Brain (`place.ts`'s own fallback). */
export const LOCAL_BRAIN = 'local'

/** One envelope's key. Both parts are encoded: a conversation id holding a
 *  colon must not reach across into the next field. */
export const workspaceKey = (brain: string, conversation: string): string =>
  `mentis:quiet:workspace:v1:${encodeURIComponent(brain)}:${encodeURIComponent(conversation)}`

/** The travelling floats' key: per Brain and per browser, not per origin. */
export const travelKey = (brain: string): string =>
  `mentis:quiet:travel:v1:${encodeURIComponent(brain)}`

/** The Fluid Holder's same-tab copy of a place (`place.ts` SESSION), read
 *  here only to say WHICH snapshot wins (F9); it is never written here. */
const SESSION = 'mentis.fluid.arr:'
const SESSION_TOUCHED = ':changed'

/** Coalesced writes wait this long: long enough that scrolling a reading is
 *  one write rather than one a frame, short enough that leaving the tab a
 *  moment later still has something to flush. */
const COALESCE_MS = 400

/* -- storage, which may not be there at all -------------------------------- */

function local(): Storage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    /* denied in private mode, or by a policy: this session only */
    return null
  }
}

function readRaw(key: string): string | null {
  try {
    return local()?.getItem(key) ?? null
  } catch {
    return null
  }
}

function writeRaw(key: string, value: string): boolean {
  try {
    const store = local()
    if (!store) return false
    store.setItem(key, value)
    return true
  } catch {
    /* refused or full: the envelope stays in memory and the session works */
    return false
  }
}

/* -- validation: what is read back is checked, never repaired -------------- */

const isObject = (v: unknown): v is Record<string, unknown> =>
  !!v && typeof v === 'object' && !Array.isArray(v)
const str = (v: unknown): v is string => typeof v === 'string' && v.length > 0
const fin = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

const ROOM_MODES = new Set(['single', 'panes', 'board'])
const RAILS = new Set(['topics', 'brief', 'activity', 'carried'])

function readAnchor(v: unknown): ReadingBookmark['flow']['anchor'] {
  if (!isObject(v) || !str(v.post) || !fin(v.offset)) return null
  return { post: v.post as Id, offset: v.offset }
}

function readBatch(v: unknown): ReadingBookmark['flow']['batch'] | null {
  if (!isObject(v)) return null
  const out: { before?: number; after?: number } = {}
  if (v.before !== undefined) {
    if (!fin(v.before)) return null
    out.before = v.before
  }
  if (v.after !== undefined) {
    if (!fin(v.after)) return null
    out.after = v.after
  }
  return out
}

function readMargin(v: unknown): ReadingBookmark['margin'] {
  const o = isObject(v) ? v : {}
  const scrolls: Record<string, number> = {}
  if (isObject(o.scrollByReading))
    for (const [rail, px] of Object.entries(o.scrollByReading))
      if (RAILS.has(rail) && fin(px)) scrolls[rail] = px
  return {
    reading: str(o.reading) && RAILS.has(o.reading)
      ? (o.reading as ReadingBookmark['margin']['reading'])
      : null,
    searchOpen: o.searchOpen === true,
    query: typeof o.query === 'string' ? o.query : '',
    scrollByReading: scrolls as ReadingBookmark['margin']['scrollByReading'],
  }
}

function readReading(v: unknown): ReadingBookmark | null {
  if (!isObject(v) || !isObject(v.flow)) return null
  const batch = readBatch(v.flow.batch)
  if (!batch) return null
  const t = v.thread
  let thread: ReadingBookmark['thread'] = null
  if (isObject(t)) {
    if (!str(t.root) || !str(t.target) || !str(t.replyTo)) return null
    thread = {
      root: t.root as Id,
      target: t.target as Id,
      replyTo: t.replyTo as Id,
      anchor: readAnchor(t.anchor),
    }
  } else if (t !== null && t !== undefined) return null
  return {
    flow: {
      topic: str(v.flow.topic) ? (v.flow.topic as Id) : null,
      batch,
      anchor: readAnchor(v.flow.anchor),
    },
    thread,
    margin: readMargin(v.margin),
  }
}

function readRoom(v: unknown): RoomBookmark | null {
  if (!isObject(v) || !str(v.mode) || !ROOM_MODES.has(v.mode) || !fin(v.readingPx)) return null
  return { mode: v.mode as RoomBookmark['mode'], readingPx: v.readingPx }
}

function readDestination(v: unknown): QuietDestination | null {
  if (!isObject(v)) return null
  if (v.kind === 'workspace') return { kind: 'workspace' }
  if (v.kind !== 'deep-dive') return null
  if (!str(v.conversation) || !str(v.openingTurn) || !isObject(v.origin)) return null
  const o = v.origin
  if (!str(o.conversation) || !str(o.page) || !str(o.post) || !isObject(o.place)) return null
  return {
    kind: 'deep-dive',
    conversation: v.conversation as Id,
    openingTurn: v.openingTurn as Id,
    origin: {
      conversation: o.conversation as Id,
      page: o.page,
      post: o.post as Id,
      /* the existing `fluid/actions.ts` Place, passage and version kept as
         they were written: a dive's provenance is not re-derived here */
      place: o.place as Place,
    },
  }
}

function mapOf<T>(v: unknown, read: (x: unknown) => T | null): Record<string, T> {
  const out: Record<string, T> = {}
  if (!isObject(v)) return out
  for (const [key, value] of Object.entries(v)) {
    const got = read(value)
    if (got !== null) out[key] = got
  }
  return out
}

/** THE LAYOUT IS CHECKED BY THE ONE READER OF IT. `fromLayout` is Fluid's
 *  own, so a layout this accepts is a layout the Holder can enter, and an
 *  arrangement from a newer build is refused by the same rule as everywhere
 *  else rather than by a second opinion here. */
function readLayout(v: unknown): Record<string, unknown> | null {
  if (!isObject(v)) return null
  try {
    return fromLayout(v) ? v : null
  } catch {
    return null
  }
}

/** THE ENVELOPE AS STORED, or null when there is no valid snapshot in it.
 *
 *  A malformed or unknown-version envelope is NOT repaired and NOT replaced:
 *  null means "nothing to resume from", the stored characters stay exactly as
 *  they are, and only a deliberate change by the reader later overwrites
 *  them. A valid envelope whose LAYOUT alone cannot be read keeps the rest of
 *  itself -- the readings and the margin are still theirs. */
export function readEnvelope(text: string | null): WorkspaceEnvelope | null {
  if (text === null) return null
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return null
  }
  if (!isObject(raw) || raw.version !== ENVELOPE_VERSION) return null
  return {
    version: ENVELOPE_VERSION,
    touched: raw.touched === true,
    selectedPage: str(raw.selectedPage) ? raw.selectedPage : CONVERSATION_PAGE,
    destinations: mapOf(raw.destinations, readDestination),
    layout: readLayout(raw.layout),
    readings: mapOf(raw.readings, readReading),
    rooms: mapOf(raw.rooms, readRoom),
  }
}

export const emptyEnvelope = (): WorkspaceEnvelope => ({
  version: ENVELOPE_VERSION,
  touched: false,
  selectedPage: CONVERSATION_PAGE,
  destinations: {},
  layout: null,
  readings: {},
  rooms: {},
})

/* -- merging a change in --------------------------------------------------- */

/** ONLY WHAT IS SUPPLIED MOVES, and a map moves entry by entry: remembering
 *  where the margin was must not replace the Page list, the layout or another
 *  Page's reading. An explicit null removes a map entry; a room merges
 *  partially, as `onRoom` hands it over. */
function merge(base: WorkspaceEnvelope, patch: WorkspacePatch): WorkspaceEnvelope {
  const next: WorkspaceEnvelope = {
    ...base,
    ...(patch.touched !== undefined ? { touched: patch.touched } : {}),
    ...(patch.selectedPage !== undefined ? { selectedPage: patch.selectedPage } : {}),
    ...(patch.layout !== undefined ? { layout: patch.layout } : {}),
  }
  if (patch.destinations) {
    next.destinations = { ...base.destinations }
    for (const [page, value] of Object.entries(patch.destinations)) {
      if (value === null) delete next.destinations[page]
      else next.destinations[page] = value
    }
  }
  if (patch.readings) {
    next.readings = { ...base.readings }
    for (const [page, value] of Object.entries(patch.readings)) {
      if (value === null) delete next.readings[page]
      else next.readings[page] = value
    }
  }
  if (patch.rooms) {
    next.rooms = { ...base.rooms }
    for (const [page, value] of Object.entries(patch.rooms)) {
      if (value === null) {
        delete next.rooms[page]
        continue
      }
      /* A ROOM MERGES PARTIALLY, as `onRoom` hands it over: changing the mode
         does not forget the width the separator was dragged to. A Page with
         no room yet starts at Single chat and the readable floor; L clamps
         upwards from there and owns the roomier initial widths. */
      const had = base.rooms[page]
      next.rooms[page] = {
        mode: value.mode ?? had?.mode ?? 'single',
        readingPx: value.readingPx ?? had?.readingPx ?? READABLE,
      }
    }
  }
  return next
}

/* -- what is held per identity -------------------------------------------- */

interface Held {
  /** THE LAST COPY KNOWN TO BE IN STORAGE -- what was read back, or what was
   *  written -- which the changes not yet written are re-applied OVER. While
   *  the Brain is unknown there is no stored copy, so this is where its
   *  memory-only session starts from. */
  base: WorkspaceEnvelope
  envelope: WorkspaceEnvelope
  /** a valid envelope was read back from, or written to, storage */
  stored: boolean
  /** this copy is worth answering with: it was read or changed */
  live: boolean
  /** THE CHANGES THIS TAB OWES STORAGE, in order: the patches merged in memory
   *  that no successful write has yet included. They are what makes a write a
   *  change to the FIELDS THIS TAB PATCHED rather than a replacement of the
   *  whole envelope, and they are what a refused write keeps hold of. */
  dirty: WorkspacePatch[]
  /** a change is owed to storage: it is cleared by a write that succeeded */
  waiting: boolean
  timer: ReturnType<typeof setTimeout> | null
  listeners: Set<() => void>
}

const held = new Map<string, Held>()

const idOf = (identity: WorkspaceIdentity): string =>
  `${identity.brain ?? ''}\u0000${identity.conversation}`

function blank(): Held {
  return {
    base: emptyEnvelope(),
    envelope: emptyEnvelope(),
    stored: false,
    live: false,
    dirty: [],
    waiting: false,
    timer: null,
    listeners: new Set(),
  }
}

function slot(identity: WorkspaceIdentity): Held {
  const id = idOf(identity)
  const had = held.get(id)
  if (had) return had
  const h = blank()
  held.set(id, h)
  if (identity.brain === null) return h
  const got = readEnvelope(readRaw(workspaceKey(identity.brain, identity.conversation)))
  if (got) {
    h.base = got
    h.envelope = got
    h.stored = true
    h.live = true
  }
  /* WHAT WAS DONE BEFORE THE BRAIN WAS KNOWN is not lost when it becomes
     known: the patches made against the pending identity are taken over as
     this identity's own unwritten changes, in order, and written for the
     first time here. */
  const pending = held.get(idOf({ brain: null, conversation: identity.conversation }))
  if (pending && pending.dirty.length) {
    h.dirty.push(...pending.dirty)
    h.live = true
    h.waiting = true
    pending.dirty = []
    commit(identity, h)
  }
  return h
}

const tell = (h: Held) => {
  for (const fn of [...h.listeners]) fn()
}

/** THE LATEST STORED COPY. Another tab may have changed it since this one
 *  read it, and the last completed change to a field is the one that holds.
 *  Where there is nothing readable there -- a pending Brain, refused storage,
 *  another tab's unreadable characters -- the last copy this tab knows was
 *  stored stands in, so a change is never merged into a blank. */
function stored(identity: WorkspaceIdentity, h: Held): WorkspaceEnvelope {
  if (identity.brain === null) return h.base
  return readEnvelope(readRaw(workspaceKey(identity.brain, identity.conversation))) ?? h.base
}

/** THE ENVELOPE AS IT STANDS: what is in storage now, with this tab's own
 *  unwritten changes over it, field by field.
 *
 *  Both halves matter. Re-reading storage is why ANOTHER TAB'S selection or
 *  layout survives a write of ours that was only ever about a room; keeping
 *  the patches is why a REFUSED write loses nothing -- the next change still
 *  builds on everything this session did, not on the older persisted copy. */
function rebuild(identity: WorkspaceIdentity, h: Held): WorkspaceEnvelope {
  let out = stored(identity, h)
  for (const patch of h.dirty) out = merge(out, patch)
  return out
}

/** WRITE WHAT IS OWED, MERGED AT WRITE TIME -- never the whole envelope as it
 *  was held when the change was made. A write that succeeds is the new base
 *  and clears the debt; a write that is refused keeps it, so the session goes
 *  on remembering what storage would not take. */
function commit(identity: WorkspaceIdentity, h: Held): void {
  if (h.timer) {
    clearTimeout(h.timer)
    h.timer = null
  }
  h.envelope = rebuild(identity, h)
  if (identity.brain === null) {
    /* no key names an unknown Brain, so there is no write to wait for */
    h.waiting = false
    return
  }
  if (writeRaw(workspaceKey(identity.brain, identity.conversation), JSON.stringify(h.envelope))) {
    h.base = h.envelope
    h.dirty = []
    h.waiting = false
    h.stored = true
  }
}

/** THE VALIDATED ENVELOPE FOR THIS IDENTITY, or null where there is no valid
 *  snapshot to resume from. Malformed storage is left exactly as it is. */
export function readWorkspace(identity: WorkspaceIdentity): WorkspaceEnvelope | null {
  const h = slot(identity)
  return h.live ? h.envelope : null
}

/** Whether a valid envelope exists in storage for this identity. false is
 *  honest rather than empty: a first visit, refused storage and an unresolved
 *  Brain all read false and all leave a usable session. */
export function hasWorkspace(identity: WorkspaceIdentity): boolean {
  return slot(identity).stored
}

/** Merge a change into this identity's envelope and persist it. */
export function patchWorkspace(
  identity: WorkspaceIdentity,
  patch: WorkspacePatch,
  options: PatchOptions = {},
): WorkspaceEnvelope {
  const h = slot(identity)
  h.dirty.push(patch)
  h.live = true
  h.waiting = true
  if (options.coalesce) {
    h.envelope = rebuild(identity, h)
    if (!h.timer) h.timer = setTimeout(() => commit(identity, h), COALESCE_MS)
  } else {
    commit(identity, h)
  }
  tell(h)
  return h.envelope
}

/** COMMIT WHAT IS WAITING, NOW. Called at `pagehide` and
 *  `visibilitychange`-hidden, and before leaving a destination -- the moments
 *  after which there may be no later chance. */
export function flushWorkspace(identity: WorkspaceIdentity): void {
  const h = held.get(idOf(identity))
  if (!h || !h.waiting) return
  commit(identity, h)
}

/** Changes to this identity's envelope, including ones another tab made (the
 *  `storage` event). A listener is told that it changed; what it does about it
 *  is its own -- in particular, nothing here moves a surface being read. */
export function subscribeWorkspace(identity: WorkspaceIdentity, listener: () => void): () => void {
  const h = slot(identity)
  h.listeners.add(listener)
  const key = identity.brain === null ? null : workspaceKey(identity.brain, identity.conversation)
  const changed = (e: StorageEvent) => {
    if (key === null || (e.key !== null && e.key !== key)) return
    const got = readEnvelope(readRaw(key))
    if (!got) return
    /* AN EVENT IS NOT DROPPED BECAUSE A WRITE OF OURS IS WAITING. What the
       other tab wrote becomes the base, and this tab's own unwritten changes
       go back over it: each tab's last completed change to a FIELD holds, and
       neither tab's whole envelope wins. Nothing here moves a surface being
       read -- the listener is told, and what it does about it is its own. */
    h.base = got
    h.envelope = h.dirty.length ? rebuild(identity, h) : got
    h.stored = true
    h.live = true
    tell(h)
  }
  if (key !== null && typeof window !== 'undefined') window.addEventListener('storage', changed)
  return () => {
    h.listeners.delete(listener)
    if (key !== null && typeof window !== 'undefined') window.removeEventListener('storage', changed)
  }
}

/** Forget what is held in memory. Storage is untouched: this is for a test or
 *  a re-resolved Brain, not a way to delete somebody's bookmark. */
export function forgetWorkspace(identity?: WorkspaceIdentity): void {
  if (!identity) {
    for (const h of held.values()) if (h.timer) clearTimeout(h.timer)
    held.clear()
    return
  }
  const id = idOf(identity)
  const h = held.get(id)
  if (h?.timer) clearTimeout(h.timer)
  held.delete(id)
}

/* -- the travelling floats ------------------------------------------------- */

/** The owner's pinned travelling floats, as this browser left them. Validated
 *  by Fluid's own `readTravel`, so an entry this build cannot read is left out
 *  rather than guessed at. A pending Brain has none to read. */
export function readTravelBookmark(brain: string | null): Float[] {
  if (brain === null) return []
  const text = readRaw(travelKey(brain))
  if (text === null) return []
  try {
    return readTravel(JSON.parse(text))
  } catch {
    return []
  }
}

/** Mirror them for the next session. A pending Brain writes nothing. */
export function writeTravelBookmark(brain: string | null, value: Float[]): void {
  if (brain === null) return
  writeRaw(travelKey(brain), JSON.stringify(value))
}

/* -- which browser copy wins (F9) ------------------------------------------ */

const sessionText = (key: string): string | null => {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage.getItem(key)
  } catch {
    return null
  }
}

/** WHICH SNAPSHOT THE HOLDER ENTERS, and whether it is protected.
 *
 *  Same-tab reload: the session copy the Holder itself wrote, with ITS
 *  touched state. A new session with no valid tab copy: this envelope's
 *  durable layout, with the envelope's touched state. Either way the answer
 *  carries `protect: true`, which is W1's instruction that the delayed Brain
 *  read and the untouched-session replacement beside it may NOT take it away
 *  or merge shared geometry over it -- a reader's own arrangement is theirs
 *  even when they changed nothing in it this time. Snapshot protection is
 *  tracked apart from `touched`, which keeps its unsaved-edits meaning.
 *
 *  THE DECISION IS S'S; ENTERING IT IS W1'S HOLDER. `session` is injectable
 *  so the choice can be checked without a browser. */
export function chooseSnapshot(
  identity: WorkspaceIdentity,
  options: { placeKey?: string; session?: (key: string) => string | null } = {},
): BrowserSnapshot | null {
  const key = options.placeKey ?? identity.conversation
  const read = options.session ?? sessionText
  let text: string | null = null
  try {
    text = read(SESSION + key)
  } catch {
    text = null
  }
  if (text !== null) {
    let raw: unknown = null
    try {
      raw = JSON.parse(text)
    } catch {
      raw = null
    }
    const layout = readLayout(raw)
    if (layout) {
      let touched = false
      try {
        touched = read(SESSION + key + SESSION_TOUCHED) === '1'
      } catch {
        touched = false
      }
      return { from: 'session', layout, touched, protect: true }
    }
  }
  const envelope = readWorkspace(identity)
  if (envelope?.layout)
    return { from: 'local', layout: envelope.layout, touched: envelope.touched, protect: true }
  return null
}

/* -- the provider ---------------------------------------------------------- */

const Bookmark = createContext<WorkspaceBookmarkValue | null>(null)

/** The envelope as it stands, subscribed. The store is outside React and
 *  tells its listeners when it changed, so the snapshot is stable between
 *  changes and a render never writes anything. */
function useEnvelope(identity: WorkspaceIdentity | null): WorkspaceEnvelope | null {
  const key = identity ? idOf(identity) : ''
  const subscribe = useCallback(
    (listener: () => void) => (identity ? subscribeWorkspace(identity, listener) : () => {}),
    [key],
  )
  const snapshot = useCallback(() => (identity ? slot(identity).envelope : null), [key])
  return useSyncExternalStore(subscribe, snapshot, snapshot)
}

/** WHICH BRAIN THIS IS (F10), read once through the existing endpoint. null
 *  while it has not answered: memory-only, and no key written. */
function useBrain(): string | null {
  const [brain, setBrain] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    void brainIdentity().then(
      (b) => {
        /* RESOLVED WITHOUT A corpus_id IS 'local': the Brain that has no
           name, not the Brain that is not known yet. */
        if (live && b) setBrain(b.corpus_id || LOCAL_BRAIN)
      },
      () => {
        /* A failed identity read leaves the session in memory, working. */
      },
    )
    return () => {
      live = false
    }
  }, [])
  return brain
}

/** THE BOOKMARK FOR ONE ORIGIN CONVERSATION, for everything mounted under it.
 *
 *  Mounted ONCE by the shell (R). The margin, the Page controls and the
 *  working area read their identity from here rather than being handed a
 *  bookmark prop apiece (F4), which is why `useRail` and `Rail` keep the
 *  signatures they already have. */
export function WorkspaceBookmarkProvider(props: {
  originConversation: Id
  /** the Page being read; Conversation when nothing says otherwise */
  page?: string
  children?: ReactNode
}): ReactNode {
  const brain = useBrain()
  const page = props.page ?? CONVERSATION_PAGE
  const identity = useMemo<WorkspaceIdentity>(
    () => ({ brain, conversation: props.originConversation }),
    [brain, props.originConversation],
  )
  const envelope = useEnvelope(identity) as WorkspaceEnvelope
  const [location, setLocation] = useState<QuietLocation | null>(null)
  const [restoring, setRestoring] = useState(true)

  const patch = useCallback(
    (p: WorkspacePatch, options?: PatchOptions) => {
      patchWorkspace(identity, p, options)
    },
    [identity],
  )
  const flush = useCallback(() => flushWorkspace(identity), [identity])
  const settle = useCallback(() => setRestoring(false), [])

  /* LEAVING THE TAB IS THE LAST CHANCE TO WRITE. Coalesced work is committed
     at pagehide and when the page becomes hidden; each fires where the other
     does not, and neither is a Brain save. */
  useEffect(() => {
    const leave = () => flushWorkspace(identity)
    const hidden = () => {
      if (document.visibilityState === 'hidden') flushWorkspace(identity)
    }
    window.addEventListener('pagehide', leave)
    document.addEventListener('visibilitychange', hidden)
    return () => {
      window.removeEventListener('pagehide', leave)
      document.removeEventListener('visibilitychange', hidden)
      flushWorkspace(identity)
    }
  }, [identity])

  const value = useMemo<WorkspaceBookmarkValue>(
    () => ({
      identity,
      page,
      envelope,
      stored: hasWorkspace(identity),
      patch,
      flush,
      location,
      intend: setLocation,
      restoring,
      settle,
    }),
    [identity, page, envelope, patch, flush, location, restoring, settle],
  )
  return createElement(Bookmark.Provider, { value }, props.children)
}

/** THE BOOKMARK, from the provider the shell mounted -- or for an identity
 *  named outright, which is how something outside the shell reads one.
 *
 *  null means no provider is mounted and no identity was named: honest,
 *  rather than an empty envelope that would look like a fresh arrival. */
export function useWorkspaceBookmark(identity?: WorkspaceIdentity): WorkspaceBookmarkValue | null {
  const mounted = useContext(Bookmark)
  const named = identity ?? null
  const key = named ? idOf(named) : ''
  const envelope = useEnvelope(named)
  const [location, setLocation] = useState<QuietLocation | null>(null)
  const direct = useMemo<WorkspaceBookmarkValue | null>(
    () =>
      named && envelope
        ? {
          identity: named,
          page: envelope.selectedPage || CONVERSATION_PAGE,
          envelope,
          stored: hasWorkspace(named),
          patch: (p: WorkspacePatch, options?: PatchOptions) => patchWorkspace(named, p, options),
          flush: () => flushWorkspace(named),
          location,
          intend: setLocation,
          restoring: false,
          settle: () => {},
        }
        : null,
    [key, envelope, location],
  )
  return direct ?? mounted
}
