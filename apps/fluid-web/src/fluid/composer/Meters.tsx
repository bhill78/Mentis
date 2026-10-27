/* WHAT A RUNTIME HAS LEFT, in the Fluid composer (#442 #4: capacity
 * visibility). The reading is production's (`capacityMeters`, `readAgo`,
 * `/api/capacity`, asked only once somebody looks at runtimes); the drawing
 * is a quiet bar per window with its figure beside it, so colour is never
 * the only carrier. Three honest non-answers stay apart: still being read,
 * not read, and nothing reported. */

import { capacityMeters, localServerSays, readAgo, serverName, type RuntimeCapacity } from '../../composer/execution'

export default function Meters({ runtime, capacity, loading, failed }: {
  runtime: string
  capacity: RuntimeCapacity | undefined
  loading: boolean
  failed: boolean
}) {
  if (!capacity) {
    if (loading) return <span className="fc-cap fc-cap-none" role="status">reading capacity…</span>
    return failed ? <span className="fc-cap fc-cap-none">capacity not read</span> : null
  }
  if (capacity.local) {
    // LOCAL RESOURCES, NOT QUOTA: what the model servers hold now, in words,
    // with no bar -- there is no plan for a bar to be a share of.
    const servers = capacity.local.servers
    const said = servers.map(localServerSays).join('; ')
      + (capacity.local.runningTurns != null ? `; ${capacity.local.runningTurns} local turn${capacity.local.runningTurns === 1 ? '' : 's'} running` : '')
    return (
      <span className="fc-cap fc-cap-local" role="img" aria-label={`${runtime} local resources: ${said}`} title={said}>
        {servers.map((s) => (
          <span key={s.name} className={'fc-local' + (s.reachable ? '' : ' fc-local-off')}>
            {s.reachable ? localServerSays(s).replace(/^[^:]*: /, serverName(s) + ' ') : `${serverName(s)} off`}
          </span>
        ))}
      </span>
    )
  }
  const meters = capacityMeters(capacity)
  if (!meters.length)
    return <span className="fc-cap fc-cap-none" title={capacity.why_not ?? undefined}>{capacity.plan && capacity.established ? `plan ${capacity.plan}` : 'no capacity reported'}</span>
  const age = readAgo(capacity.observed_at)
  const said = meters.map((m) => `${m.group ? m.group + ' ' : ''}${m.name}: ${m.left === null ? 'reset since reported' : `${Math.round(m.left * 100)}% left`}${m.resets ? `, resets in ${m.resets}` : ''}`).join('; ') + (age ? `; ${age}` : '')
  return (
    <span className="fc-cap" role="img" aria-label={`${runtime} capacity: ${said}`} title={said}>
      {meters.map((m) => (
        <span key={(m.group ?? '') + m.label} className={'fc-meter' + (m.level ? ' fc-' + m.level : ' fc-stale')}>
          <span className="fc-mname">{m.group ? `${m.group} ` : ''}{m.name}</span>
          <span className="fc-bar" aria-hidden="true">{m.left !== null && <span style={{ width: `${Math.round(m.left * 100)}%` }} />}</span>
          <span className="fc-pct">{m.left === null ? 'reset' : `${Math.round(m.left * 100)}%`}</span>
        </span>
      ))}
    </span>
  )
}
