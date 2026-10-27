/* ------------------------------------------------------------------------ *
 * A SELECTION IN THE RENDERED TURN, AS A PLACE IN THE STORED TEXT.
 *
 * A person selects in the post they are reading. The anchor is an offset
 * into the stored text part, which is Markdown: the rendered post has lost
 * the `**`, the `## `, the `> `, a link's `(url)` and the fence lines, so a
 * DOM offset is not a stored offset. Nothing here guesses by quote: each
 * text part's rendering is wrapped in an element carrying `data-src-part`,
 * and its text nodes are ALIGNED, in reading order, against that part's
 * stored text -- a monotone walk, so the second of two identical sentences
 * maps to the second, because everything before it has already been
 * consumed. A rendered character that cannot be placed is not placed: a
 * selection covering one is refused rather than anchored somewhere near.
 *
 * Offsets are UTF-16, as the browser counts, and are sent with
 * `unit: 'utf16'` and the stored characters they cover; the server converts,
 * checks the grapheme edges and the excerpt, and finds or creates the one
 * anchor for that place. Edges are first widened to whole graphemes so a
 * selection the browser drew is never refused for splitting one.
 *
 * An element carrying `data-src-text` stands for exactly that stored text
 * (an inline reference drawn as a truncated id); `data-src-skip` is chrome
 * that is not the author's text at all.
 * ------------------------------------------------------------------------ */

export interface Passage {
  part: number
  /** UTF-16 offsets into the stored text of `part` */
  start: number
  end: number
  /** the stored characters at that range */
  excerpt: string
}

/** One rendered text node and, per character, where it is in the source
 *  (-1 where it is not), or a whole element standing for a known span. */
interface Seg {
  node: Text
  at: number[]
}

const SKIP =
  '[data-src-skip],[aria-hidden="true"],.m-span-glyph,.pr-html-bar,.pr-html-note,iframe,textarea,input'

/** A gap between two placed nodes is markup only if it holds no letter or
 *  digit -- once a link's destination, a fence's opening line and an
 *  ordered list's number, none of which is rendered, are set aside. */
const markupGap = (g: string) =>
  !/[\p{L}\p{N}]/u.test(
    g
      .replace(/\]\([^)\s]*\)/g, '')
      .replace(/(^|\n)[ \t]*(`{3,}|~{3,})[^\n]*/g, '$1')
      .replace(/(^|\n)[ \t]*\d+[.)][ \t]/g, '$1'),
  )

function textNodes(root: Element): (Text | Element)[] {
  const out: (Text | Element)[] = []
  const walk = (el: Element) => {
    for (const n of Array.from(el.childNodes)) {
      if (n.nodeType === Node.TEXT_NODE) out.push(n as Text)
      else if (n.nodeType === Node.ELEMENT_NODE) {
        const e = n as Element
        if (e.hasAttribute('data-src-text')) out.push(e)
        else if (!e.matches(SKIP)) walk(e)
      }
    }
  }
  walk(root)
  return out
}

/** Align a part's rendering against its stored text. */
export function align(root: Element, src: string): Seg[] {
  const segs: Seg[] = []
  let c = 0
  for (const n of textNodes(root)) {
    if (n.nodeType !== Node.TEXT_NODE) {
      /* an element standing for a stored span: consume it, place nothing */
      const said = (n as Element).getAttribute('data-src-text') ?? ''
      const i = said ? src.indexOf(said, c) : -1
      if (i >= 0 && markupGap(src.slice(c, i))) c = i + said.length
      continue
    }
    const t = n as Text
    const s = t.data
    if (!s) continue
    const i = src.indexOf(s, c)
    if (i >= 0 && markupGap(src.slice(c, i))) {
      segs.push({ node: t, at: unitMap(i, s.length) })
      c = i + s.length
      continue
    }
    /* NOT VERBATIM: a quote's lines lost their `> `, a list item's
       continuation its indent. Place character by character, each within a
       short reach; one that is not found stays unplaced. */
    const at: number[] = []
    for (let k = 0; k < s.length; k++) {
      const ch = s[k]
      let j = -1
      for (let r = c; r < Math.min(src.length, c + 16); r++)
        if (src[r] === ch || (/\s/.test(ch) && /\s/.test(src[r]))) {
          j = r
          break
        }
      at.push(j)
      if (j >= 0) c = j + 1
    }
    segs.push({ node: t, at })
  }
  return segs
}

function unitMap(i: number, len: number): number[] {
  const a = new Array<number>(len)
  for (let k = 0; k < len; k++) a[k] = i + k
  return a
}

/** Grapheme edges of `s`, in UTF-16 units. */
function edges(s: string): Set<number> {
  const out = new Set<number>([0, s.length])
  const Seg = (Intl as unknown as { Segmenter?: typeof Intl.Segmenter }).Segmenter
  if (!Seg) {
    for (let i = 0; i <= s.length; i++) out.add(i)
    return out
  }
  for (const g of new Seg(undefined, { granularity: 'grapheme' }).segment(s)) out.add(g.index)
  return out
}

/** The part container a node is in, if it is one of this Turn's. */
export function partOf(node: Node | null, turn: string): HTMLElement | null {
  const el = node && (node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement)
  const box = el?.closest<HTMLElement>('[data-src-part]') ?? null
  return box && box.dataset.srcTurn === turn ? box : null
}

export type Placed = { ok: Passage } | { refused: string }

/** Where a live selection is in the stored text, or why it cannot be said. */
export function placeSelection(range: Range, box: HTMLElement, src: string): Placed {
  const part = Number(box.dataset.srcPart)
  let first = -1
  let last = -1
  let unplaced = false
  for (const { node, at } of align(box, src)) {
    if (!range.intersectsNode(node)) continue
    const s = node === range.startContainer ? range.startOffset : 0
    const e = node === range.endContainer ? range.endOffset : node.data.length
    for (let k = s; k < e; k++) {
      const j = at[k]
      if (j < 0) {
        if (!/\s/.test(node.data[k])) unplaced = true
        continue
      }
      if (first < 0) first = j
      last = j
    }
  }
  if (unplaced)
    return { refused: 'part of that selection could not be placed in the text as written' }
  if (first < 0) return { refused: 'nothing of the text is selected' }
  let start = first
  let end = last + 1
  /* a double-click takes the trailing space; a triple-click the newline */
  while (start < end && /\s/.test(src[start])) start++
  while (end > start && /\s/.test(src[end - 1])) end--
  if (start >= end) return { refused: 'nothing of the text is selected' }
  const g = edges(src)
  while (start > 0 && !g.has(start)) start--
  while (end < src.length && !g.has(end)) end++
  return { ok: { part, start, end, excerpt: src.slice(start, end) } }
}

/** The rendered range for a stored UTF-16 range, for marking it in place. */
export function rangeOf(box: HTMLElement, src: string, start: number, end: number): Range | null {
  let a: [Text, number] | null = null
  let b: [Text, number] | null = null
  for (const { node, at } of align(box, src))
    for (let k = 0; k < at.length; k++) {
      const j = at[k]
      if (j < 0) continue
      if (!a && j >= start && j < end) a = [node, k]
      if (j >= start && j < end) b = [node, k + 1]
    }
  if (!a || !b) return null
  const r = document.createRange()
  r.setStart(a[0], a[1])
  r.setEnd(b[0], b[1])
  return r
}

/** Mark ranges with a named CSS highlight, where the browser has them. */
export function highlight(name: string, ranges: Range[]) {
  const reg = (globalThis.CSS as unknown as { highlights?: Map<string, unknown> })?.highlights
  const H = (globalThis as unknown as { Highlight?: new (...r: Range[]) => unknown }).Highlight
  if (!reg || !H) return
  if (ranges.length === 0) reg.delete(name)
  else reg.set(name, new H(...ranges))
}

/* One named highlight drawn for many owners at once -- every Turn on the page
   marks its own annotated passages -- so each owner's ranges are kept apart
   and the highlight is the union of them. */
const owned = new Map<string, Map<string, Range[]>>()

/** Mark this owner's ranges under a shared highlight name; [] withdraws them. */
export function highlightFor(name: string, owner: string, ranges: Range[]) {
  const m = owned.get(name) ?? new Map<string, Range[]>()
  owned.set(name, m)
  if (ranges.length > 0) m.set(owner, ranges)
  else m.delete(owner)
  highlight(name, [...m.values()].flat())
}
