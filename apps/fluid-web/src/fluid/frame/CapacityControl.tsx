/* The Classic header's capacity reading and theme control in a Fluid layer. */
import { useEffect, useRef, useState } from 'react'
import { capacityMeters, localModelSays, localServerSays, readAgo, useCapacity } from '../../composer/execution'
import Meters from '../composer/Meters'
import { Float } from '../composer/Float'
import { setTheme, useTheme, type Theme } from './look'
import { afterStartup } from '../store'

export default function CapacityControl() {
  const [open, setOpen] = useState(false)
  const [, tick] = useState(0)
  const button = useRef<HTMLButtonElement>(null)
  /* Read once the page has drawn what it opened on, or at once if opened
     before then (store.afterStartup): the ring is not what anybody came for. */
  const [wanted, setWanted] = useState(false)
  useEffect(() => { let live = true; void afterStartup().then(() => { if (live) setWanted(true) }); return () => { live = false } }, [])
  useEffect(() => { if (open) setWanted(true) }, [open])
  const cap = useCapacity(wanted)
  const theme = useTheme()
  useEffect(() => {
    const clock = window.setInterval(() => tick(n => n + 1), 30000)
    const refresh = window.setInterval(() => {
      if (document.visibilityState === 'visible') cap.reload()
    }, 300000)
    return () => { clearInterval(clock); clearInterval(refresh) }
  }, [cap.reload])
  const live = Object.values(cap.data?.capacity ?? {}).flatMap(c => capacityMeters(c)).filter(m => m.left !== null)
  const used = live.length ? Math.max(...live.map(m => 1 - m.left!)) : null
  const signal = used === null ? 'no live capacity reading' : `most-used live window: ${Math.round(used * 100)}% used`
  const close = () => { setOpen(false); button.current?.focus() }
  return <>
    <button ref={button} className="fb-ctl" data-ctl="capacity" aria-label={`Capacity: ${signal}`}
      title={`Capacity: ${signal}`} aria-haspopup="dialog" aria-expanded={open}
      onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true) } }}
      onClick={() => setOpen(v => !v)}>
      <svg className="fb-icon" width="18" height="18" viewBox="0 0 20 20" aria-hidden="true" fill="none" stroke="currentColor">
        <circle cx="10" cy="10" r="7" strokeWidth="2" opacity=".25" />
        {used !== null && <circle cx="10" cy="10" r="7" strokeWidth="2" pathLength="100" strokeDasharray={`${used * 100} 100`} transform="rotate(-90 10 10)" />}
        <path d="M10 6v4l3 2" strokeWidth="1.3" />
      </svg><span className="fb-name">Capacity</span>
    </button>
    {open && <Float at={button.current} width={440} align="end" label="Runtime capacity" className="fb-capacity" onClose={close}>
      <div onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(false) }}>
        <div className="fb-cap-head"><strong>Capacity</strong><button className="fx-ctl" autoFocus aria-disabled={cap.loading} onClick={() => { if (!cap.loading) cap.reload() }}>Refresh</button></div>
        {cap.loading && <p className="fx-faint" role="status">Reading capacity...</p>}
        {cap.error && <p role="alert">{cap.error}{cap.data && ' - showing the last reading.'}</p>}
        {Object.entries(cap.data?.capacity ?? {}).map(([runtime, capacity]) => {
          const meters = capacityMeters(capacity)
          return <section className="fb-cap-runtime" key={runtime}>
            <h3>{runtime}{capacity.plan && capacity.established ? ` - ${capacity.plan}` : ''}{capacity.local ? ' - local resources, not a subscription quota' : ''}</h3>
            <Meters runtime={runtime} capacity={capacity} loading={cap.loading} failed={!!cap.error} />
            {capacity.local && <div className="fb-cap-local">
              {capacity.local.servers.map(s => <div key={s.name}>
                <p>{localServerSays(s)}</p>
                {!s.reachable && s.why && <p className="fx-faint">{s.why}</p>}
                {(s.models ?? []).filter(m => m.loaded).map(m => <p className="fx-faint" key={m.id}>loaded: {localModelSays(m)}</p>)}
              </div>)}
              <p className="fx-faint">{capacity.local.runningTurns == null ? 'local turns running: unavailable' : `${capacity.local.runningTurns} local turn${capacity.local.runningTurns === 1 ? '' : 's'} running in MARS`}</p>
              {[...Object.entries(capacity.local.unavailable ?? {}),
                ...capacity.local.servers.flatMap(s => Object.entries(s.unavailable ?? {}).map(([k, v]) => [`${k} (${s.name})`, v] as [string, string]))]
                .map(([k, why]) => <p className="fx-faint" key={k} title={why}>{k}: unavailable</p>)}
            </div>}
            {meters.map(m => <p className="fx-faint" key={(m.group ?? '') + m.label}>{m.group ? `${m.group}: ` : ''}{m.name}: {m.stale ? 'reset since reported' : m.resets ? `resets in ${m.resets}` : 'reset time unavailable'}</p>)}
            {!capacity.established && capacity.why_not && <p className="fx-faint">{capacity.why_not}</p>}
            <p className="fx-faint">{readAgo(capacity.observed_at) ?? (capacity.observed_at ? 'read just now' : 'reading time unavailable')}</p>
          </section>
        })}
        {cap.data && !Object.keys(cap.data.capacity).length && <p>No runtimes present.</p>}
        <footer><button className="fx-row" onClick={() => setTheme(({ system: 'light', light: 'dark', dark: 'system' } as Record<Theme, Theme>)[theme])}>Light or dark: {theme}</button></footer>
      </div>
    </Float>}
  </>
}
