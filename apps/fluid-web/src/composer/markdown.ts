/* ------------------------------------------------------------------------ *
 * MARKDOWN ACCELERATORS ARE TEXT IN, TEXT OUT.
 *
 * Every function here takes the whole value of a textarea and a selection,
 * and returns the whole new value and the selection that should follow. None
 * of them touches the DOM, React, or the record: the caller applies the Edit,
 * and that separation is what lets this arithmetic be checked by reading it.
 *
 * The one bug this kind of code always has is a selection that drifts after
 * characters are inserted or removed BEFORE it. The rule used throughout: an
 * offset moves by exactly the number of characters added (or removed) at
 * positions strictly before it, and by nothing that happened after it. Each
 * place that returns a selection says which characters those were.
 *
 * Offsets are UTF-16 code units, because that is what `selectionStart` is.
 * Line breaks are '\n' only, because a textarea's value is normalised to '\n'
 * by the browser whatever the platform typed.
 * ------------------------------------------------------------------------ */

export interface Edit {
  /** the whole new value */
  text: string
  /** the new selection; start === end is a caret */
  start: number
  end: number
}

/** Callers hand over `selectionStart`/`selectionEnd`, which are ordered, but
 *  a caller computing its own range may not be; and an offset past either end
 *  would make every slice below quietly wrong rather than loudly wrong. */
function span(text: string, a: number, b: number): [number, number] {
  const x = Math.max(0, Math.min(text.length, a))
  const y = Math.max(0, Math.min(text.length, b))
  return x <= y ? [x, y] : [y, x]
}

/** Double-click on most platforms selects the word AND its trailing space, and
 *  `**word **` is not bold in any renderer. So a wrap applies to the selection
 *  without its outer whitespace. A selection that is nothing but whitespace
 *  is left as it is: there is no text in it to prefer. */
function trimmed(text: string, s: number, e: number): [number, number] {
  let a = s
  let b = e
  while (a < b && /\s/.test(text[a])) a++
  while (b > a && /\s/.test(text[b - 1])) b--
  return a < b ? [a, b] : [s, e]
}

/** `lastIndexOf('\n', -1)` still inspects index 0, so a caret at 0 in a text
 *  that begins with a newline would claim its line starts at 1. Offset 0 is
 *  always a line start; say so rather than trust the search. */
function lineStartOf(text: string, p: number): number {
  return p === 0 ? 0 : text.lastIndexOf('\n', p - 1) + 1
}

function lineEndOf(text: string, p: number): number {
  const i = text.indexOf('\n', p)
  return i === -1 ? text.length : i
}

/* ---- inline markers ------------------------------------------------------ */

/** A marker that is one character repeated ('*', '**', '_', '`') cannot be
 *  recognised by string comparison: `**bold**` starts with '*', but it is not
 *  italic, and stripping one star from it would silently turn bold into
 *  italic. Such markers are judged by the length of the run they sit in. */
function repeatedChar(marker: string): string | null {
  const c = marker[0]
  for (const ch of marker) if (ch !== c) return null
  return c
}

function runBefore(text: string, at: number, c: string, floor: number): number {
  let n = 0
  while (at - n - 1 >= floor && text[at - n - 1] === c) n++
  return n
}

function runAfter(text: string, at: number, c: string, ceil: number): number {
  let n = 0
  while (at + n < ceil && text[at + n] === c) n++
  return n
}

/** A run carries a marker of length m when it is exactly m long, or when it
 *  is three long and m is one or two: `***x***` is bold AND italic, so either
 *  toggle may take its own share out of it. A run of 2m is the doubled form
 *  of a different marker (`**` against `*`), never two copies of this one. */
function runCarries(run: number, m: number): boolean {
  return run === m || (run === 3 && m < 3)
}

/** The selection is `**x**` itself — the person selected the markers too. */
function wrappedInside(text: string, s: number, e: number, marker: string): boolean {
  const m = marker.length
  if (e - s < 2 * m) return false
  const c = repeatedChar(marker)
  if (c === null) return text.startsWith(marker, s) && text.endsWith(marker, e)
  // Runs are counted only up to the middle of the selection, so that a
  // selection of nothing but marker characters is not counted twice.
  const mid = s + Math.floor((e - s) / 2)
  return runCarries(runAfter(text, s, c, mid), m) && runCarries(runBefore(text, e, c, mid), m)
}

/** The markers sit just outside the selection — the person selected the
 *  word inside `**x**`, or the caret sits in a pair it has just inserted. */
function wrappedOutside(text: string, s: number, e: number, marker: string): boolean {
  const m = marker.length
  const c = repeatedChar(marker)
  if (c === null) {
    return s >= m && text.slice(s - m, s) === marker && text.slice(e, e + m) === marker
  }
  return runCarries(runBefore(text, s, c, 0), m) && runCarries(runAfter(text, e, c, text.length), m)
}

export function toggleWrap(text: string, start: number, end: number, marker: string): Edit {
  const [s0, e0] = span(text, start, end)
  const m = marker.length
  if (m === 0) return { text, start: s0, end: e0 }
  // Trim before looking for markers, not after: `**word** ` selected with its
  // trailing space must be recognised as already bold, not wrapped again.
  const [s, e] = trimmed(text, s0, e0)

  if (wrappedInside(text, s, e, marker)) {
    // Nothing is removed before s, so start stays; the leading marker (m) and
    // the trailing marker (m) both sat before e, so end moves back by 2m.
    return {
      text: text.slice(0, s) + text.slice(s + m, e - m) + text.slice(e),
      start: s,
      end: e - 2 * m,
    }
  }

  if (wrappedOutside(text, s, e, marker)) {
    // Only the leading marker lay before the selection; the trailing one lay
    // after it and moves nothing. Both ends therefore move back by m, not 2m.
    // With an empty selection this is what makes a second press undo the
    // first: the caret sits between an empty pair, and the pair goes.
    return {
      text: text.slice(0, s - m) + text.slice(s, e) + text.slice(e + m),
      start: s - m,
      end: e - m,
    }
  }

  // Wrap. The opening marker is inserted before both ends, so both move
  // forward by m; the closing marker is inserted after e and moves neither.
  // An empty selection takes the same arithmetic and lands the caret between
  // the pair, which is where the person is about to type.
  return {
    text: text.slice(0, s) + marker + text.slice(s, e) + marker + text.slice(e),
    start: s + m,
    end: e + m,
  }
}

/* ---- code, at the size the selection actually is ------------------------- *
 * ONE ACTION, BECAUSE A WRITER HAS ONE INTENT. Offering "code" and "code
 * block" as two buttons asks somebody to classify their own selection before
 * they are allowed to mark it, and the selection already answers: a span
 * inside a sentence is inline code, and something spanning lines is a block.
 * Choosing from the selection is not a guess, it is reading what is there.
 */
export function toggleCode(text: string, start: number, end: number): Edit {
  const [s, e] = span(text, start, end)
  if (!text.slice(s, e).includes('\n')) return toggleWrap(text, s, e, '`')

  // A fence has to own whole lines, so the block is grown to the line
  // boundaries around the selection before anything is inserted.
  const first = lineStartOf(text, s)
  const last = lineEndOf(text, e)
  const lines = text.slice(first, last).split('\n')

  // SELECTED WITH ITS FENCES: the person dragged over the whole construct.
  if (
    lines.length > 2 &&
    /^```/.test(lines[0]) &&
    /^```\s*$/.test(lines[lines.length - 1])
  ) {
    const inner = lines.slice(1, -1).join('\n')
    return {
      text: text.slice(0, first) + inner + text.slice(last),
      start: first,
      end: first + inner.length,
    }
  }

  // SELECTED WITHOUT THEM, which is the ordinary case and the one a first
  // attempt at this gets wrong. Pressing the button, then pressing it again,
  // must undo -- and after the first press the selection is the CODE, so the
  // fences it created now lie outside what is selected. They have to be
  // looked for on the lines either side rather than inside.
  const block = lines.join('\n')
  const aboveEnd = first - 1
  const above = first > 0 ? text.slice(lineStartOf(text, aboveEnd), aboveEnd) : null
  const belowStart = last + 1
  const below =
    last < text.length ? text.slice(belowStart, lineEndOf(text, belowStart)) : null
  if (above !== null && below !== null && /^```/.test(above) && /^```\s*$/.test(below)) {
    const from = lineStartOf(text, aboveEnd)
    return {
      text: text.slice(0, from) + block + text.slice(lineEndOf(text, belowStart)),
      start: from,
      end: from + block.length,
    }
  }

  // '```' plus its newline is four characters, and all four are inserted
  // before the block, so the whole selection moves forward by exactly four.
  return {
    text: text.slice(0, first) + '```\n' + block + '\n```' + text.slice(last),
    start: first + 4,
    end: first + 4 + block.length,
  }
}

/* ---- line prefixes ------------------------------------------------------- */

/** A prefix that is a list marker is placed after the line's indentation and
 *  REPLACES any other list marker already there — turning `- a` into an
 *  ordered item must give `1. a`, not `1. - a`, which is a nested list. A
 *  prefix that is not a list marker ('> ') goes at column 0 and replaces
 *  nothing but itself. */
const LIST_PREFIX = /^(?:[-*+]|\d+[.)]) $/
const ORDERED_PREFIX = /^\d+([.)]) $/
const LIST_ITEM = /^(?:[-*+]|\d+[.)]) /
const ORDERED_ITEM = /^\d+[.)] /

interface Plan {
  /** columns of indentation the marker sits after */
  indent: number
  /** length of the marker being replaced, 0 when there is none */
  old: number
  /** the marker being written in its place, '' when removing */
  add: string
}

export function toggleLinePrefix(text: string, start: number, end: number, prefix: string): Edit {
  const [s, e] = span(text, start, end)
  if (prefix === '') return { text, start: s, end: e }

  const first = lineStartOf(text, s)
  // A selection that ends exactly at the start of a line (a triple-click, a
  // drag to the left margin) has not touched that line in any sense the person
  // means, and prefixing it would surprise them.
  const last = lineEndOf(text, e > s && text[e - 1] === '\n' ? e - 1 : e)
  const lines = text.slice(first, last).split('\n')

  const list = LIST_PREFIX.test(prefix)
  const ordered = ORDERED_PREFIX.exec(prefix)
  const indentOf = (line: string): number => (list ? (/^[ \t]*/.exec(line)?.[0].length ?? 0) : 0)
  // Any number counts as "already ordered": the digits are ours to rewrite,
  // so a list numbered 3, 4, 5 is still a list this toggle can remove.
  const carries = (body: string): boolean => (ordered ? ORDERED_ITEM.test(body) : body.startsWith(prefix))

  // Blank lines between paragraphs are neither prefixed nor asked whether they
  // carry the prefix: a list of three paragraphs should not gain an empty
  // fourth item, nor fail to toggle off because the gaps lack markers. When
  // every touched line is blank — the empty textarea, a caret on an empty
  // line — those lines ARE the target, since that is how a list is begun.
  const all = lines.map((_, i) => i)
  const content = all.filter(i => lines[i].trim() !== '')
  const targets = new Set(content.length > 0 ? content : all)
  const removing = [...targets].every(i => carries(lines[i].slice(indentOf(lines[i]))))

  let n = 0
  const plans: (Plan | null)[] = lines.map((line, i) => {
    if (!targets.has(i)) return null
    const indent = indentOf(line)
    const body = line.slice(indent)
    if (removing) {
      return { indent, old: ordered ? (ORDERED_ITEM.exec(body)?.[0].length ?? 0) : prefix.length, add: '' }
    }
    // Lines that already carry the marker are rewritten rather than skipped,
    // so a partly-ordered selection comes out numbered 1..n without gaps, and
    // a partly-quoted one does not gain a second '> ' on the quoted lines.
    const old = list ? (LIST_ITEM.exec(body)?.[0].length ?? 0) : body.startsWith(prefix) ? prefix.length : 0
    const add = ordered ? `${++n}${ordered[1]} ` : prefix
    return { indent, old, add }
  })

  // Record where each line started before and after, because a line's shift
  // is the SUM of every earlier line's change plus its own — ten items each
  // gaining '- ' move the tenth by twenty, not by two. `+ 1` is the '\n' that
  // split() consumed; it is counted on both sides so the difference is exact.
  const out: string[] = []
  const rows: { oldAt: number; newAt: number; len: number; plan: Plan | null }[] = []
  let oldAt = first
  let newAt = first
  lines.forEach((line, i) => {
    const plan = plans[i]
    const next = plan === null ? line : line.slice(0, plan.indent) + plan.add + line.slice(plan.indent + plan.old)
    rows.push({ oldAt, newAt, len: line.length, plan })
    out.push(next)
    oldAt += line.length + 1
    newAt += next.length + 1
  })
  const delta = newAt - oldAt

  // `lean` decides where an offset lands when it sat at, or inside, the marker
  // being replaced. A caret leans after the new marker, so a person who starts
  // a list on an empty line types into the item. The start of a range leans
  // before it when it sat at the very start of the marker, so selected lines
  // stay whole-line selected and the toggle can be pressed again at once.
  const map = (p: number, lean: 'before' | 'after'): number => {
    if (p < first) return p
    if (p > last) return p + delta // after the block: every line's change lay before it
    for (const r of rows) {
      if (p > r.oldAt + r.len) continue
      const c = p - r.oldAt
      const { plan } = r
      if (plan === null || c < plan.indent) return r.newAt + c
      if (c === plan.indent && lean === 'before') return r.newAt + c
      if (c <= plan.indent + plan.old) return r.newAt + plan.indent + plan.add.length
      return r.newAt + c - plan.old + plan.add.length
    }
    return p + delta // not reached: every p in [first, last] falls in some row
  }

  return {
    text: text.slice(0, first) + out.join('\n') + text.slice(last),
    start: s === e ? map(s, 'after') : map(s, 'before'),
    end: map(e, 'after'),
  }
}

/* ---- Enter inside a list or quote ---------------------------------------- */

/** Quote markers first, then at most one list item inside them, so `> - a`
 *  continues as `> - `. A task item continues UNCHECKED: the next task is not
 *  done merely because the one above it was. */
const QUOTE = /^(?:> ?)+/
const ITEM = /^([ \t]*)(?:([-*+])|(\d+)([.)]))( +)(\[[ xX]\] )?/
const ORDERED_LINE = /^([ \t]*)(\d+)([.)])( +)/

export function continueLine(text: string, caret: number): Edit | null {
  const at = Math.max(0, Math.min(text.length, caret))
  const ls = lineStartOf(text, at)
  const le = lineEndOf(text, at)
  const line = text.slice(ls, le)

  const quote = QUOTE.exec(line)?.[0] ?? ''
  const item = ITEM.exec(line.slice(quote.length))
  if (quote === '' && item === null) return null
  const marker = quote + (item?.[0] ?? '')

  // A caret in the indentation or inside the marker is a person making room
  // above the item, not asking for a new one; let Enter be Enter.
  if (at - ls < marker.length) return null

  if (line.slice(marker.length).trim() === '') {
    // The empty marker is how a person leaves: the innermost construct goes.
    // An empty item inside a quote leaves the quote marker, so a second Enter
    // leaves the quote as well. The whole line is replaced, so nothing before
    // `ls` changes and the caret sits after whatever marker is kept.
    const kept = item !== null ? quote : ''
    return { text: text.slice(0, ls) + kept + text.slice(le), start: ls + kept.length, end: ls + kept.length }
  }

  let next = quote
  let tail = text.slice(at)
  if (item !== null) {
    const indent: string = item[1]
    const bullet: string | undefined = item[2]
    const num: string | undefined = item[3]
    const delim: string | undefined = item[4]
    const gap: string = item[5]
    const task: string | undefined = item[6]
    if (bullet !== undefined) {
      next += indent + bullet + gap
    } else if (num !== undefined && delim !== undefined) {
      const n = Number(num) + 1
      next += indent + `${n}${delim}` + gap
      tail = renumberAfter(tail, quote, indent, delim, n)
    }
    if (task !== undefined) next += '[ ] '
  }

  // The '\n' and the new marker are both inserted before the caret, so it
  // moves forward by exactly their length. Renumbering rewrites only `tail`,
  // which lies wholly after the caret, so however many digits it adds or
  // removes (9 becoming 10) the caret is not moved by it.
  const caretAt = at + 1 + next.length
  return { text: text.slice(0, at) + '\n' + next + tail, start: caretAt, end: caretAt }
}

/** The siblings below an inserted item each move up by one, as long as they
 *  are numbered in sequence. A list numbered `1. 1. 1.` (a common lazy style
 *  that renderers accept) breaks the sequence at once and is left alone:
 *  rewriting numbers a person chose is worse than leaving them. Lines indented
 *  deeper than the item are its children and are stepped over; anything else,
 *  a blank line included, ends the list. */
function renumberAfter(tail: string, quote: string, indent: string, delim: string, from: number): string {
  const lines = tail.split('\n')
  let expected = from // the number the first sibling below already carries
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].startsWith(quote)) break
    const body = lines[i].slice(quote.length)
    const m = ORDERED_LINE.exec(body)
    if (m !== null && m[1] === indent && m[3] === delim && Number(m[2]) === expected) {
      lines[i] = quote + indent + `${expected + 1}${delim}` + body.slice(indent.length + m[2].length + 1)
      expected++
      continue
    }
    const deeper = (/^[ \t]*/.exec(body)?.[0].length ?? 0) > indent.length
    if (deeper && body.trim() !== '') continue
    break
  }
  return lines.join('\n')
}

/* ---- links --------------------------------------------------------------- */

/** "Looks like a URL" is deliberately narrow — a scheme with '//', mailto:, or
 *  www. — and never contains whitespace. A false positive puts a person's
 *  prose into a link target where it is invisible; a false negative only
 *  costs them retyping the label. */
const URL_LIKE = /^(?:[a-z][a-z0-9+.-]*:\/\/|mailto:|www\.)[^\s<>]+$/i

/** CommonMark accepts a bare destination only when its parentheses balance;
 *  otherwise the ')' closes the link early. The pointy-bracket form accepts
 *  any parentheses, and URL_LIKE has already excluded '<', '>' and spaces. */
function destination(url: string): string {
  let depth = 0
  for (const ch of url) {
    if (ch === '(') depth++
    else if (ch === ')' && --depth < 0) return `<${url}>`
  }
  return depth === 0 ? url : `<${url}>`
}

export function makeLink(text: string, start: number, end: number): Edit {
  const [s0, e0] = span(text, start, end)
  const [s, e] = trimmed(text, s0, e0)
  const selected = text.slice(s, e)
  const before = text.slice(0, s)
  const after = text.slice(e)

  if (URL_LIKE.test(selected)) {
    // `[](url)`: only the '[' precedes the label, so the caret is s + 1. The
    // label is left empty rather than filled with the URL: a guessed label is
    // a plausible value standing in for one the person has not given.
    return { text: before + '[](' + destination(selected) + ')' + after, start: s + 1, end: s + 1 }
  }

  if (selected === '') {
    // Nothing to be the label or the target; begin with the label, which is
    // what a person reads first.
    return { text: before + '[]()' + after, start: s + 1, end: s + 1 }
  }

  // `[label]()`: the caret goes into the parentheses, after '[' (1), the
  // label, and '](' (2) — all inserted at or after s, all before the caret.
  const caretAt = s + 1 + selected.length + 2
  return { text: before + '[' + selected + ']()' + after, start: caretAt, end: caretAt }
}
