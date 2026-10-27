/* WHAT NEEDS YOU, IN A ZONE (#576). A zone whose Show is "What needs you"
 * follows the post being read like any following zone, and shows what on
 * that post or anywhere in its thread needs the owner -- Home's Needs you
 * rule asked of one post (`GET /fluid/api/needs-you?post=`). Each is Home's
 * Needs you card: where it was asked and when, who asked, and the request
 * itself as the decision form every view draws (forms build P9,
 * experimental/types/decision.tsx), answered in place, or opened.
 *
 * ANSWERING IS THE FORM'S ANSWER, NOT A SECOND ONE. The form posts the same
 * reply the post's own form posts (experimental/decisions.ts): record-only,
 * replying to the asking post, addressed to its author, naming the question.
 * Recorded is what the record says afterwards. A request that left Needs
 * you any other way -- handed to somebody else, closed -- says that, as the
 * record has it (`state`, home._ask_rows).
 *
 * ONE FORM, HOWEVER MANY QUESTIONS AND CARDS. The questions of one decision
 * form are one card, drawn as the whole form. What is being sent for a
 * question is held by its id, so every copy of the form locks while it is
 * sent and says what landed. A following zone leaves out what another zone
 * on the page keeps, and says it is kept there.
 *
 * A BLOCK WAITING FOR YOUR INPUT IS DRAWN AS THAT BLOCK (P11). An ask
 * `request_input` declared is answered by Done on the block, never by a
 * reply, so its card draws the block itself -- the same fence, part and
 * names the post card draws it with (conversation/text.ts `blockFence`), so
 * it is the same block with the same kept answers -- until Done.
 *
 * KEPT LIKE ANY OTHER OBJECT: ◆ Keep holds it in this zone by its address
 * (`needs-you:<request>`) while other posts are read, and it can be dragged
 * to another zone; a kept one says when it has been answered. */

import { useCallback, useContext, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { ago } from '../../api'
import { DecisionsOn } from '../../experimental/types/decision'
import { namesFor, turnPartScope } from '../../experimental/objects'
import { Prose } from '../../prose'
import { blockFence } from '../conversation/text'
import { GovContext } from '../governance/context'
import { Who } from '../identity/Who'
import { store, type Ask, type Id, type NeedsYouOn } from '../store'
import { trace } from '../workspace/from'
import { usePost } from '../workspace/hooks'
import { DRAG } from '../workspace/keep'
import './needs-you.css'

/** A request kept in a zone, by address. */
export const ASK = 'needs-you:'
export const isAsk = (address: string) => address.startsWith(ASK)

function useKey<T>(key: string, read: () => T): T {
  const sub = useCallback((fn: () => void) => store.subscribe(key, fn), [key])
  return useSyncExternalStore(sub, read)
}
const useAsk = (id: Id) => useKey('ask:' + id, () => store.asks.get(id))
const useOn = (post: Id) => useKey('needs-you:' + post, () => store.needsYouOn.get(post))

/** How each state is shown: its badge, and the existing state class it takes. */
const BADGES: Record<Ask['state'], [string, string]> = {
  open: ['Needs you', 'fw-state-needs-you'],
  answered: ['Answered', 'fw-state-completed'],
  withdrawn: ['Withdrawn', 'fw-state-ended'],
  elsewhere: ['No longer needs you', 'fw-state-ended'],
  closed: ['No longer needs you', 'fw-state-ended'],
}

const bare = (n: string) => '@' + n.replace(/^@/, '')

/** The asking post's first line, as Home's card heads an ask. */
function useLead(post: Id | null): string | null | undefined {
  const p = usePost(post ?? '')
  useEffect(() => { if (post && !p) void store.loadPosts([post]).catch(() => {}) }, [post, p])
  if (!post) return null
  if (!p) return undefined
  const text = p.parts.filter((x) => x.type === 'text').map((x) => x.text ?? '').join('')
  const line = text.split('\n').map((l) => l.replace(/^[#>*\-\s]+/, '').replace(/\*\*/g, '').trim()).find(Boolean)
  return line ? (line.length > 160 ? line.slice(0, 159).trimEnd() + '…' : line) : null
}

/** The block an input waits on, drawn as its post draws it, answered here. */
function InputBlock({ post, block }: { post: Id; block: NonNullable<Ask['block']> }) {
  const p = usePost(post)
  useEffect(() => { if (!p) void store.loadPosts([post]).catch(() => {}) }, [post, p])
  if (!p) return <p className="wk-quietline" aria-busy="true">Reading the block…</p>
  const text = p.parts[block.part]?.text ?? ''
  const fence = blockFence(text, block.block)
  if (!fence) return <p className="wk-quietline">The block “{block.block}” is not on the post now.</p>
  const scope = turnPartScope(p.id, block.part)
  return (
    <div className="nyc-block turn-body" data-input-block={block.block}>
      <Prose src={fence} scope={scope} names={namesFor(text, scope)} />
    </div>
  )
}

/** One request, as Home's Needs you card heads it, answerable here as its form. */
function AskCard({ id, kept, zone, page, onRemove, onKeep }: {
  id: Id; kept: boolean; zone: string; page: string; onRemove?: () => void; onKeep?: () => void
}) {
  const a = useAsk(id)
  const gov = useContext(GovContext)
  const lead = useLead(a?.post ?? null)
  const [deferred, setDeferred] = useState(false)
  if (!a) return <div className="wk-obj fw-needs-you-card nyc fw-pending" aria-busy="true" data-ask={id} data-address={ASK + id}>Reading…</div>
  if (deferred) return null
  const isAdoption = a.expects === 'adoption' || Boolean(a.because && /adopt/i.test(a.because))
  const where = `${a.conversation_name ?? 'a conversation'}${a.post_number != null ? ` · #${a.post_number}` : ''}`
  const num = a.post_number != null ? `#${a.post_number}` : 'the post'
  const [badge, tone] = BADGES[a.state] ?? BADGES[a.open ? 'open' : 'closed']
  /* The form, while it is the owner's to answer or says what they did. An
     input's block is drawn while it waits: after Done it is answered. */
  const isInput = a.expects === 'input'
  const drawn = !isAdoption && !isInput && (a.open || a.state === 'answered' || a.state === 'withdrawn')
  return (
    <article className="wk-obj fw-needs-you-card nyc" data-ask={a.id} data-address={ASK + a.id} data-needs-you={a.id} data-open={a.open || undefined}
      draggable onDragStart={(e) => {
        e.dataTransfer.setData(DRAG, JSON.stringify({ address: ASK + a.id, kept, zone, page }))
        e.dataTransfer.effectAllowed = 'copyMove'
      }}>
      <header className="fw-work-card-head">
        <span className={'fw-badge fw-state-badge ' + tone} data-state={a.state}>{badge}</span>
        <span className="fw-where" title={where}>{where}</span>
        {a.at != null && <time className="fw-time">{ago(a.at)}</time>}
        {kept && <span className="wk-quiet nyc-kept">kept here</span>}
      </header>
      <div className="fw-work-what">{lead || `${bare(a.asked_by_name)} asks you ${isAdoption ? 'to adopt' : `for a ${a.expects ?? 'response'}`}`}</div>
      <div className="wk-quiet"><Who id={a.asked_by} name={a.asked_by_name} show="line" size={16} live meta={`asked${a.because ? ` · because ${a.because}` : ''}`} /></div>
      {a.state === 'elsewhere' && (
        <div className="wk-quiet nyc-now">It's with {a.carrier_name ? <Who id={a.carrier} name={a.carrier_name} show="line" size={16} live /> : 'somebody else'} now{a.answered ? ', who has answered it' : ''}.</div>
      )}
      {a.state === 'closed' && <div className="wk-quiet nyc-now">It asks nothing of you now.</div>}
      {isInput && a.open && a.post && a.block && (
        <div className="nyc-form" draggable={false} onDragStart={(e) => e.stopPropagation()}>
          <InputBlock post={a.post} block={a.block} />
        </div>
      )}
      {isInput && a.state === 'answered' && <div className="wk-quiet nyc-now">Done: you marked it ready.</div>}
      {drawn && (
        <div className="nyc-form" draggable={false} onDragStart={(e) => e.stopPropagation()}>
          <DecisionsOn post={a.post} ids={a.post ? undefined : [a.id]} only={[a.id]}
            onChanged={() => { void store.step().catch(() => {}); void store.loadAsks([a.id]).catch(() => {}) }} />
        </div>
      )}
      <div className="wk-acts">
        {isAdoption && gov && (
          <>
            <button type="button" onClick={() => gov.openGov('adoption')}>Open adoption card →</button>
            <button type="button" onClick={() => setDeferred(true)}>Not now</button>
          </>
        )}
        {a.post && <button type="button" onClick={() => { if (a.post) { void store.loadPosts([a.post]).then(() => trace(a.post!)) } }}
          title={`Opens ${num}, where it was asked. Records nothing.`}>Open {num}</button>}
        {onKeep && <button type="button" className="fw-keep" onClick={onKeep} title="Keep it here while you read other posts">◆ Keep</button>}
        {onRemove && <button type="button" onClick={onRemove} title="Stop keeping it here">Remove</button>}
      </div>
    </article>
  )
}

/** One card per decision form: the first of its questions here stands for it. */
function oneEach(ids: Id[]): Id[] {
  const seen = new Set<Id>()
  return ids.filter((id) => {
    const f = store.asks.get(id)?.form
    if (!f) return true
    if (seen.has(f)) return false
    seen.add(f)
    return true
  })
}

/** What a zone shows of what needs you: what is kept in it, then what on
 *  the post read (or its thread) needs the owner. */
export function NeedsYou({ post, everywhere = false, number, kept, elsewhere = [], zone, page, onKeep, onRemove }: {
  /** the post being read, when the zone follows and shows What needs you */
  post: Id | null
  /** nothing is being read: every open item, one card per form (P11) */
  everywhere?: boolean
  number: number | null
  /** request ids kept in this zone */
  kept: Id[]
  /** request ids another zone on this page keeps: not shown again here */
  elsewhere?: Id[]
  zone: string
  page: string
  onKeep: (id: Id) => void
  onRemove: (id: Id) => void
}) {
  const on: NeedsYouOn | undefined = useOn(post ?? '')
  const [failed, setFailed] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!post) return
    let live = true
    setFailed(null)
    store.loadNeedsYouOn(post).catch((e) => { if (live) setFailed(String((e as Error)?.message ?? e)) })
    return () => { live = false }
  }, [post, attempt])
  const keptKey = kept.join(',')
  useEffect(() => {
    const want = keptKey ? keptKey.split(',').filter((id) => !store.asks.has(id)) : []
    if (want.length) void store.loadAsks(want).catch(() => {})
  }, [keptKey])
  /* NOTHING READ: EVERYTHING WAITING (P11), one card per item, as the bell lists it. */
  const all = useKey('needs-items', () => store.needsItems)
  useEffect(() => { if (everywhere) void store.loadNeedsItems().catch(() => {}) }, [everywhere])
  const everyKey = everywhere && all && !all.unknown ? all.items.map((it) => it.asks[0]).join(',') : ''
  useEffect(() => {
    const want = everyKey ? everyKey.split(',').filter((id) => !store.asks.has(id)) : []
    if (want.length) void store.loadAsks(want).catch(() => {})
  }, [everyKey])
  const [held, setHeld] = useState<Id[]>([])
  useEffect(() => setHeld([]), [post])
  const items = on?.items ?? []
  useEffect(() => {
    if (items.length) setHeld((h) => [...new Set([...h, ...items])])
  }, [items.join(',')]) // eslint-disable-line react-hooks/exhaustive-deps
  const keptSet = useMemo(() => new Set(kept), [keptKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const elsewhereKey = elsewhere.join(',')
  const there = useMemo(() => new Set(elsewhere), [elsewhereKey]) // eslint-disable-line react-hooks/exhaustive-deps
  const shown = held.filter((id) => !keptSet.has(id) && (items.includes(id) || store.asks.get(id)?.open === false))
  const followed = oneEach(shown.filter((id) => !there.has(id)))
  const away = shown.length - followed.length
  const n = number != null ? `#${number}` : 'this post'
  const every = everyKey ? everyKey.split(',').filter((id) => !keptSet.has(id) && !there.has(id)) : []
  return (
    <div className="nyc-list" data-needs-you-zone={post ?? ''}>
      {kept.map((id) => <AskCard key={'k' + id} id={id} kept zone={zone} page={page} onRemove={() => onRemove(id)} />)}
      {followed.map((id) => <AskCard key={id} id={id} kept={false} zone={zone} page={page} onKeep={() => onKeep(id)} />)}
      {!post && every.map((id) => <AskCard key={'e' + id} id={id} kept={false} zone={zone} page={page} onKeep={() => onKeep(id)} />)}
      {!post && everywhere && all?.unknown && <p className="wk-quietline">Unknown: this brain names no owner, so what is asked of you can't be read.</p>}
      {!post && everywhere && all && !all.unknown && all.items.length === 0 && kept.length === 0 && (
        <p className="wk-quietline">Nothing is waiting on you.</p>
      )}
      {post && failed && (
        <p className="wk-quietline wk-failed" role="alert">
          Couldn't read what needs you on {n} ({failed}).{' '}
          <button className="wk-retry" onClick={() => setAttempt((x) => x + 1)}>Retry</button>
        </p>
      )}
      {post && on?.unknown && <p className="wk-quietline">Unknown: this brain names no owner, so what is asked of you on {n} can't be read.</p>}
      {away > 0 && <p className="wk-quietline">{away === 1 ? 'One more is' : `${away} more are`} kept in another zone here.</p>}
      {post && on && !on.unknown && shown.length === 0 && kept.length === 0 && (
        <p className="wk-quietline">Nothing on {n} or its thread needs you.</p>
      )}
    </div>
  )
}
