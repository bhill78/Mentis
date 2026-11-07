/* WHAT QUIET REMEMBERS ABOUT A PLACE, as data. Round 5, package S.
 *
 * TYPE-ONLY, DELIBERATELY. `contract.ts` stays the one declaration of what
 * each package MOUNTS; this file is the one declaration of what the browser
 * KEEPS and what the destination contract names. Nothing here is a second
 * contract.ts (F2) and nothing here is a runtime export (F22): a module that
 * only declares shapes cannot drift, and the seam test asks it for no
 * functions.
 *
 * THE ENVELOPE IS BROWSER STATE, NOT A RECORD. Remembering where somebody was
 * reading is not a fact about the corpus, so none of this is ever saved to a
 * Brain and no Brain save is triggered by writing it (`bookmarks.ts`).
 */
import type { Id } from '../../api'
import type { Dived, Place } from '../../fluid/actions'
import type { RailName } from '../contract'
import type { Page as BatchCursor } from '../model'

/* -- the destination contract ---------------------------------------------- */

/** WHAT A QUIET PAGE IS FOR, beside the Fluid arrangement that Page already
 *  is. The origin conversation owns ONE existing Fluid Holder arrangement and
 *  its ordered `nav.pages`; this is the extra thing Quiet knows about one of
 *  them, keyed by the ACTUAL FLUID PAGE ID. A conversation is never encoded
 *  as an object address and the Brain arrangement format does not change. */
export type QuietDestination =
  | { kind: 'workspace' }
  | {
    kind: 'deep-dive'
    /** the real separate Conversation `actions.deepDive` returned */
    conversation: Id
    openingTurn: Id
    /** where it was dived from, exactly: `place` is the existing
     *  `fluid/actions.ts` Place, so its passage and version are preserved. */
    origin: { conversation: Id; page: string; post: Id; place: Place }
  }

/** ONE PAGE OF THE SEQUENCE, as the Page controls draw it (F23). The batch
 *  cursor in `quiet/model.ts` is also called `Page` and is a different thing
 *  entirely -- which half of a reading has been loaded. Nothing named `Page`
 *  describes a destination. */
export interface QuietSequencePage {
  id: string
  title: string
}

/** Where a nested action asks to go, routed through `WorkingArea.onNavigate`
 *  rather than applied where it was raised: no action inside the working area
 *  may switch the conversation while the Holder keeps the wrong owner. */
export type QuietNavigate = (to: { conversation: Id; topic?: Id | null; turn?: Id | null }) => void

/** What `DeepDiveAction` reports when the existing command succeeded: the
 *  Dived answer, and the Place the selection was actually made against. */
export type QuietDived = (dived: Dived, place: Place) => void

/* -- the room ------------------------------------------------------------- */

export type RoomMode = 'single' | 'panes' | 'board'

/** HOW THE ROOM IS ARRANGED on this Page. `readingPx` is the reading
 *  column's own width, which the separator drags; a narrow screen's choice of
 *  which single surface is active is DRAWING STATE and is deliberately not
 *  here, so a phone cannot overwrite a desktop's room. */
export interface RoomBookmark {
  mode: RoomMode
  readingPx: number
}

/* -- the reading ---------------------------------------------------------- */

/** WHERE A POST WAS ON THE SCREEN. `offset` is the signed distance from the
 *  visible reading viewport's top to the post's top, with a pinned header
 *  accounted for -- not `document.scrollTop`, which means nothing once the
 *  heights change, and not an arbitrary loaded id. */
export interface ReadingAnchor {
  post: Id
  offset: number
}

/** The conversation (or child conversation) being read: which topic filters
 *  it, which half of it is loaded, and which visible post was where. */
export interface ReadingFlow {
  topic: Id | null
  /** `quiet/model.ts`'s existing batch cursor, under its own name */
  batch: BatchCursor
  anchor: ReadingAnchor | null
}

/** An open thread. `target` is the post being read inside it and `replyTo`
 *  the one the composer is answering -- they are not the same choice, and a
 *  restored reply must never silently answer something else. */
export interface ReadingThread {
  root: Id
  target: Id
  replyTo: Id
  anchor: ReadingAnchor | null
}

/** The margin's own reading. Participant selection is NOT here: the
 *  authoritative store is `quiet/filter/who.ts`'s
 *  `mentis:quiet:who:<effectiveConversation>` and a second copy would
 *  disagree with it. */
export interface ReadingMargin {
  reading: RailName | null
  searchOpen: boolean
  query: string
  /** scrollTop per reading, for the ones that have been scrolled */
  scrollByReading: Partial<Record<RailName, number>>
}

export interface ReadingBookmark {
  flow: ReadingFlow
  thread: ReadingThread | null
  margin: ReadingMargin
}

/* -- the envelope --------------------------------------------------------- */

/** ONE ENVELOPE PER ORIGIN CONVERSATION, version 1.
 *
 *  `layout` is the existing `toLayout(..., { tab: true })` representation,
 *  device placements included, and is the ONLY place Page order, titles and
 *  trees are kept -- `destinations`, `readings` and `rooms` are keyed BY Page
 *  id and never duplicate the list itself.
 *
 *  `touched` is the Holder's semantic unsaved-edits flag, not a
 *  navigation-or-scroll dirty bit: a reader who scrolled has changed nothing. */
export interface WorkspaceEnvelope {
  version: 1
  touched: boolean
  selectedPage: string
  destinations: Record<string, QuietDestination>
  layout: Record<string, unknown> | null
  readings: Record<string, ReadingBookmark>
  rooms: Record<string, RoomBookmark>
}

/** WHICH ENVELOPE. `brain` is the Brain's `corpus_id`, 'local' where identity
 *  resolved without one, and null while it has not resolved at all -- which
 *  is memory-only, because an unknown-Brain key would be a lie (F10). */
export interface WorkspaceIdentity {
  brain: string | null
  conversation: Id
}

/** A CHANGE TO PART OF THE ENVELOPE. Only the fields supplied are merged, and
 *  a map here merges entry by entry: remembering where the margin was must
 *  not replace the Page list or another Page's reading. An explicit null in a
 *  map removes that entry; `rooms` takes a partial room, as `onRoom` does. */
export interface WorkspacePatch {
  touched?: boolean
  selectedPage?: string
  layout?: Record<string, unknown> | null
  destinations?: Record<string, QuietDestination | null>
  readings?: Record<string, ReadingBookmark | null>
  rooms?: Record<string, Partial<RoomBookmark> | null>
}

export interface PatchOptions {
  /** coalesce the write: scrolling is remembered, not persisted per pixel.
   *  `flushWorkspace` commits whatever is still waiting. */
  coalesce?: boolean
}

/* -- where the browser's copy came from (F9) ------------------------------- */

/** A VALIDATED BROWSER SNAPSHOT, chosen by S and entered by W1's Holder.
 *
 *  `from: 'session'` is the same-tab reload copy (`mentis.fluid.arr:<key>`
 *  and its `:changed` flag) and wins; `from: 'local'` is this envelope's
 *  durable layout, which a NEW SESSION uses. Either is PROTECTED: the delayed
 *  Brain read and the untouched-session replacement may not take it away or
 *  merge shared geometry over it, even at `touched: false`. Snapshot
 *  protection is tracked apart from `touched` on purpose -- they answer
 *  different questions. */
export interface BrowserSnapshot {
  from: 'session' | 'local'
  layout: Record<string, unknown>
  touched: boolean
  protect: true
}

/* -- where Quiet is, in the browser's address ------------------------------ */

/** ONE DESTINATION, as the hash names it:
 *  `#/c/<origin>/t/<topic>/turn/<target>/qpage/<page>`. The conversation is
 *  always the ORIGIN -- the Holder's owner -- and the Page says which
 *  effective conversation is read there. */
export interface QuietLocation {
  originConversation: Id
  topic: Id | null
  turn: Id | null
  page: string
}

/** Which Page a resumed arrival actually opens, and why. `unknownPage` names
 *  a Page the address asked for that this browser does not have (another
 *  browser's, or one since closed): Conversation is opened instead and the
 *  reader is told, rather than landing nowhere. */
export interface QuietResume {
  location: QuietLocation
  from: 'address' | 'bookmark' | 'default'
  unknownPage: string | null
}

/* -- what the provider gives its descendants ------------------------------- */

export interface WorkspaceBookmarkValue {
  /** WHICH BRAIN, DECIDED OR NOT (F10). 'pending' until `brainIdentity()`
   *  settles; 'resolved' once it named a Brain (a `corpus_id`, or 'local'
   *  where it resolved without one); 'unavailable' when it resolved null,
   *  rejected, or storage itself cannot be written to -- every one of those
   *  is a memory-only session, with no key ever written for it. A gate that
   *  needs to tell "still deciding" from "never will" reads this, not
   *  `brain`. */
  identity: 'pending' | 'resolved' | 'unavailable'
  /** the Page `readings`, `rooms` and `destinations` are read at */
  page: string
  envelope: WorkspaceEnvelope
  /** a valid stored envelope was found for this identity. false is honest
   *  rather than empty: a first visit, refused storage, or an unresolved
   *  Brain, all of which leave a usable in-memory session. */
  stored: boolean
  patch: (patch: WorkspacePatch, options?: PatchOptions) => void
  flush: () => void
  /** THE ONE DESTINATION INTENT. Quiet's location controller is the only
   *  writer of the hash; everything that wants to go somewhere says so here. */
  location: QuietLocation | null
  intend: (location: QuietLocation) => void
  /** true while a bookmark is being restored: capture is suppressed, so
   *  restoration cannot record itself over what it is restoring. */
  restoring: boolean
  settle: () => void
}

/* -- what the Holder adapter gives the shell ------------------------------- */

/** WHAT `useWorkspaceRuntime` ANSWERS. One hook, one Holder entrance, one
 *  history path: W2 replaces the body, and no second entrance effect is
 *  added beside it. */
export interface WorkspaceRuntime {
  /** the Holder has entered and its Pages are hydrated */
  ready: boolean
  pages: QuietSequencePage[]
  page: string
  selectPage: (page: string) => void
  addPage: () => void
  closePage: (page: string) => void
  /** the measured working stage, for the object hosts and Tidy */
  setArea: (element: HTMLElement | null) => void
}
