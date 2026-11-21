/* ONE SAVED PERMISSION CONFIGURATION, IN THIS BROWSER, FOR THIS BRAIN AND
 * THIS OWNER (owner approval ent-89b5beaf5e39, over the narrowed proposal
 * ent-84bcc33c26bb and its independent review ent-4a7b44c21acb).
 *
 * WHAT IT IS FOR. The owner sets Permission Mode, the task's workspaces, the
 * optional operation categories, "May coordinate this work" and the
 * original-request side-work permission on nearly every new piece of Work,
 * by hand, every time. This remembers ONE such configuration and populates a
 * fresh draft with it. That is all it is: A PREFERENCE ABOUT WHAT THE
 * CONTROLS START AT. It grants nothing, it is never consulted by the server,
 * and what authorises a run is still the owner's submission and the grant
 * recorded against it.
 *
 * DELIBERATELY BROWSER-LOCAL, with the consequences said rather than hidden:
 * another browser or device does not have it, clearing browser storage loses
 * it, and a Brain backup will not bring it back (`DEFAULT_LIMITS`). It is
 * scoped by the Brain the page is bound to AND the owner it was saved by
 * (`scopeOf`), because the same browser reads a Brain, a copy of it served
 * from elsewhere, and a Brain restored in place -- and a configuration saved
 * against one of those is not the others'.
 *
 * MALFORMED SAVED DATA IS UNAVAILABLE, NEVER WIDENED. Everything read back is
 * checked field by field against the same values the composer can choose, and
 * anything that fails -- a mode that is not one, a workspace that is not an
 * absolute directory, a category nobody offers, a depth that is not a whole
 * number -- makes the WHOLE configuration unreadable. A half-read
 * configuration is never assembled, and no reading failure ever produces
 * "Allow all operations": the page says it could not read what is saved and
 * carries on with no default at all, which is how the composer behaved before
 * any of this existed.
 *
 * A FAILED SAVE IS REPORTED. `localStorage` can be absent, blocked or full,
 * and a preference that silently did not save is worse than none: every write
 * here answers whether it happened, and the panel says so. */

import { OPTIONAL, type AskMentis, type Consent } from '../../composer/draft'
import { CONSENT_MODES, notAbsolute } from '../runs/consent'
import { followUpOf, gravityWords } from '../runs/gravity'

export const PERMISSION_DEFAULT_KEY = 'mentis.fluid.permission-default'
export const PERMISSION_DEFAULT_VERSION = 1

/** THE SELECTIONS A SAVED CONFIGURATION HOLDS: exactly the fields a request
 *  already carries (`Addressee`, `AskMentis`), so nothing is translated on
 *  the way in or out and the saved shape cannot drift from the sent shape.
 *  A field that is absent was not chosen and is not populated. */
export interface SavedPermissions {
  consent?: Consent
  coordinate?: boolean
  followUp?: number | 'unrestricted'
}

/** WHERE A SAVED CONFIGURATION BELONGS: the Brain the page is bound to and
 *  the owner acting. Null until the page can say both -- and with no scope
 *  nothing is read, saved or populated, which is what keeps a page that has
 *  not confirmed its Brain (and legacy Fluid, which binds to none) exactly
 *  as it was. */
export const scopeOf = (brain: string | null | undefined, owner: string | null | undefined): string | null =>
  brain && owner ? `${brain}|${owner}` : null

/** What a reading of the saved configuration came to. `unreadable` is an
 *  answer, not an error: something is saved, it could not be trusted, and no
 *  default is used until it is replaced. */
export type DefaultRead =
  | { state: 'none' }
  | { state: 'saved'; saved: SavedPermissions; at: number | null }
  | { state: 'unreadable'; why: string }

/** Whether a write happened, and why it did not. */
export type Wrote = { ok: true } | { ok: false; why: string }

export const DEFAULT_LIMITS = 'Saved in this browser only, for this Brain and for you: another browser or device will not have it, '
  + 'clearing this browser’s storage loses it, and a Brain backup will not bring it back.'

export const DEFAULT_SCOPE_WHY = 'Used to fill in new Work you start here, before you send it. Replies, work continued under the same request '
  + 'and work handed on to an agent keep the permissions already recorded for them.'

export const UNREADABLE_WHY = 'A permission default is saved in this browser but could not be read, so none is used. '
  + 'Choose what you want and save it again to replace it.'

export const OTHER_VERSION_WHY = 'The permission default saved in this browser was written by another version of this page, so none is used. '
  + 'Choose what you want and save it again to replace it.'

export const NO_STORAGE_WHY = 'This browser did not let the page keep anything, so nothing was saved.'

export const NOT_BOUND_WHY = 'This page cannot yet say which Brain it is on, so nothing was saved. Try again in a moment.'

export const NOTHING_TO_SAVE_WHY = 'There is nothing to save: these are already what every new piece of Work starts at. '
  + 'Choose a Permission Mode, authority or side-work permission first.'

const storageOf = (given?: Storage): Storage | null => {
  try {
    return given ?? (typeof window !== 'undefined' ? window.localStorage : null)
  } catch {
    /* a browser that refuses even to hand out the store (private modes do) */
    return null
  }
}

const MODES = CONSENT_MODES.map((m) => m.mode).filter((m) => m !== 'ask')

/** WHAT IS ACTUALLY A CONFIGURATION, checked field by field against what the
 *  composer can choose. Null for anything else -- the whole of it, never a
 *  part: a configuration read half-way is not a configuration.
 *
 *  Used on the way OUT as well as in, so an invalid selection is refused
 *  before it is saved rather than discovered when it is read back. */
export function readable(x: unknown): SavedPermissions | null {
  if (!x || typeof x !== 'object' || Array.isArray(x)) return null
  const e = x as Record<string, unknown>
  const out: SavedPermissions = {}
  if (e.consent !== undefined && e.consent !== null) {
    const c = e.consent
    if (!c || typeof c !== 'object' || Array.isArray(c)) return null
    const r = c as Record<string, unknown>
    /* `ask` is the absence of a consent, never a saved one: a saved "ask"
       would be a configuration that populates the control with the default
       it already has, and the composer sends nothing for it. */
    if (typeof r.mode !== 'string' || !(MODES as string[]).includes(r.mode)) return null
    if (!Array.isArray(r.workspaces)) return null
    if (r.workspaces.some((w) => typeof w !== 'string')) return null
    const workspaces = (r.workspaces as string[]).map((w) => w.trim()).filter(Boolean)
    /* A WORKSPACE THAT IS NOT AN ABSOLUTE DIRECTORY is what the composer
       itself marks as wrong and what the server refuses; it is not quietly
       dropped here, because dropping it would widen nothing but would make
       the saved configuration mean something the owner did not save. */
    if (notAbsolute(workspaces).length > 0) return null
    let extra: string[] | undefined
    if (r.extra !== undefined && r.extra !== null) {
      if (!Array.isArray(r.extra)) return null
      if (r.extra.some((y) => typeof y !== 'string' || !OPTIONAL.includes(y as string))) return null
      const kept = [...new Set(r.extra as string[])]
      extra = kept.length ? kept : undefined
    }
    out.consent = { mode: r.mode as Consent['mode'], workspaces, ...(extra ? { extra } : {}) }
  }
  if (e.coordinate !== undefined && e.coordinate !== null) {
    if (typeof e.coordinate !== 'boolean') return null
    out.coordinate = e.coordinate
  }
  if (e.followUp !== undefined && e.followUp !== null) {
    const f = e.followUp
    if (f === 'unrestricted') out.followUp = 'unrestricted'
    else if (typeof f === 'number' && Number.isInteger(f) && f >= 1) out.followUp = f
    else return null
  }
  return out
}

/** Whether a configuration says anything at all. An empty one is the same as
 *  none, and is not saved: it would populate nothing. */
export const says = (s: SavedPermissions): boolean =>
  s.consent !== undefined || s.coordinate !== undefined || s.followUp !== undefined

/** WHAT IS CHOSEN NOW, as a configuration: the three permission selections
 *  off whatever holds them (an addressee, or the draft's Ask Mentis), copied
 *  rather than shared. Runtime, model, effort, Persona, instance and
 *  Execution Mode are deliberately NOT here: the owner's approval is for
 *  permissions, and nothing else is remembered. */
export const savedOf = (x: SavedPermissions): SavedPermissions => ({
  ...(x.consent
    ? {
        consent: {
          mode: x.consent.mode,
          workspaces: [...x.consent.workspaces],
          ...(x.consent.extra?.length ? { extra: [...x.consent.extra] } : {}),
        },
      }
    : {}),
  ...(x.coordinate === undefined ? {} : { coordinate: x.coordinate }),
  ...(x.followUp === undefined ? {} : { followUp: x.followUp }),
})

/** The same two configurations? Compared as what they say, so a configuration
 *  carrying an empty `extra` and one carrying none are one. */
export const sameAs = (a: SavedPermissions, b: SavedPermissions): boolean =>
  JSON.stringify(savedOf(a)) === JSON.stringify(savedOf(b))

/** A FRESH DRAFT'S ASK MENTIS SELECTIONS from a saved configuration. */
export const askFrom = (s: SavedPermissions): AskMentis => savedOf(s)

/** POPULATE, NEVER OVERRIDE. A field the owner has already decided on this
 *  subject stays exactly as they left it; only what is unset is filled in.
 *  Each subject gets its own copy of the workspaces and the categories, so
 *  two addressees never share one list.
 *
 *  This is why `coordinate: false` has to be a value and not an absence: the
 *  owner saying "does this work only" is a decision, and a decision is never
 *  overwritten by the saved default. */
export function populate<T extends SavedPermissions>(x: T, s: SavedPermissions): T {
  const next = { ...x }
  if (next.consent === undefined && s.consent) next.consent = savedOf(s).consent
  if (next.coordinate === undefined && s.coordinate !== undefined) next.coordinate = s.coordinate
  if (next.followUp === undefined && s.followUp !== undefined) next.followUp = s.followUp
  return next
}

/** The selections in a few words, for the control that opens them: Permission
 *  Mode always (it is the one with consequences), then authority where
 *  anything was said about it, then side work. */
export function chosenWords(x: SavedPermissions): string {
  const mode = x.consent?.mode ?? 'ask'
  const said = [
    (CONSENT_MODES.find((m) => m.mode === mode)?.words ?? CONSENT_MODES[0].words).replace(/ \(.*\)$/, ''),
    x.coordinate === undefined ? null : x.coordinate ? 'may coordinate' : 'this work only',
    gravityWords(followUpOf(x.followUp)).replace(/^May pursue side work/, 'side work').replace(/^Asks before pursuing side work/, 'asks before side work'),
  ]
  return said.filter(Boolean).join(' · ')
}

type By = Record<string, { saved: SavedPermissions; at: number }>

/** Everything this browser has kept, as one of three answers: nothing kept,
 *  what was kept, or kept and not readable as this version's -- which is
 *  said, never treated as nothing. */
type Kept = { state: 'none' } | { state: 'held'; by: By } | { state: 'unreadable'; why: string }

function kept(s: Storage): Kept {
  let raw: string | null
  try {
    raw = s.getItem(PERMISSION_DEFAULT_KEY)
  } catch {
    return { state: 'unreadable', why: UNREADABLE_WHY }
  }
  if (!raw) return { state: 'none' }
  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return { state: 'unreadable', why: UNREADABLE_WHY }
  }
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return { state: 'unreadable', why: UNREADABLE_WHY }
  const p = parsed as Record<string, unknown>
  if (p.version !== PERMISSION_DEFAULT_VERSION)
    return { state: 'unreadable', why: typeof p.version === 'number' ? OTHER_VERSION_WHY : UNREADABLE_WHY }
  if (!p.by || typeof p.by !== 'object' || Array.isArray(p.by)) return { state: 'unreadable', why: UNREADABLE_WHY }
  return { state: 'held', by: p.by as By }
}

/** THE SAVED CONFIGURATION FOR THIS BRAIN AND OWNER, or why there is none to
 *  use. Another scope's configuration is not this one's and is not read as
 *  it: the answer is `none`, not a default from somewhere else. */
export function readDefault(scope: string | null, storage?: Storage): DefaultRead {
  if (!scope) return { state: 'none' }
  const s = storageOf(storage)
  if (!s) return { state: 'none' }
  const held = kept(s)
  if (held.state !== 'held') return held
  const entry = held.by[scope]
  if (entry === undefined || entry === null) return { state: 'none' }
  if (typeof entry !== 'object' || Array.isArray(entry)) return { state: 'unreadable', why: UNREADABLE_WHY }
  const saved = readable((entry as { saved?: unknown }).saved)
  if (!saved || !says(saved)) return { state: 'unreadable', why: UNREADABLE_WHY }
  const at = (entry as { at?: unknown }).at
  return { state: 'saved', saved, at: typeof at === 'number' ? at : null }
}

function write(s: Storage, by: By): Wrote {
  const next = JSON.stringify({ version: PERMISSION_DEFAULT_VERSION, by })
  try {
    s.setItem(PERMISSION_DEFAULT_KEY, next)
  } catch (e) {
    return { ok: false, why: `This browser would not keep it (${(e as Error).message || 'storage refused the write'}), so nothing was saved.` }
  }
  /* READ BACK, because a store that accepted the write and kept nothing is
     the one failure a preference must not shrug off. */
  try {
    if (s.getItem(PERMISSION_DEFAULT_KEY) !== next) return { ok: false, why: NO_STORAGE_WHY }
  } catch {
    return { ok: false, why: NO_STORAGE_WHY }
  }
  return { ok: true }
}

/** SAVE OR REPLACE the one configuration for this Brain and owner. Another
 *  scope's stays exactly as it was, and an invalid selection is refused here
 *  rather than written and found unreadable later. */
export function saveDefault(scope: string | null, saved: SavedPermissions, storage?: Storage, now = Date.now()): Wrote {
  if (!scope) return { ok: false, why: NOT_BOUND_WHY }
  const s = storageOf(storage)
  if (!s) return { ok: false, why: NO_STORAGE_WHY }
  const clean = readable(savedOf(saved))
  if (!clean) {
    const bad = saved.consent ? notAbsolute(saved.consent.workspaces) : []
    return {
      ok: false,
      why: bad.length
        ? `Not saved: ${bad.join(', ')} ${bad.length === 1 ? 'is not' : 'are not'} an absolute directory.`
        : 'Not saved: these selections are not ones this page can keep.',
    }
  }
  if (!says(clean)) return { ok: false, why: NOTHING_TO_SAVE_WHY }
  const held = kept(s)
  /* Something unreadable is replaced rather than preserved: it is already
     unavailable, and refusing to save over it would leave the owner stuck. */
  const by: By = held.state === 'held' ? { ...held.by } : {}
  by[scope] = { saved: clean, at: now }
  return write(s, by)
}

/** CLEAR this Brain and owner's configuration. Nothing saved is not a
 *  failure: the state asked for is the state reached. */
export function clearDefault(scope: string | null, storage?: Storage): Wrote {
  if (!scope) return { ok: true }
  const s = storageOf(storage)
  if (!s) return { ok: true }
  const held = kept(s)
  if (held.state === 'none') return { ok: true }
  if (held.state === 'unreadable') {
    /* unreadable: the whole of it goes, which is what clearing asks for */
    try {
      s.removeItem(PERMISSION_DEFAULT_KEY)
    } catch {
      return { ok: false, why: 'This browser would not let the page clear what it saved.' }
    }
    return { ok: true }
  }
  const by: By = { ...held.by }
  if (!(scope in by)) return { ok: true }
  delete by[scope]
  if (Object.keys(by).length === 0) {
    try {
      s.removeItem(PERMISSION_DEFAULT_KEY)
    } catch {
      return { ok: false, why: 'This browser would not let the page clear what it saved.' }
    }
    return { ok: true }
  }
  return write(s, by)
}
