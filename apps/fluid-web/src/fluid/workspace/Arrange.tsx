/* What the bar's Arrange sheet holds (spec 3.7), for the frame to mount
 * anchored under its Arrange button: this place's arrangement -- Save it in
 * the Brain, Restore what is saved, Reset, Undo -- the named layouts kept in
 * the Brain (use one here, save this as one, make one the default for Home,
 * conversations or unnamed ones), the objects preference and the Selection
 * rows (Fluid completion, stream A; #107, adm-c93a 5.5). */

import { useEffect, useState, useSyncExternalStore } from 'react'
import { store } from '../store'
import { Holder, deleteNamed, layoutKind, loadLibrary, saveNamed, setDefault, treeOf, useArr, useChanged, useLibrary, usePreset, withTree, workspace, type Named, type Preset } from './place'
import type { Node, Zone } from './tree'
import { openSketch } from './SketchView'
import { useSelection } from './hooks'
import * as nav from '../nav'
import { objectsOpen, onObjectsOpen, setObjectsOpen } from './open'
import { Opt, Sec } from '../frame/Sheet'
import { AppearancePicker, DEFAULT_APPEARANCE, readAppearance } from '../present'
import { showSelection, useSelectionShown } from './Zones'

const ago = (t: number | null) => {
  if (!t) return null
  const s = Math.max(0, Date.now() / 1000 - t)
  return s < 90 ? 'just now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`
}
const FROM: Record<string, string> = {
  session: 'as you left it in this tab', saved: 'as saved', default: 'from the default layout', product: 'as Mentis starts it', layout: 'from a layout',
}

/** Arrangement rows for any place's holder: the workspace's, or Home's. */
export function PlaceRows({ h, onClose, kind, onLeftover }: { h: Holder; onClose: () => void; kind: 'home' | 'workspace'; onLeftover?: (zones: Zone[]) => void }) {
  useArr(h)
  const changed = useChanged(h)
  const lib = useLibrary()
  useEffect(() => { void loadLibrary() }, [])
  const [naming, setNaming] = useState<string | null>(null)
  const place = h.kind === 'home' ? 'home' : h.kind === 'unnamed' ? 'unnamed' : 'conversation'
  const placeWords = place === 'home' ? 'Home' : place === 'unnamed' ? 'unnamed conversations' : 'conversations'
  const fail = (e: unknown) => store.setError(`Layouts: ${(e as Error).message ?? e}`)
  const usable = (lib?.layouts ?? []).filter((l) => layoutKind(l) === kind)
  const savedAgo = ago(h.savedAt)
  return (
    <>
      <Sec>This arrangement</Sec>
      <p className="wk-note" data-arrangement-from={h.from}>
        {FROM[h.from] ?? ''}{savedAgo ? ` · saved ${savedAgo}` : h.kind === 'stream' ? '' : ' · not saved'}
        {changed && <><br /><b className="wk-changed">Changed in this tab: Save keeps it, or it stays this tab's.</b></>}
      </p>
      <div className="wk-optrow">
        <Opt off={h.kind === 'stream'} onPick={() => { onClose(); void h.save().catch(fail) }}
          title="Keep it in the Brain: it opens like this on any browser">Save</Opt>
        <Opt off={!h.savedAt} onPick={() => { onClose(); void h.restoreSaved().catch(fail) }}>Restore saved</Opt>
        <Opt off={!h.canUndo()} onPick={() => { onClose(); h.undo() }}>Undo</Opt>
        <Opt onPick={() => { onClose(); h.reset() }}>Reset</Opt>
      </div>
      {h.kind !== 'stream' && (
        /* THE PLACE'S DEFAULT LOOK (#188: "each place sets a default, and any
           zone can override it"): every zone without a look of its own. */
        <AppearancePicker title="Look for every zone here" value={readAppearance(h.arr.appearance, DEFAULT_APPEARANCE)}
          onChange={(a) => h.edit((x) => ({ ...x, appearance: a }))}
          onReset={() => h.edit(({ appearance: _gone, ...x }) => x, "This place takes Mentis's quiet look again.")}
          isDefault={!h.arr.appearance} resetLabel={["Back to Mentis's quiet look", "Mentis's quiet look"]} />
      )}
      <Sec>Layouts</Sec>
      {/* THE BUILT-IN LAYOUTS (P12): one sets Home and the conversation view
          together; read-only, so each is always there to start from again. */}
      {(lib?.presets ?? []).map((p: Preset) => {
        const isDefault = lib?.defaults[place] === p.id
        return (
          <div key={p.id} className="wk-layout" data-layout={p.name} data-builtin={p.id}>
            <Opt onPick={() => { onClose(); void usePreset(p).catch(fail) }}
              title={`${p.says}. Sets Home and the conversation view; change it and Save as a layout to keep your own`}>{p.name}</Opt>
            <button className="wk-mini" aria-pressed={isDefault} title={isDefault ? `The default for ${placeWords}: click to clear` : `Start ${placeWords} from it`}
              onClick={() => void setDefault(place, isDefault ? null : p.id).catch(fail)}>{isDefault ? '✓ Default' : 'Make default'}</button>
            <span className="wk-mini wk-builtin" title="Built in: it cannot be changed or deleted. Save as a layout keeps your own copy.">Built in</span>
          </div>
        )
      })}
      {usable.map((l: Named) => {
        const isDefault = lib?.defaults[place] === l.id
        return (
          <div key={l.id} className="wk-layout" data-layout={l.name}>
            <Opt onPick={() => { onClose(); h.apply(l) }} title="Use this layout here: its zones and what each shows, nothing it held">{l.name}</Opt>
            <button className="wk-mini" aria-pressed={isDefault} title={isDefault ? `The default for ${placeWords}: click to clear` : `Start ${placeWords} from it`}
              onClick={() => void setDefault(place, isDefault ? null : l.id).catch(fail)}>{isDefault ? '✓ Default' : 'Make default'}</button>
            <button className="wk-mini" aria-label={`Delete the layout ${l.name}`} title="Delete this layout" onClick={() => void deleteNamed(l.id).catch(fail)}>{'✕'}</button>
          </div>
        )
      })}
      {naming === null ? (
        <Opt onPick={() => setNaming('')}>Save as a layout&hellip;</Opt>
      ) : (
        <form className="wk-name" onSubmit={(e) => {
          e.preventDefault()
          const name = naming.trim()
          if (!name) return
          setNaming(null)
          void saveNamed(name, h.arr).then((l) => nav.toast({ text: `Saved the layout "${l.name}": its zones and what each shows, never what they held.` }), fail)
        }}>
          <input autoFocus aria-label="Layout name" placeholder="Layout name…" value={naming} maxLength={80}
            onChange={(e) => setNaming(e.target.value)} onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); setNaming(null) } }} />
          <button type="submit" className="wk-mini" disabled={!naming.trim()}>Save</button>
        </form>
      )}
      {kind === 'workspace' && (
        <Opt
          onPick={() => {
            onClose()
            const tree = treeOf(workspace.arr, 'this-post') ?? workspace.arr.tree
            openSketch({
              tree,
              onApply: (newTree: Node, leftover: Zone[]) => {
                workspace.edit((a) => withTree(a, 'this-post', newTree), 'Sketched a new layout.')
                if (leftover.length) {
                  onLeftover?.(leftover)
                  // TODO(integrator): float leftover zones using focus model (Arr.focus)
                }
              },
            })
          }}
          title="Draw straight lines to divide regions; click lines to erase"
        >
          Sketch a layout&hellip;
        </Opt>
      )}
      {lib?.unreadable && <p className="wk-note">{lib.unreadable}</p>}
    </>
  )
}

export function ArrangeSheet({ onClose, onLeftover }: { onClose: () => void; onLeftover?: (zones: Zone[]) => void }) {
  const selected = useSelection()
  const shown = useSelectionShown()
  const mode = useSyncExternalStore(onObjectsOpen, objectsOpen)
  return (
    <div className="wk-arrange" data-sheet="arrange">
      <PlaceRows h={workspace} onClose={onClose} kind="workspace" onLeftover={onLeftover} />
      <Sec>Preferences</Sec>
      <Opt onPick={() => setObjectsOpen(mode === 'over' ? 'aside' : 'over')}
        title="Mixed: replies open beside, objects open over the arrangement">
        Objects open: {mode === 'over' ? 'over the arrangement' : 'beside This post'}
      </Opt>
      <Opt onPick={() => { onClose(); nav.toast({ text: 'Drag any boundary to give room. Split a zone with its icons; drag a divider closed to merge. Keep… puts an object where you choose; drag a card onto a zone to move it. Save keeps the arrangement in the Brain.' }) }}>
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
