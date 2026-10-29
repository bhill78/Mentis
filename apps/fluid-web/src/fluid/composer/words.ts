/* WHAT THE SEND CONTROL SAYS (completion stream B, #187 #8, #442 #4).
 *
 * The meaning of sending is production's and is not decided here: `actionOf`
 * (draft.ts) reads the draft, the POST body is built from the same reading,
 * so the label and the act cannot disagree. What this adds is WHO ACTS AND
 * WHERE: "Ask @Quill on codex". The runtime named is the one chosen on the
 * addressee, else the one that name DECLARED as its default; with neither,
 * Mentis's selection decides, and the label says "any runtime" rather than
 * implying one. Never read off the alias. */

import { consentShort } from '../runs/consent'
import { personaToken } from './designation'
import type { DesignatedPersona } from '../../api'
import { ACTION_WHY, actionOf, sendLabel, targetOf, type Action, type Addressee, type Draft } from '../../composer/draft'

export interface Declared { participant: string; default_runtime?: string | null }

/** Where one addressee's work runs, as far as anybody has said. */
export function whereOf(a: Addressee, declared: Declared[]): { runtime: string | null; said: 'chosen' | 'default' | 'open' } {
  if (a.runtime) return { runtime: a.runtime, said: 'chosen' }
  const d = declared.find((p) => p.participant === a.participant)?.default_runtime
  return d ? { runtime: d, said: 'default' } : { runtime: null, said: 'open' }
}

/** The addressee chip's second words: the constraints and only those.
 *  TASK GRAVITY IS ALWAYS SAID for somebody asked to work, "ask" included
 *  (operating-model §6): it is chosen per request, and a chip silent about
 *  it could not be told apart from one whose setting was never looked at.
 *  THE PERSONA IS SAID WHEN ONE WILL BE WORN: the chosen one, or with nothing
 *  chosen the designated one, "(designated)" -- the owner's ruling that direct
 *  addressing uses it (designation.ts) -- and "as themselves" when chosen. */
export function tokenOf(a: Addressee, declared: Declared[], personaName?: (id: string) => string | null,
  designated?: (participant: string) => DesignatedPersona | null): string {
  if (!a.dispatch) return 'addressed only'
  const w = whereOf(a, declared)
  const said = [w.runtime ? (w.said === 'default' ? `${w.runtime} · default` : w.runtime) : 'any runtime', a.model, a.effort]
    .filter(Boolean) as string[]
  const persona = personaToken(a.persona, designated?.(a.participant), personaName)
  if (persona) said.push(persona)
  if (a.summoned || a.newInstance) said.push('new')
  if (a.coordinate) said.push('coordinates')
  said.push(a.followUp === undefined ? 'asks before side work'
    : a.followUp === 'unrestricted' ? 'side work: free' : `side work: ${a.followUp} deep`)
  /* Consent is said only when chosen: asking is the default and the safe one. */
  const consent = consentShort(a.consent?.mode)
  if (consent) said.push(consent)
  return said.join(' · ')
}

export interface SendWords { action: Action; label: string; why: string }

/** The button's words and its one-line why, from the draft as it stands. */
export function sendWords(d: Draft, fallback: Action, declared: Declared[]): SendWords {
  const action = actionOf(d, fallback)
  if (action === 'record-only')
    return { action, label: 'Record only', why: 'Records this and nothing else. Nobody is asked, nothing runs.' }
  if (action === 'ask-mentis')
    return { action, label: sendLabel(action, null), why: 'Asks Mentis: ' + ACTION_WHY[action].replace(/^ask Mentis\. /, '') }
  const working = d.to.filter((a) => a.dispatch)
  if (working.length === 1) {
    const a = working[0]
    const w = whereOf(a, declared)
    return {
      action,
      label: `Ask ${a.alias} on ${w.runtime ?? 'any runtime'}`,
      why: `Asks ${a.alias} to work${w.runtime ? `, on ${w.runtime}${w.said === 'default' ? ' (their declared default)' : ''}` : '; Mentis picks the runtime'}${a.model ? `, model ${a.model}` : ''}. Nobody else is asked.`,
    }
  }
  return {
    action,
    label: sendLabel(action, targetOf(d)),
    why: `Asks ${working.map((a) => a.alias).join(', ')} to work, each where their chip says. Nobody else is asked.`,
  }
}
