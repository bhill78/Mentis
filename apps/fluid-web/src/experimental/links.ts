import type { Block } from '../blocks'

/* ------------------------------------------------------------------------ *
 * THE LINKS A POST MAKES, READ WITHOUT A BROWSER (Fluid, B5/B6).
 *
 * PURE: no React, no DOM, and no `URL` global. The server runs this file in
 * its embedded engine (QuickJS, through dist/render-check.js and
 * ./postobjects.ts), which has no `URL` and no `URLSearchParams`, and the
 * Fluid client imports the same functions. So a link is read here with a
 * small parser of its own that accepts LESS than the browser's: anything it
 * is not sure of is no link object at all (the words still link in the post,
 * as prose.tsx draws them). Where a browser is at hand the href a reader can
 * follow is still decided by `safeHref`, with the browser's own parser.
 *
 * NOTHING IS FETCHED. A link object is what the post says: the words its
 * author put around it and the domain it names.
 *
 * THE COPIES FROM prose.tsx. `safeHref`, `URL_TOKEN`, `TRAILING`, `MD_LINK`
 * and `readable` are prose.tsx's, character for character, and
 * tests/fluid_links_unit.ts holds them equal. They are copied rather than
 * moved: moving them out of prose.tsx changes production's built chunks
 * (measured: Use-*.js and main-*.js both change), and production must stay
 * byte-identical. Fluid and the server read this copy; production reads its
 * own.
 *
 * WHY NOT THE BLOCK READER. `linksOf` reads the prose itself rather than
 * through ../blocks.ts `placedIn`: the Fluid page asking production's shared
 * chunk for `placedIn` (or, through a copy of its own, for the `RENDERABLE`
 * that ../blocks.ts reads) renames that chunk's exports, which changes
 * production's built files (measured both ways). So the one thing that
 * matters for links -- that nothing inside a code fence or inline code is
 * a link -- is decided here with the block reader's own fence rule, copied;
 * tests/fluid_links_unit.ts holds `linksOf` equal to the same reading done
 * through `placedIn` and `readable`, over every post of a copy of the
 * owner's Brain.
 * ------------------------------------------------------------------------ */

/* WHERE A LINK IN A BODY IS ALLOWED TO GO (prose.tsx's rule, copied): the
   destination parsed by the browser's URL parser with NO base, one of three
   schemes, and the href is the parsed URL, never the string checked.
   BROWSER ONLY: it needs `URL`. */
const LINK_SCHEMES = new Set(['http:', 'https:', 'mailto:'])

/** The absolute URL a link may point to, or null. */
export function safeHref(raw: string): string | null {
  let u: URL
  try {
    u = new URL(raw)
  } catch {
    return null
  }
  return LINK_SCHEMES.has(u.protocol) ? u.href : null
}

/** A bare URL in prose (prose.tsx's). Trailing sentence punctuation is
 *  trimmed after, with TRAILING. */
export const URL_TOKEN = /https?:\/\/[^\s<>"'`]+/g
export const TRAILING = /[.,;:!?'")\]}]+$/
export const MD_LINK = /\[([^\]]*)\]\(([^)\s]+)\)/g

/** The texts inside a block that a reader reads as prose, in reading order
 *  (prose.tsx's). A code fence and a rule have none. */
export function readable(b: Block): string[] {
  switch (b.kind) {
    case 'para':
    case 'quote':
    case 'heading':
      return [b.text]
    case 'list':
      return b.items
    case 'table':
      return [...b.head, ...b.rows.flat()]
    default:
      return []
  }
}

/* -- an http(s) URL, read without `URL` --------------------------------------- */

export interface HttpUrl {
  scheme: 'http' | 'https'
  /** lower case, as the browser reads it; never empty */
  host: string
  port: string | null
  /** as written, '' or beginning with '/' */
  path: string
  /** as written, '' or beginning with '?' */
  query: string
}

const SHAPE = /^(https?):\/\/([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$/i
const HOST = /^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*\.?$/
const IP6 = /^\[[0-9a-f:.]+\]$/

/** An absolute http or https URL, or null for anything this reader is not
 *  sure the browser reads the same way: whitespace or control characters,
 *  a backslash, credentials (`user@host`, the lookalike trick), a host that
 *  is not plain ASCII letters, digits, dots and hyphens, or a bad port. */
export function parseHttp(raw: string): HttpUrl | null {
  if (!raw || raw.length > 2048 || /[\u0000- \u007f\\]/.test(raw)) return null
  const m = SHAPE.exec(raw)
  if (!m) return null
  const authority = m[2]
  if (authority.includes('@')) return null
  const at = /^(.*?)(?::(\d*))?$/.exec(authority)!
  const host = at[1].toLowerCase()
  if (!host || !(HOST.test(host) || IP6.test(host))) return null
  /* A host whose last label is a number is an IPv4 address to the browser,
     read in ways a reader would not guess (`1.2.3`, `010.0.0.1` in octal,
     `0x7f.1`): only a plain dotted quad is taken. */
  const labels = host.replace(/\.$/, '').split('.')
  if (/^(\d+|0x[0-9a-f]*)$/.test(labels[labels.length - 1])
      && !(labels.length === 4 && labels.every((l) => /^(0|[1-9]\d{0,2})$/.test(l) && Number(l) <= 255))) return null
  const port = at[2] ? at[2] : null
  if (port !== null && (port.length > 5 || Number(port) > 65535)) return null
  return { scheme: m[1].toLowerCase() as 'http' | 'https', host, port, path: m[3], query: m[4] ?? '' }
}

/** The domain a link names, as a reader recognises it: its host without a
 *  leading `www.` or a trailing dot. */
export const domainOf = (u: HttpUrl) => u.host.replace(/^www\./, '').replace(/\.$/, '')

/* -- one YouTube video (prose.tsx `youtubeId`'s rule, without `URL`) ---------- */

/** Exact hosts, as prose.tsx's YT_HOSTS. */
const YT_HOSTS = new Set(['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com', 'youtu.be', 'www.youtu.be'])
const VIDEO_ID = /^[A-Za-z0-9_-]{11}$/

const decode = (s: string): string | null => {
  try { return decodeURIComponent(s) } catch { return null }
}
/** The first `v` in a query, as URLSearchParams' `get` reads it. */
function firstParam(query: string, name: string): string | null {
  for (const pair of query.replace(/^\?/, '').split('&')) {
    const cut = pair.indexOf('=')
    const k = decode((cut < 0 ? pair : pair.slice(0, cut)).replace(/\+/g, ' '))
    if (k === name) return decode((cut < 0 ? '' : pair.slice(cut + 1)).replace(/\+/g, ' ')) ?? ''
  }
  return null
}

/** The id of the one video this URL is, or null: a playlist, a channel, a
 *  search, a lookalike or anything malformed is not one. A path with a dot
 *  segment (`/x/../watch`), which the browser would rewrite, is not read. */
export function youtubeOf(u: HttpUrl): string | null {
  if (!YT_HOSTS.has(u.host)) return null
  const seg = u.path.split('/').filter(Boolean)
  if (seg.some((s) => /^(\.|%2e){1,2}$/i.test(s))) return null
  let id: string | null = null
  if (u.host === 'youtu.be' || u.host === 'www.youtu.be') {
    if (seg.length === 1) id = decode(seg[0])
  } else if (seg.length === 1 && seg[0] === 'watch') {
    id = firstParam(u.query, 'v')
  } else if (seg.length === 2 && (seg[0] === 'shorts' || seg[0] === 'embed' || seg[0] === 'live')) {
    id = decode(seg[1])
  }
  return id !== null && VIDEO_ID.test(id) ? id : null
}

/* -- the links in a text --------------------------------------------------------- */

export interface Mention {
  /** the URL as written, trailing punctuation trimmed */
  url: string
  /** the words the author put around it, or null for a bare link */
  label: string | null
  domain: string
  /** the YouTube video it is, or null */
  video: string | null
  /** the lines (counted from 1) of the block it was written in */
  line: number
  end: number
}

/** A label as words: the emphasis and code marks around it taken off. */
const words = (s: string) => s.replace(/(\*\*|__|\*|_|`)(.+?)\1/g, '$2').replace(/\s+/g, ' ').trim()

/* -- what a reader reads as prose (../blocks.ts's fence rule, copied) ---------- */

const FENCE_OPEN = /^( {0,3})(`{3,}|~{3,})(.*)$/
const fenceCloses = (line: string, ch: string, len: number) => {
  const m = /^ {0,3}(`{3,}|~{3,})[ \t]*$/.exec(line)
  return m !== null && m[1][0] === ch && m[1].length >= len
}
const QUOTE = /^>\s?(.*)$/
const ROW = /^\s*\|(.+)\|\s*$/
const cells = (line: string): string[] => line.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map((c) => c.trim())

/** The runs of prose in a text -- everything outside its code fences, a run
 *  ending at a blank line -- each with its lines (from 1), its quote marks
 *  taken off and a table row read as its cells, as the block reader reads
 *  them. */
export function proseRuns(src: string): { text: string[]; line: number; end: number }[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const out: { text: string[]; line: number; end: number }[] = []
  let run: { text: string[]; line: number; end: number } | null = null
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const fence = FENCE_OPEN.exec(line)
    if (fence && !(fence[2][0] === '`' && fence[3].includes('`'))) {
      run = null
      const ch = fence[2][0], len = fence[2].length
      i += 1
      while (i < lines.length && !fenceCloses(lines[i], ch, len)) i++
      continue
    }
    if (!line.trim()) { run = null; continue }
    if (!run) out.push((run = { text: [], line: i + 1, end: i + 1 }))
    run.end = i + 1
    if (ROW.test(line)) run.text.push(...cells(line))
    else run.text.push(QUOTE.exec(line)?.[1] ?? line)
  }
  return out
}

/** Every http(s) link a text makes, one per URL, in reading order: read from
 *  its prose (never from a code fence or inline code), Markdown links first
 *  and then bare URLs, as prose.tsx's `videosOf` reads them. A labelled
 *  mention wins over a bare one of the same URL, in the bare one's place. */
export function linksOf(src: string): Mention[] {
  const out: Mention[] = []
  const at = new Map<string, number>()
  for (const r of proseRuns(src)) for (const raw of r.text) {
    const text = raw.replace(/`[^`]*`/g, ' ')
    const found: { url: string; label: string | null }[] = []
    const rest = text.replace(MD_LINK, (_all, label: string, target: string) => {
      found.push({ url: target, label: words(label) || null })
      return ' '
    })
    for (const m of rest.matchAll(URL_TOKEN)) found.push({ url: m[0].replace(TRAILING, ''), label: null })
    for (const f of found) {
      const u = parseHttp(f.url)
      if (!u) continue
      const prior = at.get(f.url)
      const m: Mention = { url: f.url, label: f.label, domain: domainOf(u), video: youtubeOf(u), line: r.line, end: r.end }
      if (prior === undefined) {
        at.set(f.url, out.length)
        out.push(m)
      } else if (f.label !== null && out[prior].label === null) {
        out[prior] = { ...m, line: out[prior].line, end: out[prior].end }
      }
    }
  }
  return out
}
