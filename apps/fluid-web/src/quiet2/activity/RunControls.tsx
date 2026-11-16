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
import { callState, feedTree, nativeWorkerLimit, recordedEntries, usageLines, workerLine, type FeedNode, type Recorded, type RunEnd } from './hierarchy'
import { READ_ONLY } from '../live'
import { repairText } from '../text'

type Open = null | 'activity' | 'permission' | 'stop'

export default function RunControls({ run, who, ended, runtime }: { run: string; who: string; ended?: boolean; runtime?: string | null }) {
  const [open, setOpen] = useState<Open>(null)
  /* AN ENDED RUN keeps what can still be read of it: its activity, with its
     native workers and what it used. Permission and Stop are a live run's. */
  if (ended) return (
    <div className="q2-runctl" aria-label={`What ${who}'s run did`}>
      <div className="q2-runctl-bar" role="group">
        <button type="button" aria-expanded={open === 'activity'} onClick={() => setOpen(open === 'activity' ? null : 'activity')}>Activity</button>
      </div>
      {open === 'activity' && <Activity run={run} runtime={runtime} />}
    </div>
  )
  const toggle = (o: Open) => setOpen((was) => (was === o ? null : o))
  return (
    <div className="q2-runctl" aria-label={`Controls for ${who}'s run`}>
      <div className="q2-runctl-bar" role="group">
        <button type="button" aria-expanded={open === 'activity'} onClick={() => toggle('activity')}>Activity</button>
        <button type="button" aria-expanded={open === 'permission'} onClick={() => toggle('permission')}>Permission</button>
        {!READ_ONLY && <button type="button" className="q2-runctl-stop" aria-expanded={open === 'stop'} onClick={() => toggle('stop')}>Stop</button>}
      </div>
      {open === 'activity' && <Activity run={run} runtime={runtime} />}
      {open === 'permission' && <Permission run={run} />}
      {open === 'stop' && <Stop run={run} who={who} onDone={() => {}} onCancel={() => setOpen(null)} />}
    </div>
  )
}

const LAST = 8

function entryWords(e: FeedEntry, end: RunEnd = { ended: false, cancelled: false }): string | null {
  if (e.kind === 'tool') return `${callState(e.status, end, e.open_at_end)} · ${repairText(e.title ?? e.tool_kind ?? 'a tool call')}`
  if (e.kind === 'message' && e.text) return repairText(e.text).slice(-240)
  if (e.kind === 'permission') return `asked: ${repairText(e.title ?? 'a permission')}${e.outcome ? ` · ${e.outcome}` : ''}`
  if (e.kind === 'plan' && e.entries?.length) return `plan: ${e.entries.filter((p) => p.status !== 'completed').length} open of ${e.entries.length}`
  return null
}

/** How many of a native worker's own calls are listed when it is opened. */
const CHILDREN = 12

/** A NATIVE WORKER (a Claude sub-agent) in the run's feed: one line, closed by
 *  default once it has ended, opening to its own tool calls, the permissions
 *  it asked for and what it handed back. It is a tool call of this run. */
function WorkerItem({ node, end }: { node: FeedNode; end: RunEnd }) {
  const e = node.entry
  const state = callState(e.status, end, e.open_at_end)
  const live = state === 'running' || state === 'pending'
  const [open, setOpen] = useState<boolean | null>(null)
  const shown = open ?? live
  const kids = node.children
  const result = typeof e.raw_output === 'string' ? e.raw_output : e.raw_output != null ? JSON.stringify(e.raw_output) : null
  return (
    <li className="q2-runctl-worker" data-state={state}>
      <button type="button" className="q2-runctl-worker-head" aria-expanded={shown} onClick={() => setOpen(!shown)}>
        <span className="q2-runctl-caret" aria-hidden="true">{shown ? '▾' : '▸'}</span>
        {workerLine(e.title ? repairText(e.title) : null, e.worker ?? {}, state, kids.filter((k) => k.entry.kind === 'tool').length)}
      </button>
      {shown && (
        <ol className="q2-runctl-feed q2-runctl-nested">
          {kids.length > CHILDREN && <li className="q2-runctl-note">{kids.length - CHILDREN} earlier not shown</li>}
          {kids.slice(-CHILDREN).map((k) => <FeedItem key={k.entry.id} node={k} end={end} />)}
          {!kids.length && <li className="q2-runctl-note">{e.worker?.event ? 'This runtime does not expose its tool calls.' : live ? 'No tool call of its own reported yet.' : 'It reported no tool call of its own.'}</li>}
          {result && !live && <li className="q2-runctl-result">Handed back: {repairText(result).slice(0, 600)}</li>}
        </ol>
      )}
    </li>
  )
}

function FeedItem({ node, end }: { node: FeedNode; end: RunEnd }) {
  const e = node.entry
  if (e.kind === 'tool' && e.worker) return <WorkerItem node={node} end={end} />
  const words = entryWords(e, end)
  if (!words) return null
  return <li className={'q2-runctl-' + e.kind}>{words}{node.orphan ? ' · of a native sub-agent no longer listed' : ''}</li>
}

function Activity({ run, runtime }: { run: string; runtime?: string | null }) {
  const { feed, entries: held, error } = useRunFeed(run)
  /* a run this server no longer holds is read from what its end act recorded */
  const recorded = feed && !feed.held_here && feed.recorded ? (feed.recorded as Recorded) : null
  const entries = recorded ? recordedEntries(recorded) : held
  const end: RunEnd = { ended: !!feed?.ended_at || !!recorded, cancelled: !!feed?.stop || feed?.outcome?.stop_reason === 'cancelled' || recorded?.stop_reason === 'cancelled' }
  const tree = feedTree(entries).filter((n) => (n.entry.kind === 'tool' && n.entry.worker) || entryWords(n.entry, end))
  const workers = tree.filter((n) => n.entry.kind === 'tool' && n.entry.worker)
  /* every native worker stays listed; of the run's own entries, the latest */
  const own = tree.filter((n) => !(n.entry.kind === 'tool' && n.entry.worker)).slice(-LAST)
  const shown = tree.filter((n) => workers.includes(n) || own.includes(n))
  const waiting = waitingPermissions(feed)
  const ended = endedWords(feed)
  const used = usageLines(entries)
  /* what this runtime does not expose of its native workers, said once */
  const limit = nativeWorkerLimit(runtime)
  return (
    <div className="q2-runctl-pane" aria-live="polite">
      {!feed && !error && <p className="q2-runctl-note">Reading what it is doing…</p>}
      {error && <p className="q2-runctl-note">Could not read its activity: {error}</p>}
      {feed && !feed.held_here && !recorded && <p className="q2-runctl-note">{feed.note ?? 'This server does not hold that run, so its live activity is not here.'}</p>}
      {recorded && <p className="q2-runctl-note">From the run's recorded end: this server no longer holds its live activity.</p>}
      {feed?.activity && !end.ended && <p className="q2-runctl-now">Now: {repairText(feed.activity)}{feed.activity_at ? ` · ${ago(feed.activity_at)}` : ''}</p>}
      {waiting.map((p) => <p key={p.form} className="q2-runctl-note">Waiting for you: {repairText(p.summary ?? p.title ?? 'a permission')}</p>)}
      {shown.length > 0 && (
        <ol className="q2-runctl-feed">
          {shown.map((n) => <FeedItem key={n.entry.id} node={n} end={end} />)}
        </ol>
      )}
      {feed && (feed.held_here || recorded) && limit && (shown.length > 0 || end.ended) && <p className="q2-runctl-note q2-runctl-limit">{limit}</p>}
      {used.map((line) => <p key={line} className="q2-runctl-note q2-runctl-usage">{line}</p>)}
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
