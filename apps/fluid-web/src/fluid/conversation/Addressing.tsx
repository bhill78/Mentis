/* @ ADDRESSING ON POSTS AND REPLIES (A5, A10; missing capabilities).
 *
 *  - WHO A POST IS ADDRESSED TO, AND WHERE EACH STANDS (A5c, A10): a quiet
 *    line under its head, one face per name, the face's ring carrying the
 *    state -- waiting (a hollow ring), working (the live ring the
 *    participant strip uses), answered (a small check; pressed, it goes to
 *    their reply), replied, which settles nothing (Classic's ◑, a broken
 *    ring; pressed, to the reply too), failed / declined / stopped (a muted
 *    warm mark), nobody is carrying it (Classic's ⌀, in the attention ink)
 *    and asking you (the needs-you accent; pressed, it reads the post, where
 *    what it asks of you is shown). Hover or keyboard focus says it in words, so
 *    colour is never the only signal; past three, the rest fold into "+N"
 *    and come out on hover or focus.
 *  - EVERY STATE CLASSIC'S ADDRESSING MARKS SHOW (surfaces/Annotations.tsx)
 *    IS HERE, in Classic's own words: read from the same facts -- each
 *    post's `addressees` and `expectations` as production's batched
 *    `/api/turns?ids=` gives them, a read, only for posts that address
 *    somebody or carry a request -- and composed by the same rules. Their
 *    eleven marks fall into seven rings, none of Classic's states lost;
 *    the words keep them apart. Who
 *    is working now is the one activity reader's (identity/activity.ts).
 *  - ADDRESSING A POST ALREADY WRITTEN (A5a): "@" in its toolbar asks
 *    somebody to respond to it, through Fluid's existing command
 *    (`POST /fluid/api/posts/<id>/address`), as production's TurnActions
 *    `addressPop` does: the conversation's people, an optional note, one
 *    press each. One operation key per request, so a retry after a lost
 *    answer is the same request. */

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { ago, CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import * as nav from '../nav'
import { closeSheet, Sheet } from '../frame/Sheet'
import { newOp, repliesOf, store, type Id, type Post } from '../store'
import { Who } from '../identity/Who'
import { at as atName, usePeople } from '../identity/people'
import { live, useActivity, workingOnPosts } from '../identity/activity'
import { useFacts } from './facts'
import { useActions } from './PostCard'
import { bare } from './text'

/* -- the record's facts about a post's addressing (production's Turn view) -- */

interface ReadAddressee {
  participant: Id; alias: string; delivered: boolean; responded: boolean; failed: boolean | null
  addressed_later: boolean; addressed_by: string | null; addressed_because: string | null
}
interface ReadExpectation {
  id: Id; expects: string; of: Id | null; of_alias: string | null; by?: Id; by_alias: string
  response_present: boolean; live_execution: boolean; unassigned?: boolean; unresolved_because?: string | null
  satisfied_by?: Id[]; failures?: { because?: string | null }[]; delegations?: unknown[]
  withdrawn?: { by_alias?: string | null; because?: string | null; reply?: Id | null } | null
  lapsed?: { because?: string | null } | null
  answered_by?: { turn: Id; number: number | null } | null
}
interface Read { addressees: ReadAddressee[]; expectations: ReadExpectation[] }

/* Held per post AS IT READ when asked: a post that moves (a reply, a new
   request, an edit) is asked again. One read for every card drawn at once. */
const held = new Map<Id, { sig: string; read: Read | null }>()
const asked = new Map<Id, string>()
let tick = 0
const heard = new Set<() => void>()
const tell = () => { tick += 1; heard.forEach((fn) => fn()) }
let flushing = 0
const sigOf = (p: Post) => `${p.version}|${(p.expectations ?? []).join(',')}|${repliesOf(p)}|${(p.addressed_to ?? []).join(',')}`
const MOST = 64   // production's TURNS_PER_READ

function want(p: Post) {
  const sig = sigOf(p)
  if (held.get(p.id)?.sig === sig || asked.get(p.id) === sig) return
  asked.set(p.id, sig)
  if (flushing) return
  flushing = window.setTimeout(flush, 40)
}
async function flush() {
  flushing = 0
  const batch = [...asked.entries()].slice(0, MOST)
  for (const [id] of batch) asked.delete(id)
  if (asked.size) flushing = window.setTimeout(flush, 40)
  try {
    const res = await fluidFetch('/api/turns?ids=' + batch.map(([id]) => encodeURIComponent(id)).join(','), { headers: { ...CLIENT_HEADERS } })
    const body = await res.json()
    for (const row of body.turns ?? []) {
      const sig = batch.find(([id]) => id === row.id)?.[1] ?? ''
      held.set(row.id, { sig, read: row.turn ? { addressees: row.turn.addressees ?? [], expectations: row.turn.expectations ?? [] } : null })
    }
  } catch { /* drawn from what the post itself says until it can be read */ }
  tell()
}

function useRead(post: Post): Read | null {
  useSyncExternalStore((fn) => { heard.add(fn); return () => { heard.delete(fn) } }, () => tick)
  const needs = (post.addressed_to ?? []).length > 0 || (post.expectations ?? []).length > 0
  const sig = sigOf(post)
  useEffect(() => { if (needs) want(post) }, [needs, sig])  // eslint-disable-line react-hooks/exhaustive-deps
  return needs ? held.get(post.id)?.read ?? null : null
}

/* -- each fact in Classic's words, and the ring it is drawn with ------------ */

export type Ring = 'waiting' | 'working' | 'answered' | 'replied' | 'failed' | 'unclaimed' | 'asking'
interface Mark { who: Id; alias: string; ring: Ring; says: string; reply?: Id | null; replyNumber?: number | null }

function ofAddressee(a: ReadAddressee): Mark {
  const late = a.addressed_later
    ? `. They were brought in later by ${a.addressed_by ?? 'somebody'}${a.addressed_because ? `, because ${a.addressed_because}` : ''}`
    : ''
  const [ring, says]: [Ring, string] = a.failed ? ['failed', `${a.alias} was addressed, and delivery failed`]
    : a.responded ? ['answered', `${a.alias} was addressed and has answered`]
      : a.delivered ? ['waiting', `${a.alias} was addressed; it reached them and they have not answered yet`]
        : ['waiting', `${a.alias} was addressed; nothing has arrived from them yet`]
  return { who: a.participant, alias: a.alias, ring, says: says + late }
}

function ofExpectation(e: ReadExpectation, me: Id | null): Mark {
  const of = e.of_alias ?? 'nobody'
  const base = { who: e.of ?? '', alias: of }
  if (e.of && e.of === me && !e.response_present && !e.withdrawn && !e.satisfied_by?.length)
    return { ...base, ring: 'asking', says: `${e.by_alias} is asking you for a ${e.expects}` }
  if (e.unassigned)
    return { ...base, ring: 'unclaimed', says: `${e.by_alias} asked for a ${e.expects}, and nobody is carrying it${e.unresolved_because ? `: ${e.unresolved_because}` : ''}` }
  if (e.failures?.length)
    return { ...base, ring: 'failed', says: `${of} was to answer this, and it failed: ${e.failures[e.failures.length - 1].because ?? 'no reason was recorded'}` }
  if (e.delegations?.length)
    return { ...base, ring: 'waiting', says: `${of} handed ${e.delegations.length === 1 ? 'this on' : `this on ${e.delegations.length} ways`} and is waiting on somebody else. The request itself is still owed.` }
  if (e.live_execution) return { ...base, ring: 'working', says: `${of} is working on this now` }
  if (e.withdrawn)
    return { ...base, ring: 'failed', reply: e.withdrawn.reply ?? null, says: `${e.withdrawn.by_alias ?? of} withdrew this ${e.expects}${e.withdrawn.because ? `: ${e.withdrawn.because}` : ''}. It was not answered.` }
  if (e.lapsed)
    return { ...base, ring: 'failed', says: `${e.by_alias} no longer asks this: ${(e.lapsed.because ?? 'its run can no longer take an answer').replace(/^no longer asked: /, '')}. It was not answered.` }
  if (e.satisfied_by?.length)
    return { ...base, ring: 'answered', reply: e.answered_by?.turn ?? null, replyNumber: e.answered_by?.number ?? null, says: `${of} says this is answered. That is their claim about their own work, not a verification of it.` }
  if (e.response_present)
    return { ...base, ring: 'replied', reply: e.answered_by?.turn ?? null, replyNumber: e.answered_by?.number ?? null, says: `${of} has replied to this. Nothing claims the ${e.expects} itself is settled.` }
  return { ...base, ring: 'waiting', says: `${e.by_alias} is waiting on ${of} for a ${e.expects}` }
}

/** Which ring a face shows when the record says several things of one name:
 *  what is happening now first, then what asks for the reader, then what
 *  nobody carries, then what went wrong, then what is still awaited; a reply
 *  that settles nothing before a claim that it is answered. */
const FIRST: Ring[] = ['working', 'asking', 'unclaimed', 'failed', 'waiting', 'replied', 'answered']
const RING_WORD: Record<Ring, string> = {
  waiting: 'waiting', working: 'working on this now', answered: 'answered', replied: 'replied, which settles nothing',
  failed: 'failed, declined or stopped', unclaimed: 'nobody is carrying it', asking: 'asking you',
}
/* The small mark on the face, Classic's own glyph where the ring alone could
   be mistaken for another (surfaces/Annotations.tsx). */
const RING_MARK: Partial<Record<Ring, string>> = { answered: '✓', replied: '◑', failed: '✕' }
const GOES: Ring[] = ['answered', 'replied']

export interface Addressee { participant: Id; alias: string; ring: Ring; says: string[]; reply: Id | null; replyNumber: number | null }

/** Everyone a post is addressed to, each once, with where they stand. */
export function useAddressees(post: Post): Addressee[] {
  const read = useRead(post)
  const all = useActivity()
  const me = store.me
  const marks: Mark[] = read
    ? [...read.addressees.map(ofAddressee), ...read.expectations.map((e) => ofExpectation(e, me))]
    : (post.addressed_to ?? []).map((id) => ({ who: id, alias: '', ring: 'waiting' as Ring, says: 'addressed' }))
  /* Working now, by the one activity reader: said as Presence says it. */
  for (const w of workingOnPosts(all, [post.id]))
    marks.push({ who: w.participant, alias: w.alias, ring: 'working', says: `${atName(w.alias)}: working on this, started ${ago(w.working_on!.since)}` })
  const by = new Map<string, Addressee>()
  for (const m of marks) {
    const key = m.who || 'nobody:' + m.says
    const had = by.get(key)
    const ring = had && FIRST.indexOf(had.ring) <= FIRST.indexOf(m.ring) ? had.ring : m.ring
    by.set(key, {
      participant: m.who, alias: had?.alias || m.alias, ring,
      says: [...(had?.says ?? []), m.says].filter((s, i, xs) => xs.indexOf(s) === i),
      reply: had?.reply ?? m.reply ?? null, replyNumber: had?.replyNumber ?? m.replyNumber ?? null,
    })
  }
  return [...by.values()]
}

const SHOWN = 3

/** "→ ◌ @Quill ◉ @Atlas ✓ @Orbit": the post's addressees, each face
 *  ringed with where they stand, the words on hover or focus. */
export function Addressees({ post }: { post: Post }) {
  const all = useAddressees(post)
  const a = useActions()
  const people = usePeople(all.length > 0)
  if (!all.length) return null
  const aliasOf = (x: Addressee) => x.alias || people.data?.find((p) => p.participant === x.participant)?.alias || 'somebody'
  const rest = all.length - SHOWN
  const go = (x: Addressee) => (e: React.MouseEvent) => {
    e.stopPropagation()
    const where = post.home ?? a.readIn
    if (GOES.includes(x.ring) && x.reply) nav.read(where, x.reply, x.replyNumber ?? store.posts.get(x.reply)?.number ?? null)
    else if (GOES.includes(x.ring)) nav.openDetail({ kind: 'replies', root: post.id, anchor: { kind: 'post', id: post.id }, mode: 'aside' })
    else if (x.ring === 'asking') nav.read(where, post.id, post.number)
  }
  return (
    <div className={'fx-to' + (rest > 0 ? ' fx-to-folds' : '')} role="group" aria-label="addressed to" onClick={(e) => e.stopPropagation()}>
      <span className="fx-to-arrow" aria-hidden="true">→</span>
      {all.map((x, i) => {
        const name = x.participant ? atName(aliasOf(x)) : 'nobody'
        const says = x.says.map((s) => (s === 'addressed' ? `${name} was addressed` : s))
        const words = `${x.participant ? name : 'Nobody'}: ${RING_WORD[x.ring]}. ${says.join('. ')}`
        const acts = GOES.includes(x.ring) || x.ring === 'asking'
        const face = x.participant
          ? <Who id={x.participant} name={aliasOf(x)} show="avatar" size={18} working={x.ring === 'working'} />
          : <span className="fx-ad-nobody" aria-hidden="true">⌀</span>
        /* nobody carrying it is said by the ⌀ face itself; somebody named
           who carries nothing gets ⌀ as the mark */
        const mark = x.ring === 'unclaimed' ? (x.participant ? '⌀' : null) : RING_MARK[x.ring]
        const body = (
          <>
            <span className="fx-ad-face">{face}{mark && <i className="fx-ad-mark" aria-hidden="true">{mark}</i>}</span>
            <span className="fx-ad-name">{x.participant ? name : 'nobody'}</span>
            <span className="fx-ad-words" role="tooltip">{words}</span>
          </>
        )
        const cls = `fx-ad fx-ad-${x.ring}` + (i >= SHOWN ? ' fx-ad-extra' : '')
        return acts
          ? <button key={x.participant || i} type="button" className={cls} data-ring={x.ring} data-participant={x.participant || undefined} aria-label={words}
              title={GOES.includes(x.ring) ? (x.reply ? 'Go to their reply' : 'Open the replies') : 'Read the post: what it asks of you is shown with it'} onClick={go(x)}>{body}</button>
          : <span key={x.participant || i} className={cls} data-ring={x.ring} data-participant={x.participant || undefined} tabIndex={0} aria-label={words}>{body}</span>
      })}
      {rest > 0 && <span className="fx-to-more" aria-hidden="true">+{rest}</span>}
    </div>
  )
}

/* -- addressing a post already written -------------------------------------- */

export const addressSheet = (post: Id) => 'address:' + post

/** The Address pop: who to ask, and an optional note. Drawn only while open. */
export function AddressPop({ post, here }: { post: Post; here: Id | null }) {
  const facts = useFacts(here ?? post.home, false)
  const activity = useActivity()
  const [why, setWhy] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const attempt = useRef<{ request: string; op: string } | null>(null)
  /* This conversation's people, as production's addressPop lists them; one
     that declares nobody offers everybody the record holds, as the
     composer's `@` does, rather than nobody at all. */
  const declared = facts.data?.participants ?? []
  const everyone = usePeople(!facts.loading && !declared.length)
  const people = declared.length ? declared : facts.loading ? [] : everyone.data ?? []
  const num = post.number != null ? `#${post.number}` : 'this post'
  const ask = async (participant: Id, alias: string) => {
    if (busy) return
    setBusy(true)
    setErr(null)
    try {
      const me = await store.loadMe()
      const because = why.trim() || null
      const request = JSON.stringify({ post: post.id, participant, by: me, because })
      const op = attempt.current?.request === request ? attempt.current.op : newOp()
      attempt.current = { request, op }
      const got = await store.addressPost(post.id, participant, me, because, op)
      attempt.current = null
      closeSheet()
      nav.toast({ text: got.dispatched === 1 ? `Asked @${bare(alias)} to respond to ${num}.` : `${num} is addressed to @${bare(alias)}.` })
    } catch (e) {
      setErr((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Sheet id={addressSheet(post.id)} label={`address ${num}`} className="fx-address-pop">
      <p className="fx-pop-note">Ask someone to respond to {num}. Choose a name to send it.</p>
      {(facts.loading || everyone.loading) && !people.length && <p className="fx-faint">Reading who is here…</p>}
      {!facts.loading && !declared.length && people.length > 0 && <p className="fx-faint fx-pop-note">Nobody takes part here yet: everyone Mentis knows.</p>}
      {!facts.loading && !everyone.loading && !people.length && <p className="fx-faint">Nobody to ask.</p>}
      {people.map((p) => (
        <button key={p.participant} className="fx-opt fx-address-row" data-participant={p.participant} disabled={busy}
          onClick={() => void ask(p.participant, p.alias)}>
          <Who id={p.participant} name={p.alias} show="line" size={20} working={live(activity).some((w) => w.participant === p.participant)} />
        </button>
      ))}
      <input className="fx-address-why" placeholder="A note for them (optional)" aria-label="a note for them (optional)"
        value={why} disabled={busy} onChange={(e) => setWhy(e.target.value)} />
      {err && <p className="fx-address-err" role="alert">{err}</p>}
    </Sheet>
  )
}
