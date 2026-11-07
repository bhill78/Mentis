/* WHOSE POSTS TO SHOW, as a hover-style strip of faces rather than a form
 * control (round 4, track A; the owner's request; UX #712, E3).
 *
 * THE DROPDOWN IS GONE FROM THE COMPOSER. Choosing who is being talked to is
 * `@` now (composer/Composer.tsx); choosing whose posts to READ is this, and
 * the two were never the same decision. A <select> could show one name at a
 * time, said nothing about who is working, and sat in the composer's row
 * competing with the words being written.
 *
 * ONLY WHO IS ACTIVE, EVERYONE ON HOVER -- Fluid's own WhoStrip
 * (fluid/conversation/Column.tsx, conversation.css §E3), reproduced here with
 * Quiet's spacing. At rest the strip shows who is working now, ringed, and
 * whoever the posts are being filtered by, then "+N" for the rest; with nobody
 * working and nobody chosen it is "All +N" and nothing more. Hover OR KEYBOARD
 * FOCUS opens it out to everyone -- hover alone would make the rest of the
 * conversation unreachable without a pointer, which is not a filter anybody
 * could use. A press shows or hides someone; a double press shows only theirs;
 * All is everyone.
 *
 * The faces are Fluid's one drawing of a person (`Who`, identity/Who.tsx), so
 * a name looks the same here, in a post and in Fluid. Who is working is the
 * one activity reader's (identity/activity.ts) -- the record's live
 * executions, never guessed from prose.
 *
 * NOT MOUNTED HERE. This module is a declared seam: the integrator mounts it
 * where the reading column's own header is, and filters the stream with
 * `filterTurns`. */

import type { Conversation, Id } from '../../api'
import { live, useActivity } from '../../fluid/identity/activity'
import { Who } from '../../fluid/identity/Who'
import { setWhoFilter, useWhoFilter } from './who'
import './filter.css'

export { clearWhoFilters, filterTurns, setWhoFilter, useWhoFilter, whoFilter } from './who'

export function WhoFilter({ conversation, facts, hidden = 0 }: {
  conversation: Id
  /** the conversation's read; null while it is still being read */
  facts: Conversation | null
  /** how many posts the filter is currently hiding, where the caller counts */
  hidden?: number
}) {
  const who = useWhoFilter(conversation)
  /* Working HERE, by the record: a run whose own conversation is this one, or
     whose post is. A participant's every run elsewhere is not work here. */
  const activity = useActivity()
  const working = new Set(live(activity)
    .filter((a) => a.conversation === conversation || a.working_on?.conversation === conversation)
    .map((a) => a.participant))
  const people = facts?.participants ?? []
  const all = people.map((p) => p.participant)
  /* NOTHING TO FILTER BY is not a control: one voice needs no chooser. */
  if (people.length < 2) return null
  const shows = (p: Id) => !who.length || who.includes(p)
  const active = (p: Id) => working.has(p) || who.includes(p)
  const toggle = (p: Id) => {
    const next = new Set(who.length ? who : all)
    if (next.has(p)) next.delete(p)
    else next.add(p)
    setWhoFilter(conversation, next, all)
  }
  /* Working first, then the rest in the conversation's own order. */
  const order = [...people.filter((p) => working.has(p.participant)),
    ...people.filter((p) => !working.has(p.participant))]
  const rest = people.filter((p) => !active(p.participant)).length
  return (
    <div className="qc-who" role="group" aria-label="Show posts by" data-working={working.size}>
      <button type="button" className="qc-who-all" aria-pressed={!who.length}
        title="Show everyone's posts" onClick={() => setWhoFilter(conversation, [], all)}>All</button>
      <div className="qc-who-scroll">
        {order.map((p) => {
          const name = p.alias.replace(/^@/, '')
          const on = working.has(p.participant)
          return (
            <button key={p.participant} type="button" data-author={p.participant}
              className={'qc-who-chip' + (active(p.participant) ? ' qc-who-active' : '')}
              data-working={on || undefined} aria-pressed={shows(p.participant)}
              aria-label={`${name}${on ? ', working now' : ''}`}
              title={`${name}${on ? ' · working now' : ''}: press to ${shows(p.participant) && who.length ? 'hide' : 'show'} their posts; double press for only theirs`}
              onClick={() => toggle(p.participant)}
              onDoubleClick={() => setWhoFilter(conversation, [p.participant], all)}>
              <Who id={p.participant} name={p.alias} show="avatar" size={20} working={on} />
            </button>
          )
        })}
      </div>
      {rest > 0 && <span className="qc-who-rest" aria-hidden="true"
        title="Everyone: hover, or move into the strip with the keyboard">+{rest}</span>}
      {hidden > 0 && <span className="qc-who-hidden"
        title={`${hidden} ${hidden === 1 ? 'post is' : 'posts are'} hidden`}>{hidden} hidden</span>}
    </div>
  )
}

export default WhoFilter
