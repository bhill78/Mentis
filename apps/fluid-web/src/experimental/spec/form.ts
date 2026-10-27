/* EXPERIMENTAL: the reading half of form (drawn in ../types/form.tsx). */
import type { Ctx, TypeSpec } from './api'
import { quoted } from '../util'

export const KINDS = ['text', 'textarea', 'number', 'date', 'select', 'radio', 'multi', 'checkbox'] as const

export type Kind = (typeof KINDS)[number]

export const CHOICE_KINDS: Kind[] = ['select', 'radio', 'multi']

/* What min/max mean per kind; kinds not listed may not have them. */
export const RANGE: Partial<Record<Kind, string>> = {
  number: 'the smallest/largest number',
  date: 'the earliest/latest date (YYYY-MM-DD)',
  text: 'the fewest/most characters',
  textarea: 'the fewest/most characters',
  multi: 'the fewest/most choices ticked',
}

export const KEYS = ['choices', 'min', 'max', 'default', 'when', 'hint', 'unit']

export const FLAGS = ['required']

export interface Field {
  id: string
  kind: Kind
  label: string
  required: boolean
  choices: string[]
  min?: string
  max?: string
  /** The default exactly as written (for the readable form). */
  default?: string
  /** The starting value the default gives. */
  init: Val
  when?: { field: string; values: string[] }
  hint?: string
  unit?: string
  /** The `## heading` the field sits under, if any. */
  section?: string
}

/** A current value: text for most kinds, a tick for checkbox, a list for multi. */
export type Val = string | boolean | string[]

/** One `key=value` value: comma-separated items, each bare or "quoted", and
    pieces may run together (`contact="text message"` is one item). */
export function readValue(s: string): { items: string[]; rest: string } | null {
  const items: string[] = []
  let i = 0
  for (;;) {
    let item = ''
    while (i < s.length && !/[\s,]/.test(s[i])) {
      if (s[i] === '"') {
        const m = /^"((?:[^"\\]|\\.)*)"/.exec(s.slice(i))
        if (!m) return null
        item += m[1].replace(/\\(.)/g, '$1')
        i += m[0].length
      } else item += s[i++]
    }
    items.push(item)
    if (s[i] === ',') { i++; continue }
    return { items, rest: s.slice(i) }
  }
}

/** The words after the label: flags (`required`) and `key=value` pairs. */
export function wordsOf(s: string) {
  const flags: string[] = []
  const pairs: Record<string, string[]> = {}
  const repeated: string[] = []
  let rest = s
  while (rest.trim()) {
    const m = /^\s*([A-Za-z][A-Za-z0-9_-]*)(=?)/.exec(rest)
    if (!m) return { flags, pairs, repeated, residue: rest.trim() }
    rest = rest.slice(m[0].length)
    if (!m[2]) {
      if (rest && !/^\s/.test(rest)) return { flags, pairs, repeated, residue: (m[1] + rest).trim() }
      flags.push(m[1])
      continue
    }
    const v = readValue(rest)
    if (!v || (v.rest && !/^\s/.test(v.rest))) return { flags, pairs, repeated, residue: `${m[1]}=${rest}`.trim() }
    if (m[1] in pairs) repeated.push(m[1])
    pairs[m[1]] = v.items
    rest = v.rest
  }
  return { flags, pairs, repeated, residue: '' }
}

export const isDate = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s + 'T00:00:00Z'))

export const isNum = (s: string) => s.trim() !== '' && Number.isFinite(Number(s.trim()))

export const isCount = (s: string) => /^\d+$/.test(s)

export function parseForm(body: string, c: Ctx): Field[] {
  const fields: Field[] = []
  let section: string | undefined
  body.split('\n').forEach((raw, n) => {
    const line = raw.trim()
    const at = `line ${n + 1}`
    if (!line) return
    const h = /^#{1,6}\s+(.*\S)$/.exec(line)
    if (h) { section = h[1]; return }
    const m = /^([A-Za-z][A-Za-z0-9_-]*)\s*:\s*([A-Za-z]+)(.*)$/.exec(line)
    if (!m) {
      c.err(at, `“${line}” is not a field. Fields look like: name: text "Your name" required`)
      return
    }
    const [, id, kindWord, after] = m
    const kind = kindWord.toLowerCase() as Kind
    if (!KINDS.includes(kind)) {
      c.err(at, `“${kindWord}” is not a field kind. Use one of: ${KINDS.join(', ')}.`)
      return
    }
    if (fields.some((f) => f.id === id)) c.err(at, `The field id “${id}” is already used above. Each field needs its own id.`)
    let label = id
    let rest = after
    const lq = quoted(after)
    if (lq) [label, rest] = lq
    else c.warn(at, `Field “${id}” has no label in double quotes after “${kindWord}”, so its id is shown as the label.`)
    const w = wordsOf(rest)
    if (w.residue) c.err(at, `I can't read “${w.residue}”. Write words like required, key=value, or key="text with spaces".`)
    for (const k of w.repeated) c.err(at, `“${k}=” is given twice on this line.`)
    for (const f of w.flags) if (!FLAGS.includes(f)) c.warn(at, `“${f}” is not a known word here (the only one is: required). It is ignored.`)
    for (const k of Object.keys(w.pairs))
      if (!KEYS.includes(k)) c.warn(at, `“${k}=” is not a known setting (known: ${KEYS.join(', ')}). It is ignored.`)
    const one = (k: string) => (w.pairs[k] ? w.pairs[k].join(',') : undefined)
    const f: Field = {
      id, kind, label,
      required: w.flags.includes('required'),
      choices: (w.pairs.choices ?? []).filter((x) => x !== ''),
      min: one('min'), max: one('max'), default: one('default'), hint: one('hint'), unit: one('unit'),
      init: kind === 'checkbox' ? false : kind === 'multi' ? [] : '',
      section,
    }
    const who = `field “${id}” (${at})`

    // choices
    if (CHOICE_KINDS.includes(kind)) {
      if (!f.choices.length) c.err(who, `A ${kind} needs choices, e.g. choices=small,medium,"extra large".`)
      const dup = f.choices.filter((x, i) => f.choices.indexOf(x) !== i)
      if (dup.length) c.warn(who, `These choices repeat: ${[...new Set(dup)].join(', ')}.`)
    } else if (w.pairs.choices) c.err(who, `choices= only belongs on select, radio or multi, not on ${kind}.`)

    // range
    if (f.min !== undefined || f.max !== undefined) {
      const meaning = RANGE[kind]
      if (!meaning) c.err(who, `min= and max= don't apply to ${kind}. They apply to: ${Object.keys(RANGE).join(', ')}.`)
      else {
        const ok = kind === 'number' ? isNum : kind === 'date' ? isDate : isCount
        const want = kind === 'number' ? 'a number' : kind === 'date' ? 'a date written YYYY-MM-DD' : 'a whole number'
        let good = true
        for (const k of ['min', 'max'] as const) {
          const v = f[k]
          if (v !== undefined && !ok(v)) { c.err(who, `${k}=${v} should be ${want} (for a ${kind} it is ${meaning}).`); good = false }
        }
        if (good && f.min !== undefined && f.max !== undefined) {
          const lo = kind === 'date' ? f.min : Number(f.min), hi = kind === 'date' ? f.max : Number(f.max)
          if (lo > hi) c.err(who, `min=${f.min} is greater than max=${f.max}, so nothing could ever be valid.`)
        }
      }
    }
    if (f.unit !== undefined && kind !== 'number') c.warn(who, `unit= is only shown for number fields; this is a ${kind}.`)

    // default
    const d = f.default
    if (d !== undefined) {
      if (kind === 'checkbox') {
        if (d !== 'yes' && d !== 'no') c.err(who, `A checkbox default is yes or no, not “${d}”.`)
        f.init = d === 'yes'
      } else if (kind === 'multi') {
        f.init = (w.pairs.default ?? []).filter((x) => x !== '')
        for (const x of f.init) if (!f.choices.includes(x)) c.err(who, `default “${x}” is not one of the choices (${f.choices.join(', ')}).`)
      } else {
        f.init = d
        if ((kind === 'select' || kind === 'radio') && !f.choices.includes(d))
          c.err(who, `default “${d}” is not one of the choices (${f.choices.join(', ')}).`)
        if (kind === 'number' && !isNum(d)) c.err(who, `default “${d}” is not a number.`)
        if (kind === 'date' && !isDate(d)) c.err(who, `default “${d}” is not a date written YYYY-MM-DD.`)
        if (kind === 'number' && isNum(d) && ((f.min && isNum(f.min) && +d < +f.min) || (f.max && isNum(f.max) && +d > +f.max)))
          c.err(who, `default ${d} is outside min/max (${f.min ?? '…'} to ${f.max ?? '…'}).`)
      }
    }

    // when: must name a field ABOVE this one (so conditions read top to bottom and can't loop)
    const wv = w.pairs.when
    if (wv) {
      const [first, ...more] = wv
      const eq = first.indexOf('=')
      const on = eq < 0 ? first : first.slice(0, eq)
      const values = eq < 0 ? [] : [first.slice(eq + 1), ...more]
      const ctl = fields.find((x) => x.id === on)
      f.when = { field: on, values }
      if (on === id) c.err(who, 'when= names this same field; a field cannot depend on itself.')
      else if (!ctl) {
        const later = body.split('\n').slice(n + 1).some((l) => new RegExp(`^\\s*${on}\\s*:`).test(l))
        c.err(who, later
          ? `when=${on} names a field that comes later. when= must name a field above this one.`
          : `when=${on} names no field. The fields above are: ${fields.map((x) => x.id).join(', ') || '(none)'}.`)
      } else if (values.length) {
        if (ctl.kind === 'checkbox') {
          for (const v of values) if (v !== 'yes' && v !== 'no') c.err(who, `“${on}” is a checkbox, so when=${on}=… must be yes or no (or just when=${on} for ticked).`)
        } else if (CHOICE_KINDS.includes(ctl.kind)) {
          for (const v of values) if (!ctl.choices.includes(v)) c.err(who, `when=${on}=${v}: “${v}” is not one of ${on}'s choices (${ctl.choices.join(', ')}).`)
        }
      }
    }
    fields.push(f)
  })
  if (!fields.length) c.err('body', 'A form needs at least one field, e.g.  name: text "Your name" required')
  return fields
}

export const formSpec: TypeSpec<Field[]> = {
  type: 'form',
  summary: 'Fields a person fills in. Values are state, checked mechanically; the Markdown keeps the fields and their defaults.',
  attrs: {
    title: { req: 'optional', says: 'a heading' },
    submit: { req: 'optional', says: 'the words on the submit button, e.g. "Request leave"' },
  },
  body:
    'one field per line: `id: kind "Label"` then any of: required, choices=a,b,"c d", min=N, max=N, default=…, when=otherid or when=otherid=value, hint="…", unit=…; `## Heading` lines group fields. Kinds: ' +
    KINDS.join(', '),
  parse: (body, _a, c) => parseForm(body, c),
}
