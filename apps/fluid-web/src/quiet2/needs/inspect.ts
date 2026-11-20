/* INSPECT BEFORE DECIDING: what a Needs You request is about, as the page
 * says it (owner, 2026-11-20).
 *
 * The server says what each request names (`GET /fluid/api/needs-you/about`,
 * mentis/fluid/inspect.py): the SUBJECT (what would be approved), the
 * EVIDENCE the record says supports it, the CONTEXT it was asked in, and what
 * its words merely REFERENCE -- each resolved by its exact id, or said to be
 * unreadable. This module is everything the page decides from that, apart
 * from React and the browser, so it is checkable
 * (`tests/quiet2_needs_inspect_unit.ts`).
 *
 * THE RULES IT KEEPS:
 *   - a reference is found by its id and by nothing else: never by a title,
 *     and never by a `#12` in somebody's prose;
 *   - an id that resolves to nothing is still shown, as what it is;
 *   - a role the record does not state is not claimed ("Also named");
 *   - a subject that cannot be opened is said before the decision is made. */

export type Opens = 'post' | 'record' | 'conversation' | 'file' | null

export interface Ref {
  id: string
  /** post, record, finding, request, run, file, conversation, participant, link, entry, activity, unknown */
  type: string
  /** a record's Kind */
  kind?: string | null
  label: string | null
  available: boolean
  /** ok, missing, deleted, erased, unreadable, purged, ... */
  state: string
  why: string | null
  opens: Opens
  /** what part the record says it plays */
  relation: string
  post?: string | null
  conversation?: string | null
  conversation_name?: string | null
  number?: number | null
  by_name?: string | null
  status?: string | null
  file?: { state: string; name?: string | null; size?: number | null; claimed_media_type?: string | null } | null
  /** a form (an input's response set, which is this reference's id): the
   *  block's name and the part of the post it is in */
  block?: string | null
  part?: number | null
}

export interface AboutOperation {
  summary?: string; command?: string; cwd?: string; tool?: string; tool_label?: string
  resources?: string[]; workspace?: string | null; within?: boolean; outside?: string[]
  why?: string | null; agent_says?: string | null
}

export interface About {
  id: string
  /** form, findings, permission, adoption, input, decision, request */
  kind: string
  form: string | null
  says: string
  asked_by_name: string
  subject: Ref[]
  evidence: Ref[]
  context: Ref[]
  referenced: Ref[]
  operation?: AboutOperation
  error?: string
}

/** An id as Mentis writes one, wherever it stands in words. (No lookbehind:
 *  the character before it is taken and put back.) */
const MENTION = /(^|[^0-9A-Za-z_-])((?:ent|opr|adm)-[0-9a-f]{6,})(?![0-9A-Za-z_-])/g

/** Every id written in the words, once each, in the order written. */
export function mentionsOf(text: string | null | undefined): string[] {
  const out: string[] = []
  for (const m of (text ?? '').matchAll(MENTION)) if (!out.includes(m[2])) out.push(m[2])
  return out
}

export type Segment = { text: string } | { ref: Ref } | { unknown: string }

/** Every reference the server resolved for this request, by its exact id. */
export function refsOf(about: About | null | undefined): Map<string, Ref> {
  const out = new Map<string, Ref>()
  if (!about || about.error) return out
  for (const r of [...about.subject, ...about.evidence, ...about.context, ...about.referenced]) if (!out.has(r.id)) out.set(r.id, r)
  return out
}

/** The words cut at each id: the words between, and each id as the reference
 *  the server resolved for EXACTLY that id -- or as unknown, where it
 *  resolved none (never the nearest thing). */
export function segments(text: string, refs: Map<string, Ref>): Segment[] {
  const out: Segment[] = []
  let at = 0
  for (const m of text.matchAll(MENTION)) {
    const start = (m.index ?? 0) + m[1].length
    if (start > at) out.push({ text: text.slice(at, start) })
    const r = refs.get(m[2])
    out.push(r ? { ref: r } : { unknown: m[2] })
    at = start + m[2].length
  }
  if (at < text.length) out.push({ text: text.slice(at) })
  return out
}

const clip = (s: string, n: number) => (s.length <= n ? s : s.slice(0, n - 1).trimEnd() + '…')
const kindWord = (k: string | null | undefined) => (k ? k.replace(/[-_]/g, ' ') : 'record')

/** What kind of thing a reference is, in a word or two. */
export function typeWords(r: Ref): string {
  if (r.type === 'record') return kindWord(r.kind)
  if (r.type === 'entry') return r.kind ? kindWord(r.kind) : 'entry'
  if (r.type === 'post') return r.number != null ? `post #${r.number}` : 'post'
  if (r.type === 'finding') return 'finding'
  if (r.type === 'request') return r.number != null ? `request in #${r.number}` : 'request'
  if (r.type === 'run') return 'run'
  if (r.type === 'file') return 'file'
  if (r.type === 'form') return 'form'
  if (r.type === 'conversation') return 'conversation'
  if (r.type === 'participant') return 'participant'
  return r.type === 'unknown' ? 'reference' : r.type
}

/** What cannot be read, said as what it is: never blank, never a guess. */
export function goneWords(r: Ref): string {
  if (r.state === 'deleted') return r.number != null ? `a deleted post (#${r.number}${r.conversation_name ? ` in ${r.conversation_name}` : ''})` : 'a deleted post'
  if (r.state === 'erased') return 'something permanently deleted'
  if (r.state === 'missing') return 'something this Brain does not hold'
  if (r.type === 'file') return r.label ? `the file “${r.label}”, which cannot be opened` : 'a file that cannot be opened'
  return 'something that could not be read'
}

/** A reference as a person reads it in running words: what it is and what it
 *  says. Its id is never its name. */
export function refName(r: Ref, max = 90): string {
  if (r.state !== 'ok') return goneWords(r)
  const what = typeWords(r)
  if (!r.label) return r.type === 'run' ? 'a run' : `a ${what}`
  if (r.type === 'conversation' || r.type === 'participant' || r.type === 'run' || r.type === 'file' || r.type === 'activity' || r.type === 'link') return r.label
  if (r.type === 'form') return `the form “${r.label}”${r.number != null ? ` in post #${r.number}` : ''}${r.part ? `, part ${r.part + 1}` : ''}`
  return `${what} “${clip(r.label, max)}”`
}

/** Where a reference is, where that is not obvious from its name. */
export function whereWords(r: Ref, here?: string | null): string | null {
  if (!r.conversation || r.type === 'conversation') return null
  const name = r.conversation_name || 'another conversation'
  if (r.type === 'post') return r.conversation === here ? null : `in ${name}`
  return [r.number != null ? `#${r.number}` : null, r.conversation === here ? null : `in ${name}`].filter(Boolean).join(' ') || null
}

/** The words with every id replaced by its readable name: for places that
 *  cannot hold a link (a button's own words, a tooltip, a label). */
export function plain(text: string | null | undefined, refs: Map<string, Ref>, max = 60): string {
  if (!text) return ''
  return segments(text, refs).map((s) => ('text' in s ? s.text : 'ref' in s ? refName(s.ref, max) : 'a reference that could not be read')).join('')
}

/** How the subject is headed, by what kind of request it is. */
export function subjectHeading(about: About): string {
  if (about.kind === 'input') return 'You are asked to fill in'
  if (about.kind === 'request') return 'You are asked for'
  return 'You are deciding on'
}

/** What is being decided where the record names no item for it: said as
 *  that, never dressed up as a record. */
export function subjectWords(about: About): string | null {
  if (about.subject.length) return null
  if (about.kind === 'permission') return about.operation?.summary ?? 'An operation the run did not describe.'
  if (about.kind === 'adoption') return null
  if (about.kind === 'request') return 'A reply to this request, as it was written.'
  if (about.kind === 'form') return 'The questions as asked. The record names no other item for them.'
  return 'The question as asked. The record names no other item for it.'
}

/** WHAT THE OWNER WOULD BE DECIDING WITHOUT SEEING: each subject that cannot
 *  be opened, and a request whose subject the record should name and does
 *  not. Said before the decision; it never blocks one. */
export function gaps(about: About | null | undefined, error?: string | null): string[] {
  if (error) return [`What this request names could not be read (${error}). Open the asking post to see what it says.`]
  if (!about) return []
  if (about.error) return [`What this request names could not be read: ${about.error}. Open the asking post to see what it says.`]
  const out: string[] = []
  for (const r of about.subject) {
    if (r.available && r.opens) continue
    out.push(`${capital(goneWords(r))} is what you would be deciding on, and it cannot be opened: ${r.why ?? 'it could not be read.'}`)
  }
  if (about.kind === 'adoption' && !about.subject.length) out.push('This asks you to adopt a record, and the request does not name which one.')
  if (about.kind === 'permission' && !about.operation?.command && !about.operation?.summary) out.push('This asks permission for an operation, and the run did not say what it is.')
  return out
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** The item's own line in the list: the question, with its ids read out. */
export function itemName(about: About | null | undefined, what: string): string {
  if (!about || about.error) return what
  if (about.kind === 'adoption' || about.kind === 'findings' || about.kind === 'permission' || about.kind === 'input') return about.says
  /* several questions: no one of them is the item's name */
  if (about.kind === 'form' && /\d+ questions\.$/.test(about.says)) return about.says
  return plain(what, refsOf(about))
}

/** What the reference's control is called, for a screen reader and a tooltip. */
export function openLabel(r: Ref): string {
  const where = r.opens === 'record' ? 'Open the record' : r.opens === 'file' ? 'Open the file' : r.opens === 'conversation' ? 'Open the conversation' : 'Go to the post'
  return `${where}: ${refName(r, 70)}`
}
