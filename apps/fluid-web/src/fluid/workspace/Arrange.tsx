/* One Workspace Settings panel: Page, Layouts, Focus, and Look/background.
 * Every choice is presented through the shared IconMenu inside Sheet. */

import { useEffect, useState, useSyncExternalStore } from 'react'
import { store } from '../store'
import {
  Holder, applyLayout, deleteNamed, layoutKind, loadLibrary, presetLayout, restoreSetAside,
  saveNamed, setAsideOf, setDefault, useArr, useChanged, useLibrary, workspace,
  type DefaultPlace, type Named, type Preset,
} from './place'
import type { Node, Zone } from './tree'
import { openSketch } from './SketchView'
import { floatZones, tidyFloats } from '../focus/model'
import { onPage, pageIn, pageView } from '../focus/page'
import { useNav, useSelection } from './hooks'
import * as nav from '../nav'
import { objectsOpen, onObjectsOpen, setObjectsOpen } from './open'
import { AppearancePicker, DEFAULT_APPEARANCE, readAppearance } from '../present'
import { showSelection, useSelectionShown } from './Zones'
import { PRESENTATIONS, lens, rememberedPresentation, type FocusPresentation } from '../focus/lens'
import { LayoutThumb } from './thumbnail'
import { IconMenu, type IconGroup, type IconItem } from '../frame/IconMenu'
import { useLookGroups } from '../frame/LookColumn'
import { LookBody } from '../frame/LookSheet'

const ago = (t: number | null) => {
  if (!t) return null
  const s = Math.max(0, Date.now() / 1000 - t)
  return s < 90 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`
}

const FROM: Record<string, string> = { session: 'as you left it in this tab', saved: 'as saved', default: 'from the default layout', product: 'as Mentis starts it', layout: 'from a layout' }
const PRESET_DISPLAY_NAMES: Record<string, string> = { 'preset-focus': 'Focus layout' }

const mark = (path: string) => <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d={path} /></svg>

function LayoutControls({ h, kind, shownPage, onClose }: { h: Holder; kind: 'home' | 'workspace'; shownPage: string; onClose: () => void }) {
  const lib = useLibrary()
  const [scope, setScope] = useState<'page' | 'place'>('page')
  const [naming, setNaming] = useState<string | null>(null)
  const [selectedDefaultLayout, setSelectedDefaultLayout] = useState('preset-focus')
  const fail = (e: unknown) => store.setError(`Layouts: ${(e as Error).message ?? e}`)
  const usable = (lib?.layouts ?? []).filter((l) => layoutKind(l) === kind)
  const pKind = kind === 'home' ? 'home' : h.kind
  const presets = (lib?.presets ?? []).map((p: Preset) => {
    const named = presetLayout(p, pKind)
    const name = PRESET_DISPLAY_NAMES[p.id] ?? p.name
    return { id: p.id, name, says: p.says, named: { ...named, name } }
  })
  const choices = [...presets.map((p) => ({ id: p.id, name: p.name })), ...usable.map((l) => ({ id: l.id, name: l.name }))]
  const active = choices.some((c) => c.id === selectedDefaultLayout) ? selectedDefaultLayout : (choices[0]?.id ?? 'preset-focus')
  const setAside = setAsideOf(shownPage)
  const choose = (id: string, named: Named) => { setSelectedDefaultLayout(id); onClose(); applyLayout(named, scope) }
  return <div className="wk-layout-controls">
    <div className="wk-scope" role="radiogroup" aria-label="Apply a layout to">
      <span className="wk-scope-label">Apply to</span>
      <button type="button" role="radio" aria-checked={scope === 'page'} onClick={() => setScope('page')} title="Change only this Page">This Page</button>
      <button type="button" role="radio" aria-checked={scope === 'place'} onClick={() => setScope('place')} title="Change every Page in this place">Whole place</button>
    </div>
    <div className="wk-thumb-grid">
      {presets.map((p) => <div key={p.id} className="wk-thumb-card" data-preset={p.id}>
        <button type="button" className="wk-thumb-btn" title={`${p.says}. Apply to ${scope === 'page' ? 'this Page' : 'the whole place'}.`} aria-label={`Apply ${p.name}`} onClick={() => choose(p.id, p.named)}><LayoutThumb tree={p.named.layout.tree} width={64} height={40} /></button>
        <span className="wk-thumb-name" title={p.name}>{p.name}</span>
      </div>)}
      {usable.map((l) => <div key={l.id} className="wk-thumb-card" data-custom-layout={l.name}>
        <button type="button" className="wk-thumb-btn" title={`Apply your layout ${l.name}`} aria-label={`Apply ${l.name}`} onClick={() => choose(l.id, l)}><LayoutThumb tree={l.layout.tree} width={64} height={40} /></button>
        <div className="wk-thumb-title-row"><span className="wk-thumb-name" title={l.name}>{l.name}</span><button type="button" className="wk-mini wk-thumb-del" aria-label={`Delete layout ${l.name}`} title="Delete this layout" onClick={() => void deleteNamed(l.id).catch(fail)}>×</button></div>
      </div>)}
    </div>
    {naming === null ? <button type="button" className="wk-settings-line" onClick={() => setNaming('')} title="Save this arrangement as a reusable layout">＋ Save as layout</button>
      : <form className="wk-name" onSubmit={(e) => { e.preventDefault(); const name = naming.trim(); if (!name) return; setNaming(null); void saveNamed(name, h.arr).then((l) => nav.toast({ text: `Saved the layout "${l.name}": its zones and what each shows, never what they held.` }), fail) }}>
        <input autoFocus aria-label="Layout name" placeholder="Layout name…" value={naming} maxLength={80} onChange={(e) => setNaming(e.target.value)} onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); setNaming(null) } }} />
        <button type="submit" className="wk-mini" disabled={!naming.trim()}>Save</button>
      </form>}
    {!!choices.length && <details className="wk-defaults-group wk-disclose">
      <summary className="wk-disclose-head" title="Which layout new Home, conversation and unnamed places start from">Default for…</summary>
      <div className="wk-defaults-head"><span className="wk-defaults-title">Default for</span><select className="wk-defaults-select" aria-label="Layout to configure as default" value={active} onChange={(e) => setSelectedDefaultLayout(e.target.value)}>{choices.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
      <div className="wk-defaults-ticks">{(['home', 'conversation', 'unnamed'] as DefaultPlace[]).map((place) => { const label = place === 'home' ? 'Home' : place === 'conversation' ? 'Conversations' : 'Unnamed'; return <label key={place} className="wk-tick-label" title={`Set as default for new ${label.toLowerCase()}`}><input type="checkbox" checked={lib?.defaults[place] === active} onChange={(e) => void setDefault(place, e.target.checked ? active : null).catch(fail)} /><span>{label}</span></label> })}</div>
    </details>}
    {!!setAside.length && <details className="wk-setaside-block wk-disclose"><summary className="wk-disclose-head" title="Sections a layout had no room for: nothing is lost, restore any of them">Set aside · {setAside.length}</summary><div className="wk-setaside-list">{setAside.map((z) => <div key={z.id} className="wk-setaside-row"><span className="wk-setaside-name">{z.name ?? 'Section'}</span><button type="button" className="wk-mini" onClick={() => restoreSetAside(shownPage, z.id)} title="Restore this section to the Page">Restore</button></div>)}</div></details>}
    {lib?.unreadable && <p className="wk-note">{lib.unreadable}</p>}
  </div>
}

function LocalLook({ h }: { h: Holder }) {
  useSyncExternalStore(onObjectsOpen, objectsOpen)
  return <div className="wk-settings-look">
    {h.kind !== 'stream' && <AppearancePicker title="Look for every zone here" value={readAppearance(h.arr.appearance, DEFAULT_APPEARANCE)} onChange={(a) => h.edit((x) => ({ ...x, appearance: a }))} onReset={() => h.edit(({ appearance: _gone, ...x }) => x, "This place takes Mentis's quiet look again.")} isDefault={!h.arr.appearance} resetLabel={["Back to Mentis's quiet look", "Mentis's quiet look"]} />}
    <button type="button" className="wk-settings-line" onClick={() => setObjectsOpen(objectsOpen() === 'over' ? 'aside' : 'over')} title="Choose whether object details open over the arrangement or beside This post">Objects open {objectsOpen() === 'over' ? 'over' : 'beside'}</button>
  </div>
}

/** Arrangement settings for either the workspace or Home. */
export function PlaceRows({ h, onClose, kind, onLeftover, more = [] }: { h: Holder; onClose: () => void; kind: 'home' | 'workspace'; onLeftover?: (zones: Zone[]) => void; more?: IconGroup[] }) {
  useArr(h)
  const shownPage = useNav().page
  const changed = useChanged(h)
  const lookGroups = useLookGroups()
  const [pres, setPres] = useState<FocusPresentation>(rememberedPresentation())
  useEffect(() => { void loadLibrary() }, [])
  const fail = (e: unknown) => store.setError(`Layouts: ${(e as Error).message ?? e}`)
  const savedAgo = ago(h.savedAt)
  const pageItems: IconItem[] = [
    { id: 'save', icon: mark('M4 3h9l3 3v11H4zM7 3v4h6V3M7 17v-5h6v5'), label: 'Save', says: 'Save this Page in the Brain for every browser', off: h.kind === 'stream', onPick: () => { onClose(); void h.save().catch(fail) } },
    { id: 'restore', icon: mark('M4 8a6 6 0 1 1 1 6M4 4v4h4'), label: 'Restore', says: 'Restore the arrangement saved in the Brain', off: !h.savedAt, onPick: () => { onClose(); void h.restoreSaved().catch(fail) } },
    { id: 'undo', icon: mark('M7 7H14a4 4 0 0 1 0 8h-3M7 7l3-3M7 7l3 3'), label: 'Undo', says: 'Undo the last arrangement change', off: !h.canUndo(), onPick: () => { onClose(); h.undo() } },
    { id: 'reset', icon: mark('M16 10a6 6 0 1 1-2-4M16 3v5h-5'), label: 'Reset', says: 'Reset this Page to how it started', onPick: () => { onClose(); h.reset() } },
  ]
  if (kind === 'workspace') pageItems.push(
    { id: 'tidy', icon: mark('M3 6h10v10H3zM7 3h10v10'), label: 'Tidy', says: 'Line up floating windows at the right', off: !pageView(h.arr, shownPage).focus?.floats?.length, onPick: () => { onClose(); const r = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect(); h.edit(onPage((a) => tidyFloats(a, r?.width ?? 0, r?.height ?? 0), shownPage), 'Tidied the floating windows.') } },
    { id: 'sketch', icon: mark('M14 3l3 3L7 16H4v-3z'), label: 'Sketch', says: 'Sketch a layout by drawing straight dividers', onPick: () => { onClose(); const page = pageIn(workspace.arr, shownPage); openSketch({ tree: pageView(workspace.arr, page).tree, page, onApply: (tree: Node, leftover: Zone[]) => { workspace.edit(onPage((v) => floatZones({ ...v, tree }, leftover), page), leftover.length ? `Sketched a new layout; ${leftover.length} section${leftover.length === 1 ? '' : 's'} float so nothing is lost.` : 'Sketched a new layout.'); if (leftover.length) onLeftover?.(leftover) } }) } },
  )
  const focusItems: IconItem[] = PRESENTATIONS.map((p) => ({ id: p.id, icon: p.icon, label: p.label, says: `${p.label}: ${p.says}`, on: pres === p.id, onPick: () => { lens.setPresentation(p.id); setPres(p.id) } }))
  const fallbackLook: IconGroup[] = lookGroups.length ? [] : [{ title: 'Background', body: <LookBody /> }]
  const groups: IconGroup[] = [
    { title: kind === 'home' ? 'Arrangement' : 'Page', items: pageItems, body: <p className="wk-settings-status">{FROM[h.from] ?? ''}{savedAgo ? ` · saved ${savedAgo}` : h.kind === 'stream' ? '' : ' · not saved'}{changed ? ' · changed in this tab' : ''}</p> },
    { title: 'Layouts', body: <LayoutControls h={h} kind={kind} shownPage={shownPage} onClose={onClose} /> },
    ...(kind === 'workspace' ? [{ title: 'Focus', items: focusItems } satisfies IconGroup] : []),
    ...lookGroups,
    ...fallbackLook,
    /* The icon Surfaces column (LookColumn.tsx) sets the workspace's look; Home keeps its own control here. */
    ...(lookGroups.length && kind === 'workspace' ? [] : [{ title: 'Surface', body: <LocalLook h={h} /> } satisfies IconGroup]),
    ...more,
  ]
  return <IconMenu groups={groups} label="Workspace settings" layout="settings" />
}

export function ArrangeSheet({ onClose, onLeftover }: { onClose: () => void; onLeftover?: (zones: Zone[]) => void }) {
  const selected = useSelection()
  const shown = useSelectionShown()
  const extra: IconGroup[] = [{ title: 'More', items: [
    { id: 'help', icon: '?', label: 'Help', says: 'How arranging this workspace works', onPick: () => { onClose(); nav.toast({ text: 'Drag a boundary to give room. Split a section with its icons; drag a divider closed to merge. Keep puts an object where you choose. Save keeps the arrangement in the Brain.' }) } },
    ...(selected.size ? [
      { id: 'selection', icon: '◩', label: 'Selection', says: `${shown === 'here' ? 'Hide' : 'Show'} the selection (${selected.size})`, on: shown === 'here', onPick: () => { onClose(); showSelection(shown !== 'here') } },
      { id: 'clear', icon: '×', label: 'Clear', says: `Clear the selection (${selected.size})`, onPick: () => { onClose(); store.clearSelection() } },
    ] : []),
  ] }]
  return <div className="wk-arrange" data-sheet="settings"><PlaceRows h={workspace} onClose={onClose} kind="workspace" onLeftover={onLeftover} more={extra} /></div>
}

export default ArrangeSheet
