/* QUIET CHAT MARK 2 — DESIGN ROUND 1: the editorial conversation.
 *
 * Served at /quiet2 beside Mark 1 (docs/quiet-chat/MARK-2.md). The
 * conversation is the page: one centred reading column, quiet chrome, and
 * margins that stay empty until something in them is asked for. Navigation
 * is stepped markers at the edges, not panels.
 *
 * Round 1 draws a sample conversation (sample.ts). The composer is Fluid's
 * own, live against the first conversation of whichever Brain serves this
 * page, so what it sends lands there and not in the sample. Arrangements
 * (two and three columns, the conversation receding) are shown as a layout
 * only: the working surfaces are placeholders. */
import '../fluid/fluid.css'
import '../fluid/frame/frame.css'
import '../fluid/conversation/conversation.css'
import './quiet2.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import Composer from '../fluid/Composer'
import { store } from '../fluid/store'
import MediaLayer from '../quiet/media/MediaLayer'
import Markers from './Markers'
import Post from './Post'
import { CONVERSATION, CONVERSATIONS, POSTS, TOPICS, type Person, type Post as PostT } from './sample'

type Arrangement = 'one' | 'two' | 'three'

/** The first conversation of the Brain serving this page: where the real
 *  composer writes. null while it is read, or where there is none. */
function useComposerConversation() {
  const [id, setId] = useState<string | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    store.loadList().then(() => {
      const first = store.list?.find((c) => c.name && !/^unnamed/i.test(c.name)) ?? store.list?.[0]
      if (first) setId(first.id); else setWhy('This Brain has no conversation for the composer to write to.')
    }).catch((e: unknown) => setWhy(`The composer could not reach a Mentis server: ${String(e)}`))
  }, [])
  return { id, name: id ? store.conversations.get(id)?.name ?? null : null, why }
}

function ArrangementControl({ value, onChange, onSide, receded, onRecede }: {
  value: Arrangement; onChange: (a: Arrangement) => void
  onSide: () => void
  receded: boolean; onRecede: () => void
}) {
  const glyph = (a: Arrangement) => (
    <svg width="18" height="14" viewBox="0 0 18 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3">
      <rect x=".65" y=".65" width="16.7" height="12.7" rx="2" />
      {a !== 'one' && <path d={a === 'two' ? 'M9 1v12' : 'M6.5 1v12M11.5 1v12'} />}
    </svg>
  )
  return (
    <div className="q2-arrange" role="group" aria-label="arrangement">
      {(['one', 'two', 'three'] as const).map((a) => (
        <button key={a} aria-pressed={value === a} onClick={() => onChange(a)}
          title={a === 'one' ? 'Conversation only' : a === 'two' ? 'Conversation beside a working surface' : 'Conversation and two working surfaces'}>{glyph(a)}</button>
      ))}
      {value === 'two' && <button onClick={onSide} title="Move the conversation to the other side">⇄</button>}
      {value !== 'one' && <button onClick={onRecede} aria-pressed={receded} title={receded ? 'Bring the conversation back' : 'Let the conversation recede'}>{receded ? 'Show conversation' : 'Recede'}</button>}
    </div>
  )
}

function Surface({ n }: { n: number }) {
  return (
    <section className="q2-surface" aria-label={`working surface ${n}`}>
      <div className="q2-surface-inner">
        <p className="q2-surface-kicker">Working surface {n}</p>
        <p>A document, a board, a run's activity or the 3D Brain would sit here. Round 1 shows only the arrangement; nothing is docked.</p>
      </div>
    </section>
  )
}

export default function Quiet2() {
  const [who, setWho] = useState<Person | null>(null)
  const [topic, setTopic] = useState<string | null>(null)
  const [list, setList] = useState(false)
  const [arr, setArr] = useState<Arrangement>('one')
  const [side, setSide] = useState<'left' | 'right'>('left')
  const [receded, setReceded] = useState(false)
  const [replying, setReplying] = useState<PostT | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const composer = useComposerConversation()
  const dock = useRef<HTMLDivElement>(null)
  const byId = useMemo(() => new Map(POSTS.map((p) => [p.id, p])), [])

  useEffect(() => { document.title = `${CONVERSATION.name} · Quiet` }, [])
  useEffect(() => { if (arr === 'one') setReceded(false) }, [arr])
  useEffect(() => {
    if (!notice) return
    const t = setTimeout(() => setNotice(null), 3200)
    return () => clearTimeout(t)
  }, [notice])

  const shown = (p: PostT) => (!who || p.by.id === who.id || p.requestedBy?.id === who.id) && (!topic || p.topics?.includes(topic))
  /* posts that do not match the filter fold into one quiet line per run */
  const rows: ({ post: PostT } | { hidden: number; key: string })[] = []
  for (const p of POSTS) {
    if (shown(p)) rows.push({ post: p })
    else {
      const last = rows[rows.length - 1]
      if (last && 'hidden' in last) last.hidden++; else rows.push({ hidden: 1, key: 'h-' + p.id })
    }
  }

  const reply = (p: PostT) => {
    setReplying(p)
    dock.current?.querySelector<HTMLTextAreaElement>('textarea')?.focus()
  }

  const conversation = (
    <main className={'q2-conv' + (receded ? ' receded' : '')} aria-label={`conversation: ${CONVERSATION.name}`}>
      {receded ? (
        <button className="q2-receded" onClick={() => setReceded(false)} title="Bring the conversation back">
          <span className="q2-receded-name">{CONVERSATION.name}</span><span className="q2-receded-new">2 new</span>
        </button>
      ) : (
        <div className="q2-col">
          <header className="q2-conv-head">
            <h1>{CONVERSATION.name}</h1>
            <p className="q2-conv-meta">{CONVERSATION.total} posts · 6 participants · <button className="q2-link" onClick={() => setNotice('Earlier posts: not part of the Round 1 sample.')}>{CONVERSATION.total - POSTS.length} earlier</button></p>
          </header>
          {(who || topic) && (
            <p className="q2-filter" role="status">
              Showing {who ? <>posts by or asked by <b>{who.name.replace(/^@/, '')}</b></> : null}{who && topic ? ' under ' : topic ? 'posts under ' : ''}{topic ? <b>#{topic}</b> : null}
              {' '}<button className="q2-link" onClick={() => { setWho(null); setTopic(null) }}>Show everything</button>
            </p>
          )}
          <div className="q2-stream">
            {rows.map((r) => 'hidden' in r
              ? <p key={r.key} className="q2-folded">{r.hidden} {r.hidden === 1 ? 'post' : 'posts'} folded by the filter</p>
              : <Post key={r.post.id} post={r.post} who={who} topic={topic}
                  replyingTo={r.post.replyTo ? byId.get(r.post.replyTo) : undefined}
                  onWho={(p) => setWho(who?.id === p.id ? null : p)}
                  onTopic={(t) => setTopic(topic === t ? null : t)}
                  onReply={reply} />)}
          </div>
          <div className="q2-dock" ref={dock}>
            {replying && (
              <p className="q2-dock-reply">Replying to {replying.by.name.replace(/^@/, '')}{replying.title ? `: ${replying.title}` : ''} <span>(sample post: the composer below writes to its own conversation)</span>
                <button className="q2-link" onClick={() => setReplying(null)}>Cancel</button></p>
            )}
            {composer.id ? (
              <>
                <Composer conversation={composer.id} replyTo={null} onClearReply={() => setReplying(null)} />
                <p className="q2-dock-note">Round 1: Fluid's composer, live. It posts to “{composer.name ?? composer.id}” in the dev Brain, not to this sample.</p>
              </>
            ) : <p className="q2-dock-note">{composer.why ?? 'Reading the Brain…'}</p>}
          </div>
        </div>
      )}
    </main>
  )

  return (
    <div className={`q2 fx q2-arr-${arr} q2-side-${side}` + (receded ? ' q2-is-receded' : '')}>
      <header className="q2-top">
        <button className="q2-logo" aria-expanded={list} onClick={() => setList(!list)} title="All conversations">Mentis</button>
        <span className="q2-top-conv">{CONVERSATION.name}</span>
        <span className="q2-top-gap" />
        <ArrangementControl value={arr} onChange={setArr} onSide={() => setSide(side === 'left' ? 'right' : 'left')}
          receded={receded} onRecede={() => setReceded(!receded)} />
      </header>
      {list && (
        <div className="q2-list" role="dialog" aria-label="All conversations">
          <ul>{CONVERSATIONS.map((c) => (
            <li key={c.key}><button className={c.key === 'onboarding' ? 'current' : ''} onClick={() => { setList(false); if (c.key !== 'onboarding') setNotice(`“${c.name}” is not part of the Round 1 sample.`) }}>
              <span>{c.name}</span><span className="q2-list-meta">{c.count}</span></button></li>
          ))}</ul>
        </div>
      )}
      <Markers label="Conversations" side="left" items={CONVERSATIONS} current="onboarding"
        onPick={(k) => { if (k !== 'onboarding') setNotice(`“${CONVERSATIONS.find((c) => c.key === k)?.name}” is not part of the Round 1 sample.`) }} />
      <Markers label="Topics in this conversation" side="right" items={TOPICS} current={topic} prefix="#"
        onPick={(k) => setTopic(topic === k ? null : k)} />
      <div className="q2-work">
        {arr === 'two' && side === 'right' && <Surface n={1} />}
        {conversation}
        {arr === 'two' && side === 'left' && <Surface n={1} />}
        {arr === 'three' && <><Surface n={1} /><Surface n={2} /></>}
      </div>
      {notice && <p className="q2-notice" role="status">{notice}</p>}
      <MediaLayer />
    </div>
  )
}
