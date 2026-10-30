/* EVERY PROVIDER, INSTALLED ONCE INTO THE ONE REGISTRY (part P3).
 *
 *   surface.ts       the surface verbs (and split, fit, merge, Look, Present,
 *                    Filter, Search where a host lends them)
 *   object.ts        Open, Peek, Keep, Open as workspace, Export, Details,
 *                    Copy link; the object kinds' own actions
 *   post.ts          a post's toolbar and More menu
 *   conversation.ts  the conversation's ⋯ and caption; the launcher tile
 *   workspace.ts     the workspace's Arrange; the Focus lens's bar
 *
 *   ../../magnet/provider.ts  the Magnet's (P7's, and only P7's): magnet.*,
 *                    conversation.makeMagnet, a Magnet's own Open as
 *                    workspace, Search and Remove from workspace */

import { AVAILABLE, registry as theRegistry } from '../registry'
import type { ActionRegistry } from '../types'
import { def } from '../words'
import { openPalette } from '../paletteStore'
import { surfaceDefs } from './surface'
import { OBJECT_KINDS, objectDefs, resourceDefs } from './object'
import { postDefs } from './post'
import { conversationDefs, launcherDefs } from './conversation'
import { lensDefs, workspaceDefs } from './workspace'
import { selectionDefs } from './selection'
import { pageDefs } from './page'
import { installMagnets } from '../../magnet/provider'

/** "Find an action…": the last row of every T2, which opens the palette on
 *  the same target. */
export const findActionDef = def('findAction', {
  plane: 'surface', writes: 'none',
  available: () => AVAILABLE,
  run: (target, ctx) => openPalette({ target, ctx, name: target.surface?.state.id ?? target.resource?.address ?? 'here' }),
})

const installed = new WeakSet<ActionRegistry>()
/** Install every provider into `r` (the one registry, or a test's own). */
export function installProviders(r: ActionRegistry = theRegistry) {
  if (installed.has(r)) return r
  installed.add(r)
  for (const d of [...surfaceDefs(), ...resourceDefs(), ...workspaceDefs(), findActionDef]) r.register(d)
  for (const k of OBJECT_KINDS) r.provide(k, objectDefs)
  r.provide('post', postDefs)
  r.provide('selection', selectionDefs)
  r.provide('surface:page-panel', pageDefs)
  r.provide('conversation', conversationDefs)
  r.provide('surface:launcher-tile', launcherDefs)
  r.provide('surface:lens', lensDefs)
  installMagnets(r)
  return r
}

/** Forget that `r` was installed (tests that reset it). */
export function uninstall(r: ActionRegistry) { installed.delete(r) }
