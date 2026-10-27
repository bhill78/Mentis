/* ------------------------------------------------------------------------ *
 * THE `@` AND `#` TRIGGER ENGINE.
 *
 * The composer is a plain textarea, and it stays one: the owner types, and
 * the picker is an offer layered over what they type, never a mode they are
 * put into. So everything here is a pure function of (text, caret). There is
 * no "open" flag held anywhere — whether a trigger is open is re-derived from
 * the text on every keystroke, which means a paste, an undo, a click into
 * the middle of an old mention, or a deletion can never leave the picker
 * believing something the text no longer says.
 *
 * Indices are UTF-16 code units throughout, because that is what
 * `selectionStart` and `String.prototype.slice` speak. Converting to code
 * points here would only mean converting back at the textarea.
 *
 * No imports and no React, deliberately: this is the part that has to be
 * right, so it is the part that must be testable without a DOM.
 * ------------------------------------------------------------------------ */

export interface Trigger {
  sigil: '@' | '#' | '/'
  /** index of the sigil character in the text */
  start: number
  /** index just past the last query character (usually the caret) */
  end: number
  /** what has been typed after the sigil, possibly '' */
  query: string
}

/* Whitespace is the only thing that ends a query. Punctuation does not,
 * because the things being named — people, topics — have names with dots,
 * hyphens and apostrophes in them, and cutting the query at the first `.`
 * would make them unreachable by typing. `\s` rather than `' '` because a
 * newline or a tab closes a trigger just as surely as a space does; the
 * owner who presses Enter after `@Ada` has finished that word. */
const WHITESPACE = /\s/

function isSpace(ch: string): boolean {
  return WHITESPACE.test(ch)
}

function isSigil(ch: string): ch is Trigger['sigil'] {
  return ch === '@' || ch === '#' || ch === '/'
}

/* A Topic is a NOUN PHRASE and a person is a handle, and the grammar has to
 * admit the difference. `@Ada` is one word by construction. "Instrumentation
 * drift" is two, and a composer that stopped the query at the first space
 * could only ever offer to make Topics with one-word names -- which is not a
 * restriction anybody would accept if it were stated out loud, so it must not
 * be imposed quietly by a parser.
 *
 * A phrase therefore runs across single spaces, and ends at the things that
 * genuinely end a name: a line break, a double space (how a person says "I
 * have finished that word"), sentence punctuation, or a length past which
 * this has stopped being a name and become prose. None of those is a guess
 * about meaning; each is a mark the writer actually made.
 */
const PHRASE_ENDS = /[,.;:!?]/
const PHRASE_MAX = 60

/** What the caret is currently inside, or null.
 *
 *  `phrase` lists the sigils whose query may contain single spaces. It is a
 *  parameter rather than a rule about `#` so that this stays a statement
 *  about grammar and not about what the application happens to name things.
 */
export function triggerAt(text: string, caret: number, phrase = '#'): Trigger | null {
  /* A caret outside the text is a caller's bug, not a position. Answering
   * null rather than clamping keeps a stale caret from quietly opening a
   * picker against text it was never measured in. */
  if (!Number.isInteger(caret) || caret < 0 || caret > text.length) return null

  /* A trigger never spans lines, so nothing before this line can open one. */
  const lineStart = caret === 0 ? 0 : text.lastIndexOf('\n', caret - 1) + 1

  /* The nearest sigil at or before the caret that opens legitimately: at the
   * start of the line, or after whitespace. Anything else has a character
   * jammed against it, which is the `a@b` and `ada@example.org` case that
   * must never open anything. Searching backwards rather than walking one
   * word back is what lets a phrase reach across the spaces inside it. */
  let start = -1
  for (let i = caret - 1; i >= lineStart; i--) {
    if (!isSigil(text[i])) continue
    if (i > lineStart && !isSpace(text[i - 1])) continue
    if (text[i] === '/' && (text[i + 1] === '/' || (i > lineStart && text[i - 1] === '/'))) continue
    start = i
    break
  }
  if (start < 0) return null

  const sigil = text[start] as Trigger['sigil']
  const spacey = phrase.includes(sigil)

  /* How far the query runs forward. For a handle that is the rest of the
   * word; for a phrase it is the rest of the name. Running to the END of the
   * run rather than stopping at the caret is deliberate: clicking back into
   * the middle of `@Ada` means the query is the whole word, or completing
   * would leave the tail stranded after the inserted name. */
  let end = start + 1
  while (end < text.length) {
    const ch = text[end]
    if (ch === '\n') break
    if (isSpace(ch)) {
      if (!spacey) break
      // A double space is how somebody says they have finished the word.
      if (isSpace(text[end + 1] ?? '')) break
    }
    if (spacey && (PHRASE_ENDS.test(ch) || end - start > PHRASE_MAX)) break
    end++
  }

  /* The caret has to be INSIDE what was found. Sitting just before the sigil
   * is not inside anything -- typing there would push the sigil along rather
   * than extend a query -- and sitting past the end means the token was
   * closed by whatever ended it. */
  if (caret <= start || caret > end) return null

  return { sigil, start, end, query: text.slice(start + 1, end) }
}

/** Replace the trigger's span with `insert`, returning the new text and where
 *  the caret should now sit. */
export function completeTrigger(
  text: string, t: Trigger, insert: string
): { text: string; caret: number } {
  /* A Trigger is a measurement of one particular text. If the text has moved
   * on since — another keystroke, a paste landing before the picker's
   * selection — then its indices point at somebody else's characters, and
   * splicing there would silently rewrite what the owner wrote. Refusing
   * loudly is the only safe answer; the caller should re-derive with
   * `triggerAt` and try again. */
  if (
    !Number.isInteger(t.start) || !Number.isInteger(t.end) ||
    t.start < 0 || t.end > text.length || t.start >= t.end ||
    text[t.start] !== t.sigil ||
    text.slice(t.start + 1, t.end) !== t.query
  ) {
    throw new RangeError('completeTrigger: trigger does not describe this text')
  }

  /* The whole span, sigil included, is replaced, so the caller decides what
   * the finished token looks like (`@Ada Lovelace`, a reference, anything):
   * this engine knows where the trigger is, not how a completed one is
   * spelled.
   *
   * Exactly one space follows, always. It closes the trigger — by rule 2 the
   * caret after a space is inside nothing, so the picker falls away on its
   * own without a separate "dismiss" state — and it puts the caret where the
   * owner's next word goes, so they never have to type a space the machine
   * could have typed for them. It is appended unconditionally even when the
   * text already continues with whitespace: predictable over clever. */
  const inserted = insert + ' '
  return {
    text: text.slice(0, t.start) + inserted + text.slice(t.end),
    caret: t.start + inserted.length,
  }
}

/* ---- `//`: a path on this machine (Scratch only) ------------------------- *
 *
 * A PATH IS NEITHER A HANDLE NOR A PHRASE. It runs to the next whitespace
 * (`//C:\Work\notes`), and a path with spaces in it is written quoted
 * (`//"C:\Program Files\x"`), so the sentence after it is never read as part
 * of a folder name.
 *
 * URL-SAFE BY THE SAME RULE AS `@`: `//` opens only where it STARTS a word --
 * at the start of a line or after whitespace. So `https://`, `http://`,
 * `file://` and `a//b` never open anything, typed or pasted: the `//` in each
 * has a character jammed against it.
 * ------------------------------------------------------------------------ */

export interface PathTrigger {
  /** index of the first `/` */
  start: number
  /** index just past the token (past the closing quote, where there is one) */
  end: number
  /** the path typed so far, without `//` or quotes */
  query: string
  quoted: boolean
}

export function pathTriggerAt(text: string, caret: number): PathTrigger | null {
  if (!Number.isInteger(caret) || caret < 0 || caret > text.length) return null
  const lineStart = caret === 0 ? 0 : text.lastIndexOf('\n', caret - 1) + 1
  let lineEnd = text.indexOf('\n', caret)
  if (lineEnd < 0) lineEnd = text.length
  for (let i = caret - 2; i >= lineStart; i--) {
    if (text[i] !== '/' || text[i + 1] !== '/') continue
    if (i > lineStart && !isSpace(text[i - 1])) continue
    /* ONLY WHAT LOOKS LIKE A PATH. `//` is also how JavaScript, C and C++
       start a comment, so `//`, `// note`, `//TODO` and
       `//eslint-disable-next-line` must stay text: the selector opens only
       once what follows `//` is a drive WITH ITS SEPARATOR (`C:\` or `C:/`
       -- `//C:` alone is comment shorthand like `//Q: why?`), the same
       quoted (`//"C:\`), or a root backslash (`//\`). Forward slashes after
       the drive (`//C:/Work`) are accepted as typed and listed as that
       folder. */
    if (!/^(?:"?[A-Za-z]:[\\/]|\\)/.test(text.slice(i + 2, i + 6))) continue
    const quoted = text[i + 2] === '"'
    let end: number
    let query: string
    if (quoted) {
      const close = text.indexOf('"', i + 3)
      end = close >= 0 && close < lineEnd ? close + 1 : lineEnd
      query = text.slice(i + 3, close >= 0 && close < lineEnd ? close : lineEnd)
      // The caret may sit just before the closing quote, inside the path.
      if (caret >= i + 3 && caret <= end) return { start: i, end, query, quoted }
    } else {
      end = i + 2
      while (end < lineEnd && !isSpace(text[end])) end++
      query = text.slice(i + 2, end)
      if (caret >= i + 2 && caret <= end) return { start: i, end, query, quoted }
    }
  }
  return null
}

/** How a path is written back into the question: `//path`, quoted when it
 *  has whitespace in it. `open` leaves the caret INSIDE the token (before a
 *  closing quote), so the selector stays open on the folder just entered;
 *  otherwise one space follows and closes it, as a finished `@` does. */
export function writePath(
  text: string, t: PathTrigger, path: string, open: boolean,
): { text: string; caret: number } {
  const quote = /\s/.test(path)
  const token = '//' + (quote ? `"${path}"` : path)
  const insert = open ? token : token + ' '
  const caret = t.start + (open && quote ? token.length - 1 : insert.length)
  return { text: text.slice(0, t.start) + insert + text.slice(t.end), caret }
}

/* ---- scoring ------------------------------------------------------------ *
 * The returned number is a RANK, not a measurement. There are three tiers
 * and they are the only numbers this function ever returns:
 *
 *   PREFIX      the candidate begins with the query — the owner is typing
 *               the name from its start, the strongest signal there is;
 *   WORD_START  the query begins some later word — `love` for
 *               `Ada Lovelace`, or `lace` for `adaLovelace`;
 *   SUBSTRING   the query appears somewhere, mid-word.
 *
 * There is deliberately no finer grading within a tier (no bonus for
 * earlier position, shorter candidate, closer length). Nothing in the record
 * says that `Ada` is a better answer than `Adam` to `ad`, and inventing a
 * decimal to decide it would be manufacturing a preference. Candidates that
 * tie keep whatever order the caller had them in — which should be an order
 * the record actually carries — so sort stably.
 * ------------------------------------------------------------------------ */

const PREFIX = 0
const WORD_START = 1
const SUBSTRING = 2

/* NFC so that `é` typed as one code point matches `é` stored as `e` plus a
 * combining accent; the owner cannot see the difference and must not be
 * punished for it. Lower-casing makes the match case-insensitive, because
 * nobody types capitals to summon a name. */
function fold(s: string): string {
  return s.normalize('NFC').toLowerCase()
}

const ALNUM = /[\p{L}\p{N}]/u
const LOWER = /\p{Ll}/u
const UPPER = /\p{Lu}/u

/* A word starts after anything that is not a letter or digit (space, `-`,
 * `_`, `.`, `/`) and also at a lower-to-upper step, because identifiers like
 * `adaLovelace` are words run together and the owner will type the second
 * one. Judged on the ORIGINAL candidate: folding throws case away, and case
 * is the only evidence of a camelCase boundary. */
function isWordStart(prev: string, cur: string): boolean {
  return !ALNUM.test(prev) || (LOWER.test(prev) && UPPER.test(cur))
}

/** Case- and position-insensitive scoring for the picker. Returns null when
 *  the candidate does not match at all, else a number where LOWER is a better
 *  match. Must rank a prefix match above a word-start match above a mere
 *  substring. */
export function score(candidate: string, query: string): number | null {
  const q = fold(query)
  const c = fold(candidate)

  /* An empty query is the owner having typed only the sigil. Everything is
   * a candidate and nothing is preferred, so everything ties at the top tier
   * and the caller's own order stands. It is not a non-match. */
  if (c.startsWith(q)) return PREFIX

  /* Absent is not Poor. A non-match is null, never a large number, so that
   * a caller cannot accidentally sort a non-match to the bottom of the list
   * and show it; it has to decide, explicitly, to leave it out. */
  if (!c.includes(q)) return null

  /* Walk the candidate by code point (so a surrogate pair is never split into
   * a fake boundary) and test the query at each word start. Each slice is
   * folded on its own rather than indexing into `c`, because lower-casing
   * can change length (`İ` becomes two code units) and an index into the
   * folded string would not be an index into the original. */
  const src = candidate.normalize('NFC')
  let prev = ''
  let i = 0
  for (const cur of src) {
    if (i > 0 && isWordStart(prev, cur) && fold(src.slice(i)).startsWith(q)) {
      return WORD_START
    }
    prev = cur
    i += cur.length
  }

  return SUBSTRING
}
