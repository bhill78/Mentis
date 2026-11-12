/* A LIVE RUN'S CONTROLS, IN QUIET CHAT (owner, 2026-11-11: parity with Fluid's run panel).
 *
 * Three things the server already supports for one run, each bound to THAT run's id, so
 * several Builders working at once each have their own:
 *
 * - Activity: the run's live feed (`GET /api/runs/<run>/feed`, Fluid's `useRunFeed`): what
 *   it is doing now, its latest messages and tool calls, a permission it waits on. Read only
 *   while open.
 * - Permission: the Permission Mode in force (`GET /api/runs/<run>/consent`) and the owner's
 *   change of it for operations FROM NOW ON (`POST` `{mode}`, a `consent-set` act). Nothing
 *   already answered changes; a request waiting for the owner is decided again under it.
 *   Beside the choice, compactly, HOW IT REACHES THIS RUN as the server says it (`effect`):
 *   applied at its next request, pending (when its session opens, from its next run, or
 *   restarting fresh), not enforced by its runtime, or not known here (item 5.7). The
 *   selected mode is marked by a check and weight as well as colour; what each mode means is
 *   help on hover and keyboard focus, not standing prose.
 * - Stop: `POST /api/runs/<run>/stop` (Fluid's `stopRun`): asks MARS to end this run's
 *   session. Asked twice, because it cannot be undone; the work is not marked done.
 *
 * EXECUTION MODE IS NOT A CONTROL. It is decided when the run starts and nothing changes it
 * while the run works; it is shown, in the server's words, as fixed, apart from Permission. */

import { useEffect, useId, useState } from 'react'
import { ago, post, read } from '../../api'
import { APPROVE_ALL_RISK, executionLine, type ConsentRead } from '../../fluid/runs/consent'
import { CHANGE_HELP, EXECUTION_HELP, PERMISSION_OPTIONS, effectBadge, type ChangeEffect } from './permission'
import { heardRunModes } from './records'
import { endedWords, stopRun, useRunFeed, waitingPermissions, type FeedEntry } from '../../fluid/runs/feed'
import { READ_ONLY } from '../live'
import { repairText } from '../text'

type Open = null | 'activity' | 'permission' | 'stop'

export default function RunControls({ run, who, ended }: { run: string; who: string; ended?: boolean }) {
  const [open, setOpen] = useState<Open>(null)
  if (ended) return null
  const toggle = (o: Open) => setOpen((was) => (was === o ? null : o))
  return (
    <div className="q2-runctl" aria-label={`Controls for ${who}'s run`}>
      <div className="q2-runctl-bar" role="group">
        <button type="button" aria-expanded={open === 'activity'} onClick={() => toggle('activity')}>Activity</button>
        <button type="button" aria-expanded={open === 'permission'} onClick={() => toggle('permission')}>Permission</button>
        {!READ_ONLY && <button type="button" className="q2-runctl-stop" aria-expanded={open === 'stop'} onClick={() => toggle('stop')}>Stop</button>}
      </div>
      {open === 'activity' && <Activity run={run} />}
      {open === 'permission' && <Permission run={run} />}
      {open === 'stop' && <Stop run={run} who={who} onDone={() => {}} onCancel={() => setOpen(null)} />}
    </div>
  )
}

const LAST = 8

function entryWords(e: FeedEntry): string | null {
  if (e.kind === 'tool') return `${e.status ?? 'tool'} · ${repairText(e.title ?? e.tool_kind ?? 'a tool call')}`
  if (e.kind === 'message' && e.text) return repairText(e.text).slice(-240)
  if (e.kind === 'permission') return `asked: ${repairText(e.title ?? 'a permission')}${e.outcome ? ` · ${e.outcome}` : ''}`
  if (e.kind === 'plan' && e.entries?.length) return `plan: ${e.entries.filter((p) => p.status !== 'completed').length} open of ${e.entries.length}`
  return null
}

function Activity({ run }: { run: string }) {
  const { feed, entries, error } = useRunFeed(run)
  const shown = entries.map((e) => [e, entryWords(e)] as const).filter(([, w]) => w).slice(-LAST)
  const waiting = waitingPermissions(feed)
  const ended = endedWords(feed)
  return (
    <div className="q2-runctl-pane" aria-live="polite">
      {!feed && !error && <p className="q2-runctl-note">Reading what it is doing…</p>}
      {error && <p className="q2-runctl-note">Could not read its activity: {error}</p>}
      {feed && !feed.held_here && <p className="q2-runctl-note">{feed.note ?? 'This server does not hold that run, so its live activity is not here.'}</p>}
      {feed?.activity && <p className="q2-runctl-now">Now: {repairText(feed.activity)}{feed.activity_at ? ` · ${ago(feed.activity_at)}` : ''}</p>}
      {waiting.map((p) => <p key={p.form} className="q2-runctl-note">Waiting for you: {repairText(p.summary ?? p.title ?? 'a permission')}</p>)}
      {shown.length > 0 && (
        <ol className="q2-runctl-feed">
          {shown.map(([e, w]) => <li key={e.id} className={'q2-runctl-' + e.kind}>{w}</li>)}
        </ol>
      )}
      {feed && feed.held_here && !shown.length && !feed.activity && <p className="q2-runctl-note">Nothing reported yet.</p>}
      {ended && <p className="q2-runctl-note">{ended}</p>}
    </div>
  )
}

type Read = ConsentRead & { effect?: ChangeEffect | null }

/** One piece of help, shown on hover and keyboard focus of what it describes, and read as
 *  that control's accessible description. */
function Tip({ id, children }: { id: string; children: string }) {
  return <span className="q2-tip" role="tooltip" id={id}>{children}</span>
}

function Permission({ run }: { run: string }) {
  const path = `/api/runs/${encodeURIComponent(run)}/consent`
  const uid = useId()
  const [got, setGot] = useState<Read | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirmAll, setConfirmAll] = useState(false)
  /* what the owner's last change came to, as the server answered it (it also names a
     waiting request answered under it); otherwise the server's reading of the mode in force */
  const [changed, setChanged] = useState<ChangeEffect | null>(null)
  /* what the server reads back is shown; a refused change keeps its reason on screen */
  const reread = () => read<Read>(path).then((g) => { setGot(g); heardRunModes(run, g) }).catch((e) => setError(e instanceof Error ? e.message : String(e)))
  useEffect(() => { void reread() }, [path]) // eslint-disable-line react-hooks/exhaustive-deps
  const change = async (mode: string) => {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const answer = await post<Read>(path, { mode, why: 'changed from Quiet Chat' })
      setChanged(answer?.effect ?? null)
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) }
    await reread()
    setBusy(false)
    setConfirmAll(false)
  }
  const c = got?.consent ?? null
  const x = got?.execution ?? null
  const badge = effectBadge(changed ?? got?.effect ?? null)
  const groupHelp = `${uid}-perm-help`
  return (
    <div className="q2-runctl-pane q2-perm">
      {!got && !error && <p className="q2-runctl-note">Reading its Permission…</p>}
      {error && <p className="q2-runctl-note" role="alert">Not changed: {error}</p>}
      {c && (
        <div className="q2-perm-row q2-perm-head">
          <span className="q2-perm-label" id={`${uid}-perm-label`}>Permission</span>
          <span className="q2-perm-item q2-perm-help">
            <button type="button" className="q2-perm-q" aria-label="About Permission" aria-describedby={groupHelp}>?</button>
            <Tip id={groupHelp}>{CHANGE_HELP}</Tip>
          </span>
        </div>
      )}
      {c && (
        <div className="q2-perm-row">
          <div className="q2-perm-modes" role="group" aria-labelledby={`${uid}-perm-label`} aria-describedby={groupHelp}>
            {PERMISSION_OPTIONS.map((m) => {
              const on = c.mode === m.mode
              const tip = `${uid}-perm-${m.mode}`
              return (
                <span key={m.mode} className="q2-perm-item">
                  <button type="button" className="q2-perm-opt" aria-pressed={on} aria-describedby={tip}
                    disabled={READ_ONLY || busy} data-mode={m.mode}
                    onClick={() => { if (on) return; if (m.mode === 'all') setConfirmAll(true); else void change(m.mode) }}>
                    <span className="q2-perm-mark" aria-hidden="true">{on ? '✓' : ''}</span>{m.words}
                  </button>
                  <Tip id={tip}>{(on ? 'In force. ' : '') + m.help}</Tip>
                </span>
              )
            })}
          </div>
        </div>
      )}
      {c && badge && (
        <div className="q2-perm-row"><span className="q2-perm-item q2-perm-effect-item">
          <span className="q2-perm-effect" data-state={badge.state} tabIndex={0} role="status"
            aria-describedby={`${uid}-perm-effect`}>
            <span className="q2-perm-glyph" aria-hidden="true">{badge.glyph}</span>{badge.short}
          </span>
          <Tip id={`${uid}-perm-effect`}>{badge.words}</Tip>
        </span></div>
      )}
      {confirmAll && (
        <div className="q2-runctl-confirm" role="alertdialog" aria-label="Allow all operations for this run">
          <p>{APPROVE_ALL_RISK}</p>
          <button type="button" disabled={busy} onClick={() => void change('all')}>Allow all operations</button>
          <button type="button" onClick={() => setConfirmAll(false)}>Cancel</button>
        </div>
      )}
      {x && (
        <div className="q2-perm-row q2-perm-exec">
          <span className="q2-perm-label" id={`${uid}-exec-label`}>Execution · fixed</span>
          <span className="q2-perm-item">
            <span className="q2-perm-fixed" tabIndex={0} aria-labelledby={`${uid}-exec-label ${uid}-exec-line`}
              aria-describedby={`${uid}-exec-help`} id={`${uid}-exec-line`}>
              {executionLine(x).replace(/^Execution: /, '')}
            </span>
            <Tip id={`${uid}-exec-help`}>{EXECUTION_HELP}</Tip>
          </span>
        </div>
      )}
    </div>
  )
}

function Stop({ run, who, onCancel }: { run: string; who: string; onDone: () => void; onCancel: () => void }) {
  const [state, setState] = useState<'confirm' | 'asking' | 'asked' | 'refused'>('confirm')
  const [why, setWhy] = useState<string | null>(null)
  const go = async () => {
    setState('asking')
    try {
      const got = await stopRun(run, 'stopped from Quiet Chat')
      setState(got.asked ? 'asked' : 'refused')
      setWhy(got.asked ? got.note : got.state.replace(/-/g, ' '))
    } catch (e) {
      setState('refused')
      setWhy(e instanceof Error ? e.message : String(e))
    }
  }
  return (
    <div className="q2-runctl-pane" role="alertdialog" aria-label={`Stop ${who}'s run`}>
      {state === 'confirm' && (
        <>
          <p>Stop this run of {who}? Its session is ended; what it was doing is not marked done, and this cannot be undone.</p>
          <button type="button" className="q2-runctl-stop" onClick={() => void go()}>Stop {who}'s run</button>
          <button type="button" onClick={onCancel}>Keep it running</button>
        </>
      )}
      {state === 'asking' && <p className="q2-runctl-note">Asking MARS to stop it…</p>}
      {state === 'asked' && <p className="q2-runctl-note">Stop asked{why ? `: ${why}` : ''}. Its end is recorded when the session closes.</p>}
      {state === 'refused' && <p className="q2-runctl-note">Not stopped: {why}</p>}
    </div>
  )
}
