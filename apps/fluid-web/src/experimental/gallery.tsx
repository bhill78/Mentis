/* EXPERIMENTAL: the renderer gallery / playground.

   Every example is live Markdown drawn by the same code a Turn uses. Beside
   it: the declaration (editable), the current state, the degraded text and
   the exact send-back payload, all recomputed as you edit or interact. The
   feedback boxes are kept in this browser only (localStorage) until you put
   them in the composer yourself; nothing here writes to Mentis. */
import { useState } from 'react'
import { Prose } from '../prose'
import { changed, markedIn, payloadOf, placeInComposer, readableOf, store, useStore } from './renderable'
import { namesFor } from './objects'
import { EXAMPLES, type Example } from './examples'
import { TYPES } from './types'

const edits: Record<string, string> = {}
const FB = (id: string) => `rb-feedback:${id}`

export function Gallery({ onClose }: { onClose: () => void }) {
  useStore()
  const [only, setOnly] = useState<string>('all')
  const cats = ['all', ...new Set(EXAMPLES.map((e) => e.category))]
  const shown = EXAMPLES.filter((e) => only === 'all' || e.category === only)
  const feedback = () =>
    EXAMPLES.map((e) => [e, localStorage.getItem(FB(e.id)) ?? ''] as const)
      .filter(([, t]) => t.trim())
      .map(([e, t]) => `**${e.category} — ${e.title}**\n${t.trim()}`)
      .join('\n\n')
  return (
    <div className="rb-gallery" role="dialog" aria-label="Renderer gallery (experimental)">
      <div className="rb-gallery-top">
        <b>Renderer gallery</b> <span className="rb-tag">experimental</span>
        <span className="rb-grow" />
        <button
          className="btn"
          onClick={() => {
            const t = feedback()
            if (!t) { alert('No feedback written yet.'); return }
            if (placeInComposer(`Renderer gallery feedback:\n\n${t}\n`)) onClose()
            else navigator.clipboard?.writeText(t).then(() => alert('No composer is open; the feedback was copied instead.'))
          }}
        >
          Put my feedback in the composer
        </button>
        <button className="btn" onClick={onClose}>Close ✕</button>
      </div>
      <p className="rb-muted rb-gallery-note">
        Everything below is drawn by the same code that draws a Turn. <b>Real:</b> parsing, validation, drawing from the declared
        attributes only, every interaction, degraded text, the payload. <b>Mocked:</b> state lasts only while this tab is open and follows the block's position; images are
        mock drawings (nothing generated or retrieved); declared source scopes are shown, never resolved; helper scope is requested, not authorised; "Send back" only drafts into a
        composer. Pinned surfaces stay in the dock after you close the gallery.
      </p>
      <div className="rb-row rb-gallery-cats">
        {cats.map((c) => (
          <button key={c} className="btn quiet" aria-pressed={only === c} onClick={() => setOnly(c)}>
            {c} {c !== 'all' && <span className="rb-muted">({EXAMPLES.filter((e) => e.category === c).length})</span>}
          </button>
        ))}
      </div>
      {shown.map((e) => <ExampleCard key={e.id} e={e} />)}
    </div>
  )
}

function ExampleCard({ e }: { e: Example }) {
  const src = edits[e.id] ?? e.source
  const scope = `gallery/${e.id}`
  const names = namesFor(src, scope)
  const parts = markedIn(src, scope, names)
  const [fb, setFb] = useState(() => localStorage.getItem(FB(e.id)) ?? '')
  const [tab, setTab] = useState<'state' | 'degraded' | 'payload'>('state')
  const types = [...new Set(parts.map((p) => p.block.type))]
  return (
    <section className="rb-ex" id={`rb-ex-${e.id}`}>
      <header className="rb-ex-head">
        <b>{e.title}</b> <span className="rb-tag">{e.category}</span>
        {types.map((t) => <code key={t} className="rb-muted"> {t}</code>)}
      </header>
      <p className="rb-ex-note">{e.note}</p>
      {e.demands && e.demands.length > 0 && (
        <ul className="rb-demands">
          {e.demands.map((d, i) => <li key={i}><b>Author burden:</b> {d}</li>)}
        </ul>
      )}
      <div className="rb-ex-grid">
        <div className="rb-ex-src">
          <div className="rb-lbl">1 · Declaration (edit it; renders as you type)</div>
          <textarea
            spellCheck={false}
            value={src}
            onChange={(ev) => { edits[e.id] = ev.target.value; changed() }}
          />
          <div className="rb-row">
            {edits[e.id] !== undefined && (
              <button className="btn quiet" onClick={() => { delete edits[e.id]; changed() }}>Reset example</button>
            )}
            <button
              className="btn quiet"
              onClick={() => { parts.forEach((p) => delete store.held[p.key]); changed() }}
            >
              Clear state
            </button>
            <span className="rb-muted">
              {types.length ? '' : 'No marked block found. '}
              {TYPES_HINT}
            </span>
          </div>
        </div>
        <div className="rb-ex-live">
          <div className="rb-lbl">2 · Rendered surface (interact with it)</div>
          <Prose src={src} scope={scope} />
        </div>
      </div>
      <div className="rb-ex-tabs">
        <span className="rb-seg">
          <button className="btn quiet" aria-pressed={tab === 'state'} onClick={() => setTab('state')}>3 · Current state</button>
          <button className="btn quiet" aria-pressed={tab === 'degraded'} onClick={() => setTab('degraded')}>4 · Degraded</button>
          <button className="btn quiet" aria-pressed={tab === 'payload'} onClick={() => setTab('payload')}>5 · Send-back payload</button>
        </span>
        <pre className="rb-pre rb-ex-out">
          {parts.length === 0
            ? '(no marked block in the declaration)'
            : tab === 'state'
              ? /* every key under this example, so a composite's nested parts show too */
                (Object.keys(store.held).filter((k) => k.startsWith(scope + '/')).sort()
                  .map((k) => `${k}: ${JSON.stringify(store.held[k], null, 1)}`).join('\n')
                  || 'none: everything shown is exactly what the declaration says.')
              : tab === 'degraded'
                ? parts.map((p) => readableOf(p.block, p.key, scope, 'degraded view (what shows when no renderer can draw it)', names)).join('\n\n')
                : parts.map((p) => JSON.stringify(payloadOf(p.block, p.key, scope, names), null, 2)).join('\n\n')}
        </pre>
      </div>
      <div className="rb-ex-fb">
        <div className="rb-lbl">Your feedback on “{e.title}” (kept in this browser until you put it in the composer)</div>
        <textarea
          value={fb}
          placeholder="What worked, what didn't, what you expected…"
          onChange={(ev) => { setFb(ev.target.value); localStorage.setItem(FB(e.id), ev.target.value) }}
        />
      </div>
    </section>
  )
}

const TYPES_HINT = `Types: ${Object.keys(TYPES).join(', ')}.`
