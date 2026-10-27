import { useMemo } from 'react'
import type { Id } from './api'
import type { PresentationStore } from './picture/store'

/* ------------------------------------------------------------------------ *
 * WHICH ATMOSPHERE THIS CANVAS IS IN, AND WHERE THAT CHOICE LIVES.
 *
 * ---------------------------------------------------------------------- *
 * THE DURABLE FACT THIS PASS REFUSED TO INVENT.
 *
 * Mentis's substrate is a generic entry/link corpus: `create_and_establish`
 * writes an entry of some `kind` with an arbitrary body, and a `scoped-to`
 * Link places it at a Conversation. A theme COULD be written that way
 * without a new table — `tests/test_web.py::test_the_ui_added_no_schema`
 * would still pass, because it counts tables and this would add none.
 *
 * It is still the wrong thing to do tonight, for three reasons found by
 * reading the substrate rather than by guessing at it:
 *
 *   1. `create_and_establish` ESTABLISHES. Every entry written that way is
 *      established knowledge and is returned by `entries_of_kind`. A colour
 *      preference is not knowledge, and making it one would put presentation
 *      into retrieval — exactly what this experiment is required not to do.
 *   2. The only Conversation-scoped kind that exists is
 *      `conversation-instruction`, whose own docstring calls it "durable
 *      behavioural material placed at one Conversation". Material placed
 *      there is DELIVERED TO AGENTS. A theme must not reach an agent.
 *   3. There is no `preference`, `presentation` or `setting` kind, and
 *      minting one — plus the API route to read and write it — is inventing
 *      a durable subsystem overnight, which is what was ruled out.
 *
 * SO THE MISSING DURABLE FACT WAS NAMED RATHER THAN FAKED: *Mentis had no
 * place to record a per-Conversation presentation preference that is not
 * also knowledge or behaviour.* For a while the choice lived in the browser.
 *
 * IT HAS ONE NOW (owner-approved, docs/design/presentation-store.md): the
 * brain's `presentation/` folder, beside the record and outside it, read and
 * written through `/api/presentation` (picture/store.ts). The three reasons
 * above are why it is a folder and not an Entry. So a choice made on one
 * device is the choice on every device. The per-Conversation defaults still
 * live in configuration.
 *
 * ---------------------------------------------------------------------- *
 * THE INHERITANCE MODEL.
 *
 *     Brain default  →  Conversation default (configured)  →  owner override
 *
 * Entering a Conversation restores whichever of those applies to it, so
 * moving between Conversations changes the atmosphere and moving back
 * restores it. Nothing is remembered about a Conversation except what the
 * owner explicitly chose for it.
 * ------------------------------------------------------------------------ */

export type BuiltIn =
  | 'default'
  | 'saltmarsh'
  | 'research'
  | 'development'
  | 'mist'
  | 'tidewater'
  | 'nightfall'
  | 'shoal'
  | 'downland'
  | 'monolith'
  | 'hailmary'

/** A look made from somebody's own picture (picture/): its CSS is written at
 *  run time by picture/store.ts, under this same attribute. */
export type Atmosphere = BuiltIn | `look-${string}`

export const ATMOSPHERES: { id: BuiltIn; name: string; says: string }[] = [
  { id: 'default', name: 'Mentis', says: 'the default canvas' },
  { id: 'saltmarsh', name: 'Harbour', says: 'dark, coastal, lantern-lit' },
  { id: 'research', name: 'Paper', says: 'warm, ruled, for reading evidence' },
  { id: 'development', name: 'Workshop', says: 'graphite and grid, for building' },
  /* THE BACKDROP CASES. One composed entirely in CSS and one carrying a real
     image file — together they show that an atmosphere may be a place, not
     only a palette, and that a plain one stays plain. */
  { id: 'mist', name: 'Mist', says: 'cool, abstract, a lot of air' },
  { id: 'tidewater', name: 'Tidewater', says: 'an aerial shore, photographed' },
  { id: 'nightfall', name: 'Nightfall', says: 'a night sky, almost unveiled' },
  { id: 'shoal', name: 'Shoal', says: 'a pale ground, and dark words on it' },
  { id: 'downland', name: 'Downland', says: 'an obelisk on a hill, last light' },
  { id: 'monolith', name: 'Monolith', says: 'a black tower in a storm sky' },
  { id: 'hailmary', name: 'Hail Mary', says: 'a red ship, and a green world' },
]

/** CONFIGURED DEFAULTS, NOT DURABLE STATE. What a conversation looks like
 *  before anybody chooses anything, matched on the name the corpus already
 *  carries. It is configuration in the same sense a stylesheet is: shipped
 *  with the interface, identical for everybody, and recorded nowhere. */
const CONFIGURED: { match: RegExp; atmosphere: Atmosphere }[] = [
  { match: /saltmarsh|harbour|tavern/i, atmosphere: 'saltmarsh' },
  { match: /electrolyte|research|stud(y|ies)|lab/i, atmosphere: 'research' },
  { match: /mark iv|interface|build|implementation|ui/i, atmosphere: 'development' },
  { match: /tidewater|estuary|offshore|marine/i, atmosphere: 'tidewater' },
  { match: /post-mortem|night|deep sky|cosmo/i, atmosphere: 'nightfall' },
  { match: /shoal|shallows|survey|pipeline/i, atmosphere: 'shoal' },
  { match: /enclosure|thermal model|sweep/i, atmosphere: 'mist' },
]

export const configuredFor = (name: string | null | undefined): Atmosphere | null => {
  if (!name) return null
  return CONFIGURED.find((c) => c.match.test(name))?.atmosphere ?? null
}

export interface Atmospheres {
  /** what this conversation resolves to, and why */
  resolve: (id: Id | null, name: string | null) => { at: Atmosphere; explicit: boolean }
  /** the Brain default, which every conversation inherits unless it is
   *  configured otherwise or the owner has chosen for it */
  brain: Atmosphere
  setBrain: (a: Atmosphere) => Promise<void>
  /** choose for one conversation; `null` returns it to what it inherits */
  set: (id: Id, a: Atmosphere | null) => Promise<void>
}

/** The atmosphere choices, as the brain's presentation store holds them. */
export function useAtmospheres(store: PresentationStore): Atmospheres {
  const { choices, choose } = store
  return useMemo<Atmospheres>(() => {
    const brain = (choices.brain ?? 'default') as Atmosphere
    const held = choices.conversations as Record<string, Atmosphere>
    return {
      brain,
      setBrain: (a) => choose(null, a === 'default' ? null : a),
      set: (id, a) => choose(id, a),
      resolve: (id, name) => {
        if (id && held[id]) return { at: held[id], explicit: true }
        const configured = configuredFor(name)
        if (configured) return { at: configured, explicit: false }
        return { at: brain, explicit: false }
      },
    }
  }, [choices, choose])
}
