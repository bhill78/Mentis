/* EXPERIMENTAL: WHAT WILL NOT RENDER, SAID TO THE AGENT THAT WROTE IT.

   checkRendering(text) reads a Turn's Markdown exactly as the UI does -- the
   same block reader (../../blocks.ts) and the same per-type readers
   (./core.ts, ./<type>.ts) -- and lists every problem the UI would show
   under a block, with where it is and what to change. It adds only what the
   UI cannot show under a block because no block is drawn for it: a fence
   whose name is a slip for a block type (drawn as plain code), a setting
   written in the body instead of on the opening line, a fence left open, and
   a name= that another block in the same post also says (../objects.ts: the
   UI then gives that name to neither, and no note is drawn for it).

   Nothing here decides whether a post is accepted. The server bundles this
   module into dist/render-check.js at build time (ui/render-check.mjs) and
   runs that file in an embedded engine; the UI never imports it.        */
import { placedIn } from '../../blocks'
import { nearest, parseInfo, readBlock, type Diag } from './core'
import { RENDERABLE, SPECS } from './index'
import { pairsOf } from '../util'
import { nameTable } from '../objects'
import { isFillable } from './fill'

/* THE SAME BUNDLE KEYS A POST'S OBJECTS FOR THE SERVER (Fluid F1): one
   function, `objectsOfPost`, used by the server through this bundle and by
   the Fluid client directly (../postobjects.ts). */
export { extractPost, objectsOfPost } from '../postobjects'

/* AND THE FILL RULES (forms build, P1): what a fillable block's fields are and
   whether given values are acceptable, the same rules the UI's controls use.
   The server calls `checkAnswers` before it records an answer, and `fillOf`
   to list a post's fillable blocks. */
export { checkAnswers, fieldsOf, fillOf, isFillable } from './fill'

export interface Problem {
  /** 1-based position of the fenced block among the fenced blocks around it; nested blocks are "2.1". */
  block: string
  /** The fence's first word: the block type it asks for (null for a bare fence). */
  type: string | null
  /** 1-based line in the text that was checked. */
  line: number
  /** The UI's own locator for the problem (fence, version, an attribute, "line 3", "data line 2" ...). */
  where: string
  severity: 'error' | 'warning'
  message: string
  fix?: string
  /** `reader`: the UI shows this under the block, word for word. `check`: only this
      check says it, because the UI draws no block to show it under. */
  from: 'reader' | 'check'
}

export interface Report {
  /** Fenced blocks read, nested ones included. */
  blocks: number
  errors: number
  warnings: number
  problems: Problem[]
  /** The block types this renderer draws. */
  types: string[]
  /** Each timer's about= ids, by block, for the server to look up: an id the
      record does not hold is its warning to add (it cannot be known here). */
  about: { block: string; line: number; ids: string[] }[]
}

type Count = { n: number; about: Report['about'] }

const BODY_LINE = /^line (\d+)$/

/** A body line that is only settings this type takes (e.g. `direction=right`). */
function strayAttrs(line: string, type: string): string | null {
  const t = line.trim()
  if (!/^[A-Za-z][A-Za-z0-9_-]*=/.test(t)) return null
  const { pairs, flags, residue } = pairsOf(t)
  const keys = Object.keys(pairs)
  if (residue || flags.length || !keys.length) return null
  return keys.every((k) => k === 'version' || k in SPECS[type].attrs) ? t : null
}

/** `dups`: the names more than one block declares in this Turn part, counted
 *  through panels as the UI counts them (../objects.ts, `nameTable`). */
function read(text: string, base: number, prefix: string, out: Problem[], count: Count, dups: ReadonlySet<string>) {
  const placed = placedIn(text)
  let n = 0
  placed.forEach((p, i) => {
    const b = p.block
    if (b.kind !== 'code' || !p.fence) return
    n += 1
    count.n += 1
    const id = prefix + n
    const at = base + p.line + 1
    const lang = b.lang
    const put = (x: Diag, line = at, from: Problem['from'] = 'check') => out.push({
      block: id, type: lang, line, where: x.where, severity: x.sev, message: x.msg, ...(x.fix ? { fix: x.fix } : {}), from,
    })

    if (lang === null || !RENDERABLE.has(lang)) {
      const near = lang ? nearest(lang, RENDERABLE) : null
      if (lang && near)
        put({ sev: 'error', where: 'fence', msg: `“${lang}” is not a block type, so this block is shown as plain code.`,
          fix: `Did you mean ${near}? Open the block with \`\`\`${near} version=1 …` })
      else if (lang && /(^|\s)version=/.test(p.fence.info))
        put({ sev: 'warning', where: 'fence', msg: `“${lang}” is not a block type Mentis draws, so this block is shown as plain code.`,
          fix: `Use one of: ${[...RENDERABLE].join(', ')}; or drop version= if this is meant to be code.` })
      if (!p.fence.closed) {
        const prev = placed[i - 1]
        const after = prev?.block.kind === 'code' && prev.block.lang && SPECS[prev.block.lang]?.nests ? prev.block.lang : null
        put({ sev: after ? 'error' : 'warning', where: 'fence', msg: 'This fence is never closed, so everything below it is shown as code.',
          fix: after
            ? `This bare fence is probably the ${after}'s own closing line: an inner block's closing ${p.fence.run} closed the ${after} early. Open and close the ${after} with a longer fence (e.g. ${'`'.repeat(p.fence.run.length + 1)}${after} version=1).`
            : `End the block with a line holding only ${p.fence.run}.` })
      }
      return
    }

    const r = readBlock({ type: lang, info: b.info ?? p.fence.info, body: b.text, closed: b.closed ?? true })
    if (lang === 'timer' && r.ok) {
      const ids = (r.data as { about?: string[] } | null)?.about ?? []
      if (ids.length) count.about.push({ block: id, line: at, ids })
    }
    const bodyLines = b.text.split('\n')
    const stray = new Map<number, string>()
    bodyLines.forEach((l, k) => { const s = strayAttrs(l, lang); if (s) stray.set(k + 1, s) })
    const moveFix = (s: string) => `Settings go on the opening fence line, not in the body. Move ${s} there: \`\`\`${lang} ${b.info?.split(/\s+/).slice(1).join(' ') || 'version=1'} ${s}`
    /* A timer says for itself that, unnamed, it keeps nothing (./timer.ts):
       it has no fields, so the notes below about "what is filled in" would
       say it a second time, in words that do not fit it. */
    const fillable = r.ok && isFillable(lang, r.attrs) && lang !== 'timer'
    const unsaved = fillable ? ` What is filled in this ${lang} will not be saved.` : ''
    for (const x of r.d) {
      const m = BODY_LINE.exec(x.where)
      const k = m ? Number(m[1]) : null
      const s = k !== null ? stray.get(k) : undefined
      if (s !== undefined) stray.delete(k!)
      put(s !== undefined ? { ...x, fix: moveFix(s) } : x, k !== null && k >= 1 && k <= bodyLines.length ? at + k : at, 'reader')
    }
    for (const [k, s] of stray)
      put({ sev: 'warning', where: `line ${k}`, msg: `“${s}” is in the body, where it is read as content, not as a setting.`, fix: moveFix(s) }, at + k)
    if (r.shared.name && dups.has(r.shared.name))
      put({ sev: 'warning', where: 'name', msg: `name=${r.shared.name} is also said by another block in this post, so neither block gets the name: each keeps its position as its identity.${unsaved}`,
        fix: `Give each block its own name=, or remove name=${r.shared.name} from all but one.` })
    /* A fillable block with no usable name cannot be found again once the post
       changes, so its answers are not saved (fill.ts). A bad name= already has
       the reader's own note; this one is for a name never given. */
    if (fillable && !r.shared.name && !r.d.some((x) => x.where === 'name'))
      put({ sev: 'warning', where: 'name', msg: `This ${lang} has no name=, so what is filled in it will not be saved: it stays in the reader's browser tab only.`,
        fix: `Add name=<a short lowercase name, unique in this post> to the opening line, e.g. \`\`\`${lang} version=1 name=${lang}-1` })
    /* A name= the reader ignored (its own note says why, core.ts) leaves a
       fillable block as unnamed as one never given: said beside that note. */
    if (fillable && !r.shared.name && r.d.some((x) => x.where === 'name'))
      put({ sev: 'warning', where: 'name', msg: `Because name=“${parseInfo(b.info ?? p.fence.info).attrs.find(([k]) => k === 'name')?.[1] ?? ''}” is ignored, what is filled in this ${lang} will not be saved: it stays in the reader's browser tab only.`,
        fix: `Use a name that starts with a lowercase letter, then up to 39 lowercase letters, digits or hyphens, unique in this post, e.g. \`\`\`${lang} version=1 name=${lang}-1` })

    // An invalid container is shown as its source, so its children are not drawn as blocks.
    if (SPECS[lang].nests && r.ok) {
      const inner: Problem[] = []
      /* Names are counted through panels; any other container's text is
         drawn as Markdown of its own, with a name table of its own, so no
         name inside it collides with one outside (or in a sibling part). */
      read(b.text, at, id + '.', inner, count, lang === 'panel' ? dups : new Set())
      for (const q of inner) {
        if (q.where === 'fence' && q.message.startsWith('This block is never closed') && q.type && /^`+$/.test(p.fence.run)
          && b.text.split('\n').some((l) => new RegExp(`^ {0,3}${p.fence!.run}\\S`).test(l)))
          q.fix = `This ${q.type} uses the same ${p.fence.run} fence as the ${lang} around it, so its closing line closed the ${lang} instead. Open and close the ${lang} with ${'`'.repeat(p.fence.run.length + 1)}.`
        out.push(q)
      }
    }
  })
}

export function checkRendering(text: string): Report {
  const problems: Problem[] = []
  const count: Count = { n: 0, about: [] }
  const src = String(text ?? '')
  read(src, 0, '', problems, count, new Set(nameTable(src).duplicates))
  return {
    blocks: count.n,
    errors: problems.filter((p) => p.severity === 'error').length,
    warnings: problems.filter((p) => p.severity === 'warning').length,
    problems,
    types: [...RENDERABLE],
    about: count.about,
  }
}
