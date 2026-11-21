/* WHEN THE SAVED PERMISSION CONFIGURATION IS READ, FILLED IN AND TAKEN BACK
 * OUT -- the composer's lifecycle for it, in one place.
 *
 * `permissionDefault.ts` holds WHAT each rule does to a draft, as plain
 * functions. This holds WHEN they run, and that is the half that actually
 * went wrong: the independent review of the first implementation
 * (adm-232c2d36269e) found four lifecycle defects -- a materialised default
 * surviving into another Brain's work, into a reply, into a draft restored
 * from before the preference existed, and over an explicit "Ask" chosen
 * while the Brain was still being answered -- none of which the unit checks
 * could see, because they read the component's source text (N3).
 *
 * So the lifecycle is a hook of its own: it can be MOUNTED, driven and
 * observed (tests/permission_lifecycle_unit.mjs mounts this very code over
 * the small hook runtime, with a real draft, a real binding and a real
 * store), and the composer is left holding only its own chrome.
 *
 * TWO THINGS ARE ANSWERED AFTER THE COMPOSER MOUNTS, and that is why this
 * subscribes rather than reads: the Brain the page is bound to (asked while
 * the page draws, quiet2/live.ts) and the owner acting (`store.loadMe()`).
 * Until both have answered there is no scope -- and with no scope nothing is
 * read, filled in or saved, which is also exactly what a page that binds to
 * no Brain gets.
 *
 * IT FAILS CLOSED, AND IT NEVER GRANTS ANYTHING. Everything here decides
 * what the permission controls START AT, before the owner sends anything.
 * What authorises a run is still the submission and the grant recorded
 * against it. */

import { useEffect, useRef, useState } from 'react'
import { confirmBrain, page, useBrainBound, useBrainMoved, type Binding } from '../../brainBinding'
import type { Draft } from '../../composer/draft'
import {
  clearDefault, forScope, leftFreshWork, readDefault, sameAs, saveDefault, savedOf, scopeOf, seedInto, seedable,
  type DefaultRead, type SavedPermissions,
} from './permissionDefault'
import type { Preference } from './Operations'

/** The page's scope: `<brain>|<owner>` once both are answered, null where the
 *  page has none (it has moved to another Brain), and `undefined` while it is
 *  still being answered -- which is NOT the same as none, and is why a draft
 *  is never emptied on it. */
export type Scope = string | null | undefined

export interface Defaulting {
  /** what is saved for this Brain and owner, or why there is nothing to use */
  saved: DefaultRead
  /** the page's scope; see `Scope` */
  scope: Scope
  /** WHAT THIS DRAFT ACTUALLY SENDS: the draft, with anything filled in for
   *  another Brain or another owner left out of it. Applied where the body is
   *  built, so that a draft the page has not yet caught up with cannot carry
   *  another scope's permissions into a submission. */
  forSending: (d: Draft) => Draft
  /** the saved-default row for a permission panel, over what that panel has
   *  chosen; absent where there is nowhere to save one */
  preferenceFor: (now: SavedPermissions) => Preference | undefined
}

export function usePermissionDefault({ enabled, fresh, owner, draft, setDraft, binding = page, confirm = confirmBrain, storage }: {
  /** this composer offers the permission controls at all: Quiet Chat's
   *  composer, and a workspace's ask -- both of which start new Work */
  enabled: boolean
  /** NEW ORIGINAL WORK: not a reply, not a post in a thread */
  fresh: boolean
  /** the owner acting, once the page can say */
  owner: string | null
  draft: Draft
  setDraft: (fn: (d: Draft) => Draft) => void
  /** the page's Brain binding; a test drives its own */
  binding?: Binding
  /** how the page asks which Brain the server serves; a test serves its own */
  confirm?: () => Promise<boolean | null>
  /** where the configuration is kept; a test passes its own store */
  storage?: Storage
}): Defaulting {
  const bound = useBrainBound(binding)
  const moved = useBrainMoved(binding)
  const scope: Scope = moved ? null : bound && owner ? scopeOf(bound, owner) : undefined

  /* WHICH BRAIN, ON A PAGE THAT DOES NOT BIND ITSELF. Quiet Chat binds as it
     opens; the workspace column is drawn by the older Fluid shell, which does
     not -- and a preference kept per Brain cannot be read, saved or scoped
     without knowing which Brain this is. So where these controls are offered
     and nothing has named one yet, the composer asks the same question Quiet
     asks (`confirmBrain`): one read, naming the Brain and nothing else. It
     does not guard this page's writes -- `guarding()` stays false -- and
     changes nothing else about the page. */
  const asked = useRef(false)
  useEffect(() => {
    if (!enabled || moved || bound !== null || asked.current) return
    asked.current = true
    void confirm()
  }, [enabled, bound, moved]) // eslint-disable-line react-hooks/exhaustive-deps

  const [saved, setSaved] = useState<DefaultRead>({ state: 'none' })
  const [why, setWhy] = useState<string | null>(null)
  /** this draft would take a default now, if one is saved */
  const wants = enabled && fresh && !!scope && seedable(draft)
  useEffect(() => {
    if (!scope) { setSaved({ state: 'none' }); setWhy(null); return }
    setSaved(readDefault(scope, storage))
  }, [scope, wants]) // eslint-disable-line react-hooks/exhaustive-deps

  /* ANOTHER BRAIN'S, OR ANOTHER OWNER'S, IS NOT THIS PAGE'S (B1). Run as soon
     as the page can say what its scope is -- and not before: `undefined` is a
     question not yet answered, and nothing is taken out of a draft on it. */
  useEffect(() => {
    if (scope === undefined) return
    setDraft((d) => forScope(d, scope))
  }, [scope, draft.seededIn]) // eslint-disable-line react-hooks/exhaustive-deps

  /* NOT NEW WORK ANY MORE (B2): choosing to reply, or writing in a thread,
     takes the default back out of the draft and out of anybody who had taken
     a copy of it, so the next recipient addressed cannot be handed it. */
  useEffect(() => {
    if (fresh) return
    setDraft(leftFreshWork)
  }, [fresh, draft.seeded]) // eslint-disable-line react-hooks/exhaustive-deps

  /* FILLED IN ONCE, into a draft started here (B3). A draft restored after a
     reload keeps the values it was filled in with, even if what is saved has
     changed since: they are what the owner has been looking at. Sending
     empties the draft, and the next fresh one is filled in from what is
     saved then. */
  useEffect(() => {
    if (!wants || !scope || saved.state !== 'saved') return
    setDraft((d) => (seedable(d) ? seedInto(d, saved.saved, scope) : d))
  }, [wants, saved, scope]) // eslint-disable-line react-hooks/exhaustive-deps

  /* SAVING AND CLEARING, offered by whichever permission panel is open, over
     what that panel has chosen. Both say whether they happened; a browser
     that would not keep it is reported, never shrugged off. */
  const preferenceFor = (now: SavedPermissions): Preference | undefined => (scope ? {
    state: saved.state,
    why: why ?? (saved.state === 'unreadable' ? saved.why : null),
    matches: saved.state === 'saved' && sameAs(saved.saved, now),
    save: () => { const r = saveDefault(scope, savedOf(now), storage); setWhy(r.ok ? null : r.why); setSaved(readDefault(scope, storage)) },
    clear: () => { const r = clearDefault(scope, storage); setWhy(r.ok ? null : r.why); setSaved(readDefault(scope, storage)) },
  } : undefined)

  return {
    saved,
    scope,
    forSending: (d: Draft) => (scope === undefined ? d : forScope(d, scope)),
    preferenceFor,
  }
}
