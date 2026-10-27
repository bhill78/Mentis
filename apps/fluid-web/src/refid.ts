/* ------------------------------------------------------------------------ *
 * WHAT A RECORD REFERENCE LOOKS LIKE WHEN SOMEBODY TYPED IT.
 *
 * Agents name the record by its references — "the Finding `ent-de912abf1e41`"
 * — and until now that text was inert: the owner was told something was
 * theirs to establish and had no way to get to it. This is the one place that
 * says what a typed reference is, so prose and anything else that reads text
 * agree about it.
 *
 * SHAPE ONLY. It says a token has the shape the spine writes (`ent-`,
 * `opr-` or `adm-` and hex) and nothing about what it refers to — whether the record
 * holds it, and what it is, is answered by the record when somebody asks.
 * ------------------------------------------------------------------------ */

/** The whole of a token, as the spine writes an entry, an operational id,
 *  or an Admission. `adm-` joined for acquired source material (Sources
 *  slice 1, U9): a reference to one observation, pinned, which the record
 *  explains as what it is -- an acquired observation, or another held
 *  artifact. */
export const REF_ID = /^(?:ent|opr|adm)-[0-9a-f]{8,}$/

/** Finds references inside running text. Bounded so that a reference
 *  embedded in a longer word or path is not torn out of it. */
export const REF_IN_TEXT = /(?<![\w/-])(?:ent|opr|adm)-[0-9a-f]{8,}(?![\w-])/g

export const isRefId = (s: string): boolean => REF_ID.test(s)

/** Where a reference sits in a piece of text, in order. */
export const refsIn = (src: string): { id: string; at: number }[] =>
  [...src.matchAll(REF_IN_TEXT)].map((m) => ({ id: m[0], at: m.index ?? 0 }))

/* A CITATION OF EXTRACTED TEXT (Sources C, C1.5), whole:
 *
 *   adm-<hex>@<src12>~<name@version+hash12>/<rep12>[<start>:<end>]{<scheme>:<token>}
 *
 * The same shape `mentis.sources.extract.cite` writes and parses. Only the
 * extracted form is matched here: a direct citation (`adm-…@d12[s:e]`, no
 * `~`) is left exactly as before -- an `adm-` chip and its text. */
const XID = String.raw`[a-z0-9][a-z0-9.-]*@[0-9A-Za-z][0-9A-Za-z.-]*\+[0-9a-f]{12}`
const NUM = String.raw`(?:0|[1-9][0-9]*)`
const CITE_BODY =
  String.raw`(adm-[0-9a-f]{8,})@([0-9a-f]{12})~(` +
  XID +
  String.raw`)\/([0-9a-f]{12})\[(` +
  NUM +
  String.raw`):(` +
  NUM +
  String.raw`)\]\{([a-z0-9][a-z0-9.-]*\/[0-9]+):([^\s{}]+)\}`

export const CITE_IN_TEXT = new RegExp(String.raw`(?<![\w/-])` + CITE_BODY, 'g')

export interface ExtractedCite {
  ref: string
  source12: string
  extractor_id: string
  representation12: string
  start: number
  end: number
  scheme: string
  token: string
}

export function parseExtractedCite(s: string): ExtractedCite | null {
  const m = new RegExp('^' + CITE_BODY + '$').exec(s)
  if (!m || Number(m[6]) <= Number(m[5])) return null
  return {
    ref: m[1],
    source12: m[2],
    extractor_id: m[3],
    representation12: m[4],
    start: Number(m[5]),
    end: Number(m[6]),
    scheme: m[7],
    token: m[8],
  }
}
