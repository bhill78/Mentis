import { useEffect, useRef, useState } from 'react'
import { qs, shortId, useApi, when, type Id } from '../../api'
import { LinkStatus } from './parts'
import RenderedNote from './Rendered'
import {
  bytes,
  reveal,
  type LinksAnswer,
  type Page,
  type Provenance,
  type SourcesRoute,
  type Span,
} from './route'

/* ------------------------------------------------------------------------ *
 * ONE OBJECT (U8): its versions, its links in and out, a page reader with
 * citations, and Show live file.
 *
 * WHICH OBSERVATION IS ON SCREEN IS SAID. Reached from a reference chip it
 * is the one the reference cites -- pinned, and never swapped for the latest
 * behind anybody's back (owner decision 3). A newer one is announced with
 * Compare and Go to latest. Reached from Browse it is the latest.
 *
 * NOTHING HERE READS THE BOUND FOLDER (G3). Every byte comes from the held
 * store; every link status comes from the record. A link or embed whose
 * target is not acquired is a labelled placeholder carrying its status --
 * never an image, never a fetch. An ACQUIRED image a note embeds is drawn in
 * the Rendered view (Sources B3), from its held bytes, and nothing else is. The one thing that reaches the live folder
 * is Show live file, and that opens Explorer on this machine and returns
 * nothing.
 * ------------------------------------------------------------------------ */

/** THE OBSERVATIONS OF EXACTLY ONE KEY, oldest first. Read by the key
 *  itself, never by searching for it: a substring page (`objects?q=<key>`)
 *  sorted by key put `x/index.md`, `y/index.md`, ... ahead of `index.md`, and
 *  past 200 of them the page said "No observation of index.md is recorded"
 *  about an object the record holds (review note 6). */
export const observationsOf = (col: Id, key: string): string =>
  `/api/sources/${encodeURIComponent(col)}/history` + qs({ key })

/** The latest observation in an exact-key history, or null where none is
 *  recorded. Append order is observation order. */
export const latestIn = (h: { known: boolean; observations?: { ref: Id }[] } | null | undefined): Id | null =>
  h?.known && h.observations?.length ? h.observations[h.observations.length - 1].ref : null

export default function ObjectPage({
  col,
  objectKey,
  pinned,
  span,
  extraction,
  go,
}: {
  /** the object, by collection and key: shows its latest observation */
  col?: Id
  objectKey?: string
  /** or one observation, by reference: shows exactly that one */
  pinned?: Id
  /** what to scroll to and highlight: where a content search hit matched --
   *  bytes, or code points of `extraction` when one is named */
  span?: Span
  /** read through this exact extraction (Sources C) */
  extraction?: string
  go: (r: SourcesRoute) => void
}) {
  /* The latest observation of the key, when the page is reached by key. */
  const latest = useApi<{ known: boolean; observations?: { ref: Id }[] }>(
    !pinned && col && objectKey ? observationsOf(col, objectKey) : null,
  )
  const byKey = latestIn(latest.data)
  const ref = pinned ?? byKey
  const prov = useApi<Provenance>(ref ? `/api/sources/provenance` + qs({ ref }) : null)
  const p = prov.data
  if (latest.data && !byKey && !pinned) return <p className="act-refused">No observation of {objectKey} is recorded.</p>
  /* A FIRST READ THAT FAILED IS SAID. When the key's history failed there
     was no ref, so provenance was never asked and nothing reported it: the
     page said "reading the record…" for as long as it was open
     (opr-39a931af7015). Try again rereads the one that failed; while that
     reread is out the page says it is reading, and its answer replaces this. */
  const failed = prov.error ? prov : !pinned && !latest.data && latest.error ? latest : null
  if (failed && !failed.loading)
    return (
      <p className="act-refused" role="alert">
        Could not read {pinned ? shortId(pinned, 16) : objectKey}: {failed.error}{' '}
        <button className="link" onClick={failed.reload}>
          Try again
        </button>
      </p>
    )
  if (!p) return <p className="src-faint">reading the record…</p>
  return <Loaded p={p} pinned={!!pinned} span={span} extraction={extraction} go={go} />
}

function Loaded({
  p,
  pinned,
  span,
  extraction,
  go,
}: {
  p: Provenance
  pinned: boolean
  span?: Span
  extraction?: string
  go: (r: SourcesRoute) => void
}) {
  const links = useApi<LinksAnswer>(
    `/api/sources/${encodeURIComponent(p.collection)}/links` + qs({ key: p.object, ...(p.connector === 'sqlite' ? { ref: p.ref } : {}) }),
  )
  const [live, setLive] = useState<string | null>(null)
  const show = async () => {
    setLive(null)
    try {
      const r = await reveal(p.collection, p.object)
      setLive(r.revealed ? 'Shown in Explorer on this machine. Nothing was recorded.' : `Not shown: ${r.why ?? r.state}`)
    } catch (e) {
      setLive((e as Error).message)
    }
  }
  const isLatest = p.ref === p.latest
  /* A STORED NOTE CAN ALSO BE READ RENDERED (Sources B, B3), with its stored
     images drawn and everything else a placeholder. Text stays the default:
     what is held is exactly the characters, and that view says so. */
  const note = !!p.text && (/\.(md|markdown)$/i.test(p.object) || p.payload_type === 'text/markdown')
  /* AN EXTRACTION OF THESE BYTES CAN BE READ (Sources C): the one a route
     names exactly -- an old one a citation pins included -- or else the
     first current one that holds text. It is said to be extracted text,
     by which extractor, with offsets in code points. */
  const usable = (p.extractions ?? []).filter((x) => x.extractor_id && x.state === 'ok')
  const xid = extraction ?? usable.find((x) => x.current)?.extractor_id ?? null
  const [view, setView] = useState<'text' | 'rendered' | 'extracted'>(
    extraction || (!p.text && xid) ? 'extracted' : 'text',
  )
  /* LINKS BELONG TO AN OBSERVATION. The links read is of the latest; when
     an older one is pinned its own relations differ, so the list is said to
     be the latest's rather than passed off as this one's. */
  const l = links.data
  return (
    <section className="src-page">
      <header className="src-head">
        <h1 className="src-key">{p.label}</h1>
      </header>
      <p className="src-sub">
        <button className="link" onClick={() => go({ at: 'collection', col: p.collection, tab: 'browse' })}>
          {p.collection_name ?? p.collection}
        </button>{' '}
        · {p.connector_label} · this observation <span className="src-mono">{shortId(p.ref, 16)}</span> · swept{' '}
        {when(p.sweep?.at ?? p.admitted_at)} · version {p.version.n} of {p.version.of}
        {isLatest ? ' (the latest)' : ''} · {p.state} · {bytes(p.size)}
      </p>
      {p.newer_exists && (
        <p className="src-banner att">
          {pinned ? 'This reference cites' : 'This is'} version {p.version.n}. Version {p.version.of} was recorded
          later{p.latest_state === 'absent' ? ', recording the file as absent' : ''}.{' '}
          <button className="link" onClick={() => go({ at: 'compare', a: p.ref, b: p.latest })}>
            Compare
          </button>{' '}
          ·{' '}
          <button className="link" onClick={() => go({ at: 'observation', ref: p.latest })}>
            Go to latest
          </button>
        </p>
      )}
      <div className="src-actions">
        {p.live === 'local-reveal' && (
          <button className="btn" onClick={show}>
            Show live file
          </button>
        )}
        {live && <span className="src-note">{live}</span>}
      </div>
      <div className="src-cols">
        <div>
          <h2 className="src-h2">
            Read
            {xid && p.state === 'present' && (
              <span className="src-view-toggle" role="group" aria-label="what to read">
                <button className={'btn quiet' + (view !== 'extracted' ? ' on' : '')} aria-pressed={view !== 'extracted'} onClick={() => setView('text')}>
                  {p.text ? 'Text' : 'Bytes'}
                </button>
                <button className={'btn quiet' + (view === 'extracted' ? ' on' : '')} aria-pressed={view === 'extracted'} onClick={() => setView('extracted')}>
                  Extracted text
                </button>
              </span>
            )}
            {note && p.state === 'present' && view !== 'extracted' && (
              <span className="src-view-toggle" role="group" aria-label="how to read it">
                <button className={'btn quiet' + (view === 'text' ? ' on' : '')} aria-pressed={view === 'text'} onClick={() => setView('text')}>
                  Text
                </button>
                <button className={'btn quiet' + (view === 'rendered' ? ' on' : '')} aria-pressed={view === 'rendered'} onClick={() => setView('rendered')}>
                  Rendered
                </button>
              </span>
            )}
          </h2>
          {p.connector === 'sqlite' && p.state === 'present' && <RecordView refId={p.ref} go={go} />}
          {p.state === 'present' && view === 'extracted' && xid ? (
            <ExtractedReader refId={p.ref} extraction={xid} span={extraction === xid ? span : undefined} />
          ) : p.state === 'present' && note && view === 'rendered' ? (
            <RenderedNote refId={p.ref} />
          ) : p.state === 'present' ? (
            <Reader refId={p.ref} text={!!p.text} span={p.text && !extraction ? span : undefined} />
          ) : (
            <p className="src-note">This observation records the file as {p.state}; there are no bytes for it.</p>
          )}
          {(p.extractions ?? []).some((x) => x.state !== 'ok') && (
            <p className="src-faint">
              {(p.extractions ?? [])
                .filter((x) => x.state !== 'ok')
                .map((x) => `${x.extractor_id ?? x.name}: ${x.status ?? x.state}`)
                .join(' · ')}
            </p>
          )}
        </div>
        <div>
          <h2 className="src-h2">Versions</h2>
          <ol className="src-list">
            {p.observations.map((o, i) => (
              <li key={o.ref}>
                {o.ref === p.ref ? (
                  <b>
                    v{i + 1} · {o.action} · {when(o.admitted_at)} (this one)
                  </b>
                ) : (
                  <button className="link" onClick={() => go({ at: 'observation', ref: o.ref })}>
                    v{i + 1} · {o.action} · {when(o.admitted_at)}
                  </button>
                )}
                {o.state !== 'present' && <span className="src-faint"> · {o.state}</span>}
              </li>
            ))}
          </ol>
          <h2 className="src-h2">Links out{p.connector === 'sqlite' ? ' (at capture time)' : !isLatest && ' (of the latest version)'}</h2>
          {links.error && <p className="act-refused">{links.error}</p>}
          {l && l.links.length === 0 && <p className="src-faint">none</p>}
          <ul className="src-links">
            {l?.links.map((x, i) => (
              <LinkStatus key={i} l={x} onOpen={(key) => go(p.connector === 'sqlite' && x.target_ref ? { at: 'observation', ref: x.target_ref } : { at: 'object', col: p.collection, key })} />
            ))}
          </ul>
          <p className="src-faint">
            Statuses are read from the record. A target that is not acquired is shown as words, never fetched.
          </p>
          <h2 className="src-h2">Linked from</h2>
          {l && l.linked_from.length === 0 && <p className="src-faint">nothing in this collection links here</p>}
          <ul className="src-list">
            {l?.linked_from.map((x, i) => (
              <li key={i}>
                <button className="link" onClick={() => go(p.connector === 'sqlite' ? { at: 'observation', ref: x.ref } : { at: 'object', col: p.collection, key: x.from })}>
                  {x.label}
                </button>{' '}
                <span className="src-faint">
                  {x.rel === 'embeds' ? 'embeds' : 'links to'} it as <code>{x.authored}</code>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}

function RecordView({ refId, go }: { refId: Id; go: (r: SourcesRoute) => void }) {
  const record = useApi<{ payload?: { fields?: Record<string, string[]>; withheld_fields?: string[] }; schema_ref?: string; note: string; bounded?: boolean }>('/api/sources/record' + qs({ ref: refId }))
  const g = record.data
  if (record.error) return <p className="act-refused">{record.error}</p>
  if (!g) return <p>Reading fields…</p>
  return <section aria-label="Captured SQLite record">
    <p>{g.note}</p>
    {g.payload?.fields && <table><thead><tr><th>Field</th><th>SQLite type</th><th>Value</th></tr></thead><tbody>{Object.entries(g.payload.fields).map(([name, value]) => <tr key={name}><th>{name}</th><td>{value[0]}</td><td><code>{value[1]}</code></td></tr>)}</tbody></table>}
    {!!g.payload?.withheld_fields?.length && <p>Withheld fields: {g.payload.withheld_fields.join(', ')}</p>}
    {g.schema_ref && <button className="link" onClick={() => go({ at: 'observation', ref: g.schema_ref! })}>Schema at capture time</button>}
  </section>
}

/** The server's page size (`reading.PAGE_BYTES`). */
const PAGE = 64 * 1024

/** A page reader over the HELD bytes, citing exactly what it shows. Text is
 *  shown as text -- plain, never rendered -- so an embed in it is the words
 *  that were written and nothing loads. */
function Reader({ refId, text, span }: { refId: Id; text: boolean; span?: Span }) {
  /* REACHED FROM A SEARCH HIT, the reader opens on the page holding it.
     Pages are 64 KiB from a start the server moves to a character
     boundary; a hit that would straddle one opens at the hit itself. */
  const [offset, setOffset] = useState(() => {
    if (!span) return 0
    const at = Math.floor(span.offset / PAGE) * PAGE
    return span.end <= at + PAGE ? at : span.offset
  })
  /* Opened past the start, the pages before it are still a Previous away:
     the start of each whole page before the one shown. */
  const [back, setBack] = useState<number[]>(() =>
    Array.from({ length: Math.ceil(offset / PAGE) }, (_, i) => i * PAGE),
  )
  const page = useApi<Page>(
    '/api/sources/page' + qs({ ref: refId, offset }),
    { live: false },
  )
  const g = page.data
  if (page.error) return <p className="act-refused">{page.error}</p>
  if (!g) return <p className="src-faint">reading the held bytes…</p>
  return (
    <div className="src-reader">
      <p className="src-faint">
        cite <code>{g.cite}</code> · bytes {g.offset}–{g.end} of {g.size} · {g.encoding}
      </p>
      {text && g.text !== undefined ? (
        <pre className="src-text">
          <Marked text={g.text} from={g.offset} span={span} />
        </pre>
      ) : (
        <p className="src-note">
          Not text: {bytes(g.size)} held exactly as acquired. It is not drawn here.
        </p>
      )}
      <p>
        {back.length > 0 && (
          <button
            className="btn quiet"
            onClick={() => {
              setOffset(back[back.length - 1])
              setBack(back.slice(0, -1))
            }}
          >
            Previous page
          </button>
        )}
        {g.next_offset !== null && text && (
          <button
            className="btn quiet"
            onClick={() => {
              setBack([...back, offset])
              setOffset(g.next_offset!)
            }}
          >
            Next page
          </button>
        )}
      </p>
    </div>
  )
}

/** Where `span` (bytes in the stored file) falls in one page of `text`
 *  that starts at byte `from`, in UTF-16 units: [start, end], or null when
 *  it is not on this page. Each character's UTF-8 length is counted, so a
 *  match after a multi-byte character is placed where it is. */
export function markRange(text: string, from: number, span?: Span): [number, number] | null {
  if (!span || span.end <= from) return null
  let b = from
  let i = 0
  let start = -1
  for (const ch of text) {
    if (start < 0 && b >= span.offset) start = i
    if (b >= span.end) return start < 0 ? null : [start, i]
    const cp = ch.codePointAt(0)!
    b += cp < 0x80 ? 1 : cp < 0x800 ? 2 : cp < 0x10000 ? 3 : 4
    i += ch.length
  }
  return start < 0 ? null : [start, text.length]
}

/** One page of text, with the bytes `span` names marked and scrolled into
 *  view. */
function Marked({ text, from, span }: { text: string; from: number; span?: Span }) {
  const mark = useRef<HTMLElement>(null)
  useEffect(() => {
    mark.current?.scrollIntoView({ block: 'center' })
  }, [text, span?.offset])
  const at = markRange(text, from, span)
  if (!at) return <>{text}</>
  return (
    <>
      {text.slice(0, at[0])}
      <mark ref={mark} className="src-hit-mark">
        {text.slice(at[0], at[1])}
      </mark>
      {text.slice(at[1])}
    </>
  )
}

/** The server's window of an extraction, in code points
 *  (`reading.WINDOW_CHARS`). */
const WINDOW = 64 * 1024

/** A reader over ONE EXACT EXTRACTION of the held bytes (Sources C), citing
 *  exactly what it shows. Offsets are code points of the extracted text,
 *  never bytes; the source location of the window shown is said in the
 *  extractor's own words. */
function ExtractedReader({ refId, extraction, span }: { refId: Id; extraction: string; span?: Span }) {
  /* A hit that would straddle two windows opens at the hit itself. */
  const [offset, setOffset] = useState(() => {
    if (!span) return 0
    const at = Math.floor(span.offset / WINDOW) * WINDOW
    return span.end <= at + WINDOW ? at : span.offset
  })
  const page = useApi<Page>('/api/sources/page' + qs({ ref: refId, offset, extraction }), { live: false })
  const g = page.data
  if (page.error) return <p className="act-refused">{page.error}</p>
  if (!g) return <p className="src-faint">reading the extracted text…</p>
  return (
    <div className="src-reader">
      <p className="src-faint">
        extracted text · {g.extraction?.extractor_id} · {g.display} · cite <code>{g.cite}</code> · code points{' '}
        {g.offset}–{g.end} of {g.size}
      </p>
      <pre className="src-text">
        <MarkedCp text={g.text ?? ''} from={g.offset} span={span} />
      </pre>
      <p>
        {g.offset > 0 && (
          <button className="btn quiet" onClick={() => setOffset(Math.max(0, g.offset - WINDOW))}>
            Previous
          </button>
        )}
        {g.next_offset !== null && (
          <button className="btn quiet" onClick={() => setOffset(g.next_offset!)}>
            Next
          </button>
        )}
      </p>
    </div>
  )
}

/** Where `span` (code points of an extraction) falls in one window of
 *  `text` that starts at code point `from`, in UTF-16 units: [start, end],
 *  or null when it is not in this window. */
export function markRangeCp(text: string, from: number, span?: Span): [number, number] | null {
  if (!span || span.end <= from) return null
  let cp = from
  let i = 0
  let start = -1
  for (const ch of text) {
    if (start < 0 && cp >= span.offset) start = i
    if (cp >= span.end) return start < 0 ? null : [start, i]
    cp += 1
    i += ch.length
  }
  return start < 0 ? null : [start, text.length]
}

function MarkedCp({ text, from, span }: { text: string; from: number; span?: Span }) {
  const mark = useRef<HTMLElement>(null)
  useEffect(() => {
    mark.current?.scrollIntoView({ block: 'center' })
  }, [text, span?.offset])
  const at = markRangeCp(text, from, span)
  if (!at) return <>{text}</>
  return (
    <>
      {text.slice(0, at[0])}
      <mark ref={mark} className="src-hit-mark">
        {text.slice(at[0], at[1])}
      </mark>
      {text.slice(at[1])}
    </>
  )
}
