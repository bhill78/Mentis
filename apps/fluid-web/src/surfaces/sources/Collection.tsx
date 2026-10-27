import { useState } from 'react'
import { post, shortId, useApi, when, type Id } from '../../api'
import Browse from './Browse'
import SqliteEdit from './sqlite/SqliteEdit'
import PickSource from './pick/PickSource'
import { AddressField } from './FilesystemFlow'
import { Confirm, Kept, PreviewBody, Result, RunBar, Tally } from './parts'
import ScopeForm, { optionDefaults, presetOf, sameOptions, type ScopeValue } from './ScopeForm'
import {
  bytes,
  cancelRun,
  count,
  runToEnd,
  takesAddress,
  type CollectionView,
  type Descriptor,
  type Preview,
  type RunView,
  type ScopeOptions,
  type SourcesRoute,
  type SweepResult,
  type Tab,
} from './route'

/* ------------------------------------------------------------------------ *
 * ONE COLLECTION (U6). Overview · Sweeps · Browse · Scope & connection.
 *
 * REFRESH PLANS AGAIN. It is the same preview-then-confirm as the first
 * acquisition, against what the record already holds, so "0 changed" means
 * the folder did not change.
 *
 * REVISE SCOPE IS A PREVIEW TOO. The new filters are surveyed and diffed;
 * confirming records the revision and the sweep under it as one act, so a
 * preview that no longer holds leaves the scope exactly as it was. Material
 * that leaves the scope is NOT EXAMINED and never recorded absent -- the
 * preview shows how much.
 *
 * UNBIND changes nothing in the record. It only forgets, on this machine,
 * which folder this collection is.
 * ------------------------------------------------------------------------ */

const TABS: [Tab, string][] = [
  ['overview', 'Overview'],
  ['sweeps', 'Sweeps'],
  ['browse', 'Browse'],
  ['scope', 'Scope & connection'],
]

export default function Collection({
  col,
  tab,
  descriptors,
  me,
  nameOf,
  go,
  onChanged,
}: {
  col: Id
  tab: Tab
  descriptors: Descriptor[]
  me: Id | null
  nameOf: (id: Id | null | undefined) => string
  go: (r: SourcesRoute) => void
  onChanged: () => void
}) {
  const view = useApi<CollectionView>(`/api/sources/${encodeURIComponent(col)}`)
  const c = view.data
  if (view.error) return <p className="act-refused">{view.error}</p>
  if (!c) return <p className="src-faint">reading the record…</p>
  const d = descriptors.find((x) => x.id === c.connector)
  const changed = () => {
    view.reload()
    onChanged()
  }
  return (
    <section className="src-page">
      <header className="src-head">
        <h1>{c.name}</h1>
      </header>
      <p className="src-sub">
        {d?.label ?? c.connector} · declared by {nameOf(c.declared_by)} {when(c.declared_at)} ·{' '}
        <span className={'src-chip ' + (c.binding.bound ? 'ok' : 'att')}>{c.state}</span>
      </p>
      {c.last_sweep && (
        <p className="src-banner ok">
          Swept {when(c.last_sweep.at)} · <span className="src-mono">{shortId(c.last_sweep.act, 14)}</span> · batch{' '}
          <span className="src-mono">{c.last_sweep.batch}</span> · {count(c.last_sweep.counts?.new)} new ·{' '}
          {count(c.last_sweep.counts?.changed)} changed · {count(c.last_sweep.counts?.absent)} absent ·{' '}
          {count(c.last_sweep.counts?.withheld)} withheld · {count(c.last_sweep.counts?.not_examined)} not examined
        </p>
      )}
      <nav className="src-tabs" aria-label="collection">
        {TABS.map(([t, label]) => (
          <button
            key={t}
            className={'src-tab' + (t === tab ? ' on' : '')}
            aria-current={t === tab || undefined}
            onClick={() => go({ at: 'collection', col, tab: t })}
          >
            {label}
          </button>
        ))}
        {c.binding.bound && (
          <button
            className={'src-tab' + (tab === 'plan' ? ' on' : '')}
            onClick={() => go({ at: 'collection', col, tab: 'plan' })}
          >
            Refresh…
          </button>
        )}
      </nav>
      {tab === 'overview' && <OverviewTab c={c} />}
      {tab === 'sweeps' && <Sweeps c={c} nameOf={nameOf} />}
      {tab === 'browse' && (
        <Browse
          col={col}
          browse={d?.browse ?? 'hierarchy'}
          onOpen={(key) => go({ at: 'object', col, key })}
          onHit={(ref, span, extraction) => go({ at: 'observation', ref, span, extraction })}
        />
      )}
      {tab === 'scope' && d && <ScopeTab c={c} d={d} me={me} nameOf={nameOf} onChanged={changed} onOffer={(connector) => go({ at: 'flow', connector })} />}
      {tab === 'plan' && <Refresh c={c} me={me} onChanged={changed} onOffer={(connector) => go({ at: 'flow', connector })} />}
    </section>
  )
}

function OverviewTab({ c }: { c: CollectionView }) {
  const n = c.counts
  return (
    <>
      <Tally
        cells={[
          [n.present, 'present'],
          [n.absent, 'absent'],
          [bytes(n.held_bytes), 'held'],
          [n.visible_not_selected ?? '—', 'visible, not selected'],
        ]}
      />
      <p className="src-note">
        {count(n.links_to)} links and {count(n.embeds)} embeds, as authored, in what is held. Scope in force:
        include <code>{c.scope.include.join(' ')}</code>, exclude <code>{c.scope.exclude.join(' ') || 'none'}</code>
        {c.scope.revision ? ' (revised)' : ' (as declared)'}.
      </p>
      {c.extraction && c.extraction.sources_with_extractor > 0 && (
        <p className="src-note">
          Extracted text, beside the record: {count(c.extraction.sources_with_extractor)}{' '}
          {c.extraction.sources_with_extractor === 1 ? 'file has' : 'files have'} an extractor ·{' '}
          {Object.entries(c.extraction.by_state)
            .map(([st, k]) => `${count(k)} ${st}`)
            .join(', ')}
          . Made from the held bytes; nothing about it is recorded.
        </p>
      )}
      {c.last_sweep && (
        <Kept
          rows={[
            ['Not acquired', 'selected but not held, with the reason', c.last_sweep.not_acquired.map((x) => `${x.path} — ${x.reason}`)],
            ['Refused', 'links or junctions, not followed; Git metadata, never acquired here', c.last_sweep.refused.map((x) => `${x.path} — ${x.reason}`)],
            ['Not examined', 'folders that could not be listed', c.last_sweep.unexamined.map((x) => `${x.path}/ — ${x.reason}`)],
          ]}
          visible={c.last_sweep.visible_not_selected}
        />
      )}
      <p className="src-faint">{c.binding.bound ? '' : 'Not bound on this machine: everything here stays readable.'}</p>
    </>
  )
}

function Sweeps({ c, nameOf }: { c: CollectionView; nameOf: (id: Id | null | undefined) => string }) {
  const revs = c.revisions
  return (
    <>
      <table className="src-table">
        <thead>
          <tr>
            <th>When</th>
            <th>By</th>
            <th>New</th>
            <th>Changed</th>
            <th>Absent</th>
            <th>Withheld</th>
            <th>Not examined</th>
            <th>Scope</th>
          </tr>
        </thead>
        <tbody>
          {c.sweeps.map((s) => (
            <tr key={s.act}>
              <td>
                {when(s.at)} <span className="src-mono">{shortId(s.act, 12)}</span>
              </td>
              <td>{nameOf(s.actor)}</td>
              <td>{count(s.counts?.new)}</td>
              <td>{count(s.counts?.changed)}</td>
              <td>{count(s.counts?.absent)}</td>
              <td>{count(s.counts?.withheld)}</td>
              <td>{count(s.counts?.not_examined)}</td>
              <td>{s.scope?.revision ? <span className="src-mono">{shortId(s.scope.revision, 12)}</span> : 'as declared'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {revs.length > 0 && (
        <>
          <h2 className="src-h2">Scope revisions</h2>
          <ul className="src-list">
            {revs.map((r) => (
              <li key={r.act}>
                {when(r.at)} by {nameOf(r.revised_by)}: include <code>{r.scope.include.join(' ')}</code>
                {r.scope.exclude.length > 0 && (
                  <>
                    , exclude <code>{r.scope.exclude.join(' ')}</code>
                  </>
                )}{' '}
                (was <code>{r.previous.include.join(' ')}</code>){r.because ? ` — ${r.because}` : ''}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}

/** Plan, preview, confirm: shared by Refresh and Revise scope. */
function usePlanned(col: Id) {
  const [run, setRun] = useState<RunView | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [decisionsDirty, setDecisionsDirty] = useState(false)
  const [refused, setRefused] = useState<string | null>(null)
  const plan = async (
    scope?: { include: string[]; exclude: string[]; options?: ScopeOptions },
    sensitive_decisions?: Record<string, 'include' | 'exclude'>,
    category_decisions?: Record<string, 'include' | 'exclude'>,
  ) => {
    setRefused(null)
    setDecisionsDirty(false)
    setPreview(null)
    try {
      const end = await runToEnd(post<RunView>('/api/sources/plan', { collection: col, scope, sensitive_decisions, category_decisions, ...((preview?.sensitive_columns || preview?.partial_required) && (sensitive_decisions || category_decisions) ? { decision_plan: preview.plan } : {}) }), setRun)
      setRun(null)
      if (end.state === 'done') setPreview(end.result as Preview)
      else setRefused(end.failure ?? end.state)
    } catch (e) {
      setRun(null)
      setRefused((e as Error).message)
    }
  }
  return { run, setRun, preview, setPreview, refused, setRefused, plan, decisionsDirty, setDecisionsDirty }
}

function Refresh({ c, me, onChanged, onOffer }: { c: CollectionView; me: Id | null; onChanged: () => void; onOffer?: (connector: string) => void }) {
  const p = usePlanned(c.collection)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SweepResult | null>(null)
  const confirm = async () => {
    if (!p.preview) return
    setBusy(true)
    try {
      const end = await runToEnd(
        post<RunView>('/api/sources/sweep', {
          collection: c.collection,
          ...p.preview.confirm,
          plan: p.preview.plan,
          acknowledge_binding_change: p.preview.binding_changed,
          by: me,
        }),
        p.setRun,
      )
      p.setRun(null)
      if (end.state === 'done') {
        setResult(end.result as SweepResult)
        setConfirming(false)
        onChanged()
      } else p.setRefused(end.failure ?? end.state)
    } catch (e) {
      p.setRun(null)
      p.setRefused((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  if (result) return <Result r={result} visible={p.preview?.visible_not_selected ?? null} />
  return (
    <>
      <p className="src-note">
        Refresh reads the folder again and previews what a sweep would record against what is already held.
        Nothing is recorded until you confirm.
      </p>
      {!p.preview && !p.run && (
        <button className="btn primary" onClick={() => void p.plan()}>
          Preview a refresh
        </button>
      )}
      {p.run && <RunBar run={p.run} onCancel={() => void cancelRun(p.run!.key)} />}
      {p.refused && !confirming && <p className="act-refused">{p.refused}</p>}
      {p.preview && (
        <>
          <PreviewBody p={p.preview} onOffer={onOffer} onDecisions={(d, cs) => void p.plan(undefined, d, cs)} onDecisionEdit={() => p.setDecisionsDirty(true)} />
          <p className="src-right">
            <button className="btn primary" onClick={() => setConfirming(true)} disabled={p.preview.can_confirm === false || p.decisionsDirty}>
              Record this sweep…
            </button>
          </p>
        </>
      )}
      {confirming && p.preview && (
        <Confirm
          title={`Refresh ${c.name}`}
          verb="Record sweep"
          busy={busy}
          refused={p.refused}
          onCancel={() => setConfirming(false)}
          onConfirm={confirm}
          effect={
            <>
              {p.preview.revising && <>1 <code>source-scope-revised</code> act, exclude <code>{p.preview.scope.exclude.join(' ')}</code> · </>}
              {count(p.preview.counts.new + p.preview.counts.changed + p.preview.counts.reappeared + p.preview.counts.absent)}{' '}
              Admissions recorded ({count(p.preview.counts.new)} new, {count(p.preview.counts.changed)} changed,{' '}
              {count(p.preview.counts.absent)} absent) · 1 <code>source-swept</code> act citing{' '}
              <span className="src-mono">{p.preview.plan}</span>, recorded as yours. If anything changed since the
              preview, nothing is recorded.
              {p.preview.binding_changed && ' This is the first sweep under a new binding, and confirming acknowledges it.'}
            </>
          }
        >
          {p.run && <RunBar run={p.run} />}
        </Confirm>
      )}
    </>
  )
}

function ScopeTab({
  c,
  d,
  me,
  nameOf,
  onChanged,
  onOffer,
}: {
  c: CollectionView
  d: Descriptor
  me: Id | null
  nameOf: (id: Id | null | undefined) => string
  onChanged: () => void
  onOffer?: (connector: string) => void
}) {
  const [editingTables, setEditingTables] = useState(false)
  const tableRules = (c.scope.options?.tables ?? {}) as Record<string, { rows?: unknown[] }>
  const filteredTables = Object.values(tableRules).filter(t => t.rows?.length).length
  const hasOptions = d.scope_fields.some((f) => f.option)
  const [value, setValue] = useState<ScopeValue>({
    preset: presetOf(d, c.scope.include, c.scope.exclude),
    include: c.scope.include,
    exclude: c.scope.exclude,
    options: { ...optionDefaults(d), ...(c.scope.options ?? {}) },
  })
  const [because, setBecause] = useState('')
  const p = usePlanned(c.collection)
  const [confirming, setConfirming] = useState<null | 'revise' | 'unbind'>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<SweepResult | null>(null)
  const [binding, setBinding] = useState<string | null>(null)
  const [choosing, setChoosing] = useState(false)
  const [address, setAddress] = useState('')
  const same =
    value.include.join('\n') === c.scope.include.join('\n') &&
    value.exclude.join('\n') === c.scope.exclude.join('\n') &&
    (!hasOptions || sameOptions(value.options, c.scope.options))

  const revise = async () => {
    if (!p.preview) return
    setBusy(true)
    try {
      const end = await runToEnd(
        post<RunView>('/api/sources/revise-scope', {
          collection: c.collection,
          include: value.include,
          exclude: value.exclude,
          ...(hasOptions ? { options: value.options } : {}),
          ...p.preview.confirm,
          plan: p.preview.plan,
          acknowledge_binding_change: p.preview.binding_changed,
          because: because.trim() || null,
          by: me,
        }),
        p.setRun,
      )
      p.setRun(null)
      if (end.state === 'done') {
        setResult(end.result as SweepResult)
        setConfirming(null)
        onChanged()
      } else p.setRefused(end.failure ?? end.state)
    } catch (e) {
      p.setRun(null)
      p.setRefused((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const unbind = async () => {
    setBusy(true)
    try {
      await post('/api/sources/unbind', { collection: c.collection })
      setConfirming(null)
      onChanged()
    } catch (e) {
      setBinding((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={'src-cols'+(d.binding==='local-file'&&editingTables?' sql-editing':'')}>
      <div>
        <h2 className="src-h2">Scope</h2>
        <p className="src-faint">
          In force since {when(c.scope.at)}
          {c.scope.revised_by ? ` (revised by ${nameOf(c.scope.revised_by)})` : ' (as declared)'}.
        </p>
        {d.binding === 'local-file' ? (editingTables ? <><p><button className="link" onClick={()=>setEditingTables(false)}>Close editor</button></p><SqliteEdit collection={c} descriptor={d} me={me} onChanged={onChanged}/></> : <><p className="src-note">{c.scope.include.length} table selections · {filteredTables} with filters</p><button className="btn primary" disabled={!c.binding.bound} onClick={()=>setEditingTables(true)}>Edit tables and rules</button></>) : result ? (
          <Result r={result} visible={p.preview?.visible_not_selected ?? null} />
        ) : (
          <>
            <ScopeForm
              descriptor={d}
              value={value}
              onChange={(v) => {
                setValue(v)
                p.setPreview(null)
              }}
            />
            {!c.binding.bound && (
              <p className="src-faint">Bind this collection on this machine to preview a revision.</p>
            )}
            {c.binding.bound && !p.preview && (
              <button className="btn primary" disabled={same || !!p.run} onClick={() => void p.plan({ include: value.include, exclude: value.exclude, ...(hasOptions ? { options: value.options } : {}) })}>
                Preview the revised scope
              </button>
            )}
            {p.run && <RunBar run={p.run} onCancel={() => void cancelRun(p.run!.key)} />}
            {p.refused && !confirming && <p className="act-refused">{p.refused}</p>}
            {p.preview && (
              <>
                <PreviewBody p={p.preview} revising onOffer={onOffer} onDecisionEdit={() => p.setDecisionsDirty(true)} onDecisions={(decisions, cs) => void p.plan({ include: value.include, exclude: value.exclude, ...(hasOptions ? { options: value.options } : {}) }, decisions, cs)} />
                <p className="src-right">
                  <button className="btn primary" onClick={() => setConfirming('revise')} disabled={p.preview.can_confirm === false || p.decisionsDirty}>
                    Revise scope…
                  </button>
                </p>
              </>
            )}
          </>
        )}
      </div>
      <div>
        <h2 className="src-h2">This machine</h2>
        {c.binding.bound ? (
          <>
            {c.binding.remote ? (
              <p className="src-note">
                Bound to the address <span className="src-mono">{c.binding.remote}</span> (
                <span className="src-mono">{c.binding.binding}</span>). This machine keeps its own copy, fetched when
                you preview; unbinding removes it.
              </p>
            ) : (
              <p className="src-note">
                Bound to a {d.binding === 'local-file' ? 'file' : 'folder'} <span className="src-mono">{c.binding.binding}</span>. The path is kept on this
                machine only.
              </p>
            )}
            <button className="btn quiet" onClick={() => setConfirming('unbind')}>
              Unbind on this machine
            </button>
            <p className="src-faint">Unbinding changes nothing in the record.</p>
          </>
        ) : (
          <>
            <p className="src-note">Not bound on this machine. Everything acquired stays readable here.</p>
            {d.binding === 'local-file' && <FileBinding collection={c.collection} onChanged={onChanged} />}
            {d.binding === 'local-folder' && (
              <>
                <button className="btn" onClick={() => setChoosing(!choosing)}>
                  Bind to a folder…
                </button>
                <p className="src-faint">
                  Nothing is recorded by binding. The first sweep afterwards previews every difference from what was
                  recorded, and must be acknowledged: a binding certifies nothing about the folder.
                </p>
                {choosing && (
                  <PickSource purpose="folder"
                    onPath={async (root) => {
                      try {
                        await post('/api/sources/bind', { collection: c.collection, root })
                        setChoosing(false)
                        onChanged()
                      } catch (e) {
                        setBinding((e as Error).message)
                      }
                    }}
                  />
                )}
              </>
            )}
            {takesAddress(d) && (
              <AddressField
                value={address}
                onChange={setAddress}
                onSubmit={async () => {
                  setBinding(null)
                  try {
                    await post('/api/sources/bind', { collection: c.collection, remote: address.trim() })
                    setAddress('')
                    onChanged()
                  } catch (e) {
                    setBinding((e as Error).message)
                  }
                }}
              />
            )}
          </>
        )}
        {binding && <p className="act-refused">{binding}</p>}
      </div>
      {confirming === 'revise' && p.preview && (
        <Confirm
          title={`Revise the scope of ${c.name}`}
          verb="Revise and sweep"
          busy={busy}
          refused={p.refused}
          onCancel={() => setConfirming(null)}
          onConfirm={revise}
          effect={
            <>
              1 <code>source-scope-revised</code> act (include <code>{value.include.join(' ')}</code>
              {p.preview.scope.exclude.length ? (
                <>
                  , exclude <code>{p.preview.scope.exclude.join(' ')}</code>
                </>
              ) : null}
              ) and 1 <code>source-swept</code> act, recorded as yours, together: {count(p.preview.counts.new)} new,{' '}
              {count(p.preview.counts.changed)} changed, {count(p.preview.counts.absent)} absent,{' '}
              {count(p.preview.counts.not_examined)} not examined. The collection keeps its identity. If anything
              changed since the preview, neither is recorded.
            </>
          }
        >
          <label className="act-field">
            <span className="act-label">Why (recorded on the revision, optional)</span>
            <textarea rows={2} value={because} onChange={(e) => setBecause(e.target.value)} />
          </label>
          {p.run && <RunBar run={p.run} />}
        </Confirm>
      )}
      {confirming === 'unbind' && (
        <Confirm
          title={`Unbind ${c.name} on this machine`}
          verb="Unbind"
          busy={busy}
          onCancel={() => setConfirming(null)}
          onConfirm={unbind}
          effect={
            <>
              This machine forgets which folder this collection is. Nothing in the record changes: acquired material,
              its history and its held bytes stay exactly as they are. Refreshing needs the folder bound again.
            </>
          }
        />
      )}
    </div>
  )
}

function FileBinding({ collection, onChanged }: { collection: Id; onChanged: () => void }) {
  const [error, setError] = useState<string | null>(null)
  return <div><PickSource purpose="database" onPath={async root => {
    try {
      const end = await runToEnd(post<RunView>('/api/sources/sqlite/inspect', { root }), () => {})
      if (end.state !== 'done') throw new Error(end.failure ?? end.state)
      await post('/api/sources/bind', { collection, root }); onChanged()
    } catch (e) { setError((e as Error).message) }
  }} />{error && <p className="act-refused">{error}</p>}</div>
}
