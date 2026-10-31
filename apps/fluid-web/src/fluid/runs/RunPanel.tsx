/* WHAT AN AGENT IS DOING, WATCHED LIVE (the run panel).
 *
 * Opened from an agent's line over the composer (or a work card): its
 * messages drawn with the Markdown Renderer, its thoughts folded, each tool
 * call with its status, its plan as a checklist, and its usage -- what MARS
 * reports, through Mentis (`feed.ts`). A permission the run waits on is a
 * decision form owed by the owner on the post it works on: the panel says so
 * and opens that post, where it is answered like any decision. The
 * consent in force sits beside it (`ConsentPanel.tsx`): what proceeds without
 * asking, changed here for what comes next.
 *
 * STOP ends the agent's SESSION. The work it was doing is not marked done:
 * the record keeps it open, to be addressed again. The panel says "Stopping…"
 * until MARS has ended the turn, then how the session ended.
 *
 * Placement-free: the panel draws a run; where it sits (over the composer,
 * in a docked zone or in a floating surface) is its host's. A host that
 * frames it (SurfaceChrome: a docked run, a run's window) takes `framed`:
 * the panel hands over what it is doing now and Stop as the frame's header
 * content and draws no head of its own, so the run has one header, and its
 * Float, Close and the rest are the frame's. */

import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Prose } from '../../prose'
import { ago } from '../../api'
import { endedWords, useRunFeed, useStop, waitingPermissions, type FeedEntry } from './feed'
import { runLine } from './gravity'
import { invalidateDecisions } from '../../experimental/decisions'
import SideWork from './SideWork'
import Consent from './ConsentPanel'
import { store } from '../store'
import { useKey } from '../sections/shared'
import './runs.css'

const TOOL_MARK: Record<string, string> = { pending: '○', in_progress: '◐', completed: '●', failed: '✕' }

function Tool({ e }: { e: FeedEntry }) {
  const [open, setOpen] = useState(false)
  const detail = e.raw_input != null || e.raw_output != null || !!e.locations?.length
  return (
    <li className={'fr-tool fr-' + (e.status ?? 'pending')}>
      <button type="button" className="fr-tool-head" onClick={() => detail && setOpen(!open)} aria-expanded={detail ? open : undefined} disabled={!detail}>
        <span className="fr-tool-mark" aria-hidden>{TOOL_MARK[e.status ?? 'pending'] ?? '○'}</span>
        <span className="fr-tool-title">{e.title ?? e.tool_kind ?? 'a tool'}</span>
        <span className="fr-tool-status">{(e.status ?? 'pending').replace('_', ' ')}</span>
      </button>
      {open && (
        <div className="fr-tool-detail">
          {!!e.locations?.length && <p className="fr-paths">{e.locations.join(' · ')}</p>}
          {e.raw_input != null && <pre>{typeof e.raw_input === 'string' ? e.raw_input : JSON.stringify(e.raw_input, null, 1)}</pre>}
          {e.raw_output != null && <pre>{typeof e.raw_output === 'string' ? e.raw_output : JSON.stringify(e.raw_output, null, 1)}</pre>}
        </div>
      )}
    </li>
  )
}

function Entry({ e, run }: { e: FeedEntry; run: string }) {
  if (e.kind === 'message') return <div className="fr-message turn-body"><Prose src={e.text || ' '} scope={`run:${run}:${e.id}`} untrusted /></div>
  if (e.kind === 'thought') return <details className="fr-thought"><summary>Thinking</summary><p>{e.text}</p></details>
  if (e.kind === 'tool') return <ul className="fr-tools"><Tool e={e} /></ul>
  if (e.kind === 'permission') return <p className="fr-note">Permission for “{e.title ?? 'a tool'}”: {e.outcome === 'selected' ? 'answered' : 'refused'}{e.answered_by === 'mentis' ? ' by Mentis' : ''}</p>
  return null
}

export function StopButton({ run, compact = false, label = 'Stop' }: { run: string; compact?: boolean; label?: string }) {
  const { state, why, stop } = useStop(run)
  const words = state === 'asking' || state === 'asked' ? 'Stopping…' : state === 'refused' ? `Could not stop${why ? ': ' + why : ''}` : label
  return (
    <button type="button" className={'fr-stop' + (compact ? ' fr-compact' : '')} onClick={(ev) => { ev.stopPropagation(); void stop() }}
      disabled={state === 'asking' || state === 'asked'} title="Stop this agent's session. The work it was doing is not marked done."
      aria-label={compact ? `${words} the session` : undefined}>
      <span className="fr-stop-mark" aria-hidden>■</span>{!compact || state !== 'idle' ? <span>{words}</span> : null}
    </button>
  )
}

export default function RunPanel({ run, who, onClose, onOpenPost, onFloat, floating = false, framed }: {
  run: string
  who?: string
  onClose?: () => void
  onOpenPost?: (conversation: string, post: string, decision?: string) => void
  /** take the run out into its own floating surface (Fluid Focus) */
  onFloat?: () => void
  /** drawn in a float: its window closes it, not Esc */
  floating?: boolean
  /** drawn in a frame (SurfaceChrome): `head` is its header content (what
   *  the run is doing now, and Stop), `panel` its body, with no head */
  framed?: (head: ReactNode, panel: ReactNode) => ReactNode
}) {
  const { feed, entries, error } = useRunFeed(run)
  /* WHO RAN IT, AS WHAT, WHERE AND HOW FAR: the run as the record reads it
     (`/fluid/api/runs`), whichever host opened the panel -- the feed is what
     MARS reports and knows nothing of Personas or Task Gravity. */
  const asked = useKey('run:' + run, () => store.runs.get(run))
  useEffect(() => { void store.loadRuns([run]).catch(() => {}) }, [run])
  const body = useRef<HTMLDivElement | null>(null)
  const pinned = useRef(true)
  useEffect(() => {
    const el = body.current
    if (el && pinned.current) el.scrollTop = el.scrollHeight
  }, [entries.length, entries[entries.length - 1]?.seq])
  useEffect(() => {
    if (floating || !onClose) return
    const esc = (ev: KeyboardEvent) => { if (ev.key === 'Escape') onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose, floating])
  const plan = entries.find((e) => e.kind === 'plan')
  const usage = entries.find((e) => e.kind === 'usage')
  const shown = entries.filter((e) => e.kind !== 'plan' && e.kind !== 'usage')
  const ended = endedWords(feed)
  const running = !!feed?.held_here && !feed.ended_at
  const permissions = waitingPermissions(feed)
  const now = <span className="fr-now" role="status" aria-live="polite">
    {feed?.stop && !feed.ended_at ? 'Stopping…' : ended ?? feed?.activity ?? (feed && !feed.held_here ? 'Not held by this server' : 'Reading…')}
  </span>
  const stop = running && !feed?.stop && <StopButton run={run} />
  const parts = <>
    {asked && !asked.error && <p className="fr-asked">{runLine(asked)}</p>}
    <SideWork turn={asked?.post} ended={!!ended} />
    {asked && !asked.error && <Consent run={run} consent={asked.consent} ended={!!ended} />}
    {permissions.map((perm) => (
      <div className="fr-permission" role="alert" key={perm.form} data-permission={perm.decision}>
        <span>Waiting for you: {perm.summary ? perm.summary : <>allow “{perm.title ?? perm.kind ?? 'a tool'}”?</>}</span>
        {perm.conversation && perm.post && onOpenPost && <button type="button" className="fx-linkish" onClick={() => {
          void invalidateDecisions(perm.post!)
          onOpenPost(perm.conversation!, perm.post!, perm.decision)
        }}>Answer</button>}
      </div>
    ))}
    {plan?.entries?.length ? (
      <ol className="fr-plan" aria-label="Plan">
        {plan.entries.map((p, i) => <li key={i} className={'fr-step fr-' + p.status}>{p.content}</li>)}
      </ol>
    ) : null}
    <div className="fr-body" ref={body} onScroll={(ev) => {
      const el = ev.currentTarget
      pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    }}>
      {shown.map((e) => <Entry key={e.id} e={e} run={run} />)}
      {feed && !feed.held_here && <p className="fr-note">{feed.note}</p>}
      {error && <p className="fr-note fr-error">{error}</p>}
    </div>
    <footer className="fr-foot">
      {usage?.usage && <span className="fr-usage">{Object.entries(usage.usage).filter(([, v]) => typeof v === 'number').map(([k, v]) => `${k.replace(/_/g, ' ')} ${Number(v).toLocaleString()}`).join(' · ')}</span>}
      {feed?.activity_at && running && <span className="fr-when">{ago(feed.activity_at)}</span>}
      {ended && <span className="fr-note">The work it was doing is not marked done by this.</span>}
    </footer>
  </>
  const label = `What ${who ?? 'the agent'} is doing`
  /* framed, a region rather than a section: the frame is the surface, and a
     section in its body would read as a nested surface of its own */
  if (framed) return <>{framed(<span className="fr-head-in">{now}{stop}</span>, <div className="fr-panel fr-framed" role="region" aria-label={label}>{parts}</div>)}</>
  return (
    <section className="fr-panel" aria-label={label}>
      <header className="fr-head">
        <span className="fr-title">{who ?? 'Agent'}</span>
        {now}
        {stop}
        {onFloat && <button type="button" className="fr-close fr-float" onClick={onFloat} aria-label="Float" title="Float: watch it in its own window while you work">⇱</button>}
        {!floating && onClose && <button type="button" className="fr-close" onClick={onClose} aria-label="Close">✕</button>}
      </header>
      {parts}
    </section>
  )
}
