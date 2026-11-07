/* THE SEAM. Quiet Chat is built by ten packages at once, so the shape each
 * one mounts by is declared here once and nowhere else.
 *
 * P0 is the only commit that writes this file. After it, a package changes
 * the BODY of the modules it owns and nothing else: not this file, not
 * QuietChat.tsx, not another package's module. `tests/quiet_seam_unit.mjs`
 * asserts every entry in ENTRIES exists and exports what it declares here,
 * so a package that renames or drops its entry fails before it is merged.
 */
import type { Activity, Conversation, ConversationSummary, Id, Part, Turn } from '../api'
import type { Attempt, PostingAction } from './model'

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
]
