/* SIDE WORK FOUND ALONG THE WAY (operating-model §6; Mark IV's "Deferred
 * work touching this turn", ui/src/surfaces/InspectSurface.tsx).
 *
 * What a run's trunk found and did not pursue: each deferred finding, who
 * found it, its generation below the original request (`depth_from_root`),
 * and whether the trunk is finished so they are due to be put to the owner.
 * Read from `/api/gravity?turn=` -- the server answers from that trunk alone
 * -- once on opening and again when the run ends, since ending is what can
 * make them due. Nothing here pursues or dismisses one: that is the owner's,
 * where reconsideration is offered.
 *
 * SAID ONLY WHEN THERE IS SOMETHING: a run that found nothing on the side
 * keeps its panel for what it is doing. */

import { useEffect, useState } from 'react'
import { read, type Gravity } from '../../api'
import { foundWords, reconsiderWords } from './gravity'

export default function SideWork({ turn, ended }: { turn: string | null | undefined; ended?: boolean }) {
  const [g, setG] = useState<Gravity | null>(null)
  useEffect(() => {
    if (!turn) return
    let live = true
    void read<Gravity>(`/api/gravity?turn=${encodeURIComponent(turn)}`)
      .then((got) => { if (live) setG(got) })
      .catch(() => {})
    return () => { live = false }
  }, [turn, ended])
  const found = g?.reconsideration?.deferred ?? g?.deferred ?? []
  if (!g || found.length === 0) return null
  const due = reconsiderWords(g)
  return (
    <details className="fr-sidework" open={!!g.reconsideration?.due_for_reconsideration}>
      <summary>Side work found along the way ({found.length})</summary>
      {due && <p className="fr-note">{due}</p>}
      <ul>
        {found.map((x) => (
          <li key={x.act} data-act={x.act}>
            <span className="fr-found-head">{foundWords(x)}</span>
            {x.because && <span className="fr-found-why">{x.because}</span>}
          </li>
        ))}
      </ul>
    </details>
  )
}
