/* FOCUS SEARCH: WHAT A QUERY IS (search-in/, the approved assignment's 1).
 *
 * A query compiled once and run over as many texts as a section holds. Pure:
 * no DOM, no React, so the client tests hold it in Node and the walker
 * (highlight.ts) is the only part that knows what a Text node is.
 *
 * LITERAL BY DEFAULT. What is typed is looked for exactly -- a reader who
 * writes `v1.2 (draft)` means those characters, not a pattern -- so every
 * regex metacharacter in the input is escaped unless the `.*` toggle asked
 * for a pattern. A pattern that does not compile is an answer, not an
 * exception: `compile` returns `{ error }` and the bar says why.
 *
 * Two bounds keep a search a reading aid and never a burden: a match of
 * zero length (an `a*` that matches everywhere) is skipped, and no text
 * yields more than MAX_MATCHES matches. */

export interface Matcher {
  /** the pattern actually run (a literal query is its escaped self) */
  readonly source: string
  readonly regex: boolean
  readonly caseSensitive: boolean
  /** the compiled expression, `g` (and `i` unless case-sensitive) */
  readonly re: RegExp
}

/** The most matches one text will yield; the bar says "2000+" by capping. */
export const MAX_MATCHES = 2000

/* Every character that means something to a RegExp, so a literal query means
   exactly what was typed. */
const METACHAR = /[.*+?^${}()|[\]\\]/g

/** Compile `query` into a Matcher, or say why the pattern is not one. */
export function compile(query: string, opts: { regex?: boolean; caseSensitive?: boolean } = {}): Matcher | { error: string } {
  const source = opts.regex ? query : query.replace(METACHAR, '\\$&')
  let re: RegExp
  try {
    re = new RegExp(source, opts.caseSensitive ? 'g' : 'gi')
  } catch (e) {
    return { error: (e as Error)?.message || String(e) }
  }
  return { source, regex: !!opts.regex, caseSensitive: !!opts.caseSensitive, re }
}

/** Whether any of `texts` holds a match (what is not drawn, asked of its
 *  source: Zones.tsx's slides not shown). */
export function anyIn(texts: (string | null | undefined)[], m: Matcher): boolean {
  return texts.some((t) => !!t && findIn(t, m).length > 0)
}

/** Every match of `m` in `text`, in order, none of them empty, at most
 *  MAX_MATCHES. The same Matcher may be run over any number of texts: the
 *  expression's cursor is rewound first. */
export function findIn(text: string, m: Matcher): { start: number; end: number }[] {
  const out: { start: number; end: number }[] = []
  if (!m.source) return out
  const re = m.re
  re.lastIndex = 0
  for (;;) {
    const hit = re.exec(text)
    if (!hit) break
    if (hit[0].length > 0) {
      out.push({ start: hit.index, end: hit.index + hit[0].length })
      if (out.length >= MAX_MATCHES) break
    } else if (re.lastIndex === hit.index) {
      /* a zero-length match does not move the cursor itself */
      re.lastIndex = hit.index + 1
    }
  }
  return out
}
