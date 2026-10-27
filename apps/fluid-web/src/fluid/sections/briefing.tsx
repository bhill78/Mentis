/* -- Section: Daily Briefing ---------------------------------------------- */

import { useEffect } from 'react'
import { store, type BriefingItem } from '../store'
import { registerSection, type SectionBodyProps } from './registry'
import { Filters, READING, useKey } from './shared'

export type BriefingPeriod = 'morning' | 'lunch' | 'evening'

export function currentBriefingPeriod(date = new Date()): BriefingPeriod {
  const h = date.getHours()
  if (h >= 0 && h < 11) return 'morning'
  if (h >= 11 && h < 15) return 'lunch'
  return 'evening'
}

const PERIODS: { key: BriefingPeriod; label: string }[] = [
  { key: 'morning', label: 'Morning' }, { key: 'lunch', label: 'Lunch' }, { key: 'evening', label: 'Evening' },
]

function DailyBriefingZone({ options, setOption, onOpenPost, chrome }: SectionBodyProps) {
  const period = (options.period as BriefingPeriod | null | undefined) ?? null
  const onPeriodChange = (p: BriefingPeriod) => setOption('period', p)
  const briefing = useKey('coll:home:briefing', () => store.briefing)

  useEffect(() => {
    void store.loadHomeBriefing(period ?? undefined)
  }, [period])

  const activePeriod = period ?? currentBriefingPeriod()
  const items = briefing?.items ?? []

  return chrome({
    filters: <Filters label="briefing periods" className="fw-period-tabs" value={activePeriod} items={PERIODS} onPick={onPeriodChange} />,
    children: !briefing ? READING : items.length === 0 ? (
      <p className="fw-empty">No briefing items for this period.</p>
    ) : (
      <ul className="fw-briefing-list fw-home-items">
        {items.map((item: BriefingItem, i: number) => (
          <li key={item.post + ':' + i} className="fw-briefing-item">
            <button
              className="fw-briefing-card fw-home-item"
              onClick={() => onOpenPost(item.conversation, item.post)}
              data-post={item.post}
            >
              <span className="fw-briefing-line">{item.line}</span>
              <span className="fw-briefing-meta fw-go" aria-hidden="true">{'→'}</span>
            </button>
          </li>
        ))}
      </ul>
    ),
  })
}

registerSection({
  show: 'briefing', name: 'Daily Briefing', body: DailyBriefingZone,
  defaults: { period: null },
  readOptions: (o) => ({ period: (o.period as BriefingPeriod | null | undefined) ?? null }),
})
