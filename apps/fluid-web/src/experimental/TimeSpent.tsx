/* "TIME SPENT" ON A TOPIC, A CONVERSATION OR A POST (owner addition T8).

   One line, drawn only where some timer's about= names this entry: the
   viewer's own time, summed across every such timer (the server's
   `time_spent`, GET /api/timers/about/<id>), with each timer listed with its
   post. It is one person's time, never mixed with anybody else's, and it is
   read when drawn and again on focus -- nothing is stored. Mounted in both
   shells: Classic's conversation header (the Conversation, and the Topic in
   focus) and Turn details; Fluid's conversation column, topic flow and post
   details sheet. */
import { Ref } from '../refs'
import { spanWords, useTimeSpent } from './timers'
import './TimeSpent.css'

export default function TimeSpent({ id, className }: { id: string | null | undefined; className?: string }) {
  const got = useTimeSpent(id)
  if (!got || !got.timers.length) return null
  const what = got.about.kind ?? 'this'
  return (
    <div className={`time-spent${className ? ` ${className}` : ''}`} data-time-spent={id ?? ''}>
      <details>
        <summary>
          Time spent on this {what === 'post' ? 'post' : what}: <b>{spanWords(got.total_s)}</b>
          {got.today_s > 0 && <> ({spanWords(got.today_s)} today)</>}
          <span className="time-spent-who"> · your time, from {got.timers.length} timer{got.timers.length === 1 ? '' : 's'}</span>
        </summary>
        <ul>
          {got.timers.map((t) => (
            <li key={t.reference}>
              <Ref id={t.post} label={t.title ?? t.block} /> <span className="time-spent-dur">{spanWords(t.total_s)}</span>
              {t.running && <> · running</>}
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}
