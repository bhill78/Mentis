/* RESOURCE VERBS AND THE OBJECT PROVIDER (rev 3 §2.2, §4, §6; part P3).
 *
 * The object row (objects/actions.ts `act`, ObjectActions.tsx) is the
 * registry's first client: Open, Peek, Keep here are its act.open, act.peek
 * and act.keep (Float, Make primary and Focus are the surface verbs, which on
 * an object run act.float, act.primary and act.focus: surface.ts).
 *
 * Specific actions whose control is drawn by the object's own body today
 * (a file's download link, a form's fields, a run's consent panel) are
 * offered with the host's function where a host lends it, and otherwise
 * listed disabled with where to find them -- never silently missing. */

import type { Availability } from '../../types'
import type { ActionDef, ActionTarget, SpecificId } from '../types'
import { ABSENT, AVAILABLE, disabled } from '../registry'
import { def } from '../words'
import { hostOf, ops } from './ops'
import { hostAvailable } from './surface'

/** The kinds the object provider speaks for (objects/registry kinds, plus a
 *  Brain entry and a run). */
export const OBJECT_KINDS = ['chart', 'diagram', 'table', 'image', 'media', 'file', 'form', 'link', 'run', 'brain', 'object', 'list', 'graph', 'timeline', 'map'] as const

const kindOf = (t: ActionTarget) => t.resource?.kind
const isObject = (t: ActionTarget) => !!kindOf(t) && (OBJECT_KINDS as readonly string[]).includes(kindOf(t)!)
const addressed = (t: ActionTarget) => isObject(t) || kindOf(t) === 'post'
const anchor = (t: ActionTarget) => ops.anchorOf(t.resource!.address)

/** Open, Peek, Keep, Open as workspace, Export, Details and Copy link: the
 *  resource verbs every addressable resource shares. */
export function resourceDefs(): ActionDef[] {
  const withHost = (id: 'open' | 'peek' | 'keep' | 'openAsWorkspace', ok: (t: ActionTarget) => boolean, run: (t: ActionTarget) => void) => def(id, {
    plane: id === 'keep' ? 'surface' : 'resource', writes: id === 'keep' ? 'placement' : 'none',
    available: (t) => hostAvailable(id, t) ?? (!t.surface && t.resource && ok(t) ? AVAILABLE : ABSENT),
    run: (t) => { const op = hostOf(t)?.[id]; if (op) op.run(); else run(t) },
  })
  return [
    withHost('open', addressed, (t) => ops.object.open(t.resource!.address, anchor(t))),
    withHost('peek', (t) => addressed(t) && kindOf(t) !== 'run', (t) => ops.object.peek(t.resource!.address, anchor(t))),
    withHost('keep', (t) => addressed(t) && kindOf(t) !== 'run', (t) => ops.object.keep(t.resource!.address, anchor(t))),
    /* a single post, a file, a link and a run have no workspace of their own */
    withHost('openAsWorkspace', (t) => isObject(t) && !['file', 'link', 'run'].includes(kindOf(t)!), (t) => ops.openAsPage(t.resource!.address)),
    def('export', {
      plane: 'resource', writes: 'none', multi: 'together',
      available: (t) => hostAvailable('export', t) ?? (kindOf(t) === 'post' || kindOf(t) === 'conversation' ? AVAILABLE : ABSENT),
      run: async (t) => {
        const op = hostOf(t)?.export
        if (op) return op.run()
        const id = idOf(t)
        if (kindOf(t) === 'post') await ops.exportTurn(id)
        else await ops.exportConversation(id)
      },
    }),
    def('details', {
      plane: 'resource', writes: 'none',
      available: (t) => hostAvailable('details', t) ?? (kindOf(t) === 'post' ? AVAILABLE : ABSENT),
      run: (t) => { const op = hostOf(t)?.details; if (op) op.run(); else ops.openPostDetails(idOf(t)) },
    }),
    def('copyLink', {
      plane: 'resource', writes: 'none',
      available: (t) => hostAvailable('copyLink', t) ?? (kindOf(t) === 'post' && ops.post(idOf(t))?.home ? AVAILABLE : ABSENT),
      run: async (t) => {
        const op = hostOf(t)?.copyLink
        if (op) return op.run()
        const p = ops.post(idOf(t))
        if (!p?.home) return
        await ops.copy(ops.postLink(p), `A link to ${p.number != null ? '#' + p.number : 'the post'} is copied.`)
      },
    }),
  ]
}

/** The id an address names: `post:<id>` → `<id>`. */
export const idOf = (t: ActionTarget) => { const a = t.resource?.address ?? ''; const i = a.indexOf(':'); return i < 0 ? a : a.slice(i + 1) }

/** A specific action drawn by the object's own body today: the host's
 *  function where lent, else disabled saying where it is. */
export function bodyAction(id: Exclude<SpecificId, `magnet.${string}` | 'conversation.makeMagnet'>, kinds: readonly string[], where: string, writes: ActionDef['writes'], extra: Partial<Pick<ActionDef, 'lead'>> = {}): ActionDef {
  return def(id, {
    plane: 'resource', writes, ...extra,
    available: (t): Availability => !kinds.includes(kindOf(t) ?? '') ? ABSENT : hostAvailable(id, t) ?? disabled(where, 'scope', false),
    run: (t) => { const op = hostOf(t)?.[id]; if (!op) throw new Error(where); op.run() },
  })
}

/** The object kinds' own actions (rev 3 §4: at most one lead per kind). */
export function objectDefs(t: ActionTarget): ActionDef[] {
  switch (kindOf(t)) {
    case 'file': return [bodyAction('file.download', ['file'], 'Download it from the file where it is shown', 'none', { lead: true })]
    case 'link': return [bodyAction('link.openExternal', ['link'], 'Open the link where it is shown', 'none', { lead: true })]
    case 'form': return [
      bodyAction('form.markReady', ['form'], 'Mark it ready on the form itself', 'record', { lead: true }),
      bodyAction('form.edit', ['form'], 'Edit it where the form is shown at full size', 'record'),
      bodyAction('form.validate', ['form'], 'Check it on the form itself', 'none'),
      bodyAction('form.history', ['form'], "Open its history from the form's ⋯", 'none'),
    ]
    case 'run': return [
      def('run.stop', {
        plane: 'resource', writes: 'record', lead: true,
        available: (x) => hostAvailable('run.stop', x) ?? AVAILABLE,
        run: async (x) => { const op = hostOf(x)?.['run.stop']; if (op) return op.run(); await ops.stopRun(idOf(x)) },
      }),
      bodyAction('run.consent', ['run'], "Change it in the run's consent panel", 'record'),
    ]
    default: return [
      /* Peek's full screen is Expand (row 49): drawn by the viewer itself */
      def('expand', {
        plane: 'surface', writes: 'none',
        available: (x) => (x.surface ? ABSENT : hostAvailable('expand', x) ?? disabled('Peek it, then choose full screen in the viewer', 'scope', false)),
        run: (x) => { const op = hostOf(x)?.expand; if (!op) throw new Error('Peek it first'); op.run() },
      }),
    ]
  }
}
