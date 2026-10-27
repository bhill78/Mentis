/* EXPERIMENTAL: timer -- a stopwatch in a post, with an optional time box
   (timer build, package A; plan adm-4fc92741cf96, A5). Drawn the same in
   Fluid and Classic, which both draw posts through ../renderable.tsx.

   A posted timer with a usable, unique name= is the owner's own, kept by
   Mentis (../timers.ts): Start / Stop / Resume, the running clock, today
   and total, today's runs, and in box mode a countdown ring with the box
   or break and how many boxes are done today. When a box or break ends it
   says so -- a browser notification when the person allowed one, otherwise
   a banner here -- and records it; the clock goes on until it is stopped.

   CHECK-IN. Two hours into a run (or after the last Continue) it asks "Still
   going?": Continue, Stop now, or "I stopped at ..." with a time picker.
   Answered within the grace (the server's CHECKIN_GRACE), that is an answer
   in time. Past it the run is FORGOTTEN, counted only to the check-in, and
   nothing pressed later brings those hours back: "I stopped at ..." is then
   the primary answer, and the others say what they now do -- "Start fresh"
   (the forgotten run stays capped; a new run starts) and "Stop at the
   check-in".

   ABOUT. about= names what the time is spent on; each reference is a link,
   or "unresolved" when the record does not hold it (never dropped). The ⋯
   menu offers "Copy reference for an agent": ent-<post>#<name>, the only way
   an owner's request directs an agent to this timer.

   Any other timer -- unnamed, or not in a posted Turn -- is a stopwatch in
   this tab only, and says so. */
import { useEffect, useRef, useState } from 'react'
import { Ref } from '../../refs'
import type { MenuGroup, RichProps, TypeDef } from '../api'
import { spanText, timerReference, timerSpec, type TimerData } from '../spec/timer'
import * as Tm from '../timers'
import { q } from '../util'
import './timer.css'

/** Tab state, for a timer Mentis does not keep: when it was started, and
    what earlier runs in this tab added up to. */
interface LocalState { startedAt: number | null; acc: number }

const timeOf = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

/** The countdown ring: how much of this box or break is left. */
function Ring({ left, length, phase, number }: { left: number; length: number; phase: 'box' | 'break'; number: number }) {
  const r = 34, c = 2 * Math.PI * r
  const frac = length > 0 ? Math.max(0, Math.min(1, left / length)) : 0
  return (
    <div className="rb-timer-ring" data-phase={phase}>
      <svg viewBox="0 0 80 80" width="80" height="80" role="img" aria-label={`${phase === 'box' ? 'Box' : 'Break'} ${number}: ${Tm.clock(left)} left`}>
        <circle cx="40" cy="40" r={r} className="rb-timer-ring-track" />
        <circle cx="40" cy="40" r={r} className="rb-timer-ring-left" strokeDasharray={`${c * frac} ${c}`} transform="rotate(-90 40 40)" />
      </svg>
      <div className="rb-timer-ring-text">
        <b>{Tm.clock(left)}</b>
        <span>{phase === 'box' ? `box ${number}` : 'break'}</span>
      </div>
    </div>
  )
}

/** "When did you actually stop?": a time between the run's start and now. */
function StoppedAt({ run, now, busy, onSave, onCancel }: { run: Tm.Run; now: number; busy: boolean; onSave(at: string): void; onCancel(): void }) {
  const min = Tm.localInput(run.start), max = Tm.localInput(new Date(now * 1000).toISOString())
  const [value, setValue] = useState(() => Tm.localInput(run.check_in_at ?? new Date(now * 1000).toISOString()))
  const at = Tm.fromLocalInput(value)
  const ok = at !== null && value >= min && value <= max
  return (
    <form className="rb-timer-picker" onSubmit={(ev) => { ev.preventDefault(); if (ok && at) onSave(at) }}>
      <label>
        When did you actually stop?{' '}
        <input type="datetime-local" value={value} min={min} max={max} onChange={(ev) => setValue(ev.target.value)} aria-label="When you stopped" />
      </label>
      <button type="submit" className="btn primary" disabled={!ok || busy}>Save</button>
      <button type="button" className="rb-link" onClick={onCancel}>Cancel</button>
      {!ok && <span className="rb-form-problem">Between {timeOf(run.start)} (the start) and now.</span>}
    </form>
  )
}

/** What the time is spent on: each about= reference a link, or unresolved. */
function About({ refs }: { refs: Tm.AboutRef[] }) {
  if (!refs.length) return null
  return (
    <p className="rb-timer-about" data-about>
      <span className="rb-timer-about-label">About</span>{' '}
      {refs.map((a, i) => (
        <span key={a.ref + i} className="rb-timer-about-ref" data-resolved={a.resolved ? 'yes' : 'no'}>
          {i > 0 && ', '}
          {a.resolved
            ? <Ref id={a.entry ?? a.ref} label={a.label ? `${a.kind}: ${a.label}` : (a.kind ?? a.ref)} />
            : <span className="rb-timer-unresolved" title={a.why ?? 'Mentis holds no such entry'}>{a.ref} <em>(unresolved)</em></span>}
        </span>
      ))}
    </p>
  )
}

/** The timer's own ⋯ menu: copy the reference an owner gives an agent. */
function referenceMenu(reference: string, onCopied: (ok: boolean) => void): MenuGroup[] {
  return [{
    label: 'Timer',
    items: [{
      label: 'Copy reference for an agent',
      onSelect: () => {
        const done = navigator.clipboard?.writeText(reference)
        if (done) void done.then(() => onCopied(true), () => onCopied(false))
        else onCopied(false)
      },
    }],
  }]
}

function KeptTimer({ attrs, help, menu }: { attrs: Record<string, string>; help: RichProps<TimerData, LocalState>['help']; menu?: RichProps<TimerData, LocalState>['menu'] }) {
  const key = help.key
  const e = Tm.useTimer(key)
  const s = e?.state
  const nowMs = Tm.useTick(!!s?.running)
  const [picking, setPicking] = useState<string | null>(null)
  const [banner, setBanner] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const address = Tm.timerAddress(key)
  const reference = s?.reference ?? (address ? timerReference(address.post, address.block) : '')
  menu?.(reference ? referenceMenu(reference, (ok) => setCopied(ok ? `Copied ${reference}: put it in your request to an agent to let that run use this timer.` : `Copy this into your request to an agent: ${reference}`)) : [])
  const [mayNotify, setMayNotify] = useState(() => typeof Notification !== 'undefined' ? Notification.permission : 'denied')
  const handled = useRef(new Set<string>())
  const askedRead = useRef<string | null>(null)
  const p = s && e?.readAt ? Tm.project(s, e.readAt, nowMs) : null

  /* A box or break ended in this tab: say so, and record it once. */
  useEffect(() => {
    if (!p?.boxEnded || !p.current) return
    const tag = `${p.current.run}-${p.boxEnded.phase}-${p.boxEnded.number}`
    if (handled.current.has(tag)) return
    handled.current.add(tag)
    const brk = s?.break_s
    const text = p.boxEnded.phase === 'box'
      ? (brk ? `Box ${p.boxEnded.number} is done: time for a ${spanText(brk)} break.` : `Box ${p.boxEnded.number} is done.`)
      : `The break is over: box ${p.boxEnded.number + 1} starts now.`
    if (!Tm.notify(attrs.title ?? 'Timer', text)) setBanner(text)
    void Tm.markTimer(key, p.boxEnded.phase === 'box' ? 'box-end' : 'break-end', {}, `${p.boxEnded.phase}-end-${tag}`)
  }, [p?.boxEnded?.phase, p?.boxEnded?.number, p?.current?.run]) // eslint-disable-line react-hooks/exhaustive-deps

  /* The check-in came due in this tab, or its grace ran out: read again, so
     the server says it. */
  useEffect(() => {
    if (!p?.current) return
    const due = p.asking && !s?.check_in?.asking
    const lapsed = p.lapsed && s?.state !== 'forgotten'
    if (!due && !lapsed) return
    const tag = `${p.current.run}-${lapsed ? 'lapsed' : 'due'}`
    if (askedRead.current === tag) return
    askedRead.current = tag
    void Tm.readTimer(key)
  }, [p?.asking, p?.lapsed, s?.check_in?.asking, s?.state, p?.current?.run]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!e) return null
  if (!s) {
    return (
      <div className="rb-timer" aria-busy={!e.readError}>
        {e.readError ? <p className="rb-form-notice" role="alert">{e.readError}</p> : <p className="rb-timer-reading">Reading the timer…</p>}
      </div>
    )
  }
  const gone = !!s.source_deleted
  const busy = !!e.busy
  const today = s.runs.filter((r) => Date.parse(r.counted_to) >= Date.parse(s.today_from))
  const current = p?.current && p.current.state !== 'stopped' ? p.current : null
  const forgottenEarlier = s.runs.filter((r) => r.state === 'forgotten' && r !== current)
  const startLabel = today.length ? 'Resume' : 'Start'
  const picked = picking ? s.runs.find((r) => r.run === picking) : null
  const labels: Record<string, string> = s.check_in?.forgotten ? (s.check_in.labels ?? {}) : {}
  const save = async (run: Tm.Run, at: string) => {
    if (await Tm.markTimer(key, 'stop', { run: run.run, at })) setPicking(null)
  }
  return (
    <div className="rb-timer" data-state={p?.asking ? 'asking' : s.state} aria-busy={busy}>
      {gone && <p className="rb-form-notice" role="note"><b>Source deleted.</b> The post this timer is in was deleted. Its runs are kept as history, and it takes no new marks.</p>}
      {e.readError && <p className="rb-form-notice" role="alert">{e.readError}</p>}
      {banner && (
        <div className="rb-timer-banner" role="alert">
          <span>{banner}</span>
          {mayNotify === 'default' && <button className="rb-link" onClick={() => void Tm.askToNotify().then((ok) => setMayNotify(ok ? 'granted' : 'denied'))}>Tell me with a notification next time</button>}
          <button className="rb-link" aria-label="Dismiss" onClick={() => setBanner(null)}>Dismiss</button>
        </div>
      )}
      <div className="rb-timer-main">
        {p?.box && current && current.state === 'running' && <Ring left={p.box.remaining_s} length={p.box.length_s} phase={p.box.phase} number={p.box.number} />}
        <div className="rb-timer-face">
          <div className="rb-timer-clock" aria-live="off">{Tm.clock(p?.run ?? 0)}</div>
          <div className="rb-timer-sub">
            {current?.state === 'running' && !p?.asking && <>running since {timeOf(current.start)}</>}
            {current?.state === 'forgotten' && <>{current.says}</>}
            {!current && (s.runs.length ? 'stopped' : 'not started')}
          </div>
          <div className="rb-timer-totals">
            <span>Today <b>{Tm.spanWords(p?.today ?? s.today_s)}</b></span>
            <span>Total <b>{Tm.spanWords(p?.total ?? s.total_s)}</b></span>
            {s.box_s && <span>Boxes today <b>{s.boxes_today}</b></span>}
          </div>
          <About refs={s.about ?? []} />
        </div>
        <div className="rb-timer-acts">
          {!current && <button className="btn primary" disabled={busy || gone} onClick={() => void Tm.markTimer(key, 'start')}>{startLabel}</button>}
          {current?.state === 'running' && !p?.asking && <button className="btn" disabled={busy || gone} onClick={() => void Tm.markTimer(key, 'stop')}>Stop</button>}
        </div>
      </div>
      {p?.asking && current && (p.forgotten ? (
        /* FORGOTTEN: nothing pressed now counts past the check-in, so the
           real stop time comes first, and the others say what they do. */
        <div className="rb-timer-checkin" data-forgotten="yes" role="alertdialog" aria-label="Still going?">
          <p><b>Still going?</b> Nobody answered at the 2-hour check-in ({timeOf(current.check_in_at ?? current.start)}), so this run is <b>{current.says ?? 'forgotten, counted to the 2h check-in'}</b>. Only the time you really stopped counts past it.</p>
          <div className="rb-timer-checkin-acts">
            <button className="btn primary" disabled={busy || gone} onClick={() => setPicking(current.run)}>I stopped at…</button>
            <button className="btn" disabled={busy || gone} onClick={() => void Tm.markTimer(key, 'continue')}>{labels.continue ?? 'Start fresh'}</button>
            <button className="btn" disabled={busy || gone} onClick={() => void Tm.markTimer(key, 'stop')}>{labels.stop ?? 'Stop at the check-in'}</button>
          </div>
        </div>
      ) : (
        <div className="rb-timer-checkin" data-forgotten="no" role="alertdialog" aria-label="Still going?">
          <p><b>Still going?</b> It has been running for two hours.</p>
          <div className="rb-timer-checkin-acts">
            <button className="btn primary" disabled={busy || gone} onClick={() => void Tm.markTimer(key, 'continue')}>Continue</button>
            <button className="btn" disabled={busy || gone} onClick={() => void Tm.markTimer(key, 'stop')}>Stop now</button>
            <button className="btn" disabled={busy || gone} onClick={() => setPicking(current.run)}>I stopped at…</button>
          </div>
        </div>
      ))}
      {copied && <p className="rb-timer-said" role="status">{copied}</p>}
      {forgottenEarlier.map((r) => (
        <p key={r.run} className="rb-form-notice" role="note">
          A run started {new Date(r.start).toLocaleString()} was <b>{r.says}</b>.{' '}
          <button className="rb-link" disabled={busy || gone} onClick={() => setPicking(r.run)}>When did you actually stop?</button>
        </p>
      ))}
      {picked && <StoppedAt run={picked} now={p?.now ?? Date.parse(s.now) / 1000} busy={busy} onSave={(at) => void save(picked, at)} onCancel={() => setPicking(null)} />}
      {e.said && (
        <p className={e.said.ok ? 'rb-timer-said' : 'rb-form-failed'} role={e.said.ok ? 'status' : 'alert'}>
          {e.said.text}{' '}
          {!e.said.ok && e.pending && <button className="rb-link" onClick={() => void Tm.retryMark(key)}>Try again</button>}
        </p>
      )}
      {s.conflicts.length > 0 && <p className="rb-form-conflict">Two corrections of one stop disagree; it is counted to the earlier. Correct it again to settle it.</p>}
      {today.length > 0 && (
        <details className="rb-timer-runs">
          <summary>Today's runs ({today.length})</summary>
          <ol>
            {today.map((r) => (
              <li key={r.run} data-state={r.state}>
                {timeOf(r.start)}–{r.end ? timeOf(r.end) : r.state === 'running' ? 'now' : timeOf(r.counted_to)}{' '}
                <span className="rb-timer-dur">{Tm.spanWords(r === current && p ? p.run : r.seconds)}</span>
                {r.state === 'forgotten' && <> · {r.says}</>}
                {r.corrected && <> · corrected</>}
                {r.conflict && <> · two corrections disagree</>}
                {r.also_started.length > 0 && <> · started again while running</>}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  )
}

function LocalTimer({ data, state, set }: { data: TimerData; state: LocalState | undefined; set(s: LocalState | undefined): void }) {
  const st = state ?? { startedAt: null, acc: 0 }
  const now = Tm.useTick(st.startedAt !== null)
  const run = st.startedAt !== null ? (now - st.startedAt) / 1000 : 0
  const total = st.acc + run
  const cycle = data.box ? data.box + (data.brk ?? 0) : 0
  const pos = cycle && st.startedAt !== null ? run % cycle : 0
  const inBox = data.box !== null && pos < data.box
  return (
    <div className="rb-timer" data-saved="tab" data-state={st.startedAt !== null ? 'running' : 'stopped'}>
      <p className="rb-form-notice rb-kept-quiet" role="note"><b>Runs here aren't kept:</b> this timer has no name= in a posted Turn, so it is a stopwatch in this tab only.</p>
      <div className="rb-timer-main">
        {data.box && st.startedAt !== null && (
          <Ring left={inBox ? data.box - pos : cycle - pos} length={inBox ? data.box : (data.brk ?? 0)} phase={inBox ? 'box' : 'break'} number={Math.floor(run / cycle) + 1} />
        )}
        <div className="rb-timer-face">
          <div className="rb-timer-clock">{Tm.clock(run)}</div>
          <div className="rb-timer-totals"><span>In this tab <b>{Tm.spanWords(total)}</b></span></div>
          <About refs={(data.about ?? []).map((ref) => ({ ref, resolved: true, kind: null, label: null }))} />
        </div>
        <div className="rb-timer-acts">
          {st.startedAt === null
            ? <button className="btn primary" onClick={() => set({ startedAt: Date.now(), acc: st.acc })}>{st.acc ? 'Resume' : 'Start'}</button>
            : <button className="btn" onClick={() => set({ startedAt: null, acc: total })}>Stop</button>}
        </div>
      </div>
    </div>
  )
}

function TimerView({ data, attrs, state, set, help, menu }: RichProps<TimerData, LocalState>) {
  if (Tm.timerAddress(help.key)) return <KeptTimer attrs={attrs} help={help} menu={menu} />
  menu?.([])
  return <LocalTimer data={data} state={state} set={set} />
}

export const timer: TypeDef<TimerData, LocalState> = {
  ...timerSpec,
  Rich: (p) => <TimerView {...p} />,
  readable(data, a, s, help) {
    const out = [a.title ? `timer: ${q(a.title)}` : 'timer']
    if (data.box) out.push(`time box: ${spanText(data.box)}${data.brk ? `, then a ${spanText(data.brk)} break` : ''}`)
    if (data.about?.length) out.push(`about: ${data.about.join(', ')}`)
    const e = Tm.timerAddress(help.key) ? Tm.timerEntry(help.key) : null
    const st = e?.state
    if (st) {
      out.push(`kept by Mentis: today ${Tm.spanWords(st.today_s)}, total ${Tm.spanWords(st.total_s)}, ${st.runs.length} run(s); now ${st.state}`)
      for (const r of st.runs.filter((x) => x.state === 'forgotten')) out.push(`run started ${r.start}: ${r.says}`)
    } else if (e) out.push('kept by Mentis (not read yet)')
    else out.push(`not kept (a stopwatch in this tab): ${Tm.spanWords((s?.acc ?? 0))} counted here`)
    return out.join('\n')
  },
}
