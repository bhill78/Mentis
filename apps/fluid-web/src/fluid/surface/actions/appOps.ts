/* THE PROVIDERS' OPERATIONS, BOUND TO TODAY'S FUNCTIONS (part P3).
 *
 * Each operation is the call the existing control makes, named where it is
 * made, so a registry action does exactly what its button does:
 *
 *   object.*            objects/actions.ts act (the object row)
 *   openAsPage          workspace/Detail.tsx openAsPage
 *   post acts           Shell's PostActions (render/post.tsx), provided by Shell
 *   details, full,      nav.openDetail, with the toolbar's and card's details
 *   replies
 *   address             frame/Sheet openSheet(addressSheet(id)) (render/post.tsx)
 *   annotate            the post's own ☺ (Annotations.tsx Annotate), pressed
 *   exportTurn,         api.ts exportTurn / exportConversation
 *   exportConversation
 *   views               nav.openDetail 'about' (Column.tsx ConversationMenu)
 *   follow              nav.setFollow (Column.tsx useFollowItem)
 *   conversation focus  conversation/threads setFocused
 *   put away / back     focus/Launcher minimizeConversation / restoreConversation
 *   holder              workspace/place workspace (Arrange.tsx's `h`)
 *   put all away, tidy  model setAllMinimized / tidyFloats through
 *                       workspace.edit(onPage(...)), as Arrange.tsx does
 *   lens                focus/lens lens.restore / keepLayout; lensImpl toggleTidy / toggleHide
 *   stopRun             runs/feed stopRun (RunPanel's Stop) */

import * as nav from '../../nav'
import { wireMagnets } from '../magnet/client'
import { store } from '../../store'
import { exportConversation, exportTurn } from '../../../api'
import { act } from '../../objects/actions'
import { openAsPage } from '../../workspace/Detail'
import { openSheet } from '../../frame/Sheet'
import { addressSheet } from '../../conversation/Addressing'
import { focused, setFocused } from '../../conversation/threads'
import { minimizeConversation, restoreConversation } from '../../focus/Launcher'
import { workspace } from '../../workspace/place'
import { followSlot, splitOuter, zone } from '../../workspace/tree'
import { onPage, pageView, shownPage } from '../../focus/page'
import { setAllMinimized, tidyFloats } from '../../focus/model'
import { lens } from '../../focus/lens'
import { lensOf, toggleHide, toggleTidy } from '../../focus/lensImpl'
import { stopRun } from '../../runs/feed'
import { bindOps, type Ops, type PostActs, type PostFacts, type SelectionActs } from './providers/ops'

let postActs: PostActs | null = null
let selectionActs: SelectionActs | null = null
let here: string | null = null
/** Shell gives its post actions (the ones its Actions context provides). */
export function providePostActs(a: (PostActs & { here: string | null }) | null) { postActs = a; here = a?.here ?? null }
/** Shell supplies the same callbacks that Column.tsx's SelectionBar runs. */
export function provideSelectionActs(a: SelectionActs | null) { selectionActs = a }

const postEl = (id: string) => document.querySelector(`[data-post="${CSS.escape(id)}"]`)
const anchorOf = (address: string): Element | null => (address.startsWith('post:') ? postEl(address.slice(5)) : document.querySelector(`[data-address="${CSS.escape(address)}"]`))
const objectTarget = (address: string, anchor?: Element | null) => ({ address, anchor: (anchor as HTMLElement | null) ?? null })
const floats = () => pageView(workspace.arr, shownPage()).focus?.floats ?? []

export const appOps: Ops = {
  object: {
    open: (a, el) => act.open(objectTarget(a, el)),
    peek: (a, el) => act.peek(objectTarget(a, el)),
    float: (a, el) => act.float(objectTarget(a, el)),
    keep: (a, el) => act.keep(objectTarget(a, el)),
    primary: (a, el) => act.primary(objectTarget(a, el)),
    focus: (a, el) => act.focus(objectTarget(a, el)),
  },
  openPlace: (key) => nav.enter(key),
  back: () => nav.back(),
  openAsPage: (address) => openAsPage(address),
  closePage: (id) => nav.closePage(id),
  anchorOf,
  confirm: (q) => window.confirm(q),
  toast: (text) => nav.toast({ text }),
  copy: async (text, said) => {
    try { await navigator.clipboard.writeText(text); nav.toast({ text: said }) }
    catch (e) { nav.toast({ text: `Could not copy: ${(e as Error).message}` }) }
  },
  post(id, via): PostFacts | null {
    const p = store.posts.get(id)
    if (!p) return null
    const included = (p.memberships ?? []).some((m) => m.conversation === here && m.via === 'linked')
    return { id, home: p.home ?? null, number: p.number ?? null, deleted: !!p.deleted, here, included, via }
  },
  postActs: () => postActs,
  selectionActs: () => selectionActs,
  postLink: (p) => `${location.origin}/fluid?c=${encodeURIComponent(p.home ?? '')}&t=${encodeURIComponent(p.id)}`,
  openPostDetails: (id) => nav.openDetail({ kind: 'post-details', id, anchor: { kind: 'post', id }, mode: 'aside' }),
  openPostFull: (id) => nav.openDetail({ kind: 'full', of: 'post', id, anchor: { kind: 'post', id }, mode: 'over' }),
  openReplies: (id) => nav.openDetail({ kind: 'replies', root: id, anchor: { kind: 'post', id }, mode: 'aside' }),
  openAddress: (id, el) => openSheet(addressSheet(id), el ?? postEl(id) ?? document.body),
  openAnnotate: (id, el) => {
    const button = (el ?? postEl(id))?.querySelector<HTMLButtonElement>('[data-act="annotate"]')
    if (button) button.click()
    else nav.toast({ text: 'Show the post to annotate it.' })
  },
  exportTurn: (id) => exportTurn(id),
  conversationViews: (id) => nav.openDetail({ kind: 'about', conversation: id, section: 'brief', anchor: { kind: 'zone', zone: 'conversation' }, mode: 'aside' }),
  following: () => !!nav.snapshot().follow,
  setFollow: (on) => nav.setFollow(on),
  conversationFocused: () => focused(),
  setConversationFocused: (on) => setFocused(on),
  putConversationAway: () => minimizeConversation(),
  bringConversationBack: () => restoreConversation(),
  conversationPutAway: () => !!pageView(workspace.arr, shownPage()).focus?.minimized,
  exportConversation: (id) => exportConversation(id),
  holder: () => workspace,
  floatsHere: () => ({ count: floats().length, unfolded: floats().filter((f) => !f.pinned && !f.min).length }),
  putAllAway: () => workspace.edit(onPage((a) => setAllMinimized(a, true), shownPage()), 'Minimised all unpinned windows.'),
  tidyFloats: () => {
    const r = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
    workspace.edit(onPage((a) => tidyFloats(a, r?.width ?? 0, r?.height ?? 0), shownPage()), 'Tidied the floating windows.')
  },
  newFollower: () => workspace.edit(onPage((v) => ({ ...v, tree: splitOuter(v.tree, 'right', zone(v.tree, followSlot())) }), shownPage()),
    'Added a section that follows what you read.'),
  lensOn: () => !!lensOf(),
  exitFocus: () => lens.restore(),
  keepLensLayout: () => lens.keepLayout(),
  tidyAround: () => toggleTidy(),
  hideOthers: () => toggleHide(),
  stopRun: (run) => stopRun(run),
}

/** Wire the providers to the app (once, from the shell). */
export function wireActions() { bindOps(appOps); wireMagnets() }
