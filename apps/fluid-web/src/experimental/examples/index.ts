/* EXPERIMENTAL: every gallery example, in display order. */
import { basicExamples } from './basic'
import { dataExamples } from './data'
import { graphExamples } from './graph'
import { mediaExamples } from './media'
import type { Example } from './model'
import { dungeonExamples } from './dungeon'
import { problemExamples } from './problems'
import { refExamples } from './ref'
import { heatmapExamples } from './heatmaps'

export type { Example } from './model'
export const EXAMPLES: Example[] = [...dungeonExamples, ...refExamples, ...problemExamples, ...basicExamples, ...dataExamples, ...graphExamples, ...mediaExamples, ...heatmapExamples]
