/* EXPERIMENTAL: WHAT A PERSON FILLS IN, AND THE RULES ITS VALUES ARE HELD TO.

   One set of fill rules for every fillable block, read by the UI (types/*.tsx
   import them) and by the server, which bundles this module into
   dist/render-check.js (through ./check.ts) and runs it in an embedded engine
   to check an answer before it is recorded. So it is PURE: no React, no DOM.
   A rule changed here is changed for both callers; there is no second copy.

   Which blocks are fillable, and their fields (design revision 3, F6):
     form       its named fields;
     checklist  one tick per item, keyed by the item's TEXT (not its position);
     table      one field per editable cell, keyed by row key and column
                (only when it declares editable= or select=);
     pad        one text field;
     timer      no fields at all: what it keeps are each person's starts and
                stops (`timer-mark`, mentis/conversation/timers.py), never an
                answer, so any value given to it is refused. It is listed
                here because its kept marks need the same thing a form does
                -- a set that finds the block again -- so it is saveable by
                the same rules (a usable, unique name=).
   Selection in a table is not a field yet: whether it is saved is an open
   owner choice (build plan C9), so `fieldsOf` lists cells only.

   SAVEABLE. What is filled in can be saved only when the block can be found
   again after the post changes: a usable name= that no other block in the
   same Turn part also says, a key= for a table, and checklist items whose
   texts differ. `saveable` says which of these is missing; `check.ts` says it
   to the agent that wrote the block. */
import { blocksOf } from '../../blocks'
import { readBlock, type RBlock } from './core'
import { SPECS } from './index'
import { isDate, isNum, type Field, type Val } from './form'
import type { Items } from './basic'
import type { TableData } from './table'
import type { TimerData } from './timer'
import { nameTable } from '../objects'

/* ------------------------------------------------------------ form values */

export interface FormState {
  /** Only values that differ from the default are held. Keyed by field id. */
  values?: Record<string, Val>
  /** The person pressed the submit button while the form was valid. */
  submitted?: boolean
}

export const valueOf = (f: Field, s: FormState | undefined): Val => (s?.values && f.id in s.values ? s.values[f.id] : f.init)
export const isEmpty = (v: Val) => (Array.isArray(v) ? v.length === 0 : typeof v === 'string' ? v.trim() === '' : !v)
export const same = (a: Val, b: Val) => JSON.stringify(a) === JSON.stringify(b)

/** Which fields are shown now. A field whose controlling field is hidden is hidden too. */
export function visibility(fields: Field[], s: FormState | undefined): Record<string, boolean> {
  const shown: Record<string, boolean> = {}
  for (const f of fields) {
    if (!f.when) { shown[f.id] = true; continue }
    const ctl = fields.find((x) => x.id === f.when!.field)
    if (!ctl || !shown[ctl.id]) { shown[f.id] = false; continue }
    const v = valueOf(ctl, s)
    const want = f.when.values
    shown[f.id] = !want.length
      ? !isEmpty(v)
      : typeof v === 'boolean'
        ? want.includes(v ? 'yes' : 'no')
        : Array.isArray(v) ? v.some((x) => want.includes(x)) : want.includes(v)
  }
  return shown
}

/** The problem with one field's current value, or null. */
export function problemOf(f: Field, v: Val): string | null {
  if (f.kind === 'checkbox') return f.required && !v ? 'Must be ticked.' : null
  if (Array.isArray(v)) {
    if (!v.length) return f.required ? 'Choose at least one.' : null
    const gone = v.filter((x) => !f.choices.includes(x))
    if (gone.length) return `No longer a choice: ${gone.join(', ')}.`
    if (f.min && v.length < +f.min) return `Choose at least ${f.min}.`
    if (f.max && v.length > +f.max) return `Choose at most ${f.max}.`
    return null
  }
  const t = String(v)
  if (t.trim() === '') return f.required ? 'Required.' : null
  switch (f.kind) {
    case 'number': {
      if (!isNum(t)) return `“${t}” is not a number.`
      const x = Number(t.trim())
      if (f.min && isNum(f.min) && x < +f.min) return `Must be at least ${f.min}${f.unit ? ' ' + f.unit : ''}.`
      if (f.max && isNum(f.max) && x > +f.max) return `Must be at most ${f.max}${f.unit ? ' ' + f.unit : ''}.`
      return null
    }
    case 'date':
      if (!isDate(t)) return `“${t}” is not a date (YYYY-MM-DD).`
      if (f.min && t < f.min) return `Must be on or after ${f.min}.`
      if (f.max && t > f.max) return `Must be on or before ${f.max}.`
      return null
    case 'select':
    case 'radio':
      return f.choices.includes(t) ? null : `“${t}” is not one of the choices.`
    default:
      if (f.min && t.length < +f.min) return `At least ${f.min} characters (now ${t.length}).`
      if (f.max && t.length > +f.max) return `At most ${f.max} characters (now ${t.length}).`
      return null
  }
}

/** Everything about the form as it stands: what is shown, and what is wrong. */
export function evaluate(fields: Field[], s: FormState | undefined) {
  const shown = visibility(fields, s)
  const problems: { field: string; label: string; msg: string }[] = []
  for (const f of fields) {
    if (!shown[f.id]) continue
    const p = problemOf(f, valueOf(f, s))
    if (p) problems.push({ field: f.id, label: f.label, msg: p })
  }
  return { shown, problems }
}

/** A value as an agent wants it: numbers as numbers, empty as null. */
export function typed(f: Field, v: Val): unknown {
  if (typeof v !== 'string') return v
  if (v.trim() === '') return null
  return f.kind === 'number' && isNum(v) ? Number(v.trim()) : v
}

/* ---------------------------------------------------------- fillable blocks */

/** One thing a person can fill in, whatever block it is in. */
export interface FillField {
  /** Stable within the block: a form field's id, a checklist item's text,
      a pad's `text`, a table cell's JSON `[row key, column]`. */
  id: string
  /** What value it takes: `checkbox` a tick, `multi` a list, all else text. */
  kind: Field['kind']
  label: string
  required: boolean
  /** The value it starts at, from the Markdown. */
  init: Val
  /** For a table cell. */
  cell?: { row: string; column: string }
  /** For a form field: the rules it is declared with, so a change to any
      of them is a change to the field (an interpretation read against the
      earlier declaration is then out of date). */
  rules?: { choices: string[]; min: string | null; max: string | null; default: string | null;
            when: { field: string; values: string[] } | null; unit: string | null }
}

/** Whether a block of `type` with these attributes takes anything filled in. */
export function isFillable(type: string, attrs: Record<string, string>): boolean {
  if (type === 'form' || type === 'checklist' || type === 'pad' || type === 'timer') return true
  if (type === 'table') return (attrs.editable ?? '').split(',').some((x) => x.trim() !== '') || (attrs.select ?? 'none') !== 'none'
  return false
}

export const cellId = (row: string, column: string) => JSON.stringify([row, column])

/** The fields of a fillable block, from what its reader returned. [] for any other block. */
export function fieldsOf(type: string, data: unknown): FillField[] {
  if (type === 'form') {
    return (data as Field[]).map((f) => ({ id: f.id, kind: f.kind, label: f.label, required: f.required, init: f.init,
      rules: { choices: f.choices, min: f.min ?? null, max: f.max ?? null, default: f.default ?? null, when: f.when ?? null, unit: f.unit ?? null } }))
  }
  if (type === 'checklist') {
    return (data as Items).map((it) => ({ id: it.text, kind: 'checkbox' as const, label: it.text, required: false, init: it.checked }))
  }
  if (type === 'pad') return [{ id: 'text', kind: 'textarea', label: 'text', required: false, init: data as string }]
  if (type === 'table') {
    const t = data as TableData
    const out: FillField[] = []
    t.rows.forEach((r, i) => {
      for (const col of t.editable) {
        const c = t.header.indexOf(col)
        if (c < 0) continue
        out.push({ id: cellId(t.ids[i], col), kind: 'text', label: `${t.ids[i]} / ${col}`, required: false, init: r[c] ?? '', cell: { row: t.ids[i], column: col } })
      }
    })
    return out
  }
  return []
}

/** Whether one block takes anything filled in, and its fields, read with the
    same block reader `checkAnswers` uses -- named or not, so the server can
    list a block it cannot save (no usable name=) and decide which tables
    take answers exactly as the table rules read `editable=` and `select=`. */
export function fillOf(b: RBlock): { fillable: boolean; readable: boolean; fields: FillField[] } {
  if (!(b.type in SPECS)) return { fillable: false, readable: false, fields: [] }
  const a = readBlock(b)
  const fillable = isFillable(b.type, a.attrs)
  return { fillable, readable: a.ok, fields: fillable && a.ok ? fieldsOf(b.type, a.data) : [] }
}

/** The checklist item texts said more than once. */
export const repeatedItems = (items: Items) => [...new Set(items.map((x) => x.text).filter((t, i, all) => all.indexOf(t) !== i))]

/** Why what is filled in this block cannot be saved; [] when it can.
    `duplicates` are the names more than one block in the Turn part says. */
export function unsaveable(type: string, attrs: Record<string, string>, name: string | null, data: unknown,
  duplicates: ReadonlySet<string>): string[] {
  const why: string[] = []
  if (!name) why.push('it has no usable name=')
  else if (duplicates.has(name)) why.push(`another block in this post also says name=${name}`)
  if (type === 'table' && attrs.key === undefined) why.push('it has no key= column')
  if (type === 'checklist' && Array.isArray(data) && repeatedItems(data as Items).length)
    why.push(`items repeat (${repeatedItems(data as Items).map((t) => `“${t}”`).join(', ')}), and ticks are saved by item text`)
  return why
}

/* -------------------------------------------------------- checking answers */

export interface FoundBlock { type: string; name: string | null; block: RBlock }

/** Every marked block in a Turn part, panels opened at any depth, in order. */
export function marked(src: string): FoundBlock[] {
  const out: FoundBlock[] = []
  const walk = (s: string) => {
    for (const b of blocksOf(s)) {
      if (b.kind !== 'code' || b.info === undefined || !b.lang) continue
      const rb: RBlock = { type: b.lang, info: b.info, body: b.text, closed: b.closed ?? true }
      if (!(b.lang in SPECS)) continue
      const a = readBlock(rb)
      out.push({ type: b.lang, name: a.shared.name, block: rb })
      if (b.lang === 'panel' && a.ok) walk(a.data as string)
    }
  }
  walk(src)
  return out
}

export interface AnswerCheck {
  /** a block of that name was found in the text */
  found: boolean
  type: string | null
  /** the block reads without errors, so it is drawn and can be filled */
  readable: boolean
  saveable: boolean
  /** why it cannot be saved (empty when it can) */
  why: string[]
  fields: FillField[]
  /** values that cannot be an answer at all: an unknown field, or a value of the wrong shape */
  refused: { field: string; msg: string }[]
  /** what the block's own rules say about the values, field by field, exactly as the UI shows them */
  problems: { field: string; label: string; msg: string }[]
  /** fields not asked now, because their condition is not met */
  not_asked: string[]
  /** required fields shown and still empty */
  missing: string[]
  /** no refusals and no problems */
  valid: boolean
  /** For a timer: its box and break, in seconds (null when not given), as
      its reader reads them, so the server times boxes by the same rules. */
  timer?: { box: number | null; break: number | null; title: string | null; about: string[] }
}

const shapeOf = (f: FillField, v: unknown): string | null => {
  if (f.kind === 'checkbox') return typeof v === 'boolean' ? null : 'expects true or false'
  if (f.kind === 'multi') return Array.isArray(v) && v.every((x) => typeof x === 'string') ? null : 'expects a list of choices'
  return typeof v === 'string' ? null : 'expects text'
}

/** The fill rules applied to `values` (field id -> value) for the block named
    `name` in the Turn part `text`. Values not given keep the block's own
    starting value. Pure; the server runs it in its embedded engine. */
export function checkAnswers(text: string, name: string, values: Record<string, unknown>): AnswerCheck {
  const src = String(text ?? '')
  const none: AnswerCheck = { found: false, type: null, readable: false, saveable: false, why: [], fields: [], refused: [], problems: [], not_asked: [], missing: [], valid: false }
  const hit = marked(src).filter((b) => b.name === name)
  if (!hit.length) return { ...none, why: [`no block in this post says name=${name}`] }
  const b = hit[0]
  const a = readBlock(b.block)
  const dups = new Set(nameTable(src).duplicates)
  if (!a.ok) return { ...none, found: true, type: b.type, why: ['the block has errors, so it is shown as source and nothing can be filled in'] }
  if (!isFillable(b.type, a.attrs)) return { ...none, found: true, type: b.type, readable: true, why: [`a ${b.type} like this takes nothing filled in`] }
  const why = unsaveable(b.type, a.attrs, a.shared.name, a.data, dups)
  const fields = fieldsOf(b.type, a.data)
  const byId = new Map(fields.map((f) => [f.id, f]))
  const refused: AnswerCheck['refused'] = []
  const given: Record<string, Val> = {}
  for (const [k, v] of Object.entries(values ?? {})) {
    const f = byId.get(k)
    if (!f) { refused.push({ field: k, msg: `this ${b.type} has no field “${k}”` }); continue }
    const bad = shapeOf(f, v)
    if (bad) { refused.push({ field: k, msg: `“${f.label}” ${bad}` }); continue }
    given[k] = v as Val
  }
  let problems: AnswerCheck['problems'] = []
  let notAsked: string[] = []
  let missing: string[] = []
  if (b.type === 'form') {
    const formFields = a.data as Field[]
    const s: FormState = { values: given }
    const ev = evaluate(formFields, s)
    problems = ev.problems
    notAsked = formFields.filter((f) => !ev.shown[f.id]).map((f) => f.id)
    missing = formFields.filter((f) => ev.shown[f.id] && f.required && isEmpty(valueOf(f, s))).map((f) => f.id)
  }
  const timer = b.type === 'timer' ? { box: (a.data as TimerData).box, break: (a.data as TimerData).brk, title: a.attrs.title ?? null, about: (a.data as TimerData).about ?? [] } : undefined
  return { found: true, type: b.type, readable: true, saveable: why.length === 0, why, fields, refused, problems, not_asked: notAsked, missing, valid: !refused.length && !problems.length, ...(timer ? { timer } : {}) }
}
