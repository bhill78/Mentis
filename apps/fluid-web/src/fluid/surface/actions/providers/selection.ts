/* THE SELECTION PROVIDER (rev 3 row 14; part P3).
 * Compare and exporting one archive stay deferred. These actions call the
 * exact callbacks used by Column.tsx's SelectionBar and supplied by Shell. */

import type { ActionDef, ActionTarget } from '../types'
import { ABSENT, AVAILABLE, disabled } from '../registry'
import { def } from '../words'
import { ops } from './ops'

export function selectionDefs(t: ActionTarget): ActionDef[] {
  const a = ops.selectionActs()
  const ready = () => !a || !t.selection?.length ? ABSENT
    : a.busy ? disabled('Busy: the last change is still being made') : AVAILABLE
  return [
    def('selection.keepConversation', {
      plane: 'resource', writes: 'record', multi: 'together', available: ready,
      run: () => a!.keepConversation(),
    }),
    def('selection.include', {
      plane: 'resource', writes: 'record', multi: 'together', available: ready,
      run: () => a!.include(),
    }),
    def('selection.remove', {
      plane: 'resource', writes: 'record', multi: 'together',
      available: () => !a?.remove ? ABSENT : ready(),
      run: () => a!.remove!(),
    }),
  ]
}
