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
 * WHAT IS RECORDED IS WHAT THE SERVER SAID IT RECORDED. An answer has an
 * identity and is kept on this device from the moment it is sent
 * (../decisionOutbox.ts), and the form says which of four things is true:
 *
 *   Sending       the request is out
 *   Recorded      the server wrote the post (#N); whether that closed the
 *                 question is then read from the record and said separately
 *   Not confirmed the request ended without an answer: the server is asked,
 *                 the owner's words stay here, and sending again cannot
 *                 make a second post
 *   Not sent      the server refused it and wrote nothing, and why
 *
 * A reply the record holds that did NOT close its question (words alone on a
 * decision about findings) is shown as exactly that, from the record, on any
 * page and after any refresh: never "Nothing sent yet".
 * ------------------------------------------------------------------------ */
import { useContext, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { useSteadyPress } from '../../steady'
import { ago } from '../answers'
import * as D from '../decisions'
import * as P from '../decisionPresentation'
import * as K from '../draftKeep'
import { OpenRef, RefWordsContext, Words } from '../refWords'
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
/** What withdrawing does, said before it is sent -- the whole disclosure,
 *  including that closing the last question MAY let the Work resume under its
 *  existing rules (../decisionPresentation). It is not a promise that anything
 *  runs, and not a promise of a clearer question. */
export const WITHDRAW_SAYS = P.withdrawSays(true)
export const WITHDRAW_SAYS_ALONE = P.withdrawSays(false)

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

/** THE ONE PRIMARY SOURCE, where one was explicitly recorded; else exactly
 *  what the record does say. No placeholder, no "first reference", and never
 *  the nearest similarly named thing. */
function Primary({ standing }: { standing: P.PrimaryStanding }) {
  const host = useContext(RefWordsContext)
  if (standing.kind === 'unrecorded')
    return <div className="rb-dec-said" data-primary="unrecorded">The record does not name a primary source for this decision.</div>
  if (standing.kind === 'none')
    return (
      <div className="rb-dec-said" data-primary="none">
        No primary source{standing.because ? <>: <Words>{standing.because}</Words></> : '. The record does not say why.'}
      </div>
    )
  const r = standing.ref
  const opens = P.refOpens(r)
  /* A RECORD IS OPENED THE WAY ITS HOST OPENS ONE (../refWords). Where the
     host offers no way, that is said: approval material that cannot be
     inspected from here is said before the decision, not discovered after. */
  const opened = opens && 'record' in opens ? host?.open?.(opens.record, 'Open it') ?? null : null
  return (
    <div className="rb-dec-primary" data-primary="ref" data-ref-kind={r.kind}>
      <span className="rb-dec-op-k">Inspect</span>
      <span className="rb-dec-primary-what">
        {opens && 'url' in opens
          ? <a className="rb-link" href={opens.url} target="_blank" rel="noreferrer noopener">{P.refWords(r)}</a>
          : <span className="rb-dec-label">{P.refWords(r)}</span>}
        {opened}
        {opens && 'record' in opens && !opened && (
          <span className="rb-dec-aside"> — it cannot be opened from here; the asking post has it.</span>
        )}
      </span>
    </div>
  )
}

/** WHAT THIS QUESTION ASKS, AS ITS AUTHOR DECLARED IT: what an answer would
 *  authorise and at which stage, any condition on it, the one primary source
 *  to inspect, the further material it names folded away, and -- where the
 *  record holds none of those -- exactly which of them is missing
 *  (../decisionPresentation).
 *
 *  A READ, AND ONLY A READ. Drawing this amends, withdraws, supersedes or
 *  recreates nothing, and it adds no meaning to the question: every sentence
 *  here is either the author's own words or a statement that the record does
 *  not hold them. It is per question: one question's primary source is never
 *  drawn on another's. */
export function Presented({ ask, status, form }: { ask: D.Ask; status: P.PresentationStatus; form?: P.Asking | null }) {
  const p = P.presentationOf(ask)
  const known = !!p && p.version === 1 && P.TYPES.includes(p.type)
  const scope = P.scopeWords(ask)
  const stages = known ? P.stageWords(p!.stages) : ''
  const when = P.appliesWhen(ask)
  /* NOTHING IS READ OUT OF PRESENTATION DATA THIS PAGE DOES NOT SUPPORT: an
     unknown version or type is preserved and said to be unsupported, and its
     fields are not drawn as though they were version 1's. */
  const supporting = known ? P.supportingOf(ask) : []
  /* THE FORM ROW GOES WITH THE QUESTION: whether the record says this form
     carries a generated approval is read from it, never guessed from the
     question's words (../decisionPresentation, ent-9f0291944c9a). */
  const gaps = P.gapsOf(status, ask, form)
  const primary = P.primaryOf(ask)
  return (
    <div className="rb-dec-asks" data-presentation={status.state}>
      {known && <div className="rb-dec-kind">{P.TYPE_WORDS[p!.type]}</div>}
      {scope && (
        <div className="rb-dec-scope">
          <span className="rb-dec-op-k">Your answer</span>
          <span className="rb-dec-primary-what"><Words>{scope}</Words></span>
        </div>
      )}
      {stages && (
        <div className="rb-dec-scope">
          <span className="rb-dec-op-k">Covers</span>
          <span className="rb-dec-primary-what">{stages}</span>
        </div>
      )}
      {when && (
        <div className="rb-dec-scope" data-applies-when>
          <span className="rb-dec-op-k">Applies when</span>
          <span className="rb-dec-primary-what"><Words>{when}</Words><span className="rb-dec-aside"> {P.APPLIES_WHEN_SAYS}</span></span>
        </div>
      )}
      {known && <Primary standing={primary} />}
      {supporting.length > 0 && (
        <details className="rb-dec-supporting" data-supporting={supporting.length}>
          <summary>{supporting.length === 1 ? 'One more thing it names' : `${supporting.length} more things it names`}</summary>
          <ul>
            {supporting.map((r, i) => (
              <li key={i}>
                {r.kind === 'url'
                  ? <a className="rb-link" href={r.url} target="_blank" rel="noreferrer noopener">{P.refWords(r)}</a>
                  : <>{P.refWords(r)}{r.kind === 'record' && <> <OpenRef id={r.id} words="Open it" /></>}</>}
              </li>
            ))}
          </ul>
        </details>
      )}
      {/* AN OLDER DECISION IS NOT A BROKEN ONE: it is shown as recorded, said
          to be an earlier format, and not claimed to have been verified. The
          absence of a declared primary role is said here, once, rather than
          listed as an omission of a contract it was never written against. */}
      {status.state === 'legacy' && <div className="rb-dec-why" data-earlier-format>{P.EARLIER_FORMAT}</div>}
      {/* MARKED APART FROM THE PANEL'S OWN `data-gap`: that one says what the
          REQUEST names and could not be read (quiet2/needs/NeedsAbout.tsx);
          this one says what the QUESTION does not say. A host drawing both must
          be able to ask for either. */}
      {gaps.map((g, i) => <p key={i} className="rb-dec-gap" role="note" data-dec-gap>{g}</p>)}
    </div>
  )
}

/** One option, as every question draws it. */
function OptionRow({ i, o, on, state, disabled, title, onPick, tabbable, sent, labelAs, thenAs }: {
  i: number | 'own' | 'withdraw'; o?: D.Option; on: boolean; state?: 'pending' | 'recorded' | 'settled'
  disabled?: boolean; title?: string; onPick?: (ev: React.MouseEvent<HTMLButtonElement>) => void; tabbable?: boolean
  /** what became of the answer this row is part of, once it was sent */
  sent?: string | null
  /** said instead of the row's own words, where the same payload is offered as
   *  something else (a withdrawal offered as asking for a clearer question) */
  labelAs?: string
  thenAs?: string
}) {
  const label = labelAs ?? (i === 'own' ? 'Your own words' : i === 'withdraw' ? 'Withdraw' : o!.label)
  const then = thenAs ?? (i === 'own' ? undefined : i === 'withdraw' ? 'close it unanswered, with your reason' : o!.consequence)
  /* AN OFFERED ALTERNATIVE WITH NO RECORDED CONSEQUENCE is said to have none,
     never left blank as though choosing it did nothing (contract §5). Its
     wording and what it records are untouched. */
  const noThen = typeof i === 'number' && !then
  const mark = i === 'own' ? '…' : i === 'withdraw' ? '⊘' : letter(i)
  const cls = 'rb-dec-option' + (i === 'withdraw' ? ' rb-dec-withdraw' : i === 'own' ? ' rb-dec-own' : '') + (on ? ' on' : '') + (state ? ' ' + state : '')
  const inner = (
    <>
      <span className="rb-dec-mark" aria-hidden="true">{state === 'recorded' ? '✓' : on ? (state === 'pending' ? '…' : '●') : ''}</span>
      <span className="rb-dec-text">
        {/* an id in an option's words reads as the thing it names (../refWords) */}
        <span className="rb-dec-label"><b className="rb-dec-letter">{mark}</b> <Words how="names">{label}</Words></span>
        {then && <span className="rb-dec-then"><Words how="names">{then}</Words></span>}
        {noThen && <span className="rb-dec-then rb-dec-then-missing" data-no-consequence>What choosing this leads to was not recorded.</span>}
        {on && sent && <span className="rb-dec-tag">{sent}</span>}
        {on && !sent && state === 'pending' && <span className="rb-dec-tag">sending — not yet recorded</span>}
        {on && !sent && !state && i !== 'withdraw' && <span className="rb-dec-tag">selected — not sent yet</span>}
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

/** A question the record says is closed: answered, withdrawn, or no longer
 *  asked because the run that asked it can no longer take an answer. */
/** An answer sent from this device whose outcome was never confirmed, on a
 *  question the record now shows closed some other way. Its words are not
 *  thrown away and nothing is assumed: the owner asks, or gives it up. */
function Unconfirmed({ e, kept }: { e: D.Ask; kept: D.Sent }) {
  const [working, setWorking] = useState(false)
  const [said, setSaid] = useState<string | null>(null)
  const act = async (f: () => Promise<unknown>, none: string) => {
    if (working) return
    setWorking(true)
    try { if (!(await f())) setSaid(none) } finally { setWorking(false) }
  }
  return (
    <div className="rb-dec-landing unknown" data-unconfirmed role="alert">
      An answer you sent from this device was never confirmed: “{clip(kept.text || kept.label || '', 160)}”.
      This question has since been closed, and that answer may or may not also be in the record.
      {said && <> {said}</>}
      {' '}<button type="button" className="rb-link" data-check disabled={working}
        onClick={() => void act(async () => (await D.checkSent(e.id)) !== null, 'The server could not be asked just now.')}>Check</button>
      {' · '}<button type="button" className="rb-link" data-give-up disabled={working}
        onClick={() => void act(() => D.giveUp(e.id), D.isLegacySent(e.id) ? D.LEGACY : 'The server could not be asked just now.')}>Withdraw it if it was not recorded</button>
    </div>
  )
}

function Closed({ e, post, fresh }: { e: D.Ask; post: D.PostHead | null; fresh?: D.Sent }) {
  const options = e.options ?? []
  const w = e.withdrawn
  const l = e.lapsed
  if (l && !w) {
    const because = (l.because ?? '').replace(/^no longer asked: /, '')
      .replace(/; nothing was allowed by this question$/, '').trim()
    return (
      <div className="rb-dec-closed withdrawn lapsed">
        <div className="rb-dec-recorded">
          <span className="rb-dec-recorded-mark" aria-hidden="true">⊘</span>
          <span className="rb-dec-recorded-word">No longer asked</span>
          <span className="rb-dec-recorded-what">
            {l.at ? ago(l.at) : ''}{because ? ` · ${clip(because, 110)}` : ''}
          </span>
        </div>
        <p className="rb-dec-why">
          The run that asked can no longer take an answer, so nothing you choose here would reach it.
          Nothing was allowed by this question; the question stays in the record, unchanged.
        </p>
      </div>
    )
  }
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
        <p className="rb-dec-why" data-what-it-did>
          {pick && pick.option != null ? `Answered ${letter(pick.option)}. ` : 'Answered. '}
          {/* WHAT IT DID IS WHAT THE SERVER SAID IT DID, said apart from "recorded". */}
          {fresh.did
            ? `The server recorded your choice for each finding: ${fresh.did.pursued} to pursue, ${fresh.did.deferred} kept deferred, ${fresh.did.dismissed} dismissed. `
              + (fresh.did.pursued === 0 ? 'Nothing was started.'
                : fresh.did.started === null ? 'It did not say what work it started for the ones to pursue: see Work.'
                  : `It started ${fresh.did.started} piece${fresh.did.started === 1 ? '' : 's'} of work for the ones to pursue; whether each is running is shown in Work, not here.`)
            : D.decidesFindings(e)
              ? 'This decided what happens to the findings. What it started is shown in Work, not here.'
              : fresh.continued
                ? (fresh.dispatched === null ? 'You asked them to continue; the server did not say whether a run was started.'
                  : fresh.dispatched > 0 ? `You asked them to continue, and the server started ${fresh.dispatched === 1 ? 'a run' : `${fresh.dispatched} runs`}.`
                    : 'You asked them to continue, and the server started no run.')
                : 'Your reply was recorded, and nothing was started by it.'}
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
function Open({ e, pick, text, kept, error, declared, onForm, onPick, onText, onTakeBack }: {
  e: D.Ask; pick: D.Pick | undefined; text: string; kept?: D.Sent; error?: string
  /** what the record holds of what this asks (../decisionPresentation) */
  declared: P.PresentationStatus
  /** a question of a decision form, whose closure may resume its Work when it
   *  is the last one; else an ask on its own post */
  onForm: boolean
  onPick: (p: D.Pick | undefined) => void; onText: (t: string) => void
  onTakeBack: (back: { pick: D.Pick; text: string }) => void
}) {
  const options = e.options ?? []
  const decision = e.expects === 'decision'
  /* WHAT CANNOT BE READ FROM THE RECORD CHANGES WHAT IS OFFERED, not what
     anything records: the withdrawal is additionally offered as the way to ask
     for a clearer question, under the same payload and the same reason field,
     and own words are said plainly to be an answer that closes it. */
  const unclear = P.unclear(declared)
  const locked = !!kept
  /* While its answer is sent or unconfirmed, the question shows WHAT WAS SENT,
     not whatever draft is held: the owner's words stay in front of them. */
  if (kept) { pick = kept.pick as D.Pick; text = kept.text }
  const group = useRef<HTMLDivElement | null>(null)
  /* A choice is made only on the option aimed at (opr-e87efe7171a7). */
  const steady = useSteadyPress(group, '[role="radio"]')
  const box = useRef<HTMLTextAreaElement | null>(null)
  /* Only what is SAID changes with time, never what is known: a request that
     is taking long is still Sending, and says the answer is kept meanwhile. */
  const [slow, setSlow] = useState(false)
  const [asked, setAsked] = useState<string | null>(null)
  const [working, setWorking] = useState(false)
  useEffect(() => {
    setSlow(false)
    setAsked(null)
    if (!kept || kept.phase === 'unknown') return
    const t = window.setTimeout(() => setSlow(true), 8000)
    return () => window.clearTimeout(t)
  }, [kept?.phase, kept?.op])
  const check = async () => {
    if (working || !kept) return
    setWorking(true)
    try {
      const got = await D.checkSent(e.id)
      setAsked(got === 'recorded' || got === 'voided' ? null
        : got === 'absent' ? (kept.phase === 'sending' ? 'The server does not hold it yet. It is still being sent.' : null)
          : 'The server could not be asked just now.')
    } finally { setWorking(false) }
  }
  const again = async () => {
    if (working) return
    setWorking(true)
    if (D.isLegacySent(e.id)) { setAsked(D.LEGACY); setWorking(false); return }
    try { await D.resend(e.id) } finally { setWorking(false) }
  }
  /* CHANGE IT FIRST IS THE SERVER'S TO ALLOW: it gives the answer up in one
     transaction, and only if nothing was recorded do the words come back. */
  const change = async () => {
    if (working) return
    setWorking(true)
    try {
      const got = await D.giveUp(e.id)
      if (!got) setAsked(D.isLegacySent(e.id) ? D.LEGACY : 'The server could not be asked just now, so nothing was changed.')
      else if (got.outcome === 'voided') onTakeBack({ pick: got.pick, text: got.text })
    } finally { setWorking(false) }
  }
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
  const what = kept ? ((kept.pick as D.Pick).kind === 'withdraw' ? 'your withdrawal' : kept.label ? `“${kept.label}”` : 'your answer') : ''
  const onDevice = kept?.kept === false ? 'held on this page (this browser would not store it, so do not close the page)' : 'kept on this device'
  const status = !kept ? null
    : kept.phase === 'sending'
      ? (slow ? `Still sending ${what}. It is ${onDevice} and cannot be recorded twice.` : `Sending ${what}…`)
      : kept.phase === 'recorded'
        ? (slow
          ? `Recorded as #${kept.number ?? '?'}. The record has not yet shown what it did to this question; this will say so when it does.`
          : `Recorded as #${kept.number ?? '?'}. Checking whether it closed this question…`)
        : kept.why === D.WITHDRAWN
          ? `Withdrawn before it was recorded: the server will not record ${what}. Your words are ${onDevice}.`
          : `Not confirmed: ${kept.why ?? 'the server did not answer'}. It may or may not have been recorded. Your words are ${onDevice}, and sending again cannot record it twice.`
  /* WHAT THE RECORD SAYS OF A REPLY THAT DID NOT CLOSE THIS: read, not remembered. */
  const replied = !kept && !e.response_present && e.answered_by ? e.answered_by : null
  /* On the chosen row itself: one of the three things that can be true of it. */
  const tag = !kept ? null
    : kept.phase === 'sending' ? 'sending — not yet recorded'
      : kept.phase === 'recorded' ? `recorded as #${kept.number ?? '?'}`
        : kept.why === D.WITHDRAWN ? 'withdrawn, not recorded' : 'not confirmed'
  const findings = D.decidesFindings(e)
  return (
    <>
      <div ref={group} className="rb-dec-options" role="radiogroup" aria-label={e.question ? `the choices for: ${e.question}` : 'the choices you were asked with'}
        aria-disabled={locked || undefined} onKeyDown={onKey} onPointerDownCapture={steady.onPointerDownCapture}>
        {options.map((x, i) => (
          <OptionRow key={i} i={i} o={x} on={chosen === i} state={chosen === i && locked ? 'pending' : undefined} sent={tag}
            disabled={locked && chosen !== i} tabbable={chosen === i || (at < 0 && i === 0)}
            title={`Answers ${e.by_alias}; nothing else is recorded`}
            onPick={(ev) => { if (steady.accept(ev)) choose({ kind: 'option', option: i }) }} />
        ))}
        <OptionRow i="own" on={own} sent={tag} disabled={locked} tabbable={own || (at < 0 && options.length === 0)}
          title={`Answers ${e.by_alias} in your own words; nothing else is recorded`}
          onPick={(ev) => { if (steady.accept(ev)) choose({ kind: 'own' }) }} />
        {decision && (
          <OptionRow i="withdraw" on={withdrawing} sent={tag} disabled={locked} tabbable={withdrawing}
            labelAs={unclear ? P.WITHDRAW_CLARIFY_LABEL : undefined} thenAs={unclear ? P.WITHDRAW_CLARIFY_THEN : undefined}
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
                <span className="rb-dec-label" title={`Exact reference: ${f.ref}`}><Words>{f.label}</Words></span>
                {f.why && <span className="rb-dec-label rb-muted">Why it was set aside: <Words>{f.why}</Words></span>}
                {/* the finding itself, as it was recorded: opened by its exact reference */}
                <OpenRef id={f.ref} words="Read this finding" />
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
      {withdrawing && <div className="rb-dec-why" data-withdraw-says>{P.withdrawSays(onForm)}</div>}
      {pick && (
        <textarea ref={box} className="rb-form-input rb-form-area rb-dec-words" rows={2} value={text}
          disabled={locked && kept?.phase !== 'unknown'} readOnly={locked}
          aria-label={withdrawing ? (unclear ? 'why you are withdrawing it, and what you would need to decide it' : 'why you are withdrawing it') : own ? 'your answer, in your own words' : 'add to your choice'}
          placeholder={withdrawing
            ? (unclear ? 'What is unclear, and what would you need in order to decide it? (required)' : 'Why are you withdrawing this decision? (required)')
            : own ? (decision ? 'Decide in your own words…' : 'Answer…') : 'Add to your choice (optional)…'}
          onChange={(ev) => onText(ev.target.value)}
          /* Escape in the field belongs to the field: it does not close what the form is in. */
          onKeyDown={(ev) => { if (ev.key === 'Escape') ev.stopPropagation() }} />
      )}
      {withdrawing && !locked && !text.trim() && <div className="rb-dec-note">{D.WITHDRAW_NEEDS_REASON}</div>}
      {own && !locked && findings && (
        <div className="rb-dec-note" data-leaves-open>
          Your words alone are recorded as a reply and leave this decision open: it is decided by choosing what
          happens to the findings. To decide, choose an option above. “Decide each finding” sets each one, and
          what you write is added to your choice.
        </div>
      )}
      {/* AN ANSWER IN YOUR OWN WORDS IS AN ANSWER, said before it is sent --
          so "please clarify" is not typed into it as a passive request for a
          clearer question. What it records is unchanged. */}
      {own && !locked && !findings && (
        <div className="rb-dec-why" data-own-closes>
          {P.OWN_WORDS_CLOSES}{unclear ? ' ' + P.OWN_WORDS_NOT_A_CLARIFICATION : ''}
        </div>
      )}
      {status && (
        <div className={'rb-dec-landing ' + kept!.phase} data-sent={kept!.phase} role={kept!.phase === 'unknown' ? 'alert' : 'status'} aria-live="polite">
          {status}
          {asked && <> {asked}</>}
          {kept!.phase === 'sending' && slow && (
            <> <button type="button" className="rb-link" data-check disabled={working} onClick={() => void check()}>Check whether it was recorded</button></>
          )}
          {kept!.phase === 'unknown' && (
            <span className="rb-dec-recover">
              {' '}<button type="button" className="rb-link" data-check disabled={working} onClick={() => void check()}>Check again</button>
              {kept!.why !== D.WITHDRAWN && (
                <>{' · '}<button type="button" className="rb-link" data-resend disabled={working} onClick={() => void again()}>Send again</button></>
              )}
              {' · '}<button type="button" className="rb-link" data-take-back disabled={working}
                title="Asks the server to give this answer up. If it was already recorded, that is said instead and nothing changes."
                onClick={() => void change()}>Change it first</button>
            </span>
          )}
        </div>
      )}
      {replied && (
        <div className="rb-dec-landing recorded-open" data-reply-recorded={replied.number ?? ''} role="status">
          Your reply{replied.number != null ? ` #${replied.number}` : ''} is recorded.{' '}
          {findings
            ? 'It did not decide this: a decision about findings is made by choosing what happens to them. Choose an option above (“Decide each finding” sets each one); what you write is added to your choice.'
            : 'The record does not count it as the answer to this question, which is still open.'}
        </div>
      )}
      {error && <div className="rb-form-failed" role="alert">Not sent, and nothing was recorded: {error}</div>}
    </>
  )
}

/** The label of the one answer action, for what is chosen. */
function answerLabel(chosen: { ask: D.Ask; pick: D.Pick }[], open: D.Ask[]): string {
  if (chosen.length === 0) return open.every((a) => a.expects === 'decision') ? 'Decide' : 'Answer'
  if (chosen.length > 1) return `Send ${chosen.length} answers`
  const [{ ask, pick }] = chosen
  /* Words alone on a decision about findings are a reply, and say so. */
  if (pick.kind === 'own' && D.decidesFindings(ask)) return 'Reply, leaving it open'
  return pick.kind === 'withdraw' ? 'Withdraw' : ask.expects === 'decision' ? 'Decide' : 'Answer'
}

/* A CHOICE NOT YET SENT IS THE FORM'S, NOT ITS DRAWING'S (Fluid Focus: one
   object drawn in a post, a section, a float or the primary place): kept by
   the form's key for the life of the tab, so a form drawn again elsewhere
   keeps what was chosen and typed, and every copy drawn at once shows the
   same draft. Answer still sends it, and the record says what was sent.

   IN MEMORY, FOR THE PAGE, AND NOWHERE ELSE: never the browser's storage, so
   a reload starts every form empty. Where the host asks (`DraftKeepContext`,
   Quiet Chat's Needs you, which shows the same question again after a
   reference was opened), a draft is also remembered with what it was made
   against (../draftKeep.ts) and discarded if the question no longer reads
   that way, and dropped when its question closes. Everywhere else -- legacy
   Fluid -- exactly as it was. */
const { drafts, madeFor, draftsTold } = K
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
  const sent = D.useSent()
  /* whether the host asks that a draft be kept only for the question it was
     made against (Quiet's Needs you); the draft itself is in memory, as always */
  const guarded = useContext(K.DraftKeepContext)
  const [picks, setPicks] = useDraft<Record<string, D.Pick | undefined>>(group.key + '|picks')
  const [texts, setTexts] = useDraft<Record<string, string>>(group.key + '|texts')
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [left, setLeft] = useState(false)
  const [busy, setBusy] = useState(false)
  const mine = group.asks.filter((a) => !!me && a.of === me)
  /* WHERE THE HOST ASKS: a draft is only for the question it was made against.
     When what is asked changes -- a question closes, here or anywhere, or
     reads otherwise than when the draft was made -- that draft is dropped,
     never applied to what is asked now. */
  const asked = mine.map((a) => `${a.id}:${a.response_present ? 'closed' : K.askSignature(a)}`).join(',')
  useEffect(() => {
    if (!guarded) return
    const gone = mine.filter((a) => {
      const k = group.key + '|' + a.id
      const held = !!picks[a.id] || !!texts[a.id]
      if (a.response_present) { madeFor.delete(k); return held }
      const made = madeFor.get(k)
      if (held && made && !K.stillFor(made, a, picks[a.id])) { madeFor.delete(k); return true }
      return false
    }).map((a) => a.id)
    if (!gone.length) return
    setPicks((p) => Object.fromEntries(Object.entries(p).filter(([k]) => !gone.includes(k))))
    setTexts((t) => Object.fromEntries(Object.entries(t).filter(([k]) => !gone.includes(k))))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guarded, group.key, asked])
  /* what the owner has just chosen or typed is made against the question as it reads now */
  useEffect(() => {
    if (!guarded) return
    for (const a of mine) {
      const k = group.key + '|' + a.id
      if (!a.response_present && (picks[a.id] || texts[a.id])) madeFor.set(k, K.madeAgainst(a, picks[a.id]))
      else madeFor.delete(k)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [guarded, group.key, picks, texts])
  if (mine.length === 0) return null
  const open = mine.filter((a) => !a.response_present)
  const lead = mine[0]
  const several = group.form !== null && mine.length > 1
  const post = group.post
  const locked = (a: D.Ask) => !!sent.get(a.id) && !a.response_present
  const chosen = open.filter((a) => picks[a.id] && !locked(a)).map((a) => ({ ask: a, pick: picks[a.id]!, text: texts[a.id] ?? '' }))
  /* Handing the work back is the composer's "+ continue" on an ask on its
     own post; a form's work resumes by itself when its last question closes. */
  const alone = group.form === null
  const author = post?.author ?? null
  /* NOT ON WORK FOUND ALONG THE WAY. Its options each select what happens to
     a finding (`selections`): choosing Pursue already starts that finding as
     its own work, and "+ continue" would start a second, empty request for
     the same carrier carrying only the option's words (2026-11-08). */
  const reconsidering = (lead.options ?? []).some((o) => !!o.selections)
  const canContinue = alone && !reconsidering && !!author && author !== me && chosen.length === 1 && chosen[0].pick.kind !== 'withdraw'
  const authorName = post?.author_alias ?? 'them'
  const sendNow = async (continuing: boolean) => {
    if (busy || chosen.length === 0) return
    setErrors({})
    setBusy(true)
    try {
      const got = await D.send(group, chosen, me, continuing ? author : null)
      /* ONLY WHAT THE SERVER SAID IT RECORDED LEAVES THE DRAFT. A refused
         answer and one whose outcome is not known keep the owner's words. */
      setPicks((p) => Object.fromEntries(Object.entries(p).filter(([k]) => !got.sent.includes(k))))
      setTexts((t) => Object.fromEntries(Object.entries(t).filter(([k]) => !got.sent.includes(k))))
      if (got.refused) setErrors({ [got.refused.ask]: got.refused.why })
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
            {(group.because ?? lead.because) && <> · because <Words>{group.because ?? lead.because}</Words></>}
          </div>
          {lead.stopped_work && <StoppedWorkLine w={lead.stopped_work} />}
          {group.operation && open.length > 0 && <OperationLine op={group.operation} by={lead.by_alias} question={several ? null : lead.question} />}
          {/* WHAT CLOSES AN ASK AND WHAT RECORDS NOTHING, once, before either is done. */}
          {open.length > 0 && <div className="rb-dec-why">{HINT + (open.some((a) => a.expects === 'decision') ? WITHDRAW_HINT : '')}</div>}
        </div>
      )}
      {mine.map((a, k) => {
        const l = sent.get(a.id)
        /* PER QUESTION, from this question's own expectation and its form row:
           a form-wide union would make one question's primary source appear to
           belong to another. A closed question stays a historical display --
           what it asked, what was chosen, and nothing added to it. */
        const status = P.statusOf(a, group)
        return (
          <fieldset key={a.id} className="rb-dec-q" data-question={a.id} data-presentation={status.state}
            data-state={a.withdrawn ? 'withdrawn' : a.response_present ? 'answered' : 'open'}>
            {a.question && <legend className="rb-dec-question">{several ? `${k + 1}. ` : ''}<Words>{a.question}</Words></legend>}
            {a.response_present
              ? <>
                  <Closed e={a} post={post} fresh={l?.phase === 'recorded' ? l : D.freshOf(a.id)} />
                  {/* however it closed (answered, withdrawn, no longer asked) */}
                  {l && l.phase !== 'recorded' && <Unconfirmed e={a} kept={l} />}
                </>
              : <>
                  <Presented ask={a} status={status} form={group} />
                  <Open e={a} pick={picks[a.id]} text={texts[a.id] ?? ''} kept={l} error={errors[a.id]}
                    declared={status} onForm={group.form !== null}
                    onPick={(p) => { setPicks((m) => ({ ...m, [a.id]: p })); setErrors({}) }}
                    onText={(t) => setTexts((m) => ({ ...m, [a.id]: t }))}
                    onTakeBack={(back) => { setPicks((m) => ({ ...m, [a.id]: back.pick })); setTexts((m) => ({ ...m, [a.id]: back.text })) }} />
                </>}
          </fieldset>
        )
      })}
      {open.length > 0 && (
        <div className="rb-form-foot rb-row rb-dec-foot">
          <span className="rb-form-status rb-muted" role="status">
            {open.some((a) => locked(a) && sent.get(a.id)!.phase === 'unknown') ? 'Not confirmed: see above'
              : open.some((a) => locked(a) && sent.get(a.id)!.phase === 'sending') ? 'Sending…'
                : open.some(locked) ? 'Recorded; reading what it did…'
                  : chosen.length ? `${chosen.length === 1 ? 'One answer' : `${chosen.length} answers`} chosen, not sent yet`
                    : several ? `${answered} of ${mine.length} answered`
                      : open.some((a) => !!a.answered_by)
                        ? `Your reply${open.find((a) => a.answered_by)!.answered_by!.number != null ? ` #${open.find((a) => a.answered_by)!.answered_by!.number}` : ''} is recorded; this is still open`
                        : 'Nothing sent yet'}
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
          {/* WHAT THE ONE ANSWER ACTION DOES, exactly: it records the answer and
              closes its question, and closing the last question of a form MAY
              let its Work resume under its existing rules. Neither "nothing
              runs" nor a promise that something will. */}
          <button type="button" className="btn primary" disabled={busy || chosen.length === 0}
            title={chosen.some((c) => c.pick.kind === 'withdraw') ? P.WITHDRAW_SAYS_FOOT : alone ? P.ANSWER_SAYS_ALONE : P.ANSWER_SAYS_FORM}
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
