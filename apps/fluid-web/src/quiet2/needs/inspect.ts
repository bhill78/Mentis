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

/** A REFERENCE EXACTLY AS ONE QUESTION DECLARED IT, with how the record it
 *  names stands now (`mentis/fluid/inspect.py` `declared`): the author's own
 *  reference object, and -- for a record -- `availability`, that id resolved
 *  by the same resolver as every other reference here. */
export interface DeclaredRef {
  kind?: string
  id?: string
  label?: string
  repository?: string
  sha?: string
  url?: string
  availability?: Ref | null
}

/** WHAT ONE QUESTION OF A FORM DECLARES, BY ITS EXACT EXPECTATION ID, as the
 *  server projects it (`question_references`, contract ent-40166218c575 §3).
 *  A form-wide union must never make one question's primary source appear to
 *  belong to another, so where the server gives this, each question's subject
 *  is drawn under that question and the union is not drawn as the item's
 *  single subject. Absent from a server that does not project it; then nothing
 *  per question is claimed. */
export interface QuestionReference {
  expectation: string
  presentation?: unknown
  presentation_status?: { state?: string | null; problems?: unknown } | null
  /** the one source that question declares, or null where it declared none */
  primary?: DeclaredRef | null
  supporting?: DeclaredRef[] | null
}

/** One question of a form, as this page draws it. */
export interface AboutQuestion {
  id: string
  question: string | null
  subject: Ref[]
  evidence?: Ref[]
  /** complete, legacy, incomplete, unsupported: the derived, read-only state */
  presentation_state?: string | null
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
  /** each question of this form by its expectation id, where the server
   *  projects it: never pooled, never keyed by anything but that id */
  question_references?: QuestionReference[] | null
  operation?: AboutOperation
  error?: string
}

/** What part a declared reference plays, in the question's own words. */
export const PRIMARY_ROLE = 'the one source this question is about'
export const SUPPORTING_ROLE = 'further material this question names'

/** A DECLARED REFERENCE AS THIS PAGE SHOWS ONE. A record is the resolution of
 *  its exact id and nothing else -- never the author's label standing in for a
 *  record that could not be read. A commit or an address is named as what it
 *  is, with where it is, and is not opened from here. */
export function declaredRef(d: DeclaredRef | null | undefined, relation: string): Ref | null {
  if (!d || typeof d !== 'object') return null
  const label = typeof d.label === 'string' && d.label.trim() ? d.label.trim() : null
  if (d.kind === 'record' && typeof d.id === 'string') {
    const a = d.availability
    if (a && typeof a === 'object' && typeof a.id === 'string') return { ...a, relation }
    /* the server named it and did not say how it stands: say exactly that */
    return { id: d.id, type: 'unknown', label, available: false, state: 'unreadable',
      why: 'How this stands now was not read.', opens: null, relation }
  }
  if (d.kind === 'commit' && typeof d.sha === 'string') {
    return { id: `commit:${d.repository ?? ''}:${d.sha}`, type: 'commit', label, available: false, state: 'ok',
      why: `${d.repository ?? 'a repository'} ${d.sha.slice(0, 12)}`, opens: null, relation }
  }
  if (d.kind === 'url' && typeof d.url === 'string') {
    return { id: `url:${d.url}`, type: 'url', label, available: false, state: 'ok', why: d.url, opens: null, relation }
  }
  return null
}

/** The questions a form declares separately, where there is more than one of
 *  them: that is the only case in which a union could mislead. `words` is each
 *  question's own recorded wording, where the list read carries it. */
export function questionsOf(about: About | null | undefined, words?: ReadonlyMap<string, string | null>): AboutQuestion[] {
  if (!about || about.error || !Array.isArray(about.question_references)) return []
  const qs = about.question_references.filter((q) => !!q && typeof q.expectation === 'string')
  if (qs.length < 2) return []
  return qs.map((q) => ({
    id: q.expectation,
    question: words?.get(q.expectation) ?? null,
    subject: [declaredRef(q.primary, PRIMARY_ROLE),
      ...(Array.isArray(q.supporting) ? q.supporting : []).map((s) => declaredRef(s, SUPPORTING_ROLE))]
      .filter((r): r is Ref => !!r),
    presentation_state: typeof q.presentation_status?.state === 'string' ? q.presentation_status.state : null,
  }))
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
  /* A question's own references are resolved too, so an id in its words reads
     as the thing that question names -- by its exact id, as everywhere here. */
  const perQuestion = (about.question_references ?? []).flatMap((q) =>
    [declaredRef(q?.primary, PRIMARY_ROLE),
      ...(Array.isArray(q?.supporting) ? q.supporting : []).map((s) => declaredRef(s, SUPPORTING_ROLE))]
      .filter((r): r is Ref => !!r))
  for (const r of [...about.subject, ...about.evidence, ...about.context, ...about.referenced, ...perQuestion]) {
    if (r && !out.has(r.id)) out.set(r.id, r)
  }
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
  if (r.type === 'commit') return 'commit'
  if (r.type === 'url') return 'link'
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
export function gaps(about: About | null | undefined, error?: string | null, words?: ReadonlyMap<string, string | null>): string[] {
  if (error) return [`What this request names could not be read (${error}). Open the asking post to see what it says.`]
  if (!about) return []
  if (about.error) return [`What this request names could not be read: ${about.error}. Open the asking post to see what it says.`]
  const out: string[] = []
  for (const r of about.subject) {
    if (r.available && r.opens) continue
    out.push(`${capital(goneWords(r))} is what you would be deciding on, and it cannot be opened: ${r.why ?? 'it could not be read.'}`)
  }
  /* SEVERAL QUESTIONS, SEVERAL SUBJECTS: each said under the question it
     belongs to, so a subject that cannot be opened is never attributed to the
     wrong question. */
  for (const q of questionsOf(about, words)) {
    for (const r of q.subject ?? []) {
      /* a commit or an address is named with where it is, and was never
         something this page opens: that is not an omission */
      if ((r.available && r.opens) || r.type === 'commit' || r.type === 'url') continue
      const which = q.question ? ` in “${clip(q.question, 80)}”` : ''
      const words = `${capital(goneWords(r))} is what you would be deciding on${which}, and it cannot be opened: ${r.why ?? 'it could not be read.'}`
      if (!out.includes(words)) out.push(words)
    }
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
