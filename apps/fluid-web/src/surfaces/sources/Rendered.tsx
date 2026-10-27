import type React from 'react'
import { qs, useApi, type Id } from '../../api'
import { inline, Prose } from '../../prose'
import AcquiredChip from './AcquiredChip'
import AcquiredPicture from './AcquiredPicture'
import type { LinkRow } from './route'

/* ------------------------------------------------------------------------ *
 * A STORED NOTE, RENDERED WITH ITS STORED IMAGES (Sources B, B3).
 *
 * The note's own held bytes, read whole from `/api/sources/rendered`, drawn
 * by the app's own Markdown reader in its untrusted mode: no raw HTML is
 * interpreted, no renderable block runs, no HTML fence is previewed, and a
 * link goes nowhere the reader does not already allow.
 *
 * EVERY EMBED IS RESOLVED BY THE RECORD, never by its text. The server reads
 * the relation recorded for it (G1's `resolved` key) against the record as it
 * stood while this observation was current, and says what the target is
 * (G2). Only an `acquired` image is drawn, and only through
 * `/api/artifacts/<adm>`. Everything else is the labelled placeholder with
 * its status -- including an `http(s)` image, which is never fetched and is
 * shown as its address. Viewing writes nothing.
 * ------------------------------------------------------------------------ */

interface Embed extends Omit<LinkRow, 'rel' | 'resolver'> {
  view?: string | null
  state?: string
}

interface RenderedAnswer {
  ref: Id
  key: string
  text: string
  truncated: boolean
  size: number
  cite: string
  embeds: Embed[]
}

/* An inline image `![alt](dest "title")`, the same image wrapped in a link to
   itself `[![alt](dest)](dest)` -- how notes exported from the web carry
   nearly every image -- or a wiki embed `![[target|alt]]`. The destination is
   matched the way the connector recorded it (`filesystem._IMAGE`). */
const DEST = String.raw`\(\s*(<[^>\n]*>|[^)\s]+)(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)`
const IMAGE = String.raw`!\[((?:[^\]\\\n]|\\.)*)\]` + DEST
const EMBED = new RegExp(
  String.raw`\[(${IMAGE})\]\([^)\n]*\)|${IMAGE}|!\[\[([^\]\n]+?)\]\]`,
  'g',
)

export function EmbedPlaceholder({ e, alt }: { e: Embed; alt: string }) {
  return (
    <span className="acq-placeholder" data-target={e.target}>
      <span className="acq-placeholder-kind">embed</span>
      <span className="acq-placeholder-label">{alt || e.authored}</span>
      <code className="acq-placeholder-dest">{e.authored}</code>
      <span className="acq-placeholder-state">
        {e.target}
        {e.reason ? ` (${e.reason})` : ''}
      </span>
    </span>
  )
}

export function EmbedView({ e, alt }: { e: Embed; alt: string }) {
  if (e.target === 'acquired' && e.target_ref) {
    if (e.view === 'image' || (e.state && e.state !== 'held'))
      return <AcquiredPicture id={e.target_ref} label={alt || e.resolved || e.authored} state={e.state} />
    return <AcquiredChip id={e.target_ref} said={alt || e.authored} />
  }
  return <EmbedPlaceholder e={e} alt={alt} />
}

/** `inline`, with each embed the note recorded drawn as what the record says
 *  it is. Embeds are matched to the record in order of appearance, by what
 *  was authored; one the record does not hold is a placeholder, unresolved. */
export function embedsInline(embeds: Embed[]) {
  const used = new Set<number>()
  const find = (syntax: string, authored: string): Embed => {
    const i = embeds.findIndex((e, j) => !used.has(j) && e.syntax === syntax && e.authored === authored)
    if (i < 0) return { syntax, authored, resolution: 'not-resolved', resolved: null, target: 'not resolved' }
    used.add(i)
    return embeds[i]
  }
  return (src: string, key: string): React.ReactNode[] => {
    const out: React.ReactNode[] = []
    let at = 0
    let n = 0
    for (const m of src.matchAll(EMBED)) {
      const i = m.index ?? 0
      if (i > at) out.push(...inline(src.slice(at, i), `${key}-t${n}`))
      const k = `${key}-e${n++}`
      if (m[6] !== undefined) {
        // wiki: what was recorded is the target before `|` and `#`
        const [target, alt] = m[6].split('|')
        out.push(<EmbedView key={k} e={find('wiki', target.split('#')[0])} alt={alt ?? ''} />)
      } else {
        // groups: 1-3 an image wrapped in a link, 4-5 a bare image
        const alt = m[2] ?? m[4] ?? ''
        const dest = m[3] ?? m[5] ?? ''
        out.push(<EmbedView key={k} e={find('inline', dest)} alt={alt} />)
      }
      at = i + m[0].length
    }
    if (at < src.length) out.push(...inline(src.slice(at), `${key}-t${n}`))
    return out
  }
}

export default function RenderedNote({ refId }: { refId: Id }) {
  const got = useApi<RenderedAnswer & { refused?: boolean; error?: string }>(
    '/api/sources/rendered' + qs({ ref: refId }),
    { live: false },
  )
  const r = got.data
  if (got.error) return <p className="act-refused">{got.error}</p>
  if (!r) return <p className="src-faint">reading the held bytes…</p>
  if (r.refused) return <p className="act-refused">{r.error}</p>
  return (
    <div className="src-rendered">
      <p className="src-faint">
        cite <code>{r.cite}</code> · rendered from the held bytes · embeds resolved from the record, never fetched
        {r.truncated ? ' · cut at 2 MB: the Text view pages the rest' : ''}
      </p>
      <div className="turn-body src-rendered-body">
        <Prose src={r.text} scope={`Source ${r.ref}`} inlineOf={embedsInline(r.embeds)} untrusted />
      </div>
    </div>
  )
}
