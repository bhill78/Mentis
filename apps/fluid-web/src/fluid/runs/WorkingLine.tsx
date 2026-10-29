/* "@Caretaker is working · Read AGENTS.md" (#568 4.6; production's Presence
 * line), over the composer, only while somebody is.
 *
 * EACH AGENT IS A BUTTON: it opens the run panel (RunPanel.tsx) over the
 * line, with what the agent is saying and doing. Beside it, what it is doing
 * now -- its own tool's words, from what MARS reports (`/api/activity` runs'
 * `activity`) -- and Stop, for a run this server holds. The post the work is
 * on, when the record says, is still a press away.
 *
 * ONE BUTTON PER RUN, not per participant: `working` is one entry per run
 * (identity/activity.ts `live`), all of them this conversation's, so two
 * runs of @Caretaker are two buttons, each opening its own run. */

import { useState } from 'react'
import * as nav from '../nav'
import { Who } from '../identity/Who'
import { aliasOf, postOf, workingLine, workKey, type Working } from '../conversation/working'
import { workspace } from '../workspace/place'
import { floatRun } from '../focus/model'
import { onPage } from '../focus/page'
import RunPanel from './RunPanel'

/** The run of `w` this server holds and is running, if any. */
export const heldRun = (w: Working) => (w.runs ?? []).find((r) => r.held_here && r.state === 'running')
  ?? (w.runs ?? []).find((r) => r.held_here) ?? null

/** Which of several runs of one participant this is: the post it is on. */
const onWords = (w: Working) => (w.working_on?.number != null ? ` on #${w.working_on.number}` : '')

export default function WorkingLine({ working }: { working: Working[] }) {
  const [open, setOpen] = useState<string | null>(null)
  const on = working.find((a) => postOf(a))
  const go = () => {
    const w = on?.working_on
    if (w && w.conversation) nav.read(w.conversation, w.turn, w.number)
  }
  const shown = working.slice(0, 3)
  const openRun = open ? working.flatMap((w) => (w.runs ?? []).map((r) => ({ w, r }))).find((x) => x.r.run === open) : null
  const twice = (w: Working) => working.filter((x) => x.participant === w.participant).length > 1
  return (
    <>
      {openRun && (
        <RunPanel run={openRun.r.run} who={aliasOf(openRun.w) + (twice(openRun.w) ? onWords(openRun.w) : '')} onClose={() => setOpen(null)}
          onOpenPost={(c, p, decision) => nav.read(c, p, decision ? { decision } : null)}
          onFloat={() => {
            const who = aliasOf(openRun.w) + (twice(openRun.w) ? onWords(openRun.w) : '')
            const main = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
            const W = main?.width ?? 1200
            workspace.edit(onPage((a) => floatRun(a, openRun.r.run, who, { x: Math.max(0, W - 400), y: 40, w: 360, h: 300 })),
              `${who}'s run floats; it keeps going there while you work.`)
            setOpen(null)
          }} />
      )}
      <p className="fx-working" role="status" aria-live="polite">
        {shown.map((w) => {
          const r = heldRun(w)
          const one = working.length === 1
          if (!r) return <Who key={workKey(w)} id={w.participant} name={w.alias} show="avatar" size={16} working />
          return (
            <span key={workKey(w)} className="fr-agent-wrap" data-run={r.run}>
              <button type="button" className="fr-agent" aria-expanded={open === r.run}
                title={`See what ${aliasOf(w)}${onWords(w)} is doing${r.activity ? ` · ${r.activity}` : ''}`} onClick={() => setOpen(open === r.run ? null : r.run)}>
                <Who id={w.participant} name={w.alias} show="avatar" size={16} working />
                {one && <span>{workingLine(working)}</span>}
                {one && r.activity && <span className="fr-doing">· {r.activity}</span>}
                {r.permission && <span className="fr-waits">· waiting for you</span>}
              </button>
              {r.stopping && <span className="fr-doing">Stopping…</span>}
            </span>
          )
        })}
        {!(working.length === 1 && heldRun(working[0])) && workingLine(working)}
        {on?.working_on?.number != null && <> on <button className="fx-linkish fx-working-on" onClick={go}>#{on.working_on.number}</button></>}
      </p>
    </>
  )
}
