/* THE RESULT CHOOSER ON ITS OWN, over the frozen Magnet fixture.
 *
 * Why a harness: the chooser is mounted into the conversation by the
 * integrator's own patch (Quiet2.tsx has one editor), so until that lands
 * there is no place in the running application to drive it from. This mounts
 * the real component with the real fixture and a host that records what it
 * was asked to open, so the keyboard walk, the paging and the narrow layout
 * can be checked for real in a browser rather than asserted from markup.
 *
 * It is not the application: no Brain, no server, no router, no opener. What
 * it proves is what the chooser does with what it is given. */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import ResultsEntry from '../../../src/quiet2/results/ResultsEntry'
import type { MoreResults, ResultChoice, ResultsHost, SourceChoice } from '../../../src/quiet2/results/host'
import {
  crowdedFirstPage, group88Rest, olderPage, overview, wideRest, WORK,
} from '../magnetResults'

declare global {
  interface Window {
    __chosen: { work: string; group: string; ref: string }[]
    __sources: { work: string; group: string }[]
    __reads: string[]
  }
}

window.__chosen = []
window.__sources = []
window.__reads = []

const wait = (ms: number) => new Promise((go) => setTimeout(go, ms))

/** The host's continuation reads, as the server's pages would arrive. */
const more: MoreResults = {
  async groupsBefore(work, cursor) {
    window.__reads.push(`groups:${work}:${cursor}`)
    await wait(20)
    return olderPage
  },
  async itemsAfter(work, group, cursor) {
    window.__reads.push(`items:${work}:${group}:${cursor}`)
    await wait(20)
    return group === 'grp-80-wide' ? wideRest : group88Rest
  },
}

const host: ResultsHost = {
  open: (c: ResultChoice) => window.__chosen.push({ work: c.work, group: c.group.id, ref: c.item.ref }),
  openSource: (c: SourceChoice) => window.__sources.push({ work: c.work, group: c.group.id }),
  more,
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <section data-scenario="f1">
      <h1>F1 · the compact page, #88 within the cap</h1>
      <ResultsEntry results={{ work: WORK, title: 'Yellow Quiet Magnet', mapping: 'update', page: overview }} host={host} />
    </section>
    <section data-scenario="f2">
      <h1>F2 · later rounds fill the cap; #88 is an older group</h1>
      <ResultsEntry results={{ work: WORK, title: 'Yellow Quiet Magnet', mapping: 'request', page: crowdedFirstPage }} host={host} />
    </section>
    <section data-scenario="nohost">
      <h1>No host · listed, not openable here</h1>
      <ResultsEntry results={{ work: WORK, title: 'Yellow Quiet Magnet', mapping: 'work', page: overview }} host={null} />
    </section>
  </StrictMode>,
)
