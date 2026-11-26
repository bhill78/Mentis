/** Magnet Management: the list, one Magnet's own page, and CREATION.
 *
 *  CREATION IS ONE SENTENCE AND ONE PRESS (owner's correction
 *  `ent-8a4357b5f7fc`, amendment `adm-c38044ee5157` §4: "Purpose-driven
 *  creation should lead directly to activation and useful results, without
 *  requiring the user to navigate several configuration screens").
 *
 *  What it used to be: a Name field, a sentence saying a name was enough, and
 *  an optional Conversation picker -- after which the owner had an empty Magnet
 *  and a tour of Settings ahead of them before anything was ever collected.
 *
 *  What it is now: the owner says what they want to follow. As they finish
 *  typing, the server proposes -- these sources, this much of them, this often
 *  -- in ordinary words, having written nothing (`proposeMagnet`). One press
 *  applies that configuration, runs the first collection, turns periodic
 *  refresh on and opens the Magnet on its collected items
 *  (`acceptProposal`). A name is derived from the sentence, never demanded.
 *  `Adjust` is one disclosure, not a screen: the name, and which of the
 *  proposed sources to keep.
 *
 *  NOTHING HERE ROUTES THROUGH SETTINGS. Settings is where the owner goes to
 *  CHANGE something later; it is not a step in getting started, and creation
 *  does not mention it except where there is genuinely nothing to collect yet. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { MagnetConfig } from '../../fluid/surface/magnet/types'
import type { SavedMagnet } from './contract'
import { acceptProposal, listMagnets, proposeMagnet, type MagnetProposal } from './managementApi'
import { collectionRhythm, magnetName } from './configuration'
import { resourcesOfBrain } from '../space/registry'
import type { QuietMagnetResource } from './navigation'
import CollectionConfiguration from './CollectionConfiguration'
import '../brain/brain.css'
import './management.css'

export type MagnetFilter = 'all' | 'available' | 'unavailable'

export function listedMagnets(rows: SavedMagnet[], query: string, filter: MagnetFilter): SavedMagnet[] {
  const words = query.trim().toLocaleLowerCase()
  return rows.filter((row) => {
    if (filter === 'available' && (row.reason || !row.config)) return false
    if (filter === 'unavailable' && !row.reason && row.config) return false
    return !words || `${row.name} ${row.id}`.toLocaleLowerCase().includes(words)
  })
}

export const openableMagnet = (row: SavedMagnet | undefined): row is SavedMagnet & { config: MagnetConfig } =>
  !!row?.config && !row.reason

const TABS: { id: MagnetFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'available', label: 'Available' },
  { id: 'unavailable', label: 'Needs attention' },
]

export default function Management(p: {
  open: boolean; brainKey: string | null; conversation: string | null;
  canCreate(id: string): boolean; fixture: boolean;
  onOpen(saved: SavedMagnet): void; onClose(): void;
}) {
  const [rows, setRows] = useState<SavedMagnet[] | null>(null)
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<MagnetFilter>('all')
  const [selected, setSelected] = useState('')
  const [view, setView] = useState<'list' | 'detail' | 'create'>('list')
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  /** What the owner said they want to follow: the whole of what creation asks. */
  const [want, setWant] = useState('')
  const [proposal, setProposal] = useState<MagnetProposal | null>(null)
  const [proposing, setProposing] = useState(false)
  /** The two things `Adjust` discloses: the derived name, and which of the
   *  proposed sources to keep. Nothing else, and no screen. */
  const [adjusting, setAdjusting] = useState(false)
  const [name, setName] = useState('')
  const [dropped, setDropped] = useState<number[]>([])
  const [creating, setCreating] = useState(false)
  const [createWords, setCreateWords] = useState('')
  const operation = useRef<string | null>(null)
  const box = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const identity = useRef(p.brainKey); identity.current = p.brainKey
  const current = useRef(p); current.current = p

  useEffect(() => {
    if (!p.open || !p.brainKey) return
    const ctl = new AbortController(), key = p.brainKey
    setError(null)
    void listMagnets(ctl.signal).then((found) => {
      if (ctl.signal.aborted || identity.current !== key) return
      setRows(found)
      setSelected((old) => found.some((row) => row.id === old) ? old : '')
    }, (e: unknown) => {
      if (!ctl.signal.aborted && identity.current === key) { setRows([]); setError(e instanceof Error ? e.message : String(e)) }
    })
    return () => ctl.abort()
  }, [p.open, p.brainKey, revision])

  /** THE PROPOSAL ARRIVES WHILE THE SENTENCE IS BEING TYPED, so the only press
   *  in creation is the one that accepts it. The proposal command writes
   *  nothing, on the server or here, so asking again as the sentence changes
   *  costs the record nothing and leaves nothing behind if the owner walks
   *  away. The previous ask is abandoned rather than raced. */
  useEffect(() => {
    if (!p.open || view !== 'create' || !p.brainKey || creating) return
    const said = want.trim()
    if (!said) { setProposal(null); setProposing(false); setCreateWords(''); return }
    const ctl = new AbortController(), key = p.brainKey
    const timer = window.setTimeout(() => {
      setProposing(true)
      void proposeMagnet(said, undefined, ctl.signal).then((got) => {
        if (ctl.signal.aborted || identity.current !== key) return
        setProposal(got); setName(got.name); setDropped([]); setCreateWords(''); setProposing(false)
        operation.current = null
      }, (e: unknown) => {
        if (ctl.signal.aborted || identity.current !== key) return
        setProposal(null); setProposing(false)
        setCreateWords(e instanceof Error ? e.message : String(e))
      })
    }, 400)
    return () => { clearTimeout(timer); ctl.abort() }
  }, [p.open, p.brainKey, view, want, creating])

  useLayoutEffect(() => {
    if (p.open) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
      requestAnimationFrame(() => input.current?.focus({ preventScroll: true }))
    } else {
      const to = opener.current; opener.current = null
      if (to && document.contains(to)) to.focus({ preventScroll: true })
    }
  }, [p.open])

  useEffect(() => {
    setView('list'); setSelected(''); setName(''); setWant(''); setProposal(null)
    setAdjusting(false); setDropped([]); setCreateWords(''); operation.current = null
  }, [p.brainKey])

  useEffect(() => {
    if (!want.trim() && !creating) return
    const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [want, creating])

  if (!p.open) return null
  const shown = listedMagnets(rows ?? [], query, filter)
  const chosen = rows?.find((row) => row.id === selected)
  const leave = () => p.onClose()
  const trap = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      if (view !== 'list') { setView('list'); requestAnimationFrame(() => input.current?.focus()) } else leave()
      return
    }
    if (e.key !== 'Tab' || !box.current) return
    const stops = [...box.current.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), [href]')].filter((el) => el.offsetParent !== null)
    if (!stops.length) return
    const first = stops[0], last = stops[stops.length - 1]
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
  }
  const back = () => { setView('list'); requestAnimationFrame(() => input.current?.focus({ preventScroll: true })) }
  const kept = (proposal?.listed ?? []).map((row, i) => ({ ...row, i })).filter((row) => !dropped.includes(row.i))
  /** ONE PRESS: APPLY, COLLECT, AND BE LOOKING AT THE RESULTS.
   *
   *  `acceptProposal` does the three existing doors in order and reports what
   *  the first collection actually did. Whatever it did, the Magnet is opened
   *  on its COLLECTED ITEMS, not on a configuration summary and not on an
   *  empty Summary -- and if the collection was empty or failed, those words
   *  are put where the results would be, so the screen is never silent. */
  const accept = async () => {
    if (creating || !proposal || !p.brainKey || !p.canCreate('home')) return
    const key = p.brainKey
    const issue = name.trim() ? null : 'Give this Magnet a name, or leave the one derived from your sentence.'
    if (issue) { setCreateWords(issue); return }
    const sources = proposal.sources.filter((_, i) => !dropped.includes(i))
    const asked: MagnetProposal = { ...proposal, name: name.trim(), sources, seed: { ...proposal.seed, sources } }
    const op = operation.current ?? (operation.current = `quiet-magnet-${crypto.randomUUID()}`)
    setCreating(true); setCreateWords('Setting this Magnet up and collecting for the first time…')
    try {
      const done = await acceptProposal({ key, arrangement: 'home', proposal: asked, op, manual: !p.fixture })
      if (identity.current !== key) return
      operation.current = null; setRevision((n) => n + 1)
      setWant(''); setProposal(null); setName(''); setDropped([]); setAdjusting(false); setCreateWords('')
      current.current.onOpen(done.saved)
      // THE RESULTS ARE WHAT IS LEFT ON SCREEN. The card opens on its
      // collected items rather than its Summary, and what the first
      // collection did is said above them.
      const r = resourcesOfBrain<QuietMagnetResource>('magnet', key).find((v) => v.saved.id === done.saved.id)
      if (r) { r.update({ tab: 'All', overlay: null, collectionMessage: done.words }); void r.read() }
    } catch (e) {
      if (identity.current === key) setCreateWords(`${(e as Error).message} Your sentence and operation key are kept; pressing again repeats the same creation rather than making a second Magnet.`)
    } finally { if (identity.current === key) setCreating(false) }
  }

  return <div className="q2-brain-veil q2-magnet-veil" onPointerDown={(e) => { if (e.target === e.currentTarget) leave() }}>
    <div ref={box} className="q2-brain-card q2-magnet-management" role="dialog" aria-modal="true" aria-label="Magnet Management" onKeyDown={trap}>
      <div className="q2-cl">
        <header className="q2-cl-head">
          {view !== 'list' && <button type="button" className="q2-magnet-back" aria-label="Back to Magnets" onClick={back}>←</button>}
          <h2>{view === 'detail' ? chosen?.name ?? 'Magnet' : view === 'create' ? 'Follow something' : 'Magnets'}</h2>
          <span className="q2-brain-tools">
            {view === 'list' && <button type="button" className="q2-brain-more" aria-label="Follow something new" title="Follow something new" onClick={() => setView('create')}>+</button>}
            <button type="button" className="q2-cl-close" aria-label="Close" title="Close" onClick={leave}>×</button>
          </span>
        </header>

        {view === 'list' && <>
          <input ref={input} type="search" className="q2-cl-filter" value={query} placeholder="Find a Magnet" autoComplete="off" spellCheck={false}
            aria-label="Find a Magnet" onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Escape' && query) { e.preventDefault(); e.stopPropagation(); setQuery('') } }} />
          <div className="q2-cl-tabs" role="tablist" aria-label="Which Magnets">
            {TABS.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={filter === tab.id} tabIndex={filter === tab.id ? 0 : -1} onClick={() => setFilter(tab.id)}>{tab.label}</button>)}
          </div>
          <ul className="q2-brain-rows q2-magnet-rows" role="listbox" aria-label="Magnets">
            {!rows && !error && <li className="q2-cl-note" role="status">Reading Magnets…</li>}
            {error && <li className="q2-cl-note" role="alert">Could not read Magnets: {error}</li>}
            {rows && !shown.length && !error && <li className="q2-cl-note">{query.trim() || filter !== 'all' ? 'Nothing matches.' : 'No Magnets in this Brain yet.'}</li>}
            {shown.map((row) => <li key={row.id}>
              <button type="button" className="q2-brain-row" role="option" aria-selected={selected === row.id} data-magnet={row.id}
                onClick={() => { setSelected(row.id); setView('detail') }}>
                <span className="q2-brain-text"><span className="q2-brain-name">{row.name}</span>
                  <span className={'q2-brain-meta' + (row.reason ? ' q2-brain-off' : '')}>{row.reason ? 'Needs attention · definition unavailable here' : sourceSummary(row.config)}</span>
                </span>
              </button>
            </li>)}
          </ul>
          {rows && <p className="q2-brain-foot"><span>{shown.length} of {rows.length} {rows.length === 1 ? 'Magnet' : 'Magnets'}</span><button type="button" className="q2-link" onClick={() => setRevision((n) => n + 1)}>Refresh</button></p>}
        </>}

        {/* WHAT THIS MAGNET LOOKS AT COMES FIRST (owner request ent-068c167fa7e6
            §2: viewing and managing configured sources, with the administrative
            record disclosed rather than stacked in front of it). The identity,
            the saved modes and the Magnet's own Conversation are all still here
            and still exact; they are one press away instead of the first screen. */}
        {view === 'detail' && chosen && <div className="q2-magnet-detail">
          {chosen.reason && <p className="q2-magnet-alert" role="alert">{chosen.reason}</p>}
          {chosen.config && p.brainKey && <details className="q2-magnet-detail-config"><summary>Change sources and what to collect</summary><CollectionConfiguration key={chosen.id} magnet={chosen.id} config={chosen.config} brainKey={p.brainKey} canWrite={p.canCreate} onSaved={(config) => setRows((old) => old?.map((r) => r.id === chosen.id ? { ...r, config, reason: undefined } : r) ?? null)} /></details>}
          {/* DELETED (#802, amendment §4): this list used to recite `mag-…`
              as "Identity", `ent-…` as "Own Conversation", and the saved
              `collection`/`synthesis` MODE WORDS as facts -- four rows of the
              schema's own vocabulary and internal references, which no owner
              chose and none of which can be acted on. What is left is what
              this Magnet is, what it follows and how often, in ordinary
              words. Nothing was hidden that the owner can do anything with:
              the sources themselves are one press away above, the own
              Conversation is reached from the Magnet's own Settings, and the
              identity is in the record for anything that needs it. */}
          <details className="q2-magnet-detail-about"><summary>About this Magnet</summary>
            <dl>
              <div><dt>Name</dt><dd>{magnetName(chosen.config, chosen.name)}{magnetName(chosen.config, '') ? '' : ' · named after where it is shown'}</dd></div>
              {followsWhat(chosen.config) && <div><dt>Follows</dt><dd>{followsWhat(chosen.config)}</dd></div>}
              <div><dt>Looks at</dt><dd>{sourceSummary(chosen.config)}</dd></div>
              <div><dt>How often</dt><dd>{chosen.config ? collectionRhythm(chosen.config) : 'Unavailable here'}</dd></div>
            </dl>
          </details>
          <div className="q2-magnet-actions"><button type="button" className="q2-magnet-primary" disabled={!openableMagnet(chosen)} onClick={() => { if (openableMagnet(chosen)) p.onOpen(chosen) }}>Open in current workspace</button></div>
        </div>}

        {view === 'create' && <form className="q2-magnet-create" onSubmit={(e) => { e.preventDefault(); void accept() }}>
          {!p.canCreate('home') && <p className="q2-magnet-alert">{p.fixture ? 'Independent creation is disabled in this disposable fixture because it permits writes only to its test Conversation arrangement.' : 'Magnet creation is unavailable while this page cannot write to Brain Home.'}</p>}
          {/* ONE QUESTION. Not a name, not a source, not a mode: what the owner
              wants to follow, in their own words. */}
          <label className="q2-magnet-want"><span>What do you want to follow?</span>
            <textarea value={want} rows={2} maxLength={2000} disabled={creating} autoFocus
              placeholder="the solid electrolytes work, every day"
              onChange={(e) => { setWant(e.target.value); operation.current = null }} /></label>
          <p className="q2-magnet-help">One sentence is enough — Mentis works out what to follow and how often to look. Say “every day”, “hourly” or “every week” if you want a particular rhythm.</p>

          {proposing && !proposal && <p className="q2-magnet-help" role="status">Working out what that means…</p>}

          {proposal && <div className="q2-magnet-proposal" aria-live="polite">
            <h3>{name || proposal.name}</h3>
            <dl>
              <div><dt>Follows</dt><dd>{kept.length ? kept.map((row) => row.title).join(' · ') : proposal.words.sources}</dd></div>
              <div><dt>Collects</dt><dd>{proposal.words.collect}</dd></div>
              <div><dt>Looks again</dt><dd>{proposal.words.cadence}</dd></div>
            </dl>
            {!!proposal.unavailable.length && <details className="q2-magnet-unavailable">
              <summary>{proposal.unavailable.length} {proposal.unavailable.length === 1 ? 'thing' : 'things'} this Magnet cannot read yet</summary>
              <ul>{proposal.unavailable.map((row) => <li key={`${row.kind}:${row.title}`}><strong>{row.title}</strong><span> — {row.why}</span></li>)}</ul>
            </details>}
            {/* ADJUST IS ONE DISCLOSURE, NOT A SCREEN: the derived name, and
                which of the proposed sources to keep. The rhythm is said in
                the sentence, and everything else is changed later in Settings,
                which creation never sends anybody to. */}
            <details open={adjusting} onToggle={(e) => setAdjusting(e.currentTarget.open)}>
              <summary>Adjust</summary>
              <label><span>Name</span><input value={name} maxLength={80} disabled={creating}
                onChange={(e) => setName(e.target.value)} /></label>
              {!!proposal.listed.length && <div className="q2-magnet-proposed-sources">
                {proposal.listed.map((row, i) => <label key={`${row.title}:${i}`}>
                  <input type="checkbox" checked={!dropped.includes(i)} disabled={creating}
                    onChange={(e) => setDropped(e.target.checked ? dropped.filter((d) => d !== i) : [...dropped, i])} />
                  <strong>{row.title}</strong><small>{row.says}</small>
                </label>)}
              </div>}
            </details>
          </div>}

          {createWords && <p className="q2-magnet-help" role="status">{createWords}</p>}
          <div className="q2-magnet-actions"><button type="submit" className="q2-magnet-primary"
            disabled={creating || !proposal || !name.trim() || !p.canCreate('home')}>
            {creating ? 'Setting it up…' : operation.current ? 'Try that again' : 'Follow this'}</button></div>
        </form>}
      </div>
    </div>
  </div>
}

/** WHAT A SOURCE IS, IN ORDINARY WORDS. The row used to end in the schema's
 *  own kind words (`conversation, file`), which named a shape in a JSON file
 *  rather than anything the owner recognises. */
const KIND_WORDS: Record<string, string> = {
  conversation: 'Conversations', file: 'held files', brain: 'Topics',
  web: 'web pages', database: 'databases', connector: 'connected services',
  other: 'other material', 'agent-results': 'agent results',
}
export function sourceSummary(config: SavedMagnet['config']): string {
  const sources = config?.sources ?? []
  if (!config) return 'Unavailable here'
  if (!sources.length) return 'Nothing yet · ready to converse'
  const kinds = [...new Set(sources.map((source) => KIND_WORDS[source.kind] ?? source.kind))]
  const said = kinds.length === 1 ? kinds[0]
    : `${kinds.slice(0, -1).join(', ')} and ${kinds[kinds.length - 1]}`
  return `${sources.length} ${sources.length === 1 ? 'source' : 'sources'} · ${said}`
}
/** What the owner said they wanted to follow, kept in the definition as the
 *  selection's own criteria when the Magnet was made from a sentence. */
export function followsWhat(config: SavedMagnet['config']): string {
  const said = config?.selection?.criteria
  return typeof said === 'string' ? said.trim() : ''
}
