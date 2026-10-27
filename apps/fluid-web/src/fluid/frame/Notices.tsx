/* THE TOASTS FOR RESULTS AND REQUESTS (D2): Classic's Toasts.tsx behaviour in
 * Fluid's frame. What they say and when is frame/notifications.ts.
 *
 * Under the bar at the right, where nothing being written is covered (the
 * composer is at the bottom; Fluid's own "Done · Undo" toast is at the bottom
 * right). At most three. Each stays 6 s unless the pointer or the keyboard is
 * on it -- hover or focus stops its clock, leaving starts what was left.
 * Esc dismisses the one in focus; choosing one goes to the post. */

import { useEffect, useRef, useState } from 'react'
import { Who } from '../identity/Who'
import type { Id } from '../store'
import { dismissNotice, useNotifications, useToasts, type Notice } from './notifications'

const LIFE_MS = 6000
const noun = (n: Notice) => (n.kind === 'result' ? (n.more === 1 ? 'result' : 'results') : n.more === 1 ? 'request' : 'requests')

export default function Notices({ me, here, onOpen }: { me: Id | null; here: Id | null; onOpen: (n: Notice) => void }) {
  useNotifications(me, here)
  const toasts = useToasts()
  return (
    <section className="fx-notices" aria-label="Notifications">
      <ol className="fx-notices-stack" aria-live="polite" aria-relevant="additions text">
        {toasts.map((t) => <Note key={t.key} t={t} onOpen={(n) => { dismissNotice(n.key); onOpen(n) }} />)}
      </ol>
    </section>
  )
}

function Note({ t, onOpen }: { t: Notice; onOpen: (n: Notice) => void }) {
  const [held, setHeld] = useState({ hover: false, focus: false })
  const left = useRef(LIFE_MS)
  useEffect(() => {
    if (held.hover || held.focus) return
    const from = Date.now()
    const timer = window.setTimeout(() => dismissNotice(t.key), left.current)
    return () => {
      window.clearTimeout(timer)
      left.current = Math.max(1500, left.current - (Date.now() - from))
    }
  }, [held.hover, held.focus, t.key])
  const burst = t.more > 0 ? `${t.more} more ${noun(t)} in ${t.convName}` : null
  return (
    <li className={'fx-notice fx-notice-' + t.kind} data-kind={t.kind}
      onMouseEnter={() => setHeld((h) => ({ ...h, hover: true }))}
      onMouseLeave={() => setHeld((h) => ({ ...h, hover: false }))}
      onFocus={() => setHeld((h) => ({ ...h, focus: true }))}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setHeld((h) => ({ ...h, focus: false })) }}
      onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); dismissNotice(t.key) } }}>
      <button className="fx-notice-go" onClick={() => onOpen(t)} title="Go to it">
        <span className="fx-notice-kind">{t.kind === 'result' ? 'Result' : 'For you'}</span>
        <span className="fx-notice-head">
          {t.actor && t.actorAlias ? <Who id={t.actor} name={t.actorAlias} show="avatar" size={18} /> : null}
          <span>{t.headline}</span>
        </span>
        <span className="fx-notice-where">in {t.where}</span>
        {t.excerpt && <span className="fx-notice-said">{t.excerpt}</span>}
        {burst && <span className="fx-notice-more">{burst}</span>}
      </button>
      <button className="fx-notice-x" aria-label={`Dismiss: ${t.headline}`} title="Dismiss" onClick={() => dismissNotice(t.key)}>×</button>
    </li>
  )
}
