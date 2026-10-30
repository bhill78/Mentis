import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useWorkDetail } from './api'
import type { TurnLink } from './contract'
import { openWorkOrigin, turnHref } from './navigation'
import { WorkflowSection } from './WorkflowSection'
import { useMe } from '../identity'
import './work.css'

export interface WorkDrawerProps {
  expectation: string
  /** Who is looking; '' or null is nobody, and then no decision is "yours". */
  viewer: string | null
  onClose: () => void
  /** A modal full-screen sheet now, whatever the width: the opener's layout
   *  has no room for it beside the content. At 600px or below it always is. */
  sheet?: boolean
  /** Where focus goes back to on close, when it is not what had it on open
   *  (a drawer whose content another opener replaced). */
  returnFocus?: { current: HTMLElement | null }
}

/** Typing somewhere: Escape there belongs to that field, not to the drawer. */
const typing = (el: EventTarget | null) =>
  el instanceof HTMLElement && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))

export interface DrawerShellProps {
  /** The small line above the title, e.g. the work's state. */
  kicker: ReactNode
  title: ReactNode
  /** What the close button says to a screen reader. */
  closeLabel: string
  onClose: () => void
  sheet?: boolean
  returnFocus?: { current: HTMLElement | null }
  /** What it shows; when this changes, the drawer starts again at its top, focused. */
  showing: string
  children?: ReactNode
}

/** ONE OPEN DRAWER, APP-WIDE. Whoever opened a drawer last owns it, and
 *  claiming closes the other's: the Work drawer from a pill (Compare shows
 *  two conversations), from the Ledger, and the decision drawer alike. An
 *  opener that can claim before it renders (a pill) closes the other in the
 *  same render; every `DrawerShell` claims again when it mounts, with the
 *  `onClose` it was given, so no opener can leave two drawers stacked. */
let owner: (() => void) | null = null
export function claimDrawer(close: () => void) {
  if (owner && owner !== close) owner()
  owner = close
}
export function releaseDrawer(close: () => void) {
  if (owner === close) owner = null
}
/** The shells mounted now: for the moment one replaces another, both are.
 *  The page-wide marks (`work-drawer-open`, `#root`'s `inert`) and the focus
 *  going back belong to the last one out, not to the one being replaced. */
let shells = 0
let baseInert = false

/** THE ONE DRAWER SHELL: focus in and back, Escape, the sheet's `inert` and
 *  focus trap, and closing when the reader navigates. The Work drawer and the
 *  decision drawer are both this, with different things inside. */
export function DrawerShell({ kicker, title: heading, closeLabel, onClose, sheet = false, returnFocus, showing, children }: DrawerShellProps) {
  const panel = useRef<HTMLElement>(null)
  const close = useRef<HTMLButtonElement>(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const title = useId()
  const forced = useRef(sheet)
  forced.current = sheet
  const modalNow = useRef<(() => void) | null>(null)
  useEffect(() => modalNow.current?.(), [sheet])
  const first = useRef(true)
  useEffect(() => {
    // ANOTHER PILL'S WORK IN THE SAME DRAWER: start it at its top, focused.
    if (first.current) { first.current = false; return }
    panel.current?.scrollTo?.({ top: 0 })
    close.current?.focus({ preventScroll: true })
  }, [showing])
  useEffect(() => {
    const mine = onCloseRef.current
    claimDrawer(mine)
    const previous = document.activeElement as HTMLElement | null
    const mobile = window.matchMedia('(max-width: 600px)')
    const isSheet = () => forced.current || mobile.matches
    const root = document.getElementById('root')
    if (shells++ === 0) {
      document.documentElement.classList.add('work-drawer-open')
      baseInert = root?.inert ?? false
    }
    const modal = () => {
      if (root) root.inert = isSheet() || baseInert
      panel.current?.setAttribute('aria-modal', String(isSheet()))
    }
    modalNow.current = modal
    modal()
    mobile.addEventListener('change', modal)
    close.current?.focus()
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !typing(e.target)) { e.preventDefault(); onCloseRef.current() }
      if (e.key !== 'Tab' || !isSheet()) return
      const targets = panel.current?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], textarea:not([disabled])')
      if (!targets?.length) return
      const first = targets[0], last = targets[targets.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    const moved = () => onCloseRef.current()
    window.addEventListener('keydown', key)
    window.addEventListener('popstate', moved)
    window.addEventListener('hashchange', moved)
    return () => {
      releaseDrawer(mine)
      mobile.removeEventListener('change', modal)
      modalNow.current = null
      window.removeEventListener('keydown', key)
      window.removeEventListener('popstate', moved)
      window.removeEventListener('hashchange', moved)
      // REPLACED BY ANOTHER DRAWER: that one has the page and the focus now.
      if (--shells > 0) return
      document.documentElement.classList.remove('work-drawer-open')
      if (root) root.inert = baseInert
      const back = returnFocus?.current?.isConnected ? returnFocus.current : previous
      if (back?.isConnected) back.focus({ preventScroll: true })
    }
  }, [])
  return createPortal(
    <aside className="work-drawer" data-sheet={sheet ? 'true' : undefined} role="dialog" aria-labelledby={title} ref={panel}>
      <div className="work-drawer-kicker">
        <span>{kicker}</span>
        <button ref={close} aria-label={closeLabel} onClick={onClose}>×</button>
      </div>
      <h2 id={title}>{heading}</h2>
      {children}
    </aside>, document.body,
  )
}

export default function WorkDrawer({ expectation, viewer: who, onClose, sheet = false, returnFocus }: WorkDrawerProps) {
  const viewer = who || null
  const { me } = useMe()
  const read = useWorkDetail(expectation, viewer)
  const d = read.data?.expectation === expectation ? read.data : null
  const link = (origin: TurnLink, words: string, view: 'turn' | 'replies' | 'activity' = 'turn') => (
    <a href={turnHref(origin)} onClick={(e) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      e.preventDefault()
      onClose()
      openWorkOrigin(origin, view)
    }}>{words}</a>
  )
  return (
    <DrawerShell kicker={d?.heading ?? 'WORK DETAILS'} closeLabel="Close work details" onClose={onClose}
      sheet={sheet} returnFocus={returnFocus} showing={expectation}
      title={d?.title ?? (d ? 'Work title unknown' : 'Reading the record…')}>
      {read.error && <p role="alert">Details unavailable: {read.error} <button className="work-link" onClick={read.reload}>Try again</button></p>}
      {d && <>
        <div className="work-drawer-meta">{d.origin.conversation_name ?? 'Conversation unknown'} · from Turn {link(d.origin, d.origin.number === null ? 'number unknown' : `#${d.origin.number}`)}
          {d.started_at && <> · started {time(d.started_at)}</>}</div>
        <dl className="work-kv">
          {d.stage_words && <><dt>Stage</dt><dd data-stage={d.stage}>{d.stage_words}
            {d.stage_evidence?.head && <span className="work-muted">{` · head ${d.stage_evidence.head.slice(0, 10)}`}</span>}
            {d.stage_source === 'computed-from-prose' && <span className="work-muted"> · verdict read from the review's words</span>}</dd></>}
          <dt>Completes when</dt><dd>{d.completes_when ?? d.completes_when_why ?? 'Unknown'}</dd>
          <dt>Executions</dt><dd>{d.executions_words}</dd>
          <dt>Agents</dt><dd>{d.agents.join(', ') || 'Unknown'}</dd>
        </dl>
        {d.why_unknown && <p className="work-muted">Unknown — {d.why_unknown}</p>}
        {d.decisions.filter((decision) => !decision.answered).map((decision) => <section
          className={`work-decision${viewer && decision.owed_by === viewer ? ' for-you' : ''}`} key={decision.expectation}>
          <h3>{viewer && decision.owed_by === viewer ? 'Your decision' : `Decision · ${decision.owed_by_alias ?? 'owner unknown'}`}</h3>
          <p>{decision.question ?? 'Question unknown'}</p>
          {decision.options.length > 0 && <p className="work-muted">Options: {decision.options.join(' · ')}</p>}
          {decision.origin ? <div className="work-decision-actions">{link(decision.origin, 'Decide ›')}
            {link(decision.origin, `Open the question${decision.origin.number === null ? '' : ` in #${decision.origin.number}`} ›`)}</div>
            : <p className="work-muted">Question Turn unknown</p>}
        </section>)}
        <WorkflowSection view={d.workflow} expectation={expectation} owner={!!me} onChanged={read.reload} />
        <h3 className="work-section-title">Agents and executions</h3>
        {d.agents_detail.length === 0 && <p className="work-muted">No agent details recorded.</p>}
        {d.agents_detail.map((agent) => <section className="work-agent" key={agent.participant}>
          <div className="work-agent-heading"><strong>{agent.alias ? `@${agent.alias.replace(/^@/, '')}` : 'Agent unknown'}</strong><span>{agent.state_words}</span></div>
          {agent.executions.map((execution, index) => <div className="work-execution" key={execution.execution ?? `${execution.expectation}-${index}`}>
            <span>{execution.task ?? 'Task unknown'}{execution.summary && <> — {execution.summary}</>}</span>
            <span className="work-execution-state">{execution.state.replaceAll('_', ' ')}{execution.exit_code !== null && execution.exit_code !== 0 && <> · exit {execution.exit_code}</>}</span>
          </div>)}
        </section>)}
        <h3 className="work-section-title">Outcome so far</h3>
        <p className="work-outcome">{d.outcome ?? 'No outcome recorded yet.'}</p>
        <nav className="work-drawer-links" aria-label="Work navigation">
          {link(d.origin, `Open Turn${d.origin.number === null ? '' : ` #${d.origin.number}`} ›`)}
          {link(d.origin, `Reply chain${d.replies === null ? ' (unknown)' : ` (${d.replies})`} ›`, 'replies')}
          {link(d.origin, 'Full activity ›', 'activity')}
        </nav>
      </>}
    </DrawerShell>
  )
}

function time(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export { WorkDrawer }
