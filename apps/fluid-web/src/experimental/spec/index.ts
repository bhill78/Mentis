/* EXPERIMENTAL: the registry of what every marked-block type READS. The
   drawing registry (../types/index.ts) holds one TypeDef per spec here, built
   by spreading it, so the two cannot name different types (a test holds them
   to it). */
import type { TypeSpec } from './api'
import { chartSpec, checklistSpec, padSpec } from './basic'
import { compareSpec, reviewSpec } from './decide'
import { formSpec } from './form'
import { diagramSpec, whiteboardSpec } from './graph'
import { gallerySpec, imageSpec } from './media'
import { panelSpec } from './panel'
import { helperSpec } from './helper'
import { problemsSpec } from './problems'
import { refSpec } from './ref'
import { tableSpec } from './table'
import { timelineSpec } from './timeline'
import { calendarHeatmapSpec } from './calendar-heatmap'
import { matrixHeatmapSpec } from './matrix-heatmap'
import { statusGridSpec } from './status-grid'
import { timerSpec } from './timer'

export const SPECS: Record<string, TypeSpec> = Object.fromEntries(
  [checklistSpec, chartSpec, padSpec, formSpec, tableSpec, timelineSpec, diagramSpec, whiteboardSpec, imageSpec, gallerySpec, compareSpec, reviewSpec, panelSpec, problemsSpec, refSpec, helperSpec, calendarHeatmapSpec, matrixHeatmapSpec, statusGridSpec, timerSpec]
    .map((t) => [t.type, t as TypeSpec]),
)

export const RENDERABLE: ReadonlySet<string> = new Set(Object.keys(SPECS))
