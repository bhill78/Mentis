import { useContext, useRef, useState } from 'react'
import { qs, shortId, useApi } from '../../api'
import { anchored, Floating } from '../../bits'
import { parseExtractedCite } from '../../refid'
import { TurnQuote } from '../../turnQuote'
import { openInSources } from './route'
import './sources.css'

/* ------------------------------------------------------------------------ *
 * A CITATION OF EXTRACTED TEXT, IN A TURN (Sources C, C4).
 *
 *   adm-…@<src12>~<extractor_id>/<rep12>[start:end]{scheme:token}
 *
 * One chip for the whole citation, not an `adm-` chip followed by inert
 * text. Opened, it says the source, where in it (the scheme's own words),
 * which extractor made the text, and whether the citation is VERIFIED --
 * the exact representation it names still says it, at that place -- or
 * NOT REPRODUCIBLE HERE, in which case it shows what the citation itself
 * carries (the source and its location) and the quote the Turn holds. It
 * is never re-pointed to another extractor's text.
 *
 * A direct citation (`adm-…@d12[s:e]`, bytes of a text file) is not this:
 * it stays the `adm-` chip it always was.
 *
 * THE QUOTE is the Turn's own: a passage in quotation marks before it, the
 * blockquote it sits in, or the blockquote just before it (`turnQuote`).
 * It is sent with the question and shown whether or not anything here can
 * reproduce the citation -- with the source and location the citation
 * itself carries.
 *
 * Asks `/api/sources/cite`, which reads the record and the extraction store
 * and writes nothing. It never builds an extraction while the hover waits:
 * a missing one is started in the background and the answer is `pending`.
 * ------------------------------------------------------------------------ */

interface Verdict {
  status: 'verified' | 'pending' | 'not reproducible here' | 'mismatch' | 'unreadable' | 'malformed'
  why?: string
  label?: string
  key?: string
  display?: string
  extractor_id?: string
  scheme?: string
  token?: string
  start?: number
  end?: number
  text?: string
  shows?: { source: string; location: string; quote: string | null }
}

export default function CiteChip({ cite, quote: near }: { cite: string; quote?: string }) {
  const c = parseExtractedCite(cite)
  const inTurn = useContext(TurnQuote)
  const quote = inTurn?.(cite) ?? near
  const [open, setOpen] = useState(false)
  const [pin, setPin] = useState(false)
  const at = useRef<HTMLButtonElement | null>(null)
  const shown = open || pin
  const v = useApi<Verdict>(shown ? '/api/sources/cite' + qs({ cite, quote: quote ?? '' }) : null, { live: false })
  const d = v.data
  if (!c) return <>{cite}</>
  return (
    <span className="ref-wrap acq-wrap">
      <button
        ref={at}
        className="ref acq-chip cite-chip"
        title={`citation of extracted text · ${cite}`}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.stopPropagation()
          setPin(!pin)
        }}
      >
        {shortId(c.ref, 12)} · {c.scheme}:{c.token}
      </button>
      {shown && (
        <Floating>
          <span
            className="ref-pop acq-pop"
            role={pin ? 'dialog' : 'tooltip'}
            style={anchored(at.current, 380)}
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => setOpen(false)}
          >
            <span className="ref-kind">extracted text · {c.extractor_id}</span>
            {v.loading && !d && <span className="ref-title">checking the citation…</span>}
            {v.error && <span className="ref-note">{v.error}</span>}
            {d && (
              <>
                <span className="ref-title">{d.label ?? d.key ?? c.ref}</span>
                <span className="ref-note">
                  {d.display ?? `${c.scheme}:${c.token}`} · code points {c.start}–{c.end}
                </span>
                <span className={'ref-note cite-status ' + (d.status === 'verified' ? 'ok' : 'att')}>
                  {d.status === 'verified'
                    ? 'verified: this exact extraction still says it, at this place'
                    : d.status}
                  {d.why && d.status !== 'verified' ? ` — ${d.why}` : ''}
                </span>
                {d.status === 'not reproducible here' && (
                  <span className="ref-note">
                    Source <code>{c.ref}</code> at <code>{`${c.scheme}:${c.token}`}</code>
                    {quote ? (
                      <>
                        {' '}
                        · quoted in this Turn: “{quote}”
                      </>
                    ) : (
                      ' · the quote is the Turn’s own text beside this citation'
                    )}
                  </span>
                )}
                {d.status === 'verified' && (
                  <span className="acq-actions">
                    <button
                      className="btn"
                      onClick={() =>
                        openInSources({
                          at: 'observation',
                          ref: c.ref,
                          extraction: c.extractor_id,
                          span: { offset: c.start, end: c.end },
                        })
                      }
                    >
                      Open in Sources
                    </button>
                  </span>
                )}
              </>
            )}
            <span className="ref-id">{cite}</span>
          </span>
        </Floating>
      )}
    </span>
  )
}
