/* WHAT EVERY BLOCK MENTIS KEEPS DRAWS AROUND ITS FIELDS (forms build P5a-P5c).

   A form, checklist, editable table or pad in a post, with a unique name=,
   is saved through ../answers.ts. Whatever the block, the same things are
   drawn around what it asks, so the four read alike:

     NOTICES     why it is not saved (then it keeps to the tab), a read that
                 failed, a deleted source, answers on an earlier version of
                 the post with Move;
     AT A FIELD  who set it (an initial when it was somebody else; who and
                 when on hover), a conflict with both values, a save that
                 failed with Try again, one not saved yet;
     OWN WORDS   a box for the person's own words, kept as written, and what
                 an agent has read into them, beside the passage it quotes,
                 unconfirmed until Confirm, Change or Decline (F1);
     THE FOOT    one status line, Send back to the post's author, Done;
     HISTORY     every answer each field has had, and every version of the
                 own words, from the block's ⋯ menu.

   The block draws its own controls; this draws nothing that decides what a
   value means. */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Help } from '../api'
import { q } from '../util'
import './data.css'
import type { Val } from '../spec/form'
import * as A from '../answers'

/** A value as a sentence reads it. */
export const shownVal = (v: Val | unknown) => (typeof v === 'boolean' ? (v ? 'yes (ticked)' : 'no (not ticked)') : Array.isArray(v) ? (v.length ? v.map((x) => q(String(x))).join(', ') : '(none chosen)') : v === '' ? '(empty)' : q(String(v)))

/** One field as the chrome names it. */
export interface Named { id: string; label: string }

/** The kept entry for this block, and why it is not saved (null when it is,
 *  or when the block is not posted). `blocked` is a reason the block's own
 *  fill rules give before anything is sent (a table with no key=). */
export function useKept(help: Help, attrs: Record<string, string>, what: string, blocked?: string | null) {
  const found = A.useAnswers(help.key)
  /* Said on the entry too, so nothing else (the readable text, the ⋯ menu) takes it as kept. */
  if (found && blocked && !found.cannot) found.cannot = blocked
  const e = found && !found.cannot ? found : null
  let why: string | null = null
  if (found) why = blocked ?? found.cannot ?? null
  else if (A.isPosted(help.where))
    why = attrs.name ? `another block in this post also says name=${attrs.name}, so neither can be told apart` : `this ${what} has no name=, which is what lets its answers be kept`
  return { found, e, why }
}

/** Above the fields: why nothing is saved, a failed read, a deleted source, an earlier version. */
export function KeptNotices({ e, why, blockKey, quiet, what = 'form' }: { e: A.Entry | null; why: string | null; blockKey: string; quiet?: boolean; what?: string }) {
  const s = e?.set
  const gone = !!s?.source_deleted
  const earlier = !!s && Object.values(s.fields).some((x) => x.heads.some((h) => h.earlier_version))
  return (
    <>
      {why && (
        <p className={'rb-form-notice' + (quiet ? ' rb-kept-quiet' : '')} role="note">
          <b>Answers here aren't saved:</b> {why}. What you fill in is kept in this tab only, until it is closed or reloaded.
        </p>
      )}
      {e?.readError && <p className="rb-form-notice" role="alert">{e.readError}</p>}
      {gone && (
        <p className="rb-form-notice" role="note">
          <b>Source deleted.</b> The post this is in was deleted. Its answers are kept as history, and no new answers are taken.
        </p>
      )}
      {earlier && !gone && e && (
        <div className="rb-form-notice rb-form-earlier" role="note">
          <b>The {what} changed after you answered.</b> Your answers are kept on the version you gave them against.{' '}
          {e.movePlan ? (
            <>
              Some fields changed{e.movePlan.filter((p) => !p.matches).length ? `: ${e.movePlan.filter((p) => !p.matches).map((p) => p.field).join(', ')} will stay where they are` : ''}.{' '}
              <button className="rb-link" disabled={!!e.busy} onClick={() => void A.move(blockKey, true)}>Move the rest</button>
            </>
          ) : (
            <button className="rb-link" disabled={!!e.busy} onClick={() => void A.move(blockKey)}>Move them to this version</button>
          )}
        </div>
      )}
    </>
  )
}

/** What is drawn at one kept field: who set it, a conflict, a save that failed or has not happened. */
export function atField(e: A.Entry | null, blockKey: string, field: string): { mark: ReactNode; says: ReactNode[]; who: string | null } {
  if (!e) return { mark: null, says: [], who: null }
  const x = e.set?.fields[field]
  const says: ReactNode[] = []
  let mark: ReactNode = null
  let who: string | null = null
  if (x && !x.conflict && x.heads[0]) {
    const h = x.heads[0]
    who = `Set by ${A.aliasOf(h)}, ${A.ago(h.at)}`
    if (e.you && h.by !== e.you)
      mark = <span className="rb-form-by" title={who} aria-label={who}>{A.initialOf(h)}</span>
  }
  if (x?.conflict)
    says.push(
      <div key="c" className="rb-form-conflict" role="alert" data-conflict={field}>
        <b>Two answers disagree:</b>{' '}
        {x.heads.map((h, i) => (
          <span key={h.answer}>{i ? ' and ' : ''}<span className="rb-form-conflict-v">{shownVal(h.value)}</span> ({A.aliasOf(h)}, {A.ago(h.at)})</span>
        ))}. Give a new answer to settle it.
      </div>,
    )
  const failed = e.failed[field]
  if (failed)
    says.push(
      <div key="f" className="rb-form-failed" role="alert">
        {failed.error}{' '}
        <button className="rb-link" onClick={() => void A.retry(blockKey, field)}>Try again</button>{' · '}
        <button className="rb-link" onClick={() => A.discard(blockKey, field)}>Discard</button>
      </div>,
    )
  else if (e.saving[field]) says.push(<div key="s" className="rb-muted rb-form-saving">Saving…</div>)
  else if (field in e.drafts) says.push(<div key="u" className="rb-form-unsaved">Not saved yet</div>)
  return { mark, says, who }
}

/** The foot of a kept block: the one status line, Send back, Done. */
export function KeptFoot({ e, blockKey, label = 'Done', onDone }: { e: A.Entry; blockKey: string; label?: string; onDone: () => void }) {
  const gone = !!e.set?.source_deleted
  const canSendBack = !!e.author && e.author !== e.you
  return (
    <>
      <div className="rb-form-foot rb-row">
        <span className="rb-form-status rb-muted" role="status">{A.statusOf(e)}</span>
        <span className="rb-grow" />
        {canSendBack && (
          <button className="btn" disabled={gone || !!e.busy} onClick={() => void A.sendBack(blockKey)}
            title={`Hand these answers to ${e.authorAlias ?? 'the agent'} to act on now`}>
            Send back to {e.authorAlias ?? 'agent'}
          </button>
        )}
        <button className="btn primary" disabled={gone || !!e.busy} onClick={onDone}>{label}</button>
      </div>
      {e.said && !e.said.ok && <p className="rb-form-failed" role="alert">{e.said.text}</p>}
    </>
  )
}

/** Done for a block with no rules of its own: save what is typed, then mark ready. */
export async function doneWith(blockKey: string, inits: Record<string, Val>) {
  if (await A.flush(blockKey, inits)) await A.markReady(blockKey)
}

/** What a proposal would do, as plain text. */
const proposingText = (p: A.Proposes) => (p.type === 'set-field' ? `set ${p.field} to ${shownVal(p.value)}`
  : p.type === 'add-row' ? `add a row: ${Object.entries(p.row).map(([k, v]) => `${k} ${q(v)}`).join(', ')}`
    : `add a field ${p.field.id} (${p.field.kind})`)

/** The readable text's lines for the own words and what was read into them. */
export function wordsLines(d: A.Durable | undefined): string[] {
  if (!d) return []
  const out: string[] = []
  for (const w of d.words) out.push(`own words, by ${w.by} (kept exactly as written):`, ...w.text.split('\n').map((l) => '> ' + l))
  for (const p of d.proposals) out.push(`read into them by ${p.by}, ${p.state}${p.state === 'pending' ? ' (unconfirmed)' : ''}: ${q(p.excerpt)} -> ${proposingText(p.proposes)}`)
  return out
}

/* ------------------------------------------------------------- history */

/** Every answer each field has had, oldest first, and every version of the
 *  own words: who, what, when. `answeredOnly` lists only fields that have
 *  answers (a table has a field per editable cell). */
export function History({ blockKey, fields, answeredOnly, onClose }: { blockKey: string; fields: Named[]; answeredOnly?: boolean; onClose: () => void }) {
  const e = A.peek(blockKey)
  const asked = useMemo(() => (answeredOnly ? fields.filter((f) => e?.set?.fields[f.id]) : fields), [fields, answeredOnly, e?.set])
  const [got, setGot] = useState<Record<string, A.Head[]> | null>(null)
  const [words, setWords] = useState<A.Words[] | null>(null)
  useEffect(() => {
    void A.historyOf(blockKey, asked.map((f) => f.id)).then(setGot)
    void A.wordsHistory(blockKey).then(setWords)
  }, [blockKey, asked])
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => { if (ev.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="rb-modal" role="dialog" aria-modal="true" aria-label="History of these answers" onClick={onClose}>
      <div className="rb-modal-box rb-form-history" onClick={(ev) => ev.stopPropagation()}>
        <h4>History</h4>
        {!got ? <p className="rb-muted">Reading…</p> : <>
          {!asked.length && <p className="rb-muted">Nothing has been answered.</p>}
          {asked.map((f) => (
            <section key={f.id}>
              <b>{f.label}</b>
              {got[f.id]?.length ? (
                <ul>
                  {got[f.id].map((h) => (
                    <li key={h.answer}>{shownVal(h.value)} <span className="rb-muted">by {A.aliasOf(h)}, {new Date(h.at * 1000).toLocaleString()}</span></li>
                  ))}
                </ul>
              ) : <p className="rb-muted">Never answered.</p>}
            </section>
          ))}
        </>}
        {!!words?.length && (
          <section className="rb-words-history">
            <b>Own words</b>
            <ul>
              {words.map((w) => (
                <li key={w.words}>
                  <span className="rb-words-text">{w.text}</span>{' '}
                  <span className="rb-muted">by {w.by_alias ?? w.by}, {new Date(w.at * 1000).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
        <div className="rb-row"><span className="rb-grow" /><button className="btn" onClick={onClose}>Close</button></div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------- own words */

/** Code points to UTF-16 units: the record counts the one, a string the other. */
function units(text: string, cp: number): number {
  let i = 0, n = 0
  for (const ch of text) { if (n === cp) return i; i += ch.length; n++ }
  return i
}

/** `text` cut at every passage edge, each piece with the passages that cover it. */
function pieces(text: string, spans: { id: string; start: number; end: number }[]) {
  const at = spans.map((s) => ({ ...s, a: units(text, s.start), b: units(text, s.end) }))
  const edges = [...new Set([0, text.length, ...at.flatMap((s) => [s.a, s.b])])].sort((x, y) => x - y)
  const out: { text: string; ids: string[] }[] = []
  for (let k = 0; k + 1 < edges.length; k++) {
    const a = edges[k], b = edges[k + 1]
    if (a === b) continue
    out.push({ text: text.slice(a, b), ids: at.filter((s) => s.a <= a && s.b >= b).map((s) => s.id) })
  }
  return out
}

/** What a proposal would do, in words. */
function proposing(p: A.Proposes, labelOf: (f: string) => string): ReactNode {
  if (p.type === 'set-field') return <>set <b>{labelOf(p.field)}</b> to <b>{shownVal(p.value)}</b></>
  if (p.type === 'add-row') return <>add a row: {Object.entries(p.row).map(([k, v], i) => <span key={k}>{i ? ', ' : ''}{k} <b>{q(v)}</b></span>)}</>
  return <>add a field <b>{p.field.label ?? p.field.id}</b> ({p.field.kind})</>
}

const OUTCOME: Record<string, string> = { confirmed: 'Confirmed', changed: 'Changed', declined: 'Declined' }

/** Change: the value (or the row, or the field) the person would rather. */
function ChangeEditor({ p, onSave, onCancel, busy }: { p: A.Proposal; onSave: (x: { value?: Val; changed_to?: Record<string, unknown> }) => void; onCancel: () => void; busy: boolean }) {
  const pr = p.proposes
  const [v, setV] = useState<Val>(pr.type === 'set-field' ? pr.value : '')
  const [row, setRow] = useState<Record<string, string>>(pr.type === 'add-row' ? { ...pr.row } : {})
  const [fld, setFld] = useState(pr.type === 'add-field' ? { id: pr.field.id, kind: pr.field.kind, label: pr.field.label ?? '' } : { id: '', kind: '', label: '' })
  const save = () => {
    if (pr.type === 'set-field') onSave({ value: v })
    else if (pr.type === 'add-row') onSave({ changed_to: { row } })
    else onSave({ changed_to: { field: { id: fld.id, kind: fld.kind, ...(fld.label ? { label: fld.label } : {}) } } })
  }
  return (
    <div className="rb-prop-change" role="group" aria-label="Change this proposal">
      {pr.type === 'set-field' && (typeof v === 'boolean'
        ? <label className="rb-form-tick"><input type="checkbox" checked={v} onChange={(ev) => setV(ev.target.checked)} /> ticked</label>
        : <input className="rb-form-input" aria-label="Your value" value={Array.isArray(v) ? v.join(', ') : String(v)}
            onChange={(ev) => setV(Array.isArray(pr.value) ? ev.target.value.split(',').map((x) => x.trim()).filter(Boolean) : ev.target.value)} />)}
      {pr.type === 'add-row' && Object.keys(row).map((k) => (
        <label key={k} className="rb-prop-pair">{k} <input className="rb-form-input" value={row[k]} onChange={(ev) => setRow({ ...row, [k]: ev.target.value })} /></label>
      ))}
      {pr.type === 'add-field' && (['id', 'kind', 'label'] as const).map((k) => (
        <label key={k} className="rb-prop-pair">{k} <input className="rb-form-input" value={fld[k]} onChange={(ev) => setFld({ ...fld, [k]: ev.target.value })} /></label>
      ))}
      <div className="rb-row">
        <button className="btn primary" disabled={busy} onClick={save}>Save change</button>
        <button className="btn" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

/** One proposal, beside the passage it quotes. Only the person whose words
 *  it read may answer it; out of date, it may only be declined. */
function ProposalCard({ e, blockKey, p, labelOf, lit, onLight }: {
  e: A.Entry; blockKey: string; p: A.Proposal; labelOf: (f: string) => string; lit: boolean; onLight: (id: string | null) => void
}) {
  const [changing, setChanging] = useState(false)
  const mine = !!e.you && p.for === e.you
  const stale = p.state === 'out of date'
  const busy = e.replying === p.interpretation
  const off = !!e.replying || !!e.set?.source_deleted
  const error = e.replyError?.[p.interpretation]
  return (
    <div className={'rb-prop' + (lit ? ' rb-prop-lit' : '') + (stale ? ' rb-prop-stale' : '')} data-proposal={p.interpretation} data-state={p.state}
      onMouseEnter={() => onLight(p.interpretation)} onMouseLeave={() => onLight(null)} onFocus={() => onLight(p.interpretation)} onBlur={() => onLight(null)}>
      <div className="rb-prop-head">
        <span className="rb-prop-tag">{stale ? 'Out of date' : 'Unconfirmed'}</span>{' '}
        <span className="rb-muted">{p.by_alias ?? p.by}, {A.ago(p.at)}</span>
      </div>
      <blockquote className="rb-prop-quote">{p.excerpt}</blockquote>
      <div className="rb-prop-what">Would {proposing(p.proposes, labelOf)}.</div>
      {stale && p.why_out_of_date && <div className="rb-muted rb-prop-why">{p.why_out_of_date[0].toUpperCase() + p.why_out_of_date.slice(1)}. It can only be declined.</div>}
      {error && <div className="rb-form-failed" role="alert">{error}</div>}
      {mine && (changing ? (
        <ChangeEditor p={p} busy={busy} onCancel={() => setChanging(false)}
          onSave={(x) => void A.reply(blockKey, p, 'change', x).then(() => { if (!A.peek(blockKey)?.replyError?.[p.interpretation]) setChanging(false) })} />
      ) : (
        <div className="rb-row rb-prop-acts">
          {!stale && <button className="btn primary" disabled={off} onClick={() => void A.reply(blockKey, p, 'confirm')}>Confirm</button>}
          {!stale && <button className="btn" disabled={off} onClick={() => setChanging(true)}>Change…</button>}
          <button className="btn" disabled={off} onClick={() => void A.reply(blockKey, p, 'decline')}>Decline</button>
        </div>
      ))}
      {!mine && <div className="rb-muted">Only {p.for === e.author ? e.authorAlias ?? 'its writer' : 'the person whose words these are'} can answer this.</div>}
    </div>
  )
}

/** One person's words, drawn with the passages read into them marked. */
function Marked({ text, spans, lit, gaps }: { text: string; spans: { id: string; start: number; end: number }[]; lit: string | null; gaps?: { start: number; end: number }[] }) {
  const all = [...spans, ...(gaps ?? []).map((g, i) => ({ id: `gap:${i}`, ...g }))]
  return (
    <div className="rb-words-read">
      {pieces(text, all).map((x, i) => {
        const cited = x.ids.filter((id) => !id.startsWith('gap:'))
        const gap = x.ids.some((id) => id.startsWith('gap:'))
        if (!cited.length && !gap) return <span key={i}>{x.text}</span>
        return <mark key={i} className={'rb-words-mark' + (gap ? ' rb-words-gap' : '') + (lit && cited.includes(lit) ? ' rb-words-lit' : '')}
          data-cited={cited.join(' ') || undefined}>{x.text}</mark>
      })}
    </div>
  )
}

/** The own-words area every kept block has: the person's own words in a
 *  large box, kept as written; somebody else's beside them; and what an
 *  agent has read into them, beside the passage each reading quotes. */
export function OwnWords({ e, blockKey, labelOf }: { e: A.Entry; blockKey: string; labelOf: (field: string) => string }) {
  const s = e.set
  const mine = A.mineOf(e)
  const others = (s?.own_words ?? []).filter((w) => w.by !== e.you)
  const proposals = s?.proposals ?? []
  const onMine = proposals.filter((p) => mine && p.words === mine.words)
  const current = new Set((s?.own_words ?? []).map((w) => w.words))
  const earlier = proposals.filter((p) => !current.has(p.words))
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [hovered, setLit] = useState<string | null>(null)
  /* A card answered under the pointer is gone without a pointer leaving it. */
  const lit = proposals.some((p) => p.interpretation === hovered && p.status === 'pending') ? hovered : null
  const [acc, setAcc] = useState<A.Accounting | null | 'reading'>(null)
  const box = useRef<HTMLTextAreaElement>(null)
  const gone = !!s?.source_deleted
  const off = gone || !e.read
  /* The box shows the words as saved, unless something is typed or failed. */
  const text = e.wordsDraft ?? e.wordsSaving?.text ?? e.wordsFailed?.text ?? mine?.text ?? ''
  const reading = !!mine && onMine.length > 0 && !editing && e.wordsDraft === undefined && !e.wordsFailed
  const shown = open || !!mine || e.wordsDraft !== undefined || !!e.wordsFailed
  useEffect(() => { if (editing || (open && !mine)) box.current?.focus() }, [editing, open, mine])
  /* What was asked for is about the words then; new words, ask again. */
  useEffect(() => { setAcc(null) }, [mine?.words])
  const gaps = acc && acc !== 'reading' ? acc.words.find((w) => w.words === mine?.words)?.not_cited : undefined
  const pending = onMine.filter((p) => p.status === 'pending')
  const answered = onMine.filter((p) => p.status !== 'pending')
  const card = (p: A.Proposal) => <ProposalCard key={p.interpretation} e={e} blockKey={blockKey} p={p} labelOf={labelOf} lit={lit === p.interpretation} onLight={setLit} />

  return (
    <section className="rb-words" aria-label="Your own words">
      {!shown && !others.length ? (
        <button className="rb-link rb-words-add" disabled={off} onClick={() => setOpen(true)}>Add your own words…</button>
      ) : <>
        <div className="rb-words-head">
          <b>In your own words</b>
          <span className="rb-muted"> · kept exactly as you write them; anything read into them waits for you to confirm it</span>
        </div>
        {!shown && <button className="rb-link rb-words-add" disabled={off} onClick={() => setOpen(true)}>Add your own words…</button>}
        {shown && (
          <div className={'rb-words-grid' + (pending.length ? ' rb-words-with' : '')}>
            <div className="rb-words-own">
              {reading ? (
                <>
                  <Marked text={mine!.text} spans={onMine.map((p) => ({ id: p.interpretation, ...p.passage }))} lit={lit} gaps={gaps} />
                  <button className="rb-link" disabled={off} onClick={() => setEditing(true)}>Edit your words</button>
                </>
              ) : (
                <textarea ref={box} className="rb-form-input rb-words-box" disabled={off} aria-label="Your own words" placeholder="Write anything the fields don't ask: it is kept exactly as written."
                  value={text} onChange={(ev) => A.draftWords(blockKey, ev.target.value)}
                  onBlur={() => { setEditing(false); void A.finishWords(blockKey) }} />
              )}
              {e.wordsFailed && (
                <div className="rb-form-failed" role="alert">
                  {e.wordsFailed.error}{' '}
                  {e.wordsFailed.text.trim() && <><button className="rb-link" onClick={() => void A.retryWords(blockKey)}>Try again</button>{' · '}</>}
                  <button className="rb-link" onClick={() => A.discardWords(blockKey)}>Discard</button>
                </div>
              )}
              {e.wordsSaving && <div className="rb-muted rb-form-saving">Saving…</div>}
              {e.wordsDraft !== undefined && !e.wordsSaving && <div className="rb-form-unsaved">Not saved yet</div>}
              {mine && <div className="rb-form-who rb-words-who">Saved {A.ago(mine.at)}{mine.replaces.length ? ', a later version' : ''}</div>}
              {mine && (
                <div className="rb-words-acc">
                  {acc === null && <button className="rb-link" onClick={() => { setAcc('reading'); void A.accountingOf(blockKey).then(setAcc) }}>What no proposal quotes</button>}
                  {acc === 'reading' && <span className="rb-muted">Reading…</span>}
                  {acc && acc !== 'reading' && (
                    <div className="rb-words-gaps" role="note">
                      {gaps?.length ? <>Not quoted by any proposal: {gaps.map((g, i) => <span key={i}>{i ? '; ' : ''}“{g.excerpt.trim()}”</span>)}.</> : 'Every passage has been quoted by a proposal.'}{' '}
                      <button className="rb-link" onClick={() => setAcc(null)}>Hide</button>
                    </div>
                  )}
                </div>
              )}
            </div>
            {pending.length > 0 && <div className="rb-words-props" aria-label="Read into your words">{pending.map(card)}</div>}
          </div>
        )}
        {answered.length > 0 && (
          <details className="rb-disclosure rb-props-done">
            <summary>{answered.length} answered</summary>
            <ul>
              {answered.map((p) => (
                <li key={p.interpretation} data-proposal={p.interpretation} data-state={p.state}>
                  <b>{OUTCOME[p.status]}</b>: “{p.excerpt}” → {proposing(p.reply?.changed_to ?? p.proposes, labelOf)} <span className="rb-muted">({p.by_alias ?? p.by})</span>
                </li>
              ))}
            </ul>
          </details>
        )}
        {earlier.length > 0 && (
          <div className="rb-props-earlier">
            <div className="rb-muted">Read from an earlier version of the words:</div>
            {earlier.filter((p) => p.status === 'pending').map(card)}
          </div>
        )}
        {others.map((w) => {
          const theirs = proposals.filter((p) => p.words === w.words)
          return (
            <div key={w.words} className="rb-words-other">
              <div className="rb-muted">{w.by_alias ?? w.by}'s own words, {A.ago(w.at)}</div>
              <Marked text={w.text} spans={theirs.map((p) => ({ id: p.interpretation, ...p.passage }))} lit={lit} />
              {theirs.filter((p) => p.status === 'pending').map(card)}
            </div>
          )
        })}
      </>}
    </section>
  )
}
