/* FOCUS SEARCH OVER WHAT IS SHOWN (search-in/, the approved assignment's 2).
 *
 * A reading aid laid over one section's current content. It never changes
 * the stored content, the Brain record or the section's source: the only
 * marks are attributes it puts on what is drawn (`data-fs-on`, `data-fs-hit`,
 * `data-fs-near`, `data-fs-obj`), each one removed by `clear()`, and paint
 * through the CSS Custom Highlight API, which rewrites no DOM at all --
 * Markdown formatting, links, controls, annotations and forms stay exactly
 * as they were. Where that API is missing, the matching block element is
 * outlined instead of the match itself.
 *
 * WHAT COUNTS AS TEXT. The visible text nodes, walked so a match spanning
 * inline elements (a bold word inside a sentence) is still found: the index
 * is one flat string and each match becomes one Range across the nodes it
 * covers. Scripts, styles, form fields, hidden and `[data-search-skip]`
 * subtrees are not text. A non-text object counts by the text its source
 * carries -- `[data-search-text]`, `img[alt]`, `figcaption`, `svg` titles,
 * descriptions and aria-labels on figures and charts -- never OCR, never
 * invented text; such a match outlines the object it belongs to. TEXT WINS
 * OVER ITS ELEMENT (claimObjects): a card's own words are always read, but
 * the card counts as a match only where no text -- and no object -- inside
 * it matched, so a section's cards never hide the matches in them and
 * nothing is found twice.
 *
 * EMPHASIS. While a search is on, `data-fs-on` on the root lets the CSS dim
 * every block that is neither a hit nor near the current one; the current
 * match's block and its neighbours stay at full strength (planBlocks, pure
 * and tested in Node).
 *
 * SEVERAL SECTIONS MAY SEARCH AT ONCE: the Highlight API keys ranges by one
 * name for the stylesheet, so all instances register theirs here and the two
 * named highlights ('fs-match', 'fs-current', the current painted over) are
 * their union; clearing one instance withdraws only its own. */

import { findIn, MAX_MATCHES, type Matcher } from './match'

export interface SearchState {
  readonly count: number
  /** which match is current, 0-based; -1 while there are none */
  readonly index: number
  /** the next match, wrapping; scrolled into view, centred */
  next(): void
  /** the previous match, wrapping */
  prev(): void
  /** what is shown changed (a post arrived): re-run, keeping the index */
  refresh(): void
  /** remove every attribute and highlight this search added */
  clear(): void
}

/** The blocks emphasis is counted in. */
const BLOCKS = 'p, li, pre, blockquote, h1, h2, h3, h4, h5, h6, tr, figure, .wk-obj, .fx-post, [data-search-block]'
/** Subtrees that are not searchable text. */
const SKIP = 'script, style, textarea, input, select, noscript, template, iframe, [aria-hidden="true"], [data-search-skip]'
/** Elements whose boundaries keep two blocks' words from reading as one. */
const BREAKS = new Set([
  'p', 'div', 'li', 'ul', 'ol', 'pre', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'section', 'article', 'figure', 'figcaption',
  'hr', 'header', 'footer', 'aside', 'details', 'summary', 'form', 'fieldset', 'dl', 'dt', 'dd', 'main',
])

/** Which blocks are near the current match -- itself and its neighbours --
 *  and which are plain hits. Pure: siblings are asked of the DOM by the
 *  caller, so the rule itself is held in Node (tests/fluid_search_in_unit). */
export function planBlocks<T>(blocks: T[], current: T | null, neighbours: (b: T) => (T | null)[]): { near: T[]; hit: T[] } {
  const near = new Set<T>()
  const hit = new Set<T>(blocks)
  if (current !== null && hit.has(current)) {
    hit.delete(current)
    near.add(current)
    for (const s of neighbours(current)) {
      if (s !== null && !near.has(s)) {
        near.add(s)
        hit.delete(s)
      }
    }
  }
  return { near: [...near], hit: [...hit] }
}

/* -- the flat text index ---------------------------------------------------- */

interface Seg { node: Text | null; start: number; end: number }
/** A non-text object's searchable text, anchored where it was walked past. */
interface ObjText { el: Element; text: string; at: number; end: number }

/** The text an element's own source gives it, or '' (svg is its own case). */
function ownWords(el: Element): string {
  const dst = el.getAttribute('data-search-text')
  if (dst?.trim()) return dst.trim()
  if (el.tagName === 'IMG') return el.getAttribute('alt')?.trim() ?? ''
  if (el.matches('figure, [role="img"], [role="figure"], canvas')) return el.getAttribute('aria-label')?.trim() ?? ''
  return ''
}

function index(root: HTMLElement): { flat: string; segs: Seg[]; objs: ObjText[] } {
  const segs: Seg[] = []
  const objs: ObjText[] = []
  let flat = ''
  /* Block boundaries read as a line break, so the last word of one block and
     the first of the next never match as if they were one word. */
  const newline = () => {
    if (flat && !flat.endsWith('\n')) {
      segs.push({ node: null, start: flat.length, end: flat.length + 1 })
      flat += '\n'
    }
  }
  const words = (node: Text) => {
    if (!node.data) return
    segs.push({ node, start: flat.length, end: flat.length + node.data.length })
    flat += node.data
  }
  const walk = (el: Element, svg: string[] | null, svgText: boolean) => {
    for (const node of Array.from(el.childNodes)) {
      if (node.nodeType === 3) {
        /* Inside an svg only a <text> is visible; its words are text. */
        if (!svg || svgText) words(node as Text)
        continue
      }
      if (node.nodeType !== 1) continue
      const child = node as Element
      const tag = child.tagName.toLowerCase()
      if (child.matches(SKIP)) continue
      if (svg && (tag === 'title' || tag === 'desc')) {
        /* an svg's title and description are its text, not the document's */
        const t = child.textContent?.trim()
        if (t && !svg.includes(t)) svg.push(t)
        continue
      }
      if (tag === 'br') { newline(); continue }
      const brk = BREAKS.has(tag)
      if (brk) newline()
      if (tag === 'svg') {
        const at = flat.length
        const parts: string[] = []
        walk(child, parts, false)
        const add = (s: string | null | undefined) => { const t = s?.trim(); if (t && !parts.includes(t)) parts.push(t) }
        add(child.getAttribute('aria-label'))
        let n = 0
        for (const d of child.querySelectorAll('[aria-label]')) { if (++n > 40) break; add(d.getAttribute('aria-label')) }
        if (parts.length) objs.push({ el: child, text: parts.join(' — '), at, end: flat.length })
      } else {
        const own = svg ? '' : ownWords(child)
        const at = flat.length
        walk(child, svg, svgText || (svg !== null && tag === 'text'))
        /* data-search-text & co. are read whatever the element shows; whether
           they count is claimObjects', once the text has been searched. Added
           after the walk, so an inner object always comes before its outer. */
        if (own) objs.push({ el: child, text: own, at, end: flat.length })
      }
      if (brk) newline()
    }
  }
  walk(root, null, false)
  return { flat, segs, objs }
}

/** One match's Range across every text node it covers. */
function rangeFor(segs: Seg[], start: number, end: number): Range | null {
  let sn: Text | null = null, so = 0, en: Text | null = null, eo = 0
  for (const s of segs) {
    if (!s.node || s.end <= start || s.start >= end) continue
    if (!sn) { sn = s.node; so = Math.max(0, start - s.start) }
    en = s.node
    eo = Math.min(s.node.data.length, end - s.start)
  }
  if (!sn || !en) return null
  const r = document.createRange()
  r.setStart(sn, so)
  r.setEnd(en, eo)
  return r
}

/* -- one hit: a range over text, or an object to outline --------------------- */

/** Which objects count as matches: those whose own text matches and inside
 *  which neither a text match nor an object already counted lies. `objs`
 *  come innermost first (as the walk adds them). Pure: the containment is
 *  asked of the caller, so the rule is held in Node (tests/fluid_search_in_unit). */
export function claimObjects<O>(objs: O[], matches: (o: O) => boolean, textInside: (o: O) => boolean,
  inside: (inner: O, outer: O) => boolean): O[] {
  const out: O[] = []
  for (const o of objs) {
    if (!matches(o) || textInside(o)) continue
    if (out.some((k) => inside(k, o))) continue
    out.push(o)
  }
  return out
}

interface Hit { at: number; range: Range | null; el: Element | null }

function hitsOf(root: HTMLElement, m: Matcher): Hit[] {
  const { flat, segs, objs } = index(root)
  const hits: Hit[] = []
  const found = findIn(flat, m)
  for (const h of found) {
    const r = rangeFor(segs, h.start, h.end)
    if (r) hits.push({ at: h.start + 0.5, range: r, el: null })
  }
  const budget = Math.max(0, MAX_MATCHES - hits.length)
  /* an object matches or it does not: one hit, however many matches the
     text it carries holds -- and none where a match inside it already is */
  const claimed = claimObjects(objs, (o) => findIn(o.text, m).length > 0,
    (o) => found.some((h) => h.start >= o.at && h.start < o.end),
    (inner, outer) => inner.el !== outer.el && outer.el.contains(inner.el))
  for (const o of claimed.slice(0, budget)) hits.push({ at: o.at + 0.25, range: null, el: o.el })
  hits.sort((a, b) => a.at - b.at)
  return hits
}

/* -- the shared highlight registry ------------------------------------------- */

interface HLRegistry { set(name: string, h: object): void; delete(name: string): void }
const registry = (): HLRegistry | null =>
  (globalThis as { CSS?: { highlights?: HLRegistry } }).CSS?.highlights ?? null
const highlightCtor = (): (new (...ranges: Range[]) => object) | null =>
  (globalThis as { Highlight?: new (...ranges: Range[]) => object }).Highlight ?? null

/** Every live search's ranges, so the two named highlights are their union. */
const live = new Map<number, { ranges: Range[]; current: Range[] }>()

function paint() {
  const reg = registry(), H = highlightCtor()
  if (!reg || !H) return
  const all: Range[] = [], cur: Range[] = []
  for (const v of live.values()) {
    all.push(...v.ranges)
    cur.push(...v.current)
  }
  const mh = new H(...all) as { priority?: number }
  mh.priority = 0
  const ch = new H(...cur) as { priority?: number }
  ch.priority = 1
  reg.set('fs-match', mh)
  reg.set('fs-current', ch)
}

const reducedMotion = () =>
  typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

/* -- one search --------------------------------------------------------------- */

let seq = 0

/** Search `root`'s current content for `m`. `onChange` is called after every
 *  re-count (navigation, a refresh that found more or fewer). */
export function searchIn(root: HTMLElement, m: Matcher, onChange?: () => void, start?: number): SearchState {
  const id = ++seq
  /* a search coming back with its content (kept.ts) resumes at its match,
     once there are matches -- a zone just placed draws its cards a moment
     after it is measured */
  let resume = start !== undefined && start > 0 ? start : -1
  const supported = !!(registry() && highlightCtor())
  let hits: Hit[] = []
  let index = -1
  let done = false
  let timer: ReturnType<typeof setTimeout> | undefined
  /* every element this search put an attribute on, so clear() restores the
     presentation exactly */
  const marked = new Set<Element>()

  const unmark = () => {
    for (const el of marked) {
      el.removeAttribute('data-fs-hit')
      el.removeAttribute('data-fs-near')
      el.removeAttribute('data-fs-obj')
    }
    marked.clear()
    root.removeAttribute('data-fs-on')
  }

  const anchorOf = (r: Range | null): Element | null => {
    if (!r) return null
    const c = r.startContainer
    return c.nodeType === 1 ? (c as Element) : c.parentElement
  }

  const blockOf = (h: Hit): Element | null => {
    const start = h.el ?? anchorOf(h.range)
    const b = start?.closest(BLOCKS) ?? null
    return b && root.contains(b) && b !== root ? b : null
  }

  const mark = () => {
    unmark()
    if (!hits.length) return
    root.setAttribute('data-fs-on', '')
    const curHit = index >= 0 && index < hits.length ? hits[index] : null
    const seen = new Set<Element>()
    const blocks: Element[] = []
    for (const h of hits) {
      const b = blockOf(h)
      if (b && !seen.has(b)) { seen.add(b); blocks.push(b) }
    }
    const curBlock = curHit ? blockOf(curHit) : null
    const plan = planBlocks(blocks, curBlock, (b) => [b.previousElementSibling, b.nextElementSibling])
    for (const b of plan.near) { b.setAttribute('data-fs-near', ''); marked.add(b) }
    for (const b of plan.hit) { b.setAttribute('data-fs-hit', ''); marked.add(b) }
    /* an ancestor block of a marked block stays at full strength too, or
       dimming it would dim the match inside it */
    for (const b of [...marked]) {
      for (let p = b.parentElement; p && p !== root; p = p.parentElement) {
        if (marked.has(p)) break
        if (p.matches(BLOCKS)) { p.setAttribute('data-fs-near', ''); marked.add(p) }
      }
    }
    for (const h of hits) {
      if (h.el) { h.el.setAttribute('data-fs-obj', h === curHit ? 'current' : 'hit'); marked.add(h.el) }
    }
    /* Without the Highlight API the matching block is outlined instead. */
    if (!supported) {
      for (const b of blocks) { b.setAttribute('data-fs-obj', curBlock === b ? 'current' : 'hit'); marked.add(b) }
    }
  }

  const scrollToHit = (h: Hit) => {
    const behavior: ScrollBehavior = reducedMotion() ? 'auto' : 'smooth'
    const el = h.el ?? anchorOf(h.range)
    if (!el) return
    let rect: DOMRect | null = null
    if (h.range) {
      const r = h.range.getBoundingClientRect()
      if (r && (r.width || r.height)) rect = r
    }
    if (!rect) { el.scrollIntoView({ block: 'center', behavior }); return }
    /* centre the match's own box in its nearest scroller, not the block's */
    let sc: Element | null = el
    while (sc && sc !== root) {
      const s = getComputedStyle(sc)
      if (/(auto|scroll)/.test(s.overflowY) && sc.scrollHeight > sc.clientHeight) break
      sc = sc.parentElement
    }
    if (!sc || sc === root.parentElement) { el.scrollIntoView({ block: 'center', behavior }); return }
    const b = sc.getBoundingClientRect()
    const delta = rect.top + rect.height / 2 - (b.top + b.height / 2)
    if (Math.abs(delta) > 8) sc.scrollBy({ top: delta, behavior })
  }

  const apply = (scroll: boolean) => {
    const cur = index >= 0 && index < hits.length ? hits[index] : null
    live.set(id, {
      ranges: supported ? hits.filter((h) => h !== cur && h.range).map((h) => h.range as Range) : [],
      current: supported && cur?.range ? [cur.range] : [],
    })
    paint()
    mark()
    if (scroll && cur) scrollToHit(cur)
    onChange?.()
  }

  const compute = (): boolean => {
    hits = hitsOf(root, m)
    if (hits.length && resume >= 0) {
      index = Math.min(resume, hits.length - 1)
      resume = -1
      return true
    }
    if (!hits.length) index = -1
    else if (index < 0) index = 0
    else if (index >= hits.length) index = hits.length - 1
    return false
  }

  const refresh = () => {
    if (done) return
    apply(compute())
  }

  /* Content changed: re-run, keeping the index. Attributes this search sets
     are not observed, so its own emphasis never re-triggers it. */
  const mo = new MutationObserver(() => {
    clearTimeout(timer)
    timer = setTimeout(refresh, 150)
  })
  mo.observe(root, { childList: true, subtree: true, characterData: true })

  const step = (d: 1 | -1) => {
    if (!hits.length) return
    index = (((index + d) % hits.length) + hits.length) % hits.length
    apply(true)
  }

  compute()
  apply(true)

  return {
    get count() { return hits.length },
    get index() { return index },
    next: () => step(1),
    prev: () => step(-1),
    refresh,
    clear: () => {
      if (done) return
      done = true
      mo.disconnect()
      clearTimeout(timer)
      unmark()
      live.delete(id)
      paint()
    },
  }
}
