/* THE DECISION FORM (forms build P9; design revision 3, section 9B).
 *
 * One form for every decision, drawn the same way wherever its post is
 * drawn: Classic's Turn, Fluid's conversation column, thread sheet and full
 * screen, and the Needs You zone. It replaces the two hand-built decision
 * cards (Classic's `Awaited` card and Fluid's Needs You card), and draws
 * through the form chrome every kept block uses (`rb-form`, its fields and
 * its foot), so no view can lose a control.
 *
 * A form is one decision form of several questions (P7), or one ask on its
 * own post -- every decision asked before P7, and every other ask of the
 * owner -- drawn as a one-question form. Each open question offers:
 *
 *   the options the asker stated, lettered in their order, each with what
 *     choosing it leads to; one asking a choice per finding opens those;
 *   your own words, always, as the last alternative;
 *   Withdraw, on a decision: closed unanswered, with your reason.
 *
 * ONE ANSWER ACTION. Choices are a draft until Answer (Decide, Withdraw)
 * sends them: one reply per question chosen, each naming its question, as
 * the cards sent them (../decisions.ts). A question left unchosen stays
 * open. Leave open records nothing.
 *
 * WHAT IS RECORDED IS READ FROM THE RECORD. A choice stays selected while it
 * is sent and until the reread shows it answered; then the question says
 * Recorded with the option taken or the words said, or Withdrawn with who,
 * when and why.
 * ------------------------------------------------------------------------ */
import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useSteadyPress } from '../../steady'
import { ago } from '../answers'
import * as D from '../decisions'
import '../renderable.css'
import './data.css'

const letter = (i: number) => String.fromCharCode(65 + i)
const clip = (s: string, n: number) => (s.length <= n ? s : s.slice(0, n - 1).trimEnd() + '…')

/** What closes an ask and what records nothing, said before either is done. */
export const HINT =
  'Leave open records nothing: it stays owed. Any Answer (a choice, or your own words), ' +
  'Establish, Supersede and Set aside each record a response and close the ask.'
/** And for a decision, the one way to close it without answering. */
export const WITHDRAW_HINT =
  ' Withdraw closes a decision without answering it, and records your reason from the field below.'
/** What withdrawing does, said before it is sent. */
export const WITHDRAW_SAYS =
  'Withdraw closes this decision without answering it. Your reason is recorded as your reply; ' +
  'the question and its choices stay as they are, and nothing runs.'

/** How an ask is headed: something owed by the owner, and by whom asked. */
export function line(e: D.Ask): string {
  if (e.expects === 'decision') return 'Decision owed by you'
  if (e.expects === 'clarification') return `${e.by_alias} asked you a question`
  return `${e.by_alias} is waiting on you for a ${e.expects}`
}

/** What a wake-check review decides about: the request and the stopped run. */
export function StoppedWorkLine({ w }: { w: D.StoppedWork }) {
  return (
    <div className="rb-dec-why rb-dec-stopped" aria-label="the stopped work this decides about">
      <div>
        Requested by {w.requester_alias ?? 'unknown'}
        {w.request_number != null && ` in #${w.request_number}`}
        {w.request_said && <>: “{clip(w.request_said, 240)}”</>}
      </div>
      <div>
        {w.run_state === 'ended-unseen' ? 'Ended unseen' : 'Interrupted'}:{' '}
        {w.carrier_alias ? `${w.carrier_alias}'s` : 'the'} run {w.run}
        {w.runtime && ` (${w.runtime})`}
        {w.execution && <> · execution <code>{w.execution}</code></>}
        {w.stopped_at != null && ` · stopped ${ago(w.stopped_at)}`}
      </div>
    </div>
  )
}

/** WHAT A PERMISSION COVERS, before its answers: what the agent wants to do
 *  (unless the question already says it), what it affects, why it belongs to
 *  the task in the record's words and the agent's own, and whether it is
 *  inside the task's boundary. The exact command is Details, never the
 *  question. What each answer covers is each option's own consequence. */
export function OperationLine({ op, by, question }: { op: D.Operation; by: string; question?: string | null }) {
  const affects = [...(op.resources ?? []), ...(op.workspace && !(op.resources ?? []).length ? [op.workspace] : [])]
  return (
    <div className="rb-dec-op" aria-label="what this permission covers">
      {op.summary && op.summary !== question && <div><span className="rb-dec-op-k">Wants to</span> {op.summary}</div>}
      {affects.length > 0 && (
        <div><span className="rb-dec-op-k">Affects</span> {affects.join(' · ')}
          {op.workspace && (op.resources ?? []).length > 0 && <span className="rb-dec-op-in"> in {op.workspace}</span>}
        </div>
      )}
      {op.why && <div><span className="rb-dec-op-k">For</span> {op.why}</div>}
      {op.agent_says && <div><span className="rb-dec-op-k">{by} says</span> “{clip(op.agent_says, 240)}”</div>}
      {op.within === true && <div className="rb-dec-op-within">Inside this task's boundary</div>}
      {op.within === false && (
        <div className="rb-dec-op-outside">Outside this task{op.outside?.length ? ': ' + op.outside.join('; ') : ''}</div>
      )}
      {op.command && (
        <details className="rb-dec-op-details">
          <summary>Details</summary>
          <pre>{op.command}</pre>
          {(op.cwd || op.tool_label || op.tool) && (
            <div className="rb-dec-op-in">{[op.tool_label || op.tool, op.cwd && `in ${op.cwd}`].filter(Boolean).join(' · ')}</div>
          )}
        </details>
      )}
    </div>
  )
}

/** One option, as every question draws it. */
function OptionRow({ i, o, on, state, disabled, title, onPick, tabbable }: {
  i: number | 'own' | 'withdraw'; o?: D.Option; on: boolean; state?: 'pending' | 'recorded' | 'settled'
  disabled?: boolean; title?: string; onPick?: (ev: React.MouseEvent<HTMLButtonElement>) => void; tabbable?: boolean
}) {
  const label = i === 'own' ? 'Your own words' : i === 'withdraw' ? 'Withdraw' : o!.label
  const then = i === 'own' ? undefined : i === 'withdraw' ? 'close it unanswered, with your reason' : o!.consequence
  const mark = i === 'own' ? '…' : i === 'withdraw' ? '⊘' : letter(i)
  const cls = 'rb-dec-option' + (i === 'withdraw' ? ' rb-dec-withdraw' : i === 'own' ? ' rb-dec-own' : '') + (on ? ' on' : '') + (state ? ' ' + state : '')
  const inner = (
    <>
      <span className="rb-dec-mark" aria-hidden="true">{state === 'recorded' ? '✓' : on ? (state === 'pending' ? '…' : '●') : ''}</span>
      <span className="rb-dec-text">
        <span className="rb-dec-label"><b className="rb-dec-letter">{mark}</b> {label}</span>
        {then && <span className="rb-dec-then">{then}</span>}
        {on && state === 'pending' && <span className="rb-dec-tag">sending — not yet recorded</span>}
        {on && !state && i !== 'withdraw' && <span className="rb-dec-tag">selected — not sent yet</span>}
        {state === 'recorded' && <span className="rb-dec-tag">recorded</span>}
      </span>
    </>
  )
  if (!onPick) return <div className={cls} data-option={i}>{inner}</div>
  return (
    <button type="button" role="radio" aria-checked={on} tabIndex={tabbable ? 0 : -1} disabled={disabled}
      className={cls} data-option={i} title={title} onClick={onPick}>
      {inner}
    </button>
  )
}

/** A question the record says is closed: answered, or withdrawn. */
function Closed({ e, post, fresh }: { e: D.Ask; post: D.PostHead | null; fresh?: D.Landing }) {
  const options = e.options ?? []
  const w = e.withdrawn
  if (w) {
    const because = (w.because ?? '').trim()
    return (
      <div className={'rb-dec-closed withdrawn' + (fresh ? ' fresh' : '')} role={fresh ? 'status' : undefined}>
        <div className="rb-dec-recorded">
          <span className="rb-dec-recorded-mark" aria-hidden="true">⊘</span>
          <span className="rb-dec-recorded-word">Withdrawn</span>
          <span className="rb-dec-recorded-what">
            by {w.by_alias ?? 'the person it was asked of'}
            {w.at ? ` · ${ago(w.at)}` : ''}
            {because ? ` · “${clip(because, 110)}”` : ''}
          </span>
        </div>
        <p className="rb-dec-why">
          Closed without an answer. The question{e.form ? '' : post?.number != null ? ` in #${post.number}` : ''}
          {options.length > 0 ? ' and the choices it offered stay' : ' stays'} in the record, unchanged.
        </p>
        {options.length > 0 && (
          <div className="rb-dec-options" aria-label="the choices you were asked with">
            {options.map((o, i) => <OptionRow key={i} i={i} o={o} on={false} state="settled" />)}
          </div>
        )}
      </div>
    )
  }
  const by = e.answered_by ?? null
  const pick = by?.chose && !by.chose.withdraw ? by.chose : null
  const said = by?.said ?? ''
  return (
    <div className={'rb-dec-closed answered' + (fresh ? ' fresh' : '')} role={fresh ? 'status' : undefined}>
      <div className="rb-dec-recorded">
        <span className="rb-dec-recorded-mark" aria-hidden="true">✓</span>
        <span className="rb-dec-recorded-word">Recorded</span>
        <span className="rb-dec-recorded-what">
          {pick && pick.option != null
            ? `You chose ${letter(pick.option)} ${pick.label}`
            : said
              ? `You answered “${clip(said, 110)}”`
              : by
                ? 'You answered in your own words'
                : 'the record shows this was answered'}
          {by?.number != null && ` · #${by.number}`}
          {fresh?.continued && ' · and asked them to continue'}
        </span>
      </div>
      {fresh && (
        <p className="rb-dec-why">
          {pick && pick.option != null ? `Answered ${letter(pick.option)}. ` : 'Answered. '}
          Nothing else was recorded. No governed material changed.
        </p>
      )}
      {fresh && options.length > 0 && (
        <div className="rb-dec-options" aria-label="the choices you were asked with">
          {options.map((o, i) => <OptionRow key={i} i={i} o={o} on={pick?.option === i} state={pick?.option === i ? 'recorded' : 'settled'} />)}
        </div>
      )}
    </div>
  )
}

/** One open question: its choices, own words and Withdraw, and the field. */
function Open({ e, pick, text, landing, error, onPick, onText }: {
  e: D.Ask; pick: D.Pick | undefined; text: string; landing?: D.Landing; error?: string
  onPick: (p: D.Pick | undefined) => void; onText: (t: string) => void
}) {
  const options = e.options ?? []
  const decision = e.expects === 'decision'
  const locked = !!landing
  const group = useRef<HTMLDivElement | null>(null)
  /* A choice is made only on the option aimed at (opr-e87efe7171a7). */
  const steady = useSteadyPress(group, '[role="radio"]')
  const box = useRef<HTMLTextAreaElement | null>(null)
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (landing?.phase !== 'sent') return
    setSlow(false)
    const t = window.setTimeout(() => setSlow(true), 6000)
    return () => window.clearTimeout(t)
  }, [landing?.phase, landing?.turn])
  const chosen = pick?.kind === 'option' ? pick.option : null
  const own = pick?.kind === 'own'
  const withdrawing = pick?.kind === 'withdraw'
  const o = chosen !== null ? options[chosen] : null
  const slots: D.Pick[] = [...options.map((_, i) => ({ kind: 'option', option: i }) as D.Pick), { kind: 'own' }, ...(decision ? [{ kind: 'withdraw' } as D.Pick] : [])]
  const at = slots.findIndex((s) => s.kind === pick?.kind && (s.kind !== 'option' || (pick?.kind === 'option' && s.option === pick.option)))
  const choose = (p: D.Pick) => {
    if (locked) return
    const same = at >= 0 && slots[at].kind === p.kind && (p.kind !== 'option' || (pick?.kind === 'option' && pick.option === p.option))
    onPick(same ? undefined : p)
    if (!same && p.kind !== 'option') window.setTimeout(() => box.current?.focus(), 0)
  }
  /* One tab stop, arrows move: the radiogroup behaves like one. */
  const onKey = (ev: React.KeyboardEvent) => {
    if (locked) return
    const step = ev.key === 'ArrowDown' || ev.key === 'ArrowRight' ? 1 : ev.key === 'ArrowUp' || ev.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    ev.preventDefault()
    const to = ((at < 0 ? (step > 0 ? -1 : 0) : at) + step + slots.length) % slots.length
    onPick(slots[to])
    group.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[to]?.focus()
  }
  const status = landing
    ? landing.phase === 'sending'
      ? `Sending ${landing.pick.kind === 'withdraw' ? 'your withdrawal' : landing.label ? `“${landing.label}”` : 'your answer'}…`
      : slow
        ? `Sent as #${landing.number ?? '?'}. The record has not shown it yet; it will be marked Recorded here when it does.`
        : `Sent as #${landing.number ?? '?'} — waiting for the record to confirm…`
    : null
  return (
    <>
      <div ref={group} className="rb-dec-options" role="radiogroup" aria-label={e.question ? `the choices for: ${e.question}` : 'the choices you were asked with'}
        aria-disabled={locked || undefined} onKeyDown={onKey} onPointerDownCapture={steady.onPointerDownCapture}>
        {options.map((x, i) => (
          <OptionRow key={i} i={i} o={x} on={chosen === i} state={chosen === i && locked ? 'pending' : undefined}
            disabled={locked && chosen !== i} tabbable={chosen === i || (at < 0 && i === 0)}
            title={`Answers ${e.by_alias}; nothing else is recorded`}
            onPick={(ev) => { if (steady.accept(ev)) choose({ kind: 'option', option: i }) }} />
        ))}
        <OptionRow i="own" on={own} disabled={locked} tabbable={own || (at < 0 && options.length === 0)}
          title={`Answers ${e.by_alias} in your own words; nothing else is recorded`}
          onPick={(ev) => { if (steady.accept(ev)) choose({ kind: 'own' }) }} />
        {decision && (
          <OptionRow i="withdraw" on={withdrawing} disabled={locked} tabbable={withdrawing}
            title={`Closes this decision without answering ${e.by_alias}; your reason is recorded`}
            onPick={(ev) => { if (steady.accept(ev)) choose({ kind: 'withdraw' }) }} />
        )}
      </div>
      {o?.per_finding && o.findings && pick?.kind === 'option' && (
        <div className="rb-dec-options" aria-label="what to do with each finding">
          {o.findings.map((f) => {
            const now = pick.findings?.[f.ref] ?? 'defer'
            return (
              <div key={f.ref} className="rb-dec-finding" role="radiogroup" aria-label={f.label}>
                <span className="rb-dec-label">{f.label}</span>
                {(['pursue', 'defer', 'dismiss'] as const).map((c) => (
                  <button key={c} type="button" role="radio" aria-checked={now === c} disabled={locked}
                    className={'rb-link rb-dec-each' + (now === c ? ' on' : '')}
                    onClick={() => onPick({ ...pick, findings: { ...(pick.findings ?? {}), [f.ref]: c } })}>
                    {c === 'pursue' ? 'Pursue' : c === 'defer' ? 'Keep deferred' : 'Dismiss'}
                  </button>
                ))}
              </div>
            )
          })}
        </div>
      )}
      {withdrawing && <div className="rb-dec-why">{WITHDRAW_SAYS}</div>}
      {pick && (
        <textarea ref={box} className="rb-form-input rb-form-area rb-dec-words" rows={2} value={text} disabled={locked}
          aria-label={withdrawing ? 'why you are withdrawing it' : own ? 'your answer, in your own words' : 'add to your choice'}
          placeholder={withdrawing ? 'Why are you withdrawing this decision? (required)' : own ? (decision ? 'Decide in your own words…' : 'Answer…') : 'Add to your choice (optional)…'}
          onChange={(ev) => onText(ev.target.value)}
          /* Escape in the field belongs to the field: it does not close what the form is in. */
          onKeyDown={(ev) => { if (ev.key === 'Escape') ev.stopPropagation() }} />
      )}
      {withdrawing && !locked && !text.trim() && <div className="rb-dec-note">{D.WITHDRAW_NEEDS_REASON}</div>}
      {status && <div className={'rb-dec-landing ' + landing!.phase} role="status" aria-live="polite">{status}</div>}
      {error && <div className="rb-form-failed" role="alert">Not sent: {error}</div>}
    </>
  )
}

/** The label of the one answer action, for what is chosen. */
function answerLabel(chosen: { ask: D.Ask; pick: D.Pick }[], open: D.Ask[]): string {
  if (chosen.length === 0) return open.every((a) => a.expects === 'decision') ? 'Decide' : 'Answer'
  if (chosen.length > 1) return `Send ${chosen.length} answers`
  const [{ ask, pick }] = chosen
  return pick.kind === 'withdraw' ? 'Withdraw' : ask.expects === 'decision' ? 'Decide' : 'Answer'
}

/* A CHOICE NOT YET SENT IS THE FORM'S, NOT ITS DRAWING'S (Fluid Focus: one
   object drawn in a post, a section, a float or the primary place): kept by
   the form's key for the life of the tab, so a form drawn again elsewhere
   keeps what was chosen and typed, and every copy drawn at once shows the
   same draft. Answer still sends it, and the record says what was sent. */
const drafts = new Map<string, Record<string, unknown>>()
const draftsTold = new Set<() => void>()
const EMPTY: Record<string, never> = {}
function useDraft<T extends Record<string, unknown>>(key: string): [T, (f: (t: T) => T) => void] {
  const now = useSyncExternalStore(
    (f) => { draftsTold.add(f); return () => { draftsTold.delete(f) } },
    () => drafts.get(key) ?? EMPTY,
  ) as T
  const set = (f: (t: T) => T) => {
    const next = f((drafts.get(key) ?? EMPTY) as T)
    if (Object.keys(next).length) drafts.set(key, next)
    else drafts.delete(key)
    draftsTold.forEach((g) => g())
  }
  return [now, set]
}

/** ONE DECISION FORM: a decision form's questions, or one ask on its post.
 *  `me` is who answers here; only what is asked of them is drawn, as the
 *  cards drew it. `onChanged` is told once something was sent. */
export function DecisionForm({ group, me, onChanged }: { group: D.Group; me: string | null; onChanged?: () => void }) {
  const landings = D.useLandings()
  const [picks, setPicks] = useDraft<Record<string, D.Pick | undefined>>(group.key + '|picks')
  const [texts, setTexts] = useDraft<Record<string, string>>(group.key + '|texts')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [left, setLeft] = useState(false)
  const [busy, setBusy] = useState(false)
  const mine = group.asks.filter((a) => !!me && a.of === me)
  if (mine.length === 0) return null
  const open = mine.filter((a) => !a.response_present)
  const lead = mine[0]
  const several = group.form !== null && mine.length > 1
  const post = group.post
  const locked = (a: D.Ask) => !!landings.get(a.id) && !a.response_present
  const chosen = open.filter((a) => picks[a.id] && !locked(a)).map((a) => ({ ask: a, pick: picks[a.id]!, text: texts[a.id] ?? '' }))
  /* Handing the work back is the composer's "+ continue" on an ask on its
     own post; a form's work resumes by itself when its last question closes. */
  const alone = group.form === null
  const author = post?.author ?? null
  const canContinue = alone && !!author && author !== me && chosen.length === 1 && chosen[0].pick.kind !== 'withdraw'
  const authorName = post?.author_alias ?? 'them'
  const sendNow = async (continuing: boolean) => {
    if (busy || chosen.length === 0) return
    setErrors({})
    setBusy(true)
    try {
      await D.send(group, chosen, me, continuing ? author : null)
      setPicks((p) => Object.fromEntries(Object.entries(p).filter(([k]) => !chosen.some((c) => c.ask.id === k))))
      setTexts((t) => Object.fromEntries(Object.entries(t).filter(([k]) => !chosen.some((c) => c.ask.id === k))))
    } catch (e) {
      const at = (e as { ask?: string }).ask ?? lead.id
      setErrors({ [at]: String((e as Error).message ?? e) })
    } finally {
      setBusy(false)
      onChanged?.()
    }
  }
  const answered = mine.length - open.length
  const state = open.length === 0 ? 'closed' : answered ? 'partly' : 'open'

  /* Folded because the owner left it open, and saying exactly that. */
  if (left && open.length && !open.some(locked))
    return (
      <div className="rb-form rb-decision rb-dec-left" data-decision-form={group.key}>
        <div className="rb-dec-why">
          Left open: nothing was recorded, and it is still owed.{' '}
          <button type="button" className="rb-link" onClick={() => setLeft(false)}>Answer it now</button>
        </div>
      </div>
    )

  return (
    <section className="rb-form rb-decision" data-decision-form={group.key} data-state={state}
      aria-label={several ? `${mine.length} decisions owed by you` : line(lead)}>
      {(open.length > 0 || several) && (
        <div className="rb-dec-head">
          <div className="rb-dec-line">
            {!several ? line(lead) : open.length ? `${open.length === mine.length ? mine.length : `${open.length} of ${mine.length}`} decisions owed by you` : `${mine.length} decisions you were asked, all closed`}
          </div>
          <div className="rb-dec-why">
            {lead.by_alias} asked
            {(group.because ?? lead.because) && ` · because ${group.because ?? lead.because}`}
          </div>
          {lead.stopped_work && <StoppedWorkLine w={lead.stopped_work} />}
          {group.operation && open.length > 0 && <OperationLine op={group.operation} by={lead.by_alias} question={several ? null : lead.question} />}
          {/* WHAT CLOSES AN ASK AND WHAT RECORDS NOTHING, once, before either is done. */}
          {open.length > 0 && <div className="rb-dec-why">{HINT + (open.some((a) => a.expects === 'decision') ? WITHDRAW_HINT : '')}</div>}
        </div>
      )}
      {mine.map((a, k) => {
        const l = landings.get(a.id)
        return (
          <fieldset key={a.id} className="rb-dec-q" data-question={a.id}
            data-state={a.withdrawn ? 'withdrawn' : a.response_present ? 'answered' : 'open'}>
            {a.question && <legend className="rb-dec-question">{several ? `${k + 1}. ` : ''}{a.question}</legend>}
            {a.response_present
              ? <Closed e={a} post={post} fresh={l} />
              : <Open e={a} pick={picks[a.id]} text={texts[a.id] ?? ''} landing={l} error={errors[a.id]}
                  onPick={(p) => { setPicks((m) => ({ ...m, [a.id]: p })); setErrors({}) }}
                  onText={(t) => setTexts((m) => ({ ...m, [a.id]: t }))} />}
          </fieldset>
        )
      })}
      {open.length > 0 && (
        <div className="rb-form-foot rb-row rb-dec-foot">
          <span className="rb-form-status rb-muted" role="status">
            {open.some(locked) ? 'Sending…'
              : chosen.length ? `${chosen.length === 1 ? 'One answer' : `${chosen.length} answers`} chosen, not sent yet`
                : several ? `${answered} of ${mine.length} answered` : 'Nothing sent yet'}
          </span>
          <span className="rb-grow" />
          {!open.some(locked) && (
            <button type="button" className="btn quiet" title="Records nothing. The ask stays owed." onClick={() => setLeft(true)}>Leave open</button>
          )}
          {canContinue && (
            <button type="button" className="btn" disabled={busy}
              title={lead.continues_work ? `Also hands the work back to ${authorName}` : `Would start new work for ${authorName}; there is no open authorised work here for it to carry on`}
              onClick={() => void sendNow(true)}>
              {answerLabel(chosen, open)} + continue with {authorName}
            </button>
          )}
          <button type="button" className="btn primary" disabled={busy || chosen.length === 0}
            title={chosen.some((c) => c.pick.kind === 'withdraw') ? 'Closes it without an answer and records your reason. Nothing runs.' : 'Records each answer as your reply and closes its question. Nothing runs.'}
            onClick={() => void sendNow(false)}>
            {answerLabel(chosen, open)}
          </button>
        </div>
      )}
    </section>
  )
}

/** Every decision form on one read, each drawn whole. */
export function DecisionForms({ read, me, only, focus, onChanged }: { read: D.Read; me?: string | null; only?: string[]; focus?: string | null; onChanged?: () => void }) {
  const who = me ?? read.you
  const root = useRef<HTMLDivElement | null>(null)
  const groups = D.groupsOf(read, only)
  if (focus) groups.sort((a, b) => Number(b.asks.some((x) => x.id === focus)) - Number(a.asks.some((x) => x.id === focus)))
  useEffect(() => {
    if (!focus) return
    const question = [...(root.current?.querySelectorAll<HTMLElement>('[data-question]') ?? [])]
      .find((el) => el.dataset.question === focus)
    question?.scrollIntoView({ block: 'center' })
  }, [focus, read])
  return (
    <div ref={root}>
      {groups.map((g) => <DecisionForm key={g.key} group={g} me={who} onChanged={onChanged} />)}
    </div>
  )
}

/** The decision forms on a post (or asks by id), read and kept current. */
export function DecisionsOn({ post, ids, only, focus, me, onChanged }: { post?: string | null; ids?: string[]; only?: string[]; focus?: string | null; me?: string | null; onChanged?: () => void }) {
  const key = post ? D.keyOf({ post }) : ids?.length ? D.keyOf({ ids }) : null
  const got = D.useDecisions(key)
  if (!got?.read) return got?.error ? <p className="rb-form-failed" role="alert">Couldn't read the decisions here ({got.error}).</p> : null
  return <DecisionForms read={got.read} me={me} only={only} focus={focus} onChanged={onChanged} />
}
