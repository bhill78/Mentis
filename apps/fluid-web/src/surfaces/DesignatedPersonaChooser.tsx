import { useState } from 'react'
import { post, type Id, type WhoRead } from '../api'
import { useMe } from '../identity'

/* ------------------------------------------------------------------------ *
 * WHICH PERSONA THIS NAME'S DIRECTLY ADDRESSED WORK USES WHEN NONE IS CHOSEN.
 *
 * The owner's ruling (2026-10-29): "Directly addressing a participant should
 * automatically use its designated Persona unless I explicitly select
 * another. This applies to all participants, not just @Caretaker."
 *
 * Mirrors RuntimeDefaultChooser: a standing declaration about the
 * Participant, kept beside it and never read from its name. Choosing writes
 * one designation and supersedes the last, so History keeps what it was;
 * "none" ends it. Only the owner may (the server refuses anybody else, and
 * that refusal is shown). What is shown is what `/api/who` reads back
 * (`designated_persona`), not what was last picked here.
 * ------------------------------------------------------------------------ */

/** A Persona the chooser can offer: only standing ones may be designated. */
export interface StandingPersona { entry: Id; summary: string }

/** The `<select>`'s value for a read: the designated Persona's id when this
 *  Participant's own designation resolves, else '' -- an intake designation
 *  is said beside it but is not ended from here. */
export const designationValue = (who: WhoRead | null | undefined): string => {
  const d = who?.designated_persona
  return d?.resolved && d.source === 'designation' && d.persona ? d.persona : ''
}

/** What the read says, in words. */
export function designationSays(who: WhoRead | null | undefined, alias: string): string {
  const d = who?.designated_persona
  if (!d) return 'This server does not say whether a Persona is designated for this name.'
  const name = d.name ?? d.persona ?? 'a Persona'
  if (d.resolved && d.source === 'designation')
    return `Work addressed directly to @${alias} is done as ${name} unless another Persona, or none, is chosen for it.`
  if (d.resolved && d.source === 'intake')
    return `No Persona is designated for @${alias}, but it carries requests addressed to nobody as ${name}, so directly addressed work is done as ${name} too unless another is chosen.`
  return d.why
    ? `No designated Persona resolves: ${d.why}. Directly addressed work is done as @${alias} itself unless a Persona is chosen.`
    : `No Persona is designated. Directly addressed work is done as @${alias} itself unless a Persona is chosen.`
}

/** The POST body for a choice: '' ends the designation (null). */
export const designationBody = (value: string, alias: string, me: Id | null) => ({
  persona: value || null,
  because: value ? `designated on @${alias}'s participant page` : `designation ended on @${alias}'s participant page`,
  attributed_to: me,
})

export default function DesignatedPersonaChooser({
  participant,
  alias,
  who,
  personas,
  onChanged,
}: {
  participant: Id
  alias: string
  /** the `/api/who` read */
  who: WhoRead | null
  /** the standing Personas (`/api/governed?kind=persona`, standing only) */
  personas: StandingPersona[]
  onChanged?: () => void
}) {
  const { me } = useMe()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const choose = async (value: string) => {
    setBusy(true)
    setError(null)
    try {
      await post(`/api/participants/${encodeURIComponent(participant)}/designated-persona`, designationBody(value, alias, me))
      onChanged?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!who) return null
  const value = designationValue(who)
  /* A designated Persona the standing list does not hold (it may be read
     before the list is) is still offered, so the select can show it. */
  const shown = value && !personas.some((p) => p.entry === value)
    ? [{ entry: value, summary: who.designated_persona?.name ?? value }, ...personas]
    : personas
  return (
    <p className="wp-runtime wp-designated">
      <label>
        Designated Persona{' '}
        <select value={value} disabled={busy || !me || !who.designated_persona} onChange={(e) => void choose(e.target.value)}>
          <option value="">{value ? 'none (ends the designation)' : 'none designated'}</option>
          {shown.map((p) => (
            <option key={p.entry} value={p.entry}>
              {p.summary || p.entry}
            </option>
          ))}
        </select>
      </label>
      <span className="wp-runtime-why">{designationSays(who, alias)}</span>
      {error && <span className="wp-error"> {error}</span>}
    </p>
  )
}
