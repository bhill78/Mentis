/* THE TWO CHOICES A ZONE'S ⋯ SHEET OFFERS FOR LOOKS (#188: Show; Appearance
 * with Panel and Content set separately). Every zone's sheet mounts them and
 * writes the zone slot's `present` and `appearance` (workspace/Zones.tsx). Each is a row group
 * that fits a choice sheet: compact segmented controls, words where they
 * say what a choice does. */

import type { ReactElement } from 'react'
import { APPEARANCE_PRESETS, PRESENT_MODES, readAppearance, type Appearance, type Fill, type PresentMode } from './types'

const same = (a: Appearance, b: Appearance) => a.panel === b.panel && a.content === b.content && Math.abs(a.opacity - b.opacity) < 0.005

/** SHOW AS: how the zone presents what it holds. */
export function PresentPicker({ mode, onMode }: { mode: PresentMode; onMode: (m: PresentMode) => void }) {
  return (
    <div className="pz-pick" role="group" aria-label="Show as">
      <div className="wk-sec">Show as</div>
      <div className="pz-modes">
        {PRESENT_MODES.map((p) => (
          <button key={p.mode} className={'pz-mode' + (p.mode === mode ? ' on' : '')} role="menuitemradio" aria-checked={p.mode === mode}
            data-mode={p.mode} title={p.says} onClick={() => onMode(p.mode)}>
            <ModeIcon mode={p.mode} />
            <span>{p.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

/** A small drawing of each mode, so the choice is seen, not read (and, in
 *  a zone's head, what it is shown as: C4). */
export function ModeIcon({ mode }: { mode: PresentMode }) {
  const r = (x: number, y: number, w: number, h: number, k?: string) => <rect key={k ?? `${x}${y}`} x={x} y={y} width={w} height={h} rx="1.2" />
  const parts: Record<PresentMode, ReactElement[]> = {
    cards: [r(1, 1, 8, 6), r(11, 1, 8, 9), r(1, 9, 8, 6), r(11, 12, 8, 3)],
    gallery: [r(1, 1, 5, 4), r(7.5, 1, 5, 4), r(14, 1, 5, 4), r(1, 6.5, 5, 4), r(7.5, 6.5, 5, 4), r(14, 6.5, 5, 4), r(1, 12, 5, 3), r(7.5, 12, 5, 3)],
    slides: [r(3, 1, 14, 10), <circle key="a" cx="7" cy="13.5" r="1" />, <circle key="b" cx="10" cy="13.5" r="1" />, <circle key="c" cx="13" cy="13.5" r="1" />],
    list: [r(1, 1.5, 3, 3), r(5.5, 2, 13.5, 2), r(1, 6.5, 3, 3), r(5.5, 7, 13.5, 2), r(1, 11.5, 3, 3), r(5.5, 12, 13.5, 2)],
    focus: [r(1, 1, 12, 14), r(14.5, 1, 4.5, 4), r(14.5, 6, 4.5, 4), r(14.5, 11, 4.5, 4)],
    previews: [r(1, 1, 8.5, 6), r(10.5, 1, 8.5, 9), r(1, 8.5, 8.5, 6.5), r(10.5, 11.5, 8.5, 3.5)],
    across: [r(1, 1, 5.5, 12), r(7.25, 1, 5.5, 12), r(13.5, 1, 5.5, 12), <path key="ar" d="M5 15h10M13 13.8l2 1.2-2 1.2" fill="none" stroke="currentColor" strokeWidth="1" />],
  }
  return <svg className="pz-micon" viewBox="0 0 20 16" aria-hidden="true">{parts[mode]}</svg>
}

const FILL_LABEL: Record<Fill, string> = { transparent: 'Clear', tinted: 'Tinted', solid: 'Solid' }

/** A look in a word or two, for a section menu's one Look row ("Cards ·
 *  by reply · Clear"): the preset it matches, else its panel and content. */
export function lookWords(value: Appearance): string {
  const a = readAppearance(value)
  const preset = APPEARANCE_PRESETS.find((p) => same(p.a, a))
  return preset ? preset.label : a.panel === a.content ? FILL_LABEL[a.panel] : `${FILL_LABEL[a.panel]} panel, ${FILL_LABEL[a.content].toLowerCase()} content`
}

function FillRow({ name, says, value, onPick }: { name: string; says: string; value: Fill; onPick: (f: Fill) => void }) {
  return (
    <div className="pz-arow" role="radiogroup" aria-label={name}>
      <span className="pz-alabel" title={says}>{name}</span>
      <span className="pz-seg">
        {(['transparent', 'tinted', 'solid'] as Fill[]).map((f) => (
          <button key={f} className={f === value ? 'on' : ''} role="radio" aria-checked={f === value} data-fill={f}
            title={`${name}: ${f}`} onClick={() => onPick(f)}>{FILL_LABEL[f]}</button>
        ))}
      </span>
    </div>
  )
}

/** APPEARANCE: the panel and the content, each transparent / tinted /
 *  solid, and how strongly a fill covers the atmosphere. Looks are
 *  presets of the same three values. `onReset` (optional) returns the zone
 *  to its place's default. */
export function AppearancePicker({ value, onChange, onReset, isDefault, resetLabel, title = 'Appearance' }: {
  value: Appearance; onChange: (a: Appearance) => void; onReset?: () => void; isDefault?: boolean
  /** what the reset button says: [to go back, when already there] */
  resetLabel?: [string, string]
  title?: string
}) {
  const a = readAppearance(value)
  const pct = Math.round(a.opacity * 100)
  const covers = a.panel !== 'transparent' || a.content !== 'transparent'
  return (
    <div className="pz-pick pz-appearance" role="group" aria-label={title}>
      <div className="wk-sec">{title}</div>
      <div className="pz-presets">
        {APPEARANCE_PRESETS.map((p) => (
          <button key={p.id} className={'pz-preset' + (same(p.a, a) ? ' on' : '')} data-preset={p.id} aria-pressed={same(p.a, a)}
            title={p.says} onClick={() => onChange(p.a)}>
            <span className={`pz-swatch pz-panel-${p.a.panel} pz-content-${p.a.content}`} aria-hidden="true"><i /><i /></span>
            {p.label}
          </button>
        ))}
      </div>
      <FillRow name="Panel" says="behind the whole zone" value={a.panel} onPick={(panel) => onChange({ ...a, panel })} />
      <FillRow name="Content" says="behind each object in it" value={a.content} onPick={(content) => onChange({ ...a, content })} />
      <label className="pz-arow pz-opacity" title={covers ? 'how much of the atmosphere a fill covers' : 'nothing is filled: opacity has nothing to cover'}>
        <span className="pz-alabel">Opacity</span>
        <input type="range" min={0} max={100} step={5} value={pct} disabled={!covers} aria-label="Opacity"
          onChange={(e) => onChange({ ...a, opacity: Number(e.target.value) / 100 })} />
        <span className="pz-pct">{pct}%</span>
      </label>
      {onReset && (
        <button className="pz-reset" disabled={isDefault} onClick={onReset}>
          {isDefault ? resetLabel?.[1] ?? 'This is the default look' : resetLabel?.[0] ?? 'Back to the default look'}
        </button>
      )}
    </div>
  )
}
