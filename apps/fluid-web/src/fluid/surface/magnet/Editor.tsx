/* THE MAGNET'S CONFIGURATION EDITOR (owner Turns #1318, #1592: "setting
 * sources and values").
 *
 * One editor for every Magnet, over the universal configuration (types.ts
 * MagnetConfig): its sources, what it selects, how it collects and
 * synthesizes, what it would notify and how it is presented. Nothing here is
 * conversation-specific -- a conversation is one source value among the
 * kinds -- and saving changes the SAME Magnet through magnet.reconfigure: its
 * id, its zone, where it is and its view state stay.
 *
 * Every value the server keeps can be set. What a value asks that this build
 * does not run (a source nothing here reads, scheduled or continuous
 * collection, synthesis, notifications, selection beyond information types)
 * is kept and said beside it, with its reason (model.ts notRunning,
 * sourceChoices); nothing is hidden and nothing is run.
 *
 * The draft is working state, held by the Magnet (client.ts useDraft), so it
 * survives the pane being docked, floated or collapsed until it is saved or
 * discarded. */

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { store } from '../../store'
import {
  COLLECTION_MODES, INFORMATION_TYPES, RENDERERS, SYNTHESIS_MODES,
  type MagnetConfig, type MagnetSeed, type MagnetSource,
} from './types'
import {
  BUILD_ENV, CATEGORY_LABEL, SELECTION_KEPT, capabilitiesOfConfig, changeOf, draftProblems, notRunning, sourceChoices, sourceReason,
  tidySelection, type InformationType,
} from './model'
import { adapters } from './runtime'
import { saveConfig, setDraft, useDraft } from './client'
import { setViewState } from '../viewState'
import { Icon } from './icons'

const seedOf = ({ id: _id, ...rest }: MagnetConfig): MagnetSeed => rest

const RENDERER_SAYS: Record<MagnetSeed['presentation']['renderer'], string> = {
  disc: 'A disc, with its ring showing what it holds',
  ring: 'A heavier ring: what it holds, at a glance',
  cards: 'Its items as cards',
  list: 'Its items as a list',
  gallery: 'Its items as tiles; pictures shown',
}

/** The conversations this browser knows of, for a conversation source. */
function useConversations(): Array<{ id: string; name: string }> {
  useEffect(() => { if (store.list === null) void store.loadList().catch(() => {}) }, [])
  const tick = useSyncExternalStore((fn) => store.subscribe('coll:conversations', fn), () => store.list)
  void tick
  const by = new Map<string, string>()
  for (const c of store.list ?? []) by.set(c.id, c.name)
  for (const c of store.conversations.values()) if (!by.has(c.id)) by.set(c.id, c.name)
  return [...by].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
}

export function Editor({ id, config, at }: { id: `mag-${string}`; config: MagnetConfig; at: 'all' | 'collects' }) {
  const held = useDraft(id)
  const d: MagnetSeed = held ?? seedOf(config)
  const set = (fn: (x: MagnetSeed) => MagnetSeed) => setDraft(id, fn(d))
  const [saving, setSaving] = useState(false)
  const [refused, setRefused] = useState<string | null>(null)
  const conversations = useConversations()
  const first = useRef<HTMLFieldSetElement | null>(null)
  useEffect(() => { if (at === 'collects') first.current?.scrollIntoView?.({ block: 'start' }) }, [at])

  const tidy: MagnetSeed = { ...d, selection: tidySelection(d.selection) }
  const change = changeOf(config, tidy)
  const changed = Object.keys(change).length > 0
  const problems = draftProblems(tidy)
  const draftConfig: MagnetConfig = { ...tidy, id }
  const off = notRunning(draftConfig, BUILD_ENV, adapters)
  const offOf = (facet: string) => off.filter((o) => o.facet === facet)
  const can = capabilitiesOfConfig(draftConfig, BUILD_ENV, adapters)
  const kinds = sourceChoices(BUILD_ENV, adapters)
  const types = d.selection.informationTypes ?? []

  const close = () => { setDraft(id, null); setViewState({ surface: id, resource: 'magnet:' + id }, 'panel', 'results') }
  const save = async () => {
    setSaving(true); setRefused(null)
    try {
      await saveConfig(id, change)
      close()
    } catch (e) { setRefused((e as Error).message) } finally { setSaving(false) }
  }
  const setSource = (i: number, s: MagnetSource) => set((x) => ({ ...x, sources: x.sources.map((y, j) => (j === i ? s : y)) }))
  const addSource = (kind: MagnetSource['kind']) => set((x) => ({ ...x, sources: [...x.sources, blank(kind)] }))
  const toggleType = (t: InformationType) => set((x) => {
    const now = x.selection.informationTypes ?? []
    const next = now.includes(t) ? now.filter((y) => y !== t) : [...now, t]
    return { ...x, selection: { ...x.selection, informationTypes: INFORMATION_TYPES.filter((y) => next.includes(y)) } }
  })

  return <form className="mg-edit" aria-label="Configure this magnet" onSubmit={(e) => { e.preventDefault(); if (changed && !problems.length && !saving) void save() }}>
    <p className="mg-edit-lead">The same magnet, whatever you change: it keeps its place, its id and how you left it.</p>

    <fieldset ref={first} data-part="sources">
      <legend>Sources</legend>
      {d.sources.map((s, i) => {
        const why = sourceReason(s, BUILD_ENV, adapters)
        return <div key={i} className="mg-edit-row" data-source={s.kind}>
          <Icon name={s.kind} />
          {s.kind === 'conversation'
            ? <select aria-label={`Source ${i + 1}: conversation`} value={s.conversation} onChange={(e) => setSource(i, { kind: 'conversation', conversation: e.target.value })}>
                {!s.conversation && <option value="">Choose a conversation…</option>}
                {!conversations.some((c) => c.id === s.conversation) && s.conversation && <option value={s.conversation}>{store.conversations.get(s.conversation)?.name ?? s.conversation}</option>}
                {conversations.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            : <span className="mg-edit-src">{kindWord(s)}</span>}
          <button type="button" className="mg-link" disabled={d.sources.length <= 1} title={d.sources.length <= 1 ? 'A magnet reads at least one source' : 'Remove this source'}
            onClick={() => set((x) => ({ ...x, sources: x.sources.filter((_, j) => j !== i) }))}>Remove</button>
          {why && <p className="mg-why" data-code={why.code}>{why.message}</p>}
        </div>
      })}
      <div className="mg-edit-add">
        <span>Add a source:</span>
        {kinds.map((k) => {
          const why = k.availability.state === 'disabled' ? k.availability.reason.message : null
          return <button key={k.kind} type="button" className="mg-chip" aria-disabled={why ? true : undefined} title={why ?? `Add a ${k.label.toLowerCase()} source`}
            onClick={() => { if (!why) addSource(k.kind) }}><Icon name={k.kind} size={12} /> {k.label}</button>
        })}
      </div>
      <p className="mg-why">{kinds.filter((k) => k.availability.state === 'disabled').map((k) => `${k.label}: ${k.availability.state === 'disabled' ? k.availability.reason.message : ''}`).join(' ')}</p>
    </fieldset>

    <fieldset data-part="collects">
      <legend>What it collects</legend>
      <div className="mg-edit-types">
        {INFORMATION_TYPES.map((t) => <label key={t} className="mg-check" data-type={t} title={can.has(t) ? CATEGORY_LABEL[t] : `None of its sources can show ${CATEGORY_LABEL[t].toLowerCase()} in this build`}>
          <input type="checkbox" checked={types.includes(t)} onChange={() => toggleType(t)} />
          <Icon name={t} size={14} /> {CATEGORY_LABEL[t]}{!can.has(t) && <span className="mg-why-inline"> (not here)</span>}
        </label>)}
      </div>
      <label className="mg-field">Words it looks for
        <input type="text" value={d.selection.criteria ?? ''} placeholder="criteria" onChange={(e) => set((x) => ({ ...x, selection: { ...x.selection, criteria: e.target.value } }))} />
      </label>
      <label className="mg-field">Phrases (one per line)
        <textarea rows={2} value={(d.selection.phrases ?? []).join('\n')} onChange={(e) => set((x) => ({ ...x, selection: { ...x.selection, phrases: e.target.value.split('\n') } }))} />
      </label>
      <div className="mg-edit-dates">
        <label className="mg-field">After<input type="date" value={(d.selection.dates?.after ?? '').slice(0, 10)}
          onChange={(e) => set((x) => ({ ...x, selection: { ...x.selection, dates: { ...x.selection.dates, after: e.target.value || undefined } } }))} /></label>
        <label className="mg-field">Before<input type="date" value={(d.selection.dates?.before ?? '').slice(0, 10)}
          onChange={(e) => set((x) => ({ ...x, selection: { ...x.selection, dates: { ...x.selection.dates, before: e.target.value || undefined } } }))} /></label>
      </div>
      {offOf('selection').length ? offOf('selection').map((o, i) => <p key={i} className="mg-why" data-code={o.reason.code}>{o.reason.message}</p>)
        : <p className="mg-why">Words, phrases and dates: {SELECTION_KEPT}</p>}
    </fieldset>

    <fieldset data-part="when">
      <legend>Collection and synthesis</legend>
      <div className="mg-edit-pair">
        <label className="mg-field">Collects
          <select value={d.collection.mode} onChange={(e) => set((x) => ({ ...x, collection: { mode: e.target.value as MagnetSeed['collection']['mode'] } }))}>
            {COLLECTION_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        {d.collection.mode === 'scheduled' && <label className="mg-field">Schedule
          <input type="text" value={d.collection.schedule ?? ''} placeholder="PT1H or 0 * * * *" onChange={(e) => set((x) => ({ ...x, collection: { mode: 'scheduled', schedule: e.target.value } }))} /></label>}
        <label className="mg-field">Synthesis
          <select value={d.synthesis.mode} onChange={(e) => set((x) => ({ ...x, synthesis: { mode: e.target.value as MagnetSeed['synthesis']['mode'] } }))}>
            {SYNTHESIS_MODES.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        {d.synthesis.mode === 'scheduled' && <label className="mg-field">Schedule
          <input type="text" value={d.synthesis.schedule ?? ''} placeholder="PT1H or 0 * * * *" onChange={(e) => set((x) => ({ ...x, synthesis: { mode: 'scheduled', schedule: e.target.value } }))} /></label>}
      </div>
      {[...offOf('collection'), ...offOf('synthesis')].map((o, i) => <p key={i} className="mg-why" data-code={o.reason.code}>{o.reason.message}</p>)}
      <div className="mg-edit-types">
        {(['newItems', 'changes', 'failures'] as const).map((k) => <label key={k} className="mg-check">
          <input type="checkbox" checked={d.notifications[k]} onChange={() => set((x) => ({ ...x, notifications: { ...x.notifications, [k]: !x.notifications[k] } }))} />
          Notify on {k === 'newItems' ? 'new items' : k}
        </label>)}
      </div>
      {offOf('notifications').map((o, i) => <p key={i} className="mg-why" data-code={o.reason.code}>{o.reason.message}</p>)}
    </fieldset>

    <fieldset data-part="presentation">
      <legend>Presentation</legend>
      <div className="mg-edit-types" role="radiogroup" aria-label="How it is presented">
        {RENDERERS.map((r) => <label key={r} className="mg-check" title={RENDERER_SAYS[r]}>
          <input type="radio" name={`mg-renderer-${id}`} checked={d.presentation.renderer === r} onChange={() => set((x) => ({ ...x, presentation: { renderer: r } }))} /> {r}
        </label>)}
      </div>
      <p className="mg-why">{RENDERER_SAYS[d.presentation.renderer]}. Where it sits (disc, card, docked, floating, a workspace) is its placement, not its configuration.</p>
    </fieldset>

    {problems.length > 0 && <ul className="mg-problems">{problems.map((p) => <li key={p}>{p}</li>)}</ul>}
    {refused && <p className="mg-problems" role="alert">{refused}</p>}
    <div className="mg-edit-foot">
      <button type="submit" className="fl-btn mg-save" disabled={!changed || problems.length > 0 || saving}>{saving ? 'Saving…' : 'Save'}</button>
      <button type="button" className="fl-btn" onClick={close}>{changed ? 'Discard' : 'Done'}</button>
    </div>
  </form>
}

function blank(kind: MagnetSource['kind']): MagnetSource {
  switch (kind) {
    case 'conversation': return { kind, conversation: '' }
    case 'brain': return { kind, brain: '' }
    case 'connector': return { kind, connector: '' }
    case 'web': return { kind }
    case 'other': return { kind, type: '', ref: '' }
  }
}
function kindWord(s: MagnetSource): string {
  switch (s.kind) {
    case 'brain': return `Brain ${s.brain}`
    case 'connector': return `Connector ${s.connector}${s.location ? ' · ' + s.location : ''}`
    case 'web': return `Web ${s.url ?? s.domain ?? ''}`
    case 'other': return `${s.type} ${s.ref}`
    case 'conversation': return s.conversation
  }
}
