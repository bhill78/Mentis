/* PAGE-SPECIFIC ACTIONS (rev 3 row 57; part P3). */

import type { ActionDef, ActionTarget } from '../types'
import { AVAILABLE } from '../registry'
import { def } from '../words'
import { ops } from './ops'

export function pageDefs(t: ActionTarget): ActionDef[] {
  return [def('removeFromWorkspace', {
    plane: 'surface', writes: 'placement', available: () => AVAILABLE,
    run: () => ops.closePage(t.surface!.id),
  })]
}
