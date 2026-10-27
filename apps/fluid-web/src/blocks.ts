/* HOW A TURN'S BODY IS READ INTO BLOCKS: the one reader behind ./prose.tsx's
   drawing and behind ./experimental/spec/check.ts, which tells an agent what
   will not render. Moved out of prose.tsx unchanged so it imports nothing
   that draws; prose.tsx re-exports it. */
import { RENDERABLE } from './experimental/spec'

export type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'para'; text: string }
  | { kind: 'quote'; text: string }
  | { kind: 'code'; lang: string | null; text: string; info?: string; closed?: boolean }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; head: string[]; rows: string[][] }
  | { kind: 'rule' }

/* A CODE FENCE, AS COMMONMARK 0.31.2 §4.5 DEFINES ONE.
 *
 * It was /^```(\w*)\s*$/, and that got four things wrong, each measured
 * against the real `blocksOf`. A label that was not all word characters --
 * `vega-lite`, `c++`, `python title=x` -- or an opening indented by a space
 * or three did not open a block, and its closing ``` then OPENED one that
 * swallowed everything after it. `~~~` and four-backtick fences were not
 * fences at all. And a ```js line inside a block closed it, so a block
 * showing somebody how to write a fence was cut in half.
 *
 * Now: up to three spaces, then three or more of ONE character, then the
 * info string, whose first word is the language. A backtick fence's info
 * string may not hold a backtick (that line is inline code, not a fence).
 * Only a fence of the same character, at least as long, with nothing after
 * it but spaces or tabs, closes the block; an unclosed block runs to the end
 * of the body, as before. */
const FENCE_OPEN = /^( {0,3})(`{3,}|~{3,})(.*)$/
const fenceCloses = (line: string, ch: string, len: number) => {
  const m = /^ {0,3}(`{3,}|~{3,})[ \t]*$/.exec(line)
  return m !== null && m[1][0] === ch && m[1].length >= len
}
const HEADING = /^(#{1,6})\s+(.*)$/
const QUOTE = /^>\s?(.*)$/
const BULLET = /^\s*[-*+]\s+(.*)$/
const NUMBER = /^\s*\d+[.)]\s+(.*)$/
const RULE = /^\s*(-{3,}|\*{3,}|_{3,})\s*$/
const ROW = /^\s*\|(.+)\|\s*$/
const DIVIDER = /^\s*\|?[\s:|-]+\|[\s:|-]*$/

const cells = (line: string): string[] =>
  line
    .replace(/^\s*\|/, '')
    .replace(/\|\s*$/, '')
    .split('|')
    .map((c) => c.trim())

/* AN IMAGE PLACED IN THE POST. A paragraph that holds nothing but one
   Admission -- `![alt](adm-…)`, or the bare `adm-…` -- is where the author
   put a figure, the way a figure sits in a source document. It is drawn as
   a block in the flow of the post when the record says it is an image, and
   stays that one reference otherwise. The same `adm-` inside running text
   keeps its compact thumbnail. Moved here from prose.tsx unchanged, so the
   object model (./experimental/objects.ts) reads figures without React. */
const PLACED = /^\s*(?:!\[([^\]\n]*)\]\((adm-[0-9a-f]{8,})\)|`?(adm-[0-9a-f]{8,})`?)\s*$/

/** The Admission a paragraph holds on its own, with its alt text, or null. */
export function placedRef(text: string): { id: string; label?: string } | null {
  const m = PLACED.exec(text)
  if (!m) return null
  return m[2] ? { id: m[2], label: m[1] || undefined } : { id: m[3] }
}

/** Where a block starts and ends, and for a code block the fence that opened it. */
export interface Placed {
  block: Block
  /** 0-based index of the block's first line in the body read. */
  line: number
  /** 0-based index of the line after the block's last. */
  end: number
  fence?: { run: string; info: string; closed: boolean }
}

/** A block and where it sits in the body: its first line and the line after
 *  its last, counted from 0. Read by the object model, never used to draw. */
export type PlacedBlock = Block & { line: number; end: number }

/** Read a body into blocks. Never throws; anything unrecognised is prose. */
export function blocksOf(src: string): Block[] {
  return placedIn(src).map((p) => p.block)
}

/** `blocksOf`, with where each block sits in the body. */
export function blocksAt(src: string): PlacedBlock[] {
  return placedIn(src).map(({ block, line, end }) => ({ ...block, line, end }))
}

/** blocksOf, saying where each block is and how each fence was written
 *  (for ./experimental/spec/check.ts). */
export function placedIn(src: string): Placed[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const out: Placed[] = []
  let at = 0
  let i = 0
  /* A block ends after the last line the loop consumed for it; a paragraph,
     at the line that ended it. */
  const put = (block: Block, line: number, fence?: Placed['fence'], end = Math.min(lines.length, i + 1)) => {
    out.push(fence ? { block, line, end, fence } : { block, line, end })
  }
  let para: string[] = []

  const flush = () => {
    if (para.length) put({ kind: 'para', text: para.join('\n').trim() }, at, undefined, i)
    para = []
  }

  for (; i < lines.length; i++) {
    const line = lines[i]

    const fence = FENCE_OPEN.exec(line)
    if (fence && !(fence[2][0] === '`' && fence[3].includes('`'))) {
      flush()
      const [, indent, run, info] = fence
      const opened = i
      /* Content lines lose up to as many leading spaces as the opening
         fence had, and no more. */
      const strip = new RegExp(`^ {0,${indent.length}}`)
      const body: string[] = []
      i += 1
      while (i < lines.length && !fenceCloses(lines[i], run[0], run.length))
        body.push(lines[i++].replace(strip, ''))
      const lang = info.trim().split(/\s+/)[0]
      put({
        kind: 'code',
        lang: lang || null,
        text: body.join('\n'),
        /* EXPERIMENTAL (experimental/renderable.tsx): only a marked block
           carries its attributes and whether it was closed. */
        ...(RENDERABLE.has(lang) ? { info: info.trim(), closed: i < lines.length } : {}),
      }, opened, { run, info: info.trim(), closed: i < lines.length })
      continue
    }

    if (!line.trim()) {
      flush()
      continue
    }

    if (RULE.test(line)) {
      flush()
      put({ kind: 'rule' }, i)
      continue
    }

    const h = HEADING.exec(line)
    if (h) {
      flush()
      put({ kind: 'heading', level: h[1].length, text: h[2].trim() }, i)
      continue
    }

    /* A table needs a header row and a divider under it. Without the divider
       it is prose that happens to contain pipes, and it stays prose. */
    if (ROW.test(line) && i + 1 < lines.length && DIVIDER.test(lines[i + 1])) {
      flush()
      const from = i
      const head = cells(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && ROW.test(lines[i])) rows.push(cells(lines[i++]))
      i -= 1
      put({ kind: 'table', head, rows }, from)
      continue
    }

    if (QUOTE.test(line)) {
      flush()
      const from = i
      const body: string[] = []
      while (i < lines.length && QUOTE.test(lines[i]))
        body.push(QUOTE.exec(lines[i++])![1])
      i -= 1
      put({ kind: 'quote', text: body.join('\n').trim() }, from)
      continue
    }

    const bullet = BULLET.exec(line)
    const number = NUMBER.exec(line)
    if (bullet || number) {
      flush()
      const from = i
      const ordered = !bullet
      const items: string[] = []
      while (i < lines.length) {
        const b = BULLET.exec(lines[i])
        const n = NUMBER.exec(lines[i])
        if (bullet ? !b : !n) {
          /* a plain indented line continues the item above it */
          if (items.length && /^\s+\S/.test(lines[i]) && lines[i].trim()) {
            items[items.length - 1] += ' ' + lines[i].trim()
            i += 1
            continue
          }
          break
        }
        items.push(((b ?? n) as RegExpExecArray)[1].trim())
        i += 1
      }
      i -= 1
      put({ kind: 'list', ordered, items }, from)
      continue
    }

    if (!para.length) at = i
    para.push(line)
  }
  flush()
  return out
}
