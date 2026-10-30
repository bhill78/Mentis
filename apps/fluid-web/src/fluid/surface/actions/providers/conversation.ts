/* THE CONVERSATION PROVIDER (rev 3 §6 "Column.tsx conversation ⋯ and caption,
 * ConvLeaf.tsx", rows 19–28; part P3).
 *
 * The conversation surface's ⋯, through the functions it calls today:
 * the about views (nav.openDetail 'about'), Follow (nav.setFollow), the
 * conversation's Focus (threads.setFocused), Minimise, which is Put away
 * (Launcher.minimizeConversation), and Export (api.exportConversation).
 * Own and New here are Home's, lent by Home's column as a host. The Who strip,
 * topics and the agent-work switch are drawn by the column itself: they are
 * listed, and point there, unless the column lends them. */

import type { ActionDef, ActionTarget } from '../types'
import { ABSENT, AVAILABLE, disabled } from '../registry'
import { def } from '../words'
import { hostOf, ops } from './ops'
import { hostAvailable } from './surface'
import { idOf, bodyAction } from './object'

const hostOr = (id: ActionDef['id'], t: ActionTarget, fallback: () => ReturnType<ActionDef['available']>) => hostAvailable(id, t) ?? fallback()
const runHostOr = (id: ActionDef['id'], t: ActionTarget, fallback: () => void | Promise<void>) => { const op = hostOf(t)?.[id]; return op ? op.run() : fallback() }
const isConv = (t: ActionTarget) => t.resource?.kind === 'conversation'

export function conversationDefs(t: ActionTarget): ActionDef[] {
  if (!isConv(t)) return []
  const id = idOf(t)
  const homeOnly = (x: 'conversation.own' | 'conversation.newHere') => def(x, {
    plane: 'resource', writes: 'none',
    available: () => hostAvailable(x, t) ?? ABSENT,
    run: () => runHostOr(x, t, () => { throw new Error('Only on Home') }),
  })
  return [
    def('conversation.views', {
      plane: 'resource', writes: 'none',
      available: () => hostOr('conversation.views', t, () => AVAILABLE),
      run: () => runHostOr('conversation.views', t, () => ops.conversationViews(id)),
    }),
    homeOnly('conversation.own'),
    homeOnly('conversation.newHere'),
    bodyAction('conversation.topics', ['conversation'], 'Choose a topic from the chips above the conversation', 'none'),
    def('filter', {
      plane: 'surface', writes: 'none',
      available: () => hostOr('filter', t, () => disabled("Use the Who strip and the agent-work switch above the conversation", 'scope', false)),
      run: () => runHostOr('filter', t, () => { throw new Error('Use the Who strip above the conversation') }),
    }),
    /* Follow and Hold: the conversation's one follow switch (row 20) */
    def('follow', {
      plane: 'surface', writes: 'none',
      available: () => hostOr('follow', t, () => (ops.following() ? ABSENT : AVAILABLE)),
      run: () => runHostOr('follow', t, () => ops.setFollow(true)),
    }),
    def('hold', {
      plane: 'surface', writes: 'none',
      available: () => hostOr('hold', t, () => (ops.following() ? AVAILABLE : ABSENT)),
      run: () => runHostOr('hold', t, () => ops.setFollow(false)),
    }),
    /* the conversation's Focus ⤢/⤡ is Focus and Exit focus (row 21) */
    def('focus', {
      plane: 'surface', writes: 'none',
      available: () => hostOr('focus', t, () => (ops.conversationFocused() ? ABSENT : AVAILABLE)),
      run: () => runHostOr('focus', t, () => ops.setConversationFocused(true)),
    }),
    def('exitFocus', {
      plane: 'surface', writes: 'none',
      available: () => hostOr('exitFocus', t, () => (ops.conversationFocused() ? AVAILABLE : ABSENT)),
      run: () => runHostOr('exitFocus', t, () => ops.setConversationFocused(false)),
    }),
    /* Minimise is Put away (row 22); the launcher's restore is Bring back (row 23) */
    def('putAway', {
      plane: 'surface', writes: 'placement',
      available: () => hostOr('putAway', t, () => (ops.conversationPutAway() ? ABSENT : AVAILABLE)),
      run: () => runHostOr('putAway', t, () => ops.putConversationAway()),
    }),
    def('bringBack', {
      plane: 'surface', writes: 'placement',
      available: () => hostOr('bringBack', t, () => (ops.conversationPutAway() ? AVAILABLE : ABSENT)),
      run: () => runHostOr('bringBack', t, () => ops.bringConversationBack()),
    }),
  ]
}

/** The launcher tile: the conversation put away (rows 23, 45). Tap is Bring
 *  back; its menu's three targets are the tile's own variants. */
export function launcherDefs(t: ActionTarget): ActionDef[] {
  return [
    def('bringBack', {
      plane: 'surface', writes: 'placement', lead: true,
      available: () => hostOr('bringBack', t, () => AVAILABLE),
      run: () => runHostOr('bringBack', t, () => ops.bringConversationBack()),
    }),
  ]
}
