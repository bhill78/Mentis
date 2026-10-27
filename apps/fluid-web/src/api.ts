import { useCallback, useEffect, useRef, useState } from 'react'
import { fluidFetch } from './fluid/http'

/* ------------------------------------------------------------------ *
 * Types mirror exactly what the API returns. Nothing is derived here. *
 * ------------------------------------------------------------------ */

export type Id = string

export interface Part {
  type: string
  text?: string
  ref?: string
  media_type?: string
  alt?: string
  /** What the server says stands behind `ref`, read at request
   *  time. Only `state: 'held'` means Mentis has the bytes. */
  artifact?: HeldState
  /** An `anchor` part, as the anchor resolves now (Anchored Interaction). */
  anchor_view?: AnchorView | null
  anchor_error?: string
}

/* ANCHORED INTERACTION. Mirrors `mentis/conversation/anchors.py`. */
export interface Selector {
  type: 'version' | 'text-range'
  version: Id
  part?: number
  start?: number
  end?: number
  unit?: 'codepoint'
}

export interface AnchorView {
  anchor: Id
  selector: Selector
  turn: Id
  conversation: Id
  by: Id
  at: number
  author: Id
  deleted: boolean
  version_is_current: boolean
  current_version: Id | null
  /** read from the immutable version now; null once the Turn is deleted */
  excerpt: string | null
  excerpt_withheld?: string
  /** the range in UTF-16 units, for drawing it in a browser */
  utf16?: { start: number; end: number }
  likeness_in_current?: { occurrences: number; is_identity: false }
}

export interface AnchorOnTurn extends AnchorView {
  reactions: { token: string; count: number }[]
  replies: Id[]
  deep_dives: Id[]
}

export interface ReactionRow {
  reaction: Id
  /** null when somebody other than the reactor deleted it: withheld. */
  token: string | null
  by: Id
  by_alias: string
  at: number
  changes: Id | null
  changed_to: Id | null
  /** The reactor's own Delete. Another actor's is `deleted_by`, not this. */
  withdrawn: boolean
  in_withdrawn_line: boolean
  deleted: boolean
  deletion?: Id
  deleted_by?: Id
  deleted_by_alias?: string
  deleted_at?: number
  token_withheld?: string
  /** Superseded by somebody else's act (generic supersede or revise), not
   *  by the reactor's own change: who did it, and with what. */
  replaced_by: ReplacedBy[]
  replaces: ReplacedBy[]
  current: boolean
}

export interface ReplacedBy {
  entry: Id
  kind: string
  by: Id
  by_alias: string
}

export interface AnchorInteractions {
  anchor: Id
  reactions: ReactionRow[]
  current: { token: string; count: number }[]
  replies: Id[]
  deep_dives: Id[]
}

export interface Origin {
  anchor: Id
  selector: Selector
  turn: Id
  conversation: Id
  conversation_name: string
  turn_author_alias: string
  anchored_by_alias: string
  why: string
  opened_by_alias: string
  deleted: boolean
  excerpt: string | null
}

/** The server's answer about a ref, never the interface's guess. */
export interface HeldState {
  ref: string
  /** held | held-but-missing | held-but-corrupt | not-held | unknown | not-an-artifact */
  state: string
  url?: string
  name?: string | null
  size?: number | null
  digest?: string
  door?: string | null
  claimed_media_type?: string | null
  treatment?: { view: string; content_type: string; claimed: string | null; agrees: boolean }
}

export interface Addressee {
  participant: Id
  alias: string
  addressed: boolean
  delivered: boolean
  responded: boolean
  failed: boolean | null
  addressed_later: boolean
  addressed_by: string | null
  addressed_because: string | null
}

/** One alternative a decision was asked with, exactly as the asker stated it. */
export interface DecisionOption {
  label: string
  /** what choosing it leads to; absent where the asker did not say */
  consequence?: string
  /** A RECONSIDERATION'S "DECIDE EACH" ALTERNATIVE: the findings it offered,
   *  each to be pursued, kept deferred or dismissed. What is chosen for each
   *  goes with the answer as data; no label or prose is ever read for it. */
  per_finding?: boolean
  findings?: { ref: Id; label: string }[]
}

/** What the owner may do with each finding a reconsideration offers. */
export type FindingChoice = 'pursue' | 'defer' | 'dismiss'

/** The work a wake-check review decides about (`wakecheck.stopped_work`). */
export interface StoppedWork {
  request: Id
  request_turn: Id | null
  request_number: number | null
  request_said: string | null
  requester: Id | null
  requester_alias: string | null
  run: Id
  execution: string | null
  runtime: string | null
  carrier: Id | null
  carrier_alias: string | null
  run_state: 'interrupted' | 'ended-unseen' | string | null
  stopped_at: number | null
}

export interface Expectation {
  id: Id
  expects: string
  /** WHO CARRIES IT, or null because nobody does. An unassigned request is a
   *  real state and not a missing field, so neither of these may be filled in
   *  from anything else. */
  of: Id | null
  of_alias: string | null
  by?: Id
  by_alias: string
  /** the requester's own recorded reason for needing this.
   *
   *  IT IS NOT THE QUESTION. The question is the prose of the Turn it hangs
   *  on, and is read there. */
  because?: string | null
  /** THE ALTERNATIVES THE ASKER STATED, as recorded on this expectation.
   *
   *  null or absent means none were stated — never that none exist: the owner
   *  can always answer in their own words. Nothing here reads alternatives out
   *  of prose, and nothing may manufacture them. */
  options?: DecisionOption[] | null
  response_present: boolean
  live_execution: boolean
  /** NOBODY IS CARRYING THIS — a different fact from nobody having replied, and
   *  the one that used to be invisible. `unresolved_because` is the intake
   *  act's own words for why, never this interface's guess. */
  unassigned?: boolean
  unresolved_because?: string | null
  /** Acts CLAIMING this is answered, kept apart from `response_present`:
   *  a reply existing is not a claim that the work succeeded. */
  satisfied_by?: Id[]
  /** THE REPLY THAT ANSWERED IT, where one did, as the read states it. The
   *  answered line used to find this reply among the Turns in hand; a reply is
   *  never a thread root, so a bounded flow never sends one and every answered
   *  ask read "the record shows this was answered". Null is "nothing answered
   *  it", which is a different fact from "nothing in hand did". */
  answered_by?: {
    turn: Id
    number: number | null
    said: string
    author: Id
    chose: { expectation: Id; option: number; label: string } | null
    /** this reply withdrew the ask rather than answering it */
    withdrawn?: boolean
  } | null
  /** CLOSED WITHOUT AN ANSWER: the person it was asked of withdrew it, with
   *  their reason and the reply that gave it. Null while it is not withdrawn.
   *  A withdrawn ask is never shown as Answered. */
  withdrawn?: {
    act: Id
    by: Id
    by_alias: string | null
    at: number
    because: string | null
    reply: Id | null
  } | null
  /** WHETHER ANSWERING THIS WOULD CONTINUE AUTHORISED WORK — asked of the same
   *  machinery that would do it (`continuation_candidates`), never guessed from
   *  the shape of the ask. False means a reply starts ordinary work, however it
   *  is sent, so nothing may promise that it hands work back. */
  continues_work?: boolean
  /** WHAT A WAKE-CHECK REVIEW IS ABOUT: the original request and who asked
   *  for it, and the stopped run with its execution. Null for any other ask. */
  stopped_work?: StoppedWork | null
  /** WHAT THE ASK NAMES, where it names governed material.
   *
   *  It is what lets an act on that item know it answered this ask, and what
   *  the governance links on an ask card are drawn from. EMPTY IS NOT A CLAIM
   *  THAT IT CONCERNS NOTHING: it says nobody wrote down what. The route has
   *  always sent it; nothing here declared it, so every reader that wanted it
   *  declared its own shape — and one of them got the key wrong. */
  material?: Id[]
  /** Work handed on. Each names the child expectation to ask about, so
   *  "waiting on a specialist" is readable without inventing a state. */
  delegations?: { act: Id; expectation: Id | null; by: Id; at: number }[]
  failures?: { act: Id; because: string | null; at: number }[]
  requires?: string[]
}

/** ONE OUTSTANDING OBLIGATION OF THIS CONVERSATION, enough to place its mark.
 *
 *  It is NOT `Expectation`: it comes from `expectation_state`, which says
 *  `expected_of` and `requested_by` where that says `of` and `by` — this was
 *  declared as `Expectation` for a long time while its one reader compensated
 *  inline for the difference.
 *
 *  THE LIST IS WHOLE while the flow is a batch, which is why the marks on a
 *  Turn are read from here rather than from the replies that happen to have
 *  arrived, and `root` says which thread each one hangs in.
 *
 *  OUTSTANDING ONLY — an answered expectation marks nothing and is not owed.
 *  `response_present` is therefore always false; it is kept so that a reader
 *  which checks it is right rather than merely lucky. Every state of the loop
 *  rides on each row (`unassigned`, `live_execution`, `delegations`,
 *  `failures`, `satisfied_by`, `assigned`, `requires`); only the rows and the
 *  fields declared below are relied on here. */
export interface OwedHere {
  expectation: Id
  turn: Id
  root?: Id
  /** the Turns from the thread's root down to `turn`, inclusive, so a Turn can
   *  ask whether an obligation is AT OR UNDER IT. Matching on `root` alone
   *  marks a Turn for an obligation on a sibling branch of the same thread. */
  path?: Id[]
  conversation: Id
  expects: string
  requested_by: Id
  requested_by_alias?: string | null
  /** who carries it, or null because nobody does */
  expected_of: Id | null
  expected_of_alias?: string | null
  response_present: boolean
}

export interface AgentWork {
  kind: 'brief' | 'result' | 'finding' | 'follow-up'
  why: string
  to: Id | null
  to_name: string | null
}

export interface Turn {
  id: Id
  number: number
  parts: Part[]
  /** Artifacts the run that posted this Turn returned. NOT parts:
   *  the author did not write them into the Turn; their run handed them over. */
  returned_with?: HeldState[]
  /** Set when this reply was RECOVERED: the runtime wrote it, nothing in
   *  Mentis saw the run end, and somebody recorded it afterwards. */
  recovered?: {
    act: Id; by: Id; by_alias: string | null; at: number
    because: string | null; source: string | null
  } | null
  /** THE RUN THAT RECORDED THIS TURN'S WORK, and the runtime that carried it,
   *  read with the Turn: the latest act on it naming an execution, never
   *  `execution-started`. null: the record ties none to it. */
  execution?: string | null
  runtime?: string | null
  author: Id
  author_alias: string
  written_by: string | null
  at: number
  addressees: Addressee[]
  topics: Id[]
  answering: Id | null
  /** THE THREAD THIS BELONGS TO, itself when it is a top-level post.
   *
   *  The flow decides what is top-level with this. It used to ask whether the
   *  parent happened to be loaded, which is a question about the response: as
   *  soon as a read is bounded, every reply whose parent was older became a
   *  post of its own. */
  root?: Id
  /** the coordinate of what it answers, so a reply says what it replies to
   *  with that Turn nowhere in hand */
  answering_number?: number | null
  /** IS THE PARENT WITHIN THIS READ'S SCOPE — the Topic when one is in force,
   *  the Conversation otherwise. With a Topic focused the flow stands a filed
   *  reply at top level when its parent is not filed; that test was "is the
   *  parent loaded", which is true of nothing once reads are bounded. null
   *  when it answers nothing. */
  parent_in_scope?: boolean | null
  /** how many Turns are under this thread, whole — the foot's count is the
   *  thread's and not the batch's */
  thread_replies?: number
  /** who wrote the most recent of them, for the faces beside that count */
  thread_repliers?: Id[]
  /** WHICH REQUEST'S TURN THIS WAS DISCOVERED UNDER, computed by the server
   *  from the `work-discovered` act's recorded causality. null: this Turn is
   *  not a finding. `turn: null` with source `unknown`: it is a finding and the
   *  record cannot say where it was found. Absent: an older server that does
   *  not compute it -- which is none of those answers. */
  /** AGENT WORK (`conversation.agent_work`): agent-to-agent chatter the
   *  conversation folds away by default, and why -- "brief to @Builder",
   *  "finding", "result to @Caretaker". null for everything the owner reads;
   *  absent from an older server, which folds nothing. */
  agent_work?: AgentWork | null
  discovered_under?: {
    turn: Id | null
    number: number | null
    conversation: Id | null
    expectation: Id | null
    source: 'computed' | 'unknown'
    why?: string
  } | null
  replies: Id[]
  /** the anchors in this Turn, each with what is attached to it */
  anchors?: AnchorOnTurn[]
  /** which offered alternative this reply chose, as its author set it when
   *  posting; null for every Turn that chose none. `withdraw` instead says
   *  this reply withdrew the decision and chose nothing. */
  chose?:
    | { expectation: Id; option: number; label: string; withdraw?: undefined }
    | { expectation: Id; withdraw: true; option?: undefined; label?: undefined }
    | null
  expectations: Expectation[]
  operational_acts: number
  /** EDITED: this Turn's line has later versions, and `parts` above is the
   *  current one's. Absent or null: never edited. */
  revision?: Revision | null
  /** DELETED: its line ends in a deletion record. `parts` is empty; what it
   *  said is disclosed only in Details. Absent or null: not deleted. */
  deleted?: Deletion | null
  /** THE OTHER CONVERSATIONS THIS POST IS SHOWN IN, AS A LINK. It belongs to
   *  the one it was written in; these only show it. Absent: an older server. */
  linked_into?: Id[]
  /** Present only where this post is shown in a Conversation that is NOT its
   *  home: where it lives, who linked it here and when. */
  linked?: LinkedFrom | null
}

export interface LinkedFrom {
  link: Id
  home: Id
  home_name: string | null
  by: Id
  by_alias: string
  at: number
}

/** One filing or link a post ever had, and how it ended if it did. */
export interface FilingRow {
  link: Id
  relation: 'about-topic' | 'linked-into'
  /** the Topic or the Conversation */
  to: Id
  name: string | null
  at: number
  by: Id
  by_alias: string
  ended: { record: Id; at: number; by: Id; by_alias: string; because: string | null } | null
}

/* ------------------------------------------------------------------------ *
 * EDIT AND DELETE, APPEND-ONLY. A version is a new entry that supersedes the
 * last; a deletion is a record that supersedes the current version. Nothing
 * is overwritten or erased. See `mentis/conversation/versions.py`.
 * ------------------------------------------------------------------------ */
export interface Revision {
  versions: number
  current: Id
  edited_at: number
  edited_by: Id
}

export interface Deletion {
  record: Id
  at: number
  by: Id
  by_alias?: string
  because: string | null
}

export interface VersionRow {
  entry: Id
  version: number
  at: number
  by: Id
  by_alias: string
  because: string | null
  current: boolean
  /** a Turn's version carries its parts; any other entry its body */
  parts?: Part[]
  body?: Record<string, unknown>
}

export interface VersionsRead {
  entry: Id
  versions: VersionRow[]
  current: Id | null
  deleted: (Deletion & { by_alias: string }) | null
}

/** What an interface may offer on an entry, by the rules the acts apply. */
export interface Offers {
  edit: boolean
  delete: boolean
  edit_mode: 'proposed' | 'candidate' | 'edited' | null
  why_not: string | null
  current?: Id
}

/* --------------------------------------------------------------------- *
 * A DURABLE THING SOME WORK LEFT BEHIND.
 *
 * Read from the ordinary `produced` Relation by the server and from nothing
 * else — never from `about[]`, a Kind name, an act name or prose. `about[]`
 * has always meant "this act concerned these things"; the fixture holds an
 * act that REFERENCES a Finding one Turn after the act that MADE it, and the
 * two must not look alike here.
 *
 * NOTHING IN THIS INTERFACE MAY ENUMERATE `kind`. A Kind is self-describing
 * and anybody may define one, so what a product is comes back in the Kind's
 * own declared terms — `kind`, its declared `meaning`, its declared `fields`
 * — and is rendered from those. A Kind nobody has heard of renders because
 * nothing here was ever taught the names of the ones we have.
 * --------------------------------------------------------------------- */
export interface Product {
  entry: Id
  /** substrate: `entry`, `admission`. Closed and small; not a Kind. */
  family: string | null
  /** the Kind's own name, as it was declared. Never matched against a list. */
  kind: string | null
  version?: number
  /** what the Kind's author said it means. Absent where they declared none. */
  meaning: string | null
  /** everything else the Kind declared about itself, verbatim */
  properties: Record<string, unknown>
  /** the Kind's declared fields, in declared order */
  fields: string[]
  body: Record<string, unknown>
  /** the first declared field that holds text — the product in one line */
  summary: string | null
  /** the reason recorded on the `produced` link itself */
  why?: string | null
  at?: number
  unreadable?: boolean
}

export interface Act {
  id: Id
  at: number
  actor: Id
  act: string
  conversation: Id | null
  turn: Id | null
  /** WHERE THE ACT HAPPENED, said by the read rather than looked up. The
   *  surfaces that draw acts print the Turn's `#N`, open its thread and narrow
   *  by Topic; they used to find all three by searching the Turns in hand,
   *  which only worked while that was every Turn of the Conversation.
   *  `turn_topics` is empty for a Turn filed under no Topic. */
  turn_number?: number | null
  turn_root?: Id | null
  /** absent when the read was not scoped to one Conversation; see
   *  `actsInTopic`. Empty means filed under no Topic, which is different. */
  turn_topics?: Id[]
  execution: Id | null
  runtime: string | null
  because: string | null
  caused_by: Id | null
  about: string[]
  detail: Record<string, unknown>
  /** what this act brought into being. Empty for an act that made nothing. */
  produced: Product[]
}

/** THE ACTS A TOPIC REACHES, said once so the three surfaces that narrow by a
 *  Topic cannot drift apart. Each act states which Topics its Turn is filed
 *  under; this used to be done by intersecting with the Turns the focused flow
 *  had loaded, which against a bounded read meant "the Topic Turns the reader
 *  has scrolled back to" and silently dropped every act older than that.
 *
 *  AN ACT THAT DOES NOT SAY IS NOT NARROWED AWAY. Only a Conversation-scoped
 *  read answers `turn_topics` — a Topic belongs to one Conversation — so an act
 *  without it came from a read that was never asked the question. Dropping it
 *  would turn the absence of a question into "nothing happened here". */
export function actsInTopic(acts: Act[], topic: Id | null): Act[] {
  if (!topic) return acts
  return acts.filter((a) =>
    a.turn_topics === undefined || (a.turn && a.turn_topics.includes(topic)))
}

/** The word for one product, in the Kind's own terms and never ours.
 *  Falls back to the substrate family, then to nothing worth saying. */
export const termOf = (p: Product): string => p.kind ?? p.family ?? 'entry'

/** One product said in a sentence, from declared terminology only. Where the
 *  Kind declared no meaning, that is said plainly rather than invented. */
export function saysOf(p: Product): string {
  const term = termOf(p)
  const head = p.summary ? `${term} — ${p.summary}` : term
  return p.meaning ? `${head}\n${term}: ${p.meaning}` : head
}

/* --------------------------------------------------------------------- *
 * BACKWARDS, FROM A DURABLE THING TO THE WORK THAT MADE IT.
 *
 * `produced-by` is the inverse of the same Relation the forward direction
 * reads, and the chain below is `caused_by` walked back from the producing
 * act. There is no second provenance store and there must never be one: this
 * is reconstructed from the same record on every read.
 * --------------------------------------------------------------------- */
export interface ProducedBy {
  act: Id
  act_type?: string
  actor?: Id
  actor_alias?: string
  because?: string | null
  at?: number
  execution?: Id | null
  runtime?: string | null
  conversation?: Id | null
  turn?: Id | null
  turn_number?: number | null
  /** the ancestry, oldest first: the steer, then what it caused */
  caused_by?: Id[]
  missing?: boolean
}

export interface Provenance {
  entry: Id
  product: Product | null
  produced_by: ProducedBy[]
  /** present when nothing claims to have produced it — said, never guessed */
  why_not?: string
}

/** A durable object the reader has asked to see, and everything needed to
 *  show it where it belongs: the act that minted it and the Turn that act's
 *  work started at. Assembled by the layout, which is the only place that can
 *  see the spine and the conversation at once. */
export interface RevealedProduct {
  product: Product
  /** the operational act that minted it */
  by: Act
  /** that act's actor, by the name this conversation uses */
  who?: string | null
  /** the Turn its work originated at — where the card is shown */
  turn: Id
  /** true only where the media surface actually holds this artifact */
  openable?: boolean
  /** the media item's key, where there is one to open */
  mediaKey?: string
}

/** Everything a set of acts left behind, in the order it was produced. */
export const productsIn = (acts: Act[]): Product[] =>
  acts
    .flatMap((a) => a.produced ?? [])
    .sort((x, y) => (x.at ?? 0) - (y.at ?? 0))

export interface AttentionItem {
  what: string
  detail: string
  conversation: Id | null
  contribution: Id | null
  participant: Id | null
  /** absent on a delivery observed to fail, which was not delivered */
  delivered?: boolean
}

export interface Execution {
  execution: Id
  participant: Id
  alias: string
  conversation: Id | null
  scope: string
  runtime: string
  persona: Id | null
}

export interface BrainConversation {
  conversation: Id
  name: string
  about: string
  participants: number
  contributions: number
  topics: number
  last_activity: number
  awaiting_response: number
  recent_media: string[]
}

export interface Brain {
  brain: { primary: Id; attached: unknown[] }
  conversations: BrainConversation[]
  conversations_total: number
  conversations_omitted: number
  participants: { participant: Id; alias: string; conversations: number }[]
  participants_total: number
  participants_omitted: number
  active_executions: Execution[]
  attention: AttentionItem[]
  attention_total: number
  attention_omitted: number
  /** of `attention_total`, how many never reached anybody */
  attention_undelivered?: number
  note: string
  rendered: string
  corpus_path?: string
  corpus_id?: string
  /** the Brain's own name and purpose, from its manifest (UI polish 2, #8);
   *  null with a reason where it has none */
  corpus_name?: string | null
  corpus_role?: string | null
  corpus_name_why_not?: string
}

export interface TopicRef {
  id: Id
  name: string
  about?: string
  turns: number
}

export interface ConversationSummary {
  id: Id
  name: string
  about: string
  turns: number
  participants: number
  topics: TopicRef[]
  /** posts from other Conversations shown here as links; never numbered here */
  linked?: number
  awaiting: number
  live_executions: number
  last_activity: number
}

export interface ConversationList {
  conversations: ConversationSummary[]
}

export interface Instruction {
  id: Id
  /** WHICH KIND, because this list is no longer one Kind. The server answers
   *  what is PLACED here and DIRECTS WORK -- a rule placed at this Conversation
   *  governs it exactly as an instruction does -- so the row says which, rather
   *  than leaving a reader to assume. Optional because an older server omits it. */
  kind?: string
  text: string
  about: string
}

/** WHAT ONE READ DELIVERED, AND WHAT LIES OUTSIDE IT.
 *
 *  Counted in the unit the read pages by and in the scope it was asked about,
 *  by the server. The client renders these; it does not rebuild them from
 *  collections of its own, which is how a focused view came to offer history
 *  that did not exist. */
export interface Batch {
  /** `thread` unfocused — the flow draws thread roots — and `turn` with a
   *  Topic in force, where the flow draws the Topic's Turns flat. The two
   *  modes keep separate cursors; neither is the other's position. */
  unit: 'thread' | 'turn'
  shown: number
  units_total: number
  older: number
  newer: number
  /** the first and last unit's coordinate, which is how the next batch is
   *  asked for */
  first: number | null
  last: number | null
  size: number | null
  mode: 'recent' | 'before' | 'after' | 'around' | 'all'
}

export interface Conversation {
  id: Id
  name: string
  about: string
  /** opened from an anchor: resolved now, never copied */
  origin?: Origin | null
  participants: {
    participant: Id
    alias: string
    /** A PERSON'S DECLARATION of the runtime this name's work runs on when
     *  the work names none, or null. Never derived from the alias. */
    default_runtime?: string | null
    /** `default` (declared), `auto` (declared runtime-auto) or `undeclared` */
    runtime_mode?: 'default' | 'auto' | 'undeclared'
  }[]
  topics: TopicRef[]
  instructions: Instruction[]
  turns: Turn[]
  turns_total: number
  /** POSTS FROM ELSEWHERE, SHOWN HERE AS LINKS. Not Turns of this
   *  Conversation: each keeps its number in its own home. */
  linked?: Turn[]
  linked_total?: number
  focus_topic: Id | null
  awaiting: AttentionItem[]
  /** WHAT IS OWED HERE, which is not `awaiting`. `awaiting` is descriptive —
   *  somebody was addressed and has not replied — and must not become an
   *  obligation through wording. This is the recorded obligation. */
  owed?: OwedHere[]
  /** what this read delivered; absent from an older server */
  batch?: Batch
  failures: unknown[]
}

export interface Inspector {
  kind: string
  stands: boolean
  incoming: Record<string, unknown>
  operational: Act[]
  deliveries: unknown[]
  conversation: Id | null
}

export type TurnDetail = Turn & {
  inspector: Inspector
  versions?: VersionsRead
  /** every filing and link it ever had, oldest first */
  filings?: FilingRow[]
}

export interface OrientationRecent {
  id: Id
  by: string
  parts: string[]
  topics: Id[]
  said: string
}

export interface Orientation {
  conversation: Id
  name: string
  about: string
  topic: Id | null
  recent: OrientationRecent[]
  reply_context: OrientationRecent[]
  unresolved_for_you: Id[]
  withheld: number
  elsewhere_in_conversation: number
}

export interface ActivityEntry {
  participant: Id
  alias: string
  about: string
  /** Their open runs, each in the server's one sentence for it (the same
   *  reading as `/api/working`); the time behind it is in the words. */
  runs?: { run: Id; state: string; words: string; at: number | null;
           source: 'recorded' | 'runtime' | 'unknown'; held_here: boolean }[]
  has_live_execution: boolean
  execution: Id | null
  runtime: string | null
  scope: string | null
  conversation: Id | null
  recent_acts: {
    id: Id
    act: string
    at: number
    conversation: Id | null
    turn: Id | null
    because: string | null
  }[]
  conversations: Id[]
  /* WHAT A LIVE EXECUTION IS ACTUALLY WORKING ON — the Turn its acts were
     recorded against, which is an addressable Conversation contribution
     somebody can go and read.

     EXACTLY ONE OF THESE IS EVER SET. `execution-started` is not required to
     carry a Turn and often does not — an execution begun at Brain scope has
     none to carry. Where the record does not say, `working_on_gap` says that
     in words and `working_on` stays null. The interface reports the gap; it
     never falls back to the act's prose, and it never infers from silence. */
  working_on: {
    turn: Id
    number: number | null
    conversation: Id | null
    since: number
    from_act: Id
  } | null
  working_on_gap: string | null
}

export interface Activity {
  activity: ActivityEntry[]
  note: string
}

export interface OperationalList {
  operational: Act[]
}

export interface HistoryNode {
  id: Id
  kind: 'participant' | 'conversation' | 'turn' | 'act' | 'execution' | 'artifact' | 'finding'
  label: string
  at?: number
  actor?: Id
  conversation?: Id
  number?: number
  runtime?: string
}

export interface HistoryEdge {
  from: Id
  to: Id
  edge: 'did' | 'said' | 'in' | 'concerns' | 'caused' | 'about' | 'replies-to'
}

export interface History {
  nodes: HistoryNode[]
  edges: HistoryEdge[]
}

export interface GravityItem {
  act: Id
  by: string
  because: string | null
  about: string[]
  at: number
  conversation: Id | null
  originating_turn: Id | null
  depth_from_root: number
}

export interface Gravity {
  deferred: GravityItem[]
  reconsideration?: {
    trunk: {
      originating_turn: Id | null
      turn_number: number | null
      complete: boolean
      outstanding_on_trunk: string[]
    }
    deferred: GravityItem[]
    due_for_reconsideration: boolean
  }
}

export interface ContextComponent {
  source_kind: string
  source_id: Id | null
  scope: string
  text: string
  why: string
  about: string
}

export interface ContextPayload {
  scope: string
  components: ContextComponent[]
  conflicts: unknown[]
  withheld: { source_kind: string; source_id: Id | null; why: string }[]
  payload_chars: number
}

export interface ParticipantsList {
  participants: {
    participant: Id
    alias: string
    about: string
    conversations: Id[]
    avatar?: Id | null
    runtime?: string | null
    default_runtime?: string | null
    runtime_mode?: 'default' | 'auto' | 'undeclared'
  }[]
}

/* ---------------------------------- fetch ---------------------------------- */

export interface ApiState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** EVERY JSON REQUEST SAYS IT IS THIS INTERFACE. The server refuses a JSON
 *  route without it (mentis/web CLIENT_HEADER): a page on another site cannot
 *  send a non-safelisted header without a preflight, and the preflight grants
 *  nothing. Artifact and picture URLs, loaded by `<img src>`, do not need it. */
export const CLIENT_HEADERS = { 'X-Mentis-Client': '1' } as const

/** Trigger direct browser download of an export archive. */
export async function downloadExport(url: string, defaultFilename: string): Promise<void> {
  const res = await fluidFetch(url, { headers: CLIENT_HEADERS })
  if (!res.ok) {
    let msg = `Export failed: ${res.statusText}`
    try {
      const err = await res.json()
      if (err?.error) msg = err.error
    } catch { /* ignore */ }
    throw new Error(msg)
  }
  const blob = await res.blob()
  let filename = defaultFilename
  const disposition = res.headers.get('Content-Disposition')
  if (disposition) {
    const m = disposition.match(/filename="?([^";]+)"?/)
    if (m && m[1]) filename = m[1].trim()
  }
  if (typeof document === 'undefined') return
  const blobUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = blobUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(blobUrl)
}

export function exportConversation(id: string): Promise<void> {
  return downloadExport(`/api/conversations/${encodeURIComponent(id)}/export`, `conversation-${id}.zip`)
}

export function exportTurn(id: string): Promise<void> {
  return downloadExport(`/api/turns/${encodeURIComponent(id)}/export`, `turn-${id}.zip`)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fluidFetch(path, {
    ...init,
    headers: { ...(init?.headers as Record<string, string> | undefined), ...CLIENT_HEADERS },
  })
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    throw new Error(`${res.status}: ${text.slice(0, 200)}`)
  }
  if (!res.ok || (body && typeof body === 'object' && 'error' in (body as object))) {
    const e = (body as { error?: string })?.error ?? res.statusText
    throw new Error(e)
  }
  return body as T
}

/** ONE READ, WITHOUT A HOOK.
 *
 *  Everything on this side reads through `useApi`, which is a hook and so
 *  cannot be called once per row of an answer that only arrived at runtime.
 *  Where a surface has to follow a handful of links it learns about from its
 *  first read — the open asks, and then the Turn each one hangs on — it reads
 *  them with this and holds the result in state. Same request, same errors, no
 *  second client: the only thing missing is the reread-on-advance that a hook
 *  gets for free, so whoever uses this keys it on what its first read said. */
export const read = <T,>(path: string): Promise<T> => request<T>(path)

/** The single fetch hook. `path` null means "nothing to fetch". */
/** EVERY READER HEARS IT, so no reader has to be wired up by hand.
 *
 *  The shell's own `onChanged` reloads the handful of things the shell
 *  holds, and that was not enough: surfaces keep their own `useApi` -- the
 *  presence line reads `/api/activity` itself -- so an agent could be
 *  working and the line still said nobody was. Enumerating those call sites
 *  would mean maintaining a list that is wrong the moment somebody adds a
 *  surface.
 *
 *  So the advance is announced once and every `useApi` rereads its OWN path.
 *  Nothing is pushed, nothing is diffed, and no second model of anything is
 *  built: each reader still reads exactly what it always read.
 */
const readers = new Set<(moved: Moved, where?: Where | null) => void>()

/** WHAT AN ANNOUNCEMENT SAYS MOVED, handed to each reader so that it can
 *  decide for itself how soon to reread (`rereadPlan`). */
export type Moved = 'durable' | 'live'

/** THE READERS THAT SHOW LIVE RUNS (or Scratch), which also hear the live
 *  half of the pulse moving on its own. That half moves on practically every
 *  stream event of a working agent (`RunObservation.mark()` counts events),
 *  so it used to wake every reader about every 1.2s with nothing durable
 *  changed: ~13 Conversation and Brain-wide rereads per beat, more server
 *  time than the beat, and a Conversation switch queued behind them
 *  (diagnosis adm-d21151019085). Now only these follow it. */
const runReaders = new Set<(moved: Moved) => void>()

/** WHERE THE RECORD MOVED, as `/api/pulse?since=` says it (`mentis/web/
 *  moved.py`): the Conversations whose material was written, the executions
 *  named, and whether governed material or participants were. `loose`: some
 *  of what was written could not be placed, so every reader rereads. */
export interface Where {
  conversations: Id[]
  executions: string[]
  governed: boolean
  people: boolean
  loose: boolean
}

/** IS A READER OF `path` CONCERNED BY A MOVE `where`?
 *
 *  A post in one Conversation used to reread everything on screen -- 40 to
 *  60 requests through one server for a single Turn, which is what kept a post
 *  waiting seconds to appear. Each reader now rereads only where what it shows
 *  could have changed.
 *
 *  ONLY WHAT IS CERTAIN IS NARROWED. No answer, a `loose` one, or a path this
 *  does not know: reread, exactly as before. A path is narrowed here only
 *  when what it reads is plainly scoped by its own address -- one
 *  Conversation, one execution -- or is governed material or participants. */
export function concerns(path: string, where: Where | null | undefined): boolean {
  if (!where || where.loose) return true
  const q = path.indexOf('?')
  const route = q < 0 ? path : path.slice(0, q)
  const params = new URLSearchParams(q < 0 ? '' : path.slice(q + 1))
  const inConv = (cid: string | null) => !!cid && where.conversations.includes(decodeURIComponent(cid))

  // One run's execution sheet: that run, or what governs it.
  if (route === '/api/governance/execution' && params.get('execution')) {
    return where.executions.includes(params.get('execution') as string) || where.governed
  }
  // Governed material, read Brain-wide.
  if (route === '/api/governed' || route === '/api/kinds' || route === '/api/personas'
      || route === '/api/governance/applies' || route === '/api/governance/authoring') {
    return where.governed
  }
  if (route === '/api/participants') return where.people
  // The list of Conversations: one of them, or who is in them.
  if (route === '/api/conversations') return where.conversations.length > 0 || where.people
  // ONE CONVERSATION'S OWN READS, named in the address. What governs it also
  // moves with governed material; work is left alone (delegated runs report
  // where they ran).
  const conv = /^\/api\/conversations\/([^/]+)(\/[^/]+)?$/.exec(route)
  if (conv) {
    const sub = conv[2] ?? ''
    if (sub === '/work') return true
    if (sub === '/governs') return inConv(conv[1]) || where.governed
    if (sub === '' || sub === '/media') return inConv(conv[1]) || where.people
    return true
  }
  if (route === '/api/operational' && params.get('conversation')) {
    return inConv(params.get('conversation'))
  }
  return true
}

export function announceAdvance(where?: Where | null) {
  for (const r of [...readers]) r('durable', where ?? null)
}

/** HOW A READER HEARS AN ADVANCE, as `useApi` registers it: every reader
 *  hears the record moving; a `runs` reader also hears live execution move.
 *  Each is told which, so a reader can space the live half out
 *  (`rereadPlan`). Returns the way to stop hearing. */
export function hearAdvance(reread: (moved: Moved, where?: Where | null) => void,
                            runs = false): () => void {
  readers.add(reread)
  if (runs) runReaders.add(reread)
  return () => {
    readers.delete(reread)
    runReaders.delete(reread)
  }
}

/** Only live execution moved: reread what shows it, nothing else. */
export function announceRunAdvance() {
  for (const r of [...runReaders]) r('live')
}

/** WHICH HALF OF THE PULSE MOVED. The token is `<durable>/<live>`: the
 *  record's own advance, and a digest of the runs this server holds plus
 *  Scratch. The durable half moving is the record moving -- every reader
 *  rereads, as always. Only the live half moving is execution the record has
 *  not heard about yet -- only `runs` readers reread. */
export function pulseChange(prev: string | null, next: string): 'durable' | 'live' | null {
  if (prev === null || prev === next) return null
  const cut = (t: string) => {
    const i = t.indexOf('/')
    return i < 0 ? [t, ''] : [t.slice(0, i), t.slice(i + 1)]
  }
  const [d0, l0] = cut(prev)
  const [d1, l1] = cut(next)
  if (d0 !== d1) return 'durable'
  return l0 !== l1 ? 'live' : null
}

/** `live: false` for a reader that costs something real.
 *
 *  Two endpoints here are deliberately expensive and say so in their own
 *  docstrings: `/api/execution` discovers runtimes and lists models (3.5s of
 *  subprocesses), and `/api/capacity` asks each runtime what it has left
 *  (7s, and it RECORDS the reading). Rereading those every time anything in
 *  the brain moves would fan out subprocess storms during exactly the
 *  dispatch somebody is watching, and would grow a capacity stream on a
 *  timer instead of on an act. They keep their own refresh and sit this out.
 */
export interface ApiOptions {
  live?: boolean
  /** RE-READ AT MOST THIS OFTEN (ms) on an advance. For a reader that is
   *  worth keeping live but costs enough that every advance would be too
   *  many: advances inside the window become one re-read at its end. */
  spacing?: number
  /** THIS READER SHOWS LIVE RUNS OR SCRATCH -- `/api/working`,
   *  `/api/activity`, a Conversation's `/work`, a Scratch -- so it also
   *  rereads when only live execution moved. Every other reader rereads only
   *  when the record itself did. */
  runs?: boolean
  /** A `runs` READER REREADS FOR LIVE MOVEMENT AT MOST THIS OFTEN (ms),
   *  counted from its last read, whatever started that read. Live moves
   *  inside the window become exactly one reread at its end -- trailing,
   *  never dropped. The durable half moving is not held by it: the record
   *  moving still rereads at once (or per `spacing`, which keeps its own
   *  meaning and applies to both halves). 0, the default, rereads on every
   *  live move as before. Each call site says why it chose its window. */
  runsSpacing?: number
  /** AN ERROR IS SAID ONLY FOR THE PATH THAT FAILED. Off, the default, an
   *  error stays until a later read succeeds, whichever path it was. On, a
   *  new path has no error until its own read fails -- so a reader whose path
   *  just changed shows that it is reading, not the last path's failure. The
   *  Conversation pane turns it on: a switch is drawn as opening, and a
   *  failure left over from the Conversation before must not hide that. */
  ownErrors?: boolean
}

/** READERS ASKING IN THE SAME MOMENT SHARE ONE REQUEST.
 *
 *  Main mounts four readers of the same `/api/owed` -- the app bar's counter,
 *  the toasts, the rail's dots and Needs you -- and every advance rereads all
 *  of them at once. On the live Brain that path takes 5-9s and the server
 *  answered the four one after another. A request is joined only by readers
 *  that ask in the same task as the one that started it, which is the same
 *  instant: nobody is handed an answer to a read that began before their own
 *  reason to read. Nothing is kept once it settles; this is not a cache. */
const flights = new Map<string, Promise<unknown>>()

function together<T>(path: string): Promise<T> {
  const f = flights.get(path)
  if (f) return f as Promise<T>
  const p = request<T>(path)
  flights.set(path, p)
  window.setTimeout(() => {
    if (flights.get(path) === p) flights.delete(path)
  }, 0)
  return p
}

/** WHAT A REREAD PLAN NEEDS FROM ITS SURROUNDINGS: a clock, timers, whether
 *  anybody can see the page, and the reread itself. `useApi` hands it the
 *  browser's; a test or a simulation hands it its own, so the decision below
 *  is exercised exactly as shipped, with no React and no browser. */
export interface RereadWorld {
  now: () => number
  setTimer: (fn: () => void, ms: number) => number
  clearTimer: (id: number) => void
  visible: () => boolean
  reread: () => void
}

export interface RereadPlan {
  /** An announcement reached this reader (`hearAdvance`). */
  heard: (moved: Moved) => void
  /** A read of this reader's path just started, for whatever reason: first
   *  load, `reload()`, an advance. It answers every live move before it. */
  read: () => void
  /** The page became visible again. */
  shown: () => void
  stop: () => void
}

/** WHEN A READER REREADS FOR AN ADVANCE -- the whole decision, in one place,
 *  pure enough to run in node.
 *
 *  THE LIVE HALF IS NOT THE RECORD. It moves on practically every stream
 *  event of a working agent: measured in production at ~28 moves a minute
 *  during agent runs against ~4 durable ones. `useApi` already keeps one read
 *  per reader out and folds every later advance into one reread after it
 *  lands -- which, for a path as slow as a Conversation's `/work` (0.94s
 *  alone, 1-10s under load), meant rereading it BACK TO BACK for as long as
 *  an agent worked. One Python process serves everything, so that load made
 *  every other request 10-40x slower, the Conversation switch included.
 *
 *  So, per reader:
 *    - the DURABLE half moving rereads at once, exactly as it always did
 *      (held only by `spacing`, which keeps its meaning: at most this often,
 *      for every advance);
 *    - the LIVE half moving rereads at most once per `runsSpacing`, counted
 *      from the reader's last read, TRAILING: moves inside the window become
 *      exactly one reread at its end. Nothing is dropped; a move is only ever
 *      answered by a read that STARTED after it, and any read that starts --
 *      a durable reread, `reload()`, a poll -- answers every move before it;
 *    - a HIDDEN page does not reread for live moves at all. Nobody is looking,
 *      and the record has not moved. It remembers that it missed some and
 *      rereads once when it is looked at again. Durable rereads in a hidden
 *      page are untouched: those are the record moving.
 *
 *  `runsSpacing` 0 and a visible page is exactly the old behaviour: every
 *  live move rereads at once, synchronously. */
export function rereadPlan(spacing: number, runsSpacing: number, w: RereadWorld): RereadPlan {
  let timer: number | null = null
  let due = Infinity
  let lastRead = -Infinity   // the last read that started, whatever started it
  let lastSpaced = -Infinity // the last `spacing` reread, as `spacing` always counted
  let owedDurable = false
  let missedHidden = false

  const disarm = () => {
    if (timer !== null) w.clearTimer(timer)
    timer = null
    due = Infinity
  }
  const go = () => {
    disarm()
    owedDurable = missedHidden = false
    lastRead = lastSpaced = w.now()
    w.reread()
  }
  // Keep whichever owed reread is due first; one timer per reader.
  const arm = (at: number) => {
    if (timer !== null && due <= at) return
    disarm()
    due = at
    timer = w.setTimer(fire, Math.max(0, at - w.now()))
  }
  function fire() {
    timer = null
    due = Infinity
    // A live-only reread falling due while nobody can see the page waits for
    // them, like any other live move heard while hidden.
    if (!owedDurable && !w.visible()) {
      missedHidden = true
      return
    }
    go()
  }
  // When the live half may next reread: its own window, and `spacing` too.
  const liveAt = () => Math.max(lastRead + runsSpacing, spacing ? lastSpaced + spacing : -Infinity)
  const live = () => {
    const at = liveAt()
    // Exactly the old path when nothing holds it: reread now, synchronously.
    if (timer === null && !spacing && at <= w.now()) return go()
    arm(at)
  }

  return {
    heard(moved) {
      if (moved === 'durable') {
        owedDurable = true
        if (!spacing) return go()
        return arm(lastSpaced + spacing)
      }
      if (!w.visible()) {
        missedHidden = true
        return
      }
      live()
    },
    read() {
      lastRead = w.now()
      // This read answers every live move heard so far. A held durable
      // reread stays held: `spacing` is about how often, not about what.
      missedHidden = false
      if (timer !== null && !owedDurable) disarm()
    },
    shown() {
      if (!missedHidden) return
      missedHidden = false
      live()
    },
    stop: disarm,
  }
}

export function useApi<T>(path: string | null,
                          opts: ApiOptions = {}): ApiState<T> {
  const live_ = opts.live !== false
  const spacing = opts.spacing ?? 0
  const runs = opts.runs === true
  const runsSpacing = runs ? opts.runsSpacing ?? 0 : 0
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<{ path: string; message: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [nonce, setNonce] = useState(0)
  const live = useRef(0)
  /* ONE READ OF A PATH OUT AT A TIME, PER READER. Only the newest request's
     answer is applied, so while rereads started faster than a slow path
     answered, every answer was discarded and the reader never settled: Needs
     you said "reading the record…" indefinitely on a busy Brain. A reread
     asked for while this path's read is out now waits for that read to land
     -- its answer is shown, as what it is, the last settled answer -- and
     then asks once more. Asked again and again in the meantime is still once. */
  const out = useRef<{ token: number; path: string } | null>(null)
  const again = useRef(false)
  const plan = useRef<RereadPlan | null>(null)

  // Reread on an advance, but only while there is something to reread, and
  // as soon as `rereadPlan` says. DECLARED BEFORE THE READ so that, on a new
  // path, the plan exists when the first read starts and counts it.
  useEffect(() => {
    if (!path || !live_) return
    const p = rereadPlan(spacing, runsSpacing, {
      now: () => Date.now(),
      setTimer: (fn, ms) => window.setTimeout(fn, ms),
      clearTimer: (id) => window.clearTimeout(id),
      visible: () => typeof document === 'undefined' || document.visibilityState === 'visible',
      reread: () => setNonce((n) => n + 1),
    })
    plan.current = p
    /* A DURABLE MOVE THAT DOES NOT CONCERN THIS PATH IS NOT HEARD (`concerns`).
       The live half is untouched: it is already only the run readers'. */
    const stop = hearAdvance((moved, where) => {
      if (moved === 'durable' && !concerns(path, where)) return
      p.heard(moved)
    }, runs)
    const shown = () => {
      if (document.visibilityState === 'visible') p.shown()
    }
    if (runs && typeof document !== 'undefined') document.addEventListener('visibilitychange', shown)
    return () => {
      stop()
      p.stop()
      if (plan.current === p) plan.current = null
      if (runs && typeof document !== 'undefined') document.removeEventListener('visibilitychange', shown)
    }
  }, [path, live_, spacing, runs, runsSpacing])

  useEffect(() => {
    if (!path) {
      ++live.current
      out.current = null
      again.current = false
      setData(null)
      setError(null)
      setLoading(false)
      return
    }
    if (out.current && out.current.path === path) {
      again.current = true
      return
    }
    const token = ++live.current
    out.current = { token, path }
    again.current = false
    plan.current?.read()
    setLoading(true)
    together<T>(path)
      .then((d) => {
        if (live.current === token) {
          setData(d)
          setError(null)
        }
      })
      .catch((e: Error) => {
        if (live.current !== token) return
        setError({ path, message: e.message })
        // KEEP WHAT IS ALREADY ON SCREEN. Clearing it was survivable while a
        // refetch only happened because somebody had just acted; now anything
        // moving in the brain triggers one, so a single failed request would
        // blank the conversation to `API error` and take the composer -- and
        // the half-written turn in it -- with it. A first load that fails has
        // nothing to keep and still reports the error.
        setData((prev) => prev)
      })
      .finally(() => {
        if (out.current?.token !== token) return
        out.current = null
        if (again.current) {
          again.current = false
          setNonce((n) => n + 1)
        } else if (live.current === token) setLoading(false)
      })
  }, [path, nonce])

  const reload = useCallback(() => setNonce((n) => n + 1), [])

  const said = opts.ownErrors ? (error?.path === path ? error.message : null)
    : error?.message ?? null
  return { data, error: said, loading, reload }
}

/** THE RECORD ADVANCED — REREAD WHAT YOU ALREADY READ.
 *
 *  The whole of the live-update mechanism on this side. Every surface here
 *  already knows how to read itself and already has a `reload`; what was
 *  missing was anybody saying that the record had moved unless this client
 *  had moved it, so an agent's acknowledgement, reply, status or product sat
 *  there unseen until somebody pressed refresh.
 *
 *  It asks one cheap question and compares the answer to the last one. It
 *  carries no domain object, builds no second model of anything, and never
 *  reloads the page — `onAdvance` is the shell's existing `onChanged`, which
 *  rereads the same endpoints the same way, so nothing about where the reader
 *  is or what they were typing is disturbed.
 *
 *  A failed poll is not an event. The server going away and coming back is a
 *  gap in asking, not a change in the record, so the token is only compared
 *  when one actually comes back.
 */
/** ASK THE PULSE NOW rather than at the next beat: something done here has just
 *  moved the record, and the readers it concerns should hear it at once. */
let beatNow: (() => void) | null = null
export function pulseNow() {
  beatNow?.()
}

export function usePulse(everyMs = 1200) {
  const seen = useRef<string | null>(null)
  useEffect(() => {
    let alive = true
    let miss = 0
    let timer: number | undefined
    let asking = false
    let askAgain = false
    const beat = async () => {
      // One question out at a time; asked for meanwhile, asked once after.
      if (asking) {
        askAgain = true
        return
      }
      if (timer) window.clearTimeout(timer)
      timer = undefined
      asking = true
      try {
        // SAYING WHAT WAS LAST SEEN, so the answer can say where it moved.
        const since = seen.current ? seen.current.split('/')[0] : null
        const r = await request<{ token: string; moved?: Where | null }>(
          '/api/pulse' + qs({ since }))
        if (!alive) return
        // ONE ANNOUNCEMENT, NOT TWO. Calling the shell's `onChanged` here as
        // well doubled every request: it reloads hooks that are themselves
        // `useApi`, and those already hear the advance. Measured at 16
        // requests for one advance where 8 readers were mounted.
        //
        // AND ONLY AS FAR AS WHAT MOVED: the live half alone wakes only the
        // readers that show live runs (`pulseChange`).
        const moved = pulseChange(seen.current, r.token)
        if (moved === 'durable') announceAdvance(r.moved)
        else if (moved === 'live') announceRunAdvance()
        seen.current = r.token
        miss = 0
      } catch {
        /* unreachable for a moment: ask again, decide nothing. Backing off
           so a stopped server is not hit once a second forever, per tab. */
        miss = Math.min(miss + 1, 5)
      } finally {
        // Nobody is watching a hidden tab, so nothing needs to be fresh in
        // one. It catches up on the first beat after it is looked at again.
        asking = false
        const hidden = document.visibilityState !== 'visible'
        const wait = hidden ? Math.max(everyMs, 5000) : everyMs * (1 + miss)
        if (alive && askAgain) {
          askAgain = false
          timer = window.setTimeout(beat, 0)
        } else if (alive) timer = window.setTimeout(beat, wait)
      }
    }
    beatNow = () => void beat()
    beat()
    return () => {
      alive = false
      if (beatNow) beatNow = null
      if (timer) window.clearTimeout(timer)
    }
  }, [everyMs])
}

export function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

/* --------------------------------- helpers --------------------------------- */
/* Presentation only: truncation and time formatting. No domain meaning. */

export function shortId(id: string | null | undefined, n = 10): string {
  if (!id) return ''
  return id.length <= n ? id : id.slice(0, n) + '…'
}

export function when(ts: number | null | undefined): string {
  if (!ts) return ''
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function qs(params: Record<string, string | number | null | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== '') p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

/** Relative time, for reading rather than auditing. */
export function ago(ts: number | null | undefined): string {
  if (!ts) return ''
  const s = Date.now() / 1000 - ts
  if (s < 90) return 'just now'
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.round(h / 24)
  if (d < 7) return `${d}d ago`
  return when(ts)
}

/** The day an act belongs to, said the way a person says it. */
export function dayOf(ts: number): string {
  const d = new Date(ts * 1000)
  const now = new Date()
  const y = new Date(now)
  y.setDate(now.getDate() - 1)
  if (d.toDateString() === now.toDateString()) return 'Today'
  if (d.toDateString() === y.toDateString()) return 'Yesterday'
  return d.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
}

/** Clock time alone, for a row that already says which day it is. */
export function clock(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

/** A stable colour per participant id. Identity only — never a status. */
export function whoColour(id: string | null | undefined): string {
  if (!id) return 'var(--text-faint)'
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0
  return `var(--who-${(h % 6) + 1})`
}

/** First letter of an alias, without its @. */
export function initial(alias: string | null | undefined): string {
  const s = (alias ?? '').replace(/^@/, '')
  return s ? s[0].toUpperCase() : '?'
}

/** Wording only: the act names the record keeps, said the way a person would
 *  say them. Nothing is inferred and nothing is hidden. */
const SAID: Record<string, string> = {
  'execution-started': 'started working',
  'result-returned': 'returned a result',
  'result-recovered': "recovered a run's result",
  'expectation-recorded': 'asked for something',
  'expectation-met': 'delivered what was owed',
  'problem-noticed': 'noticed a problem',
  'media-marked': 'marked a representation',
  'media-generated': 'generated a representation',
  'artifact-changed': 'changed an artifact',
  'help-requested': 'asked for help',
  'clarification-requested': 'asked a question',
  'clarification-answered': 'answered a question',
  'turn-addressed': 'brought somebody in',
  'turn-said': 'said something',
  'brain-oriented': 'got its bearings',
  'consulted-mentis': 'consulted the record',
}
export const said = (act: string) => SAID[act] ?? act.replace(/-/g, ' ')

/* --------------------------- act semantics --------------------------- *
 * Two — and only two — operational facts this interface draws differently
 * from an ordinary act. Both match production exactly:
 *
 *  deferred    `problem-noticed` with NOTHING CAUSED BY IT.
 *              mentis/operational/__init__.py::deferred.
 *  unresolved  `media-marked` whose detail.ref is null and which no
 *              `media-generated` act was caused by. See media.ts.
 *
 * A leaf is not a status. Everything else — including a completed
 * `result-returned` nothing followed — is ordinary.
 * ------------------------------------------------------------------- */
export type ActSemantic = 'ordinary' | 'deferred' | 'unresolved'

export function semantics(acts: Act[]): Map<Id, ActSemantic> {
  const followed = new Set<Id>()
  const generatedFrom = new Set<Id>()
  for (const a of acts) {
    if (a.caused_by) followed.add(a.caused_by)
    if (a.act === 'media-generated' && a.caused_by) generatedFrom.add(a.caused_by)
  }
  const out = new Map<Id, ActSemantic>()
  for (const a of acts) {
    if (a.act === 'problem-noticed' && !followed.has(a.id)) out.set(a.id, 'deferred')
    else if (a.act === 'media-marked' && a.detail.ref == null && !generatedFrom.has(a.id))
      out.set(a.id, 'unresolved')
    else out.set(a.id, 'ordinary')
  }
  return out
}

/* --------------------------------------------------------------------- *
 * WHERE EACH STATUS FIELD CAME FROM. Four sources, and nothing is shown
 * stronger than its source says:
 *
 *   recorded   an act in the record says exactly this
 *   computed   derived from recorded acts by a stated rule
 *   runtime    what THIS server process observes now; not durable
 *   unknown    the record cannot say, and `why` says why
 * --------------------------------------------------------------------- */
export type Source = 'recorded' | 'computed' | 'runtime' | 'unknown'

export interface Sourced<T> {
  value: T
  source: Source
  why?: string
}

/** Something an expectation asks OF the viewer and nobody has answered. */
export interface OwedItem {
  expectation: Id
  expects: string
  turn: Id | null
  number: number | null
  conversation: Id | null
  /** present on the Brain-wide read, where the Conversation is not implied */
  conversation_name?: string | null
  asked_by: Id
  asked_by_alias: string | null
  because: string | null
  /** how many alternatives the asker stated; 0 is none stated */
  options: number
  at: number
  /** a question of a decision form (P7): its form and its own words */
  form?: string | null
  question?: string | null
}

export interface OwedList {
  participant: Id
  /** null when the question could not be asked, never "nothing owed" */
  owed: OwedItem[] | null
  total: number | null
  omitted: number | null
  error?: string
}

export interface WorkChild {
  expectation: Id
  carrier: Id | null
  carrier_alias: string | null
  persona: Id | null
  /** the child's state AS SHOWN: `running` only when this server observes the
   *  run (source runtime); a start with no end otherwise is `started-no-end`;
   *  else the record's word (not-ended, returned, failed, ...) */
  state: string
  source: Source
  /** the record's own word (`_child_state`), which resumption reads */
  record_state: string
  /** declared as needed back by the parent (`returns_to`) */
  required: boolean
  turn: Id | null
  number: number | null
  ended_at: number | null
  because: string | null
  claimed_met: boolean
  /** which Workflow activity its delegation said it is for ("<ref>#<key>"); a label, never a position */
  activity?: string | null
}

/** A WORKFLOW GOVERNING A REQUEST, as the work status COMPUTES it from the
 *  record: each activity with the children whose delegation named it, or
 *  "nothing delegated for it". Nothing here is stored and nothing moves the work on. */
export interface WorkflowProgress {
  entry: Id
  name: string
  about: string
  activities: {
    key: string
    what: string
    who: { role?: string; persona?: Id; participant?: Id; persona_name?: string | null; participant_alias?: string | null }
    /** each as it would reach a child now: the current version of what the
     *  procedure pins (`pinned` when that was superseded), and why it reaches
     *  nobody when it does not stand */
    disciplines: { entry: Id; name: string | null; stands?: boolean; why?: string | null; pinned?: Id }[]
    done_when: string
    coordinates: boolean
    children: { expectation: Id; carrier_alias: string | null; state: string; source: Source; number: number | null; turn: Id | null }[]
    said: string | null
  }[]
  /** decisions the Workflow reserves to the owner, as written */
  decisions: string[]
  /** decisions asked under this work (`request_decision`), beside them; no mapping is inferred */
  asked: { expectation: Id; answered: boolean; owed_by_alias: string | null; turn: Id | null; number: number | null; text: string }[]
  done_when: string
  /** children under this work that name no activity of this Workflow */
  elsewhere: number
}

/** ONE PIECE OF WORK, reconstructed from the record on every read. */
export interface TrunkStatus {
  expectation: Id
  turn: Id
  number: number | null
  conversation: Id
  expects: string
  requested_by: Id
  requested_by_alias: string | null
  state: Sourced<string> & { label: string }
  carrier: Sourced<{
    participant: Id | null
    alias: string | null
    assigned_by: Id | null
    assigned_by_alias: string | null
    by_assignment_act: boolean
  }> & {
    persona: Sourced<Id | null>
    runtime: Sourced<string | null> & { execution: Id | null; at: number | null }
    live: Sourced<{ observed: Id[] | null; liveness: Record<Id, string> | null }> | null
    /** runs started before a later run ended, whose own end was never recorded */
    orphaned?: { execution: Id; at: number }[]
  }
  children: Sourced<{
    counts: Record<string, number>
    /** where each count's state came from: runtime for running, else recorded */
    count_sources?: Record<string, Source>
    total: number
    items: WorkChild[]
    omitted: number
    decisions: { expectation: Id; owed_by: Id | null; owed_by_alias: string | null; answered: boolean }[]
    /** other work this declared it waits on (`await_work`); absent from an older server */
    awaits?: {
      expectation: Id
      carrier_alias: string | null
      turn: Id | null
      number: number | null
      met: boolean
      claimed_by_alias: (string | null)[]
    }[]
  }>
  /** null value: nobody said who is looking, which is UNKNOWN and not "nothing" */
  you_owe: Sourced<OwedItem[] | null>
  /** null value: the next transition is not knowable (UNKNOWN), with `why` */
  next: Sourced<string | null>
  last_act: Sourced<{ at: number; act: string; actor: Id; actor_alias: string | null; id: Id }>
  /** absent from an older server */
  workflow?: Sourced<WorkflowProgress[]>
}

export interface ConversationWork {
  conversation: Id
  viewer: Id | null
  runtime_why_not: string | null
  items: TrunkStatus[]
}

/** WHAT CODE THE RUNNING SERVER IS. Observed, never inferred from a branch. */
export interface ServerIdentity {
  process: { pid: number; started_at: number; python: string; host: string | null; port: number | null }
  code: {
    commit: string | null
    commit_why_not: string | null
    subject: string | null
    dirty: boolean | null
    dirty_why_not: string | null
    branch_at_start: string | null
    untracked?: number | null
    repository: string
    observed: string
  }
  /** the checkout on disk NOW, read per request: what lazily imported code and
   *  every worker subprocess read */
  checkout_now?: {
    commit: string | null
    commit_why_not: string | null
    dirty: boolean | null
    dirty_why_not: string | null
    untracked: number | null
    differs_from_start: boolean | null
    /** what counts as code here: the Python the server and workers import */
    code_scope?: string
    /** by content, against the files at start; null with a reason if unknown */
    code_changed_since_start?: boolean | null
    code_changed_why_not?: string | null
    loaded_after_start: string[] | null
    loaded_after_start_why_not: string | null
    observed: string
  }
  ui: {
    present: boolean
    why_not?: string
    assets?: string[]
    index_mtime?: number
    built_from?: { commit: string | null; dirty: boolean | null; untracked?: number | null; built_at: number } | null
    built_from_why_not?: string | null
    changed_since_start: boolean | null
    dist: string
    observed: string
  }
  workspace: string
  corpus: string
  not_claimed: string
}

/* ------------------------------------------------------------------------ *
 * THE GOVERNANCE READS THE SHELL ITSELF ASKS FOR.
 *
 * The lenses, the sheets and the investigations declared their own shapes
 * locally and on purpose: each owns the read it makes. These are the ones
 * the SHELL asks for -- the register's own upgrades, the attention counts on
 * the tabs, the Participant inspector -- and they live here because more than
 * one of the shell's own files reads them.
 *
 * ABSENT, EMPTY AND UNKNOWN ARE THREE ANSWERS, and each of these shapes
 * keeps them apart rather than collapsing them into a nullable number. A
 * count that could not be taken is not zero, and every field below that
 * could be either says which it is.
 * ------------------------------------------------------------------------ */

/** `/api/governance/applies` -- which way one standing item could reach an
 *  execution at all. Read from placement links and the composer's own scope
 *  vocabulary, never from a Kind name. */
export interface AppliesRowRead {
  entry: Id
  kind: string | null
  applies: 'placed' | 'by_persona' | 'when_named'
  why: string
  placed_at: Id[]
  /** null is the Kind declaring nothing, and is never read as false. */
  truth_apt: boolean | null
}

export interface AppliesRead {
  rows: AppliesRowRead[]
  facets: { any_way: number; placed: number; by_persona: number; when_named: number }
  limit: string
}

/** `/api/governance/conditions` -- how often each item actually reached an
 *  execution, from delivery records and nothing else. */
export interface ConditionRowRead {
  entry: Id
  records: number
  selected_as_persona_in: number
  named_in: number
  executions: number
  /** TRUE IS ABSENT, NOT ZERO: no delivery record names it, so nothing was
   *  counted. A zero would claim the looking had been done. */
  uncounted: boolean
  why_uncounted: string | null
}

export interface ConditionsRead {
  rows: ConditionRowRead[]
  /** the denominator, stated, so "named for 3 of 11" can be said */
  executions_with_records: number
  counts_are: string
  error?: string
}

/** One governance act, as `what_changed` reports it. The reason is quoted as
 *  it was recorded: nothing composes a sentence on anybody's behalf. */
export interface ChangedActRead {
  act: Id
  at: number
  /** the act's own word -- established, superseded, disputed, asked ... */
  what: string
  actor: Id | null
  conversation: Id | null
  turn: Id | null
  /** which entries the act was about. An act about nothing names nothing. */
  about: Id[]
  because: string | null
  detail: Record<string, unknown> | null
}

/** `/api/governance/since` -- what changed between this person's last two
 *  arrivals.
 *
 *  A CATCH-UP IS A PAIR OF ARRIVALS. Never having arrived is ABSENT, one
 *  arrival BOUNDS NOTHING, and both say so instead of reporting an empty
 *  window as "nothing changed". There is no mark-as-read anywhere. */
export interface SinceRead {
  participant: Id
  conversation: Id | null
  arrivals: number
  bounded: boolean
  window: { from: number; to: number; from_arrival: Id; to_arrival: Id } | null
  changed: { acts: ChangedActRead[]; total: number; empty: string | null } | null
  first_arrival?: number
  why?: string
  error?: string
}

/** One side of `/api/…` `proposed`: what is put forward, in one direction.
 *
 *  PROPOSED IS NOT DONE. Nothing in here has ended anything or reaches
 *  anybody: every predecessor named stands exactly as it stood, and several
 *  competing proposals may name the same one. `withdrawn` counts proposals
 *  whose own link was superseded, which are left out of `items` for the same
 *  reason a superseded link is left out of `incoming`. */
export interface ProposedSideRead {
  items: {
    entry: Id
    link: Id
    reason: string | null
    attributed_to: Id | null
    by_alias: string | null
    written_by: string | null
    at: number | null
    kind: string | null
    summary: string | null
    stands: boolean
    state: 'candidate' | 'stands' | 'ended' | 'replaced'
  }[]
  total: number
  omitted: number
  withdrawn: number
}

/** `proposed` on an item read, a timeline step or a register row.
 *
 *  TWO DIRECTIONS, NEVER MERGED, AND NEITHER IS `superseded_by`. `successors`
 *  are the ones put forward to replace this; `predecessors` are what this is
 *  put forward to replace. What actually ended something is `superseded_by`
 *  and is a different fact on a different relation.
 *
 *  The whole object is null when the record declares no relation that proposes
 *  the superseding role — NOT DECLARED, which is not "none recorded". */
export interface ProposedRead {
  entry: Id
  relation: string
  successors: ProposedSideRead
  predecessors: ProposedSideRead
  confers: string
}

/** One step of `/api/governance/history`, oldest first. */
export interface HistoryStepRead {
  entry: Id
  missing?: boolean
  kind?: string | null
  body?: Record<string, unknown>
  at?: number
  attributed_to?: Id
  written_by?: string | null
  state?: 'candidate' | 'stands' | 'ended' | 'replaced'
  /** AN EMPTY LIST IS THE SENTENCE "nobody established this". */
  established?: GovLinkRead[]
  placed_at?: GovLinkRead[]
  superseded_by?: GovLinkRead[]
  supersedes?: GovLinkRead[]
  disputes?: DisputeRead[]
  /** what is merely PROPOSED to replace this step, and what it proposes to
   *  replace. A timeline that walked `supersedes` alone could show an item
   *  with four proposals against it as one nothing had been proposed against. */
  proposed?: ProposedRead | null
}

export interface GovLinkRead {
  link: Id
  relation: string
  from: Id
  to: Id
  at: number
  by: Id | null
  by_alias: string | null
  written_by: string | null
  /** what the act said it was for, where the act said anything */
  reason: string | null
}

/** One challenge, and whether it was answered.
 *
 *  A SET-ASIDE IS NOT A THIRD KIND OF LINK. It is the opposing act on the
 *  same axis, so both facts stay true at once: the item was disputed AND it
 *  stands. `open` is the engine's own word for the first without the second.
 *  `from` is the note that carries the challenge in the disputer's words. */
export type DisputeRead = GovLinkRead & {
  disputed_by: Id
  set_aside: GovLinkRead | null
  open: boolean
}

export interface ItemHistoryRead {
  entry: Id
  chain: Id[]
  timeline: HistoryStepRead[]
  oldest_first: boolean
  /** which relation carries "proposed to replace" in this record, or null
   *  where none does. Null is NOT DECLARED and never "none recorded". */
  proposal_relation?: string | null
  proposals_readable?: boolean
  error?: string
}

/** `/api/governance/deliveries` -- which delivery records named this item,
 *  newest first. The other direction from the execution sheet: a count cannot
 *  be opened, and this is what opens it. */
export interface DeliveryNamingRead {
  delivery: Id
  execution: Id
  participant: Id | null
  runtime: string | null
  conversation: Id | null
  mechanism: string | null
  at: number | null
  /** every way each item asked about reached this execution. One record may
   *  name the same item twice and by two ways, and both are facts. */
  names: Record<Id, { source_kind: string; scope: string; how: string; why: string }[]>
  carries: Id[]
  carries_all: boolean
}

export interface DeliveriesPerEntry {
  entry: Id
  /** `absent` or `named`. Absent is not a count of zero. */
  answer: 'absent' | 'named'
  records: number
  executions: number
  latest: Id | null
  latest_execution: Id | null
  latest_at: number | null
  latest_participant: Id | null
  participants: Id[]
  records_naming_no_participant: number
  uncounted: boolean
  why_uncounted: string | null
}

export interface DeliveriesRead {
  entries: Id[]
  deliveries: DeliveryNamingRead[]
  returned: number
  total: number
  omitted: number
  per_entry: DeliveriesPerEntry[]
  records_considered: number
  /** a real answer about those records, not a reason to drop them */
  records_listing_no_behavioural_material: number
  error?: string
}

/** `/api/who/<id>` -- what the record knows about one name. Observed, never
 *  inferred.
 *
 *  A PARTICIPANT IS DURABLE, AND IS NOT A RUNTIME AND NOT A PERSONA. The
 *  runtimes here are the ones this name has actually been carried on, which is
 *  history and not a capability; the Persona it was started as is a
 *  per-execution choice and is read from delivery records, not from here.
 *
 *  WHETHER IT IS A PERSON IS NOT A FACT THIS RECORD HOLDS. The resolve read
 *  says so in its own docstring: nothing is derived from the prose in `about`.
 *  So there is no `person` field to mirror, and a surface that wants the
 *  distinction has to say UNKNOWN rather than guess it. */
export interface WhoRead {
  ref: Id
  known: boolean
  why_not?: string
  what?: string
  kind?: string
  alias?: string
  about?: string
  conversations?: Id[]
  working_now?: Id[]
  /** observed in this name's own history; not a claim about what it could do */
  runtimes_observed?: string[]
  models_observed?: string[]
  /** the held image chosen to picture this name; null means the default */
  avatar?: Id | null
  /** where this name last ran; null if it never has */
  runtime?: string | null
  /** A PERSON'S DECLARATION of the runtime this name's work runs on when the
   *  work names none, or null. Never derived from the alias. */
  default_runtime?: string | null
  /** `default` (declared), `auto` (declared runtime-auto) or `undeclared` */
  runtime_mode?: 'default' | 'auto' | 'undeclared'
  /** the runtimes this Mentis knows how to run */
  runtimes_known?: string[]
  acts_seen?: number
  recent?: { id: Id; act: string; at: number; execution?: Id | null; runtime?: string | null }[]
}
