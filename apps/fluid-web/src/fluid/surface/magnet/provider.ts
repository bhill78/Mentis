/* THE MAGNET ACTION PROVIDER (plan adm-b848fa881c8d §3.5, §3.10; part P7).
 *
 * Owned and installed only here (providers/index.ts calls installMagnets).
 * There is no Magnet toolbar or menu of its own: a Magnet's T1, T2 and the
 * palette are the one registry's list for its target, as for every surface.
 *
 *   conversation.makeMagnet  the conversation's convenience entry (Switcher,
 *                            the conversation's ⋯, the palette): prepares a
 *                            seed and calls the generic magnet.create path
 *   magnet.create            generic creation (the workspace's palette), with no
 *                            conversation provider needed: from the conversation
 *                            shown, or in a workspace of its own from the source
 *                            chosen in the editor (`chooser`, createChosen)
 *   magnet.tab               the compact pane's tabs
 *   magnet.configure,        the configuration editor, in the Magnet's own
 *   magnet.reconfigure       pane: every facet of the same config, sent by
 *                            magnet.reconfigure; reconfigure opens it at
 *                            what it collects
 *   peek                     its quick summary card, anchored to it
 *   openAsWorkspace          "Open its source conversation": a one-conversation
 *                            Magnet opens that conversation's place
 *                            (nav.openPlace); no config change; other Magnets
 *                            say why not
 *   search                   the compact pane's Search tab
 *   removeFromWorkspace      the shared zone out (server patch), then its
 *                            config forgotten; asks first
 *   magnet.activate          one press, one key: its one extract step, once,
 *                            into its own Conversation (activation.ts);
 *                            disabled with the reason where it can't run
 *   magnet.setUpActivation   adds what it lacks of manual activation to the
 *                            same id, through magnet.reconfigure, only when
 *                            pressed; nothing is ever added silently
 *   magnet.conversation      its own Conversation, distinct from its source;
 *                            made on that press if it has none
 *
 * Surface verbs (Expand, Collapse, Dock, Float, Close…) are the shared ones:
 * they run through workspace.apply with the Magnet's own id.
 *
 * Browser-free: what an action finally does is bound in client.ts. */

import type { ActionCtx, ActionDef, ActionTarget, ActionRegistry, SpecificId } from '../actions/types'
import { ABSENT, AVAILABLE, disabled } from '../actions/registry'
import { surfaceDefs } from '../actions/providers/surface'
import { def } from '../actions/words'
import type { MagnetConfig, MagnetId, MagnetSeed } from './types'
import { MAGNET_CHOICES, conversationSeed } from './choices'
import { BUILD_ENV, MAGNET_CONFIG_GONE, conversationOf, magnetAvailability, type AdapterRegistry, type TabId } from './model'

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
  /** where a new Magnet starts by choosing its source (a workspace of its own,
   *  with no conversation shown), what opens the editor for it; else null */
  chooser?(): (() => void) | null
  conversationName(conversation: string): string
  showTab(id: MagnetId, tab: TabId): void
  /** open its configuration editor; `at` the part to start at */
  configure(id: MagnetId, at: 'all' | 'collects'): void
  /** show its quick summary card */
  peek(id: MagnetId): void
  /** open its Look: the shared Look column (zoneMenu.tsx lookGroup), in its window */
  look(id: MagnetId): void
  remove(id: MagnetId, name: string): Promise<void>
  /** the source adapters availability is judged by */
  adapters(): AdapterRegistry
  /** choose a workspace to curate it in; absent, not offered */
  toWorkspace?(what: { kind: 'magnet' | 'conversation'; ref: string; name: string }): void
  /** one press of Activate; how it went is said by what binds it. Absent, not offered */
  activate?(id: MagnetId): Promise<void>
  /** a press is being answered: Activate waits for it */
  activating?(id: MagnetId): boolean
  /** add what it lacks of manual activation to this same Magnet */
  setUpActivation?(id: MagnetId): Promise<void>
  /** its own Conversation's id, made if it has none. Absent, not offered */
  ownConversation?(id: MagnetId): Promise<string>
}
/* Unbound (a test of other providers), the Magnet offers nothing. */
let ops: MagnetOps | null = null
export function bindMagnetOps(o: MagnetOps | null) { ops = o }
const bound = (): MagnetOps => { if (!ops) throw new Error('the Magnet actions are not bound'); return ops }

type MagnetActionId = Extract<SpecificId, `magnet.${string}` | 'conversation.makeMagnet' | 'conversation.toWorkspace'>
export const MAGNET_WORDS: Record<MagnetActionId, { label: string; glyph: string; group: ActionDef['group']; says: string; synonyms: string[] }> = {
  'conversation.makeMagnet': { label: 'Make magnet', glyph: '◉', group: 'arrange', says: 'Make magnet: a small live view of this conversation in your workspace', synonyms: ['open as magnet', 'magnet', 'pin conversation', 'watch'] },
  'conversation.toWorkspace': { label: 'Put in a workspace', glyph: '▦', group: 'arrange', says: 'Put this conversation in a workspace: a new one, or one there is', synonyms: ['workspace', 'new workspace', 'add to workspace'] },
  'magnet.toWorkspace': { label: 'Put in a workspace', glyph: '▦', group: 'arrange', says: 'Put this magnet in a workspace too: the same magnet, in one more place', synonyms: ['workspace', 'new workspace', 'add to workspace'] },
  'magnet.create': { label: 'New magnet', glyph: '⊚', group: 'arrange', says: 'New magnet: a live view, here, of what you choose to collect', synonyms: ['create magnet', 'add magnet', 'magnet'] },
  'magnet.tab': { label: 'Tabs', glyph: '⊟', group: 'view', says: 'Its tabs: posts, files, images and search', synonyms: ['posts', 'files', 'images', 'switch tab'] },
  'magnet.configure': { label: 'Configure', glyph: '⚒', group: 'look', says: 'Configure: what it collects, how and when', synonyms: ['settings', 'sources', 'selection', 'magnet settings'] },
  'magnet.reconfigure': { label: 'Change what it collects', glyph: '⟴', group: 'look', says: 'Change its sources or selection, keeping the same Magnet', synonyms: ['reconfigure', 'renderer', 'change sources'] },
  'magnet.activate': { label: 'Activate', glyph: '⏵', group: 'resource', says: 'Activate: run its one extract step now, once, into its own Conversation', synonyms: ['run', 'run magnet', 'extract', 'manual activation'] },
  'magnet.setUpActivation': { label: 'Set up manual activation', glyph: '⏷', group: 'resource', says: 'Add manual activation with one extract step to this same Magnet; nothing runs until you press Activate', synonyms: ['enable activation', 'manual activation', 'make it runnable'] },
  'magnet.conversation': { label: 'Open its own Conversation', glyph: '⌂', group: 'resource', says: 'Its own Conversation, where what it produces goes: not the one it reads', synonyms: ['magnet conversation', 'own conversation', 'results', 'where it records'] },
}
export const OPEN_SOURCE = 'Open its source conversation'
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

/** The editor's Make magnet: the seed its source was chosen in, where New magnet
 *  starts by choosing one (`chooser`). Nothing is made anywhere else. */
export async function createChosen(seed: MagnetSeed, name: string): Promise<MagnetConfig> {
  const o = bound()
  if (!o.chooser?.()) throw new Error(MAGNET_CHOICES.notHere)
  const made = await o.create(seed, name)
  o.reveal(made.id)
  return made
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
  }), word('conversation.toWorkspace', {
    plane: 'resource', writes: 'none',
    available: () => (bound().toWorkspace ? AVAILABLE : ABSENT),
    run: () => bound().toWorkspace?.({ kind: 'conversation', ref: conversation, name: bound().conversationName(conversation) }),
  })]
}

/** The workspace's generic New magnet, from the palette: seeded with the
 *  conversation shown, without the conversation provider; in a workspace of its
 *  own, where none is shown, the editor opens to choose its source first. */
export function workspaceMagnetDefs(): ActionDef[] {
  if (!ops) return []
  return [word('magnet.create', {
    plane: 'resource', writes: 'placement',
    available: () => {
      const o = bound()
      if (o.chooser?.()) return AVAILABLE
      const why = o.notHere()
      return why ? disabled(why, 'scope', false) : o.current() ? AVAILABLE : disabled('Nothing here to collect from yet.', 'source', false)
    },
    run: async () => {
      const o = bound()
      const choose = o.chooser?.()
      if (choose) { choose(); return }
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
  const of = (a: 'magnet.tab' | 'search' | 'peek' | 'openAsWorkspace' | 'magnet.configure' | 'magnet.reconfigure' | 'magnet.activate' | 'magnet.setUpActivation' | 'magnet.conversation') =>
    (avail ? avail.get(a) ?? ABSENT : disabled(MAGNET_CONFIG_GONE, 'state', true))
  const name = (config && o.conversationName(conversationOf(config) ?? '')) || 'Magnet'
  return [
    word('magnet.activate', {
      plane: 'resource', writes: 'record',
      available: () => {
        if (!o.activate) return ABSENT
        const can = of('magnet.activate')
        return can.state === 'available' && o.activating?.(id) ? disabled('It is running: the answer to this press comes first.', 'state', true) : can
      },
      run: () => o.activate?.(id),
    }),
    word('magnet.setUpActivation', {
      plane: 'resource', writes: 'placement',
      available: () => (o.setUpActivation ? of('magnet.setUpActivation') : ABSENT),
      run: () => o.setUpActivation?.(id),
    }),
    word('magnet.conversation', {
      plane: 'resource', writes: 'record',
      available: () => (o.ownConversation ? of('magnet.conversation') : ABSENT),
      /* never its source's place: that is Open as workspace */
      run: async (_t, ctx) => {
        const c = await o.ownConversation?.(id)
        if (c) ctx.nav.openPlace(c)
      },
    }),
    word('magnet.tab', { plane: 'surface', writes: 'none', available: () => of('magnet.tab'), run: () => o.showTab(id, 'post') }),
    def('search', { plane: 'resource', writes: 'none', available: () => of('search'), run: () => o.showTab(id, 'search') }),
    /* the quick summary card: what it holds, read from its sources, nothing changed */
    def('peek', { plane: 'resource', writes: 'none', available: () => of('peek'), run: () => o.peek(id) }),
    /* LOOK, as a section's and a window's (amendment ent-56d18f7b54a5): the
       same Appearance and the same Look column, for its window -- the
       slide-out, or the pane floating -- and not for its disc or docked */
    def('settings', {
      plane: 'surface', writes: 'placement',
      available: (t) => {
        const s = t.surface?.state
        return config && s?.placement.kind === 'float' && (s.level.override ?? s.level.auto) !== 'icon' ? AVAILABLE : ABSENT
      },
      run: () => o.look(id),
    }),
    /* it goes to that conversation, not a workspace: Put in a workspace is the way to one */
    { ...def('openAsWorkspace', {
      plane: 'resource', writes: 'none',
      available: () => of('openAsWorkspace'),
      /* navigation only: no config is changed; Back returns to the Magnet */
      run: (_t, ctx) => {
        const c = conversationOf(o.config(id))
        if (!c) throw new Error('Only a Magnet of one conversation has a source conversation to open.')
        ctx.nav.openPlace(c)
      },
    }), label: OPEN_SOURCE, says: 'Open the conversation this magnet reads (Back returns); Put in a workspace is the way to a workspace', synonyms: ['open as workspace', 'source', 'conversation', 'open conversation'] },
    /* both open the one editor; what it saves goes through magnet.reconfigure,
       on the same id, never a new Magnet */
    word('magnet.configure', { plane: 'resource', writes: 'placement', available: () => of('magnet.configure'), run: () => o.configure(id, 'all') }),
    word('magnet.reconfigure', { plane: 'resource', writes: 'placement', available: () => of('magnet.reconfigure'), run: () => o.configure(id, 'collects') }),
    /* the same Magnet in one more place: a reference, nothing copied */
    word('magnet.toWorkspace', { plane: 'resource', writes: 'none', available: () => (o.toWorkspace ? AVAILABLE : ABSENT), run: () => o.toWorkspace?.({ kind: 'magnet', ref: id, name }) }),
    /* the shared zone leaves the workspace on every device, then its config */
    def('removeFromWorkspace', { plane: 'surface', writes: 'placement', available: () => AVAILABLE, run: () => o.remove(id, name) }),
    /* NOT CONNECTED FOR A MAGNET, and so said: nothing draws a surface's full
       screen in this build, and wide has no launcher for a Magnet, whose disc is
       where it is put away (capabilities.ts). Offered as they were, each did nothing. */
    ...surfaceDefs().flatMap((d) => d.id === 'fullscreen'
      ? [{ ...d, available: (t: ActionTarget) => (t.surface ? disabled('A Magnet has no full screen in this build: Expand opens it out, and Open as workspace gives its conversation the whole place.', 'runtime', false) : ABSENT) }]
      : d.id === 'putAway'
        ? [{ ...d, available: (t: ActionTarget, ctx: ActionCtx) => {
          if (!t.surface || ctx.cls !== 'wide') return d.available(t, ctx)
          const s = t.surface.state
          return disabled((s.level.override ?? s.level.auto) === 'icon'
            ? 'A Magnet’s disc is already where it is put away on a wide screen. Close here hides it on this device.'
            : 'On a wide screen a Magnet is put away as its disc: Collapse folds it back to it.', 'state', false)
        } }]
        : []),
  ]
}

/** Install the Magnet provider into `r` (providers/index.ts). */
export function installMagnets(r: ActionRegistry) {
  r.provide('conversation', conversationMagnetDefs)
  r.provide('workspace', workspaceMagnetDefs)
  r.provide('magnet', magnetDefs)
}
