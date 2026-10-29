/* The designated Persona in Fluid (the owner's ruling, 2026-10-29: "Directly
 * addressing a participant should automatically use its designated Persona
 * unless I explicitly select another. This applies to all participants, not
 * just @Caretaker."). The composer's unset choice names the designated
 * Persona and still sends null; "as themselves" is its own choice and sends
 * "none"; a chosen Persona sends its id; with no designation the words are
 * the old ones. The chip and a run's line say it; the participant page's
 * chooser posts what it reads. */
import assert from 'node:assert/strict'
import { bodyOf, emptyDraft, type Addressee } from '../src/composer/draft'
import { NO_PERSONA, designatedName, personaOptions, personaToken, unsetPersonaWords } from '../src/fluid/composer/designation'
import { tokenOf } from '../src/fluid/composer/words'
import { runLine } from '../src/fluid/runs/gravity'
import { designationBody, designationSays, designationValue } from '../src/surfaces/DesignatedPersonaChooser'
import type { DesignatedPersona, WhoRead } from '../src/api'

const designated: DesignatedPersona = { resolved: true, persona: 'ent-rev', name: 'Reviewer', source: 'designation', why: null }
const intake: DesignatedPersona = { resolved: true, persona: 'ent-care', name: 'Caretaker', source: 'intake', why: null }
const unresolved: DesignatedPersona = { resolved: false, persona: null, name: null, source: null, why: 'two designations stand' }
const personas = [{ persona: 'ent-rev', name: 'Reviewer', behaviour: 'reviews' }, { persona: 'ent-b', name: 'Builder', behaviour: 'builds' }]

const who: Addressee = { participant: 'p1', alias: '@Orbit', dispatch: true }
const spec = (a: Addressee) => bodyOf({ ...emptyDraft(), text: 'go', to: [a] }, 'p-me', []).dispatch[0] as Record<string, unknown>

/* ---- the unset button's words ---- */
assert.equal(unsetPersonaWords(designated), 'as Reviewer (designated)')
assert.equal(unsetPersonaWords(intake), 'as Caretaker (designated)')
// no designation resolves: today's words, unchanged
assert.equal(unsetPersonaWords(null), 'as themselves')
assert.equal(unsetPersonaWords(undefined), 'as themselves')
assert.equal(unsetPersonaWords(unresolved), 'as themselves')
// a resolved designation without a name is named from the Personas, never by id
assert.equal(unsetPersonaWords({ ...designated, name: null }, (id) => (id === 'ent-rev' ? 'Rev' : null)), 'as Rev (designated)')
assert.equal(designatedName({ ...designated, name: null }), 'designated Persona')

/* ---- the explicit choices ---- */
// with a designation, "as themselves" is its own choice, keyed "none", first
const withD = personaOptions(designated, personas)
assert.deepEqual(withD.map((o) => [o.key, o.label]), [['none', 'as themselves'], ['ent-rev', 'Reviewer'], ['ent-b', 'Builder']])
// without one, only the Personas, as today
assert.deepEqual(personaOptions(null, personas).map((o) => o.key), ['ent-rev', 'ent-b'])
assert.deepEqual(personaOptions(unresolved, personas).map((o) => o.key), ['ent-rev', 'ent-b'])
// a draft that already holds "none" can still show it
assert.deepEqual(personaOptions(null, personas, NO_PERSONA).map((o) => o.key), ['none', 'ent-rev', 'ent-b'])

/* ---- what each choice sends ---- */
assert.equal(NO_PERSONA, 'none')
assert.equal(spec(who).persona, null) // unset: the designated Persona
assert.equal(spec({ ...who, persona: NO_PERSONA }).persona, 'none') // explicitly none
assert.equal(spec({ ...who, persona: 'ent-b' }).persona, 'ent-b') // that Persona
// record-only still dispatches nothing
assert.deepEqual(bodyOf({ ...emptyDraft(), text: 'x', action: 'record-only', to: [{ ...who, persona: NO_PERSONA }] }, 'p-me', []).dispatch, [])

/* ---- the chip ---- */
const names = (id: string) => personas.find((p) => p.persona === id)?.name ?? null
assert.equal(personaToken(undefined, designated, names), 'Reviewer (designated)')
assert.equal(personaToken(undefined, null, names), null)
assert.equal(personaToken(NO_PERSONA, designated, names), 'as themselves')
assert.equal(personaToken('ent-b', designated, names), 'Builder')
const chip = (a: Addressee, d: DesignatedPersona | null) => tokenOf(a, [], names, () => d)
assert.equal(chip(who, designated), 'any runtime · Reviewer (designated) · asks before side work')
assert.equal(chip(who, null), 'any runtime · asks before side work')
assert.equal(chip({ ...who, persona: NO_PERSONA }, designated), 'any runtime · as themselves · asks before side work')
assert.equal(chip({ ...who, persona: 'ent-b' }, designated), 'any runtime · Builder · asks before side work')
// without the designation reader (older callers), the chip is as before
assert.equal(tokenOf(who, [], names), 'any runtime · asks before side work')
assert.equal(chip({ ...who, dispatch: false }, designated), 'addressed only')

/* ---- a run's line ---- */
assert.equal(runLine({ participant_name: '@Orbit', persona: 'ent-rev', persona_name: 'Reviewer', persona_from: 'designation' }),
  'Orbit · Reviewer (designated) · Asks before pursuing side work')
assert.equal(runLine({ participant_name: '@Orbit', persona: 'ent-care', persona_name: 'Caretaker', persona_from: 'intake' }),
  'Orbit · Caretaker (designated) · Asks before pursuing side work')
assert.equal(runLine({ participant_name: '@Orbit', persona: 'ent-b', persona_name: 'Builder', persona_from: 'chosen' }),
  'Orbit · Builder · Asks before pursuing side work')
assert.equal(runLine({ participant_name: '@Orbit', persona: 'ent-b', persona_name: 'Builder' }),
  'Orbit · Builder · Asks before pursuing side work')

/* ---- the participant page's chooser ---- */
const read = (d?: DesignatedPersona): WhoRead => ({ ref: 'p1', known: true, alias: '@Orbit', designated_persona: d })
assert.equal(designationValue(read(designated)), 'ent-rev')
assert.equal(designationValue(read(intake)), '') // intake is said, not chosen here
assert.equal(designationValue(read(unresolved)), '')
assert.equal(designationValue(read()), '')
assert.deepEqual(designationBody('ent-b', 'Orbit', 'p-me'), { persona: 'ent-b', because: "designated on @Orbit's participant page", attributed_to: 'p-me' })
// "none" ends the designation: null
assert.equal(designationBody('', 'Orbit', 'p-me').persona, null)
assert.match(designationSays(read(designated), 'Orbit'), /done as Reviewer unless another Persona, or none, is chosen/)
assert.match(designationSays(read(intake), 'Orbit'), /carries requests addressed to nobody as Caretaker/)
assert.match(designationSays(read(unresolved), 'Orbit'), /two designations stand/)
assert.match(designationSays(read(), 'Orbit'), /does not say/)

console.log('fluid designation: ok')
