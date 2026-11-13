/* WHAT IS LEFT OF A PERMANENTLY DELETED CONVERSATION.
 *
 *   DeletedList     "Deleted conversations", opened from the quiet link at
 *                   the foot of the Trash tab: one row per tombstone, newest
 *                   deletion first -- never a name or a word of it.
 *   TombstoneView   a deleted conversation, opened (from that list, or from
 *                   any link to it): when it was made, when and by whom it
 *                   was deleted, what was removed (counts), and the records
 *                   and relationships that survive it. Nothing of its content
 *                   can be read or recovered from here.
 *
 * Both read the server (`store.deletedConversations`, `store.tombstone`);
 * nothing here writes. */
import './conversations.css'
import { useEffect, useState } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { store, type Id, type SurvivingRecord, type Tombstone } from '../../fluid/store'
import { READ_ONLY } from '../live'
import { cleanupMeaning, cleanupOf, cleanupOffered, cleanupWords, dayWord, recordWords, relationWords, tombstoneLabel, type Cleanup } from './manage'

/* -- who: participants' names, read once ------------------------------------ */
let people: Promise<Map<Id, string>> | null = null
function readPeople(): Promise<Map<Id, string>> {
  people ??= fetch('/fluid/api/participants?limit=500', { headers: CLIENT_HEADERS })
    .then((r) => (r.ok ? r.json() : { participants: [] }))
    .then((j: { participants?: { id: Id; alias: string }[] }) => new Map((j.participants ?? []).map((p) => [p.id, p.alias])))
    .catch(() => { people = null; return new Map<Id, string>() })
  return people
}
function usePeople(): Map<Id, string> {
  const [m, setM] = useState<Map<Id, string>>(new Map())
  useEffect(() => { let live = true; void readPeople().then((x) => { if (live) setM(x) }); return () => { live = false } }, [])
  return m
}

const Bin = () => (
  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2.5 4.5h11M6 4.5V3h4v1.5M4 4.5l.7 9h6.6l.7-9M6 7.5l4 4M10 7.5l-4 4" /></svg>
)

/** "Deleted conversations": the list inside the conversation card. */
export function DeletedList({ onOpen, onBack }: { onOpen: (id: Id) => void; onBack: () => void }) {
  const [rows, setRows] = useState<Tombstone[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const who = usePeople()
  useEffect(() => {
    let live = true
    store.deletedConversations().then((t) => { if (live) setRows(t) }, (e: unknown) => { if (live) setError(`Could not read the deleted conversations: ${e instanceof Error ? e.message : String(e)}`) })
    return () => { live = false }
  }, [])
  return (
    <div className="q2-cl-deleted">
      <div className="q2-cl-deleted-head">
        <button type="button" className="q2-link-quiet q2-cl-back" autoFocus onClick={onBack}>← Trash</button>
        <h3>Deleted conversations</h3>
      </div>
      <p className="q2-cl-deleted-note">Only that they existed is kept, and the records that came from them. Nothing here can be restored.</p>
      <ul className="q2-cl-list" role="list" aria-busy={!rows && !error || undefined}>
        {(rows ?? []).map((t) => {
          const by = t.deleted_by ? who.get(t.deleted_by) ?? null : null
          const clean = cleanupOf(t.physical_cleanup)
          return (
            <li key={t.id} className="q2-cl-row deleted" data-id={t.id}>
              <button type="button" className="q2-cl-open" aria-label={`${tombstoneLabel(t, by)}, ${cleanupWords(clean).toLowerCase()}`} onClick={() => onOpen(t.id)}>
                <span className="q2-cl-name"><Bin /> Deleted conversation</span>
                <span className={'q2-cl-time' + (clean.status === 'failed' ? ' q2-cl-failed' : '')}>deleted {dayWord(t.deleted_at)}{clean.status !== 'completed' ? ` · ${clean.status === 'failed' ? 'cleanup failed' : clean.status === 'pending' ? 'cleanup pending' : ''}` : ''}</span>
              </button>
            </li>
          )
        })}
        {rows && !rows.length && <li className="q2-cl-note">No conversation has been permanently deleted.</li>}
        {!rows && !error && <li className="q2-cl-note">Reading…</li>}
        {error && <li className="q2-cl-note" role="alert">{error}</li>}
      </ul>
    </div>
  )
}

const when = (at: number | null | undefined) => (at ? new Date(at * 1000).toLocaleString([], { day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit' }) : 'an unrecorded time')

/** PHYSICAL CLEANUP: its verified status, and "Finish cleanup" while it is
 *  pending or failed (the owner's explicit act; nothing retries by itself). */
function CleanupLine({ id, cleanup, onDone }: { id: Id; cleanup: Cleanup; onDone: (c: Cleanup) => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const finish = async () => {
    setBusy(true); setErr(null)
    try {
      const author = store.me ?? await store.loadMe()
      const got = await store.finishCleanup(id, author)
      const now = cleanupOf(got.physical_cleanup ?? (got as { status?: string }).status as never)
      if (now.status === 'unknown') { const t = await store.tombstone(id); onDone(cleanupOf(t?.physical_cleanup)) } else onDone(now)
    } catch (e: unknown) {
      setErr(`Could not finish the cleanup: ${e instanceof Error ? e.message : String(e)}`)
    } finally { setBusy(false) }
  }
  return (
    <div className={`q2-tomb-cleanup q2-cleanup-${cleanup.status}`} role="status">
      <p><b>{cleanupWords(cleanup)}</b> <span>{cleanupMeaning(cleanup)}</span></p>
      {cleanupOffered(cleanup) && !READ_ONLY && (
        <button type="button" className="q2-quiet-btn" disabled={busy} onClick={() => void finish()}>{busy ? 'Finishing cleanup…' : 'Finish cleanup'}</button>
      )}
      {err && <p className="q2-state-failed" role="alert">{err}</p>}
    </div>
  )
}

/** A SURVIVING RECORD'S OWN BASIS, read from the Ladder (`/api/ladder/items/<id>`):
 *  each reference it rests on, a deleted post or conversation said so as a
 *  quiet chip -- never a broken link, never its former words. */
interface BasisRef { ref: Id; relation: string; kind: string | null; label: string | null }
function BasisOf({ id }: { id: Id }) {
  const [rows, setRows] = useState<{ b: BasisRef; deleted: 'post' | 'conversation' | null; words: string }[] | null>(null)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    void (async () => {
      const r = await fetch(`/api/ladder/items/${encodeURIComponent(id)}`, { headers: CLIENT_HEADERS })
      const j = await r.json().catch(() => null) as { basis?: BasisRef[]; error?: string } | null
      if (!r.ok || !j || j.error) throw new Error(j?.error ?? r.statusText)
      const basis = j.basis ?? []
      const posts = basis.filter((b) => b.kind === 'contribution').map((b) => b.ref)
      const convs = basis.filter((b) => b.kind === 'conversation').map((b) => b.ref)
      await Promise.all([posts.length ? store.loadPosts(posts, true) : null, convs.length ? store.loadConversations(convs) : null])
      return basis.map((b) => {
        const p = store.posts.get(b.ref) as ({ erased?: boolean; deleted?: unknown; home_name?: string | null; number?: number | null } | undefined)
        const c = store.conversations.get(b.ref)
        if (p?.erased) return { b, deleted: 'post' as const, words: '' }
        if (c?.state === 'deleted') return { b, deleted: 'conversation' as const, words: '' }
        const words = p ? `a post${p.number ? ` #${p.number}` : ''}${p.home_name ? ` in ${p.home_name}` : ''}` : c ? `“${c.name}”` : (b.label || b.ref)
        return { b, deleted: null, words }
      })
    })().then((x) => { if (live) setRows(x) }, (e: unknown) => { if (live) setErr(e instanceof Error ? e.message : String(e)) })
    return () => { live = false }
  }, [id])
  if (err) return <p className="q2-tomb-note" role="alert">Could not read what it rests on: {err}</p>
  if (!rows) return <p className="q2-tomb-note" role="status">Reading what it rests on…</p>
  if (!rows.length) return <p className="q2-tomb-note">It names no basis.</p>
  return (
    <ul className="q2-tomb-basis" aria-label="What it rests on">
      {rows.map(({ b, deleted, words }) => (
        <li key={b.ref + b.relation}>{b.relation.replace(/[-_]/g, ' ')}{' '}
          {deleted ? <span className="q2-deleted-chip" title="Permanently deleted: nothing of it can be shown">{deleted === 'post' ? 'Deleted post' : 'Deleted conversation'}</span> : <span>{words}</span>}
        </li>
      ))}
    </ul>
  )
}

function SurvivingRow({ r }: { r: SurvivingRecord }) {
  const [open, setOpen] = useState(false)
  return (
    <li>
      <span className="q2-tomb-record">{recordWords(r)}</span>
      <span className="q2-tomb-rel">{relationWords(r.relation)} · its source is <span className="q2-deleted-chip">deleted</span></span>
      <span className="q2-tomb-idrow"><code title="This record's identity in Mentis">{r.id}</code>
        <button type="button" className="q2-link-quiet" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? 'Less' : 'What it rests on'}</button></span>
      {open && <BasisOf id={r.id} />}
    </li>
  )
}

/** A deleted conversation, opened: its tombstone and what survives it. */
export function TombstoneView({ id }: { id: Id }) {
  const [t, setT] = useState<Tombstone | null | undefined>(undefined)
  const [error, setError] = useState<string | null>(null)
  const who = usePeople()
  useEffect(() => {
    let live = true
    setT(undefined); setError(null)
    store.tombstone(id).then((x) => { if (live) setT(x) }, (e: unknown) => { if (live) setError(e instanceof Error ? e.message : String(e)) })
    return () => { live = false }
  }, [id])
  if (error) return <p className="q2-filter" role="alert">Could not read what is left of it: {error}</p>
  if (t === undefined) return <p className="q2-tomb-note" role="status">Reading what is left of it…</p>
  if (t === null) return <p className="q2-tomb-note">This conversation is not deleted.</p>
  const c = t.counts ?? {}
  const name = (x: Id | null) => (x ? who.get(x) ?? 'somebody' : 'somebody')
  const removed = [
    c.posts ? `${c.posts} ${c.posts === 1 ? 'post' : 'posts'}` : null,
    c.replies ? `${c.replies} ${c.replies === 1 ? 'reply' : 'replies'}` : null,
    c.versions ? `${c.versions} earlier ${c.versions === 1 ? 'version' : 'versions'}` : null,
    c.files_removed ? `${c.files_removed} ${c.files_removed === 1 ? 'file' : 'files'} only it held (unreadable now; bytes per cleanup below)` : null,
    c.runs_material ? `what agents were sent (${c.runs_material})` : null,
  ].filter(Boolean)
  const records = t.surviving_records ?? []
  return (
    <section className="q2-tomb" aria-label="What is left of a deleted conversation">
      <p className="q2-tomb-facts">
        <span className="q2-state-chip"><Bin />Permanently deleted</span>
        <span>Created {when(t.created)}{t.created_by ? ` by ${name(t.created_by)}` : ''}</span>
        <span>Deleted {when(t.deleted_at)} by {name(t.deleted_by)}</span>
      </p>
      <p className="q2-tomb-lead">Its posts, replies and the files only it held can no longer be read through Mentis, and cannot be recovered here.</p>
      <CleanupLine id={t.id} cleanup={cleanupOf(t.physical_cleanup)} onDone={(c) => setT((x) => (x ? { ...x, physical_cleanup: { status: c.status as 'pending', reason: c.reason } } : x))} />
      <dl className="q2-tomb-dl">
        <div><dt>Removed</dt><dd>{removed.length ? removed.join(' · ') : 'nothing but its name'}</dd></div>
        <div><dt>Kept</dt><dd>
          That it existed, and who did what and when{c.acts ? ` (${c.acts} activity ${c.acts === 1 ? 'record' : 'records'})` : ''}, without the content.
          {c.files_kept ? ` ${c.files_kept} shared ${c.files_kept === 1 ? 'file stays' : 'files stay'} where ${c.files_kept === 1 ? 'it is' : 'they are'} also held.` : ''}
        </dd></div>
      </dl>
      <h2 className="q2-tomb-h">{records.length ? `Records that survive it (${records.length})` : 'Records that survive it'}</h2>
      {records.length ? (
        <ul className="q2-tomb-records">
          {records.map((r) => <SurvivingRow key={r.id + r.relation} r={r} />)}
        </ul>
      ) : <p className="q2-tomb-note">No record was made from it.</p>}
    </section>
  )
}
