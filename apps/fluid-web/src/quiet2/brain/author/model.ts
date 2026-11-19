/* THE ONE AUTHORING MODEL FOR BRAIN RECORDS IN QUIET CHAT.
 *
 * Creating a record (the compact modal) and revising one (on the record's
 * page) are two presentations of what is here: what a draft holds, what is
 * shown first and what waits behind "+ Add", what is still missing, and
 * exactly what is sent to the server and in what order. Nothing in this file
 * draws anything, so every rule is checkable without a browser
 * (`tests/brain_author_unit.ts`).
 *
 * WHAT IT DOES NOT DECIDE. Which fields a Kind has, how each is asked for,
 * whether it can be placed and whether it needs a basis are the server's
 * answers (`/api/governance/authoring`). The only thing added here is which
 * fields are the FIRST VIEW: a small table for the seven Kinds an owner
 * writes, and "the first field" for any Kind defined later.
 *
 * AUTHORITY. Recording writes a proposal, always: every create says so
 * explicitly, whatever the server's own default is, and nothing here can
 * establish. Establishing is a separate act on the record. Revising goes
 * through `edit` only, which proposes a new version of a record that stands
 * and never transfers its standing. */
import type { Id } from '../../../api'
import {
  activityRows, fieldText, fieldValue, formOf, storedRow,
  type ActivityRow, type FieldForm, type KindAuthoring,
} from '../../../surfaces/governance/r2Model'
import { citesAfterCreate, entryCreateBody, requiresBasis } from '../../../surfaces/governance/creating'

/** Something held that a record can point at, with words a person can read.
 *  `ref` is the exact reference the server is given; it is never shown. */
export interface Ref { ref: string; label: string; kind: string; note?: string }

export interface Placement { to: 'conversation' | 'persona'; where: string; name: string; reason: string }

export interface Draft {
  /** each field as text, in the form every input here edits it (lists one per
   *  line, activities as JSON): `r2Model.fieldText` / `fieldValue` */
  fields: Record<string, string>
  /** the optional parts on screen, in the order they were asked for */
  open: string[]
  basis: Ref[]
  basisReason: string
  /** what a decision settles: a post or a conversation */
  context: Ref | null
  place: Placement | null
  /** where a conversation instruction applies */
  conversation: { id: Id; name: string } | null
  /** why a revision is being made (optional, as the server has it) */
  because: string
}

export const emptyDraft = (): Draft => ({
  fields: {}, open: [], basis: [], basisReason: '', context: null, place: null, conversation: null, because: '',
})

/* -- what is shown first -------------------------------------------------- */

/** The parts of an editor that are not fields of the record's body. */
export type Extra = 'basis' | 'context' | 'place' | 'because'

interface KindWords { title: string; first: string[]; ask: Record<string, string>; add?: Record<string, string>; example?: string; note?: string }

const WORDS: Record<string, KindWords> = {
  rule: { title: 'rule', first: ['text'], ask: { text: 'What should be done?' }, add: { about: 'Subject' } },
  decision: {
    title: 'decision', first: ['text'], ask: { text: 'What was decided?' }, add: { about: 'Subject' },
    example: 'Question: do releases go to TEST before DAY-TO-DAY? Settled: yes, always; a release reaches DAY-TO-DAY only after it has been accepted on TEST.',
    note: 'Recording a decision does not answer or close an open request.',
  },
  lesson: { title: 'lesson', first: ['text'], ask: { text: 'What was learned?' }, add: { limits: 'Where it stops being true' } },
  persona: { title: 'persona', first: ['name', 'behaviour'], ask: { name: 'What is it called?', behaviour: 'How should it behave?' }, add: { about: 'What it is for' } },
  'conversation-instruction': { title: 'conversation instruction', first: ['text'], ask: { text: 'What should happen in this conversation?' }, add: { about: 'Subject' } },
  discipline: { title: 'discipline', first: ['name', 'text'], ask: { name: 'What is it called?', text: 'Principles and procedure' } },
  workflow: { title: 'workflow', first: ['name', 'activities'], ask: { name: 'What is it called?' } },
}

/** The seven Kinds an owner writes, in the order "New" lists them. A Kind
 *  defined later and declared authorable follows them. */
export const KIND_ORDER = ['rule', 'decision', 'lesson', 'persona', 'workflow', 'discipline', 'conversation-instruction']

export const kindTitle = (kind: string) => WORDS[kind]?.title ?? kind.replace(/[-_]+/g, ' ')
export const kindExample = (kind: string) => WORDS[kind]?.example ?? null
export const kindNote = (kind: string) => WORDS[kind]?.note ?? null

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** One entry per authorable Kind, by name: what "New" offers. */
export function kindChoices(kinds: KindAuthoring[]): { kind: string; label: string }[] {
  const able = kinds.filter((k) => k.authoring)
  const known = KIND_ORDER.filter((n) => able.some((k) => k.kind === n))
  const later = able.map((k) => k.kind).filter((n) => !KIND_ORDER.includes(n)).sort()
  return [...known, ...later].map((kind) => ({ kind, label: cap(kindTitle(kind)) }))
}

export interface Plan {
  kind: string
  title: string
  form: Record<string, FieldForm>
  /** fields on screen from the start */
  first: string[]
  /** fields behind "+ Add" */
  optional: string[]
  /** what else "+ Add" offers */
  extras: Extra[]
  /** shown from the start because the server will not record without it */
  needsBasis: boolean
  needsConversation: boolean
  placeable: boolean
  personaPlaceable: boolean
}

/** A Kind whose material is placed only by reference (a Workflow): a plain
 *  placement is refused by the server, so one is never offered. The
 *  authoring read reports such a Kind as placeable; what tells it apart is
 *  the row group only that sort of Kind declares. */
const placedByReference = (form: Record<string, FieldForm>) => Object.values(form).some((f) => f.input === 'activities')

export function planOf(k: KindAuthoring, mode: 'create' | 'revise' = 'create'): Plan {
  const form = formOf(k.form) ?? {}
  const w = WORDS[k.kind]
  const first = (w?.first ?? k.fields.slice(0, 1)).filter((f) => k.fields.includes(f))
  const a = k.authoring
  const instruction = a?.door === 'instruction'
  const needsBasis = requiresBasis(k)
  const offersBasis = a?.basis === true || needsBasis
  const placeable = mode === 'create' && !instruction && a?.placeable === true && !placedByReference(form)
  const personaPlaceable = mode === 'create' && a?.persona_placeable === true
  const extras: Extra[] = []
  if (k.kind === 'decision' && mode === 'create') extras.push('context')
  if (offersBasis && !needsBasis) extras.push('basis')
  if (placeable || personaPlaceable) extras.push('place')
  if (mode === 'revise') extras.push('because')
  return {
    kind: k.kind, title: kindTitle(k.kind), form, first,
    optional: k.fields.filter((f) => !first.includes(f)),
    extras, needsBasis: needsBasis, needsConversation: instruction && mode === 'create',
    placeable, personaPlaceable,
  }
}

const humane = (f: string) => cap(f.replace(/[_-]+/g, ' '))

/** The question a field is asked with, in the first view. */
export const askOf = (plan: Plan, f: string) => WORDS[plan.kind]?.ask[f] ?? plan.form[f]?.label ?? humane(f)

/** What a part is called in "+ Add" and in its one-line summary. */
export function nameOf(plan: Plan, part: string): string {
  if (part === 'basis') return 'What it is based on'
  if (part === 'context') return 'The question it settles'
  if (part === 'place') return 'Where it applies'
  if (part === 'because') return 'Why it is changing'
  return WORDS[plan.kind]?.add?.[part] ?? plan.form[part]?.label ?? humane(part)
}

export const inputOf = (plan: Plan, f: string): NonNullable<FieldForm['input']> => plan.form[f]?.input ?? 'text'

/* -- what a field says, collapsed to a line ------------------------------- */

const clip = (s: string, n: number) => { const t = s.replace(/\s+/g, ' ').trim(); return t.length > n ? t.slice(0, n - 1).trimEnd() + '…' : t }

export function activityLine(a: ActivityRow, i: number): string {
  return clip((a.what ?? '').split(/\n/)[0] || `Activity ${i + 1}, not written yet`, 90)
}

/** A field's value in one line, for a collapsed part. `names` turns a chosen
 *  participant or persona into its name; an id is never shown. */
export function summaryOf(plan: Plan, f: string, raw: string, names: Record<string, string> = {}): string {
  const input = inputOf(plan, f)
  if (input === 'activities') { const n = activityRows(raw).length; return n === 1 ? '1 activity' : `${n} activities` }
  if (input === 'participant' || input === 'persona') return raw ? (names[raw] ?? 'Chosen') : ''
  const v = fieldValue(raw, input)
  if (Array.isArray(v)) return clip((v as string[]).join(', '), 110)
  return clip(String(v), 110)
}

export const hasValue = (plan: Plan, f: string, raw: string | undefined): boolean => {
  if (!raw) return false
  if (inputOf(plan, f) === 'activities') return activityRows(raw).length > 0
  return raw.trim() !== ''
}

/* -- a draft from a record (revision) ------------------------------------- */

/** The draft a revision starts from: the record's own values, with every
 *  field that already says something on screen, so nothing set earlier is
 *  hidden. */
export function draftFrom(plan: Plan, body: Record<string, unknown>, basis: Ref[]): Draft {
  const fields: Record<string, string> = {}
  for (const f of [...plan.first, ...plan.optional]) fields[f] = fieldText(body[f], plan.form[f]?.input)
  return { ...emptyDraft(), fields, basis, open: plan.optional.filter((f) => hasValue(plan, f, fields[f])) }
}

/* -- has anything been written -------------------------------------------- */

const sameRefs = (a: Ref[], b: Ref[]) => a.length === b.length && a.every((x, i) => x.ref === b[i].ref)

/** The record's body as it would be stored, for comparing two drafts. */
function stored(plan: Plan, d: Draft): string {
  return JSON.stringify([...plan.first, ...plan.optional].map((f) => fieldValue(d.fields[f] ?? '', plan.form[f]?.input)))
}

/** Whether `now` holds anything `start` did not: typed words, an added or
 *  removed activity or row, a reference chosen, a placement begun. */
export function dirty(plan: Plan, start: Draft, now: Draft): boolean {
  return stored(plan, start) !== stored(plan, now) || !sameRefs(start.basis, now.basis)
    || start.basisReason.trim() !== now.basisReason.trim() || (start.context?.ref ?? '') !== (now.context?.ref ?? '')
    || JSON.stringify(start.place) !== JSON.stringify(now.place) || start.because.trim() !== now.because.trim()
    || (start.conversation?.id ?? '') !== (now.conversation?.id ?? '')
    // a row added and still empty is structure the reader made
    || [...plan.first, ...plan.optional].some((f) => (start.fields[f] ?? '') !== (now.fields[f] ?? '') && inputOf(plan, f) !== 'text' && inputOf(plan, f) !== 'line')
}

/* -- what is missing ------------------------------------------------------ */

export interface Problem { message: string; part: string; index?: number }

const said = (d: Draft, f: string) => (d.fields[f] ?? '').trim() !== ''

/** Why this draft cannot be recorded yet, one thing at a time, with the part
 *  to go to; null where it can. ONLY what the server will refuse, what an act
 *  that follows needs (a reason for a citation or a placement), and the one
 *  thing no record can do without: something written. No Kind is given a
 *  required field its definition does not have. */
export function problem(plan: Plan, k: KindAuthoring, d: Draft, mode: 'create' | 'revise', start?: Draft): Problem | null {
  const door = k.authoring?.door
  if (door === 'persona') {
    if (!said(d, 'name')) return { message: 'Give the persona a name.', part: 'name' }
    if (!said(d, 'behaviour')) return { message: 'Say how the persona should behave.', part: 'behaviour' }
  }
  if (door === 'instruction' && !said(d, 'text')) return { message: 'Write the instruction first.', part: 'text' }
  const fields = [...plan.first, ...plan.optional]
  if (!fields.some((f) => hasValue(plan, f, d.fields[f]))) return { message: 'Write it first.', part: plan.first[0] ?? fields[0] }
  for (const f of fields) {
    if (inputOf(plan, f) !== 'activities') continue
    const rows = activityRows(d.fields[f] ?? '')
    const blank = rows.findIndex((r) => !(r.what ?? '').trim())
    if (blank >= 0) return { message: `Activity ${blank + 1} is empty. Write it or remove it.`, part: f, index: blank }
    const keys = withKeys(rows).map((r) => r.key)
    const bad = rows.findIndex((r) => (r.key ?? '').trim() !== '' && !KEY.test(r.key.trim()))
    if (bad >= 0) return { message: `Activity ${bad + 1}'s short name can use letters, digits, _ . and -, up to 40, starting with a letter or digit.`, part: f, index: bad }
    const twice = keys.findIndex((x, i) => keys.indexOf(x) !== i)
    if (twice >= 0) return { message: `Two activities have the short name "${keys[twice]}". Each needs its own.`, part: f, index: twice }
  }
  if (mode === 'create') {
    if (plan.needsConversation && !d.conversation) return { message: 'Choose the conversation it is for.', part: 'conversation' }
    if (plan.needsBasis && !d.basis.length) return { message: `A ${plan.title} has to be based on something already held. Choose at least one.`, part: 'basis' }
    if (d.basis.length && !plan.needsBasis && !d.basisReason.trim()) return { message: 'Say how what you chose leads to this.', part: 'basisReason' }
    if (d.place && !d.place.where) return { message: d.place.to === 'persona' ? 'Choose the persona.' : 'Choose the conversation.', part: 'place' }
    if (d.place && !d.place.reason.trim()) return { message: 'Say why it belongs there.', part: 'placeReason' }
  } else if (start) {
    if (plan.needsBasis && !d.basis.length) return { message: `A ${plan.title} has to be based on something already held. Choose at least one.`, part: 'basis' }
    if (!Object.keys(changedBody(plan, start, d)).length && sameRefs(start.basis, d.basis)) return { message: 'Nothing has changed yet.', part: plan.first[0] ?? fields[0] }
  }
  return null
}

/* -- activity keys -------------------------------------------------------- */

/** What the server accepts as an activity's key. */
export const KEY = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$/

const slug = (what: string) => {
  const s = what.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32).replace(/-+$/, '')
  return s || 'activity'
}

/** Every activity with a key. ONE THAT HAS A KEY KEEPS IT, always: delegated
 *  work is labelled by it. One written here gets a key made from its words,
 *  made unique among all the keys of the workflow. */
export function withKeys(rows: ActivityRow[]): ActivityRow[] {
  const taken = new Set(rows.map((r) => (r.key ?? '').trim()).filter(Boolean))
  return rows.map((r) => {
    if ((r.key ?? '').trim()) return r
    const base = slug(r.what ?? '')
    let key = base
    for (let n = 2; taken.has(key); n++) key = `${base.slice(0, 36)}-${n}`
    taken.add(key)
    return { ...r, key }
  })
}

/** A field as the server stores it; activities are given their keys here. */
function sent(plan: Plan, f: string, raw: string): unknown {
  if (inputOf(plan, f) === 'activities') return withKeys(activityRows(raw)).map(storedRow)
  return fieldValue(raw, plan.form[f]?.input)
}

/* -- what is sent --------------------------------------------------------- */

export interface Step {
  /** what this act is, for a message when it fails */
  name: 'record' | 'evidence' | 'placement'
  /** given the id the first act returned */
  path: (id: Id | null) => string
  body: Record<string, unknown>
}

/** THE ACTS THAT RECORD A NEW RECORD, in order: the record, then (where its
 *  basis is optional) what it is based on, then its placement. The first one
 *  answers with the record's id; a later one failing leaves the record in
 *  place to retry from. NONE OF THEM ESTABLISHES, and the first says so. */
export function createSteps(plan: Plan, k: KindAuthoring, d: Draft, me: Id): Step[] {
  const door = k.authoring?.door
  const refs = d.basis.map((r) => r.ref)
  const steps: Step[] = []
  if (door === 'instruction') {
    steps.push({ name: 'record', path: () => `/api/conversations/${encodeURIComponent(d.conversation?.id ?? '')}/instructions`,
      body: { ...Object.fromEntries(k.fields.map((f) => [f, d.fields[f] ?? ''])), attributed_to: me, establish: false } })
    return steps
  }
  if (door === 'persona') {
    steps.push({ name: 'record', path: () => '/api/personas',
      body: { ...Object.fromEntries(k.fields.map((f) => [f, d.fields[f] ?? ''])), attributed_to: me, propose: true, establish: false } })
  } else {
    const body = Object.fromEntries(k.fields.map((f) => [f, sent(plan, f, d.fields[f] ?? '')]))
    steps.push({ name: 'record', path: () => '/api/entries',
      body: entryCreateBody({ k, body, me, establishes: false, falsifier: '', context: d.context?.ref ?? '', sources: refs }) })
    if (citesAfterCreate(k, refs)) steps.push({ name: 'evidence', path: (id) => `/api/entries/${id}/derive-from`,
      body: { attributed_to: me, from: refs, because: d.basisReason.trim() } })
  }
  if (d.place) steps.push({ name: 'placement', path: (id) => `/api/entries/${id}/place`,
    body: { attributed_to: me, where: d.place.where, because: d.place.reason.trim() } })
  return steps
}

/** The fields a revision changes, as the server stores them: only those. */
export function changedBody(plan: Plan, start: Draft, now: Draft): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of [...plan.first, ...plan.optional]) {
    const was = sent(plan, f, start.fields[f] ?? ''), is = sent(plan, f, now.fields[f] ?? '')
    if (JSON.stringify(was) !== JSON.stringify(is)) out[f] = is
  }
  return out
}

/** WHAT A REVISION SENDS: the `edit` act, with the changed fields, the reason
 *  where one was given, and the basis only where it was changed (left alone,
 *  the new version rests on what this one rests on). Never `revise`, which
 *  establishes. */
export function reviseRequest(plan: Plan, start: Draft, now: Draft, me: Id): Record<string, unknown> {
  return {
    attributed_to: me, body: changedBody(plan, start, now),
    ...(now.because.trim() ? { because: now.because.trim() } : {}),
    ...(sameRefs(start.basis, now.basis) ? {} : { basis: now.basis.map((r) => r.ref) }),
  }
}

/* -- what recording will do, in one line ---------------------------------- */

/** Said beside Record. For a revision it follows what the server says saving
 *  would really do to THIS record (`edit_mode`), so a proposal that is placed
 *  is not told that nothing changes. */
export function consequence(mode: 'create' | 'revise', x: { standingApt: boolean; editMode?: string | null; placed?: number }): string {
  if (mode === 'create') return x.standingApt ? 'Records a proposal. It is not in effect until you establish it.' : 'Records it. Standing does not apply to this kind.'
  if (x.editMode === 'proposed') return 'Records a proposed new version. The current one stays in effect until you establish the new one.'
  if (x.editMode === 'candidate') return 'Replaces this proposal with the new wording. It is still a proposal.'
    + (x.placed ? ' It stays placed where this one is.' : '')
  return 'Saves a new version. It replaces the current one now; the old one is kept.'
}

/* -- what changes --------------------------------------------------------- */

export interface Piece { op: 'same' | 'add' | 'cut'; text: string }

/** Word-level difference between two wordings, for "Show what changes". */
export function diffWords(a: string, b: string): Piece[] {
  const x = a.split(/(\s+)/).filter((t) => t !== ''), y = b.split(/(\s+)/).filter((t) => t !== '')
  const n = x.length, m = y.length
  // a long table is not worth freezing the page for: say it whole
  if (n * m > 400000) return [{ op: 'cut', text: a }, { op: 'add', text: b }]
  const t: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0))
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) t[i][j] = x[i] === y[j] ? t[i + 1][j + 1] + 1 : Math.max(t[i + 1][j], t[i][j + 1])
  const out: Piece[] = []
  const put = (op: Piece['op'], text: string) => { const l = out[out.length - 1]; if (l && l.op === op) l.text += text; else out.push({ op, text }) }
  let i = 0, j = 0
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) { put('same', x[i]); i++; j++ }
    else if (j < m && (i === n || t[i][j + 1] >= t[i + 1][j])) { put('add', y[j]); j++ }
    else { put('cut', x[i]); i++ }
  }
  return out
}

/** A field as words to compare: activities as numbered lines. */
function readable(plan: Plan, f: string, raw: string): string {
  if (inputOf(plan, f) !== 'activities') return raw
  return activityRows(raw).map((r, i) => {
    const who = [r.who?.role, r.disciplines?.length ? `${r.disciplines.length} discipline${r.disciplines.length === 1 ? '' : 's'}` : '', r.done_when ? `finished when ${r.done_when}` : ''].filter(Boolean).join('; ')
    return `${i + 1}. ${r.what ?? ''}${who ? ` (${who})` : ''}`
  }).join('\n')
}

/** Each changed field with its difference; empty where nothing changed. */
export function changes(plan: Plan, start: Draft, now: Draft): { field: string; name: string; pieces: Piece[] }[] {
  return Object.keys(changedBody(plan, start, now)).map((f) => ({
    field: f, name: plan.first.includes(f) ? askOf(plan, f) : nameOf(plan, f),
    pieces: diffWords(readable(plan, f, start.fields[f] ?? ''), readable(plan, f, now.fields[f] ?? '')),
  }))
}
