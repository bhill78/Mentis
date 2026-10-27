/* ABOUT THIS CONVERSATION: Brief, Actions, Follow ups, Media and Guidance as
 * one slide-out beside it (#188's capability table: "zone kinds or
 * slide-outs; no header strip"), opened from the conversation's menu.
 *
 * What each says comes from what the record already answers, read when the
 * slide-out opens -- nothing is computed from prose:
 *   Brief      the newest post somebody else wrote, what waits on you, who
 *              is working now
 *   Actions    what is owed here and not answered (production's `owed`),
 *              and what failed
 *   Follow ups production's rule (surfaces/followups.ts): side-notes nobody
 *              carries, and agents' posts that address nobody
 *   Media      the attachments of the posts in hand
 *   Guidance   what governs work here (`/api/conversations/<id>/governs`)
 * Every row goes to its post; nothing here writes. */

import { useEffect, useMemo, useState } from 'react'
import { ago } from '../../api'
import * as nav from '../nav'
import { store, type Id } from '../store'
import { getJson, refreshFacts, useFacts } from './facts'
import { Who } from '../identity/Who'
import { useCollection, useConversation } from './hooks'
import { excerpt } from './text'
import { showWorkspaceContent } from './threads'

const SECTIONS: [nav.AboutSection, string][] = [
  ['brief', 'Brief'], ['actions', 'Actions'], ['followups', 'Follow ups'], ['media', 'Media'], ['guidance', 'Guidance'],
]

/** Go to a post in this conversation: read it (loading it first if needed). */
function goTo(conversation: Id, post: Id) {
  const go = () => nav.read(conversation, post, store.posts.get(post)?.number ?? null)
  if (store.posts.has(post)) go()
  else void store.loadPosts([post]).then(go)
}

export default function About({ conversation, section }: { conversation: Id; section: nav.AboutSection }) {
  const conv = useConversation(conversation)
  const facts = useFacts(conversation)
  useEffect(() => { refreshFacts(conversation) }, [conversation])
  const open = (s: nav.AboutSection) =>
    nav.openDetail({ kind: 'about', conversation, section: s, anchor: { kind: 'zone', zone: 'conversation' }, mode: 'aside' })
  return (
    <aside className="fw-thread fx-sheet fx-about" aria-label="about this conversation">
      <header className="fx-sheet-head fw-thread-head">
        <button className="fx-ret" data-act="back" title="Back to the conversation" onClick={() => nav.closeAll()}>‹ Conversation</button>
        <h3>About {conv?.name ?? 'this conversation'}</h3>
        <button className="fx-ctl fx-x fw-close" aria-label="Back to the conversation" onClick={() => nav.closeAll()}>✕</button>
      </header>
      <nav className="fx-about-tabs" aria-label="about">
        {SECTIONS.map(([k, label]) => (
          <button key={k} className={'fx-tab' + (k === section ? ' on' : '')} aria-pressed={k === section} onClick={() => open(k)}>{label}</button>
        ))}
      </nav>
      <div className="fx-sheet-body">
        {facts.error && <p className="fx-faint">Could not read this conversation's facts: {facts.error}</p>}
        {section === 'brief' && <Brief conversation={conversation} />}
        {section === 'actions' && <Actions conversation={conversation} />}
        {section === 'followups' && <FollowUps conversation={conversation} />}
        {section === 'media' && <Media conversation={conversation} />}
        {section === 'guidance' && <Guidance conversation={conversation} />}
      </div>
    </aside>
  )
}

/** Somebody named by the record, drawn as everywhere (E2); else the words. */
const name = (id: Id | null | undefined, alias: string | null | undefined, otherwise: string) =>
  alias ? <Who id={id} name={alias} show="line" size={16} live /> : otherwise

function Brief({ conversation }: { conversation: Id }) {
  const conv = useConversation(conversation)
  const facts = useFacts(conversation)
  const coll = useCollection('conversation:' + conversation)
  const me = store.me
  const latest = useMemo(() => {
    const items = coll?.items ?? []
    for (let i = items.length - 1; i >= 0; i--) {
      const p = store.posts.get(items[i].id)
      if (p && p.author !== me && !p.deleted) return p
    }
    return null
  }, [coll, me])
  const mine = (facts.data?.owed ?? []).filter((o) => me && o.expected_of === me)
  return (
    <div className="fx-about-sec">
      <h4>What's going on</h4>
      {latest ? (
        <button className="fx-about-row" onClick={() => goTo(conversation, latest.id)}>
          <span><Who id={latest.author} name={latest.author_name} show="line" size={16} live meta={`${latest.number != null ? `#${latest.number} · ` : ''}${ago(latest.at)}`} /></span>
          <span className="fx-faint">{excerpt(latest, 180) || 'no words: what it carries is in This post'}</span>
        </button>
      ) : <p className="fx-faint">Nobody else has written here yet.</p>}
      <h4>Waiting on you</h4>
      {facts.loading && !facts.data ? <p className="fx-faint">Reading…</p> : mine.length ? mine.map((o) => (
        <button key={o.expectation} className="fx-about-row" onClick={() => goTo(conversation, o.turn)}>
          <span>{name(o.requested_by, o.requested_by_alias, 'Somebody')} needs: {o.expects}</span>
        </button>
      )) : <p className="fx-faint">Nothing here waits on you.</p>}
      <h4>Now</h4>
      <p className="fx-faint">{conv?.working ? `${conv.working} working here now` : 'Nobody is working here now'} · {conv?.posts ?? '…'} posts{conv?.included ? ` + ${conv.included} included` : ''} · {facts.data?.participants.length ?? '…'} people</p>
    </div>
  )
}

function Actions({ conversation }: { conversation: Id }) {
  const facts = useFacts(conversation)
  const owed = facts.data?.owed ?? []
  const fails = facts.data?.failures ?? []
  if (facts.loading && !facts.data) return <p className="fx-faint">Reading…</p>
  return (
    <div className="fx-about-sec">
      <h4>Owed here, not answered · {owed.length}</h4>
      {owed.length === 0 && <p className="fx-faint">Nothing is owed here.</p>}
      {owed.slice(0, 60).map((o) => (
        <button key={o.expectation} className="fx-about-row" onClick={() => goTo(conversation, o.turn)} data-expectation={o.expectation}>
          <span>{name(o.requested_by, o.requested_by_alias, 'Somebody')} asked {name(o.expected_of, o.expected_of_alias, o.unassigned ? 'nobody yet (unassigned)' : 'somebody')}
            {o.live_execution?.length ? ' · working now' : ''}{o.failures?.length ? ` · failed ${o.failures.length}×` : ''}</span>
          <span className="fx-faint">{o.expects}</span>
        </button>
      ))}
      {owed.length > 60 && <p className="fx-faint">{owed.length - 60} more.</p>}
      {fails.length > 0 && <h4>Failed · {fails.length}</h4>}
      {fails.slice(0, 20).map((f, i) => (
        <p key={i} className="fx-faint">{f.because ?? 'failed'}{f.at ? ` · ${ago(f.at)}` : ''}</p>
      ))}
    </div>
  )
}

interface TurnRow {
  id: Id; number: number; at: number; author: Id; author_alias: string; deleted?: unknown
  written_by?: string | null; answering?: Id | null; addressees: { participant: Id }[]
  expectations: { unassigned?: boolean; response_present?: boolean; of?: Id | null }[]
  discovered_under?: { turn?: Id } | null; parts?: { type: string; text?: string }[]
}

/* Production's follow-up rule, on the Turns production's read gives. */
const uncarried = (t: TurnRow) => t.expectations.some((e) => e.unassigned && !e.response_present)
const byExecution = (t: TurnRow) => !!t.written_by && t.written_by !== 'unattributed-local-request'
const stray = (t: TurnRow, owner: Id | null) => !!owner && t.author !== owner && byExecution(t) &&
  !t.answering && t.addressees.length === 0 && !t.expectations.some((e) => !!e.of)

function FollowUps({ conversation }: { conversation: Id }) {
  const [rows, setRows] = useState<TurnRow[] | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    void getJson<{ turns: TurnRow[] }>(`/api/conversations/${encodeURIComponent(conversation)}?batch=80`)
      .then((r) => {
        if (!live) return
        const owner = store.me
        setRows(r.turns.filter((t) => !t.deleted && (t.discovered_under ? uncarried(t) : stray(t, owner)))
          .sort((a, b) => b.at - a.at || b.number - a.number))
      })
      .catch((e: Error) => live && setWhy(e.message))
    return () => { live = false }
  }, [conversation])
  if (why) return <p className="fx-faint">Could not read the follow ups: {why}</p>
  if (!rows) return <p className="fx-faint">Reading…</p>
  return (
    <div className="fx-about-sec">
      <h4>Follow ups · {rows.length} <span className="fx-faint">in the newest 80 threads</span></h4>
      {rows.length === 0 && <p className="fx-faint">No side-notes wait to be carried, and no agent post here addresses nobody.</p>}
      {rows.map((t) => (
        <button key={t.id} className="fx-about-row" onClick={() => goTo(conversation, t.id)}>
          <span><Who id={t.author} name={t.author_alias} show="line" size={16} live meta={`#${t.number} · ${ago(t.at)}${t.discovered_under ? ' · side-note nobody carries' : ' · addresses nobody'}`} /></span>
          <span className="fx-faint">{(t.parts ?? []).filter((x) => x.type === 'text').map((x) => x.text ?? '').join('').replace(/[#*`>_]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 160)}</span>
        </button>
      ))}
    </div>
  )
}

function Media({ conversation }: { conversation: Id }) {
  const coll = useCollection('conversation:' + conversation)
  const items = useMemo(() => {
    const out: { post: Id; number: number | null; ref: string; name: string; image: boolean }[] = []
    for (const it of coll?.items ?? []) {
      const p = store.posts.get(it.id)
      if (!p) continue
      for (const part of p.parts) {
        if (part.type === 'text' || !part.ref) continue
        const mt = String((part as { media_type?: string }).media_type ?? '')
        out.push({ post: p.id, number: p.number, ref: String(part.ref), name: String(part.alt ?? part.name ?? part.ref), image: part.type === 'image' || mt.startsWith('image/') })
      }
    }
    return out.reverse()
  }, [coll])
  return (
    <div className="fx-about-sec">
      <h4>Media · {items.length} <span className="fx-faint">in the posts loaded here</span></h4>
      {items.length === 0 && <p className="fx-faint">No attachments in the posts loaded here.</p>}
      <div className="fx-media-grid">
        {items.map((m, i) => (
          <button key={m.ref + i} className="fx-media" title={`${m.name} · ${m.number != null ? '#' + m.number : ''}`}
            onClick={() => { goTo(conversation, m.post); nav.showPage('this-post'); showWorkspaceContent() }}>
            {m.image ? <img src={`/api/artifacts/${m.ref}`} alt={m.name} loading="lazy" /> : <span className="fx-file">{m.name}</span>}
            <span className="fx-media-n">{m.number != null ? `#${m.number}` : ''}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

interface GovernRow { entry: Id; kind: string; text: string; placed?: string[] }
function Guidance({ conversation }: { conversation: Id }) {
  const [g, setG] = useState<{ governing: GovernRow[]; candidates?: GovernRow[] } | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    void getJson<{ governing: GovernRow[]; candidates?: GovernRow[] }>(`/api/conversations/${encodeURIComponent(conversation)}/governs`)
      .then((r) => live && setG(r)).catch((e: Error) => live && setWhy(e.message))
    return () => { live = false }
  }, [conversation])
  if (why) return <p className="fx-faint">Could not read what governs work here: {why}</p>
  if (!g) return <p className="fx-faint">Reading…</p>
  const kind = (k: string) => k.replace(/[-_]/g, ' ')
  return (
    <div className="fx-about-sec">
      <h4>Stands here and reaches every execution · {g.governing.length}</h4>
      {g.governing.length === 0 && <p className="fx-faint">Nothing governs work here.</p>}
      {g.governing.map((r) => (
        <div key={r.entry} className="fx-gov"><span className="fx-gov-kind">{kind(r.kind)}{r.placed?.includes('whole-brain') ? ' · whole brain' : ''}</span><p>{r.text}</p></div>
      ))}
      {(g.candidates ?? []).length > 0 && <h4>Proposed, reaches nobody · {g.candidates!.length}</h4>}
      {(g.candidates ?? []).map((r) => (
        <div key={r.entry} className="fx-gov fx-faint"><span className="fx-gov-kind">{kind(r.kind)}</span><p>{r.text}</p></div>
      ))}
    </div>
  )
}
