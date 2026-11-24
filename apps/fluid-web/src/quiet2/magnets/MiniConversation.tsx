/* THE MAGNET'S CONVERSATION, DRAWN BY MENTIS'S OWN CONVERSATION (owner §5).
 *
 * There is no second conversational experience here. A post in this card is
 * drawn by `quiet2/Post.tsx` and its replies by `quiet2/Thread.tsx` -- the same
 * components the reading column uses -- reading the same one store of posts
 * (`quiet2/real.ts`), so Markdown, pictures, attached files, replies, the
 * byline, the time and the post's operational status are the conversation's
 * own and are not re-implemented. What used to live here (a private `Words`,
 * `PostView` and `WorkLine`) is gone, not reproduced.
 *
 * WHAT MAKES IT THE MAGNET'S. The page those shared components are given
 * (`PostPage`) is bounded to this card: replying aims the card's own footer
 * composer, a thread is read inside the card, a reference in a post's words
 * opens as evidence inside the card (`RefIndex`'s `openEntry`), and there is no
 * working surface, no Brain navigation and no annotation margin to take the
 * owner out of the Magnet. Nothing here replaces or rearranges the surrounding
 * workspace.
 *
 * THIS IS THE CONVERSATION VIEW, NOT THE COMPOSER. The composer is persistent
 * and lives in the frame's footer slot, on every tab (`ComposerBar.tsx`); this
 * view reads and shows the Conversation the bar writes into, and the two share
 * one store (`miniConversationOf`) for everything that is written: the owner it
 * writes as, an unresolved send, the reply target and this Magnet's own
 * Conversation. Reading is the shared store's, writing is the Magnet store's. */

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { useBrainBound } from '../../brainBinding'
import { RefIndex } from '../../refs'
import Post, { PageContext, type PostPage } from '../Post'
import { ReplyFold, ThreadView } from '../Thread'
import { postOf, readThread, threadRootOf, useRealFlow, usePosts } from '../real'
import type { Id, Post as PostT } from '../sample'
import type { Viewable } from '../viewer/types'
import type { MagnetResource } from './contract'
import {
  NO_OWN_CONVERSATION, miniConversationOf, type MiniPost,
} from './conversation'
import './conversation.css'
import { restore, writePlace } from './places'

/** NO EXTERNAL NAVIGATION IS PASSED INTO THIS VIEW (owner §3). A Magnet is a
 *  self-contained working surface, so the Conversation view takes what it needs
 *  to work here -- writing, and reading a citation inside the card -- and
 *  nothing that takes the owner somewhere else. Leaving the card is the one
 *  explicit contextual action in Settings ("Navigate to full Magnet
 *  Conversation"), reached deliberately, not a link standing above the posts on
 *  every open. The return behaviour below is the opposite thing and stays: it
 *  is drawn only when the owner actually came from somewhere. */
export interface MiniConversationProps {
  resource: MagnetResource
  canWrite: boolean
  onEvidence?(ref: string): void
}

/** The reply target the Magnet's own store keeps, built from the post the owner
 *  actually pressed Reply on. The number and the author are the record's, read
 *  from the shared store, so the composer can say WHICH post is being answered
 *  instead of "a post" (owner §6). Only `id`, `number` and `authorAlias` are
 *  read by `store.replyTo`; the rest is this post as the shared store holds it. */
export function replyTargetOf(p: PostT): MiniPost {
  return {
    id: p.id,
    number: p.number ?? null,
    authorAlias: p.by.name,
    agent: !!p.by.agent,
    at: p.atTime ?? 0,
    text: p.text ?? '',
    replyTo: p.replyTo ?? null,
    replyNumber: p.replyNumber ?? null,
    root: p.root ?? null,
    replies: p.threadCount ?? 0,
    work: [],
    deleted: false,
  }
}

/** WHAT A MESSAGE FOUND IN THE SEARCH ASKS THIS VIEW FOR: the exact post, by
 *  its id, from the one target the card carries (`MagnetSearchTarget.message`).
 *  Null for every other kind of result, and for a target that names no message:
 *  this view never guesses which post a result meant. */
export const messageTargetOf = (s: { searchTarget: { kind: string; message?: string } | null }): string | null =>
  s.searchTarget && s.searchTarget.kind === 'Conversation' && s.searchTarget.message ? s.searchTarget.message : null

/** A PLAIN REFERENCE, as Prose marks one in the words it drew
 *  (`data-src-text`): exactly `ent-`/`opr-`/`adm-` and its hex, and nothing
 *  else. A citation of extracted text carries a range as well and is not one. */
const PLAIN_REFERENCE = /^(?:ent|opr|adm)-[0-9a-f]{8,}$/

/** THE REFERENCE A CLICK INSIDE A POST'S WORDS LANDED ON, or null. Prose draws
 *  every reference an agent wrote as Mentis's own reference component and marks
 *  the span it stands for with the stored text; the card reads that mark, so a
 *  citation is opened as evidence HERE whatever kind of reference it is --
 *  which is what the card did before it drew Mentis's own post, and is what
 *  keeps a Magnet self-contained. */
export function referenceClicked(target: Element | null): string | null {
  const marked = target?.closest<HTMLElement>('[data-src-text]')
  if (!marked || !marked.closest('.q2-body')) return null
  const said = marked.getAttribute('data-src-text') ?? ''
  return PLAIN_REFERENCE.test(said) ? said : null
}

/** Where a reference opened from inside the card goes: the `adm-` or `ent-`
 *  this viewable stands for, or null when it stands for nothing the card can
 *  show inside itself (a picture built for the viewer, say). */
export function refOfViewable(v: Viewable): string | null {
  if (v.kind === 'file') return v.item.ref || null
  if (v.kind === 'pdf') return null
  return null
}

/** WHERE A POST SITS IN THE CARD'S ONE SCROLL CONTAINER. Returned as the offset
 *  to keep in the Conversation's place, so the frame applies it through exactly
 *  the machinery that restores a reading position -- nothing here scrolls the
 *  DOM itself, and nothing moves the surrounding workspace. */
export function offsetInBox(el: { top: number }, box: { top: number; scrollTop: number }, gap = 12): number {
  return Math.max(0, Math.round(el.top - box.top + box.scrollTop - gap))
}

export default function MiniConversation({ resource, canWrite, onEvidence }: MiniConversationProps) {
  const bound = useBrainBound()
  const working = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  /* The same store the footer composer writes through: two would read this
     Conversation twice and could disagree about what was sent. It is not
     disposed here -- it outlives this view, as the composer does. */
  const { store } = miniConversationOf(resource, canWrite, bound)
  const s = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  /* redrawn whenever the one shared store of posts changes, which is how an
     agent's reply arrives: `useRealFlow` reads this Conversation again on the
     page's existing /api/pulse beat (real.ts `flowMoved`, `FLOW_SPACING`).
     No second poll, no stream and no timer is started here. */
  usePosts()
  const conversation = store.conversation
  const [thread, setThread] = useState<Id | null>(null)
  const [at, setAt] = useState<Id | null>(null)
  /** a post older than the latest batch: the flow is read around its number */
  const [around, setAround] = useState<number | undefined>(undefined)
  const [reread, setReread] = useState(0)
  const [note, setNote] = useState<string | null>(null)
  const [targetError, setTargetError] = useState<string | null>(null)
  const section = useRef<HTMLElement | null>(null)
  const flow = useRealFlow(conversation ? 'real' : null, conversation, reread, around)

  /* The Magnet's own store still reads this Conversation once, for what only it
     answers: how much work it carries, and the page its message search offers
     as already-loaded entries. It is read again when a message is recorded. */
  useEffect(() => { void store.read() }, [store])
  useEffect(() => {
    if (!s.sent) return
    setReread((n) => n + 1)
  }, [s.sent?.op]) // eslint-disable-line react-hooks/exhaustive-deps

  /* THE WAY BACK, saved when a message was sent from another view, or when a
     search result was opened. Restoring a route moves the card, never the
     words: the draft and any inquiry draft are held per Magnet and `restore()`
     does not touch them. */
  const back = working.returnRoute
  const returnToWhereIWas = back && <button type="button" id="return-view" className="q2-mini-link"
    onClick={() => { restore(resource, back); resource.update({ returnRoute: null }) }}>
    ← Return to {back.overlay === 'search' ? 'search results' : back.overlay === 'settings' ? 'settings' : back.tab}
  </button>

  /* -- THE EXACT MESSAGE A SEARCH RESULT MEANT (owner §6) -------------------
     A hit may be older than the page this card has read, and it may be a reply
     inside a thread. Both are read where they are: the server names the hit's
     thread root, the thread is read into the shared store (so the post, its
     number and its root are in hand), a reply opens its thread here, and a
     top-level post older than the latest batch is read with the flow around
     its own number. Every step is counted (`resolving`): a read that lands
     after the owner has opened another result writes nothing, so a stale read
     can never overwrite a later target. */
  const target = messageTargetOf(working)
  const resolving = useRef(0)
  const applied = useRef<string | null>(null)
  /** THE TARGET THIS VIEW ITSELF LET GO, having positioned on it. The owning
   *  source asks for exactly that (Part C's §2): a target left standing would
   *  pull a later reader back to this message, and the frame's Escape order
   *  clears a target before anything else, so the first Escape would do
   *  nothing the reader could see. Letting it go is not the same event as the
   *  reader leaving it, so what was mounted for it stays mounted. */
  const cleared = useRef<string | null>(null)
  useEffect(() => {
    if (!target || !conversation) {
      /* The target let go: the latest batch again, and nothing kept from it --
         unless this view let it go itself, having arrived at the message. */
      if (!target && !cleared.current) { applied.current = null; setTargetError(null); setAround(undefined); setAt(null) }
      return
    }
    if (applied.current === target) return
    cleared.current = null
    const mine = ++resolving.current
    const mineStill = () => resolving.current === mine
    let live = true
    void (async () => {
      try {
        const held = postOf(target)
        const inFlow = !!held?.real && !held.replyTo && (flow.read?.top ?? []).includes(target)
        if (!inFlow) {
          const root = await threadRootOf(conversation, target)
          if (!live || !mineStill()) return
          await readThread(conversation, root)
          if (!live || !mineStill()) return
          const got = postOf(target)
          if (root !== target) { setThread(root); setAt(target) }
          else {
            setThread(null); setAt(null)
            if (got?.number != null) setAround(got.number)
          }
        } else { setThread(null); setAt(null) }
        if (mineStill()) setTargetError(null)
      } catch (e) {
        if (live && mineStill()) setTargetError(`That message could not be opened: ${e instanceof Error ? e.message : String(e)}`)
      }
    })()
    return () => { live = false }
  }, [target, conversation]) // eslint-disable-line react-hooks/exhaustive-deps

  /** THE POSITION A TARGET ASKS FOR, written into the Conversation's place so
   *  the frame applies it exactly as it applies a restored reading position. */
  const put = useCallback((id: string) => {
    const box = section.current?.closest<HTMLElement>('.q2-magnet-view')
    const el = section.current?.querySelector<HTMLElement>(`[data-post="${id}"]`)
    if (!box || !el) return false
    writePlace(resource, 'Conversation', {
      scroll: offsetInBox(el.getBoundingClientRect(), { top: box.getBoundingClientRect().top, scrollTop: box.scrollTop }),
    })
    return true
  }, [resource])
  useEffect(() => {
    const want = at ?? target
    if (!want || applied.current === target) return
    if (!put(want)) return
    applied.current = target
    /* POSITIONED: the target has been honoured, so it is let go here and not
       left for a later reader to be pulled back by. The reading position it
       asked for stays in the Conversation's place, and the way back to the
       results stays where the source saved it. */
    cleared.current = target
    if (target) resource.update({ searchTarget: null })
  }, [at, target, thread, flow.read, put, resource])

  /* -- THE PAGE THE SHARED POSTS ARE DRAWN IN, bounded to this card ---------
     Built before anything below returns early: a Magnet whose own Conversation
     is made by its first send goes from unavailable to available WHILE THIS
     VIEW IS MOUNTED, and a hook after that branch would be a different hook
     order between those two renders (which took the whole card down with it).
     `me` is deliberately null: this card reads and replies, and editing a post
     belongs to the Conversation itself, where the owner is known. With no
     working surface and no Brain lent, the shared post offers neither, so no
     control here leads out of the Magnet. */
  const page: PostPage = useMemo(() => ({
    me: null, who: null, topic: null,
    compact: true,
    onWho: () => {}, onTopic: () => {},
    onReply: (p) => {
      store.replyTo(replyTargetOf(p))
      /* The composer is the card's one footer bar, wherever this view is. */
      requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>('.q2-magnet-composer textarea')?.focus())
    },
    onEnter: (root, post) => { setThread(root); setAt(post ?? null) },
    onBeside: null,
    onView: (content) => {
      const ref = refOfViewable(content)
      if (ref && onEvidence) onEvidence(ref)
      else setNote('That is opened from the full Conversation; this card keeps reading inside the Magnet.')
    },
    openElsewhere: () => null,
    say: setNote,
    working: [],
  }), [store, onEvidence])

  if (s.unavailable) {
    return <section className="q2-mini q2-mini-unavailable" aria-label="Magnet conversation" ref={section}>
      <h3 id="view-title" tabIndex={-1}>{s.unavailable === NO_OWN_CONVERSATION ? 'Start a Conversation here' : 'Magnet conversation unavailable'}</h3>
      <p>{s.unavailable}</p>
      {s.unavailable === NO_OWN_CONVERSATION && canWrite && <>
        <p className="q2-mini-muted">Writing a message below makes this Conversation and records the message in it. Creating it first is the same act, without a message.</p>
        <button type="button" className="q2-mini-send"
          disabled={s.creating} onClick={() => void store.createOwn()}>
          {s.creating ? 'Creating Conversation…' : 'Create own Conversation'}
        </button>
      </>}
      {returnToWhereIWas}
      {s.contextError && <p className="q2-mini-alert" role="status">{s.contextError}</p>}
      {s.sendError && <p className="q2-mini-alert" role="status">{s.sendError}</p>}
    </section>
  }

  const blocked = !!s.identity
  const top = (flow.read?.top ?? []).map((id) => postOf(id)).filter((p): p is PostT => !!p)
  const total = flow.read?.total ?? s.total
  const older = flow.read?.older ?? 0

  return <section className="q2-mini" aria-label="Magnet conversation" ref={section}>
    <div className="q2-mini-head">
      <h3 id="view-title" tabIndex={-1}>{flow.read?.name || s.name || 'Magnet conversation'}</h3>
      {/* ONLY THE WAY BACK, AND ONLY WHEN THERE IS ONE (owner §3): no
          persistent navigation link stands here. The header carried "Open full
          Conversation →" on every open of this tab, which is the Magnet
          behaving as a way out of itself. */}
      {returnToWhereIWas && <span className="q2-mini-head-actions">{returnToWhereIWas}</span>}
    </div>
    {/* NO STANDING EXPLANATION OF WHAT AN AGENT READS HERE (owner §6): a
        sentence drawn above every message, on every tab, every time the card
        opens, is the administrative prose that was taking the working area --
        and what a message actually carries is now the one thing the composer
        shows, beside the words it belongs to. Nothing it said is weakened:
        collected information cannot be sent as context at all while
        configured-source access is unenforced, and the composer says so, in
        the moment it matters, if the owner attaches some. */}
    <p className="q2-mini-muted">
      {total !== null ? `${total} ${total === 1 ? 'post' : 'posts'}` : 'How many posts are recorded here is unavailable'}
      {s.owed ? ` · ${s.owed} ${s.owed === 1 ? 'request' : 'requests'} still to be answered` : ''}
    </p>
    {s.collection && onEvidence && <button type="button" className="q2-mini-link"
      onClick={() => onEvidence(s.collection!.artifact.ref)}>View collected information</button>}
    {s.contextError && <p className="q2-mini-alert" role="status">{s.contextError}</p>}
    {s.dispatchStatus && <p className="q2-mini-muted" role="status">{s.dispatchStatus}</p>}
    {blocked && <p className="q2-mini-alert" role="status">{s.identity}</p>}
    {s.error && <p className="q2-mini-alert" role="status">{s.error}</p>}
    {flow.error && <p className="q2-mini-alert" role="status">{flow.error}</p>}
    {targetError && <p className="q2-mini-alert" role="status">{targetError}</p>}
    {note && <p className="q2-mini-muted" role="status">{note}</p>}
    {!flow.read && !flow.error && conversation && <p className="q2-mini-muted" role="status">Reading this Conversation…</p>}

    {/* A REFERENCE IN A POST'S WORDS OPENS INSIDE THIS CARD, as a citation
        opened from any other tab does (`withInspections`). Two things make
        that true and neither changes what a post draws: the shared reference
        component is given this card's own opener, and a click on the reference
        Prose marked in the words is read here (`referenceClicked`) so every
        kind of reference -- a post, a version, a retained artifact -- is read
        as evidence in the card rather than anywhere else. */}
    <RefIndex conversation={null} acts={[]} alias={() => null} openEntry={onEvidence}>
      <PageContext.Provider value={page}>
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <div className="q2-mini-reading" onClickCapture={onEvidence ? (e) => {
        const ref = referenceClicked(e.target as Element)
        if (!ref) return
        e.preventDefault(); e.stopPropagation()
        onEvidence(ref)
      } : undefined}>
        {thread
          ? <div className="q2-mini-thread">
              <div className="q2-mini-head">
                <h4>Thread</h4>
                <button type="button" className="q2-mini-link"
                  onClick={() => { setThread(null); setAt(null) }}>← Back to the Conversation</button>
              </div>
              <ThreadView root={thread} selected={at} />
            </div>
          : <>
              {older > 0 && flow.earlier && <p className="q2-mini-earlier">
                <button type="button" className="q2-mini-link"
                  onClick={() => void flow.earlier!()}>{`Earlier posts (${older} older)`}</button>
              </p>}
              {top.length === 0 && flow.read && <p className="q2-mini-muted">No posts have been read here yet.</p>}
              <div className="q2-mini-posts">
                {top.map((p) => <div className="q2-mini-post" key={p.id}>
                  <Post post={p} />
                  <ReplyFold root={p.id} />
                </div>)}
              </div>
            </>}
      </div>
      </PageContext.Provider>
    </RefIndex>

    {/* No composer here: the card has one, in its footer, on every tab. What
        the owner may not do is still said where they would look for it. */}
    {!canWrite && <p className="q2-mini-muted q2-mini-nowrite">Sending is unavailable for this Magnet here. Nothing in this card writes to the record.</p>}
  </section>
}
