/** CLICKABLE LINKS, AND STATEMENTS LAID OUT TO BE READ (owner ent-0b4f3f69b836).
 *
 *  The owner approved the Magnet and asked for one thing: "Include clickable
 *  links and maybe slightly better formatting for reading". On the deployed
 *  candidate a collected web row led with its held-file key
 *  ("space-missions-and-astronomy-what-launch/a733ec1ec5e51a4b") while the
 *  article's own headline and address sat as plain text inside a 180-character
 *  preview, and a written answer arrived as a stack of one-line paragraphs with
 *  a 200-character address run through the middle of one. This module is the
 *  whole of the fix: where a recorded address is, how it is shown, and how a
 *  recorded statement is laid out.
 *
 *  NO ADDRESS IS INVENTED HERE, and none is fetched. Part W's three web
 *  connectors write the acquired bytes with one header -- the thing's own
 *  headline, a blank line, its permalink, a blank line, then the material
 *  (`mentis/sources/webpages.py` `_page_body`, `mentis/sources/feeds.py`
 *  `_entry_body`). Those bytes ARE the row's captured range, which
 *  `collectionRows` has already verified whole against its recorded digest,
 *  length and citation, so reading the headline and the address back out of
 *  them reports what was recorded. A row whose captured text has no bare
 *  `https://` address where that header puts one is not web-shaped: it gets no
 *  link and keeps exactly the row, title and preview it always had.
 *
 *  NOTHING HERE TOUCHES WHAT IS CLAIMED. An answer's own characters are
 *  rendered as recorded -- split into a statement and its quotation, never
 *  edited -- and grounding, provenance and citations are drawn by their own
 *  components, untouched. Laying a sentence out does not make it say more.
 */
import { createContext, useContext, type ReactNode } from 'react'
import type { RouteResult } from '../../fluid/surface/magnet/route'
import { inline } from '../../prose'
import { DIRECT_CITE_RUN_IN_TEXT, parseCiteRun, type DirectCite } from '../../refid'
import './links.css'

const object = (v: unknown): Record<string, any> =>
  v && typeof v === 'object' && !Array.isArray(v) ? v as Record<string, any> : {}
const isHeldSource = (r: RouteResult) => (r as RouteResult & { via?: string }).via === 'held-source'

/** A line that is nothing but an https address. Only such a line is read as the
 *  header's address: a feed entry with no link of its own writes its summary
 *  where the address would go (`feeds.py _entry_body` appends the link only
 *  `if entry["link"]`), and a summary is not an address. */
const ONLY_ADDRESS = /^https:\/\/\S+$/

export interface HeldHeader {
  /** The thing's own headline, or null where it recorded none. */
  headline: string | null
  /** Its permalink exactly as recorded, or null where the row has no header. */
  link: string | null
  /** The material under the header -- or the whole captured text, unchanged,
   *  for every row that is not web-shaped. */
  body: string
}

/** A feed entry's recorded trailer: a `--` rule, then what the feed stated
 *  about the entry and the provider's terms note (`feeds.py _entry_body`). That
 *  is provenance, not the entry's words, and the surfaces here state their own
 *  provenance; the whole captured range is still shown by the inspection. */
function withoutTrailer(body: string): string {
  const lines = body.split('\n')
  for (let i = 0; i < lines.length; i++)
    if (lines[i].trim() === '--' && /^Published:/.test((lines[i + 1] ?? '').trim()))
      return lines.slice(0, i).join('\n')
  return body
}

/** The header Part W wrote on an acquired web row, read back out of the row's
 *  own verified bytes. `{ headline: null, link: null, body: text }` for
 *  anything else, so a Conversation post, a README, a Git file and a feed entry
 *  with no link of its own are all read exactly as they were before. */
export function heldHeader(text: unknown): HeldHeader {
  const raw = typeof text === 'string' ? text : ''
  const plain: HeldHeader = { headline: null, link: null, body: raw }
  const lines = raw.split('\n')
  if (lines.length < 3 || lines[1].trim()) return plain
  const link = lines[2].trim()
  if (!ONLY_ADDRESS.test(link)) return plain
  // A page with no title of its own has its address written on the headline
  // line instead (`_page_body`: `title or url`), and an address is not a
  // headline -- it is already the link.
  const first = lines[0].trim()
  const headline = first && first !== link && !ONLY_ADDRESS.test(first) ? first : null
  // `_page_body` writes the material directly after the address; `_entry_body`
  // puts a blank line between them. One optional blank line covers both.
  const rest = lines.slice(3)
  if (rest.length && !rest[0].trim()) rest.shift()
  return { headline, link, body: withoutTrailer(rest.join('\n')).trim() }
}

/** One collected row's header, from the text the batch retains for it. Only a
 *  held-source row can carry one: a collected post's words are its parts, and
 *  the batch never captured a page for it. */
export function rowHeader(r: RouteResult): HeldHeader | null {
  if (!r || !isHeldSource(r)) return null
  const text = object(r.value).text
  if (typeof text !== 'string' || !text) return null
  const got = heldHeader(text)
  return got.link ? got : null
}

/** This row's recorded address, or null. The only thing anything here puts in
 *  an `href`. */
export const rowLink = (r: RouteResult): string | null => rowHeader(r)?.link ?? null
/** This row's own headline, or null -- what a row leads with instead of the
 *  held-file key the collection stores it under. */
export const rowHeadline = (r: RouteResult): string | null => rowHeader(r)?.headline ?? null
const squeezed = (words: unknown) => String(words ?? '').toLowerCase().replace(/[^a-z0-9]+/g, '')

/** Whether quoting `words` under `headline` would say the same thing twice.
 *
 *  A news feed commonly records an entry's title as its summary as well: in the
 *  owner's own Magnet almost every row does, so each one showed its headline
 *  and then quoted the headline again under it. The headline IS the row's own
 *  words in that case, said once; the whole captured text is still one press
 *  away in the inspection. This is `perspectives_work._restates`, which makes
 *  the same decision for a written answer. */
export function restates(headline: string | null, words: string): boolean {
  const a = squeezed(headline), b = squeezed(words)
  return !!a && !!b && (a.includes(b) || b.includes(a))
}

/** The material under this row's header, or null where the row has no header
 *  and its captured text is read whole as before. May be `''`: a feed entry
 *  that recorded nothing but its headline, or nothing but its headline said
 *  twice, shows neither a repeated headline nor an empty quotation. */
export const rowBody = (r: RouteResult): string | null => {
  const got = rowHeader(r)
  if (!got) return null
  return restates(got.headline, got.body) ? '' : got.body
}

/** The site a recorded address belongs to, or null. A domain name, which is
 *  what a reader recognises and is not a recorded identity. */
export function linkHost(url: unknown): string | null {
  if (typeof url !== 'string' || !ONLY_ADDRESS.test(url.trim())) return null
  try { return new URL(url.trim()).host.replace(/^www\./, '') || null } catch { return null }
}

/** AN ADDRESS AS A READER WANTS TO SEE IT: the site, and enough of the path to
 *  tell two of them apart. The whole address is the `href` and the `title`, so
 *  nothing is hidden -- what is shortened is the 200 characters of opaque feed
 *  identifier the owner was reading in the middle of a sentence. */
export function shortLink(url: string, most = 48): string {
  const said = typeof url === 'string' ? url.trim() : ''
  let host: string, path: string
  try {
    const u = new URL(said)
    host = u.host.replace(/^www\./, '')
    path = `${u.pathname}${u.search}`.replace(/\/+$/, '')
  } catch {
    return said.length > most ? `${said.slice(0, most - 1)}…` : said
  }
  if (!path) return host
  const whole = `${host}${path}`
  if (whole.length <= most) return whole
  const room = most - host.length - 1
  return room > 1 ? `${host}${path.slice(0, room)}…` : `${host}…`
}

export type Piece = { text: string } | { url: string } | { cites: DirectCite[]; said: string }

/** An https address Mentis wrote into a statement. Bounded away from the
 *  quotation marks the answers are written with (`“ ”`) and from brackets, so
 *  an address at the end of a quoted sentence is found and the quote's own
 *  punctuation is not swallowed. */
const IN_PROSE = /https:\/\/[^\s<>"'“”(){}[\]]+/g

/** The characters one piece stands for -- what makes `linkPieces` lossless
 *  whatever kind of piece it produced. */
export const saidIn = (p: Piece): string => 'url' in p ? p.url : 'cites' in p ? p.said : p.text

/** Addresses and direct citations, in one scan, so neither is found inside the
 *  other's characters. */
const IN_PROSE_OR_CITED = new RegExp(`${DIRECT_CITE_RUN_IN_TEXT.source}|${IN_PROSE.source}`, 'g')

/** A recorded statement split into its words, the addresses in it and the
 *  citations in it. Pure, and lossless: every character of the input comes back
 *  in exactly one piece (`saidIn`). */
export function linkPieces(text: unknown): Piece[] {
  const words = typeof text === 'string' ? text : ''
  const out: Piece[] = []
  let at = 0
  const take = (start: number, piece: Piece, length: number) => {
    if (start > at) out.push({ text: words.slice(at, start) })
    out.push(piece)
    at = start + length
  }
  for (const match of words.matchAll(IN_PROSE_OR_CITED)) {
    const start = match.index ?? 0
    if (start < at) continue
    /* A CITATION IS PROVENANCE, NOT WORDS. Its reference, digest and byte
       range are kept on the piece and never drawn as running text. */
    const cited = parseCiteRun(match[0])
    if (cited.length) { take(start, { cites: cited, said: match[0] }, match[0].length); continue }
    // A full stop, comma or colon after an address belongs to the sentence, not
    // to the address.
    const url = match[0].replace(/[.,;:!?)\]]+$/, '')
    if (url.length <= 'https://'.length) continue
    // AN ADDRESS THAT WAS CUT IS NOT AN ADDRESS. An excerpt bounded at 220
    // characters can end in the middle of one, and an answer recorded before
    // this refinement quoted a whole captured text that way -- the owner's own
    // standing answer holds "https://news.google.com/rss/articles/CBMi0AF…".
    // Making that a link would be a link that does not resolve, so it stays
    // the plain text it is.
    if (url.includes('…')) continue
    take(start, { url }, url.length)
  }
  if (at < words.length) out.push({ text: words.slice(at) })
  return out
}

/* ------------------------------------------------------------------------- *
 * A CITATION AS A READER WANTS ONE (owner `ent-bce57ba67f38`: "Stop
 * presenting ordinary information as forensic evidence. Use natural prose
 * with numbered inline citations [1], [2], etc., and accessible source
 * details. Preserve provenance internally without forcing users to read it.")
 *
 * WHAT WAS WRONG. A recorded answer carries its citations in its own
 * characters, and this renderer recognised bare addresses and nothing else --
 * so `[adm-e3d8cae2cb43@a79673349571[0:7631]]` was drawn as those 38
 * characters, in the middle of the sentence, three or four times a paragraph.
 * The reference, the source digest and the byte range are all true and all
 * provenance: the reader needs to know WHICH SOURCE, which is a title.
 *
 * WHAT IT IS NOW. Each distinct cited record is numbered once, in the order a
 * reader meets it across the whole answer (`citedRefs`), and drawn as that
 * number. The number is a press that opens the captured record inside the
 * card -- where Inspection's own provenance disclosure already holds the
 * origin, version, capture time and bounds -- and the answer carries a
 * Sources list naming each one in words (`SourceNotes`). The whole recorded
 * token stays on the element as `data-cite`, so nothing of the provenance is
 * lost from the surface; it is simply not in the running text.
 *
 * NOTHING IS NUMBERED THAT THE SURFACE CANNOT NAME. Where no index is
 * provided, or the index does not know a reference, the token is drawn as the
 * characters that were recorded -- exactly as before. A number standing for
 * nothing a reader can open would be worse than the token.
 * ------------------------------------------------------------------------- */

/** What a surface must be able to say about a cited record for the number to
 *  stand in for it. Supplied by the view that holds the collection
 *  (`Summary.answerSources`); `null` where this run of text has none. */
export interface CitationIndex {
  /** The recorded row for a publication's literal [n] marker. Older answers
   *  carry direct references instead and do not need this lookup. */
  refOf?(number: number): string | null
  /** The number this record carries in the answer, from 1, or null where the
   *  answer's own sources do not include it. */
  numberOf(ref: string): number | null
  /** What the record is, in words -- the title a reader recognises. */
  nameOf(ref: string): string | null
  /** Open the captured record inside the card. `from` is the element the press
   *  came from, so closing returns the reader to the citation they pressed. */
  open(ref: string, from?: string): void
}

export const Citations = createContext<CitationIndex | null>(null)

/** The records a run of recorded texts cites, each once, in the order a reader
 *  meets them. The answer-wide order: the same record cited in the first and
 *  the fourth statement is `[1]` in both. */
export function citedRefs(texts: string[]): string[] {
  const out: string[] = [], seen = new Set<string>()
  for (const said of texts)
    for (const m of String(said ?? '').matchAll(DIRECT_CITE_RUN_IN_TEXT))
      for (const cited of parseCiteRun(m[0])) {
        if (seen.has(cited.ref)) continue
        seen.add(cited.ref)
        out.push(cited.ref)
      }
  return out
}

/** ONE RUN OF CITATIONS, drawn as its numbers -- or the characters that were
 *  recorded, where this surface cannot number them. The index is the one
 *  around this text (`Citations`), or the one the caller names: `citedInline`
 *  hands prose its own, because it has already decided with it which runs it
 *  is replacing. */
export function Cite({ cites, said, index: named }:
  { cites: { ref: string }[]; said: string; index?: CitationIndex | null }) {
  const around = useContext(Citations)
  const index = named ?? around
  const numbers = index ? cites.map((c) => index.numberOf(c.ref)) : []
  if (!index || numbers.some((n) => n === null)) return <>{said}</>
  return <span className="q2-magnet-cites" data-cite={said}>{cites.map((c, i) => {
    const n = numbers[i] as number
    const name = index.nameOf(c.ref)
    return <button key={c.ref} type="button" className="q2-magnet-cite"
      id={`cite-mark-${n}`} aria-label={`Source ${n}${name ? `: ${name}` : ''}`}
      title={name ? `Source ${n}: ${name}` : `Source ${n}`}
      onClick={() => index.open(c.ref, `cite-mark-${n}`)}>[{n}]</button>
  })}</span>
}

/** `inline`, with every direct citation drawn as its number instead of as its
 *  recorded characters. Handed to `Prose` as `inlineOf`, so a written briefing
 *  keeps the one Markdown renderer Fluid has and gains nothing but readable
 *  citations. The extracted citation form is untouched: `inline` already draws
 *  it as its own chip, and the two shapes cannot match each other. */
export function citedInline(index: CitationIndex | null): (src: string, key: string) => ReactNode[] {
  if (!index) return inline
  return (src, key) => {
    const out: ReactNode[] = []
    let at = 0, n = 0
    const runs: { start: number; said: string; cites: { ref: string }[] }[] = []
    for (const m of src.matchAll(DIRECT_CITE_RUN_IN_TEXT)) {
      const cited = parseCiteRun(m[0])
      if (!cited.length || cited.some((c) => index.numberOf(c.ref) === null)) continue
      runs.push({ start: m.index ?? 0, said: m[0], cites: cited })
    }
    for (const m of src.matchAll(/(?<!\\)\[([1-9]\d*)\](?![\[(])/g)) {
      const ref = index.refOf?.(Number(m[1]))
      if (ref && index.numberOf(ref) === Number(m[1]))
        runs.push({ start: m.index ?? 0, said: m[0], cites: [{ ref }] })
    }
    runs.sort((a, b) => a.start - b.start)
    // A code span containing only a known citation is a citation wrapper.
    // Keep the token on Cite unchanged; consume only its balanced delimiters.
    // Citations inside ordinary inline code belong to that code instead.
    const code = [...src.matchAll(/(?<![\\`])(`+)([^`]+)\1(?!`)/g)].map((m) => ({
      start: m.index ?? 0, end: (m.index ?? 0) + m[0].length, ticks: m[1].length,
    }))
    for (const run of runs) {
      let start = run.start, end = start + run.said.length
      const span = code.find((c) => start >= c.start && end <= c.end)
      if (span) {
        if (start !== span.start + span.ticks || end !== span.end - span.ticks) continue
        start = span.start
        end = span.end
      }
      if (start < at) continue
      if (start > at) out.push(...inline(src.slice(at, start), `${key}-p${n}`))
      out.push(<Cite key={`${key}-c${n++}`} cites={run.cites} said={run.said} index={index} />)
      at = end
    }
    if (at < src.length) out.push(...inline(src.slice(at), `${key}-p${n}`))
    return out
  }
}

/** WHAT EACH NUMBER STANDS FOR, as a list under the answer: the number, the
 *  record's own title, and the accessible detail (what it came from, when it
 *  was captured). Pressing one opens the captured record, which is where the
 *  exact reference, digest and bounds are already disclosed. */
export interface SourceNote {
  n: number
  ref: string
  title: string
  detail: string
  /** Null where the collection shown does not hold the record, which is said
   *  rather than guessed at. */
  open: (() => void) | null
}
export const SOURCES_HEADING = 'Sources'
export function SourceNotes({ notes }: { notes: SourceNote[] }) {
  if (!notes.length) return null
  return <div className="q2-magnet-sources">
    <div className="mgd-eyebrow">{SOURCES_HEADING}</div>
    <ol className="q2-magnet-source-list" aria-label="Sources this answer cites">
      {notes.map((s) => <li key={s.ref} value={s.n}>
        {s.open
          ? <button type="button" className="mgd-link" id={`cite-source-${s.n}`} onClick={s.open}>{s.title}</button>
          : <span>{s.title}</span>}
        <span className="mgd-subtle"> · {s.detail}</span>
      </li>)}
    </ol>
  </div>
}

export interface Statement {
  /** What the statement says. */
  lead: string
  /** The record's own words it quoted, without the quotation marks, or null
   *  where the statement is not of that recorded shape. */
  quote: string | null
}

/** A RECORDED STATEMENT, LAID OUT RATHER THAN RE-WRITTEN.
 *
 *  Mentis writes a statement about the collection and then quotes the record it
 *  was written from, in one line: `<what it says>: “<the record's own words>”`
 *  (`mentis/magnet/perspectives_work.py`). As one paragraph that is a wall;
 *  told apart it is a statement with its quotation under it. The characters are
 *  the recorded ones either way -- this splits, it never edits -- and a
 *  statement not of that shape comes back whole, as one paragraph, as before. */
export function statement(line: unknown): Statement {
  const said = typeof line === 'string' ? line : ''
  if (!said.endsWith('”')) return { lead: said, quote: null }
  const at = said.indexOf(': “')
  if (at <= 0) return { lead: said, quote: null }
  const lead = said.slice(0, at), quote = said.slice(at + ': “'.length, -1)
  return lead.trim() && quote.trim() ? { lead, quote } : { lead: said, quote: null }
}

/** Words with their addresses as links and their citations as numbers. Only an
 *  `https://` match from the text itself ever reaches an `href`, so no other
 *  scheme can be written into one. */
export function Linked({ text }: { text: string }) {
  return <>{linkPieces(text).map((piece, i) => 'url' in piece
    ? <a key={`l${i}`} className="q2-magnet-url" href={piece.url} title={piece.url}
      target="_blank" rel="noopener noreferrer">{shortLink(piece.url)}</a>
    : 'cites' in piece
      ? <Cite key={`c${i}`} cites={piece.cites} said={piece.said} />
      : <span key={`t${i}`}>{piece.text}</span>)}</>
}

/** One statement of a recorded answer: what it says, then the record's own
 *  words under it. `lead` marks the answer's opening statement, which the
 *  Summary sets in its lead type. */
export function AnswerStatement({ line, lead }: { line: string; lead?: boolean }) {
  const said = statement(line)
  return <div className="q2-magnet-statement">
    <p className={`mgd-p${lead ? ' q2-magnet-lead' : ''}`}><Linked text={said.lead} /></p>
    {said.quote !== null && <p className="q2-magnet-said">“<Linked text={said.quote} />”</p>}
  </div>
}

/** A COLLECTED ROW'S OWN ADDRESS, as a link the reader can follow.
 *
 *  Drawn beside the row rather than inside it: the row itself is a button that
 *  opens the record in the card, and a link inside a button is neither valid
 *  nor pressable. So the reader gets both -- the row opens what was captured,
 *  the link goes to the thing itself. */
export function SourceLink({ url, label }: { url: string; label?: string }) {
  // A FEED PERMALINK IS NOT WORTH READING. `news.google.com/rss/articles/
  // CBMiT0FVX3lxTE45Yy…` told the owner nothing the byline above it had not;
  // where the address has a host, the link says where it goes and the whole
  // address is its `title` and its `href`.
  const host = linkHost(url)
  return <a className="q2-magnet-row-link mgd-small" href={url} title={url}
    target="_blank" rel="noopener noreferrer">{label ?? (host ? `Open at ${host}` : shortLink(url))} ↗</a>
}
