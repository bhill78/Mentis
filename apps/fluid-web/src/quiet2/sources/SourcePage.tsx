/* ONE SOURCE, IN THE CENTRE READING COLUMN (Manage Sources in Quiet Chat).
 *
 * The Brain record's surface (brainRecord.css: `.rv`, `.rv-grid`, `.rv-d`),
 * so it takes the width it is given exactly as a record does: what the source
 * is, how it stands and what can be done beside its contents where the column
 * is wide, one under the other where it is not.
 *
 * NOTHING IS REBUILT. Every act here is the source system's own, asked for
 * exactly as Fluid's Manage Sources asks (surfaces/sources/Collection.tsx):
 *
 *   Refresh            POST /api/sources/plan, then /sweep with that plan
 *   Change included    POST /plan with the new scope, then /revise-scope
 *   Locate             POST /bind            Stop refreshing    POST /unbind
 *   Cancel             POST /<key>/run/cancel
 *
 * and the parts that carry the system's own rules -- the preview with its
 * decisions (`PreviewBody`), the scope form, the path picker, the SQLite
 * editor, the browser of what is held -- are Fluid's, hosted here.
 *
 * THE EXTERNAL SOURCE AND THE COPY MENTIS HOLDS ARE KEPT APART in every
 * sentence: refreshing takes a new copy, stopping forgets only where the
 * source is on this machine, and what is held is never removed here. */
import { useEffect, useRef, useState } from 'react'
import { useUnfinished, type Standing } from '../leaving'
import { post, shortId, useApi, type Id } from '../../api'
import Browse from '../../surfaces/sources/Browse'
import { usePlanned } from '../../surfaces/sources/Collection'
import { AddressField } from '../../surfaces/sources/FilesystemFlow'
import { Kept, PreviewBody } from '../../surfaces/sources/parts'
import PickSource from '../../surfaces/sources/pick/PickSource'
import ScopeForm, { optionDefaults, presetOf, sameOptions, type ScopeValue } from '../../surfaces/sources/ScopeForm'
import SqliteEdit from '../../surfaces/sources/sqlite/SqliteEdit'
import {
  cancelRun, runToEnd, takesAddress,
  type CollectionView, type Descriptor, type Picker, type Preview, type RunView, type SourcesRoute, type SweepResult,
} from '../../surfaces/sources/route'
import { count, failed, failedWords, failureWords, itemWord, moment, patternWords, previewWords, redact, reviseWords, runWords, running, size, sweepWords } from './words'

type Panel = null | 'refresh' | 'scope' | 'locate' | 'stop'

export default function SourcePage({ col, descriptors, picker, me, nameOf, canWrite, onOpenContent, onChanged, onAddKind }: {
  col: Id
  descriptors: Descriptor[]
  picker?: Picker
  me: Id | null
  nameOf: (id: Id | null | undefined) => string
  /** nothing that writes is offered where the page may not write */
  canWrite: boolean
  /** a held file, a search hit: beside this where there is room, else in place */
  onOpenContent: (r: SourcesRoute) => void
  /** something about the sources changed: whoever lists them reads again */
  onChanged: () => void
  /** the preview's offer of another kind for the same place (a repository found in a folder) */
  onAddKind: (connector: string) => void
}) {
  const view = useApi<CollectionView>(`/api/sources/${encodeURIComponent(col)}`)
  const c = view.data
  const p = usePlanned(col)
  const [panel, setPanel] = useState<Panel>(null)
  const [open, setOpen] = useState<Record<string, boolean>>({ contents: true })
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [wrong, setWrong] = useState<string | null>(null)
  const [because, setBecause] = useState('')
  const [scope, setScope] = useState<ScopeValue | null>(null)
  const [formKey, setFormKey] = useState(0)
  /* the contents are read again after a refresh took something */
  const [taken, setTaken] = useState(0)
  /* WHAT IS UNFINISHED HERE, for somebody leaving for a conversation
     (leaving.ts). Reading a source is never unfinished work; a selection
     being changed, or a preview in hand, is. Set below, once the source has
     been read -- so while it is still being read there is nothing to lose,
     and the hook is never conditional. */
  const standing = useRef<Standing | null>(null)
  standing.current = null
  useUnfinished(() => standing.current)

  const changed = () => { view.reload(); onChanged() }
  /* ONE PREVIEW AT A TIME, from the press until it ends: `p.run` is only
     known once the server answers, so the press itself closes the door.
     A second press cannot start a second plan, and a preview can only
     land under the panel that asked for it. */
  const asking = useRef(false)
  const [waiting, setWaiting] = useState(false)
  const plan: typeof p.plan = async (...args) => {
    if (asking.current) return
    asking.current = true; setWaiting(true); did.current = 'plan'
    try { await p.plan(...args) } finally { asking.current = false; setWaiting(false) }
  }
  /* what this page last asked for, so a failure is called what it was */
  const did = useRef<RunView['kind']>('plan')
  /* A RUN SOMEBODY ELSE STARTED (another tab, an agent's tool) is watched
     while it runs: a run is not in the record, so nothing announces it. One
     this page started is already followed by `runToEnd`. */
  const other = c && !p.run ? running(c) : null
  useEffect(() => {
    if (!other) return
    const t = window.setInterval(() => view.reload(), 1500)
    return () => clearInterval(t)
  }, [!!other]) // eslint-disable-line react-hooks/exhaustive-deps
  /* a run this page followed has ended: what the server keeps of it is read */
  const had = useRef(false)
  useEffect(() => {
    /* it began: whoever lists the sources reads again, and follows it from there */
    if (p.run) { if (!had.current) onChanged(); had.current = true; return }
    if (had.current) { had.current = false; changed() }
  }, [p.run]) // eslint-disable-line react-hooks/exhaustive-deps

  if (view.error && !c) return <div className="rv rv-full"><p className="q2m-faint" role="alert">Could not read this source: {view.error} <button type="button" className="rv-link" onClick={view.reload}>Retry</button></p></div>
  if (!c) return <div className="rv rv-full"><p className="q2m-faint" role="status">Reading the source…</p></div>

  const d = descriptors.find((x) => x.id === c.connector)
  const label = d?.label ?? c.connector
  const file = d?.binding === 'local-file'
  const n = c.counts
  const bound = !!c.binding?.bound
  const live: RunView | null = p.run ?? other
  const hasOptions = !!d?.scope_fields.some((f) => f.option)
  const cancelled = !!p.refused && /^cancelled/i.test(p.refused)
  const bad = !live ? (p.refused && !cancelled ? { text: p.refused, kind: did.current, at: null as number | null } : failed(c) ? { text: failed(c)!.failure, kind: failed(c)!.kind, at: failed(c)!.ended_at } : null) : null
  const why = bad ? failureWords(bad.text) : null

  const toggle = (id: string) => setOpen((o) => ({ ...o, [id]: !o[id] }))
  const close = () => { setPanel(null); p.setPreview(null); p.setRefused(null); setWrong(null) }
  const scopeArg = (v: ScopeValue) => ({ include: v.include, exclude: v.exclude, ...(hasOptions ? { options: v.options } : {}) })

  const refresh = () => { setNote(null); setWrong(null); setPanel('refresh'); void plan() }
  const editScope = () => {
    setNote(null); setWrong(null); p.setPreview(null); p.setRefused(null)
    if (d) setScope({ preset: presetOf(d, c.scope.include, c.scope.exclude), include: c.scope.include, exclude: c.scope.exclude, options: { ...optionDefaults(d), ...(c.scope.options ?? {}) } })
    setBecause(''); setFormKey((k) => k + 1); setPanel('scope'); setOpen((o) => ({ ...o, scope: true }))
  }
  const done = (r: SweepResult, what: string) => {
    const by = r.admitted_by_action ?? {}
    const parts = [
      by.new?.length ? `${count(by.new.length)} new` : '', (by.changed?.length ?? 0) + (by.reappeared?.length ?? 0) ? `${count((by.changed?.length ?? 0) + (by.reappeared?.length ?? 0))} changed` : '',
      r.absent?.length ? `${count(r.absent.length)} gone from the source` : '', r.withheld?.length ? `${count(r.withheld.length)} withheld` : '',
      r.not_examined?.length ? `${count(r.not_examined.length)} not examined` : '',
    ].filter(Boolean)
    setNote(`${what} ${parts.length ? parts.join(', ') + '.' : 'Nothing had changed.'}`)
    setPanel(null); p.setPreview(null); setTaken((t) => t + 1); changed()
  }
  /* the sweep, and the revision with its sweep: Collection.tsx's own requests */
  const act = async (url: string, body: Record<string, unknown>, what: string) => {
    if (!p.preview || asking.current) return
    setBusy(true); p.setRefused(null); did.current = 'sweep'
    try {
      const end = await runToEnd(post<RunView>(url, {
        collection: c.collection, ...body, ...p.preview.confirm, plan: p.preview.plan,
        acknowledge_binding_change: p.preview.binding_changed, by: me,
      }), p.setRun)
      p.setRun(null)
      if (end.state === 'done') done(end.result as SweepResult, what)
      else { p.setPreview(null); p.setRefused(end.failure ?? end.state) }
    } catch (e) { p.setRun(null); p.setPreview(null); p.setRefused((e as Error).message) } finally { setBusy(false) }
  }
  const take = () => act('/api/sources/sweep', {}, 'Refreshed.')
  const revise = () => scope && act('/api/sources/revise-scope', { ...scopeArg(scope), because: because.trim() || null }, 'What is included was changed, and the source refreshed.')
  const bind = async (body: Record<string, unknown>) => {
    setWrong(null)
    try { await post('/api/sources/bind', { collection: c.collection, ...body }); setPanel(null); setNote('Connected on this machine. Preview a refresh to see what has changed since Mentis last took a copy.'); changed() }
    catch (e) { setWrong((e as Error).message) }
  }
  const unbind = async () => {
    setBusy(true); setWrong(null)
    try { await post('/api/sources/unbind', { collection: c.collection }); setPanel(null); setNote('This machine no longer refreshes this source. Everything Mentis holds from it is unchanged.'); changed() }
    catch (e) { setWrong((e as Error).message) } finally { setBusy(false) }
  }

  const sameScope = !!scope && scope.include.join('\n') === c.scope.include.join('\n') && scope.exclude.join('\n') === c.scope.exclude.join('\n') && (!hasOptions || sameOptions(scope.options, c.scope.options))
  /* A REFRESH OR A PREVIEW RUNNING HERE IS THE SERVER'S, not this page's:
     it carries on whether or not the reader stays, and leaving never
     cancels it. So it is said, and it never holds anybody here. */
  standing.current = {
    what: c.name,
    dirty: panel === 'scope' && !sameScope,
    preview: !!p.preview,
    run: live ? { what: `${live.kind === 'sweep' ? 'Refreshing' : 'Looking at'} ${c.name}`, interrupted: false } : null,
  }
  const needs = (pv: Preview) => pv.can_confirm === false || p.decisionsDirty
  const moved = (pv: Preview) => (pv.counts.new ?? 0) + (pv.counts.changed ?? 0) + (pv.counts.reappeared ?? 0) + (pv.counts.absent ?? 0) > 0

  /* what a preview says, shared by Refresh and Change what is included */
  const previewBlock = (pv: Preview, verb: string, go: () => void, revising: boolean) => (
    <div className="q2-src-panel" role="region" aria-label="Preview">
      <h3>Preview · nothing has been taken</h3>
      <p className="q2-src-lead">{revising ? reviseWords(pv.counts) : previewWords(pv.counts)}{pv.bytes_new_to_store ? ` About ${size(pv.bytes_new_to_store)} to take.` : ''}</p>
      {pv.binding_changed && <p className="q2-src-warn">This is the first refresh since the source was located here again. Taking it accepts that this place is the same source.</p>}
      {needs(pv) && <p className="q2-src-warn">Some of what was found needs your decision before anything can be taken. Answer below, then preview those decisions.</p>}
      <div className="q2-src-acts">
        {(moved(pv) || revising || pv.binding_changed) && <button type="button" className="q2-src-btn go" disabled={busy || waiting || needs(pv)} onClick={go}>{busy ? 'Taking…' : !moved(pv) && !revising ? 'Accept this place' : verb}</button>}
        <button type="button" className="q2-src-btn" disabled={busy || waiting} onClick={() => void plan(revising && scope ? scopeArg(scope) : undefined)}>Preview again</button>
        <button type="button" className="q2-src-btn quiet" disabled={busy} onClick={close}>{moved(pv) || revising || pv.binding_changed ? 'Not now' : 'Close'}</button>
      </div>
      <details className="q2-src-all" open={needs(pv) || undefined}>
        <summary>Everything the preview found</summary>
        <div className="q2-src-host">
          <PreviewBody p={pv} revising={revising} onOffer={onAddKind} onDecisionEdit={() => p.setDecisionsDirty(true)}
            onDecisions={(dec, cats) => void plan(revising && scope ? scopeArg(scope) : undefined, dec, cats)} />
        </div>
      </details>
      <p className="q2-src-faint">If the source changes before you take this, nothing is recorded and you preview again.</p>
    </div>
  )

  const included = c.scope.options?.tables && typeof c.scope.options.tables === 'object'
    ? `${c.scope.include.length} table ${c.scope.include.length === 1 ? 'selection' : 'selections'}`
    : patternWords(c.scope.include)
  const leftOut = c.scope.exclude.filter(Boolean).length
  const sweep = c.last_sweep
  const kept = sweep ? [
    ['Withheld', 'selected but not taken, with the reason', sweep.not_acquired.map((x) => `${x.path} — ${x.reason}`)],
    ['Refused', 'links or junctions, not followed; Git metadata, never taken', sweep.refused.map((x) => `${x.path} — ${x.reason}`)],
    ['Not examined', 'folders that could not be listed', sweep.unexamined.map((x) => `${x.path}/ — ${x.reason}`)],
  ] as [string, string, string[]][] : []
  const keptN = kept.reduce((a, r) => a + r[2].length, 0)
  const facts = [
    `${count(n.present)} ${itemWord(c.connector, n.present)}`, `${size(n.held_bytes)} held`,
    n.links_to + n.embeds ? `${count(n.links_to + n.embeds)} ${n.links_to + n.embeds === 1 ? 'link' : 'links'} between them` : '',
    n.visible_not_selected ? `${count(n.visible_not_selected)} seen, not included` : '',
    n.absent ? `${count(n.absent)} gone from the source` : '',
  ].filter(Boolean)
  const fold = (id: string, title: string, sub: string, body: () => React.ReactNode) => (
    <div className={'rv-d' + (open[id] ? ' open' : '')}>
      <button type="button" aria-expanded={!!open[id]} onClick={() => toggle(id)}><span className="c">{open[id] ? '▾' : '▸'}</span>{title}<span className="s">{sub}</span></button>
      {open[id] && <div className="rv-body">{body()}</div>}
    </div>
  )

  return (
    <div className="rv rv-full q2-src-page" data-source={c.collection}>
      <div className="rv-grid">
        <div className="rv-main">
          <div className="rv-top"><p className="rv-kind">{label}{c.binding?.remote ? ' · remote' : ''}</p></div>
          <h1 className="q2-src-name">{c.name}</h1>
          <p className="q2-src-what">
            {sweep
              ? <>Mentis holds a copy of {facts[0]}, taken {moment(sweep.at)}. Agents read that copy, never the source itself.</>
              : <>Declared {moment(c.declared_at)} by {nameOf(c.declared_by)}. Nothing has been taken from it yet.</>}
          </p>

          {live && (
            <div className="q2-src-progress" role="group" aria-label={runWords(live)}>
              <p><b>{runWords(live)}</b> · {count(live.progress.files)} {live.progress.files === 1 ? 'file' : 'files'}, {size(live.progress.bytes)} so far{live.kind === 'sweep' ? '' : ' · nothing is being taken'}</p>
              {live.progress.current && <p className="cur">{live.progress.current}</p>}
              <div className="q2-src-bar"><i /></div>
              <div className="q2-src-acts">
                {canWrite && <button type="button" className="q2-src-btn" disabled={live.cancel_requested} onClick={() => void cancelRun(live.key).then(() => view.reload(), () => {})}>{live.cancel_requested ? 'Stopping…' : live.kind === 'sweep' ? 'Cancel this refresh' : 'Cancel'}</button>}
                <span className="q2-src-faint">No total is known. Cancel works until the record is written.</span>
              </div>
            </div>
          )}

          {bad && why && (
            <div className="q2-src-alert" role="alert">
              <h3>{failedWords(bad)}{why.title ? `: ${why.title}` : ''}</h3>
              <p><code>{why.said}</code></p>
              {why.advice && <p>{why.advice}</p>}
              <p className="q2-src-faint">{bad.at ? `${moment(bad.at)}. ` : ''}Nothing was taken. What Mentis already holds is unchanged{bad.at ? '. This is kept only while Mentis keeps running' : ''}.</p>
            </div>
          )}

          {!live && (
            <p className="rv-state">
              <span className={'dot' + (bad ? ' ask' : !bound ? ' q2-src-hollow' : '')} />
              <span>
                <span className="q2e-status">{bad ? 'Held · not refreshed' : bound ? 'Connected here' : sweep ? 'Not connected on this machine' : 'Declared'}</span>
                {bound ? 'Refreshed only when you ask.'
                  : sweep ? 'Still held and readable. Locate it on this machine to refresh it.'
                    : 'Locate it on this machine, then preview what would be taken.'}
              </span>
            </p>
          )}
          {cancelled && !live && <p className="q2-src-note">Cancelled. Nothing was taken, and what Mentis held before is unchanged.</p>}
          {note && <p className="q2-src-note" role="status">{note}</p>}

          {canWrite && !live && (
            <div className="q2-src-acts q2-src-primary">
              {bound ? (
                <>
                  <button type="button" className="q2-src-btn go" disabled={waiting} onClick={refresh} title="Looks at the source and shows what would change, before anything is taken">{bad ? 'Try again' : sweep ? 'Refresh…' : 'Preview what would be taken…'}</button>
                  <button type="button" className="q2-src-btn" disabled={waiting} onClick={editScope}>Change what is included…</button>
                  <button type="button" className="q2-src-btn quiet" onClick={() => { p.setPreview(null); setWrong(null); setPanel('stop') }}>Stop refreshing here</button>
                </>
              ) : <button type="button" className="q2-src-btn go" onClick={() => { setWrong(null); setPanel('locate') }}>Locate it on this machine…</button>}
            </div>
          )}

          {panel === 'refresh' && p.preview && !live && previewBlock(p.preview, sweep ? 'Take these changes' : `Take ${count(p.preview.counts.new)} ${itemWord(c.connector, p.preview.counts.new)}`, () => void take(), false)}

          {panel === 'scope' && d && !live && (
            file ? (
              <div className="q2-src-panel">
                <h3>Change what is included</h3>
                {bound ? <div className="q2-src-host"><SqliteEdit collection={c} descriptor={d} me={me} onChanged={() => { setTaken((t) => t + 1); changed() }} /></div>
                  : <p className="q2-src-faint">Locate the database on this machine first: its tables are read from the file.</p>}
                <div className="q2-src-acts"><button type="button" className="q2-src-btn quiet" onClick={close}>Close</button></div>
              </div>
            ) : p.preview ? (
              <>
                {previewBlock(p.preview, 'Save and take', () => void revise(), true)}
                <label className="q2-src-field q2-src-because"><span>Why (kept with the change, optional)</span><textarea rows={2} value={because} onChange={(e) => setBecause(e.target.value)} /></label>
              </>
            ) : scope && (
              <div className="q2-src-panel">
                <h3>Change what is included</h3>
                <div className="q2-src-host"><ScopeForm key={formKey} descriptor={d} value={scope} onChange={(v) => { setScope(v); p.setPreview(null) }} /></div>
                <div className="q2-src-acts">
                  <button type="button" className="q2-src-btn go" disabled={sameScope || waiting} onClick={() => void plan(scopeArg(scope))}>Preview this change</button>
                  <button type="button" className="q2-src-btn quiet" onClick={close}>Cancel</button>
                </div>
                <p className="q2-src-faint">Nothing changes until you take the preview. What leaves the selection stays held.</p>
              </div>
            )
          )}

          {panel === 'locate' && d && (
            <div className="q2-src-panel">
              <h3>Where is {c.name} on this machine?</h3>
              <div className="q2-src-host">
                {file && <PickSource purpose="database" picker={picker} onPath={async (root) => {
                  const end = await runToEnd(post<RunView>('/api/sources/sqlite/inspect', { root }), () => {})
                  if (end.state !== 'done') throw new Error(end.failure ?? end.state)
                  await bind({ root })
                }} />}
                {d.binding === 'local-folder' && <PickSource purpose="folder" picker={picker} onPath={(root) => bind({ root })} />}
                {takesAddress(d) && <LocateAddress onBind={(remote) => bind({ remote })} />}
              </div>
              <p className="q2-src-faint">Read-only. Locating records nothing; the next refresh shows every difference.</p>
              <div className="q2-src-acts"><button type="button" className="q2-src-btn quiet" onClick={close}>Cancel</button></div>
            </div>
          )}

          {panel === 'stop' && (
            <div className="q2-src-panel">
              <h3>Stop refreshing {c.name} from this machine?</h3>
              <p className="q2-src-lead">This machine forgets where the source is. Everything Mentis holds from it stays, and agents can still read it. You can locate it again later.</p>
              <div className="q2-src-acts">
                <button type="button" className="q2-src-btn go" disabled={busy} onClick={() => void unbind()}>{busy ? 'Working…' : 'Stop refreshing here'}</button>
                <button type="button" className="q2-src-btn quiet" disabled={busy} onClick={close}>Keep it connected</button>
              </div>
            </div>
          )}
          {wrong && <p className="q2-src-alert q2-src-alert-line" role="alert">{redact(wrong)}</p>}

          {sweep && <p className="q2-src-facts">{[...facts.slice(1), `last refresh by ${nameOf(sweep.actor)}: ${sweepWords(sweep.counts)}`].join(' · ')}</p>}
        </div>

        <div className="rv-more">
          {fold('contents', 'Contents', sweep ? `${count(n.present)} ${itemWord(c.connector, n.present)}` : 'nothing yet', () => (
            sweep ? (
              <div className="q2-src-host q2-src-browse">
                <Browse key={taken} col={c.collection} browse={d?.browse ?? 'hierarchy'}
                  onOpen={(key) => onOpenContent({ at: 'object', col: c.collection, key })}
                  onHit={(ref, span, extraction) => onOpenContent({ at: 'observation', ref, span, extraction })} />
              </div>
            ) : <p>Nothing has been taken from this source yet.</p>
          ))}
          {fold('scope', 'What is included', leftOut ? `${included === 'everything' ? 'everything' : 'a selection'}, except ${leftOut} ${leftOut === 1 ? 'pattern' : 'patterns'}` : included === 'everything' ? 'everything' : 'a selection', () => (
            <>
              <dl className="q2-src-kv">
                <dt>Includes</dt><dd>{included === 'everything' || !c.scope.include.length ? included : c.scope.include.map((x) => <code key={x}>{x}</code>)}</dd>
                <dt>Leaves out</dt><dd>{leftOut ? c.scope.exclude.filter(Boolean).map((x) => <code key={x}>{x}</code>) : 'nothing'}</dd>
                {Object.entries(c.scope.options ?? {}).filter(([, v]) => typeof v !== 'object').map(([k, v]) => (
                  <div key={k} className="q2-src-kvrow"><dt>{d?.scope_fields.find((f) => f.name === k)?.label ?? k}</dt><dd>{String(v)}</dd></div>
                ))}
                <dt>In force since</dt><dd>{moment(c.scope.at)}{c.scope.revised_by ? `, changed by ${nameOf(c.scope.revised_by)}` : ', as declared'}{c.revisions.length ? ` · ${c.revisions.length} ${c.revisions.length === 1 ? 'change' : 'changes'}` : ''}</dd>
              </dl>
              {canWrite && bound && !live && <p className="q2-src-faint"><button type="button" className="rv-link" onClick={editScope}>Change what is included…</button></p>}
            </>
          ))}
          {fold('history', 'Refresh history', `${c.sweeps.length} ${c.sweeps.length === 1 ? 'refresh' : 'refreshes'}`, () => (
            c.sweeps.length ? (
              <>
                <ul className="q2-src-list">
                  {c.sweeps.map((s) => <li key={s.act}><span className="w">{moment(s.at)}</span><span>{nameOf(s.actor)} · {sweepWords(s.counts)}{s.binding_changed ? ' · located again' : ''}</span></li>)}
                </ul>
                {c.revisions.length > 0 && (
                  <ul className="q2-src-list">
                    {c.revisions.map((r) => <li key={r.act}><span className="w">{moment(r.at)}</span><span>{nameOf(r.revised_by)} changed what is included{r.because ? `: ${r.because}` : ''}</span></li>)}
                  </ul>
                )}
                <p className="q2-src-faint">Only refreshes that completed are kept. Failed and cancelled ones are not recorded.</p>
              </>
            ) : <p>It has not been refreshed yet.</p>
          ))}
          {sweep && keptN > 0 && fold('kept', 'Withheld and not examined', `${count(keptN)} at the last refresh`, () => (
            <div className="q2-src-host"><Kept rows={kept} visible={sweep.visible_not_selected} /></div>
          ))}
          {c.extraction && c.extraction.sources_with_extractor > 0 && fold('text', 'Text read from files', `${count(c.extraction.sources_with_extractor)} ${c.extraction.sources_with_extractor === 1 ? 'file' : 'files'}`, () => (
            <>
              <ul className="q2-src-list">{Object.entries(c.extraction!.by_state).map(([st, k]) => <li key={st}><span>{st}</span><span className="n">{count(k)}</span></li>)}</ul>
              <p className="q2-src-faint">Text is read from files that are not plain text (PDF today), from the copy Mentis holds. A scanned page has no text to read.</p>
            </>
          ))}
          {fold('where', 'Where it is on this machine', bound ? 'connected' : 'not connected', () => (
            <>
              {bound
                ? <p>{c.binding.remote ? <>Connected by the address <code>{redact(c.binding.remote)}</code>. This machine keeps its own copy of the repository, fetched when you preview.</> : <>Connected to a {file ? 'file' : 'folder'} on this machine{c.binding.binding ? <> (<code>{shortId(c.binding.binding, 16)}</code>)</> : null}.</>}</p>
                : <p>Not connected on this machine. Everything taken stays readable here.</p>}
              <p className="q2-src-faint">Mentis remembers where a source is on this machine only, apart from the Brain. Another machine with the same Brain sees it as not connected until it is located there.</p>
              {canWrite && !live && <p className="q2-src-faint"><button type="button" className="rv-link" onClick={() => { setWrong(null); setPanel('locate') }}>{bound ? 'Locate it somewhere else…' : 'Locate it on this machine…'}</button></p>}
            </>
          ))}
          {fold('who', 'Who can read it', 'every agent', () => (
            <p>What Mentis holds from a source can be read and searched by every agent, in every conversation. There is no per-source restriction, and stopping refresh does not change that.</p>
          ))}
        </div>
      </div>
    </div>
  )
}

function LocateAddress({ onBind }: { onBind: (remote: string) => void }) {
  const [address, setAddress] = useState('')
  return <AddressField value={address} onChange={setAddress} onSubmit={() => { if (address.trim()) onBind(address.trim()) }} />
}
