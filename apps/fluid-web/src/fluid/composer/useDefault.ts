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
 * AND BECAUSE BOTH ARE ANSWERED LATE, A SUBMISSION ASKS WHERE IT IS GOING
 * BEFORE IT IS BUILT (`sending`; focused re-review adm-871e7b570a26, B1).
 * Taking what was filled in back out of the DRAFT once the answer arrives is
 * not enough on its own: Send can be pressed while the answer is still
 * pending, and the body is serialised then -- before the page's write guard,
 * which waits for the binding and names the Brain in a header it adds to an
 * already built body. So the concrete values a submission carries are placed
 * against the scope resolved AT SUBMISSION, and a submission the page cannot
 * place is not sent at all.
 *
 * IT FAILS CLOSED, AND IT NEVER GRANTS ANYTHING. Everything here decides
 * what the permission controls START AT, before the owner sends anything.
 * What authorises a run is still the submission and the grant recorded
 * against it. */

import { useEffect, useRef, useState } from 'react'
import { brainNow, confirmBrain, guarding, page, useBrainBound, useBrainMoved, type Binding } from '../../brainBinding'
import type { Draft } from '../../composer/draft'
import {
  clearDefault, filledIn, forScope, leftFreshWork, readDefault, sameAs, saveDefault, savedOf, scopeOf, seedInto, seedable,
  type DefaultRead, type SavedPermissions,
} from './permissionDefault'
import type { Preference } from './Operations'

/** The page's scope: `<brain>|<owner>` once both are answered, null where the
 *  page has none (it has moved to another Brain), and `undefined` while it is
 *  still being answered -- which is NOT the same as none, and is why a draft
 *  is never emptied on it. */
export type Scope = string | null | undefined

/** WHAT A SUBMISSION MAY CARRY, answered before its body is built: the draft
 *  to build it from, for the scope it is actually going to -- or that it is
 *  not to be sent, and why. Never a draft the page could not place.
 *
 *  `brain` IS WHAT THE WRITE MUST NAME (re-review B1-F2): the Brain this
 *  submission's values were placed against, for a body that carries any of
 *  them, so that the server refuses it if it has come to serve another Brain
 *  between the asking and the writing (`X-Mentis-Brain`, 409 `BrainChanged`).
 *  Null where the body carries nothing scoped -- nothing was filled in, or
 *  what was filled in was left out -- and such a write names no Brain and is
 *  exactly as it always was. A page that guards its own writes names it
 *  anyway, through the guard. */
export type Sending =
  | { ok: true; draft: Draft; scope: string | null; brain: string | null }
  | { ok: false; why: string }

/** WHAT A SEND MADE BEFORE THE PAGE CAN SAY WHERE IT IS GOING COMES TO: NOT
 *  SENT -- and what was filled in is taken out of the draft as it is refused,
 *  so that what the controls say is exactly what the next send carries. The
 *  words, the people, the attachments and the owner's own choices are
 *  untouched: nothing of theirs is lost by this. */
export const UNPLACED_SEND = 'Nothing was sent: this page cannot say which Brain and owner this would be recorded for, '
  + 'so the permission settings remembered in this browser have been taken out of it. '
  + 'Your words and your own choices are kept — check the permissions and send again.'

export interface Defaulting {
  /** what is saved for this Brain and owner, or why there is nothing to use */
  saved: DefaultRead
  /** the page's scope; see `Scope` */
  scope: Scope
  /** WHETHER THIS DRAFT MAY BE SENT, AND AS WHAT -- asked where a submission
   *  is built, BEFORE its body is serialised and before anything is written.
   *
   *  THIS IS THE HALF A SCOPE KNOWN LATER BREAKS (review adm-871e7b570a26,
   *  B1). The Brain and the owner are answered after the composer mounts, so
   *  Send can be pressed while the page cannot yet say WHERE the submission
   *  goes -- and a body built in that moment carries whatever was filled in
   *  for the Brain the draft was written on. The page's write guard cannot
   *  save it: it waits for the binding and names the Brain in a header, by
   *  which time the body is already serialised, so the write leaves naming
   *  one Brain and carrying another's permission selections.
   *
   *  So the scope is RESOLVED HERE, by asking the same question the guard
   *  asks (`brainNow`), and the draft is placed against the answer:
   *    - the scope it was filled in for: it stands, unchanged;
   *    - another scope: what was filled in is left out of the body (and out
   *      of the draft), and the owner's own choices stay;
   *    - no scope the page can name: NOT SENT, with the words kept.
   *  A draft nothing was filled into is sent as it always was, and asks
   *  nothing of the server to find that out.
   *
   *  AND THE ANSWER IS CARRIED INTO THE WRITE ITSELF (`Sending.brain`): the
   *  resolved Brain is what a body holding its values names, so a server that
   *  comes to serve another one between this question and that write refuses
   *  it rather than recording one Brain's permissions in another's Work. */
  sending: (d: Draft) => Promise<Sending>
  /** THE SAME RULE AGAINST THE SCOPE AS IT IS KNOWN NOW, without asking
   *  anybody: what this draft would carry if it were sent in this moment.
   *  FAILS CLOSED -- a scope the page has not answered yet is not a scope to
   *  send another's selections to, so they are left out. `sending` resolves a
   *  scope first and is what the composer submits through. */
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

  /* WHERE A SUBMISSION MADE NOW WOULD BE RECORDED, asked for rather than
     waited on: the Brain the write guard would name (`brainNow`) and the
     owner acting. A page that does not guard its own writes is asked again
     even when it is bound, because nothing else on it would notice the
     server having moved on to another Brain.
     THE BRAIN IS KEPT, not only the scope it makes: a check before a write
     cannot say where that write is committed, so whatever the answer placed
     has to NAME it (`Sending.brain`). */
  const placeNow = async (): Promise<{ brain: string | null; scope: string | null }> => {
    if (binding.moved()) return { brain: null, scope: null }
    const brain = await brainNow(binding, confirm, !guarding())
    return { brain, scope: scopeOf(brain, owner) }
  }

  return {
    saved,
    scope,
    sending: async (d: Draft): Promise<Sending> => {
      /* NOTHING WAS FILLED IN: there is nothing of any default in it, so it
         is sent exactly as it was before this preference existed -- and the
         server is asked nothing to establish that. */
      if (!filledIn(d)) return { ok: true, draft: d, scope: scope ?? null, brain: null }
      const at = await placeNow()
      if (at.scope === null) {
        setDraft((x) => forScope(x, null))
        return { ok: false, why: UNPLACED_SEND }
      }
      /* NAMED ONLY WHERE SOMETHING SCOPED IS STILL IN IT. Placed against
         another scope, the default is out of the draft and the body carries
         nothing of that Brain's, so the write names no Brain and is as it
         always was; placed against its own, the values stand and the write
         names the Brain they belong to. */
      const placed = forScope(d, at.scope)
      return { ok: true, draft: placed, scope: at.scope, brain: filledIn(placed) ? at.brain : null }
    },
    forSending: (d: Draft) => forScope(d, scope ?? null),
    preferenceFor,
  }
}
