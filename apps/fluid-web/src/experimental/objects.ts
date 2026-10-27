import { blocksAt, blocksOf, placedRef, type Block, type PlacedBlock } from '../blocks'
import { readBlock, SIZES, type RBlock } from './spec/core'
import type { Size } from './spec/api'

/* ------------------------------------------------------------------------ *
 * EXPERIMENTAL: WHAT A POST HOLDS, AS OBJECTS (Fluid Workspace, L1).
 *
 * One reading of one Turn part, shared by everything that needs to know what
 * is in it: the conversation (to key a named block's state), the Workspace
 * Lab (to compose a post's sections onto a page), and the server-side
 * checker that bundles the UI's own parsers. So it is PURE: it reads Markdown
 * with the same `blocksOf` (../blocks.ts) and `readBlock` (./spec/core.ts)
 * the renderer draws with, and draws, fetches and touches nothing.
 *
 * NAMES. A block may say `name=…`. A name is an identity only when it is
 * unambiguous in its Turn part, nested panels included: if two blocks say the
 * same name, NEITHER gets it, and both keep their positional keys. State held
 * under the name then attaches to nothing rather than moving to whichever
 * block was inserted (cross-review X-1).
 *
 * KEYS. A named block is `<scope>/@<name>:<type>`, where scope is the Turn
 * part (`turnPartScope`), however deeply it is nested. An unnamed block keeps
 * exactly the key it always had: `<parent>/<type>#<n>`, counted among the
 * marked blocks of its own body. A placed figure is
 * `<scope>/fig:<adm-…>#<occurrence>`, counted over the whole Turn part.
 * ------------------------------------------------------------------------ */

/** The scope a posted block is keyed under: the Turn it was WRITTEN in and
 *  the index of its text part (../renderable.tsx says why). Defined here, in
 *  the pure half, so the server's bundle and every client key alike. */
export const turnPartScope = (turn: string, part: number) => `Turn ${turn}` + (part ? ` part ${part}` : '')

export interface NameTable {
  /** every usable name, and how many blocks in the Turn part declare it */
  counts: Map<string, number>
  /** the names declared more than once: none of their blocks gets the name */
  duplicates: string[]
}

/** A name table and the scope its named keys hang from (the Turn part). */
export interface Names { root: string; table: NameTable }

type Marked = Extract<Block, { kind: 'code' }> & { info: string; lang: string }
const isMarked = (b: Block): b is Marked => b.kind === 'code' && b.info !== undefined && !!b.lang
const rblock = (b: Marked): RBlock => ({ type: b.lang, info: b.info, body: b.text, closed: b.closed ?? true })

/* A post is read every time it is drawn; the same words give the same table. */
const kept = new Map<string, NameTable>()

/** Every name declared in `src`, counted through panels at any depth. */
export function nameTable(src: string): NameTable {
  const hit = kept.get(src)
  if (hit) return hit
  const counts = new Map<string, number>()
  const walk = (s: string) => {
    for (const b of blocksOf(s)) {
      if (!isMarked(b)) continue
      const a = readBlock(rblock(b))
      if (a.shared.name) counts.set(a.shared.name, (counts.get(a.shared.name) ?? 0) + 1)
      if (b.lang === 'panel' && a.ok) walk(a.data as string)
    }
  }
  walk(src)
  const table = { counts, duplicates: [...counts].filter(([, n]) => n > 1).map(([k]) => k) }
  if (kept.size > 400) kept.delete(kept.keys().next().value as string)
  kept.set(src, table)
  return table
}

export const namesFor = (src: string, scope: string): Names => ({ root: scope, table: nameTable(src) })

/** The key a marked block's state is held under: its name when the name is
 *  unambiguous in its Turn part, its position otherwise. */
export function keyOf(parent: string, type: string, n: number, name: string | null, names?: Names): string {
  return name && names && names.table.counts.get(name) === 1 ? `${names.root}/@${name}:${type}` : `${parent}/${type}#${n}`
}

export interface ObjectDescriptor {
  key: string
  /** the name the key uses; null when unnamed or ambiguous */
  name: string | null
  /** a name declared but shared with another block, so not used */
  duplicate?: string
  /** the enclosing block's key; null at the top of the post */
  parent: string | null
  kind: 'block' | 'figure' | 'post-text'
  /** the block type; `figure` for a placed figure, `text` for post text */
  type: string
  label: string | null
  sizes: Size[]
  prefer: Size
  /** own `page`, else the parent's; null for the Post page */
  page: string | null
  open: boolean
  /** first line in the Turn part's text, counted from 1 */
  line: number
  /** last line in the Turn part's text, counted from 1 (the block's closing fence) */
  end: number
  /** a block's own Markdown */
  block?: RBlock
  /** a figure's Admission */
  ref?: string
  /** post text's own words */
  text?: string
}

/** Every object in one Turn part, in reading order, parents before their
 *  children. Media (attachments, returned files) are not in the text and
 *  are not here: they come from `mediaOf`. */
export function objectsIn(src: string, scope: string, names: Names = namesFor(src, scope)): ObjectDescriptor[] {
  const out: ObjectDescriptor[] = []
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const figs: Record<string, number> = {}
  let texts = 0
  const walk = (s: string, at: string, parent: string | null, page: string | null, base: number) => {
    const top = parent === null
    const seen: Record<string, number> = {}
    let run: PlacedBlock[] = []
    /* Unmarked text between two objects at the top of the post is one object
       of its own, so nothing the author wrote is left out of a composition. */
    const endRun = () => {
      if (!run.length) return
      const first = run[0].line
      const last = run[run.length - 1].end
      const words = lines.slice(first, last).join('\n').trim()
      run = []
      if (words)
        out.push({ key: `${scope}/text#${texts++}`, name: null, parent: null, kind: 'post-text', type: 'text', label: null,
          sizes: [...SIZES], prefer: 'large', page: null, open: true, line: first + 1, end: last, text: words })
    }
    for (const b of blocksAt(s)) {
      const line = base + b.line
      if (isMarked(b)) {
        endRun()
        const n = (seen[b.lang] = (seen[b.lang] ?? -1) + 1)
        const block = rblock(b)
        const a = readBlock(block)
        const declared = a.shared.name
        const key = keyOf(at, b.lang, n, declared, names)
        const named = !!declared && names.table.counts.get(declared) === 1
        const own = a.shared.page ?? page
        out.push({
          key, name: named ? declared : null, ...(declared && !named ? { duplicate: declared } : {}), parent, kind: 'block',
          type: b.lang, label: a.shared.label, sizes: a.shared.sizes, prefer: a.shared.prefer, page: own, open: a.shared.open,
          line: line + 1, end: base + b.end, block,
        })
        if (b.lang === 'panel' && a.ok) walk(a.data as string, key, key, own, line + 1)
        continue
      }
      const fig = b.kind === 'para' ? placedRef(b.text) : null
      if (fig) {
        endRun()
        const occ = (figs[fig.id] = (figs[fig.id] ?? -1) + 1)
        out.push({
          key: `${scope}/fig:${fig.id}#${occ}`, name: null, parent, kind: 'figure', type: 'figure', label: fig.label ?? null,
          sizes: [...SIZES], prefer: 'medium', page, open: true, line: line + 1, end: base + b.end, ref: fig.id,
        })
        continue
      }
      if (top) run.push(b)
    }
    endRun()
  }
  walk(src, scope, null, null, 0)
  return out
}
