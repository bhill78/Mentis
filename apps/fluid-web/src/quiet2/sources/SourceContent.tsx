/* WHAT MENTIS HOLDS FROM A SOURCE, READ (Manage Sources in Quiet Chat): one
 * held file or record, one observation of it, or two compared. The reader is
 * Fluid's own (surfaces/sources/Object.tsx, Compare.tsx), hosted: provenance,
 * versions, links, extracted text and pages are exactly what they are there.
 *
 * Shown in a working column beside the source (Surface.tsx) or in place in
 * the centre column (SourceMain.tsx). Wherever it is, moving on from it --
 * another version, a linked file, a comparison -- goes forward in the same
 * place; only "the source itself" leaves it. */
import type { Id } from '../../api'
import Compare from '../../surfaces/sources/Compare'
import ObjectPage from '../../surfaces/sources/Object'
import type { SourcesRoute } from '../../surfaces/sources/route'
import '../../surfaces/sources/sources.css'
import './sources.css'

/** What is being read, in a few words, for a header. */
export function contentWords(r: SourcesRoute): string {
  if (r.at === 'object') return r.key.split('/').filter(Boolean).pop() ?? r.key
  if (r.at === 'observation') return r.span ? 'A search hit' : 'One version'
  if (r.at === 'compare') return 'Two versions compared'
  return 'Source content'
}

export default function SourceContent({ route, onRoute, onSource }: {
  route: SourcesRoute
  /** forward to other content, in this same place */
  onRoute: (r: SourcesRoute) => void
  /** to the source's own page */
  onSource: (col: Id) => void
}) {
  const go = (r: SourcesRoute) => {
    if (r.at === 'object' || r.at === 'observation' || r.at === 'compare') onRoute(r)
    else if (r.at === 'collection') onSource(r.col)
  }
  return (
    <div className="q2-src-host q2-src-content">
      {route.at === 'object' && <ObjectPage key={route.col + route.key} col={route.col} objectKey={route.key} go={go} />}
      {route.at === 'observation' && (
        <ObjectPage key={route.ref + (route.extraction ? `~${route.extraction}` : '') + (route.span ? `@${route.span.offset}-${route.span.end}` : '')}
          pinned={route.ref} span={route.span} extraction={route.extraction} go={go} />
      )}
      {route.at === 'compare' && <Compare a={route.a} b={route.b} go={go} />}
    </div>
  )
}
