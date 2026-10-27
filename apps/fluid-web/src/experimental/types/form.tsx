/* EXPERIMENTAL: form -- fields a person fills in, declared one per line.
   The author says what each field MEANS (kind, label, required, choices,
   range, unit, when it applies); the renderer decides how it looks, checks
   it mechanically and keeps what the person typed as state. The Markdown
   keeps only the defaults.

   A FORM IN A POST WITH A UNIQUE name= IS KEPT BY MENTIS (../answers.ts):
   each field is saved when it is finished, under the person's name, and
   Done and Send back hand the answers over through the server. Any other
   form -- a draft, the gallery, a post's form with no usable name -- keeps
   what is typed in the tab, and a posted one says why it is not saved. */
import { useEffect, useId, useState, type ReactNode } from 'react'
import type { Help, MenuGroup, TypeDef } from '../api'
import { q } from '../util'
import './data.css'
import { formSpec, type Field, type Val } from '../spec/form'
import { evaluate, same, typed, valueOf, type FormState } from '../spec/fill'
import * as A from '../answers'
import { atField, History, KeptFoot, KeptNotices, OwnWords, shownVal, useKept, wordsLines } from './kept'

/* ------------------------------------------------------------ line reader */

/** Write a value back the way an author would: bare if it can be, quoted if not. */
const tok = (s: string) => (/^[^\s",=]+$/.test(s) ? s : q(s))

/* The value rules (visibility, problems, typed values) are the shared fill
   rules in ../spec/fill.ts, which the server runs too. */

/** What a form's state is when Mentis keeps it: the values, and who set them. */
type Held = FormState & { durable?: A.Durable }

/* ------------------------------------------------------------ the surface */

function FormView({ data: fields, attrs: a, state, set, mode, help, menu }: {
  data: Field[]; attrs: Record<string, string>; state: FormState | undefined; set: (s: FormState | undefined) => void; mode: 'inline' | 'pin'
  help: Help; menu?: (g: MenuGroup[]) => void
}) {
  /* Whether the person has pressed Done: only then are "Required." shown as
     problems rather than as a quiet reminder. View-only, so not kept as state. */
  const [tried, setTried] = useState(false)
  const [history, setHistory] = useState(false)
  /* Element ids unique to this copy: the same form may be drawn inline and pinned at once. */
  const uid = useId()
  const key = help.key
  const { found, e, why } = useKept(help, a, 'form')

  /* Refused by the server after something was typed: keep it, in the tab. */
  useEffect(() => {
    if (found?.cannot && Object.keys(found.drafts).length) {
      set({ values: { ...(state?.values ?? {}), ...found.drafts } })
      found.drafts = {}
    }
  }, [found, found?.cannot, set, state])

  const value = (f: Field): Val => (e ? A.shownValue(e, f.id, f.init) : valueOf(f, state))
  const now: FormState = e ? { values: Object.fromEntries(fields.map((f) => [f.id, value(f)])) } : state ?? {}
  const s = e?.set
  /* A field in conflict has no one value to check: what is wrong with it is
     the conflict, said at the field, and Done is refused by the server for it. */
  const ev = evaluate(fields, now)
  const shown = ev.shown
  const problems = ev.problems.filter((p) => !s?.fields[p.field]?.conflict)
  const bad = new Map(problems.map((p) => [p.field, p.msg]))
  const gone = !!s?.source_deleted

  /* History is asked for, from the ⋯ menu; said on every draw. */
  menu?.(e && s ? [{ label: 'Answers', items: [{ label: 'History…', onSelect: () => setHistory(true) }] }] : [])

  /** A value changed; `finished` when the field is done with (a choice, a blur). */
  const put = (f: Field, v: Val, finished: boolean) => {
    if (e) {
      A.draft(key, f.id, v)
      if (finished) void A.finish(key, f.id, f.init)
      return
    }
    const values = { ...(state?.values ?? {}) }
    if (same(v, f.init)) delete values[f.id]
    else values[f.id] = v
    // Any change after submitting means it is no longer what was submitted.
    set(Object.keys(values).length ? { values } : undefined)
  }
  const done = (f: Field) => { if (e) void A.finish(key, f.id, f.init) }
  const enter = (f: Field) => (ev: React.KeyboardEvent) => { if (ev.key === 'Enter') done(f) }

  const control = (f: Field) => {
    const v = value(f)
    const id = `${uid}-${f.id}`
    /* Nothing is typed over answers that have not been read yet. */
    const off = gone || (!!e && !e.read)
    switch (f.kind) {
      case 'textarea':
        return <textarea id={id} disabled={off} className="rb-form-input rb-form-area" value={String(v)} onChange={(ev) => put(f, ev.target.value, false)} onBlur={() => done(f)} />
      case 'number':
        return (
          <span className="rb-form-num">
            <input id={id} disabled={off} className="rb-form-input" type="text" inputMode="decimal" value={String(v)} onChange={(ev) => put(f, ev.target.value, false)} onBlur={() => done(f)} onKeyDown={enter(f)} />
            {f.unit && <span className="rb-muted">{f.unit}</span>}
          </span>
        )
      case 'date':
        return <input id={id} disabled={off} className="rb-form-input" type="date" value={String(v)} min={f.min} max={f.max} onChange={(ev) => put(f, ev.target.value, false)} onBlur={() => done(f)} onKeyDown={enter(f)} />
      case 'select':
        return (
          <select id={id} disabled={off} className="rb-form-input" value={String(v)} onChange={(ev) => put(f, ev.target.value, true)}>
            <option value="">— choose —</option>
            {f.choices.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        )
      case 'radio':
        return (
          <span className="rb-form-choices" role="radiogroup" aria-labelledby={id + '-l'}>
            {f.choices.map((c) => (
              <label key={c}>
                <input type="radio" disabled={off} name={id} checked={v === c} onChange={() => put(f, c, true)} /> {c}
              </label>
            ))}
            {!f.required && v !== '' && !off && <button className="btn quiet" onClick={() => put(f, '', true)}>clear</button>}
          </span>
        )
      case 'multi': {
        const arr = v as string[]
        return (
          <span className="rb-form-choices" role="group" aria-labelledby={id + '-l'}>
            {f.choices.map((c) => (
              <label key={c}>
                <input
                  type="checkbox"
                  disabled={off}
                  checked={arr.includes(c)}
                  // keep the declared order of choices, whatever order they were ticked in
                  onChange={(ev) => put(f, f.choices.filter((x) => (x === c ? ev.target.checked : arr.includes(x))), true)}
                /> {c}
              </label>
            ))}
          </span>
        )
      }
      case 'checkbox':
        return (
          <label className="rb-form-tick">
            <input id={id} disabled={off} type="checkbox" checked={v === true} onChange={(ev) => put(f, ev.target.checked, true)} /> {f.label}
          </label>
        )
      default:
        return <input id={id} disabled={off} className="rb-form-input" type="text" value={String(v)} onChange={(ev) => put(f, ev.target.value, false)} onBlur={() => done(f)} onKeyDown={enter(f)} />
    }
  }

  const rows: ReactNode[] = []
  let lastSection: string | undefined
  fields.forEach((f) => {
    if (f.section !== lastSection && f.section !== undefined) rows.push(<div key={'s' + f.id} className="rb-form-section">{f.section}</div>)
    lastSection = f.section
    if (!shown[f.id]) return
    const p = bad.get(f.id)
    const loud = p && (tried || !/^(Required|Must be ticked|Choose at least one)\.$/.test(p))
    const changed = e ? !!s?.fields[f.id] || f.id in e.drafts : !same(valueOf(f, state), f.init)
    const k = atField(e, key, f.id)
    rows.push(
      <div key={f.id} className={'rb-form-field' + (changed && !e ? ' rb-form-changed' : '')} data-field={f.id} title={k.who ?? undefined}>
        <label id={`${uid}-${f.id}-l`} htmlFor={`${uid}-${f.id}`} className="rb-form-label">
          {f.kind === 'checkbox' ? '' : f.label}
          {f.required && <span className="rb-form-req" title="required"> *</span>}
          {k.mark}
        </label>
        <div className="rb-form-ctl">
          {control(f)}
          {f.hint && <div className="rb-muted">{f.hint}</div>}
          {p && <div className={loud ? 'rb-form-problem' : 'rb-muted'}>{p}</div>}
          {k.says}
          {k.who && <div className="rb-form-who">{k.who}</div>}
        </div>
      </div>,
    )
  })

  const submitLabel = a.submit ?? (e ? 'Done' : 'Mark as ready')
  const pressDone = async () => {
    setTried(true)
    if (problems.length) return
    if (!e) { set({ values: state?.values ?? {}, submitted: true }); return }
    if (await A.flush(key, Object.fromEntries(fields.map((f) => [f.id, f.init])))) await A.markReady(key)
  }
  return (
    <div className={'rb-form' + (mode === 'pin' ? ' rb-form-pin' : '')} data-saved={e ? 'mentis' : 'tab'}>
      <KeptNotices e={e} why={why} blockKey={key} />
      {rows}
      {e && <OwnWords e={e} blockKey={key} labelOf={(id) => fields.find((f) => f.id === id)?.label ?? id} />}
      {e ? <KeptFoot e={e} blockKey={key} label={submitLabel} onDone={() => void pressDone()} /> : (
        <div className="rb-form-foot rb-row">
          <span className="rb-grow" />
          <button className="btn primary" onClick={() => void pressDone()}>{submitLabel}</button>
        </div>
      )}
      {tried && problems.length > 0 && (
        <ul className="rb-form-list">
          {problems.map((p) => <li key={p.field}>{p.label}: {p.msg}</li>)}
        </ul>
      )}
      {!e && state?.submitted && (
        <p className="rb-ok rb-form-done">
          Marked “{submitLabel}”. Nothing has been sent: use “Send back to agent…” above to hand it over. Changing a value un-marks it.
        </p>
      )}
      {history && e && <History blockKey={key} fields={fields.map((f) => ({ id: f.id, label: f.label }))} onClose={() => setHistory(false)} />}
    </div>
  )
}

/* ---------------------------------------------------------------- the type */

export const form: TypeDef<Field[], Held> = {
  ...formSpec,
  Rich: (p) => <FormView {...p} />,
  readable(fields, a, s) {
    const { shown, problems } = evaluate(fields, s)
    const bad = new Map(problems.map((p) => [p.field, p.msg]))
    const d = s?.durable
    const out: string[] = []
    if (a.title) out.push(`title: ${q(a.title)}`)
    out.push(`submit button: ${q(a.submit ?? (d ? 'Done' : 'Mark as ready'))} (${a.submit ? 'declared' : 'not declared; the renderer’s wording'})`)
    out.push(d ? 'answers: kept by Mentis, each under the name of whoever gave it' : 'answers: kept in this tab only')
    out.push('fields (each declaration as written, then its value now):')
    let lastSection: string | undefined
    for (const f of fields) {
      if (f.section !== lastSection && f.section !== undefined) out.push(`## ${f.section}`)
      lastSection = f.section
      const decl = [`${f.id}: ${f.kind} ${q(f.label)}`]
      if (f.required) decl.push('required')
      if (f.choices.length) decl.push('choices=' + f.choices.map(tok).join(','))
      if (f.min !== undefined) decl.push(`min=${f.min}`)
      if (f.max !== undefined) decl.push(`max=${f.max}`)
      if (f.unit !== undefined) decl.push(`unit=${tok(f.unit)}`)
      if (f.default !== undefined) decl.push(`default=${f.kind === 'multi' ? (f.init as string[]).map(tok).join(',') : tok(f.default)}`)
      if (f.when) decl.push(`when=${tok(f.when.field)}${f.when.values.length ? '=' + f.when.values.map(tok).join(',') : ''}`)
      if (f.hint !== undefined) decl.push(`hint=${q(f.hint)}`)
      out.push('- ' + decl.join(' '))
      const v = valueOf(f, s)
      const from = d?.unsaved.includes(f.id) ? ' (typed here, not saved yet)' : d?.failed.includes(f.id) ? ' (not saved: the save failed)'
        : d?.by[f.id] ? ` (answered by ${d.by[f.id]})` : ' (entered by the person)'
      if (d?.conflicts[f.id]) out.push(`    now: two answers disagree: ${d.conflicts[f.id].map((c) => `${shownVal(c.value)} by ${c.by}`).join('; ')}`)
      else if (!shown[f.id]) out.push(`    now: not asked (its condition is not met), so it is left out of the values${same(v, f.init) ? '' : `; a value is still held: ${shownVal(v)}`}`)
      else out.push(`    now: ${shownVal(v)}${same(v, f.init) && !d?.by[f.id] ? (f.default !== undefined ? ' (the default)' : '') : from}`)
      if (bad.has(f.id)) out.push(`    problem: ${bad.get(f.id)}`)
    }
    const stray = Object.keys(s?.values ?? {}).filter((k) => !fields.some((f) => f.id === k))
    if (stray.length) out.push(`values held for fields no longer declared: ${stray.map((k) => `${k} = ${shownVal(s!.values![k])}`).join('; ')}`)
    out.push(problems.length ? `status: ${problems.length} problem(s); not valid` : 'status: valid')
    out.push(...wordsLines(d))
    if (d) {
      if (d.sourceDeleted) out.push('source deleted: the answers are kept as history; no new answers are taken')
      out.push(`saved: ${d.status || 'nothing answered yet'}`)
    } else out.push(`submitted by the person: ${s?.submitted ? 'yes (marked ready; nothing was sent)' : 'no'}`)
    return out.join('\n')
  },
  handoff(fields, _a, s) {
    const { shown, problems } = evaluate(fields, s)
    const values: Record<string, unknown> = {}
    for (const f of fields) if (shown[f.id]) values[f.id] = typed(f, valueOf(f, s))
    return {
      form_values: values,
      form_valid: problems.length === 0,
      form_problems: problems.map((p) => `${p.field} (${p.label}): ${p.msg}`),
      form_not_asked: fields.filter((f) => !shown[f.id]).map((f) => f.id),
      form_submitted: !!s?.submitted,
    }
  },
}
