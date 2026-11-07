/* WHAT EVERYTHING INSIDE THE WORKING STAGE NEEDS. Round 5, package W2.
 *
 * The plan's F1 inventory, after reading Workspace.tsx, TreeView.tsx,
 * Zones.tsx, zoneMenu.tsx and Detail.tsx: the REAL GovContext (Workspace
 * calls `useGovNav()` unconditionally, and that throws without one), Actions
 * targeted at the EFFECTIVE conversation, Shell's ToastView lifted onto the
 * existing `frame/toasts.ts` store with its actionable Undo, the frame Layer
 * with its `fx-layer` portal target for Sheets, menus and the Keep chooser,
 * the ActionPalette, and the idempotent action registry. None of it is
 * copied: these are the mechanisms Fluid already has, and Fluid's Shell is
 * deliberately not imported -- it owns the whole frame, its global styling
 * and its own entrance into the Holder.
 *
 * NOTHING HERE ANSWERS WITH A FAKE. `include` and `remove` are omitted rather
 * than reporting a success nobody performed; `busy`, `selectMode` and
 * `selected` are the store's own; governance opens the destinations Fluid
 * already has, under the local source and edit intent, and invents no second
 * Quiet governance interface.
 *
 * THE LAYER AND ITS PORTAL TARGET. This mounts `#fx-layer` -- what takes a
 * sheet or a menu out of the stage's own clipping and container query -- and
 * one frame Layer in it. Quiet's composer mounts a Layer of its own while it
 * is drawn (`quiet/composer/Composer.tsx`, package C) and the stage needs one
 * on a Page that parks the composer, so `fluid/frame/layer.tsx` now lets the
 * FIRST mounted host draw and the next take over: an in-scope repair of the
 * duplication this mount would otherwise introduce, noted in the return for a
 * hand-back, with /fluid's single Layer unaffected.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Id } from '../../api'
import { Layer } from '../../fluid/frame/layer'
import { dismissToast, useToast } from '../../fluid/frame/toasts'
import { presentationClass } from '../../fluid/frame/narrow'
import { GovContext, type GovNav } from '../../fluid/governance/context'
import { govObject, readHint, type OpenHint, type Source } from '../../fluid/governance/model'
import { useSelection } from '../../fluid/conversation/hooks'
import * as nav from '../../fluid/nav'
import { Actions, type PostActions } from '../../fluid/render/post'
import { store } from '../../fluid/store'
import { ActionPalette } from '../../fluid/surface/actions/ActionMenu'
import { aimFallback } from '../../fluid/surface/actions/paletteStore'
import { installProviders } from '../../fluid/surface/actions/providers'
import { providePostActs, wireActions } from '../../fluid/surface/actions/appOps'
import { hostCtx, workspaceTarget } from '../../fluid/surface/actions/targets'
import { workspace } from '../../fluid/workspace/place'
import type { WorkingProvidersView } from '../contract'

/* -- the hosted action registry -------------------------------------------- */

/** THE REGISTRY, INSTALLED ONCE AND NOT A NEW ACTION SYSTEM. Fluid's Shell
 *  does this at module scope; Quiet cannot import Shell, so the same three
 *  idempotent calls are made here the first time a stage is mounted.
 *  `installProviders` already refuses a second install of the same registry;
 *  `wireActions` and `aimFallback` are last-writer-wins and are given the
 *  same functions Shell gives them. */
let wired = false
function wire() {
  if (wired) return
  wired = true
  wireActions()
  installProviders()
  aimFallback(() => ({
    target: workspaceTarget(workspace.key ?? 'home'),
    ctx: hostCtx(presentationClass(window.innerWidth)),
    name: 'this place',
  }))
}

/* -- the toast ------------------------------------------------------------- */

/** SHELL'S TOAST, LIFTED (`fluid/Shell.tsx`'s ToastView), on the existing
 *  `frame/toasts.ts` store. Its ACTION is what matters here: every Undo the
 *  workspace offers -- a Keep, a split, a closed Page, a new Page -- is
 *  offered through `nav.toast`, and until this is mounted Quiet drops all of
 *  them on the floor. The markup and ids are Shell's own, so the same styles
 *  and the same checks apply. */
function ToastView() {
  const t = useToast()
  const [shown, setShown] = useState<typeof t>(null)
  useEffect(() => {
    if (t) setShown(t)
  }, [t])
  const on = !!t
  const v = t ?? shown
  return (
    <div className={'fx-toast' + (on ? ' on' : '')} id="toast" role="status" aria-hidden={!on}>
      <span id="toastMsg">{v?.text}</span>
      {v?.action && (
        <button
          id="toastAct"
          onClick={() => {
            const run = v.action!.run
            dismissToast()
            run()
          }}
        >
          {v.action.label}
        </button>
      )}
    </div>
  )
}

/* -- who is acting --------------------------------------------------------- */

/** ME AND THE OWNER, AS THE SERVER NAMES THEM, through the store's own single
 *  read (`store.loadMe`, which answers from its cache after the first call).
 *  Governance offers Set aside to the owner alone, so a guessed owner would
 *  be a guessed permission. */
function useMe(): { me: Id | null; owner: Id | null } {
  const [who, setWho] = useState<{ me: Id | null; owner: Id | null }>(() => ({
    me: store.me,
    owner: store.owner,
  }))
  useEffect(() => {
    if (store.me) return
    let live = true
    void store.loadMe().then(
      () => {
        if (live) setWho({ me: store.me, owner: store.owner })
      },
      () => {},
    )
    return () => {
      live = false
    }
  }, [])
  return who
}

/* -- governance ------------------------------------------------------------ */

/** Fluid's own Governance door, as `Shell.tsx`'s `govUrl` builds it. Lifted
 *  rather than reinvented: a governed item's page and the Governance list are
 *  Fluid's destinations, and Quiet leaves for them instead of growing a
 *  second governance interface of its own. */
function govUrl(a: { s?: string | null; from?: Id | null }): string {
  const q = new URLSearchParams({ gov: '1' })
  if (a.s) q.set('s', a.s)
  if (a.from) q.set('from', a.from)
  return '/fluid?' + q.toString()
}

/** Fluid's conversation door, for an item whose source is somewhere else. */
const convUrl = (c: Id): string => '/fluid?c=' + encodeURIComponent(c)

/* -- the providers --------------------------------------------------------- */

export const WorkingProviders: WorkingProvidersView = ({
  originConversation,
  effectiveConversation,
  page,
  onNavigate,
  children,
}) => {
  const { me, owner } = useMe()
  const selected = useSelection()
  const [selectMode, setSelectMode] = useState(false)
  useEffect(() => {
    wire()
  }, [])

  /* WHERE AN ITEM WAS OPENED BESIDE, AND WHETHER IT ASKED FOR ITS EDIT FORM:
     the same local intent Shell keeps, so a governed-item Page restored from
     this browser's arrangement still knows its source and opens its form
     once. Asked once: `takeEdit` answers true and forgets. */
  const sources = useRef(new Map<Id, Source | null>())
  const edits = useRef(new Set<Id>())
  const [editNonce, setEditNonce] = useState(0)

  const gov = useMemo<GovNav>(() => {
    const openGov = (section?: string) => {
      window.location.assign(govUrl({ s: section ?? null, from: originConversation }))
    }
    const openItem = (entry: Id, hint?: OpenHint | null, opts?: { edit?: boolean }) => {
      if (opts?.edit) {
        edits.current.add(entry)
        setEditNonce((n) => n + 1)
      }
      const go = (h: OpenHint) => {
        const src = h.source
        sources.current.set(entry, src)
        /* Nothing to open beside: Governance's own Stage, never a tab beside
           a conversation it has nothing to do with. */
        if (!src) {
          openGov()
          return
        }
        /* Its own conversation: a Page beside this place's Conversation, made
           by the existing operation, which reports one destination intent. */
        if (src.conversation === originConversation || src.conversation === effectiveConversation) {
          nav.openItemPage(govObject(entry), h.title)
          return
        }
        window.location.assign(convUrl(src.conversation))
      }
      if (hint?.source) go(hint)
      else
        void readHint(entry)
          .then((h) => go({ title: hint?.title ?? h.title, source: h.source }))
          .catch(() => {
            if (hint) go(hint)
            else {
              edits.current.delete(entry)
              nav.toast({ text: `Could not open ${entry}.` })
            }
          })
    }
    return {
      me,
      owner: me ? owner : null,
      openItem,
      openGov,
      /* Closing an item's page is a scoped Page close: the Page goes, the
         conversation and what the Brain keeps do not, and the existing Undo
         is still the Undo. */
      closeItem: (id: string) => nav.closePage(id),
      /* Reading a Turn leaves the working area the one way out of it. */
      readTurn: (conversation, turn) => onNavigate({ conversation, turn }),
      takeEdit: (entry) => edits.current.delete(entry),
      sourceOf: (entry) => sources.current.get(entry),
      editNonce,
    }
  }, [me, owner, editNonce, originConversation, effectiveConversation, onNavigate])

  /* ACTIONS ARE THE EFFECTIVE CONVERSATION'S. A Deep dive Page reads its own
     conversation: what is read in, replied to and gone home to is that one,
     while the Holder and the Page sequence stay the origin's. */
  const actions = useMemo<PostActions>(
    () => ({
      here: effectiveConversation,
      readIn: effectiveConversation,
      selectMode,
      selected,
      toggleSelect: (id) => store.toggleSelect(id),
      startSelect: (id) => {
        setSelectMode(true)
        if (!store.isSelected(id)) store.toggleSelect(id)
      },
      /* Replying happens in the one Quiet composer, in the reading slot: the
         post is read there and the reader answers it. */
      reply: (id) => onNavigate({ conversation: effectiveConversation, turn: id }),
      goHome: (conversation, post) => onNavigate({ conversation, turn: post }),
      /* `include` and `remove` are deliberately absent: no handler, no
         control, rather than a button that reports a success. */
      busy: false,
    }),
    [effectiveConversation, selectMode, selected, onNavigate],
  )

  /* The toolbar's hosted post acts are the same ones this context provides,
     as Shell does it -- one set of post actions, not two. */
  useEffect(() => {
    providePostActs({ ...actions, here: effectiveConversation })
    return () => providePostActs(null)
  }, [actions, effectiveConversation])

  return (
    <Actions.Provider value={actions}>
      <GovContext.Provider value={gov}>
        {children}
        {/* The portal target, always: it is what takes a sheet or a menu out
            of the stage's clipping and container query. */}
        <div id="fx-layer" data-page={page}>
          <Layer />
        </div>
        <ActionPalette />
        <ToastView />
      </GovContext.Provider>
    </Actions.Provider>
  )
}

export default WorkingProviders
