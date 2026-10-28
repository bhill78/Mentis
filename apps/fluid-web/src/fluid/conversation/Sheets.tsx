/* THE PANEL BESIDE THE CONVERSATION (spec section 6; completion stream B):
 * a post's replies, its details, or what the conversation's menu opened --
 * and the threads you pinned, as tabs.
 *
 * Slide-outs open out of their post (the anchor) and return into it: "‹"
 * and "✕" unwind the temporary view at once (`nav.closeAll`), as Esc does.
 *
 * PINNED THREADS (#187 #5, #188 decision 3). 📌 in a thread's head keeps it
 * here while you read other posts; pin several and they are tabs in this one
 * panel. A thread opened while some are pinned is one more tab, unpinned
 * (temporary: reading another post closes it, as every slide-out). Long
 * threads show the newest replies, with "Show N earlier" above them, and
 * indentation stops at three levels: deeper replies say whom they answer.
 *
 * EACH THREAD HAS ITS OWN COMPOSER (#188, #448): its header line says where
 * the reply goes, and Reply on a reply in it makes that reply its target. */

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useLinkDrop } from './linkDrop'
import type { LinkTarget } from '../render/objectRef'
import * as nav from '../nav'
import { repliesOf, store, type Id, type RunItem, type WorkItem } from '../store'
import Composer from '../Composer'
import { useCollection, useNav, usePost } from './hooks'
import { scrollBoxOf, useTall } from './PostCard'
import { PostView, WorkOn, useActions } from '../render/post'
import { Who } from '../identity/Who'
import { SectionSpin, useSectionLoad } from '../../loading'
import { useWorkingUnder } from './presence'
import { useWorkingOn } from './working'
import { bare } from './text'
import { activate, pin, pinsOf, setTarget, takePosted, targetOf, unpin, useThreads } from './threads'
import About from './About'
import { onStageClass, useOnStage } from '../workspace/origin'
import TimeSpent from '../../experimental/TimeSpent'
import { ReplyObjectStrip } from './Carries'

/** Indentation stops at three levels (#188). */
const LEVELS = 3

function Head({ ret, title, label, children, sectionId }: { ret?: string; title: string; label: string; children?: React.ReactNode; sectionId?: string | null }) {
  return (
    <header className="fx-sheet-head fw-thread-head">
      {/* The sheet's own controls close it, and an object open over it with it. */}
      {ret && <button className="fx-ret" data-act="back" title={label} onClick={() => nav.closeAll()}>‹ {ret}</button>}
      <h3>{title}</h3>
      {sectionId && <SectionSpin id={sectionId} label={title} />}
      {/* The controls are one group: where the title and they do not fit on
          one line, they move under it together and the title stays whole. */}
      <span className="fx-sheet-tools">
        {children}
        {ret && <button className="fx-ctl fx-x fw-close" data-act="back" aria-label={label} onClick={() => nav.closeAll()}>✕</button>}
      </span>
    </header>
  )
}

/** FOLLOW (A1): the sheet opens for each post read -- its replies, or its
 *  details while details are shown. A quiet toggle in the sheet's head. */
export function FollowToggle() {
  const on = !!useNav().follow
  return (
    <button className={'fx-ctl fx-follow' + (on ? ' on' : '')} aria-pressed={on} data-act="follow"
      aria-label={on ? 'following the post you read: stop' : 'follow the post you read'}
      title={on ? 'Following: each post you read opens here, with its replies. Press to stop.' : 'Follow the post you read: each post you read opens here, with its replies'}
      onClick={() => nav.setFollow(!on)}>⇢</button>
  )
}

/** One reply in the thread: read on click, indented by depth to three levels. */
function Reply({ id, depth, parent, target, root }: { id: Id; depth: number; parent: Id | null; target: boolean; root: Id }) {
  const post = usePost(id)
  const a = useActions()
  const s = useNav()
  /* A reply read from elsewhere -- a link, search, Home -- is brought into
     view in its thread, only as far as needed (opr-49f1f943b6a9). */
  const ref = useRef<HTMLDivElement | null>(null)
  const reading = s.reading === id
  /* A3: the reply somebody is answering says so, in its thread. */
  const workers = useWorkingOn(id)
  const onStage = useOnStage(id)
  const { tall, headAway } = useTall(ref, scrollBoxOf, !!post)
  /* A REPLY TAKES A LINK TOO: the reply to it carries the reference (W4) */
  const linkTo = useMemo<LinkTarget | null>(() => (post && !post.deleted && !a.selectMode ? { kind: 'post', post, here: a.here } : null), [post, a.here, a.selectMode])
  const drop = useLinkDrop(linkTo)
  useEffect(() => {
    const el = ref.current
    if (!reading || !el) return
    const box = scrollBoxOf(el)
    if (!box) return
    const r = el.getBoundingClientRect(), b = box.getBoundingClientRect()
    if (r.top < b.top || r.top > b.bottom - 48) el.scrollIntoView({ block: r.height > b.height ? 'start' : 'center' })
  }, [reading, !!post])
  if (!post) return <div className="fw-card fx-reply fw-pending" aria-busy="true" />
  const selected = a.selected.has(id)
  const readIt = () => { if (a.selectMode) a.toggleSelect(id); else nav.read(a.readIn, id, post.number) }
  const level = Math.min(LEVELS - 1, Math.max(0, depth - 1))
  const deeper = depth > LEVELS
  const answers = deeper && parent ? store.posts.get(parent) : undefined
  return (
    <div ref={ref} className={'fw-reply fw-card fx-reply' + (s.reading === id ? ' reading' : '') + (selected ? ' fw-selected' : '') + (target ? ' fx-target' : '') + (tall ? ' fx-tall' : '') + onStageClass(onStage) + drop.className}
      {...drop.props}
      data-post={id} data-reply={post.number ?? undefined} data-depth={depth} data-level={level}
      style={{ marginLeft: 6 + level * 18 }}
      tabIndex={0} role="article"
      aria-label={`Reply ${post.number != null ? '#' + post.number : ''} by @${bare(post.author_name)}${s.reading === id ? ', reading' : ''}`}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target === e.currentTarget) { e.preventDefault(); readIt() } }}
      onClick={readIt}>
      {/* A9: a reply says when, as a post does: the same renderer draws both. */}
      <PostView post={post} context="reply" here={a.here} card={ref} selecting={a.selectMode} onStage={onStage}
        check={a.selectMode ? { checked: selected, toggle: () => a.toggleSelect(id), label: `Select post #${post.number ?? id}` } : null}
        meta={<WorkOn num={post.number != null ? `#${post.number}` : 'this reply'} on={workers} under={[]} />}
        lead={deeper && <p className="fx-answers">↳ replying to {answers?.number != null ? `#${answers.number}` : 'an earlier reply'}{answers ? ` · @${bare(answers.author_name)}` : ''}</p>}
        chips={{ headAway }} />
      <ReplyObjectStrip post={post} thread={root} />
    </div>
  )
}

/** A thread: its root, its replies (the newest, with "Show N earlier"), and
 *  its own composer. Used beside the conversation and full screen. */
export function ThreadBody({ root, full }: { root: Id; full?: boolean }) {
  const coll = useCollection('thread:' + root)
  const post = usePost(root)
  const a = useActions()
  useThreads()
  const rootWorkers = useWorkingOn(root)
  const underWorkers = useWorkingUnder(root)
  const rootOnStage = useOnStage(root)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const { tall: rootTall, headAway: rootHeadAway } = useTall(rootRef, scrollBoxOf, !!post)
  const rootLink = useMemo<LinkTarget | null>(() => (post && !post.deleted && !a.selectMode ? { kind: 'post', post, here: a.here } : null), [post, a.here, a.selectMode])
  const rootDrop = useLinkDrop(rootLink)
  useEffect(() => { void store.loadThread(root) }, [root])
  const target = targetOf(root)
  /* The reply you just wrote is shown when it arrives, wherever you were in the thread. */
  const body = useRef<HTMLDivElement | null>(null)
  const count = coll?.items.length ?? 0
  const had = useRef(count)
  useLayoutEffect(() => {
    if (count > had.current && takePosted(root) && body.current) body.current.scrollTop = body.current.scrollHeight
    had.current = count
  }, [count, root])
  return (
    <>
      <div ref={body} className={'fx-sheet-body fw-thread-body' + (full ? ' fx-full-col' : '')}>
        {post ? (
          <div ref={rootRef} className={'fx-root-post fw-card' + (rootTall ? ' fx-tall' : '') + onStageClass(rootOnStage) + rootDrop.className} {...rootDrop.props} data-post={root}>
            <PostView post={post} context="root" here={a.here} onStage={rootOnStage}
              meta={<WorkOn num={post.number != null ? `#${post.number}` : 'this post'} on={rootWorkers} under={underWorkers} />}
              chips={{ headAway: rootHeadAway }} />
          </div>
        ) : <div className="fx-root-post fw-pending" aria-busy="true" />}
        {coll && coll.older > 0 && (
          <button className="fw-more fx-more-btn" onClick={() => void store.olderOfThread(root)}>Show {coll.older} earlier {coll.older === 1 ? 'reply' : 'replies'}</button>
        )}
        {coll && coll.items.length === 0 && <p className="fx-faint fx-none-yet">No replies yet. Write the first one below.</p>}
        {coll?.items.map((p) => <Reply key={p.id} id={p.id} depth={p.depth ?? 1} parent={p.parent ?? null} target={target === p.id} root={root} />)}
      </div>
      {a.here && (
        <div className={'fx-thread-composer' + (full ? ' fx-full-col' : '')}>
          <Composer conversation={a.here} thread={root} replyTo={target ?? root} onClearReply={() => setTarget(root, null)} />
        </div>
      )}
    </>
  )
}

/** The panel beside the conversation: the open sheet, or the pinned threads. */
export function ThreadPanel({ here, sheet }: { here: Id | null; sheet: nav.Detail | null }) {
  useThreads()
  const p = pinsOf(here)
  const temp = sheet?.kind === 'replies' ? sheet.root : null
  const showing = temp ?? (sheet ? null : p.active)
  const tabs = [...p.pinned, ...(temp && !p.pinned.includes(temp) ? [temp] : [])]
  return (
    <>
      {here && (tabs.length > 1 || (p.pinned.length > 0 && !!sheet && sheet.kind !== 'replies')) ? (
        <div className="fx-tabs" role="tablist" aria-label="threads">
          {tabs.map((r) => (
            <ThreadTab key={r} root={r} here={here!} on={r === showing} pinned={p.pinned.includes(r)} temporary={r === temp && !p.pinned.includes(r)} />
          ))}
        </div>
      ) : null}
      {sheet?.kind === 'post-details' && <DetailsSheet id={sheet.id} />}
      {sheet?.kind === 'about' && <About conversation={sheet.conversation} section={sheet.section} />}
      {showing && <RepliesSheet key={showing} root={showing} here={here} temporary={showing === temp} />}
    </>
  )
}

function ThreadTab({ root, here, on, pinned, temporary }: { root: Id; here: Id; on: boolean; pinned: boolean; temporary: boolean }) {
  const post = usePost(root)
  const n = post?.number != null ? `#${post.number}` : '…'
  return (
    <span className={'fx-ttab' + (on ? ' on' : '') + (temporary ? ' temp' : '')} role="tab" aria-selected={on}>
      <button className="fx-ttab-go" title={temporary ? `The thread of ${n}, not pinned: it closes when you read another post` : `The thread of ${n}, pinned`}
        onClick={() => { if (temporary) return; if (nav.sheetOf(nav.snapshot())) nav.closeAll(); activate(here, root) }}>
        {pinned ? '📌 ' : ''}{n}{post ? <span className="fx-ttab-n"> · {repliesOf(post)}</span> : null}
      </button>
      <button className="fx-ttab-x" aria-label={pinned ? `unpin the thread of ${n}` : `close the thread of ${n}`}
        title={pinned ? 'Unpin' : 'Close'} onClick={() => (pinned ? unpin(here, root) : nav.closeAll())}>✕</button>
    </span>
  )
}

export function RepliesSheet({ root, here, temporary }: { root: Id; here: Id | null; temporary: boolean }) {
  const coll = useCollection('thread:' + root)
  const post = usePost(root)
  useThreads()
  const pinned = !!here && pinsOf(here).pinned.includes(root)
  /* The whole thread, as the post's chip and its details say it. */
  const n = coll?.total ?? (post ? repliesOf(post) : 0)
  const num = post?.number != null ? `#${post.number}` : 'this post'
  const loadId = 'fluid:thread:' + root
  const loading = !coll
  useSectionLoad(loadId, `Thread ${num}`, { loading, error: null, data: coll ? true : null })
  return (
    <aside className="fw-thread fx-sheet" aria-label="thread" data-thread={root} data-pinned={pinned || undefined} aria-busy={loading || undefined}>
      <Head ret={temporary ? 'Conversation' : undefined} title={`${num} · ${n} ${n === 1 ? 'reply' : 'replies'}`} label="Back to the conversation" sectionId={loadId}>
        <FollowToggle />
        {here && (
          <button className={'fx-ctl fx-pin' + (pinned ? ' on' : '')} aria-pressed={pinned}
            title={pinned ? 'Unpin: it closes when you read another post' : 'Pin: keep this thread here while you read other posts'}
            aria-label={pinned ? `unpin the thread of ${num}` : `pin the thread of ${num}`}
            onClick={() => (pinned ? unpin(here, root) : pin(here, root))}>📌<span className="fx-pin-word">{pinned ? ' Pinned' : ' Pin'}</span></button>
        )}
        <button className="fx-ctl" title="Full screen" aria-label={`the thread of ${num} full screen`}
          onClick={() => nav.openDetail({ kind: 'full', of: 'thread', id: root, anchor: { kind: 'post', id: root }, mode: 'over' })}>⤢</button>
        {!temporary && here && (
          <button className="fx-ctl fx-x fw-close" aria-label={`unpin and close the thread of ${num}`} title="Unpin and close" onClick={() => unpin(here, root)}>✕</button>
        )}
      </Head>
      <ThreadBody root={root} />
    </aside>
  )
}

/* -- details: the work around a post, moved out of the post itself -------- */

function duration(r: RunItem): string | null {
  if (!r.ended_at) return null
  const s = Math.max(0, Math.round(r.ended_at - r.started_at))
  return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`
}

export function DetailsSheet({ id }: { id: Id }) {
  const post = usePost(id)
  const a = useActions()
  const [work, setWork] = useState<WorkItem[] | null>(null)
  const [runs, setRuns] = useState<RunItem[]>([])
  const asked = post?.expectations ?? []
  const key = asked.join(',')
  useEffect(() => {
    if (!key) { setWork([]); setRuns([]); return }
    let live = true
    void store.loadWork(key.split(','))
      .then(async (w) => {
        if (!live) return
        setWork(w)
        const ids = w.flatMap((x) => x.runs)
        if (ids.length) {
          const r = await store.loadRuns(ids)
          if (live) setRuns(r)
        }
      })
      .catch(() => live && setWork([]))
    return () => { live = false }
  }, [key])
  const num = post?.number != null ? `#${post.number}` : 'this post'
  const rows: [string, React.ReactNode][] = []
  if (post) {
    rows.push(['Written by', <Who id={post.author} name={post.author_name} show="line" size={18} meta={`· ${new Date(post.at * 1000).toLocaleString()}`} />])
    if (post.edited_at) rows.push(['Edited', `${new Date(post.edited_at * 1000).toLocaleString()}${post.versions > 1 ? ` · ${post.versions} versions` : ''}`])
    if (post.home && post.home !== a.here) rows.push(['Lives in', `${post.home_name ?? 'another conversation'}${post.number != null ? ` · #${post.number}` : ''}`])
    const linked = (post.memberships ?? []).filter((m) => m.via === 'linked')
    if (linked.length) rows.push(['Included in', linked.map((m) => m.name ?? store.conversations.get(m.conversation)?.name ?? m.conversation).join(', ')])
    if (post.reply_to) rows.push(['Replies to', `${post.reply_to_home && post.reply_to_home !== a.here ? `${post.reply_to_home_name ?? 'another conversation'} · ` : ''}${post.reply_to_number != null ? `#${post.reply_to_number}` : 'a post'}`])
    for (const w of work ?? []) {
      rows.push(['Asked of', w.carrier
        ? <Who id={w.carrier} name={w.carrier_name ?? 'somebody'} show="line" size={18} meta={`· ${w.state}`} />
        : `nobody yet · ${w.state}`])
      rows.push(['Work', w.what])
    }
    /* A run's face carries the runtime that ran it, not where the name last ran. */
    for (const r of runs) rows.push(['Run', r.participant
      ? <Who id={r.participant} name={r.participant_name ?? 'somebody'} show="line" size={18} runtime={r.runtime || null}
          meta={'· ' + [r.runtime, r.model, duration(r), r.state].filter(Boolean).join(' · ')} />
      : [r.runtime, r.model, duration(r), r.state].filter(Boolean).join(' · ')])
    if (repliesOf(post)) rows.push(['Replies', `${repliesOf(post)}`])
  }
  return (
    <aside className="fw-thread fx-sheet fx-details" aria-label="post details">
      <Head ret={num} title={`Details of ${num}`} label={`Back to ${num}`}><FollowToggle /></Head>
      <div className="fx-sheet-body">
        <TimeSpent id={id} className="fx-time-spent" />
        {!post ? <p className="fx-faint">Reading…</p> : (
          <dl className="fx-kv">
            {rows.map(([k, v], i) => <Row key={i} k={k} v={v} />)}
            {work === null && asked.length > 0 && <Row k="Asked of" v="reading…" />}
          </dl>
        )}
        <p className="fx-faint fx-note">Work details move out of the post. The post itself shows only its author, number, time and words.</p>
      </div>
    </aside>
  )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <><dt>{k}</dt><dd>{v}</dd></>
}

/** The open conversation sheet, kept on screen while it slides shut. */
export function useClosing<T>(value: T | null, ms = 380): T | null {
  const [shown, setShown] = useState<T | null>(value)
  useEffect(() => {
    if (value !== null) { setShown(value); return }
    const t = setTimeout(() => setShown(null), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return value ?? shown
}
