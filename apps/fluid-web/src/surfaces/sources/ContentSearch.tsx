import { useState } from 'react'
import { qs, read, type Id } from '../../api'
import { bytes, count, type SearchAnswer, type SearchHit, type Span } from './route'

/** What an answer lets the owner do next, and how much of the scope it
 *  speaks for: `more` pages this slice's hits, `continue` searches the
 *  next slice. `partial` unless the whole scope has been reached. */
export function searchProgress(a: SearchAnswer): {
  partial: boolean
  coverage: string
  action: { kind: 'more' | 'continue'; label: string; continuation: string | null; offset: number } | null
  empty: string
} {
  const c = a.coverage
  const partial = !c.complete
  const coverage = partial
    ? `partial: ${count(c.examined.objects)} of ${count(c.total.objects)} files examined (${bytes(c.examined.bytes)} of ${bytes(c.total.bytes)}); ${count(c.remaining.objects)} not yet searched`
    : c.exhaustive
      ? `complete: all ${count(c.total.objects)} files searched`
      : `complete: all ${count(c.total.objects)} files reached; some could not be searched (below)`
  const n = a.next
  const action =
    n === null
      ? null
      : n.continuation === a.slice.continuation
        ? { kind: 'more' as const, label: 'More matches', continuation: n.continuation, offset: n.offset }
        : {
            kind: 'continue' as const,
            label: `Continue searching (${count(c.remaining.objects)} files, ${bytes(c.remaining.bytes)} left)`,
            continuation: n.continuation,
            offset: n.offset,
          }
  const empty = partial
    ? `no match so far -- ${count(c.remaining.objects)} files have not been searched yet`
    : c.matches_so_far > 0
      ? 'no further match'
      : 'no match in the text that was searched'
  return { partial, coverage, action, empty }
}

/* ------------------------------------------------------------------------ *
 * SEARCH INSIDE THE FILES (Sources A, A2): where a phrase occurs in this
 * collection's acquired text, as snippets. Opening one goes to that
 * observation, scrolled to and highlighting the bytes it matched.
 *
 * WHAT WAS NOT SEARCHED IS SAID, every time: files that are not text and
 * have no extraction to search, by type and why (no extractor, extraction
 * pending, empty, failed), and any whose held bytes could not be read. An
 * empty answer is not "nothing there".
 *
 * A SEARCH IS SEARCHED IN SLICES (Stage F): one answer examines at most the
 * scan budget of the scope, and says how much of the scope it has examined
 * and what remains. Until the whole scope is reached the answer is called
 * partial -- "no match so far", never "no match" -- and "Continue searching"
 * asks for the next slice with the continuation the answer gave; its hits
 * are added below the ones already shown. If the record changed since the
 * search began, the server refuses, and that refusal is shown.
 *
 * A HIT IN AN EXTRACTION (Sources C) says where in the source it came from
 * -- the extractor's own location words, "page 12" -- and which extractor
 * made the text; opening it reads that exact extraction, in code points.
 *
 * Reads the held record through `/api/sources/search`; writes nothing and
 * never reads the folder.
 * ------------------------------------------------------------------------ */

export default function ContentSearch({
  col,
  onHit,
}: {
  col: Id
  onHit: (ref: Id, span: Span, extraction?: string) => void
}) {
  const [q, setQ] = useState('')
  const [asked, setAsked] = useState<string | null>(null)
  const [got, setGot] = useState<SearchAnswer | null>(null)
  const [hits, setHits] = useState<SearchHit[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const ask = async (phrase: string, offset: number, continuation: string | null = null) => {
    setBusy(true)
    setError(null)
    try {
      const a = await read<SearchAnswer>(
        '/api/sources/search' + qs({ q: phrase, collection: col, offset, continuation }),
      )
      setGot(a)
      // a new search starts the list; another page or slice adds to it
      setHits((h) => (offset === 0 && continuation === null ? a.hits : [...h, ...a.hits]))
      setAsked(phrase)
    } catch (e) {
      setError((e as Error).message)
      if (offset === 0 && continuation === null) {
        setGot(null)
        setHits([])
      }
    } finally {
      setBusy(false)
    }
  }

  const ns = got?.not_searched
  const progress = got ? searchProgress(got) : null
  const types = ns ? Object.entries(ns.by_type) : []
  const why = ns?.extraction ?? {}
  const reasons = ['extraction_pending', 'transient', 'empty', 'failed', 'unavailable', 'corrupt']
    .map((r) => [r, Object.values(why[r] ?? {}).reduce((a, b) => a + b, 0)] as const)
    .filter(([, n]) => n > 0)
  return (
    <div className="src-search">
      <form
        className="src-browse-bar"
        onSubmit={(e) => {
          e.preventDefault()
          if (q.trim()) void ask(q.trim(), 0)
        }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="a phrase in the files"
          aria-label="search file contents"
        />
        <button className="btn" type="submit" disabled={busy || !q.trim()}>
          Search
        </button>
        <span className="src-faint">literal phrase · any case · the held text, not the live folder</span>
      </form>
      {error && <p className="act-refused">{error}</p>}
      {busy && hits.length === 0 && <p className="src-faint">searching the held text…</p>}
      {got && progress && asked !== null && (
        <p className={progress.partial ? 'src-search-summary src-search-partial' : 'src-faint src-search-summary'}>
          <b>{progress.coverage}</b> · {count(got.coverage.matches_so_far)}{' '}
          {got.coverage.matches_so_far === 1 ? 'match' : 'matches'} of “{asked}”{progress.partial ? ' so far' : ''}
        </p>
      )}
      {got && asked !== null && (
        <p className="src-faint src-search-summary">
          {got.coverage.slice > 1 || progress?.partial ? `this slice (${got.coverage.slice}): ` : ''}
          {count(got.total_matches)} {got.total_matches === 1 ? 'match' : 'matches'} in{' '}
          {count(got.files_with_hits)} {got.files_with_hits === 1 ? 'file' : 'files'} · searched{' '}
          {count(got.searched.files)} text files ({bytes(got.searched.bytes)})
          {got.searched.extractions > 0 && (
            <>
              {' '}
              and {count(got.searched.extractions)} extracted {got.searched.extractions === 1 ? 'text' : 'texts'} (
              {bytes(got.searched.extraction_bytes)})
            </>
          )}
          {ns && ns.non_text > 0 && (
            <>
              {' '}
              · <b>not searched</b>: {types.map(([t, n]) => `${count(n)} ${t}`).join(', ')}
            </>
          )}
          {reasons.length > 0 && (
            <> ({reasons.map(([r, n]) => `${count(n)} ${r.replace('_', ' ')}`).join(', ')})</>
          )}
          {ns && ns.unreadable > 0 && <> · {count(ns.unreadable)} unreadable</>}
          {ns && (ns.over_slice ?? 0) > 0 && <> · {count(ns.over_slice)} too large to search in one slice</>}
          {got.not_returned.beyond_per_file > 0 && (
            <> · the first 3 of each file are listed; {count(got.not_returned.beyond_per_file)} more are in the files</>
          )}
          {got.not_returned.over_excerpt > 0 && (
            <> · {count(got.not_returned.over_excerpt)} too long to show in an excerpt</>
          )}
          {got.truncated && <> · stopped at the scan budget; {count(ns?.over_budget)} files not reached yet</>}
        </p>
      )}
      {got && progress && hits.length === 0 && !busy && <p className="src-faint">{progress.empty}</p>}
      <ol className="src-hits">
        {hits.map((h) => (
          <li key={`${h.ref}:${h.extraction?.extractor_id ?? ''}:${h.offset}`}>
            <button
              className="src-hit"
              onClick={() => onHit(h.ref, { offset: h.offset, end: h.end }, h.extraction?.extractor_id)}
            >
              <span className="src-hit-where">
                {h.key}{' '}
                <span className="src-faint">
                  {h.extraction ? `· ${h.display} · extracted text, ${h.extraction.extractor_id.split('+')[0]}` : `· line ${h.line}`}
                </span>
              </span>
              <span className="src-hit-snippet">{h.snippet}</span>
            </button>
            <span className="src-faint src-hit-count">
              match {h.match.n} of {h.match.of} in this file
              {h.more_in_file > 0 && h.match.n === h.match.of - h.more_in_file
                ? ` · ${count(h.more_in_file)} more further on in the file`
                : ''}
              {h.embeds_in_excerpt.length > 0
                ? ` · ${h.embeds_in_excerpt.length} embed${h.embeds_in_excerpt.length === 1 ? '' : 's'} nearby`
                : ''}
            </span>
          </li>
        ))}
      </ol>
      {progress?.action && asked !== null && (
        <button
          className={progress.action.kind === 'continue' ? 'btn' : 'btn quiet'}
          disabled={busy}
          onClick={() => void ask(asked, progress.action!.offset, progress.action!.continuation)}
        >
          {progress.action.label}
        </button>
      )}
    </div>
  )
}
