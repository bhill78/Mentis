/* THE SEAM. Quiet Chat is built by many packages at once, so the shape each
 * one mounts by is declared here once and nowhere else.
 *
 * ONE PACKAGE A ROUND WRITES THIS FILE, and it is the package that freezes
 * the round's contracts before anybody builds against them -- P0 in round
 * zero, S in round five. After that commit, a package changes the BODY of the
 * modules it owns and nothing else: not this file, not QuietChat.tsx, not
 * another package's module. `tests/quiet_seam_unit.mjs` asserts every entry
 * in ENTRIES exists and exports what it declares here, so a package that
 * renames or drops its entry fails before it is merged.
 *
 * (The claim that P0 is the ONLY commit that ever writes this file was true
 * of round zero and stopped being true when round five added nine modules to
 * the manifest; what holds is the rule above, which is what that claim was
 * for.)
 *
 * WHAT EACH PACKAGE MOUNTS IS HERE; WHAT THE BROWSER KEEPS IS IN
 * `workspace/types.ts`. That file is type-only and is not a second contract:
 * it declares the envelope, the destinations and the bookmarks, and this one
 * declares the components and hooks that read them.
 */
import type { Activity, Conversation, ConversationSummary, Id, Part, Turn } from '../api'
import type { Addressee, Mark, Use } from '../composer/draft'
import type { Attempt, PostingAction } from './model'
import type {
  QuietDived,
  QuietNavigate,
  QuietSequencePage,
  RoomBookmark,
  WorkspaceRuntime,
} from './workspace/types'

/** The conversation's topics, as every package reads them. */
export type Topics = Conversation['topics']

/** Which contextual reading the rail is showing, or none. `carried` is round
 *  four's: what each post carries, presented beside the stream. */
export type RailName = 'topics' | 'brief' | 'activity' | 'carried'

/** WHAT IS BEING WRITTEN, lifted out of the reading column.
 *
 *  The composer is mounted once, in the dock below the stream, so it is
 *  outside the region that scrolls. The page doing the reading says what the
 *  composer is for -- a reply to one post, or the conversation itself -- and
 *  says nothing until it has read enough to know. `null` means the dock shows
 *  no composer at all, which is what a page that has not loaded yet means. */
export type Compose = { reply: Turn | null }
export type SetCompose = (compose: Compose | null) => void

/** One unsent message, with the settling key its last failed attempt used.
 *  Held outside the tree by `composer/drafts.ts`, so moving between the
 *  conversation, a topic and a thread does not throw words away. */
export interface Draft {
  text: string
  action: PostingAction
  op: string
  sent?: Attempt
  /* -- WHAT THE `@`, `#` AND `/` PALETTES LAND IN IT (round 4, track A) -----
   *
   *  Fluid's own four fields, by their own types, so `bodyOf` reads a Quiet
   *  draft exactly as it reads a Fluid one and a post written here is the same
   *  fact as one written there. Each is OPTIONAL rather than defaulted,
   *  because a draft recorded before these existed -- and every other
   *  package's `{ ...draft }` -- has to keep meaning what it meant. */
  /** whom this post addresses, and which of them was asked to work
   *  (`Addressee.dispatch`, never inferred from a mention) */
  to?: Addressee[]
  /** Topic MEMBERSHIP: this post is filed under these. */
  topics?: Id[]
  /** Authored inline references: these characters name that Topic, post or
   *  conversation. A different fact from membership; neither implies the other. */
  marks?: Mark[]
  /** The Workflow or standing material named for this work, as `/` attaches
   *  it and the "Use…" picker names it. */
  use?: Use
}
/** `ifOp` guards the write: a draft that has moved on is not overwritten by
 *  an answer belonging to the one before it. */
export type SetDraft = (draft: Draft, ifOp?: string) => void

/* -- what each package mounts ---------------------------------------------- */

/** G: the painted ground every other package sits on. */
export type SurfaceView = (props: { children: React.ReactNode }) => React.ReactNode
/** G: choosing and persisting the atmosphere, in the header's right cell. */
export type BackgroundControlView = () => React.ReactNode

/** THE CONVERSATION LIST, read ONCE by the shell and handed to whichever of
 *  A's regions is showing. `useApi` holds its state per reader, so two
 *  readers of `/api/conversations` would be two reads of it and two
 *  independent failures; the shell reads, and the packages render. */
export interface ConversationsRead {
  choices: ConversationSummary[]
  loaded: boolean
  loading: boolean
  error: string | null
  reload: () => void
}

/** A: the global header -- brand, the centre cell the reading column
 *  continues through, and the way out to Fluid. */
export type ChromeView = (props: {
  conversation: Id | null
  conversations: ConversationsRead
}) => React.ReactNode
/** A: conversation navigation, in the work row's first cell. */
export type ConversationNavView = (props: {
  conversation: Id | null
  conversations: ConversationsRead
}) => React.ReactNode
/** A: the welcome page, when no conversation is addressed. */
export type WelcomeView = (props: { conversations: ConversationsRead }) => React.ReactNode
/** A: the conversation's eyebrow and title. */
export type HeadingView = (props: {
  name: string | null
  /** the addressed topic's name; null while it is still being read, and
   *  undefined when no topic is addressed at all */
  topic?: string | null
}) => React.ReactNode

/** B: the contextual margin, in the work row's third cell. */
export type RailView = (props: {
  rail: RailName
  close: () => void
  conversation: Id
  topic: Id | null
  facts: Conversation | null
}) => React.ReactNode
/** B: the controls that choose which reading the margin shows. */
export type RailToolsView = (props: {
  rail: RailName | null
  choose: (rail: RailName | null) => void
}) => React.ReactNode

/** D: live runs and what they are working on, inside B's margin. */
export type ActivityPanelView = (props: { conversation: Id; topic: Id | null }) => React.ReactNode
/** D: open decisions, answerable where they are shown. */
export type DecisionsView = (props: { conversation: Id; topic: Id | null }) => React.ReactNode

/** E: one post. */
export type PostView = (props: {
  turn: Turn
  conversation: Id
  topic: Id | null
  topics: Topics
  inThread?: boolean
  selected?: boolean
  onReply?: () => void
  /** ROUND 5 (R, F5): the footer's action slot, given a LIVE accessor for this
   *  post's own drawn body. Deep dive captures a passage against the Source
   *  that is actually on the screen, which is this element -- so the action
   *  that needs it is handed it here and Post never has to be edited again for
   *  it. Omitted, the footer is exactly what it was. */
  action?: (body: () => HTMLElement | null) => React.ReactNode
}) => React.ReactNode
/** E: one part of a post's body. */
export type PostPartView = (props: { part: Part; scope: string }) => React.ReactNode

/** F: a part that is a file or an image. */
export type MediaPartView = (props: { part: Part; scope: string }) => React.ReactNode
/** F: the gallery overlay, mounted once beside the shell. */
export type MediaLayerView = () => React.ReactNode

/** C: the one composer, in the dock. */
export type ComposerView = (props: {
  conversation: Id
  topic: Id | null
  me: Id | null
  reply: Turn | null
  draft: Draft
  setDraft: SetDraft
  onPosted: (id: Id) => void
}) => React.ReactNode

/** The run rows D reads, named here because `api.ts` declares their shape
 *  and D must not widen a frozen file to use them. */
export type ActivityRuns = NonNullable<Activity['activity'][number]['runs']>

/* -- round five: the Page sequence, the room and the working area ---------- */

/** R5-P: the horizontal Page sequence. Conversation is always first and is
 *  the existing `this-post` Page under its Quiet label -- never a second
 *  conversation Page implementation. `canAdd` is false where the origin
 *  Holder is not ready or no workspace is available: making a Page is
 *  browser arrangement work and is not permission to create a conversation. */
export type PageStripView = (props: {
  originConversation: Id
  pages: QuietSequencePage[]
  current: string
  onSelect: (page: string) => void
  onAdd: () => void
  canAdd: boolean
}) => React.ReactNode

/** R5-P: previous and next, by destination. null at an unavailable end, which
 *  is what disables that control -- the ends are not wrapped around. */
export type PageArrowsView = (props: {
  previous: QuietSequencePage | null
  next: QuietSequencePage | null
  onSelect: (page: string) => void
}) => React.ReactNode

/** R5-L: the room, with ALL FOUR fixed slots (F11). The saved mode says which
 *  main surface is visible and active; a parked surface is inert or hidden
 *  and is never an absent slot, and the Page controls are reachable in every
 *  applicable mode. These names and these mount identities are fixed: L
 *  replaces the body and keeps them. */
export type WorkspaceRoomView = (props: {
  originConversation: Id
  page: string
  room: RoomBookmark
  onRoom: (room: Partial<RoomBookmark>) => void
  conversation: React.ReactNode
  tools: React.ReactNode
  working: React.ReactNode
  pageControls: React.ReactNode
}) => React.ReactNode

/** R5-W2: the bounded working stage. `onNavigate` is the ONE way out of it:
 *  anything inside that wants another conversation asks here rather than
 *  switching while the Holder keeps the wrong owner. */
export type WorkingAreaView = (props: {
  originConversation: Id
  effectiveConversation: Id
  page: string
  readingPost: Id | null
  onNavigate: QuietNavigate
}) => React.ReactNode

/** R5-W2: R's SOLE Holder and nav adapter hook. One entrance, one history
 *  path; no second entrance effect is added beside it. */
export type WorkspaceRuntimeHook = (args: {
  originConversation: Id
  effectiveConversation: Id
  page: string
  readingPost: Id | null
}) => WorkspaceRuntime

/** R5-W2: everything inside the working stage that needs Fluid's own hosts --
 *  governance, actions, the toast layer and the sheet layer. */
export type WorkingProvidersView = (props: {
  originConversation: Id
  effectiveConversation: Id
  page: string
  onNavigate: QuietNavigate
  children?: React.ReactNode
}) => React.ReactNode

/** R5-O: the object, floating-window and Magnet hosts, scoped to the measured
 *  stage. W2 mounts it; O composes the existing hosts into it. */
export type ObjectHostsView = (props: {
  areaElement: HTMLElement | null
  originConversation: Id
  effectiveConversation: Id
  page: string
  onNavigate: QuietNavigate
}) => React.ReactNode

/** R5-T: Tidy, at the one controls point W2 mounts, over the same area. */
export type TidyView = (props: {
  areaElement: HTMLElement | null
  originConversation: Id
  page: string
}) => React.ReactNode

/** R5-D: the Deep dive action in a post. `body` is a LIVE accessor for that
 *  rendered post's body element (F5), so D captures a selection against the
 *  Source actually drawn and never needs an edit to Post. */
export type DeepDiveActionView = (props: {
  post: Turn
  body: () => HTMLElement | null
  effectiveConversation: Id
  originConversation: Id
  page: string
  onOpened: QuietDived
}) => React.ReactNode

/** R5-R: which origin, Page and effective conversation the links inside this
 *  reading belong to (F6). */
export type QuietNavigationView = (props: {
  originConversation: Id
  effectiveConversation: Id
  page: string
  children?: React.ReactNode
}) => React.ReactNode

/** R5-R: how a link inside the reading is written. The same arguments as
 *  `model.href`, with the Quiet location supplied for links that stay inside
 *  the effective conversation and omitted for links that leave it. */
export type QuietHref = (conversation: Id, topic?: Id | null, turn?: Id | null) => string

/* -- the manifest the seam test reads -------------------------------------- */

/** Every module a package owns, with the exports it must keep. Read by
 *  `tests/quiet_seam_unit.mjs`; the package letter is the owner. */
export const ENTRIES: { package: string; path: string; exports: string[] }[] = [
  { package: 'G', path: './surface/Surface.tsx', exports: ['default'] },
  { package: 'G', path: './surface/BackgroundControl.tsx', exports: ['default'] },
  { package: 'A', path: './chrome/Chrome.tsx', exports: ['default', 'ConversationNav', 'Welcome'] },
  { package: 'A', path: './chrome/Heading.tsx', exports: ['default'] },
  { package: 'D', path: './chrome/Toolbar.tsx', exports: ['default'] },
  { package: 'D', path: './search/QuietSearch.tsx', exports: ['default'] },
  { package: 'B', path: './rail/Rail.tsx', exports: ['default', 'RailTools', 'useRail'] },
  { package: 'D', path: './activity/ActivityPanel.tsx', exports: ['default'] },
  { package: 'D', path: './activity/Decisions.tsx', exports: ['default'] },
  { package: 'E', path: './post/Post.tsx', exports: ['default'] },
  { package: 'E', path: './post/parts.tsx', exports: ['default'] },
  { package: 'F', path: './media/MediaPart.tsx', exports: ['default'] },
  { package: 'F', path: './media/MediaLayer.tsx', exports: ['default'] },
  { package: 'C', path: './composer/Composer.tsx', exports: ['default'] },
  { package: 'C', path: './composer/drafts.ts', exports: ['useDraft', 'clearDrafts'] },
  /* Round four, Track C: the margin's boxes, the record of what each post
     carries, the annotation layer, and the one reading of what an attachment
     is that MediaPart, the viewer and the margin all share. */
  { package: 'R4C', path: './margin/Margin.tsx', exports: ['default'] },
  { package: 'R4C', path: './margin/carried.ts', exports: ['register', 'putAway', 'present', 'useCarried'] },
  { package: 'R4C', path: './annotations/Annotations.tsx', exports: ['default'] },
  { package: 'R4C', path: './media/view.ts', exports: ['viewKindOf', 'itemOf', 'isImage'] },
  /* Round 4, track A's own modules: the participant filter that replaces the
     composer's addressing dropdown's neighbour in the reading column. The
     integrator mounts `WhoFilter`; `filterTurns` is what hides a post. */
  { package: 'C', path: './filter/WhoFilter.tsx', exports: ['WhoFilter', 'useWhoFilter', 'filterTurns'] },
  { package: 'C', path: './filter/who.ts', exports: ['useWhoFilter', 'setWhoFilter', 'clearWhoFilters', 'filterTurns'] },
  /* -- ROUND FIVE. Every new module, under the package that owns its body.
     S commits them all as importable bootstraps so that nine packages can
     mount these names at once; each later owner replaces its own body and
     keeps the declaration. A style or a type module declares no runtime
     export -- there is nothing in it to rename -- but it is listed, because
     an r5 module missing from this list is an r5 module nobody owns. */
  { package: 'R5-S', path: './workspace/types.ts', exports: [] },
  { package: 'R5-S', path: './workspace/bookmarks.ts', exports: ['WorkspaceBookmarkProvider', 'useWorkspaceBookmark', 'readWorkspace', 'patchWorkspace', 'subscribeWorkspace', 'flushWorkspace', 'readTravelBookmark', 'writeTravelBookmark', 'chooseSnapshot'] },
  { package: 'R5-S', path: './pages/location.ts', exports: ['readQuietLocation', 'writeQuietLocation', 'resumeLocation'] },
  /* S owns model.ts: its `Page` stays the batch cursor and `href` gained the
     optional Quiet location (F6/F23). Listed now because this round changed
     it and an unlisted changed module is unprotected. */
  { package: 'R5-S', path: './model.ts', exports: ['place', 'href', 'conversationPath', 'flowTurns', 'postingBody'] },
  { package: 'R5-R', path: './reader/ConversationReader.tsx', exports: ['default'] },
  { package: 'R5-R', path: './reader/navigation.tsx', exports: ['QuietNavigationProvider', 'useQuietHref'] },
  { package: 'R5-R', path: './reader/scroll.ts', exports: ['captureReadingAnchor', 'restoreReadingAnchor'] },
  { package: 'R5-R', path: './QuietChat.tsx', exports: ['default'] },
  { package: 'R5-R', path: './post/ParentHeader.tsx', exports: ['default'] },
  { package: 'R5-P', path: './pages/PageStrip.tsx', exports: ['default', 'PageStrip'] },
  { package: 'R5-P', path: './pages/PageArrows.tsx', exports: ['default', 'PageArrows'] },
  { package: 'R5-P', path: './pages/controller.ts', exports: ['usePageController'] },
  { package: 'R5-P', path: './pages/pages.css', exports: [] },
  { package: 'R5-L', path: './workspace/WorkspaceRoom.tsx', exports: ['default'] },
  { package: 'R5-L', path: './workspace/room.css', exports: [] },
  { package: 'R5-L', path: './layout.css', exports: [] },
  { package: 'R5-W2', path: './workspace/WorkingArea.tsx', exports: ['default'] },
  { package: 'R5-W2', path: './workspace/runtime.tsx', exports: ['useWorkspaceRuntime'] },
  { package: 'R5-W2', path: './workspace/providers.tsx', exports: ['WorkingProviders'] },
  { package: 'R5-W2', path: './workspace/working.css', exports: [] },
  { package: 'R5-O', path: './workspace/ObjectHosts.tsx', exports: ['default'] },
  { package: 'R5-O', path: './workspace/object-hosts.css', exports: [] },
  { package: 'R5-D', path: './deep-dive/DeepDiveAction.tsx', exports: ['default'] },
  { package: 'R5-T', path: './workspace/Tidy.tsx', exports: ['default'] },
  { package: 'R5-T', path: './workspace/tidy.ts', exports: ['tidyInArea'] },
  /* M's existing modules are already listed above under their round-four
     owners and keep those rows; these are the styles it reshapes this round,
     which were never registered. */
  { package: 'R5-M', path: './rail/rail.css', exports: [] },
  { package: 'R5-M', path: './margin/margin.css', exports: [] },
]
