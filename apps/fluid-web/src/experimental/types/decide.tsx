/* EXPERIMENTAL: compare and review -- surfaces a PERSON decides on.

   Both are containers: their sections are ordinary Markdown drawn by
   help.Nested, so a section may hold a chart or a table with its own state.
   The author writes plain `## Heading` lines to divide the body; nothing else
   is new to learn.

   The renderer never judges. Compare keeps the options in the order written,
   computes no score and recommends nothing; every mark and pick is the
   person's. Review records ticks, comments and a decision as STATE only: it
   establishes nothing in Mentis, it only prepares what Send back hands over. */
import './media.css'
import { useId, useState } from 'react'
import type { Help, TypeDef } from '../api'
import { q } from '../util'
import { FENCE, compareSpec, reviewSpec, type CmpData, type RevData } from '../spec/decide'

/* ------------------------------------------------- shared: sections, text */

const hasFence = (s: string) => /^ {0,3}(`{3,}|~{3,})\s*\S/m.test(s)

/** A section in plain text for the degraded form: prose quoted, each marked
    block replaced by a pointer, then the blocks' own readable forms (with
    their state). A fence whose type isn't known stays verbatim. */
function sectionReadable(src: string, scope: string, help: Help): string[] {
  const parts = src.trim() ? help.nestedReadable(src, scope) : ''
  const known = new Set([...parts.matchAll(/^\[(\S+) (?:v1 --|-- not shown)/gm)].map((m) => m[1]))
  const out: string[] = []
  let fence: { ch: string; n: number; hide: boolean } | null = null
  for (const line of src.split('\n')) {
    const m = FENCE.exec(line)
    if (fence) {
      if (!fence.hide) out.push('> ' + line)
      if (m && m[1][0] === fence.ch && m[1].length >= fence.n && !m[2].trim()) fence = null
      continue
    }
    if (m) {
      const lang = m[2].trim().split(/\s+/)[0]
      fence = { ch: m[1][0], n: m[1].length, hide: known.has(lang) }
      out.push(fence.hide ? `> [${lang} block: its readable form is below]` : '> ' + line)
      continue
    }
    out.push('> ' + line)
  }
  if (parts) out.push('marked blocks in it, in their readable form (current state included):', parts)
  return out
}

/** Only the states that the person changed, from the nested parts' handoffs. */
const changedParts = (src: string, scope: string, help: Help) =>
  help.nestedHandoff(src, scope)
    .map((p) => p as Record<string, unknown>)
    .filter((p) => p.current_state !== null)
    .map((p) => ({ type: p.type, block_key: p.block_key, current_state: p.current_state }))

/* ------------------------------------------------------------------ compare */

type Mark = '+' | '-' | '?'
type CmpState = { pick?: string[]; marks?: Record<string, Record<string, Mark>>; notes?: Record<string, string> }

const MARKS: (Mark | '')[] = ['', '+', '-', '?']
const markText = (m: Mark | '' | undefined) => (m === '+' ? '+' : m === '-' ? '−' : m === '?' ? '?' : '·')
const markSays = { '+': 'for', '-': 'against', '?': 'unsure', '': 'not marked' }
const norm = (l: string) => l.trim().replace(/\s+/g, ' ')

export const compare: TypeDef<CmpData, CmpState> = {
  ...compareSpec,
  Rich({ data, attrs: a, state, set, help, mode }) {
    const [diff, setDiff] = useState(false)
    const how = a.choose ?? 'none'
    const pick = state?.pick ?? []
    const put = (s: CmpState) => {
      const clean: CmpState = {}
      if (s.pick?.length) clean.pick = s.pick
      const marks = Object.fromEntries(Object.entries(s.marks ?? {}).filter(([, v]) => Object.keys(v).length))
      if (Object.keys(marks).length) clean.marks = marks
      if (s.notes && Object.keys(s.notes).length) clean.notes = s.notes
      set(Object.keys(clean).length ? clean : undefined)
    }
    const togglePick = (name: string) => {
      const on = pick.includes(name)
      put({ ...state, pick: how === 'one' ? (on ? [] : [name]) : on ? pick.filter((x) => x !== name) : [...pick, name] })
    }
    const cycle = (opt: string, crit: string) => {
      const now = state?.marks?.[opt]?.[crit] ?? ''
      const next = MARKS[(MARKS.indexOf(now) + 1) % MARKS.length]
      const row = { ...(state?.marks?.[opt] ?? {}) }
      if (next) row[crit] = next
      else delete row[crit]
      put({ ...state, marks: { ...(state?.marks ?? {}), [opt]: row } })
    }
    const note = (opt: string, v: string) => {
      const notes = { ...(state?.notes ?? {}) }
      if (v) notes[opt] = v
      else delete notes[opt]
      put({ ...state, notes })
    }
    /* "Show differences": a line appears in every plain option, in some, or
       only here. It describes the text; it does not weigh it. */
    const plain = data.options.filter((o) => !hasFence(o.text))
    const canDiff = plain.length >= 2
    const count = new Map<string, number>()
    for (const o of plain) for (const l of new Set(o.text.split('\n').map(norm).filter(Boolean))) count.set(l, (count.get(l) ?? 0) + 1)
    const lineClass = (l: string) => {
      const n = count.get(norm(l)) ?? 0
      return n >= plain.length ? 'rb-cmp-same' : n === 1 ? 'rb-cmp-only' : 'rb-cmp-some'
    }
    return (
      <div className={'rb-cmp' + (mode === 'pin' ? ' rb-cmp-pin' : '')}>
        <p className="rb-muted">
          Options in the order written. Nothing here is scored, ranked or recommended; every mark{how !== 'none' ? ' and pick' : ''} is yours.
        </p>
        {data.intro && <help.Nested src={data.intro} scope={`${help.key}/intro`} />}
        <div className="rb-row">
          <button className="btn quiet" aria-pressed={diff} disabled={!canDiff} onClick={() => setDiff(!diff)}>
            {diff ? 'Hide differences' : 'Show differences'}
          </button>
          {!canDiff && <span className="rb-muted">Differences need at least two options written as plain text.</span>}
          {diff && (
            <span className="rb-muted">
              <span className="rb-cmp-only">only in this option</span> · <span className="rb-cmp-some">in some</span> · <span className="rb-cmp-same">in all</span>
            </span>
          )}
        </div>
        <div className="rb-cmp-cols">
          {data.options.map((o, i) => (
            <section key={o.name + i} className={'rb-cmp-col' + (pick.includes(o.name) ? ' rb-cmp-picked' : '')}>
              <header className="rb-row">
                <b>{o.name}</b>
                <span className="rb-grow" />
                {how !== 'none' && (
                  <label className="rb-cmp-pick">
                    <input type={how === 'one' ? 'radio' : 'checkbox'} checked={pick.includes(o.name)} onChange={() => togglePick(o.name)} /> my pick
                  </label>
                )}
              </header>
              {diff && !hasFence(o.text) ? (
                <div className="rb-cmp-diff">
                  {o.text.split('\n').map((l, n) => (l.trim() ? <div key={n} className={lineClass(l)}>{l}</div> : <br key={n} />))}
                </div>
              ) : (
                <>
                  {diff && <p className="rb-muted">Not compared line by line: this option contains a marked block.</p>}
                  <help.Nested src={o.text} scope={`${help.key}/${i}`} />
                </>
              )}
              <div className="rb-lbl">Your note on {o.name}</div>
              <textarea className="rb-img-note" value={state?.notes?.[o.name] ?? ''} onChange={(e) => note(o.name, e.target.value)} />
            </section>
          ))}
        </div>
        {data.criteria.length > 0 && (
          <div className="rb-cmp-matrix">
            <div className="rb-lbl">Your marks: click a cell to cycle + (for), − (against), ? (unsure), · (not marked). Nothing is totalled.</div>
            <table>
              <thead>
                <tr>
                  <th>criterion</th>
                  {data.options.map((o, i) => <th key={i}>{o.name}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.criteria.map((cr) => (
                  <tr key={cr}>
                    <th>{cr}</th>
                    {data.options.map((o, i) => {
                      const m = state?.marks?.[o.name]?.[cr] ?? ''
                      return (
                        <td key={i}>
                          <button
                            className={'btn quiet rb-cmp-mark rb-cmp-m' + (m === '+' ? 'p' : m === '-' ? 'm' : m === '?' ? 'q' : 'n')}
                            aria-label={`${o.name}, ${cr}: ${markSays[m]}. Click to change.`}
                            onClick={() => cycle(o.name, cr)}
                          >
                            {markText(m)}
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {how !== 'none' && (
          <p className="rb-cmp-summary">
            Your pick: {pick.length ? pick.join(', ') : '(none yet)'}
          </p>
        )}
      </div>
    )
  },
  readable(d, a, s, help) {
    const out = a.title ? [`title: ${q(a.title)}`] : []
    out.push(`choose: ${a.choose ?? 'none'}${a.choose ? '' : ' (default)'}`)
    out.push(`criteria: ${d.criteria.length ? d.criteria.map((x) => q(x)).join(', ') : '(none)'}`)
    out.push('Options are in the order written; the renderer scored and recommended nothing.')
    if (d.intro) out.push('intro:', ...sectionReadable(d.intro, `${help.key}/intro`, help))
    d.options.forEach((o, i) => {
      out.push(`option ${i + 1}: ${q(o.name)}`)
      out.push(...sectionReadable(o.text, `${help.key}/${i}`, help))
      out.push(`  note: ${s?.notes?.[o.name] ? q(s.notes[o.name]) : '(none)'}`)
    })
    if (d.criteria.length) {
      out.push('marks (the person’s; + for, − against, ? unsure, · not marked):')
      out.push('| criterion | ' + d.options.map((o) => o.name).join(' | ') + ' |')
      out.push('|' + ' --- |'.repeat(d.options.length + 1))
      d.criteria.forEach((cr) => out.push(`| ${cr} | ` + d.options.map((o) => markText(s?.marks?.[o.name]?.[cr])).join(' | ') + ' |'))
    }
    if (a.choose && a.choose !== 'none') out.push(`picked: ${s?.pick?.length ? s.pick.map((x) => q(x)).join(', ') : '(none)'}`)
    return out.join('\n')
  },
  handoff(d, _a, s, help) {
    return {
      options_in_written_order: d.options.map((o) => o.name),
      picked: s?.pick ?? [],
      marks: s?.marks ?? {},
      notes: s?.notes ?? {},
      renderer_judgement: 'none (nothing scored, ranked or recommended)',
      changed_parts: d.options.flatMap((o, i) => changedParts(o.text, `${help.key}/${i}`, help)),
    }
  },
}

/* ------------------------------------------------------------------- review */

type RevState = {
  checks?: Record<number, boolean>
  checkNotes?: Record<number, string>
  comment?: string
  decision?: string
  reason?: string
}

export const REVIEW_NOTHING_CHANGES = 'Deciding here changes nothing in Mentis.'
export const REVIEW_ONLY_DRAFT_DETAIL = 'Your ticks, comment and decision exist only in this tab. “Send back to agent…” puts them in a draft that you choose whether to post.'
const ticksNow = (d: RevData, s: RevState | undefined) => d.checks.map((c, i) => (s?.checks && i in s.checks ? s.checks[i] : c.checked))
const reasonMissing = (d: RevData, s: RevState | undefined) =>
  !!s?.decision && d.needReason.includes(s.decision) && !(s.reason ?? '').trim()

function revSummary(d: RevData, s: RevState | undefined) {
  const t = ticksNow(d, s).filter(Boolean).length
  const parts = [`${t} of ${d.checks.length} checks ticked`]
  parts.push(s?.decision ? `decision: ${s.decision}` : 'no decision yet')
  if (s?.decision) parts.push(reasonMissing(d, s) ? 'reason required but not written' : (s.reason ?? '').trim() ? 'reason given' : 'no reason given')
  return parts.join(' · ')
}

export const review: TypeDef<RevData, RevState> = {
  ...reviewSpec,
  Rich({ data: d, state, set, help }) {
    const ticks = ticksNow(d, state)
    const put = (s: RevState) => {
      const clean: RevState = {}
      if (s.checks && Object.keys(s.checks).length) clean.checks = s.checks
      if (s.checkNotes && Object.keys(s.checkNotes).length) clean.checkNotes = s.checkNotes
      if (s.comment) clean.comment = s.comment
      if (s.decision) clean.decision = s.decision
      if (s.reason) clean.reason = s.reason
      set(Object.keys(clean).length ? clean : undefined)
    }
    const tick = (i: number, v: boolean) => {
      const checks = { ...(state?.checks ?? {}) }
      if (v === d.checks[i].checked) delete checks[i]
      else checks[i] = v
      put({ ...state, checks })
    }
    const checkNote = (i: number, v: string) => {
      const checkNotes = { ...(state?.checkNotes ?? {}) }
      if (v) checkNotes[i] = v
      else delete checkNotes[i]
      put({ ...state, checkNotes })
    }
    const [noteOpen, setNoteOpen] = useState<Record<number, boolean>>({})
    const radioId = useId()
    const missing = reasonMissing(d, state)
    return (
      <div className="rb-rev">
        <details className="rb-disclosure rb-rev-notice">
          <summary><b>{REVIEW_NOTHING_CHANGES}</b></summary>
          <div className="rb-disclosure-body">{REVIEW_ONLY_DRAFT_DETAIL}</div>
        </details>
        {d.intro && <help.Nested src={d.intro} scope={`${help.key}/intro`} />}
        <div className="rb-lbl">Material under review</div>
        <div className="rb-rev-material">
          <help.Nested src={d.material} scope={`${help.key}/material`} />
        </div>
        {d.checks.length > 0 && (
          <>
            <div className="rb-lbl">Checks</div>
            <ul className="rb-rev-checks">
              {d.checks.map((c, i) => (
                <li key={i}>
                  <div className="rb-row">
                    <label className="rb-grow">
                      <input type="checkbox" checked={ticks[i]} onChange={(e) => tick(i, e.target.checked)} /> {c.text}
                    </label>
                    <button className="btn quiet" aria-expanded={!!noteOpen[i] || !!state?.checkNotes?.[i]} onClick={() => setNoteOpen({ ...noteOpen, [i]: !noteOpen[i] })}>
                      {state?.checkNotes?.[i] ? 'note ✎' : 'add note'}
                    </button>
                  </div>
                  {(noteOpen[i] || state?.checkNotes?.[i]) && (
                    <input
                      className="rb-rev-checknote"
                      placeholder={`Note on “${c.text}”`}
                      value={state?.checkNotes?.[i] ?? ''}
                      onChange={(e) => checkNote(i, e.target.value)}
                    />
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
        <div className="rb-lbl">General comment</div>
        <textarea className="rb-img-note" value={state?.comment ?? ''} onChange={(e) => put({ ...state, comment: e.target.value })} />
        <div className="rb-lbl">Decision</div>
        <div className="rb-row rb-rev-decisions" role="radiogroup" aria-label="Decision">
          {d.decisions.map((x) => (
            <label key={x} className={'rb-rev-dec' + (state?.decision === x ? ' rb-rev-dec-on' : '')}>
              <input type="radio" name={`${radioId}-decision`} checked={state?.decision === x} onChange={() => put({ ...state, decision: x })} /> {x}
              {d.needReason.includes(x) && <span className="rb-muted"> (reason required)</span>}
            </label>
          ))}
          {state?.decision && <button className="btn quiet" onClick={() => put({ ...state, decision: undefined })}>clear</button>}
        </div>
        {d.needReason.length > 0 && <p className="rb-muted">Rule: a written reason is required for {d.needReason.join(', ')}.</p>}
        <div className="rb-lbl">Reason</div>
        <textarea
          className={'rb-img-note' + (missing ? ' rb-rev-missing' : '')}
          value={state?.reason ?? ''}
          placeholder={missing ? `A reason is required for “${state?.decision}”.` : 'Why (optional unless required)'}
          onChange={(e) => put({ ...state, reason: e.target.value })}
        />
        {missing && <p className="rb-bad">A reason is required for “{state?.decision}” and hasn't been written yet.</p>}
        <p className="rb-rev-summary">{revSummary(d, state)}</p>
      </div>
    )
  },
  readable(d, a, s, help) {
    const out = a.title ? [`title: ${q(a.title)}`] : []
    out.push(`${REVIEW_NOTHING_CHANGES} ${REVIEW_ONLY_DRAFT_DETAIL}`)
    out.push(`decisions offered: ${d.decisions.join(', ')}${a.decisions ? '' : ' (default)'}`)
    out.push(`reason required for: ${d.needReason.length ? d.needReason.join(', ') : '(none)'}`)
    if (d.intro) out.push('introduction:', ...sectionReadable(d.intro, `${help.key}/intro`, help))
    out.push('material:', ...sectionReadable(d.material, `${help.key}/material`, help))
    const now = ticksNow(d, s)
    out.push('checks:')
    d.checks.forEach((c, i) => {
      out.push(`- [${now[i] ? 'x' : ' '}] ${c.text}${now[i] !== c.checked ? `   (changed; source says ${c.checked ? 'done' : 'open'})` : ''}`)
      if (s?.checkNotes?.[i]) out.push(`    note: ${q(s.checkNotes[i])}`)
    })
    if (!d.checks.length) out.push('(none)')
    out.push(`comment: ${s?.comment ? q(s.comment) : '(none)'}`)
    out.push(`decision: ${s?.decision ?? '(none yet)'}`)
    out.push(`reason: ${s?.reason ? q(s.reason) : '(none)'}${reasonMissing(d, s) ? ' -- REQUIRED for this decision and missing' : ''}`)
    out.push(`summary: ${revSummary(d, s)}`)
    return out.join('\n')
  },
  handoff(d, _a, s, help) {
    const now = ticksNow(d, s)
    return {
      decision: s?.decision ?? null,
      reason: s?.reason ?? null,
      reason_missing: reasonMissing(d, s),
      checks: d.checks.map((c, i) => ({ check: c.text, ticked: now[i], note: s?.checkNotes?.[i] ?? null })),
      comment: s?.comment ?? null,
      summary: revSummary(d, s),
      material_parts_changed: changedParts(d.material, `${help.key}/material`, help),
      effect_in_mentis: 'none; this is a draft handoff only',
    }
  },
}
