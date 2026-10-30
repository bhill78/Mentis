/* THE MAGNET ACTION PROVIDER (plan adm-b848fa881c8d §3.5, §3.10; part P7).
 *
 * Owned and installed only here (providers/index.ts calls installMagnets).
 * There is no Magnet toolbar or menu of its own: a Magnet's T1, T2 and the
 * palette are the one registry's list for its target, as for every surface.
 *
 *   conversation.makeMagnet  the conversation's convenience entry (Switcher,
 *                            the conversation's ⋯, the palette): prepares a
 *                            seed and calls the generic magnet.create path
 *   magnet.create            generic creation from a seed (the workspace's
 *                            palette): no conversation provider needed
 *   magnet.tab               the compact pane's tabs
 *   magnet.configure,        the configuration editor: kept in the list,
 *   magnet.reconfigure       disabled with the stage-B reason
 *   openAsWorkspace          a one-conversation Magnet opens that
 *                            conversation's place (nav.openPlace); no config
 *                            change; other Magnets say why not
 *   search                   the compact pane's Search tab
 *   removeFromWorkspace      the shared zone out (server patch), then its
 *                            config forgotten; asks first
 *
 * Surface verbs (Expand, Collapse, Dock, Float, Close…) are the shared ones:
 * they run through workspace.apply with the Magnet's own id.
 *
 * Browser-free: what an action finally does is bound in client.ts. */

import type { ActionDef, ActionTarget, ActionRegistry, SpecificId } from '../actions/types'
import { ABSENT, AVAILABLE, disabled } from '../actions/registry'
import { def } from '../actions/words'
import type { MagnetConfig, MagnetId, MagnetSeed } from './types'
import { MAGNET_CHOICES, conversationSeed } from './choices'
import { BUILD_ENV, MAGNET_CONFIG_GONE, STAGE_B, conversationOf, magnetAvailability, type AdapterRegistry, type TabId } from './model'

/** What the Magnet actions do, bound once by the app (client.ts); a test binds spies. */
export interface MagnetOps {
  /** null where Make magnet may run, else why not */
  notHere(): string | null
  config(id: MagnetId): MagnetConfig | undefined
  existing(conversation: string): MagnetId | null
  create(seed: MagnetSeed, name: string): Promise<MagnetConfig>
  reveal(id: MagnetId): void
  /** the conversation shown here and its name, for generic creation */
  current(): { conversation: string; name: string } | null
  conversationName(conversation: string): string
  showTab(id: MagnetId, tab: TabId): void
  remove(id: MagnetId, name: string): Promise<void>
  /** the source adapters availability is judged by */
  adapters(): AdapterRegistry
}
/* Unbound (a test of other providers), the Magnet offers nothing. */
let ops: MagnetOps | null = null
export function bindMagnetOps(o: MagnetOps | null) { ops = o }
const bound = (): MagnetOps => { if (!ops) throw new Error('the Magnet actions are not bound'); return ops }

type MagnetActionId = Extract<SpecificId, `magnet.${string}` | 'conversation.makeMagnet'>
export const MAGNET_WORDS: Record<MagnetActionId, { label: string; glyph: string; group: ActionDef['group']; says: string; synonyms: string[] }> = {
  'conversation.makeMagnet': { label: 'Make magnet', glyph: '◉', group: 'arrange', says: 'Make magnet: a small live view of this conversation in your workspace', synonyms: ['open as magnet', 'magnet', 'pin conversation', 'watch'] },
  'magnet.create': { label: 'New magnet', glyph: '⊚', group: 'arrange', says: 'New magnet: a live view, here, of what you choose to collect', synonyms: ['create magnet', 'add magnet', 'magnet'] },
  'magnet.tab': { label: 'Tabs', glyph: '⊟', group: 'view', says: 'Its tabs: posts, files, images and search', synonyms: ['posts', 'files', 'images', 'switch tab'] },
  'magnet.configure': { label: 'Configure', glyph: '⚒', group: 'look', says: 'Configure: what it collects, how and when', synonyms: ['settings', 'sources', 'selection', 'magnet settings'] },
  'magnet.reconfigure': { label: 'Change what it collects', glyph: '⟴', group: 'look', says: 'Change its sources or selection, keeping the same Magnet', synonyms: ['reconfigure', 'renderer', 'change sources'] },
}
const word = (id: MagnetActionId, d: Pick<ActionDef, 'plane' | 'writes' | 'available' | 'run'> & Partial<Pick<ActionDef, 'lead'>>): ActionDef => {
  const w = MAGNET_WORDS[id]
  return { id, label: w.label, glyph: w.glyph, group: w.group, synonyms: w.synonyms, ...d }
}

const magnetId = (t: ActionTarget): MagnetId | null => {
  const a = t.resource?.address
  return a?.startsWith('magnet:') ? a.slice(7) as MagnetId : null
}
const conversationIdOf = (t: ActionTarget): string | null => {
  const a = t.resource?.address
  return t.resource?.kind === 'conversation' && a ? (a.startsWith('conversation:') ? a.slice(13) : a) : null
}

/** magnet.create's one path: a seed, made into a Magnet here. Every entry
 *  point (Make magnet, the palette) comes through this. */
export async function createFromSeed(seed: MagnetSeed, name: string): Promise<MagnetConfig> {
  const o = bound()
  const why = o.notHere()
  if (why) throw new Error(why)
  return o.create(seed, name)
}

/** Make magnet for `conversation`: the one here already, revealed, or a new one. */
export async function makeMagnetFor(conversation: string): Promise<MagnetId> {
  const o = bound()
  const had = MAGNET_CHOICES.secondMake === 'reveal' ? o.existing(conversation) : null
  if (had) { o.reveal(had); return had }
  const made = await createFromSeed(conversationSeed(conversation), o.conversationName(conversation))
  o.reveal(made.id)
  return made.id
}

/** The conversation's Make magnet. */
export function conversationMagnetDefs(t: ActionTarget): ActionDef[] {
  const conversation = conversationIdOf(t)
  if (!conversation || !ops) return []
  return [word('conversation.makeMagnet', {
    plane: 'resource', writes: 'placement',
    available: () => { const why = bound().notHere(); return why ? disabled(why, 'scope', false) : AVAILABLE },
    run: async () => { await makeMagnetFor(conversation) },
  })]
}

/** The workspace's generic New magnet, from the palette: seeded with the
 *  conversation shown, without the conversation provider. */
export function workspaceMagnetDefs(): ActionDef[] {
  if (!ops) return []
  return [word('magnet.create', {
    plane: 'resource', writes: 'placement',
    available: () => {
      const o = bound()
      const why = o.notHere()
      return why ? disabled(why, 'scope', false) : o.current() ? AVAILABLE : disabled('Nothing here to collect from yet.', 'source', false)
    },
    run: async () => {
      const o = bound()
      const here = o.current()
      if (!here) throw new Error('Nothing here to collect from yet.')
      const made = await createFromSeed(conversationSeed(here.conversation), here.name)
      o.reveal(made.id)
    },
  })]
}

/** A Magnet's own actions, by its config's availability. */
export function magnetDefs(t: ActionTarget): ActionDef[] {
  const id = magnetId(t)
  if (!id || !ops) return []
  const o = ops
  const config = o.config(id)
  const avail = config ? magnetAvailability(config, BUILD_ENV, o.adapters()) : null
  const of = (a: 'magnet.tab' | 'search' | 'openAsWorkspace' | 'magnet.configure' | 'magnet.reconfigure') =>
    (avail ? avail.get(a) ?? ABSENT : disabled(MAGNET_CONFIG_GONE, 'state', true))
  const name = (config && o.conversationName(conversationOf(config) ?? '')) || 'Magnet'
  return [
    word('magnet.tab', { plane: 'surface', writes: 'none', available: () => of('magnet.tab'), run: () => o.showTab(id, 'post') }),
    def('search', { plane: 'resource', writes: 'none', available: () => of('search'), run: () => o.showTab(id, 'search') }),
    def('openAsWorkspace', {
      plane: 'resource', writes: 'none',
      available: () => of('openAsWorkspace'),
      /* navigation only: no config is changed; Back returns to the Magnet */
      run: (_t, ctx) => {
        const c = conversationOf(o.config(id))
        if (!c) throw new Error('Only a Magnet of one conversation opens as a workspace.')
        ctx.nav.openPlace(c)
      },
    }),
    word('magnet.configure', { plane: 'resource', writes: 'placement', available: () => of('magnet.configure'), run: () => { throw new Error(STAGE_B) } }),
    word('magnet.reconfigure', { plane: 'resource', writes: 'placement', available: () => of('magnet.reconfigure'), run: () => { throw new Error(STAGE_B) } }),
    /* the shared zone leaves the workspace on every device, then its config */
    def('removeFromWorkspace', { plane: 'surface', writes: 'placement', available: () => AVAILABLE, run: () => o.remove(id, name) }),
  ]
}

/** Install the Magnet provider into `r` (providers/index.ts). */
export function installMagnets(r: ActionRegistry) {
  r.provide('conversation', conversationMagnetDefs)
  r.provide('workspace', workspaceMagnetDefs)
  r.provide('magnet', magnetDefs)
}
