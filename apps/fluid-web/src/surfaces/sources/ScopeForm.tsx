import { useState } from 'react'
import type { Category, Descriptor, Preset, ScopeField, ScopeOptions } from './route'

/* ------------------------------------------------------------------------ *
 * THE SCOPE FORM, RENDERED FROM THE CONNECTOR'S OWN SCHEMA (U5).
 *
 * Nothing here knows what a folder is. A connector's descriptor names its
 * scope fields and its presets; this draws a preset row and, under Custom,
 * one input per field. Folder scope is two pattern lists today; Slack's will
 * be channels and a date window, and the same form draws it.
 *
 * `patterns` fields are the presets' and are edited under Custom. A field the
 * connector marks `option` -- not a pattern list: a Git repository's ref and
 * its recent-commit window -- is a `text` or `number` input that is always
 * shown, because a preset chooses patterns only, and it travels as the
 * scope's `options`. Nothing here knows what either one means. Any other
 * field type is shown as what it is, not as a working control.
 * ------------------------------------------------------------------------ */

export interface ScopeValue {
  preset: string
  include: string[]
  exclude: string[]
  options: ScopeOptions
}

/** The connector's option fields, at their declared defaults. */
export function optionDefaults(d: Descriptor): ScopeOptions {
  const out: ScopeOptions = {}
  for (const f of d.scope_fields)
    if (f.option) out[f.name] = typeof f.default === 'number' || typeof f.default === 'string' ? f.default : ''
  return out
}

export function presetValue(p: Preset, options: ScopeOptions = {}): ScopeValue {
  return { preset: p.id, include: p.include ?? ['*'], exclude: p.exclude ?? [], options }
}

/** Whether two option sets say the same thing. */
export function sameOptions(a: ScopeOptions = {}, b: ScopeOptions = {}): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  return [...keys].every((k) => String(a[k] ?? '') === String(b[k] ?? ''))
}

export function OptionField({ f, value, onChange }: { f: ScopeField; value: string | number | undefined; onChange: (v: string | number) => void }) {
  return (
    <label className="src-field">
      <span className="src-label">{f.label}</span>
      {f.type === 'number' ? (
        <input
          type="number"
          min={f.min}
          max={f.max}
          step={1}
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value === '' ? '' : Math.trunc(Number(e.target.value)))}
        />
      ) : (
        <input value={value ?? ''} onChange={(e) => onChange(e.target.value)} />
      )}
      {f.help && <span className="src-faint">{f.help}</span>}
    </label>
  )
}

/** Which preset these filters are, if any. */
export function presetOf(d: Descriptor, include: string[], exclude: string[]): string {
  const same = (a: string[] | null, b: string[]) =>
    !!a && a.length === b.length && a.every((x, i) => x === b[i])
  const hit = d.presets.find((p) => p.include && same(p.include, include) && same(p.exclude, exclude))
  return hit ? hit.id : 'custom'
}

/** A category is off while all its patterns are excluded, on while none are. */
export function categoryState(c: Category, exclude: string[]): 'off' | 'on' | 'partly excluded' {
  const n = c.patterns.filter((p) => exclude.includes(p)).length
  return n === c.patterns.length ? 'off' : n === 0 ? 'on' : 'partly excluded'
}

/** The exclude list with one category on or off. Other patterns keep their
 *  place; every category that is off has its patterns after them, in the
 *  descriptor's order, so switching back gives the preset's own list. */
export function withCategory(d: Descriptor, exclude: string[], id: string, on: boolean): string[] {
  const cats = (d.categories ?? []).filter((c) => c.id === id || categoryState(c, exclude) !== 'partly excluded')
  const managed = new Set(cats.flatMap((c) => c.patterns))
  const off = cats.filter((c) => (c.id === id ? !on : categoryState(c, exclude) === 'off'))
  return [...exclude.filter((p) => !managed.has(p)), ...off.flatMap((c) => c.patterns)]
}

/** EVIDENCE CATEGORIES (K1/K2): shown for every preset, off by default in
 *  Repository. Off is their patterns, visible in the exclude list; on removes
 *  them, and a preview then asks for a decision before acquiring any. */
export function CategoryToggles({ d, value, onChange }: { d: Descriptor; value: ScopeValue; onChange: (exclude: string[]) => void }) {
  if (!d.categories?.length) return null
  return (
    <fieldset className="src-categories">
      <legend className="src-label">Evidence categories</legend>
      {d.categories.map((c) => {
        const state = categoryState(c, value.exclude)
        return (
          <label key={c.id} className="src-field">
            <input
              type="checkbox"
              aria-label={c.label}
              checked={state === 'on'}
              onChange={(e) => onChange(withCategory(d, value.exclude, c.id, e.target.checked))}
            />{' '}
            <b>{c.label}</b> · {state}
            {state === 'on'
              ? ': not excluded. Anything of it a preview would newly acquire waits for your decision for the whole category, and is not read before it.'
              : state === 'off'
                ? <>: excluded by <code>{c.patterns.join(' ')}</code>, and reported as not selected.</>
                : <>: some of <code>{c.patterns.join(' ')}</code> are excluded.</>}
            <span className="src-faint"> {c.help}</span>
          </label>
        )
      })}
    </fieldset>
  )
}

const lines = (s: string) =>
  s
    .split(/[\n,]/)
    .map((x) => x.trim())
    .filter(Boolean)

export default function ScopeForm({
  descriptor,
  value,
  onChange,
}: {
  descriptor: Descriptor
  value: ScopeValue
  onChange: (v: ScopeValue) => void
}) {
  const [text, setText] = useState<Record<string, string>>({
    include: value.include.join('\n'),
    exclude: value.exclude.join('\n'),
  })
  return (
    <div className="src-scope">
      <div className="src-preset" role="radiogroup" aria-label="What to take">
        {descriptor.presets.map((p) => (
          <button
            key={p.id}
            role="radio"
            aria-checked={value.preset === p.id}
            className={'src-opt' + (value.preset === p.id ? ' on' : '')}
            onClick={() => {
              if (p.include) {
                const v = presetValue(p, value.options)
                setText({ include: v.include.join('\n'), exclude: v.exclude.join('\n') })
                onChange(v)
              } else onChange({ ...value, preset: p.id })
            }}
          >
            {p.label}
            <small>{p.include ? p.include.join(' ') + (p.exclude?.length ? ' − ' + p.exclude.join(' ') : '') : 'your own patterns'}</small>
          </button>
        ))}
      </div>
      <CategoryToggles
        d={descriptor}
        value={value}
        onChange={(exclude) => {
          setText({ ...text, exclude: exclude.join('\n') })
          onChange({ ...value, preset: presetOf(descriptor, value.include, exclude), exclude })
        }}
      />
      {descriptor.scope_fields
        .filter((f) => f.option && ['text', 'number'].includes(f.type))
        .map((f) => (
          <OptionField
            key={f.name}
            f={f}
            value={value.options[f.name] as string | number | undefined}
            onChange={(v) => onChange({ ...value, options: { ...value.options, [f.name]: v } })}
          />
        ))}
      {(value.preset === 'custom' || value.preset === 'repository') &&
        descriptor.scope_fields
          .filter((f) => !f.option && ['patterns', 'text', 'number'].includes(f.type))
          .map((f) =>
          f.type === 'patterns' ? (
            <label key={f.name} className="src-field">
              <span className="src-label">{f.label}</span>
              <textarea
                rows={3}
                value={text[f.name] ?? ''}
                onChange={(e) => {
                  const t = { ...text, [f.name]: e.target.value }
                  setText(t)
                  onChange({
                    preset: 'custom',
                    include: lines(t.include ?? ''),
                    exclude: lines(t.exclude ?? ''),
                    options: value.options,
                  })
                }}
                placeholder={Array.isArray(f.default) ? f.default.join('\n') : ''}
              />
              {f.help && <span className="src-faint">{f.help}</span>}
            </label>
          ) : (
            <p key={f.name} className="src-faint">
              {f.label}: a {f.type} field this connector would ask for.
            </p>
          ),
        )}
      <p className="src-note">
        Patterns: include <code>{value.include.join(' ') || '*'}</code> · exclude{' '}
        <code>{value.exclude.join(' ') || 'none'}</code>. A scope can be revised later; nothing already
        acquired is lost, and material that leaves the scope is never recorded as absent. Exclude always wins:
        nothing inside an excluded folder can be re-included, so exclude the narrower folder instead.
      </p>
    </div>
  )
}
