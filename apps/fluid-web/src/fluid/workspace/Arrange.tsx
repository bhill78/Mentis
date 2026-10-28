/* Redesigned Arrange sheet (owner's consolidation brief W3-ui).
 * Four compact icon groups: This Page, Layouts, Focus, Look.
 * Visual previews, compact icons, words in tooltips, no word-heavy menus. */

import { useEffect, useState, useSyncExternalStore } from 'react'
import { store } from '../store'
import {
  Holder,
  applyLayout,
  deleteNamed,
  layoutKind,
  loadLibrary,
  presetLayout,
  restoreSetAside,
  saveNamed,
  setAsideOf,
  setDefault,
  useArr,
  useChanged,
  useLibrary,
  workspace,
  type Named,
  type Preset,
  type DefaultPlace,
} from './place'
import type { Node, Zone } from './tree'
import { openSketch } from './SketchView'
import { floatZones, tidyFloats } from '../focus/model'
import { onPage, pageIn, pageView } from '../focus/page'
import { useNav, useSelection } from './hooks'
import * as nav from '../nav'
import { objectsOpen, onObjectsOpen, setObjectsOpen } from './open'
import { Opt, Sec } from '../frame/Sheet'
import { AppearancePicker, DEFAULT_APPEARANCE, readAppearance } from '../present'
import { showSelection, useSelectionShown } from './Zones'
import { PRESENTATIONS, lens, rememberedPresentation, type FocusPresentation } from '../focus/lens'
import { LayoutThumb } from './thumbnail'

const ago = (t: number | null) => {
  if (!t) return null
  const s = Math.max(0, Date.now() / 1000 - t)
  return s < 90 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`
}

const FROM: Record<string, string> = {
  session: 'as you left it in this tab',
  saved: 'as saved',
  default: 'from the default layout',
  product: 'as Mentis starts it',
  layout: 'from a layout',
}

const PRESET_DISPLAY_NAMES: Record<string, string> = {
  'preset-focus': 'Focus layout',
}

/** Arrangement rows for any place's holder: the workspace's, or Home's. */
export function PlaceRows({
  h,
  onClose,
  kind,
  onLeftover,
}: {
  h: Holder
  onClose: () => void
  kind: 'home' | 'workspace'
  onLeftover?: (zones: Zone[]) => void
}) {
  useArr(h)
  const shownPage = useNav().page
  const changed = useChanged(h)
  const lib = useLibrary()
  useEffect(() => { void loadLibrary() }, [])

  const [naming, setNaming] = useState<string | null>(null)
  const [pres, setPres] = useState<FocusPresentation>(rememberedPresentation())
  const [selectedDefaultLayout, setSelectedDefaultLayout] = useState<string>('preset-focus')

  const fail = (e: unknown) => store.setError(`Layouts: ${(e as Error).message ?? e}`)
  const usable = (lib?.layouts ?? []).filter((l) => layoutKind(l) === kind)
  const savedAgo = ago(h.savedAt)
  const setAside = setAsideOf(shownPage)

  // Built-in presets with names normalized (e.g. Focus preset is "Focus layout")
  const pKind = kind === 'home' ? 'home' : h.kind
  const presets: { id: string; name: string; says: string; named: Named }[] = (lib?.presets ?? []).map((p: Preset) => {
    const named = presetLayout(p, pKind)
    const displayName = PRESET_DISPLAY_NAMES[p.id] ?? p.name
    return { id: p.id, name: displayName, says: p.says, named: { ...named, name: displayName } }
  })

  // All layout choices for the defaults dropdown
  const allChoices: { id: string; name: string }[] = [
    ...presets.map((p) => ({ id: p.id, name: p.name })),
    ...usable.map((l) => ({ id: l.id, name: l.name })),
  ]

  const activeDefaultLayout = allChoices.some((c) => c.id === selectedDefaultLayout)
    ? selectedDefaultLayout
    : (allChoices[0]?.id ?? 'preset-focus')

  return (
    <>
      {/* 1. THIS PAGE */}
      <Sec>{kind === 'home' ? 'This arrangement' : 'This Page'}</Sec>
      <p className="wk-note wk-status-line" data-arrangement-from={h.from}>
        {FROM[h.from] ?? ''}
        {savedAgo ? ` · saved ${savedAgo}` : h.kind === 'stream' ? '' : ' · not saved'}
        {changed ? ' · changed in this tab' : ''}
      </p>
      <div className="wk-icon-row" role="toolbar" aria-label="This page actions">
        <button
          type="button"
          className="wk-icon-btn"
          disabled={h.kind === 'stream'}
          title="Save: keep it in the Brain for any browser"
          aria-label="Save"
          onClick={() => { onClose(); void h.save().catch(fail) }}
        >
          <svg className="wk-svg-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M3 2.5h8l3 3V13.5H3V2.5zM5 2.5v3h5v-3M5 13.5V9h6v4.5" />
          </svg>
          <span className="wk-btn-label">Save</span>
        </button>

        <button
          type="button"
          className="wk-icon-btn"
          disabled={!h.savedAt}
          title="Restore saved: back to what was saved in the Brain"
          aria-label="Restore saved"
          onClick={() => { onClose(); void h.restoreSaved().catch(fail) }}
        >
          <svg className="wk-svg-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M2.5 7.5A5.5 5.5 0 1 1 8 13.5c-2.2 0-4-1.2-4.9-3M2.5 3.5v4h4" />
          </svg>
          <span className="wk-btn-label">Restore</span>
        </button>

        <button
          type="button"
          className="wk-icon-btn"
          disabled={!h.canUndo()}
          title="Undo: last change (Ctrl+Z)"
          aria-label="Undo"
          onClick={() => { onClose(); h.undo() }}
        >
          <svg className="wk-svg-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M4 6.5h7a3.5 3.5 0 0 1 0 7H9M4 6.5L6.5 4M4 6.5L6.5 9" />
          </svg>
          <span className="wk-btn-label">Undo</span>
        </button>

        <button
          type="button"
          className="wk-icon-btn"
          title="Reset: back to the start"
          aria-label="Reset"
          onClick={() => { onClose(); h.reset() }}
        >
          <svg className="wk-svg-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M13.5 8.5A5.5 5.5 0 1 1 8 2.5c2.2 0 4 1.2 4.9 3M13.5 12.5v-4h-4" />
          </svg>
          <span className="wk-btn-label">Reset</span>
        </button>

        {kind === 'workspace' && (
          <button
            type="button"
            className="wk-icon-btn"
            disabled={!pageView(h.arr, shownPage).focus?.floats?.length}
            title="Tidy floating windows: line them up at the right"
            aria-label="Tidy floating windows"
            onClick={() => {
              onClose()
              const r = document.querySelector<HTMLElement>('.fx-main')?.getBoundingClientRect()
              h.edit(onPage((a) => tidyFloats(a, r?.width ?? 0, r?.height ?? 0), shownPage), 'Tidied the floating windows.')
            }}
          >
            <svg className="wk-svg-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="2.5" y="4.5" width="8" height="8" rx="1.5" />
              <path d="M5.5 2.5h6a1.5 1.5 0 0 1 1.5 1.5v6" />
            </svg>
            <span className="wk-btn-label">Tidy</span>
          </button>
        )}

        {kind === 'workspace' && (
          <button
            type="button"
            className="wk-icon-btn"
            title="Sketch a layout: draw straight lines to divide regions"
            aria-label="Sketch a layout"
            onClick={() => {
              onClose()
              const page = pageIn(workspace.arr, shownPage)
              openSketch({
                tree: pageView(workspace.arr, page).tree,
                page,
                onApply: (newTree: Node, leftover: Zone[]) => {
                  workspace.edit(
                    onPage((v) => floatZones({ ...v, tree: newTree }, leftover), page),
                    leftover.length ? `Sketched a new layout; ${leftover.length === 1 ? `${leftover[0].name ?? 'a section'} floats` : `${leftover.length} sections float`} so nothing is lost.` : 'Sketched a new layout.',
                  )
                  if (leftover.length) onLeftover?.(leftover)
                },
              })
            }}
          >
            <svg className="wk-svg-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M11 2.5l2.5 2.5L5 13.5H2.5V11L11 2.5z" />
            </svg>
            <span className="wk-btn-label">Sketch</span>
          </button>
        )}
      </div>

      {/* 2. LAYOUTS */}
      <Sec>Layouts</Sec>
      <div className="wk-thumb-grid">
        {presets.map((p) => {
          const tree = p.named.layout.tree
          return (
            <div key={p.id} className="wk-thumb-card" data-preset={p.id}>
              <button
                type="button"
                className="wk-thumb-btn"
                title={`${p.says}. Click to apply to this Page.`}
                aria-label={`Apply ${p.name} to this Page`}
                onClick={() => {
                  setSelectedDefaultLayout(p.id)
                  onClose()
                  void applyLayout(p.named, 'page').catch(fail)
                }}
              >
                <LayoutThumb tree={tree} width={64} height={40} />
              </button>
              <span className="wk-thumb-name" title={p.name}>{p.name}</span>
              <button
                type="button"
                className="wk-thumb-place"
                title={`Apply ${p.name} to the whole place`}
                onClick={(e) => {
                  e.stopPropagation()
                  setSelectedDefaultLayout(p.id)
                  onClose()
                  void applyLayout(p.named, 'place').catch(fail)
                }}
              >
                Whole place
              </button>
            </div>
          )
        })}

        {usable.map((l: Named) => {
          const tree = l.layout.tree
          return (
            <div key={l.id} className="wk-thumb-card" data-custom-layout={l.name}>
              <button
                type="button"
                className="wk-thumb-btn"
                title={`Custom layout "${l.name}". Click to apply to this Page.`}
                aria-label={`Apply ${l.name} to this Page`}
                onClick={() => {
                  setSelectedDefaultLayout(l.id)
                  onClose()
                  void applyLayout(l, 'page').catch(fail)
                }}
              >
                <LayoutThumb tree={tree} width={64} height={40} />
              </button>
              <div className="wk-thumb-title-row">
                <span className="wk-thumb-name" title={l.name}>{l.name}</span>
                <button
                  type="button"
                  className="wk-mini wk-thumb-del"
                  aria-label={`Delete layout ${l.name}`}
                  title="Delete this layout"
                  onClick={(e) => {
                    e.stopPropagation()
                    void deleteNamed(l.id).catch(fail)
                  }}
                >
                  ✕
                </button>
              </div>
              <button
                type="button"
                className="wk-thumb-place"
                title={`Apply ${l.name} to the whole place`}
                onClick={(e) => {
                  e.stopPropagation()
                  setSelectedDefaultLayout(l.id)
                  onClose()
                  void applyLayout(l, 'place').catch(fail)
                }}
              >
                Whole place
              </button>
            </div>
          )
        })}
      </div>

      {/* Save as layout */}
      {naming === null ? (
        <Opt onPick={() => setNaming('')}>Save as a layout&hellip;</Opt>
      ) : (
        <form
          className="wk-name"
          onSubmit={(e) => {
            e.preventDefault()
            const name = naming.trim()
            if (!name) return
            setNaming(null)
            void saveNamed(name, h.arr).then(
              (l) => nav.toast({ text: `Saved the layout "${l.name}": its zones and what each shows, never what they held.` }),
              fail,
            )
          }}
        >
          <input
            autoFocus
            aria-label="Layout name"
            placeholder="Layout name…"
            value={naming}
            maxLength={80}
            onChange={(e) => setNaming(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                e.stopPropagation()
                setNaming(null)
              }
            }}
          />
          <button type="submit" className="wk-mini" disabled={!naming.trim()}>Save</button>
        </form>
      )}

      {/* Explicit Default for... control */}
      <div className="wk-defaults-group">
        <div className="wk-defaults-head">
          <span className="wk-defaults-title">Default for:</span>
          <select
            className="wk-defaults-select"
            aria-label="Layout to configure as default"
            value={activeDefaultLayout}
            onChange={(e) => setSelectedDefaultLayout(e.target.value)}
          >
            {allChoices.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="wk-defaults-ticks">
          {(['home', 'conversation', 'unnamed'] as DefaultPlace[]).map((p) => {
            const label = p === 'home' ? 'Home' : p === 'conversation' ? 'Conversations' : 'Unnamed'
            const isDefault = lib?.defaults[p] === activeDefaultLayout
            return (
              <label key={p} className="wk-tick-label" title={`Set as default for new ${label.toLowerCase()}`}>
                <input
                  type="checkbox"
                  checked={isDefault}
                  onChange={(e) => void setDefault(p, e.target.checked ? activeDefaultLayout : null).catch(fail)}
                />
                <span>{label}</span>
              </label>
            )
          })}
        </div>
      </div>

      {/* Set-aside items */}
      {setAside.length > 0 && (
        <div className="wk-setaside-block">
          <div className="wk-setaside-head">
            <span className="wk-defaults-title">Set aside ({setAside.length})</span>
          </div>
          <div className="wk-setaside-list">
            {setAside.map((z) => (
              <div key={z.id} className="wk-setaside-row">
                <span className="wk-setaside-name">{z.name ?? 'Section'}</span>
                <button
                  type="button"
                  className="wk-mini"
                  onClick={() => restoreSetAside(z.id, shownPage)}
                  title="Restore this section to the page"
                >
                  Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. FOCUS */}
      <Sec>Focus</Sec>
      <div className="wk-icon-row wk-focus-row" role="group" aria-label="Focus presentations">
        {PRESENTATIONS.map((p) => {
          const isNow = pres === p.id
          return (
            <button
              key={p.id}
              type="button"
              className={`wk-icon-btn ${isNow ? 'on' : ''}`}
              aria-pressed={isNow}
              title={`${p.label}: ${p.says}`}
              onClick={() => {
                lens.setPresentation(p.id)
                setPres(p.id)
              }}
            >
              <span className="wk-btn-icon" aria-hidden="true">{p.icon}</span>
              <span className="wk-btn-label">{p.label}</span>
            </button>
          )
        })}
      </div>

      {/* 4. LOOK */}
      <Sec>Look</Sec>
      {h.kind !== 'stream' && (
        <AppearancePicker
          title="Look for every zone here"
          value={readAppearance(h.arr.appearance, DEFAULT_APPEARANCE)}
          onChange={(a) => h.edit((x) => ({ ...x, appearance: a }))}
          onReset={() => h.edit(({ appearance: _gone, ...x }) => x, "This place takes Mentis's quiet look again.")}
          isDefault={!h.arr.appearance}
          resetLabel={["Back to Mentis's quiet look", "Mentis's quiet look"]}
        />
      )}
      <div className="wk-look-pref">
        <Opt
          onPick={() => setObjectsOpen(objectsOpen() === 'over' ? 'aside' : 'over')}
          title="Mixed: replies open beside, objects open over the arrangement"
        >
          Objects open: {objectsOpen() === 'over' ? 'over the arrangement' : 'beside This post'}
        </Opt>
      </div>

      {lib?.unreadable && <p className="wk-note">{lib.unreadable}</p>}
    </>
  )
}

export function ArrangeSheet({ onClose, onLeftover }: { onClose: () => void; onLeftover?: (zones: Zone[]) => void }) {
  const selected = useSelection()
  const shown = useSelectionShown()
  useSyncExternalStore(onObjectsOpen, objectsOpen)
  return (
    <div className="wk-arrange" data-sheet="arrange">
      <PlaceRows h={workspace} onClose={onClose} kind="workspace" onLeftover={onLeftover} />
      <Opt
        onPick={() => {
          onClose()
          nav.toast({ text: 'Drag any boundary to give room. Split a zone with its icons; drag a divider closed to merge. Keep… puts an object where you choose; drag a card onto a zone to move it. Save keeps the arrangement in the Brain.' })
        }}
      >
        How this works
      </Opt>
      {selected.size > 0 && (
        <>
          <Sec>Selection</Sec>
          <Opt on={shown === 'here'} onPick={() => { onClose(); showSelection(shown !== 'here') }}>
            Show the selection ({selected.size})
          </Opt>
          <Opt onPick={() => { onClose(); store.clearSelection() }}>Clear the selection</Opt>
        </>
      )}
    </div>
  )
}

export default ArrangeSheet
