/* EXPERIMENTAL: the generic half of reading a marked block -- the fence line,
   version, unknown and required attributes, enumerations -- and then the
   type's own body reader. Moved here unchanged from ../renderable.tsx, which
   adds the drawing (`def`) to what this returns. The `fix` on each problem is
   new and is read only by ./check.ts; the UI shows `msg`, as before. */
import type { Shared, Size, TypeSpec } from './api'
import { SPECS } from './index'

export interface RBlock {
  type: string
  info: string
  body: string
  closed: boolean
}

export const sourceOf = (b: RBlock) => {
  const runs = [...b.body.matchAll(/^ {0,3}(`{3,})/gm)].map((m) => m[1].length)
  const fence = '`'.repeat(Math.max(3, ...runs.map((n) => n + 1)))
  return fence + b.info + '\n' + b.body + (b.closed ? '\n' + fence : '')
}

export function parseInfo(info: string) {
  const word = info.trim().split(/\s+/)[0]
  let rest = info.trim().slice(word.length)
  const attrs: [string, string][] = []
  const re = /^\s*([A-Za-z][A-Za-z0-9_-]*)=(?:"((?:[^"\\]|\\.)*)"|([^\s"]+))(?=\s|$)/
  while (rest.trim()) {
    const m = re.exec(rest)
    if (!m) return { attrs, residue: rest.trim() }
    attrs.push([m[1], m[2] !== undefined ? m[2].replace(/\\(.)/g, '$1') : m[3]])
    rest = rest.slice(m[0].length)
  }
  return { attrs, residue: '' }
}

/** Edit distance, for "did you mean" (small strings only). */
export function distance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, j) => j)
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0]
    row[0] = i
    for (let j = 1; j <= b.length; j++) {
      const was = row[j]
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1))
      prev = was
    }
  }
  return row[b.length]
}

/** The closest of `names` to `word`, if it is plausibly a slip for it. */
export function nearest(word: string, names: Iterable<string>): string | null {
  let best: string | null = null, d = Infinity
  for (const n of names) {
    const k = n.toLowerCase() === word.toLowerCase() ? 0 : distance(word.toLowerCase(), n.toLowerCase())
    if (k < d) { best = n; d = k }
  }
  return best !== null && d <= Math.max(1, Math.min(2, Math.floor(word.length / 3))) ? best : null
}

/** `fix` is for an author who will revise the Markdown; the UI shows `msg`. */
export interface Diag { sev: 'error' | 'warning'; where: string; msg: string; fix?: string }
export interface Reading {
  spec: TypeSpec
  attrs: Record<string, string>
  extra: Record<string, string>
  /** The shared attributes, read and checked, defaults applied. */
  shared: Shared
  data: unknown
  d: Diag[]
  ok: boolean
}

/* ---- the shared attributes: one contract, every type, every renderer. ----
   Five optional attributes any marked block may carry, read here so that the
   conversation, the Workspace Lab and the server-side checker read them the
   same way. They say what a block IS (a stable name, whether it starts
   open, what sizes it can be shown at, which working page it belongs on),
   never where it goes. A bad value is a note and the default applies:
   a declaration can never hide content. How a renderer USES them is its own
   affair -- the conversation ignores `open` and sizes; the Lab collapses and
   composes. Pure: nothing here draws, fetches or touches the page. */
export const SIZES: readonly Size[] = ['compact', 'medium', 'large']
export const SHARED: ReadonlySet<string> = new Set(['name', 'open', 'sizes', 'prefer', 'page'])
export const NAME = /^[a-z][a-z0-9-]{0,39}$/

const preferIn = (sizes: Size[]): Size => (sizes.includes('medium') ? 'medium' : sizes[sizes.length - 1])

/** A misspelling of a shared attribute, and what to write instead. */
const HINT: Record<string, string> = {
  collapsed: 'To start it collapsed, write open=false.',
  size: 'To say what it can be shown at, write sizes= (compact, medium, large) and prefer=.',
  id: 'To give it a stable name, write name=.',
}

export function readShared(type: string, given: Record<string, string>, label: string | null, labelFrom: Shared['labelFrom'],
  warn: (where: string, msg: string) => void): Shared {
  const s: Shared = { name: null, open: true, sizes: [...SIZES], prefer: 'medium', page: null, label, labelFrom }
  if ('name' in given) {
    if (NAME.test(given.name)) s.name = given.name
    else warn('name', `name=“${given.name}” is not a usable name: start with a lowercase letter, then up to 39 lowercase letters, digits or hyphens. It is ignored, so this ${type} keeps its position as its identity.`)
  }
  if ('sizes' in given) {
    const got = given.sizes.split(',').map((x) => x.trim())
    const bad = got.filter((x) => !(SIZES as string[]).includes(x))
    if (bad.length || !got.length) warn('sizes', `sizes must list compact, medium or large, separated by commas — not “${given.sizes}”. It is ignored, so every size is allowed.`)
    else s.sizes = SIZES.filter((x) => got.includes(x))
  }
  s.prefer = preferIn(s.sizes)
  if ('prefer' in given) {
    if (!(SIZES as string[]).includes(given.prefer)) warn('prefer', `prefer must be compact, medium or large — not “${given.prefer}”. It is ignored.`)
    else if (!s.sizes.includes(given.prefer as Size)) warn('prefer', `prefer=${given.prefer} is not one of its sizes (${s.sizes.join(', ')}). It is ignored.`)
    else s.prefer = given.prefer as Size
  }
  if ('open' in given) {
    if (given.open !== 'true' && given.open !== 'false') warn('open', `open must be true or false — not “${given.open}”. It is ignored, so this ${type} starts open.`)
    else if (given.open === 'false' && !label) warn('open', `open=false needs a label to collapse to: a title, or (for a panel) a heading as its first line. It is ignored, so this ${type} starts open.`)
    else s.open = given.open === 'true'
  }
  if ('page' in given) {
    const p = given.page.trim()
    if (!p || p.length > 60) warn('page', `page must be a short label (1 to 60 characters) — not “${given.page}”. It is ignored.`)
    else s.page = p
  }
  return s
}

/** Validation in plain language. The generic part is the core's; the body is the type's. */
export function readBlock(b: RBlock): Reading {
  const def = SPECS[b.type]
  const d: Diag[] = []
  const say = (sev: Diag['sev']) => (where: string, msg: string, fix?: string) => { d.push(fix ? { sev, where, msg, fix } : { sev, where, msg }) }
  const err = say('error'), warn = say('warning')
  const { attrs: pairs, residue } = parseInfo(b.info)
  const attrs: Record<string, string> = {}, extra: Record<string, string> = {}, given: Record<string, string> = {}
  let shared = readShared(b.type, {}, null, null, warn)
  const done = (data: unknown = null) => ({ spec: def, attrs, extra, shared, data, d, ok: !d.some((x) => x.sev === 'error') })
  const takes = `${b.type} takes: ${['version', ...Object.keys(def.attrs)].join(', ')}.`
  if (!b.closed) err('fence', 'This block is never closed (no closing ``` line), so it swallows everything below it.',
    'End the block with a line holding only the backticks that opened it (e.g. ```).')
  if (residue) err('attributes', `I can't read the attributes starting at “${residue}”. Write key=value, or key="text with spaces".`,
    'On the opening line, write each setting as key=value, or key="text with spaces", separated by spaces.')
  const seen = new Set<string>()
  for (const [k, v] of pairs) {
    if (seen.has(k)) { err(k, `“${k}” is given twice.`, `Keep one ${k}=… on the opening line.`); continue }
    seen.add(k)
    ;(k === 'version' || k in def.attrs ? attrs : SHARED.has(k) ? given : extra)[k] = v
  }
  const ver = attrs.version
  if (ver === undefined) { err('version', 'version is missing. Add version=1.', `Add version=1 to the opening line: \`\`\`${b.type} version=1 …`); return done() }
  if (ver !== '1') {
    err('version', `Only ${b.type} version 1 is known, but the block says version=${ver}. It is shown as source only.`, 'Write version=1.')
    return done()
  }
  delete attrs.version
  for (const k of Object.keys(extra)) {
    const near = nearest(k, [...Object.keys(def.attrs), ...SHARED])
    warn(k, `${b.type} has no attribute “${k}”. ${HINT[k] ? HINT[k] + ' ' : ''}It is kept, shown here, and ignored.`,
      HINT[k] ? `${HINT[k]} ${takes}` : near ? `Did you mean ${near}=? ${takes}` : `Remove ${k}=… ${takes}`)
  }
  const heading = attrs.title ? null : def.heading?.(b.body) ?? null
  shared = readShared(b.type, given, attrs.title ?? heading, attrs.title ? 'title' : heading ? 'heading' : null, warn)
  for (const [k, spec] of Object.entries(def.attrs)) {
    if (spec.req === 'required' && !(k in attrs)) err(k, `${k} is required for a ${b.type} (${spec.says}).`, `Add ${k}=… to the opening line.`)
    if (spec.choices && k in attrs && !spec.choices.includes(attrs[k]))
      err(k, `${k} must be one of: ${spec.choices.join(', ')} — not “${attrs[k]}”.`, `Change ${k}= to one of: ${spec.choices.join(', ')}.`)
  }
  if (d.some((x) => x.sev === 'error')) return done()
  let data: unknown = null
  try {
    data = def.parse(b.body, attrs, { err, warn, shared })
  } catch (e) {
    err('renderer', `The ${b.type} reader failed on this block (${(e as Error).message}). This is a fault in the experiment, not in your Markdown.`)
  }
  return done(data)
}
