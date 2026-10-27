import { when } from '../../api'
import { bytes, count, type SourcesAnswer, type SourcesRoute } from './route'

/* ------------------------------------------------------------------------ *
 * MANAGE SOURCES (U3): every collection, what it is, and its state here.
 *
 * Material acquired into this Brain and usable from every Conversation. Each
 * item is a past observation held here, not the live source -- the subtitle
 * says so, because a list of folders reads as a list of live folders unless
 * somebody says otherwise. The state is THIS machine's: bound or not. An
 * unbound collection stays fully readable; nothing is inferred from it.
 * ------------------------------------------------------------------------ */

export default function Overview({
  data,
  go,
}: {
  data: SourcesAnswer
  go: (r: SourcesRoute) => void
}) {
  const label = (id: string) => data.descriptors.find((d) => d.id === id)?.label ?? id
  return (
    <section className="src-page">
      <header className="src-head">
        <h1>Manage Sources</h1>
        <button className="btn primary" onClick={() => go({ at: 'add' })}>
          + Add source
        </button>
      </header>
      <p className="src-sub">
        Material acquired into this Brain, usable from every Conversation. Each item is a past
        observation held here, not the live source.
      </p>
      {data.collections.length === 0 && (
        <p className="src-empty">
          No sources yet. Add a folder on this machine to acquire its notes and documents.
        </p>
      )}
      {data.collections.map((c) => (
        <article key={c.collection} className="src-card">
          <div className="src-card-top">
            <button className="src-card-name" onClick={() => go({ at: 'collection', col: c.collection, tab: 'overview' })}>
              {c.name}
            </button>
            <span className="src-chip">{label(c.connector)}</span>
            <span className={'src-chip ' + (c.binding.bound ? 'ok' : 'att')}>{c.state}</span>
            <span className="src-faint src-right">
              {c.last_sweep ? `last sweep ${when(c.last_sweep.at)}` : 'never swept'}
            </span>
          </div>
          <p className="src-m">
            {count(c.counts.present)} present · {count(c.counts.absent)} absent ·{' '}
            {count(c.counts.links_to)} links and {count(c.counts.embeds)} embeds as authored ·{' '}
            {bytes(c.counts.held_bytes)} held
            {c.counts.visible_not_selected !== null &&
              ` · ${count(c.counts.visible_not_selected)} visible, not selected`}
          </p>
          <p className="src-m">
            This machine:{' '}
            {c.binding.bound ? (
              <>
                bound to a {data.descriptors.find(d => d.id === c.connector)?.binding === 'local-file' ? 'file' : 'folder'} <span className="src-mono">{c.binding.binding}</span>
              </>
            ) : (
              <>not bound. Readable, and cannot refresh until bound here. Nothing is inferred from that.</>
            )}{' '}
            ·{' '}
            {c.binding.bound && (
              <>
                <button className="link" onClick={() => go({ at: 'collection', col: c.collection, tab: 'plan' })}>
                  Refresh
                </button>{' '}
                ·{' '}
              </>
            )}
            <button className="link" onClick={() => go({ at: 'collection', col: c.collection, tab: 'browse' })}>
              Browse
            </button>{' '}
            ·{' '}
            <button className="link" onClick={() => go({ at: 'collection', col: c.collection, tab: 'sweeps' })}>
              History
            </button>
          </p>
        </article>
      ))}
    </section>
  )
}
