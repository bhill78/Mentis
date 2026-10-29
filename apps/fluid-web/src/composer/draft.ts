import type { FindingChoice, Id } from '../api'

/* ------------------------------------------------------------------------ *
 * WHAT IS BEING COMPOSED.
 *
 * The composer used to hand back a string, and every other decision the owner
 * made -- who this is for, which topic it goes under -- lived in the
 * surface's own state beside it. That worked while there were two decisions.
 * It stops working the moment addressing carries a RUNTIME, because then the
 * thing being composed has structure and the structure has to survive being
 * saved as a draft, restored, and sent from two different surfaces.
 *
 * So a draft is one value. It is what the owner has decided so far, it is
 * exactly what the POST body is built from, and it is serialisable -- which
 * is the whole reason a draft can be kept at all.
 * ------------------------------------------------------------------------ */

/** Addressing somebody, and separately deciding whether to spend a runtime.
 *
 *  THE TWO ARE NOT THE SAME DECISION, and this is the type that keeps them
 *  apart. `@Vera` in a sentence addresses Vera. It does not ask Vera's runtime
 *  to do anything, and inferring that it does would make every mention of a
 *  name cost money and start a process. `dispatch` is the owner saying so. */
export interface Addressee {
  participant: Id
  alias: string
  /** true only when the owner explicitly asked for work, never inferred */
  dispatch: boolean
  /** WHERE the work goes. Unset means unset: the selection decides, and says
   *  what informed it. This is never silently filled with a default. */
  runtime?: string
  model?: string
  effort?: string
  /** WHICH PERSONA THIS WORK IS DONE AS. A durable Persona entry id, not
   *  a name: two Personas may be called the same thing. Unset means the
   *  agent is asked as itself, which is a real answer and the usual one.
   *  Choosing one is a behavioural decision, so it sits beside runtime and
   *  model -- the other things that decide how the work is carried out. */
  persona?: Id
  /** Deliberately NOT reusing a live instance under the same binding. A fresh
   *  one is a legitimate thing to want -- a clean context -- and it is a
   *  different request from "talk to the one already there". */
  newInstance?: boolean
  /** This name was summoned rather than found. Kept apart from
   *  `newInstance`, which is about a live process: one is "somebody new to
   *  this Conversation", the other is "a clean context for somebody already
   *  here", and the two are not the same request. */
  summoned?: boolean
  /** "MAY COORDINATE THIS WORK": the owner granting THIS request the ability
   *  to organise -- summon, open places, propose, answer (handing work on
   *  with `delegate` needs no grant: every dispatched run holds it). It belongs to the
   *  request, not to the Participant: the next request to them is ordinary
   *  unless granted again or explicitly continuing work that was. No
   *  operations are chosen here; the server records which ones it contained. */
  coordinate?: boolean
  /** FOLLOW-UP PERMISSION, the owner's, on this request: may discovered side
   *  work be pursued without asking again? Absent is "ask afterward";
   *  a number is how many generations of independently pursued discovery;
   *  'unrestricted' is no limit. It carries through the work's follow-ups. */
  followUp?: number | 'unrestricted'
  /** EXECUTION CONSENT, the owner's, on this request (docs/run-consent.md §1):
   *  which OPERATIONS need asking, not whether side work may be pursued --
   *  that is `followUp`, and neither implies the other. Absent is "each
   *  operation is asked" and sends nothing. `extra` is the optional
   *  categories the owner added to the routine ones (`ROUTINE`). */
  consent?: Consent
}

export type ConsentMode = 'ask' | 'task' | 'deny'
export interface Consent { mode: 'task' | 'deny'; workspaces: string[]; extra?: string[] }
/** What is routine for a task unless the owner adds more, as the server reads it. */
export const ROUTINE = ['read', 'edit', 'test', 'build', 'run', 'git']
/** Routine only when the owner says so. */
export const OPTIONAL = ['delete', 'git-remote', 'network', 'install']

/** The dispatch spec's `consent`. CATEGORIES ONLY WHEN SOMETHING WAS ADDED,
 *  then the whole list: the routine ones are implied, and a `deny` consent
 *  refuses whatever would be asked, so it has no categories to say. */
export const consentSpec = (c: Consent) => ({
  mode: c.mode,
  workspaces: [...c.workspaces],
  ...(c.mode === 'task' && c.extra?.length ? { categories: [...ROUTINE, ...OPTIONAL.filter((x) => c.extra!.includes(x))] } : {}),
})

export interface Attached {
  /** The bytes are sent to Mentis the moment they are attached and
   *  HELD there, but nothing is RECORDED until the Turn is posted: `ref` is
   *  then `sha256:<hex>`, and the server turns it into an Admission in the
   *  same transaction as the Turn. For an artifact Mentis already holds, `ref`
   *  is its Admission id and nothing is sent again. */
  id: string
  /** metadata: what the author's machine called it. Never identity. */
  name: string
  mime: string
  size: number
  /** an object URL for preview; revoked when the draft is dropped */
  preview?: string
  ref?: string
  state?: 'sending' | 'held' | 'failed'
  error?: string
}

/** The parts a draft's attachments become. */
export const attachedParts = (a: Attached[]) =>
  a
    .filter((x) => x.ref && x.state === 'held')
    .map((x) => ({
      type: x.mime.startsWith('image/') ? 'image' : 'file',
      ref: x.ref,
      media_type: x.mime || null,
      alt: x.name,
    }))

/* ------------------------------------------------------------------------ *
 * WHAT THE AUTHOR MEANT BY SENDING THIS.
 *
 * THREE MEANINGS, NOT THREE MODES. Software cannot tell a note from a request
 * when the prose is identical, and both alternatives are worse than asking: a
 * classifier reading every Turn, or a triage conversation before every message.
 * One visible action supplies the missing bit and costs nothing to read.
 *
 *   record-only      nothing is owed and nothing runs. Notes, thinking aloud,
 *                    "thanks", disagreement, an answer that asks for nothing.
 *   ask-mentis       the normal generic request. No runtime is chosen by hand.
 *   ask-participant  somebody was picked for work, which RETARGETS the same
 *                    action rather than being a different button.
 *
 * MENTION-ONLY IS NOT ONE OF THEM. Addressing @Vera in a sentence is a fact
 * about the Turn; asking Vera's runtime to do something is a separate decision,
 * which `Addressee.dispatch` already holds. A mention retargets nothing and
 * never costs a runtime.
 * ------------------------------------------------------------------------ */

export type Action = 'record-only' | 'ask-mentis' | 'ask-participant'

export interface ScratchExecution { runtime?: string; model?: string }

/** WHAT THE OWNER SAID GOVERNS THIS WORK, by reference.
 *
 *  Standing procedural material (a Kind declaring `knowing: "how"`) chosen
 *  with "Use…". It travels as `governed` on every dispatched request and on
 *  an Ask Mentis request, which is the existing contract: the request holds
 *  ids, and each run is composed against what stands when it runs. It is not
 *  placement and changes nothing about where the material applies.
 *
 *  ABSENT IS "NOTHING SAID", and the composer drops `use` when the last chip
 *  is removed rather than sending `[]`: for a new request the two mean the
 *  same, and only the owner deliberately saying "nothing" should ever be
 *  recorded as that. `said` is the chip's words, for display only. */
export interface Use {
  governed: Id[]
  said?: Record<Id, string>
}

export interface Draft {
  /** Scratch model constraints, independent of addressing or dispatch. */
  execution?: ScratchExecution
  text: string
  to: Addressee[]
  /** Topic MEMBERSHIP: this Turn is filed under these. */
  topics: Id[]
  /** Authored inline REFERENCES: these characters name that Topic. A
   *  different fact from membership, and neither implies the other. */
  marks: Mark[]
  attached: Attached[]
  /** What the author chose, where they chose. Unset means the surface's own
   *  default applies -- and that default is `record-only` wherever a reply is
   *  being written, because answering something must never launch anything by
   *  itself. */
  action?: Action
  /** Governed material named for this work; see `Use`. */
  use?: Use
  /** REFERENCES DROPPED INTO THE DRAFT (Fluid W4): an object inside a post,
   *  or a whole post, each a reference part shown as a chip and written only
   *  when the draft is sent. See `DraftRef`. */
  refs?: DraftRef[]
}

/** A reference the draft will carry: the part exactly as it is sent --
 *  `object` (one object in a post, by its post, key and exact version;
 *  mentis/conversation/objectref.py) or `turn` (a whole post) -- never a copy
 *  of what it names. */
export interface DraftRef {
  part: { type: 'object' | 'turn'; ref: Id; text: string; [k: string]: unknown }
}

/** The parts a draft's references become, after what the author wrote: each
 *  on its own line, so the words never run into them. */
export const refParts = (text: string, refs: DraftRef[] = []): Record<string, unknown>[] =>
  refs.flatMap((r, i) => [...(text || i ? [{ type: 'text', text: '\n\n' }] : []), { ...r.part }])

/** Add a reference, once: the same object (or post) dropped twice is one chip. */
export const withRef = (refs: DraftRef[] = [], next: DraftRef): DraftRef[] =>
  refs.some((r) => r.part.type === next.part.type && r.part.ref === next.part.ref && r.part.key === next.part.key) ? refs : [...refs, next]

export const emptyDraft = (): Draft => ({ text: '', to: [], topics: [], marks: [], attached: [] })

/** The action this draft actually carries.
 *
 *  ONE FUNCTION, because the label on the button and the field in the POST must
 *  never disagree -- a button reading "Record only" over a body that dispatches
 *  would be the interface lying about what it is about to spend.
 *
 *  `record-only` DOMINATES. Choosing it while somebody is still marked for work
 *  is a contradiction, and the safe reading of a contradiction is the one that
 *  starts nothing.
 */
export const actionOf = (d: Draft, fallback: Action = 'ask-mentis'): Action => {
  if (d.action === 'record-only') return 'record-only'
  if (d.to.some((a) => a.dispatch)) return 'ask-participant'
  return d.action ?? fallback
}

/** WHAT THE BUTTON SAYS IT WILL DO, computed from the same function the POST
 *  body uses -- so the label and the act cannot disagree. Kept here, beside
 *  `actionOf`, so every composer that sends a draft says it in these words. */
export const sendLabel = (a: Action, target: string | null): string =>
  a === 'record-only' ? 'Record' : a === 'ask-participant' ? `Ask ${target ?? 'them'}` : 'Ask Mentis'

/** WHY, in one line, because the difference is worth a hover and not a manual. */
export const ACTION_WHY: Record<Action, string> = {
  'record-only': 'record this and nothing else. Nobody is asked, nothing runs.',
  'ask-mentis': 'ask Mentis. It records what is owed and assigns it; you pick no runtime.',
  'ask-participant': 'ask the people you marked for work. Nobody else is asked.',
}

/** Who `Ask …` names: the one person marked for work, or how many. */
export const targetOf = (d: Draft): string | null => {
  const working = d.to.filter((a) => a.dispatch)
  return working.length === 0 ? null : working.length === 1 ? working[0].alias : `${working.length} people`
}

export const isEmpty = (d: Draft) =>
  !d.text.trim() && d.to.length === 0 && d.attached.length === 0 && !d.refs?.length

/** WHAT A REPLY SAYS WHEN IT ANSWERS BY CHOOSING ONE OF THE OPTIONS OFFERED.
 *
 *  The label leads, so the Turn reads as an answer rather than as a comment
 *  that happens to agree. `chose` carries WHICH option as data for the server
 *  to check against what was actually offered; the prose is for the reader and
 *  is never the record of the decision.
 *
 *  CHOOSING REPLACES THE ANSWER, NOT THE TURN. Everything else the draft
 *  carries has to survive being an answer: typed text follows the label, and
 *  held attachments follow that, in the order `bodyOf` would have used. A
 *  chosen option and an attached artifact are both ordinary content of one
 *  Turn. This is exported and lives here beside `bodyOf`, rather than staying
 *  a closure inside the surface that answers, because what it builds has to be
 *  runnable to be asserted on -- and the parts it can drop are bytes the owner
 *  already staged, which go missing silently. */
export const chosenBody = (
  d: Draft,
  pick: { label: string; findings?: { ref: Id; label: string }[] },
  option: number,
  expectation: Id,
  /** what was chosen for each finding, where the option asks for that */
  selections?: Record<Id, FindingChoice>,
) => {
  const added = d.text.trim()
  /* EACH FINDING'S CHOICE IS SAID TOO, for whoever reads the Turn; what the
     server acts on is `chose.selections`, never these words. */
  const each =
    selections && pick.findings
      ? pick.findings.map((f) => `${SAID[selections[f.ref] ?? 'defer']}: ${f.label}`)
      : []
  const head = [pick.label, ...each].join('\n')
  return {
    parts: [
      { type: 'text', text: head + (added ? '\n\n' : '') },
      ...(added ? partsOf(added, d.marks) : []),
      ...refParts(head + added, d.refs),
      ...attachedParts(d.attached),
    ],
    text: head + (added ? '\n\n' + added : ''),
    chose: { expectation, option, label: pick.label, ...(selections ? { selections } : {}) },
  }
}

/** WHAT THE OWNER IS TOLD WHEN THEY WITHDRAW WITHOUT SAYING WHY. */
export const WITHDRAW_NEEDS_REASON =
  'Withdraw needs a reason. Write why in the field below, then press Withdraw.'

/** WHAT A REPLY SAYS WHEN IT WITHDRAWS A DECISION INSTEAD OF ANSWERING IT.
 *
 *  The reason is the owner's own words, typed in the same field an answer in
 *  their own words uses, and it is the whole of the Turn. `chose` names the
 *  decision and `withdraw: true`, so the server writes the act that closes it;
 *  the prose is never what closes it. A withdrawal only records -- it starts
 *  and continues nothing -- so the action is record-only whatever the draft
 *  says. No reason, no body: it throws, and the composer shows why. */
export const withdrawBody = (d: Draft, author: Id | null, topics: Id[], expectation: Id) => {
  if (!d.text.trim()) throw new Error(WITHDRAW_NEEDS_REASON)
  return {
    ...bodyOf({ ...d, action: 'record-only' }, author, topics, 'record-only'),
    action: 'record-only' as const,
    dispatch: [],
    chose: { expectation, withdraw: true as const },
  }
}

const SAID: Record<FindingChoice, string> = {
  pursue: 'Pursue',
  defer: 'Keep deferred',
  dismiss: 'Dismiss',
}

/** The POST body, built from the draft and nothing else.
 *
 *  `dispatch` carries only the addressees the owner marked for work, so the
 *  server never has to guess which mention meant "do this". An addressee who
 *  is merely addressed still appears in `addressed_to`, because being spoken
 *  to is a fact about the Turn whether or not anything runs. */
export const bodyOf = (
  d: Draft,
  author: Id | null,
  topics: Id[],
  fallback: Action = 'ask-mentis',
) => {
  const action = actionOf(d, fallback)
  /* WHAT GOVERNS THE WORK goes wherever work is asked for: on each dispatched
     request, and on the request Ask Mentis records. Never under record-only,
     where nothing is owed and nothing runs. */
  const governed = d.use ? { governed: [...d.use.governed] } : {}
  return {
    author,
    /* `parts` is what the record keeps. `text` is still sent because the seam
       accepts either and older callers pass it; when parts are present the
       server uses those, so the authored references survive. */
    parts: [...(d.text.trim() || !d.refs?.length ? partsOf(d.text.trim(), d.marks) : []), ...refParts(d.text.trim(), d.refs), ...attachedParts(d.attached)],
    text: d.text.trim(),
    addressed_to: d.to.map((a) => a.participant),
    topics,
    because: null,
    action,
    ...(action === 'ask-mentis' ? governed : {}),
    /* NOTHING TO DISPATCH UNDER `record-only`, decided here as well as at the
       server. Sending a dispatch the server then refuses would leave the
       interface's intent and the record's intent disagreeing in the log. */
    dispatch:
      action === 'record-only'
        ? []
        : d.to
            .filter((a) => a.dispatch)
            .map((a) => ({
              participant: a.participant,
              runtime: a.runtime ?? null,
              model: a.model ?? null,
              effort: a.effort ?? null,
              persona: a.persona ?? null,
              new_instance: !!a.newInstance,
              coordinate: !!a.coordinate,
              ...governed,
              ...(a.followUp === undefined
                ? {}
                : { follow_up: a.followUp === 'unrestricted' ? 'unrestricted' : { depth: a.followUp } }),
              ...(a.consent ? { consent: consentSpec(a.consent) } : {}),
            })),
  }
}

/* ------------------------------------------------------------------------ *
 * AN AUTHORED REFERENCE, KEPT AS ONE.
 *
 * WHAT WAS BEING THROWN AWAY. When somebody resolves or creates a Topic
 * inline, the composer knows two things exactly: the characters it wrote into
 * the sentence, and the Topic those characters ARE. It then flattened the
 * whole message to one text part and discarded the second. Everything
 * downstream was left to guess which `#Thermal` in the prose meant Thermal --
 * which is not answerable, because `#Thermal` also matches a Topic called
 * `Thermal drift`, and because the same words may appear twice with only one
 * of them a reference.
 *
 * A mark is that fact, held until it can be written down. It is NOT a second
 * kind of Topic membership: membership says this Turn is filed under that
 * Topic, and a mark says these particular characters name it. A Turn may have
 * either, both, or membership without any mark at all.
 *
 * THE SPAN IS TRACKED, NOT RE-FOUND. Offsets are moved by the edits that
 * happen around them and a mark whose own characters have changed is dropped.
 * That is what makes duplicates correct: the mark identifies WHICH occurrence,
 * and a second `#Thermal` typed by hand is prose because nobody resolved it.
 * ------------------------------------------------------------------------ */

export interface Mark {
  /** what this span names. A Topic files the Turn; a Conversation or a Turn
   *  is work being referred to. Different facts, so different part types,
   *  and neither is derived from the other. */
  kind?: 'topic' | 'conversation' | 'turn' | 'acquired'
  /** the identity this span names */
  topic: Id
  /** exactly the characters written, sigil included */
  text: string
  /** where they begin in the draft */
  start: number
}

/** Move marks across an edit, and drop any the edit went through.
 *
 *  The change between two versions of a textarea's value is found as a common
 *  prefix and a common suffix, which is what a single insertion, deletion or
 *  replacement looks like from the outside. It is not a general diff and does
 *  not need to be: anything it cannot account for shows up as a mark whose
 *  characters no longer match, and such a mark is dropped rather than moved to
 *  a place nobody put it.
 */
export function shiftMarks(marks: Mark[], before: string, after: string): Mark[] {
  if (before === after) return marks

  let p = 0
  const max = Math.min(before.length, after.length)
  while (p < max && before[p] === after[p]) p++
  let s = 0
  while (s < max - p && before[before.length - 1 - s] === after[after.length - 1 - s]) s++

  const oldEnd = before.length - s // end of the region that was replaced
  const delta = after.length - before.length

  const out: Mark[] = []
  for (const m of marks) {
    const end = m.start + m.text.length
    let moved: Mark
    if (end <= p) moved = m // wholly before the change
    else if (m.start >= oldEnd) moved = { ...m, start: m.start + delta } // wholly after
    else continue // the edit reached into it; it is no longer what it was
    // Kept only while the characters still say what the mark claims they say.
    if (after.slice(moved.start, moved.start + moved.text.length) === moved.text) out.push(moved)
  }
  return out
}

/** Add a mark, replacing any that overlaps it. */
export function withMark(marks: Mark[], next: Mark): Mark[] {
  const end = next.start + next.text.length
  return [
    ...marks.filter((m) => m.start + m.text.length <= next.start || m.start >= end),
    next,
  ].sort((a, b) => a.start - b.start)
}

/** The message as content parts: prose around typed references.
 *
 *  A Turn with no marks is one text part exactly as before, so nothing about
 *  an ordinary message changes shape. A Turn with marks is text, reference,
 *  text -- and the reference carries the Topic's IDENTITY, so no reader ever
 *  has to work out which characters meant what.
 */
export function partsOf(text: string, marks: Mark[]): Record<string, unknown>[] {
  /* VALIDATED HERE, NOT ASSUMED. `shiftMarks` returns early when nothing
     changed, so asking it to re-check the same text checks nothing: a mark
     left over from an edit it could not follow would then be written as a
     reference over whatever characters now sit at that offset. A mark is a
     claim about specific characters, so it is worth exactly as much as
     whether those characters are still there. */
  const kept = marks
    .filter((m) => text.slice(m.start, m.start + m.text.length) === m.text)
    .sort((a, b) => a.start - b.start)
  if (kept.length === 0) return [{ type: 'text', text }]

  const parts: Record<string, unknown>[] = []
  let at = 0
  for (const m of kept) {
    if (m.start < at) continue // overlapping; the earlier one already stands
    if (m.start > at) parts.push({ type: 'text', text: text.slice(at, m.start) })
    parts.push({ type: m.kind ?? 'topic', ref: m.topic, text: m.text })
    at = m.start + m.text.length
  }
  if (at < text.length) parts.push({ type: 'text', text: text.slice(at) })
  return parts
}
