/* A POST'S STATUS, DRAWN (Track B, B2-B4).
 *
 *  - THE DOG-EAR: a small folded corner at the post's upper right, inside
 *    the reading column (the right margin is the annotations', Margin.tsx).
 *    Its colour says the post's one state at a glance -- restrained, and
 *    never the only signal: its shape differs too (hollow while nothing has
 *    started, half while replied or claimed but not recorded met, whole once
 *    something is running, failed or stopped, or recorded met), and its name
 *    says it in words. Its ink is --ok only for work recorded met or
 *    verified; a reply, an ended run and an agent's claim are neutral. It is
 *    not a bookmark: saving a post is the toolbar's, and changes nothing here.
 *  - PRESSED, A COMPACT STATUS VIEW beside it: everyone the post concerns,
 *    each with the three dimensions apart -- how they were addressed,
 *    acknowledgment (not recorded: Mentis keeps none), and their work and
 *    what it came to, with the times the record gives. One participant
 *    finishing among several is said of them, never of the post.
 *  - AT THE FOOT, ONE QUIET LINE of attribution from the same facts --
 *    "Addressed to @Caretaker", "Working: @Builder", "Met: @Caretaker",
 *    "Claimed, not met: @Builder" -- in place of the old request line; past
 *    three, "+N" opens the view. */
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { useLayer } from '../../fluid/frame/layer'
import { Avatar } from '../../fluid/identity/Who'
import { postOf } from '../real'
import { usePage } from '../Post'
import type { Working } from '../presence'
import type { Id, Post } from '../sample'
import { useRunModes } from '../activity/records'
import { attributionOf, clock, statusOf, timesOf, useConversationWork, useFollowStatus, usePostStatus, type Ask, type Party, type PartyState, type PostAct, type PostStatus } from './status'
import './status.css'

export interface StatusHandle {
  status: PostStatus | null
  acts: PostAct[] | null
  open: boolean
  setOpen: (open: boolean) => void
  /** the dog-ear, which the view is placed against and returns focus to */
  ear: React.RefObject<HTMLButtonElement | null>
  /** the post's own time, as a number, where the record gave it */
  postAt: number | null
  /** this drawing's view: the same post drawn twice has two */
  viewId: string
  real: boolean
}

/** A post's status, live while it is drawn, and whether its view is open. */
export function useStatus(post: Post, work: Working[]): StatusHandle {
  const [open, setOpenNow] = useState(false)
  const ear = useRef<HTMLButtonElement | null>(null)
  const viewId = useId()
  const got = usePostStatus(post.id, post.status, !!post.real)
  /* where each request's work stands, as the conversation's work overview says */
  const overview = useConversationWork(post.conversation ?? null, !!post.real && !!got.facts?.expectations.length)
  const status = statusOf(got.facts, work, { work: overview, claimActs: got.claimActs })
  /* followed on the pulse only while something on it is still owed (a claim
     not recorded met may still be reconciled) */
  const owed = !!post.real && !!status?.parties.some((p) => p.state === 'running' || p.state === 'waiting' || p.state === 'pending' || p.state === 'claimed')
  useFollowStatus(post.id, post.conversation ?? null, owed, !!status?.parties.some((p) => p.state === 'running'))
  const { readActs } = got
  const setOpen = useCallback((o: boolean) => { setOpenNow(o); if (o) readActs() }, [readActs])
  return { status, acts: got.acts, open: open && !!status, setOpen, ear, postAt: post.atTime ?? null, viewId: viewId + 'status', real: !!post.real }
}

const SHAPE: Record<PostStatus['state'], string> = {
  pending: 'hollow', waiting: 'hollow', replied: 'half', claimed: 'half', running: 'whole', attention: 'whole', completed: 'whole', verified: 'whole', closed: 'whole',
}

/** Two arrows passing each other (the owner's drawing): work handed over
 *  and back. Each arrowhead fills as the state does -- neither while nothing
 *  has come back, one once replied, both once something runs, failed, or is
 *  complete -- so colour is never the only signal. */
function Exchange({ size }: { size: number }) {
  const arrow = <>
    <path className="q2-st-shaft" d="M2.2 10.4 Q2.6 3.6 10 3.6 H11.6 M7 7.9 Q8 7.1 9.6 7.1 H11.6" />
    <path className="q2-st-head" d="M11.6 1 L17.4 5.35 L11.6 9.7 Z" />
  </>
  return (
    <svg viewBox="0 0 20 20" width={size} height={size} aria-hidden="true">
      <g className="q2-st-a">{arrow}</g>
      <g className="q2-st-b" transform="rotate(180 9.8 10)">{arrow}</g>
    </svg>
  )
}

/** The status mark. Drawn only where the post has a status. */
export function DogEar({ s, post }: { s: StatusHandle; post: Post }) {
  if (!s.status) return null
  const { state, label, summary } = s.status
  const words = `Status: ${label}. ${summary}.`
  return (
    <>
      <button ref={s.ear} type="button" className={`q2-st-ear q2-st-ear-${state} q2-st-${SHAPE[state]}`} data-status={state}
        aria-expanded={s.open} aria-controls={s.viewId} aria-label={`${words} Show who was addressed and where each stands.`}
        title={`${label} · ${summary}`} onClick={(e) => { e.stopPropagation(); s.setOpen(!s.open) }}>
        <Exchange size={18} />
      </button>
      {s.open && <StatusView s={s} post={post} />}
    </>
  )
}

/* -- the view ------------------------------------------------------------- */

const WIDTH = 340, EDGE = 8, GAP = 6, TOP = 60

const PARTY_LABEL: Record<PartyState, string> = {
  running: 'Working now', waiting: 'Waiting on somebody', failed: 'Failed or stopped', stopped: 'Stopped for a consent change', unclaimed: 'Nobody carrying it',
  pending: 'Addressed; no reply recorded', claimed: 'Claimed; not recorded met', replied: 'Replied; not marked complete',
  completed: 'Objective recorded met', verified: 'Recorded met; verified', closed: 'Closed without an answer',
}

const name = (p: Party) => (p.alias ? (p.alias.startsWith('@') ? p.alias : '@' + p.alias) : 'Nobody')

function StatusView({ s, post }: { s: StatusHandle; post: Post }) {
  const page = usePage()
  const card = useRef<HTMLDivElement>(null)
  const [at, setAt] = useState<{ left: number; top: number; maxHeight: number } | null>(null)
  const place = useCallback(() => {
    const m = s.ear.current?.getBoundingClientRect(), c = card.current
    if (!m || !c) return
    const vw = window.innerWidth, vh = window.innerHeight
    const width = Math.min(WIDTH, vw - 2 * EDGE)
    const h = c.scrollHeight
    const left = Math.min(Math.max(m.right - width, EDGE), vw - EDGE - width)
    const below = vh - EDGE - (m.bottom + GAP), above = m.top - GAP - TOP
    const next = h <= below || below >= above ? { left, top: m.bottom + GAP, maxHeight: Math.max(below, 140) }
      : { left, top: Math.max(TOP, m.top - GAP - h), maxHeight: above }
    setAt((was) => (was && was.left === next.left && was.top === next.top && was.maxHeight === next.maxHeight ? was : next))
  }, [s.ear])
  const { setOpen, ear } = s
  useLayoutEffect(() => {
    place()
    const away = (e: PointerEvent) => {
      const t = e.target as Node
      /* the line's "+N more" opens it, and only opens it */
      if (!card.current?.contains(t) && !ear.current?.contains(t) && !(t as Element).closest?.('.q2-st-more')) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return
      e.preventDefault(); setOpen(false); ear.current?.focus()
    }
    window.addEventListener('resize', place); window.addEventListener('scroll', place, true)
    document.addEventListener('pointerdown', away); document.addEventListener('keydown', esc)
    return () => {
      window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true)
      document.removeEventListener('pointerdown', away); document.removeEventListener('keydown', esc)
    }
  }, [place, setOpen, ear])
  /* FOCUS GOES TO THE VIEW as it opens (Margin's Card does the same), so
     a keyboard reader is in it; Escape brings it back to the dog-ear. It is
     drawn in the page's layer a moment later, so focused once it is placed. */
  const focused = useRef(false)
  useEffect(() => {
    if (!at || focused.current) return
    /* the layer draws the placed card a frame later (until then it is
       hidden, and cannot take focus): tried each frame until it has it */
    let tries = 0, frame = 0
    const go = () => {
      const c = card.current
      c?.focus({ preventScroll: true })
      if (c && document.activeElement === c) focused.current = true
      else if (++tries < 10) frame = requestAnimationFrame(go)
    }
    frame = requestAnimationFrame(go)
    return () => cancelAnimationFrame(frame)
  }, [at])
  /* the acts arriving make it taller: placed again */
  useEffect(() => { place() }, [s.acts, s.status, place])
  const st = s.status!
  const num = post.number ? `#${post.number}` : 'this post'
  const toReply = (turn: Id) => page.onEnter(post.root ?? post.id, turn)
  useLayer(
    <div ref={card} id={s.viewId} tabIndex={-1} className="q2-st-pop" role="dialog" aria-label={`Status of ${num}`}
      style={at ? { left: at.left, top: at.top, maxHeight: at.maxHeight, width: Math.min(WIDTH, window.innerWidth - 2 * EDGE) } : { left: 0, top: 0, width: WIDTH, visibility: 'hidden' }}>
      <div className="q2-st-head">
        <span className={`q2-st-swatch q2-st-ear-${st.state} q2-st-${SHAPE[st.state]}`} aria-hidden="true">
          <Exchange size={13} />
        </span>
        <b>{st.label}</b><span className="q2-st-sum">{st.summary}</span>
      </div>
      <ul className="q2-st-parties">
        {st.parties.map((p, i) => <PartyRow key={p.participant ?? 'nobody' + i} p={p} acts={s.acts} postAt={s.postAt} real={s.real} toReply={toReply} toPost={page.onEnter} />)}
      </ul>
      <p className="q2-st-note">Acknowledgment is not recorded: Mentis keeps no act by which a participant accepts a request. A delivery or a reply is not one.
        {!s.acts && post.real ? ' Reading the times…' : ''}</p>
    </div>,
  )
  return null
}

function PartyRow({ p, acts, postAt, real, toReply, toPost }: {
  p: Party; acts: PostAct[] | null; postAt: number | null; real: boolean; toReply: (turn: Id) => void; toPost: (root: Id, turn: Id) => void
}) {
  const t = timesOf(acts, p, postAt)
  const a = p.addressed
  const addressed = a
    ? a.addressed_later ? `Brought in later by ${a.addressed_by ?? 'somebody'}${a.addressed_because ? `: ${a.addressed_because}` : ''}` : 'Named on the post'
    : p.asks.length ? `Asked through ${p.asks.length === 1 ? 'a request' : `${p.asks.length} requests`} by ${[...new Set(p.asks.map((x) => x.fact.by_alias))].join(', ')}`
      : 'Not addressed; working on it'
  const working = p.work.filter((w) => !w.waiting), waits = p.work.filter((w) => w.waiting)
  const work: string[] = []
  if (working.length) work.push(`Working now${working[0].doing ? `: ${working[0].doing}` : ''}${working[0].simulated ? ' (sample: simulated)' : ''}`)
  if (waits.length) work.push(`Its run waits on a decision: ${waits[0].waiting}`)
  if (t?.awaiting) work.push(`Waiting on other work since ${clock(t.awaiting.at)}${t.awaiting.because ? `: ${t.awaiting.because}` : ''}`)
  if (t && p.participant) work.push(t.runs.length ? `${t.runs.length === 1 ? 'A run started' : `${t.runs.length} runs started; the latest`} ${clock(t.runs[t.runs.length - 1])}` : 'No run of theirs started on this post')
  else if (real && !working.length && p.participant) work.push('Runs: reading…')
  /* THE LATEST RUN'S PERMISSION AND EXECUTION, as the server says them
     (`/api/runs/<run>/consent`): Permission Mode, Execution Mode and the
     isolation MARS reported, and how the consent is enforced -- never said
     as enforced unless the server says it is */
  const modes = useRunModes(t?.lastRun ?? null)
  if (modes) work.push(...modes.lines)
  return (
    <li className={`q2-st-party q2-st-p-${p.state}`}>
      <div className="q2-st-who">
        {p.participant ? <Avatar id={p.participant} name={p.alias ?? ''} size={18} /> : <span className="q2-st-nobody" aria-hidden="true">⌀</span>}
        <b>{name(p)}</b><span className="q2-st-word">{p.state === 'completed' && p.asks.length && p.asks.every((x) => x.state === 'answered') ? 'Answered'
          : p.state === 'replied' && !p.asks.length ? 'Replied' : PARTY_LABEL[p.state]}</span>
      </div>
      <dl className="q2-st-dims">
        <dt>Addressed</dt><dd>{addressed}{t?.asked ? <> · <time>{clock(t.asked)}</time></> : null}</dd>
        {a && (a.delivered || a.failed) ? <><dt>Reached</dt><dd>{a.failed ? 'Delivery failed' : 'A delivery to them is recorded'}</dd></> : null}
        {p.participant && <><dt>Acknowledged</dt><dd className="q2-st-unknown">Not recorded</dd></>}
        {work.length > 0 && <><dt>Work</dt><dd>{work.map((w, i) => <span key={i} className="q2-st-line-item">{w}</span>)}
          {modes?.enforcement && <span className="q2-st-line-item q2-st-enforce" data-enforced={modes.enforcement.enforced ? 'yes' : 'no'}>{modes.enforcement.words}</span>}</dd></>}
        {(p.asks.length > 0 || (a && !p.asks.length && (a.responded || a.failed))) && (
          <><dt>Outcome</dt><dd>
            {/* the same words for several requests (a run's five lapsed
                questions) said once, with each one's time */}
            {groups(p.asks).map((g) => <AskLine key={g[0].fact.id} xs={g} toReply={toReply} toPost={toPost} />)}
            {a && !p.asks.length && (a.failed ? <span className="q2-st-line-item">Delivery to them failed.</span>
              : a.responded ? <span className="q2-st-line-item">They have replied. Nothing was asked of them that could be marked complete.</span> : null)}
          </dd></>
        )}
      </dl>
    </li>
  )
}

const groups = (asks: Ask[]): Ask[][] => {
  const by = new Map<string, Ask[]>()
  for (const x of asks) by.set(x.words, [...(by.get(x.words) ?? []), x])
  return [...by.values()]
}

/** When an ask reached the state it is in, where the record says. */
const whenOf = (x: Ask) => x.state === 'withdrawn' ? x.fact.withdrawn?.at : x.state === 'lapsed' ? x.fact.lapsed?.at
  : x.state === 'failed' ? x.fact.failures?.[x.fact.failures.length - 1]?.at : undefined

function AskLine({ xs, toReply, toPost }: { xs: Ask[]; toReply: (turn: Id) => void; toPost: (root: Id, turn: Id) => void }) {
  const x = xs[0]
  const whens = xs.map(whenOf).filter((t): t is number => !!t)
  const all = (x.state === 'completed' || x.state === 'verified' || x.state === 'claimed' || x.state === 'answered' || x.state === 'replied' || x.state === 'handed-on')
    ? xs.map((y) => y.fact.answered_by).filter((r): r is { turn: Id; number: number | null } => !!r) : []
  const replies = all.slice(0, 3)
  const c = x.claim
  /* the claim in the agent's own words, apart from what the record made of
     it (said above): its summary, evidence, and every reason it is held */
  const claimed = c && xs.length === 1 ? [
    c.summary && c.recorded !== 'partly' && c.recorded !== 'not-met' ? `Their claim${c.by ? ` (${c.by.startsWith('@') ? c.by : '@' + c.by})` : ''}: ${c.summary}` : null,
    c.evidence.length ? `Evidence they name: ${c.evidence.slice(0, 3).join('; ')}${c.evidence.length > 3 ? ` (+${c.evidence.length - 3} more)` : ''}` : null,
    c.recorded === 'pending' && c.reasons.length > 1 ? `Also pending: ${c.reasons.slice(1).join('; ')}` : null,
    c.recorded === 'met' && x.state === 'completed' ? 'Recorded met from their claim, after the checks; not independently verified' : null,
  ].filter((s): s is string => !!s) : []
  const later = xs.length === 1 ? x.work?.later_findings ?? [] : []
  return (
    <span className="q2-st-line-item">
      {xs.length > 1 ? <b>{xs.length} requests: </b> : null}{x.words}
      {claimed.map((w, i) => <span key={i} className="q2-st-times">{w}</span>)}
      {/* LATER FINDINGS: records linked to this work afterwards. Neutral:
          nothing is reopened by them, and the state above is unchanged. */}
      {later.length > 0 && <span className="q2-st-times q2-st-later">Noted later: {later.slice(0, 4).map((f, i) => {
        const held = postOf(f.id)
        const what = `${f.kind ?? 'a record'}${f.at ? ` · ${clock(Date.parse(f.at) / 1000)}` : ''}`
        return <span key={f.id}>{i ? '; ' : ''}{held
          ? <button type="button" className="q2-st-go" title={f.id} onClick={() => toPost(held.root ?? held.id, held.id)}>{what}</button>
          : <span title={f.id}>{what}</span>}</span>
      })}{later.length > 4 ? ` (+${later.length - 4} more)` : ''}</span>}
      {x.spec && <Spec text={x.spec} />}
      {whens.length > 0 && <span className="q2-st-times">{whens.map((t, i) => <time key={i}>{(i ? ' · ' : '') + clock(t)}</time>)}</span>}
      {replies.map((r) => {
        const replyAt = postOf(r.turn)?.at
        return <span key={r.turn} className="q2-st-times"><button type="button" className="q2-st-go" onClick={() => toReply(r.turn)}>Their reply{r.number ? ` #${r.number}` : ''}</button>{replyAt ? ` · ${replyAt}` : ''}</span>
      })}
      {all.length > replies.length && <span className="q2-st-times">and {all.length - replies.length} more replies</span>}
    </span>
  )
}

/** What was asked, in the asker's own words: a line at first, whole on
 *  request (and whole in its title). */
const SPEC = 140
function Spec({ text }: { text: string }) {
  const [whole, setWhole] = useState(false)
  const long = text.length > SPEC
  return (
    <span className="q2-st-spec" title={long && !whole ? text : undefined}>
      “{whole || !long ? text : text.slice(0, SPEC - 1).trimEnd() + '…'}”
      {long && <> <button type="button" className="q2-st-go" aria-expanded={whole} onClick={() => setWhole(!whole)}>{whole ? 'less' : 'all of it'}</button></>}
    </span>
  )
}

/* -- the attribution line ------------------------------------------------- */

const LINE = 3

export function StatusLine({ s }: { s: StatusHandle }) {
  if (!s.status) return null
  const ps = s.status.parties
  const rest = ps.length - LINE
  return (
    <p className="q2-st-line">
      {ps.slice(0, LINE).map((p, i) => (
        <span key={p.participant ?? 'nobody' + i} className={`q2-st-at q2-st-at-${p.state}`}>{attributionOf(p)}</span>
      ))}
      {rest > 0 && <button type="button" className="q2-st-more" aria-expanded={s.open}
        onClick={(e) => { e.stopPropagation(); s.setOpen(true) }}>+{rest} more</button>}
    </p>
  )
}
