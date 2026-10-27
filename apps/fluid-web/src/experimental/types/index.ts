/* EXPERIMENTAL: the registry of marked-block TYPES. A type is a meaning, not
   an implementation; each module below may be replaced without touching the
   Markdown that uses it. */
import type { TypeDef } from '../api'
import { chart, checklist, pad } from './basic'
import { compare, review } from './decide'
import { form } from './form'
import { diagram, whiteboard } from './graph'
import { gallery, image } from './media'
import { panel } from './panel'
import { helper } from './helper'
import { problems } from './problems'
import { ref } from './ref'
import { table } from './table'
import { timeline } from './timeline'
import { calendarHeatmap } from './calendar-heatmap'
import { matrixHeatmap } from './matrix-heatmap'
import { statusGrid } from './status-grid'
import { timer } from './timer'

export const TYPES: Record<string, TypeDef> = Object.fromEntries(
  [checklist, chart, pad, form, table, timeline, diagram, whiteboard, image, gallery, compare, review, panel, problems, ref, helper, calendarHeatmap, matrixHeatmap, statusGrid, timer]
    .map((t) => [t.type, t as TypeDef]),
)
