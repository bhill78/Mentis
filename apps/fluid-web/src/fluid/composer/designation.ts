/* THE ADDRESSEE'S DESIGNATED PERSONA, SAID WHERE THE CHOICE IS MADE.
 *
 * The owner's ruling (2026-10-29): "Directly addressing a participant should
 * automatically use its designated Persona unless I explicitly select
 * another. This applies to all participants, not just @Caretaker."
 *
 * So the dispatch spec's `persona` has three answers, and the server resolves
 * them, not this file:
 *   null        nothing chosen -> the participant's designated Persona, if one
 *               resolves; with none, the agent works as itself, as before
 *   a Persona   that Persona, chosen by the owner
 *   "none"      explicitly no Persona: as themselves, designation or not
 *
 * What this file does is SAY it. The designation is read from `/api/who`
 * (`designated_persona`), never guessed from a name, and where it does not
 * resolve the words are exactly the old ones -- "as themselves" -- because
 * that is then what null means. */

import type { DesignatedPersona, Id } from '../../api'

/** The dispatch spec's explicit "no Persona". */
export const NO_PERSONA = 'none'

/** The designated Persona's name when one resolves, else null. A resolved
 *  designation whose name the server could not give is still said, as the
 *  name `personaName` finds or plainly "designated Persona", never its id. */
export function designatedName(d: DesignatedPersona | null | undefined, personaName?: (id: Id) => string | null): string | null {
  if (!d?.resolved || !d.persona) return null
  return d.name || personaName?.(d.persona) || 'designated Persona'
}

/** The unset choice's words: what sending null will do. */
export function unsetPersonaWords(d: DesignatedPersona | null | undefined, personaName?: (id: Id) => string | null): string {
  const name = designatedName(d, personaName)
  return name ? `as ${name} (designated)` : 'as themselves'
}

export interface PersonaOption { key: string; label: string; note?: string }

/** The explicit choices beside the unset one. "as themselves" is offered as
 *  its own choice ("none") only where the unset one no longer means that --
 *  a designation resolves -- or where it was already chosen, so a draft
 *  holding it can always show it. */
export function personaOptions(
  d: DesignatedPersona | null | undefined,
  personas: { persona: Id; name: string; behaviour?: string }[],
  chosen?: string,
): PersonaOption[] {
  const own = designatedName(d) !== null || chosen === NO_PERSONA
    ? [{ key: NO_PERSONA, label: 'as themselves', note: 'explicitly no Persona, even though one is designated' }]
    : []
  return [...own, ...personas.map((p) => ({ key: p.persona, label: p.name, note: p.behaviour?.slice(0, 60) }))]
}

/** The chip's Persona words, or null when there is nothing to say: an
 *  explicit choice is named, an explicit "none" says so where a designation
 *  would otherwise apply, and nothing chosen names the designated Persona. */
export function personaToken(
  persona: string | undefined,
  d: DesignatedPersona | null | undefined,
  personaName?: (id: Id) => string | null,
): string | null {
  if (persona === NO_PERSONA) return 'as themselves'
  if (persona) return personaName?.(persona) ?? 'persona'
  const name = designatedName(d, personaName)
  return name ? `${name} (designated)` : null
}
