import { useMemo } from 'react'
import { qs, shortId, useApi, when, type Id } from '../../api'
import { bytes, type LinkRow, type Page, type Provenance, type SourcesRoute } from './route'

/* ------------------------------------------------------------------------ *
 * TWO OBSERVATIONS OF ONE OBJECT (B7). The server says what differs in what
 * was recorded -- bytes, size, type, encoding, relations added or removed --
 * and hands the first page of each, for text. The line diff below is drawn
 * here and stored nowhere.
 * ------------------------------------------------------------------------ */

interface CompareAnswer {
  collection: Id
  object: string
  label: string
  a: Provenance
  b: Provenance
  same_bytes: boolean
  differences: Record<string, { a: unknown; b: unknown }>
  relations: { added: LinkRow[]; removed: LinkRow[] }
  pages: { a: Page | null; b: Page | null }
}

type Line = { t: ' ' | '-' | '+'; s: string }

/** A plain longest-common-subsequence line diff, bounded. */
function diffLines(a: string, b: string): Line[] | null {
  const x = a.split('\n')
  const y = b.split('\n')
  if (x.length * y.length > 4_000_000) return null
  const n = x.length
  const m = y.length
  const L: Uint32Array[] = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1))
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1])
  const out: Line[] = []
  let i = 0
  let j = 0
  while (i < n && j < m) {
    if (x[i] === y[j]) {
      out.push({ t: ' ', s: x[i] })
      i++
      j++
    } else if (L[i + 1][j] >= L[i][j + 1]) out.push({ t: '-', s: x[i++] })
    else out.push({ t: '+', s: y[j++] })
  }
  while (i < n) out.push({ t: '-', s: x[i++] })
  while (j < m) out.push({ t: '+', s: y[j++] })
  return out
}

export default function Compare({ a, b, go }: { a: Id; b: Id; go: (r: SourcesRoute) => void }) {
  const c = useApi<CompareAnswer>('/api/sources/compare' + qs({ a, b }), { live: false })
  const d = c.data
  const lines = useMemo(
    () => (d?.pages.a?.text !== undefined && d?.pages.b?.text !== undefined ? diffLines(d.pages.a.text!, d.pages.b.text!) : null),
    [d],
  )
  if (c.error) return <p className="act-refused">{c.error}</p>
  if (!d) return <p className="src-faint">reading the record…</p>
  const side = (p: Provenance) => (
    <>
      v{p.version.n} <span className="src-mono">{shortId(p.ref, 14)}</span> · {when(p.admitted_at)} · {p.state} ·{' '}
      {bytes(p.size)}
    </>
  )
  return (
    <section className="src-page">
      <header className="src-head">
        <h1 className="src-key">{d.label}</h1>
      </header>
      <p className="src-sub">
        Comparing {side(d.a)} with {side(d.b)}.{' '}
        <button className="link" onClick={() => go({ at: 'observation', ref: a })}>
          Open v{d.a.version.n}
        </button>{' '}
        ·{' '}
        <button className="link" onClick={() => go({ at: 'observation', ref: b })}>
          Open v{d.b.version.n}
        </button>
      </p>
      <ul className="src-kept">
        <li>
          <b>Bytes</b>: {d.same_bytes ? 'identical' : 'different'}
        </li>
        {Object.entries(d.differences).map(([k, v]) => (
          <li key={k}>
            <b>{k}</b>: <code>{JSON.stringify(v.a)}</code> → <code>{JSON.stringify(v.b)}</code>
          </li>
        ))}
        <li>
          <b>Relations</b>: {d.relations.added.length} added, {d.relations.removed.length} removed
          {d.relations.added.map((r, i) => (
            <div key={'a' + i} className="src-add">
              + {r.rel} <code>{r.authored}</code>
            </div>
          ))}
          {d.relations.removed.map((r, i) => (
            <div key={'r' + i} className="src-del">
              − {r.rel} <code>{r.authored}</code>
            </div>
          ))}
        </li>
      </ul>
      {lines ? (
        <>
          <p className="src-faint">The first page of each, line by line.</p>
          <pre className="src-text src-diff">
            {lines.map((l, i) => (
              <div key={i} className={l.t === '+' ? 'src-add' : l.t === '-' ? 'src-del' : ''}>
                {l.t} {l.s}
              </div>
            ))}
          </pre>
        </>
      ) : (
        <p className="src-note">No text page to compare line by line.</p>
      )}
    </section>
  )
}
