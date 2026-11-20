/* FINDING SOMETHING HELD, BY ITS WORDS.
 *
 * One finder for every place a record points at something else: what a
 * lesson or rule is based on, the question a decision settles, the
 * conversation or persona it applies to, the disciplines an activity uses.
 * The reader types words and chooses from what is found; the exact reference
 * travels underneath and is never shown.
 *
 * WHAT IT REACHES is everything the server accepts as a reference there:
 * Brain records, conversation posts, and passages of held files. Nothing is
 * narrowed below what could be cited before, when a reference had to be
 * typed. A link or an id somebody already has can still be pasted, as an
 * ADVANCED option that says what it accepts: it is looked up by exact id and
 * shown in words before it can be added (`pasted.ts`), so an exact citation
 * made elsewhere is not lost and nobody has to know what an id is.
 *
 * No second search: records come from the Brain browser's own read, posts
 * from the search Mentis already has (`/api/references`), files from the
 * source search (`/api/sources/search`). */
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { qs, read, type Id } from '../../../api'
import { isTurn, type Found, type Hit } from '../../../search'
import type { SearchAnswer } from '../../../surfaces/sources/route'
import { useDisciplines } from '../../../surfaces/governance/R2Inputs'
import { fetchBrainPage } from '../data'
import type { Ref } from './model'
import { resolvePasted } from './pasted'

export { PASTED, resolvePasted } from './pasted'

export type Scope = 'records' | 'posts' | 'files' | 'disciplines' | 'conversations' | 'personas'

const SCOPE_WORDS: Record<Scope, string> = {
  records: 'Brain records', posts: 'Posts', files: 'Files', disciplines: 'Disciplines', conversations: 'Conversations', personas: 'Personas',
}
const EMPTY_WORDS: Partial<Record<Scope, string>> = {
  posts: 'Type a few words to find a post.', files: 'Type a few words to find a passage in a file.',
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).replace(/[-_]/g, ' ')
const clip = (s: string, n = 220) => { const t = s.replace(/\s+/g, ' ').trim(); return t.length > n ? t.slice(0, n - 1).trimEnd() + '…' : t }

/** A file citation the basis door takes: the held file, or bytes of it. */
const FILE_CITE = /^adm-[0-9a-f]{12}(@[0-9a-f]{12,64}\[\d+:\d+\])?$/

/** What one scope finds for these words. Pure reads; each maps the server's
 *  own answer to words a person can choose from. */
export async function find(scope: Scope, q: string, here: Id | null): Promise<Ref[]> {
  const words = q.trim()
  if (scope === 'records') {
    const page = await fetchBrainPage({ view: 'all', q: words, limit: 30 })
    return page.items.map((r) => {
      const label = clip(r.summary || r.text || 'No words recorded')
      /* its own wording under the one-sentence summary, where they differ */
      const said = clip(r.text || '', 160)
      return {
        ref: r.id, label, kind: cap(r.kind || 'record'), desc: said && said !== label && !label.startsWith(said.replace(/…$/, '')) ? said : undefined,
        note: [r.by ? `recorded by ${r.by}` : '', r.conversationName ? `in ${r.conversationName}` : ''].filter(Boolean).join(' · '),
      }
    })
  }
  if (scope === 'posts') {
    if (!words) return []
    const got = await read<Found>(`/api/references${qs({ q: words, conversation: here, limit: 30 })}`)
    /* A POST IS FOUND BY ITS PROSE OR BY SOMETHING IN IT (a checklist's title,
       one of its lines), and the search answers each as its own hit on the
       same post. Each post is listed once, with the words that matched, so a
       row never reads as just "a post". */
    const seen = new Set<string>()
    return got.found.filter(isTurn).filter((h) => (seen.has(h.ref) ? false : (seen.add(h.ref), true))).map((h) => {
      const inside = h as Hit & { label?: string; field?: string; title?: string }
      return {
        ref: h.ref, label: clip(h.said || inside.label || inside.field || inside.title || h.name || 'A post with no words'), kind: 'Post',
        note: [h.number != null ? `#${h.number}` : '', h.conversation_name].filter(Boolean).join(' · '),
      }
    })
  }
  if (scope === 'files') {
    if (!words) return []
    const got = await read<SearchAnswer>(`/api/sources/search${qs({ q: words })}`)
    return got.hits.map((h) => ({
      /* THE EXACT PASSAGE WHERE THE BASIS DOOR TAKES ONE. It reads a direct
         citation (bytes of the held file) and nothing else
         (`ladder_writes.basis_reference`); a passage found in an EXTRACTION
         (a PDF's text) has a citation that door refuses, so the file itself
         is what can be cited, and the row says so rather than appearing to
         cite the passage. */
      ref: h.unit === 'byte' && FILE_CITE.test(h.cite) ? h.cite : h.ref,
      label: clip(h.snippet || h.label), kind: 'File',
      note: [h.label, h.collection_name, h.line != null ? `line ${h.line}` : h.display,
        h.unit === 'byte' && FILE_CITE.test(h.cite) ? '' : 'cites the whole file'].filter(Boolean).join(' · '),
    }))
  }
  if (scope === 'conversations') {
    const got = await read<{ conversations: { id: Id; name: string }[] }>('/api/conversations')
    return got.conversations.map((c) => ({ ref: c.id, label: c.name || 'Unnamed conversation', kind: 'Conversation' }))
  }
  if (scope === 'personas') {
    const got = await read<{ personas: { persona: Id; name: string }[] }>('/api/personas')
    return got.personas.map((p) => ({ ref: p.persona, label: p.name, kind: 'Persona' }))
  }
  return []
}

function Disciplines({ q, onFound }: { q: string; onFound: (rows: Ref[], more: boolean) => void }) {
  const { choices, more } = useDisciplines(q)
  const key = choices.map((c) => c.id).join(',')
  useEffect(() => { onFound(choices.map((c) => ({ ref: c.id, label: c.name.replace(/\s*\((\w[\w -]*)\)$/, ''), kind: cap(/\((\w[\w -]*)\)$/.exec(c.name)?.[1] ?? 'discipline') })), more) },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, more])
  return null
}

export default function Finder({ label, scopes, chosen, multi = true, here = null, paste = false, onToggle, onDone }: {
  /** what is being chosen, said to a screen reader and above the box */
  label: string
  scopes: Scope[]
  chosen: Ref[]
  multi?: boolean
  /** the conversation the reader is in: its posts are found first */
  here?: Id | null
  /** offer, as an advanced option, to paste a link or id somebody already has */
  paste?: boolean
  onToggle: (r: Ref) => void
  onDone: () => void
}) {
  const [scope, setScope] = useState<Scope>(scopes[0])
  const [q, setQ] = useState('')
  const [rows, setRows] = useState<Ref[]>([])
  const [more, setMore] = useState(false)
  const [state, setState] = useState<'idle' | 'reading' | 'failed'>('idle')
  const [why, setWhy] = useState('')
  const [act, setAct] = useState(0)
  const [pasting, setPasting] = useState(false)
  const [pasted, setPasted] = useState('')
  const [pasteWhy, setPasteWhy] = useState('')
  const [looking, setLooking] = useState(false)
  /* what the pasted text IS, as the server answered: shown before it is added */
  const [resolved, setResolved] = useState<Ref | null>(null)
  const pastedNow = useRef('')
  pastedNow.current = pasted
  const addBtn = useRef<HTMLButtonElement>(null)
  const id = useId()
  const input = useRef<HTMLInputElement>(null)
  const list = useRef<HTMLUListElement>(null)
  useEffect(() => { input.current?.focus() }, [])

  useEffect(() => {
    if (scope === 'disciplines') return
    let stale = false
    setState('reading')
    const t = window.setTimeout(() => {
      find(scope, q, here).then((r) => { if (!stale) { setRows(r); setMore(false); setState('idle'); setAct(0) } },
        (e: Error) => { if (!stale) { setRows([]); setWhy(e.message); setState('failed') } })
    }, q ? 220 : 0)
    return () => { stale = true; window.clearTimeout(t) }
  }, [scope, q, here])

  /* a short fixed list is narrowed here, as the reader types */
  const shown = useMemo(() => {
    if (scope !== 'conversations' && scope !== 'personas') return rows
    const words = q.toLowerCase().split(/\s+/).filter(Boolean)
    return rows.filter((r) => words.every((w) => r.label.toLowerCase().includes(w)))
  }, [rows, q, scope])
  const at = Math.min(act, Math.max(0, shown.length - 1))
  useEffect(() => { list.current?.children[at]?.scrollIntoView?.({ block: 'nearest' }) }, [at])
  const has = (r: Ref) => chosen.some((c) => c.ref === r.ref)
  /* one to choose: choosing it is the whole act, and whoever asked closes */
  const pick = (r: Ref) => { onToggle(r) }

  const key = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setAct(Math.min(shown.length - 1, at + 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setAct(Math.max(0, at - 1)) }
    /* Enter chooses the row that is highlighted ON SCREEN. While a new search
       is out that row still answers the earlier words, and it is still the
       one the reader is looking at: choosing anything else, or nothing, would
       be the surprise. */
    else if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); e.stopPropagation(); if (shown[at]) pick(shown[at]) }
  }
  /* LOOKED UP FIRST, ADDED SECOND. Nothing pasted is added until the server
     has said what it is and the reader has seen that; what cannot be resolved
     says so and adds nothing. */
  const lookUp = async () => {
    const asked = pasted
    if (looking || !asked.trim()) return
    setPasteWhy(''); setResolved(null); setLooking(true)
    try { const r = await resolvePasted(asked); if (pastedNow.current === asked) setResolved(r) }
    catch (e) { if (pastedNow.current === asked) setPasteWhy((e as Error).message) }
    finally { setLooking(false) }
  }
  useEffect(() => { if (resolved) addBtn.current?.focus() }, [resolved])
  const endPaste = () => { setPasted(''); setResolved(null); setPasteWhy(''); setPasting(false); input.current?.focus() }
  const addResolved = () => { if (resolved && !has(resolved)) onToggle(resolved); endPaste() }

  return (
    <div className="ba-finder" data-finder>
      {scope === 'disciplines' && <Disciplines q={q} onFound={(r, m) => { setRows(r); setMore(m); setState('idle') }} />}
      {scopes.length > 1 && (
        <div className="ba-scopes" role="tablist" aria-label="Where to look">
          {scopes.map((s) => (
            <button key={s} type="button" role="tab" aria-selected={scope === s} tabIndex={scope === s ? 0 : -1}
              onClick={() => { setScope(s); setRows([]); setAct(0); input.current?.focus(); input.current?.select() }}
              onKeyDown={(e) => {
                const i = scopes.indexOf(s)
                const to = e.key === 'ArrowRight' ? scopes[(i + 1) % scopes.length] : e.key === 'ArrowLeft' ? scopes[(i - 1 + scopes.length) % scopes.length] : null
                if (to) { e.preventDefault(); setScope(to); setRows([]); (e.currentTarget.parentElement?.children[scopes.indexOf(to)] as HTMLElement | undefined)?.focus() }
              }}>{SCOPE_WORDS[s]}</button>
          ))}
        </div>
      )}
      <input ref={input} type="text" role="combobox" aria-expanded="true" aria-controls={id} aria-label={label} autoComplete="off" spellCheck={false}
        aria-activedescendant={shown.length ? `${id}-${at}` : undefined}
        placeholder={`Search ${SCOPE_WORDS[scope].toLowerCase()} by any words…`} value={q}
        onChange={(e) => { setQ(e.target.value); setAct(0) }} onKeyDown={key} />
      <ul ref={list} id={id} role="listbox" aria-label={label} aria-multiselectable={multi || undefined}>
        {shown.map((r, i) => (
          <li key={r.ref} id={`${id}-${i}`} role="option" aria-selected={has(r)} className={i === at ? 'at' : undefined}
            onMouseDown={(e) => e.preventDefault()} onClick={() => { setAct(i); pick(r) }}>
            {multi && <span className="ba-box" aria-hidden="true" />}
            <span className="ba-found"><span className="ba-found-words">{r.label}</span>
              {r.desc && <span className="ba-found-desc">{r.desc}</span>}
              <span className="ba-found-note">{[r.kind, r.note].filter(Boolean).join(' · ')}</span></span>
          </li>
        ))}
        {!shown.length && <li className="ba-none" role="presentation">{state === 'failed' ? `Could not search: ${why}`
          : state === 'reading' ? 'Searching…' : !q.trim() && EMPTY_WORDS[scope] ? EMPTY_WORDS[scope] : 'Nothing matches. Try other words.'}</li>}
      </ul>
      {more && <p className="ba-none">More exist than are listed; type to narrow them.</p>}
      {pasting && (
        <div className="ba-paste" data-paste>
          <label htmlFor={`${id}-paste`}>Paste a link or an id <span className="ba-adv">Advanced</span></label>
          <p className="ba-hint" id={`${id}-paste-hint`}>A link copied from a record or a post, or an id an agent gave you. It is looked up exactly and shown to you before it is added. Searching by words above finds the same things.</p>
          <div className="ba-paste-row">
            <input id={`${id}-paste`} type="text" value={pasted} autoFocus spellCheck={false} autoComplete="off" aria-describedby={`${id}-paste-hint`}
              onChange={(e) => { setPasted(e.target.value); setPasteWhy(''); setResolved(null) }}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); void lookUp() } }} />
            <button type="button" className="ba-btn s" data-paste-look disabled={looking || !pasted.trim()} onClick={() => void lookUp()}>{looking ? 'Looking…' : 'Look it up'}</button>
          </div>
          {resolved && (
            <div className="ba-resolved" role="status" data-paste-found>
              <span className="ba-resolved-n">{has(resolved) ? 'Already chosen:' : 'This is:'}</span>
              <span className="ba-found"><span className="ba-found-words">{resolved.label}</span>
                <span className="ba-found-note">{[resolved.kind, resolved.note].filter(Boolean).join(' · ')}</span></span>
              <span className="ba-resolved-acts">
                <button ref={addBtn} type="button" className="ba-btn s" data-paste-add onClick={addResolved}>{has(resolved) ? 'OK' : 'Add it'}</button>
                {!has(resolved) && <button type="button" className="ba-quiet" onClick={() => { setResolved(null); setPasted(''); document.getElementById(`${id}-paste`)?.focus() }}>Not this one</button>}
              </span>
            </div>
          )}
          {pasteWhy && <p className="ba-err" role="alert" data-paste-refused>{pasteWhy}</p>}
        </div>
      )}
      <div className="ba-finder-foot">
        <span>{chosen.length && multi ? `${chosen.length} chosen` : '↑ ↓ to move, Enter to choose'}</span>
        {paste && !pasting && <button type="button" className="ba-quiet" data-paste-open title="For a link or id you already have" onClick={() => setPasting(true)}>Advanced: paste a link or id</button>}
        {pasting && <button type="button" className="ba-quiet" onClick={endPaste}>Close paste</button>}
        <button type="button" className="ba-btn s" data-finder-done onClick={onDone}>Done</button>
      </div>
    </div>
  )
}
