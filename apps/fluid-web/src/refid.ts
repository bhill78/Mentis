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

/** AN ADMISSION NAMED EXACTLY, and only that: `adm-` and twelve hex digits,
 *  with nothing else in the token. A destination somebody typed earns an
 *  artifact action at this exactness and no other -- not `adm-1234`, not
 *  `adm-…` with a path or a query after it, not a Windows path that happens
 *  to hold a reference. What the record then says that Admission is, and
 *  whether its bytes are held, is still the record's answer. */
export const ADMISSION_REF = /^adm-[0-9a-f]{12}$/

export const isAdmissionRef = (s: string): boolean => ADMISSION_REF.test(s)

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

/* A DIRECT CITATION OF CAPTURED BYTES, whole:
 *
 *   adm-<hex>@<source12>[<start>:<end>]
 *
 * The other shape `mentis.sources.extract.cite` writes -- the same held
 * reference and source digest, with the captured byte range and no extractor.
 * It was left as plain text ON PURPOSE while nothing could draw it, and the
 * owner read the consequence in the middle of a sentence
 * (`ent-bce57ba67f38`): "The collection combines
 * [adm-e3d8cae2cb43@a79673349571[0:7631]] and ...". A reference, a digest and
 * a byte range are provenance; they are not what the sentence says.
 *
 * SHAPE ONLY, like everything else here. What the record holds for that
 * reference, and whether the surface showing it has the row, is the record's
 * answer -- this says a token has the shape and nothing more.
 *
 * DISJOINT FROM THE EXTRACTED FORM by construction: the bracket must follow
 * the twelve digest digits immediately, where an extracted citation has `~`
 * and its extractor. So neither recogniser can take the other's token, and
 * the extracted form keeps exactly the chip and the text it already had. */
const DIRECT_BODY = String.raw`adm-[0-9a-f]{8,}@[0-9a-f]{12}\[` + NUM + ':' + NUM + String.raw`\]`

/** A direct citation in running text -- WITH the square brackets an agent
 *  wrote around it where it wrote them, so what replaces the token is not
 *  drawn inside a second pair (`[[1]]`). The bracketed alternative is first,
 *  so it wins over the bare one at the same place. */
export const DIRECT_CITE_IN_TEXT = new RegExp(
  String.raw`(?<![\w/-])\[` + DIRECT_BODY + String.raw`\]|(?<![\w/-])` + DIRECT_BODY, 'g')

export interface DirectCite {
  ref: string
  source12: string
  start: number
  end: number
  /** The captured characters this citation stands for, exactly as the author
   *  wrote them -- the brackets around it included. Kept so provenance can be
   *  carried on the element that replaces it, never shown as running text. */
  said: string
}

/** One direct citation, parsed. Accepts the bracketed form as written: an
 *  agent's `[adm-…@…[0:7631]]` is that citation, not a reference inside a
 *  link. `null` for anything else, and for a range that ends where it starts
 *  or earlier -- which is not a range. */
export function parseDirectCite(s: string): DirectCite | null {
  const said = typeof s === 'string' ? s : ''
  const bare = /^\[(adm-.*\])\]$/.exec(said)?.[1] ?? said
  const m = new RegExp(String.raw`^(adm-[0-9a-f]{8,})@([0-9a-f]{12})\[(` + NUM + '):(' + NUM + String.raw`)\]$`).exec(bare)
  if (!m || Number(m[4]) <= Number(m[3])) return null
  return { ref: m[1], source12: m[2], start: Number(m[3]), end: Number(m[4]), said }
}
