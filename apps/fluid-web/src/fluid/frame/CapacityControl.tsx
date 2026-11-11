/* The Classic header's capacity reading and theme control in a Fluid layer. */
import { useEffect, useRef, useState } from 'react'
import { capacityMeters, localModelSays, localServerSays, readAgo, serverName, useCapacity } from '../../composer/execution'
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
          const unavailable = [...Object.entries(capacity.local?.unavailable ?? {}),
            ...(capacity.local?.servers ?? []).flatMap(s => Object.entries(s.unavailable ?? {}).map(([k, v]) => [`${k} (${s.name})`, v] as [string, string]))]
          return <section className="fb-cap-runtime" key={runtime}>
            <h3>
              {runtime}
              {capacity.plan && capacity.established && <span className="fb-cap-tag">{capacity.plan}</span>}
              {capacity.local && <span className="fb-cap-tag">local</span>}
              <span className="fb-cap-age">{readAgo(capacity.observed_at) ?? (capacity.observed_at ? 'just now' : '')}</span>
            </h3>
            <Meters runtime={runtime} capacity={capacity} loading={cap.loading} failed={!!cap.error} />
            {meters.length > 0 && <div className="fb-cap-resets">
              {meters.map(m => <span key={(m.group ?? '') + m.label} title={m.stale ? 'reset since reported' : m.resets ? `resets in ${m.resets}` : 'reset time unavailable'}>
                {m.group ? `${m.group} ` : ''}{m.name}: {m.stale ? 'reset' : m.resets ?? '?'}
              </span>)}
            </div>}
            {capacity.local && <div className="fb-cap-stats">
              {capacity.local.servers.map(s => {
                const loaded = (s.models ?? []).filter(m => m.loaded)
                return <div className="fb-cap-stat" key={s.name} title={[localServerSays(s), s.why, ...loaded.map(localModelSays)].filter(Boolean).join(' · ')}>
                  <span className="fb-cap-stat-value">{s.reachable ? `${loaded.length}/${(s.models ?? []).length}` : 'off'}</span>
                  <span className="fb-cap-stat-label">{serverName(s)}</span>
                </div>
              })}
              <div className="fb-cap-stat">
                <span className="fb-cap-stat-value">{capacity.local.runningTurns ?? '?'}</span>
                <span className="fb-cap-stat-label">local turns</span>
              </div>
            </div>}
            {unavailable.length > 0 && <p className="fx-faint" title={unavailable.map(([, why]) => why).join(' · ')}>
              unavailable: {unavailable.map(([k]) => k).join(', ')}
            </p>}
            {!capacity.established && capacity.why_not && <p className="fx-faint">{capacity.why_not}</p>}
          </section>
        })}
        {cap.data && !Object.keys(cap.data.capacity).length && <p>No runtimes present.</p>}
        <footer><button className="fx-row" onClick={() => setTheme(({ system: 'light', light: 'dark', dark: 'system' } as Record<Theme, Theme>)[theme])}>Light or dark: {theme}</button></footer>
      </div>
    </Float>}
  </>
}
