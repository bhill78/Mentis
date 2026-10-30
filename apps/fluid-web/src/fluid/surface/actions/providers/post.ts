/* THE POST PROVIDER (rev 3 §6 "render/post.tsx row and More menu", rows 1–16;
 * part P3).
 *
 * What a post's toolbar and More menu offer, each through the function the
 * toolbar calls today: Shell's post actions (reply, select, include, remove),
 * the Address and Annotate sheets, nav's details and full-screen views, and
 * api's exportTurn. Include and Remove inclusion ask first, as the toolbar's
 * confirmation does. Full screen is Expand (I-1). */

import type { ActionDef, ActionTarget } from '../types'
import { ABSENT, AVAILABLE, disabled } from '../registry'
import { def } from '../words'
import { hostOf, ops, type PostFacts } from './ops'
import { hostAvailable } from './surface'
import { idOf } from './object'

const num = (p: PostFacts) => (p.number != null ? `#${p.number}` : 'this post')

/** Offered by the host when lent, else by `fallback`. */
const hostOr = (id: ActionDef['id'], t: ActionTarget, fallback: () => ReturnType<ActionDef['available']>) => hostAvailable(id, t) ?? fallback()
const runHostOr = (id: ActionDef['id'], t: ActionTarget, fallback: () => void | Promise<void>) => { const op = hostOf(t)?.[id]; return op ? op.run() : fallback() }

export function postDefs(t: ActionTarget): ActionDef[] {
  const p = ops.post(idOf(t))
  const a = ops.postActs()
  const busy = () => (a?.busy ? disabled('Busy: the last change is still being made') : AVAILABLE)
  if (!p) return []
  const live = !p.deleted
  return [
    def('post.reply', {
      plane: 'resource', writes: 'none', lead: true,
      available: () => hostOr('post.reply', t, () => (a?.reply && live ? AVAILABLE : ABSENT)),
      run: () => runHostOr('post.reply', t, () => a!.reply!(p.id)),
    }),
    def('post.address', {
      plane: 'resource', writes: 'record',
      available: () => hostOr('post.address', t, () => (live && (p.here ?? p.home) ? AVAILABLE : ABSENT)),
      run: () => runHostOr('post.address', t, () => ops.openAddress(p.id, ops.anchorOf(t.resource!.address))),
    }),
    def('post.annotate', {
      plane: 'resource', writes: 'record',
      available: () => hostOr('post.annotate', t, () => (live ? AVAILABLE : ABSENT)),
      run: () => runHostOr('post.annotate', t, () => ops.openAnnotate(p.id, ops.anchorOf(t.resource!.address))),
    }),
    def('post.select', {
      plane: 'resource', writes: 'none', multi: 'each',
      available: () => hostOr('post.select', t, () => (a ? AVAILABLE : ABSENT)),
      run: () => runHostOr('post.select', t, () => a!.startSelect(p.id)),
    }),
    def('post.include', {
      plane: 'resource', writes: 'record', multi: 'each',
      available: () => hostOr('post.include', t, () => (!p.included && a?.include && p.here && p.home && p.home !== p.here ? busy() : ABSENT)),
      run: () => runHostOr('post.include', t, () => {
        if (ops.confirm(`Include ${num(p)} here? It stays in its own conversation; this one shows it too. Nothing is moved or copied.`)) a!.include!(p.id)
      }),
    }),
    def('post.removeInclusion', {
      plane: 'resource', writes: 'record', multi: 'each',
      available: () => hostOr('post.removeInclusion', t, () => (p.included && a?.remove ? busy() : ABSENT)),
      run: () => runHostOr('post.removeInclusion', t, () => {
        if (ops.confirm(`Remove ${num(p)} from here? It stays in its own conversation; only its inclusion here ends. Nothing is deleted.`)) a!.remove!(p.id)
      }),
    }),
    def('post.carries', {
      plane: 'resource', writes: 'none',
      available: () => hostOr('post.carries', t, () => AVAILABLE),
      /* what it carries is listed under the post: read it there */
      run: () => runHostOr('post.carries', t, () => ops.object.open(t.resource!.address, ops.anchorOf(t.resource!.address))),
    }),
    def('thread.replies', {
      plane: 'resource', writes: 'none',
      available: () => hostOr('thread.replies', t, () => AVAILABLE),
      run: () => runHostOr('thread.replies', t, () => ops.openReplies(p.id)),
    }),
    /* More → Full screen is Expand (I-1): the post enlarged over everything */
    def('expand', {
      plane: 'surface', writes: 'none',
      available: () => hostOr('expand', t, () => AVAILABLE),
      run: () => runHostOr('expand', t, () => ops.openPostFull(p.id)),
    }),
  ]
}
