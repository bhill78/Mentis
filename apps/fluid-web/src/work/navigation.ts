import { writeAddress } from '../address'
import { addressOf, announceGoTo, entered, HOME, type Place } from '../nav'
import type { TurnLink } from './contract'

export const turnHref = (origin: TurnLink) =>
  `#/c/${origin.conversation}/turn/${origin.turn}`

/** Shared components have no host navigation prop. Use the shell's existing
 * Place/history protocol, including its thread stack and explanation view. */
export function openWorkOrigin(origin: TurnLink, view: 'turn' | 'replies' | 'activity' = 'turn') {
  const state = window.history.state ?? {}
  const was: Place = state.mentis ?? HOME
  const next = entered(was, {
    ...was, conversation: origin.conversation, topic: null, turn: origin.turn,
    gov: null, sources: null, space: false, compare: false, primary: 'conversation',
    depth: view === 'replies' ? [{ kind: 'thread', id: origin.turn }] : [],
    thread: view === 'replies' ? origin.turn : null,
    resolution: view === 'activity' ? 'explanation' : 'glance',
    aux: view === 'replies' ? 'thread' : view === 'activity' ? 'history' : null,
    from: 'shell',
  })
  const pushed = { ...state, mentis: next, depth: (state.depth ?? 0) + 1 }
  window.history.pushState(pushed, '', writeAddress(addressOf(next)))
  window.dispatchEvent(new PopStateEvent('popstate', { state: pushed }))
  announceGoTo(origin.turn)
}
