/* ADD A SOURCE, IN THE CENTRE READING COLUMN (Manage Sources in Quiet Chat).
 *
 *   Kind  ›  Where and what  ›  Preview  ›  Take
 *
 * THE KINDS COME FROM THE SOURCE SYSTEM (`descriptors` of `/api/sources`),
 * never from a list kept here: a connector that becomes available appears,
 * and one that is only described stays out of the way, folded under "Not
 * available yet". While the available kinds are few they are cards; past
 * `SEARCH_FROM` of them a search line narrows the cards by name and by what
 * they say of themselves, so more connectors need no redesign.
 *
 * THE FLOW IS THE SOURCE SYSTEM'S OWN, asked for exactly as Fluid's Manage
 * Sources asks (surfaces/sources/FilesystemFlow.tsx): a preview is a DRAFT
 * (`POST /api/sources/plan {draft}`) that declares and records nothing;
 * taking it (`POST /api/sources/sweep {draft, plan}`) declares the source,
 * connects it on this machine and takes it as one act, refused whole if the
 * source changed since the preview. Changing anything after a preview drops
 * that preview. A database file has its own flow (tables, columns, rules,
 * suspected secrets): Fluid's `SqliteFlow`, hosted here unchanged.
 *
 * NO PASSWORD IS ASKED FOR OR KEPT. A remote repository is reached with this
 * machine's own Git sign-in; an address that carries one is refused by the
 * server. */
import { useEffect, useRef, useState } from 'react'
import { post, type Id } from '../../api'
import { useUnfinished } from '../leaving'
import { adding } from './holding'
import { AddressField } from '../../surfaces/sources/FilesystemFlow'
import { PreviewBody } from '../../surfaces/sources/parts'
import PickSource from '../../surfaces/sources/pick/PickSource'
import { baseName } from '../../surfaces/sources/pick/recent'
import ScopeForm, { optionDefaults, presetValue, type ScopeValue } from '../../surfaces/sources/ScopeForm'
import SqliteFlow, { type SqliteHeld } from '../../surfaces/sources/sqlite/SqliteFlow'
import {
  cancelRun, runToEnd, takesAddress,
  type Choices, type Descriptor, type Picker, type Preview, type RunView, type SweepResult,
} from '../../surfaces/sources/route'
import { SEARCH_FROM, count, failureWords, itemWord, kindsShown, size } from './words'

const STEPS = ['Kind', 'Where and what', 'Preview', 'Take']

export default function AddSourcePage({ descriptors, picker, me, connector, onConnector, onOpenSource, onChanged, onCancel }: {
  descriptors: Descriptor[]
  picker?: Picker
  me: Id | null
  connector: string | null
  onConnector: (connector: string | null) => void
  onOpenSource: (col: Id) => void
  onChanged: () => void
  onCancel: () => void
}) {
  const [q, setQ] = useState('')
  /* a preview is in hand: the kind is not changed under it by a stray press */
  const [locked, setLocked] = useState(false)
  const [step, setStep] = useState(1)
  const available = descriptors.filter((d) => d.available)
  const later = descriptors.filter((d) => !d.available)
  const shown = kindsShown(descriptors, q)
  const d = available.find((x) => x.id === connector) ?? null
  const at = !d ? 0 : step
  /* A DATABASE FILE'S FLOW keeps its own state (SqliteFlow, shared with
     Fluid's Manage Sources), so it SAYS what it is holding rather than
     having it guessed from the step it is on: a name typed on the first
     step is already something a reader would not want to lose. A folder or
     a repository says the same four things, below. */
  const sqlite = useRef<SqliteHeld | null>(null)
  useUnfinished(() => (d && d.binding === 'local-file' && sqlite.current ? adding(sqlite.current) : null))
  return (
    <div className="rv rv-full q2-src-page q2-src-addpage">
      <div className="rv-top"><p className="rv-kind">New source</p></div>
      <h1 className="q2-src-name">Add a source</h1>
      {/* a database file's flow draws its own steps (it can go back through them) */}
      {!(d && d.binding === 'local-file') && <ol className="q2-src-steps" aria-label="Steps">{STEPS.map((s, i) => <li key={s} className={i === at ? 'on' : i < at ? 'done' : ''} aria-current={i === at ? 'step' : undefined}>{s}</li>)}</ol>}

      <p className="q2-src-h">Kind</p>
      {available.length >= SEARCH_FROM && (
        <input type="search" className="q2-src-kindfind" value={q} placeholder="Find a kind of source" aria-label="Find a kind of source"
          autoComplete="off" spellCheck={false} onChange={(e) => setQ(e.target.value)} />
      )}
      <div className="q2-src-kinds" role="radiogroup" aria-label="Kind of source">
        {shown.map((k) => (
          <button key={k.id} type="button" role="radio" aria-checked={connector === k.id} disabled={locked && connector !== k.id}
            className={'q2-src-kindcard' + (connector === k.id ? ' on' : '')}
            onClick={() => { if (connector !== k.id) { setStep(1); setLocked(false); onConnector(k.id) } }}>
            <b>{k.label}</b>{k.summary && <span>{k.summary}</span>}
          </button>
        ))}
        {!shown.length && <p className="q2-src-faint">No kind matches.</p>}
      </div>
      {later.length > 0 && (
        <details className="q2-src-later">
          <summary>Not available yet ({later.length})</summary>
          <p>{later.map((k) => k.label).join(', ')}</p>
          {[...new Set(later.map((k) => k.why_not).filter(Boolean))].map((w) => <p key={w}>{w}</p>)}
        </details>
      )}

      {!d && <div className="q2-src-acts"><button type="button" className="q2-src-btn quiet" onClick={onCancel}>Cancel</button></div>}
      {d && d.binding === 'local-file' && (
        <div className="q2-src-host q2-src-sqlite">
          <SqliteFlow key={d.id} descriptor={d} picker={picker} me={me} onChanged={onChanged} onStep={(s) => { setStep(Math.min(3, s)); setLocked(s > 1) }}
            onHolding={(h) => { sqlite.current = h }}
            go={(r) => { if (r.at === 'collection') onOpenSource(r.col); else if (r.at === 'flow') { setStep(1); setLocked(false); onConnector(r.connector) } }} />
        </div>
      )}
      {d && d.binding !== 'local-file' && (
        <FolderFlow key={d.id} descriptor={d} picker={picker} me={me} onStep={setStep} onLock={setLocked}
          onChanged={onChanged} onOpenSource={onOpenSource} onCancel={onCancel}
          onOffer={(id) => { setStep(1); setLocked(false); onConnector(id) }} />
      )}
    </div>
  )
}

/** A folder on this machine, or a repository there or at an address: any
 *  kind whose place is a folder or an address. It names the kind and never
 *  branches on which one it is (its fields come from its descriptor). */
function FolderFlow({ descriptor, picker, me, onStep, onLock, onChanged, onOpenSource, onOffer, onCancel }: {
  descriptor: Descriptor
  picker?: Picker
  me: Id | null
  onStep: (n: number) => void
  onLock: (locked: boolean) => void
  onChanged: () => void
  onOpenSource: (col: Id) => void
  onOffer: (connector: string) => void
  onCancel: () => void
}) {
  const first = descriptor.presets.find((x) => x.id === 'notes') ?? descriptor.presets[0]
  const byAddress = takesAddress(descriptor)
  const [name, setName] = useState('')
  const [nameEdited, setNameEdited] = useState(false)
  const [root, setRoot] = useState<string | null>(null)
  const [via, setVia] = useState<string | undefined>()
  const [choosing, setChoosing] = useState(true)
  const [address, setAddress] = useState('')
  const [scope, setScope] = useState<ScopeValue>(presetValue(first, optionDefaults(descriptor)))
  const [run, setRun] = useState<RunView | null>(null)
  const [preview, setPreviewNow] = useState<Preview | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [refused, setRefused] = useState<string | null>(null)
  const [result, setResult] = useState<SweepResult | null>(null)
  /* Preview was pressed with something missing: said at the input it is missing from */
  const [tried, setTried] = useState(false)
  const hasOptions = descriptor.scope_fields.some((f) => f.option)
  const remote = byAddress && !root && address.trim() ? address.trim() : null
  const where = root ?? remote
  /* SOMETHING WAS FILLED IN HERE AND NOTHING HAS RECORDED IT. Once the
     source has been taken (`result`) there is nothing unfinished left.
     A PATH TYPED INTO THE PICKER AND NOT YET USED counts: it never reaches
     `edited()`, because nothing has been chosen with it yet, and leaving
     used to take it with no word said. */
  const [touched, setTouched] = useState(false)
  const [typedPath, setTypedPath] = useState('')
  useUnfinished(() => adding({
    typed: touched || !!typedPath.trim(),
    preview: !!preview,
    run: run?.kind ?? null,
    done: !!result,
  }))
  /* STILL ON THE PAGE. A run that ends after the reader has gone never pulls
     them back out of the conversation they chose: the run is not cancelled
     and what it did stands (the source IS added), but the screen it would
     have changed is not theirs any more.
     IT IS SET ON THE WAY IN AS WELL AS THE WAY OUT: a remount (StrictMode in
     development, and anything that remounts this page) runs the cleanup and
     then the effect again, and a flag only ever cleared would stay cleared. */
  const here = useRef(true)
  useEffect(() => { here.current = true; return () => { here.current = false } }, [])

  /* ANYTHING CHANGED AFTER A PREVIEW DROPS IT: what would be taken is only
     ever what the server said of exactly this configuration */
  const setPreview = (pv: Preview | null) => { setPreviewNow(pv); onLock(!!pv); onStep(pv ? 3 : 1) }
  /* every edit moves this on: a preview still on its way when something
     changed is of the old configuration, and is dropped when it lands */
  const version = useRef(0)
  const edited = () => { version.current += 1; setTouched(true); if (preview) setPreview(null); setRefused(null) }

  const doPreview = async (decisions?: Record<string, 'include' | 'exclude'>, categories?: Choices) => {
    if (!where || !name.trim()) { setTried(true); return }
    setTried(false); setRefused(null); setDirty(false); setPreview(null); onStep(2)
    const mine = version.current
    try {
      const end = await runToEnd(post<RunView>('/api/sources/plan', {
        draft: {
          connector: descriptor.id, name: name.trim(), ...(remote ? { remote } : { root }),
          include: scope.include, exclude: scope.exclude, sensitive_decisions: decisions, category_decisions: categories,
          ...(hasOptions ? { options: scope.options } : {}),
        },
      }), setRun)
      if (!here.current) return
      setRun(null)
      if (mine !== version.current) { onStep(1); return }
      if (end.state === 'done') setPreview(end.result as Preview)
      else { setRefused(end.failure ?? end.state); onStep(1) }
    } catch (e) { if (!here.current) return; setRun(null); setRefused((e as Error).message); onStep(1) }
  }
  const take = async () => {
    if (!preview?.draft) return
    setBusy(true); setRefused(null)
    try {
      const end = await runToEnd(post<RunView>('/api/sources/sweep', { draft: preview.draft, plan: preview.plan, by: me }), setRun)
      /* THE SOURCE WAS TAKEN WHETHER OR NOT THE READER STAYED, so whoever
         lists the sources is told either way; only the page they left is
         not reopened over the conversation they went to. */
      if (end.state === 'done') onChanged()
      if (!here.current) return
      setRun(null)
      if (end.state === 'done') {
        const r = end.result as SweepResult
        setResult(r); onLock(false)
        if (r.collection) onOpenSource(r.collection)
      } else { setPreview(null); setRefused(end.failure ?? end.state) }
    } catch (e) { if (!here.current) return; setRun(null); setPreview(null); setRefused((e as Error).message) } finally { if (here.current) setBusy(false) }
  }

  const why = refused && !/^cancelled/i.test(refused) ? failureWords(refused) : null
  const needs = !!preview && (preview.can_confirm === false || dirty)
  return (
    <div className="rv-grid q2-src-addgrid">
      <div className="rv-main">
        <p className="q2-src-h">Where and what</p>
        <label className={'q2-src-field q2-src-short' + (tried && !name.trim() ? ' q2-src-wrong' : '')}><span>Name</span>
          <input type="text" value={name} placeholder="Filled in from the place you choose" disabled={busy || !!result}
            aria-invalid={tried && !name.trim() || undefined}
            onChange={(e) => { setNameEdited(true); setName(e.target.value); edited() }} />
          {tried && !name.trim() && <p className="q2-src-bad" role="alert">Give it a name.</p>}
        </label>
        <div className="q2-src-field"><span>Where it is, on this machine</span>
          {root && (
            <p className="q2-src-chosen"><b>{baseName(root)}</b><code>{root}</code>
              {via && <span className="q2-src-faint">The folder that contains {via}.</span>}
              {!busy && !result && <button type="button" className="rv-link" onClick={() => setChoosing((x) => !x)}>{choosing ? 'Keep this' : 'Change…'}</button>}
            </p>
          )}
          {choosing && !result && (
            <div className="q2-src-host">
              <PickSource purpose="folder" picker={picker} onTyping={setTypedPath} onPath={(path, file) => {
                setRoot(path); setVia(file); setAddress(''); setChoosing(false); edited()
                if (!nameEdited) setName(baseName(path))
              }} />
            </div>
          )}
          {!root && <p className="q2-src-faint">Read-only: Mentis never changes anything in the source.</p>}
        </div>
        {byAddress && !result && (
          <div className="q2-src-host q2-src-address">
            <AddressField value={address} disabled={busy} onChange={(v) => { setAddress(v); if (v.trim()) { setRoot(null); setChoosing(true) } edited() }} />
          </div>
        )}
        {tried && !where && <p className="q2-src-bad" role="alert">{byAddress ? 'Choose where it is, or give its address.' : 'Choose where it is.'}</p>}
        {why && (
          <div className="q2-src-alert" role="alert">
            <h3>{why.title ? `It could not be read: ${why.title}` : 'It could not be read'}</h3>
            <p><code>{why.said}</code></p>
            {why.advice && <p>{why.advice}</p>}
            <p className="q2-src-faint">Nothing was declared or taken.</p>
          </div>
        )}
        {where && !result && (
          <div className="q2-src-field"><span>What to include</span>
            <div className="q2-src-host"><ScopeForm descriptor={descriptor} value={scope} onChange={(v) => { setScope(v); edited() }} /></div>
          </div>
        )}
        {!result && (
          <div className="q2-src-acts">
            <button type="button" className="q2-src-btn go" disabled={!!run || busy} onClick={() => void doPreview()}>{preview ? 'Preview again' : 'Preview'}</button>
            <button type="button" className="q2-src-btn quiet" disabled={busy} onClick={onCancel}>Cancel</button>
          </div>
        )}
      </div>

      <div className="rv-more q2-src-addside">
        {run && (
          <div className="q2-src-progress" role="group" aria-label="In progress">
            <p><b>{run.kind === 'sweep' ? 'Taking it now' : 'Looking at the source'}</b> · {count(run.progress.files)} {run.progress.files === 1 ? 'file' : 'files'}, {size(run.progress.bytes)} so far</p>
            {run.progress.current && <p className="cur">{run.progress.current}</p>}
            <div className="q2-src-bar"><i /></div>
            <div className="q2-src-acts"><button type="button" className="q2-src-btn" disabled={run.cancel_requested} onClick={() => void cancelRun(run.key).catch(() => {})}>{run.cancel_requested ? 'Stopping…' : 'Cancel'}</button></div>
          </div>
        )}
        {refused && !why && <p className="q2-src-note">Cancelled. Nothing was declared or taken.</p>}
        {!run && !preview && !result && (
          <div className="q2-src-panel q2-src-wait">
            <h3>Preview</h3>
            <p className="q2-src-faint">Shows exactly what would be taken, left out or withheld, before anything enters the Brain. It takes nothing.</p>
          </div>
        )}
        {preview && !run && !result && (
          <div className="q2-src-panel" role="region" aria-label="Preview">
            <h3>Preview · nothing has been taken</h3>
            <p className="q2-src-lead">{count(preview.counts.new)} {itemWord(descriptor.id, preview.counts.new)} would be taken, about {size(preview.bytes_new_to_store)}.
              {preview.counts.not_acquired ? ` ${count(preview.counts.not_acquired)} withheld.` : ''}{preview.visible_not_selected ? ` ${count(preview.visible_not_selected)} seen and not included.` : ''}</p>
            {needs && <p className="q2-src-warn">Some of what was found needs your decision before anything can be taken. Answer below, then preview those decisions.</p>}
            <div className="q2-src-acts">
              <button type="button" className="q2-src-btn go" disabled={busy || needs || preview.admit.length === 0} onClick={() => void take()}>{busy ? 'Taking…' : `Take ${count(preview.counts.new)} ${itemWord(descriptor.id, preview.counts.new)}`}</button>
              <button type="button" className="q2-src-btn quiet" disabled={busy} onClick={() => setPreview(null)}>Back to the settings</button>
            </div>
            <p className="q2-src-faint">Taking it adds <b>{name.trim()}</b>, connects it on this machine and copies these into the Brain. If the source changes first, nothing is recorded and you preview again.</p>
            <details className="q2-src-all" open={needs || undefined}>
              <summary>Everything the preview found</summary>
              <div className="q2-src-host"><PreviewBody p={preview} onDecisions={(dec, cs) => void doPreview(dec, cs)} onDecisionEdit={() => setDirty(true)} onOffer={onOffer} /></div>
            </details>
          </div>
        )}
        {result && (
          <div className="q2-src-panel">
            <h3>{name.trim()} was added</h3>
            <p className="q2-src-lead">{count(result.admitted?.length)} {itemWord(descriptor.id, result.admitted?.length ?? 0)} were taken into the Brain.</p>
            {result.collection && <div className="q2-src-acts"><button type="button" className="q2-src-btn go" onClick={() => onOpenSource(result.collection!)}>Open {name.trim()}</button></div>}
          </div>
        )}
      </div>
    </div>
  )
}
