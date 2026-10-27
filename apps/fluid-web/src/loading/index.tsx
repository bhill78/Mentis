/* THE SECTION LOADER: what each section says about its read, drawn (timer
 * build, package B; updated Workstream C for stage-anchored indicators).
 * The store is ./sections.ts; this is how a section reports to it and how
 * the page shows it:
 *
 *   useSectionLoad(id, label, state)  a section's loading / error / data,
 *                                     reported as it changes, dropped when
 *                                     the section leaves the page
 *   <SectionSpin id>                  the spinner in that section's header,
 *                                     only while it loads (the section sets
 *                                     aria-busy from `useSectionPhase`)
 * ------------------------------------------------------------------------ */
import { useEffect, useRef, useSyncExternalStore } from 'react'
import { sections, type LoadState, type Phase } from './sections'
import './loading.css'

export { sections } from './sections'
export type { LoadState, Phase } from './sections'

/** Report this section's read to the page's loader. Returns its phase. */
export function useSectionLoad(id: string | null, label: string, state: LoadState): Phase | null {
  const retry = useRef(state.retry)
  retry.current = state.retry
  const failure = state.error ? (typeof state.error === 'string' ? state.error : (state.error as { message?: string }).message ?? 'failed') : null
  const have = state.data !== null && state.data !== undefined
  useEffect(() => {
    if (!id) return
    sections.report(id, label, { loading: state.loading, error: failure, data: have ? true : null, retry: () => retry.current?.() })
  }, [id, label, state.loading, failure, have])
  useEffect(() => (id ? () => sections.drop(id) : undefined), [id])
  return useSectionPhase(id)
}

/** A section's phase, read back (for its header and aria-busy). */
export function useSectionPhase(id: string | null | undefined): Phase | null {
  useSyncExternalStore(sections.subscribe, sections.version)
  return id ? sections.phase(id) : null
}

/** The header's spinner, while the section loads. */
export function SectionSpin({ id, label }: { id: string | null | undefined; label?: string }) {
  const phase = useSectionPhase(id)
  if (phase !== 'loading') return null
  return <span className="ld-spin" role="img" aria-label={label ? `${label} is loading` : 'loading'} />
}

/** The global strip is retired (Workstream C); stage-anchored contextual indicators are used. */
export function LoaderStrip() {
  return null
}
