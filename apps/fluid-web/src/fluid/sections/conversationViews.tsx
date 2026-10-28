/* -- Sections: this conversation's Brief, Actions, Follow ups, Media and
 * Guidance ------------------------------------------------------------
 *
 * The About slide-out's five views (conversation/About.tsx), registered as
 * sources (scope 'conversation') so a workspace section can bring one in as
 * its feed (`slot.feed`, workspace/feedSection.ts). The slide-out draws
 * these same bodies with the same data and the same useFacts; a section
 * draws one through the registry, reading the conversation of the place it
 * is in (`props.conversation`) and drawn with its own chrome -- a
 * passthrough when `inSection`.
 *
 * What each says comes from what the record already answers, read when the
 * view opens -- nothing is computed from prose:
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
import { getJson, useFacts } from '../conversation/facts'
import { Who } from '../identity/Who'
import { useCollection, useConversation } from '../conversation/hooks'
import { excerpt } from '../conversation/text'
import { showWorkspaceContent } from '../conversation/threads'
import { registerSection, type SectionBodyProps } from './registry'
import { Filters } from './shared'

/** Somebody named by the record, drawn as everywhere (E2); else the words. */
const name = (id: Id | null | undefined, alias: string | null | undefined, otherwise: string) =>
  alias ? <Who id={id} name={alias} show="line" size={16} live /> : otherwise

function BriefView({ conversation, onOpenPost, chrome }: SectionBodyProps) {
  const conv = useConversation(conversation ?? null)
  const facts = useFacts(conversation ?? null)
  const coll = useCollection(conversation ? 'conversation:' + conversation : '')
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
  if (!conversation) return null
  return chrome({
    children: (
      <div className="fx-about-sec">
        <h4>What's going on</h4>
        {latest ? (
          <button className="fx-about-row" onClick={() => onOpenPost(conversation, latest.id)}>
            <span><Who id={latest.author} name={latest.author_name} show="line" size={16} live meta={`${latest.number != null ? `#${latest.number} · ` : ''}${ago(latest.at)}`} /></span>
            <span className="fx-faint">{excerpt(latest, 180) || 'no words: what it carries is in This post'}</span>
          </button>
        ) : <p className="fx-faint">Nobody else has written here yet.</p>}
        <h4>Waiting on you</h4>
        {facts.loading && !facts.data ? <p className="fx-faint">Reading…</p> : mine.length ? mine.map((o) => (
          <button key={o.expectation} className="fx-about-row" onClick={() => onOpenPost(conversation, o.turn)}>
            <span>{name(o.requested_by, o.requested_by_alias, 'Somebody')} needs: {o.expects}</span>
          </button>
        )) : <p className="fx-faint">Nothing here waits on you.</p>}
        <h4>Now</h4>
        <p className="fx-faint">{conv?.working ? `${conv.working} working here now` : 'Nobody is working here now'} · {conv?.posts ?? '…'} posts{conv?.included ? ` + ${conv.included} included` : ''} · {facts.data?.participants.length ?? '…'} people</p>
      </div>
    ),
  })
}

function ActionsView({ conversation, options, setOption, onOpenPost, chrome, inSection }: SectionBodyProps) {
  const facts = useFacts(conversation ?? null)
  const me = store.me
  /* The one option: everything owed here, or only what is owed to me (the
   *  facts' `owed` names who each is expected of, so both are read off the
   *  same answer). Offered where the choice is kept -- a section's feed
   *  options; the slide-out shows everything owed, as it always has. */
  const mine = inSection && options.owed === 'me'
  const all = facts.data?.owed ?? []
  const owed = mine ? all.filter((o) => !!me && o.expected_of === me) : all
  const fails = facts.data?.failures ?? []
  if (!conversation) return null
  if (facts.loading && !facts.data) return chrome({ children: <p className="fx-faint">Reading…</p> })
  return chrome({
    children: (
      <div className="fx-about-sec">
        {inSection && (
          <Filters label="what actions to show" className="fw-actions-tabs" value={mine ? 'me' : 'all'}
            items={[{ key: 'all' as const, label: 'Everything owed' }, { key: 'me' as const, label: 'Owed to me' }]}
            onPick={(k) => setOption('owed', k)} />
        )}
        <h4>Owed here, not answered · {owed.length}</h4>
        {owed.length === 0 && <p className="fx-faint">{mine ? 'Nothing here is owed to you.' : 'Nothing is owed here.'}</p>}
        {owed.slice(0, 60).map((o) => (
          <button key={o.expectation} className="fx-about-row" onClick={() => onOpenPost(conversation, o.turn)} data-expectation={o.expectation}>
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
    ),
  })
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

function FollowUpsView({ conversation, onOpenPost, chrome }: SectionBodyProps) {
  const [rows, setRows] = useState<TurnRow[] | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    if (!conversation) return
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
  if (!conversation) return null
  if (why) return chrome({ children: <p className="fx-faint">Could not read the follow ups: {why}</p> })
  if (!rows) return chrome({ children: <p className="fx-faint">Reading…</p> })
  return chrome({
    children: (
      <div className="fx-about-sec">
        <h4>Follow ups · {rows.length} <span className="fx-faint">in the newest 80 threads</span></h4>
        {rows.length === 0 && <p className="fx-faint">No side-notes wait to be carried, and no agent post here addresses nobody.</p>}
        {rows.map((t) => (
          <button key={t.id} className="fx-about-row" onClick={() => onOpenPost(conversation, t.id)}>
            <span><Who id={t.author} name={t.author_alias} show="line" size={16} live meta={`#${t.number} · ${ago(t.at)}${t.discovered_under ? ' · side-note nobody carries' : ' · addresses nobody'}`} /></span>
            <span className="fx-faint">{(t.parts ?? []).filter((x) => x.type === 'text').map((x) => x.text ?? '').join('').replace(/[#*`>_]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 160)}</span>
          </button>
        ))}
      </div>
    ),
  })
}

function MediaView({ conversation, onOpenPost, chrome }: SectionBodyProps) {
  const coll = useCollection(conversation ? 'conversation:' + conversation : '')
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
  if (!conversation) return null
  return chrome({
    children: (
      <div className="fx-about-sec">
        <h4>Media · {items.length} <span className="fx-faint">in the posts loaded here</span></h4>
        {items.length === 0 && <p className="fx-faint">No attachments in the posts loaded here.</p>}
        <div className="fx-media-grid">
          {items.map((m, i) => (
            <button key={m.ref + i} className="fx-media" title={`${m.name} · ${m.number != null ? '#' + m.number : ''}`}
              onClick={() => { onOpenPost(conversation, m.post); nav.showPage('this-post'); showWorkspaceContent() }}>
              {m.image ? <img src={`/api/artifacts/${m.ref}`} alt={m.name} loading="lazy" /> : <span className="fx-file">{m.name}</span>}
              <span className="fx-media-n">{m.number != null ? `#${m.number}` : ''}</span>
            </button>
          ))}
        </div>
      </div>
    ),
  })
}

interface GovernRow { entry: Id; kind: string; text: string; placed?: string[] }
function GuidanceView({ conversation, chrome }: SectionBodyProps) {
  const [g, setG] = useState<{ governing: GovernRow[]; candidates?: GovernRow[] } | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => {
    if (!conversation) return
    let live = true
    void getJson<{ governing: GovernRow[]; candidates?: GovernRow[] }>(`/api/conversations/${encodeURIComponent(conversation)}/governs`)
      .then((r) => live && setG(r)).catch((e: Error) => live && setWhy(e.message))
    return () => { live = false }
  }, [conversation])
  if (!conversation) return null
  if (why) return chrome({ children: <p className="fx-faint">Could not read what governs work here: {why}</p> })
  if (!g) return chrome({ children: <p className="fx-faint">Reading…</p> })
  const kind = (k: string) => k.replace(/[-_]/g, ' ')
  return chrome({
    children: (
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
    ),
  })
}

/* The slide-out's tabs offer them in this order; the About views read the
 *  conversation of the place they are in, so they are never offered on Home. */
registerSection({ show: 'brief', name: 'Brief', body: BriefView, scope: 'conversation' })
registerSection({
  show: 'actions', name: 'Actions', body: ActionsView, scope: 'conversation',
  defaults: { owed: 'all' },
  readOptions: (o) => ({ owed: o.owed === 'me' ? 'me' : 'all' }),
})
registerSection({ show: 'followups', name: 'Follow ups', body: FollowUpsView, scope: 'conversation' })
registerSection({ show: 'media', name: 'Media', body: MediaView, scope: 'conversation' })
registerSection({ show: 'guidance', name: 'Guidance', body: GuidanceView, scope: 'conversation' })
