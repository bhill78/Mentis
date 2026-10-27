import { useEffect, useMemo, useState } from 'react'
import { post, useApi, when, type Id, type DisputeRead } from '../../api'
import type { WorkspaceProps } from './Workspace'
import type { Row } from '../Register'
import { AskCard, onePerForm, type AskRow } from './Asks'
import ActDialog from './ActDialogs'
import R2Create from './R2Forms'
import R2Record from './R2Record'
import PreviewSheet from './PreviewSheet'
import ImportArchiveTab from '../../fluid/governance/ImportArchiveTab'
import { useAskCoverage } from './askCoverage'
import { filterRows, IMPORT_TAB, inConversation, KNOWN_TABS, tabsOf, waitingChallenges, type KindAuthoring } from './r2Model'
import './R2Workspace.css'

/** Is this one of the three sections the surface has always had? Anything
 *  else is a section a Kind declared, and is authored generically. */
const known = (section: string) => section === IMPORT_TAB[0] || KNOWN_TABS.some(([s]) => s === section)

export function Pills({ row }: { row: Row }) {
  return <span className="r2-pills"><span className={`r2-status ${row.state}`}>{row.state === 'stands' ? 'In force' : row.state === 'candidate' ? 'Proposed · reaches nobody' : row.state === 'ended' ? 'Ended or deleted' : row.state === 'replaced' ? 'Replaced before establishment' : 'Standing undeclared'}</span>
    {row.disputed_by.length > 0 && <span className="r2-status disputed">Disputed{row.state === 'stands' ? ' · still stands' : ''}</span>}</span>
}

/** A challenge to material in force. `onSetAside`, where given, runs Set
 *  aside in the host's own place (Fluid's Stage) instead of this dialog. */
export function Challenge({ row, me, onInspect, onEdit, onChanged, onSetAside }: { row: Row; me: Id | null;
  onInspect: () => void; onEdit: () => void; onChanged: () => void;
  onSetAside?: (dispute: DisputeRead, done: () => void) => void }) {
  const got = useApi<{ disputes: DisputeRead[] }>(`/api/governance/disputes?entry=${row.entry}`)
  const capabilities = useApi<{ governance_actions: Record<string, boolean | string | null> }>(`/api/entries/${row.entry}`)
  const [aside, setAside] = useState<DisputeRead | null>(null)
  const open = got.data?.disputes.filter(d => d.open) ?? []
  if (got.data && !open.length) return null
  return <article className="r2-challenge"><span className="r2-tag">Challenge to material in force</span><p className="r2-prose">{row.summary}</p><Pills row={row} />
    {open.map(d => <div key={d.link}><p>{d.by_alias ?? 'Unattributed'}: “{d.reason ?? 'No words recorded'}”</p><div className="r2-actions">{capabilities.data?.governance_actions.edit === true && <button disabled={!me} onClick={onEdit}>Propose new version…</button>}{capabilities.data?.governance_actions.set_aside === true && <button disabled={!me} onClick={() => onSetAside ? onSetAside(d, () => { got.reload(); onChanged() }) : setAside(d)}>Set aside…</button>}<button onClick={onInspect}>Inspect</button><span className="r2-dim">Leave open records nothing.</span></div></div>)}
    {aside && <ActDialog act="set-aside" item={{ entry: row.entry, kind: row.kind, text: row.summary, stands: true, standing: 'stands' }} dispute={aside} me={me} onCancel={() => setAside(null)} onDone={() => { setAside(null); got.reload(); onChanged() }} />}
  </article>
}

export default function R2Workspace({ conversation, conversationName, gov, onGov, me, names = {},
  onChanged, onExit, onLeave, exitLabel, onOpenConversation, onGoToTurn }: WorkspaceProps) {
  const section = gov.section ?? (conversation ? 'instructions' : 'start')
  const here = Boolean(conversation && !gov.whole && section !== 'personas')
  const [create, setCreate] = useState<string | null>(null)
  const [preview, setPreview] = useState(false)
  const [previewPersona, setPreviewPersona] = useState<Id | null>(null)
  const openPreview = (persona: Id | null = null) => { setPreviewPersona(persona); setPreview(true) }
  const [edit, setEdit] = useState<Id | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [landed, setLanded] = useState<string | null>(null)
  const definitions = useApi<{ kinds: KindAuthoring[] }>('/api/governance/authoring')
  // Search the register on the server, before its bounded result cut.
  const corpus = useApi<{ groups: Record<string, Row[]>; omitted: Record<string, number> }>(`/api/governed?limit=500${gov.filters.q ? '&q=' + encodeURIComponent(gov.filters.q) : ''}${gov.filters.kind ? '&kind=' + encodeURIComponent(gov.filters.kind) : ''}`)
  const owed = useApi<{ owed: AskRow[]; omitted: number }>(me ? `/api/owed?participant=${me}` : null)
  const coverage = useAskCoverage(me)
  const convs = useApi<{ conversations: { id: Id; name: string }[] }>('/api/conversations')
  const choices = { ...names, ...Object.fromEntries((convs.data?.conversations ?? []).map(c => [c.id, c.name])) }
  const kinds = definitions.data?.kinds ?? []
  // THE TABS ARE THE BRAIN'S: Start, the three this surface has always had,
  // and every section a Kind declares (`r2Model.tabsOf`).
  const tabs = [...tabsOf(kinds).filter(([s]) => s !== IMPORT_TAB[0]), IMPORT_TAB]
  const rows = useMemo(() => Object.values(corpus.data?.groups ?? {}).flat(), [corpus.data])
  const activeKinds = kinds.filter(k => k.authoring?.section === section)
  const asks = (owed.data?.owed ?? []).filter(a => !here || a.conversation === conversation)
  const scoped = here ? rows.filter(r => inConversation(r, conversation!)) : rows
  const challenged = waitingChallenges(scoped, entry => coverage.known && coverage.named.has(entry))
  const state = gov.filters.state || 'standing'
  // The register searches complete bodies before its cut. Do not search the
  // shortened display summaries again: that would discard valid deep matches.
  const rowFilters = { ...gov.filters, q: '' }
  const filtered = filterRows(rows, kinds, section, { ...rowFilters, state }, here ? conversation : null, section === 'instructions' && !here ? gov.conversationFilter : '')
  const changed = () => { corpus.reload(); definitions.reload(); owed.reload(); onChanged?.() }
  const inspect = (id: Id) => { setEdit(null); onGov({ item: id, participant: null }) }
  const setTab = (tab: string) => { setCreate(null); setPreview(false); onGov({ section: tab, centre: { view: 'lens' }, filters: { q: '', state: 'standing', kind: '', applies: '' }, conversationFilter: undefined }) }
  useEffect(() => { setPreview(false) }, [gov.section, conversation])
  useEffect(() => {
    if (me) void post('/api/governance/arrive', { participant: me, conversation }).catch(() => {})
  }, [me, conversation])
  useEffect(() => {
    const escape = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || document.querySelector('[role="dialog"]')) return
      if (create) { setCreate(null); e.preventDefault() }
      else if (preview) { setPreview(false); e.preventDefault() }
      else if (gov.item) { onGov({ item: null }); e.preventDefault() }
    }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [create, preview, gov.item, onGov])
  const renderRows = (items: Row[]) => items.length ? <div className={'r2-list' + (expanded ? ' expanded' : '')}>{items.map(r => <button className={'r2-row' + (gov.item === r.entry ? ' selected' : '')} key={r.entry} onClick={() => inspect(r.entry)}>
    <span className="r2-row-text"><span className="r2-tag">{r.kind}</span><span className="r2-words">{r.summary}</span>{expanded && r.secondary && <span>{r.secondary}</span>}</span><Pills row={r} />
    <span className="r2-meta">{r.placed_at.map(p => p.name ?? choices[p.conversation] ?? p.conversation).join(', ') || (kinds.find(k => k.kind === r.kind)?.authoring?.door === 'persona' ? 'When selected as a persona' : 'Only when named')} · {r.author_alias ?? 'Unattributed'}{r.at ? ` · ${when(r.at)}` : ''}</span>
  </button>)}</div> : <p className="r2-empty">No material matches. <button onClick={() => onGov({ filters: { q: '', state: 'any', kind: '', applies: '' }, conversationFilter: undefined })}>Clear filters</button></p>
  const fold = (label: string, items: Row[]) => <details className="r2-fold"><summary>{label} <span className="r2-dim">· {items.length}</span></summary>{renderRows(items)}</details>
  const creationKinds = create ? kinds.filter(k => k.authoring?.section === kinds.find(x => x.kind === create)?.authoring?.section) : []
  const title = section === 'start' ? 'Governance' : section === 'instructions' && here ? conversationName ?? 'This conversation' : tabs.find(t => t[0] === section)?.[1] ?? section
  const description = section === 'start' ? 'What is owed to you, and the material that governs work.' : section === 'personas' ? 'Create, change or preview a role for a run.' : section === 'instructions' ? 'What everyone working in a conversation is told.' : section === 'rules' ? 'Record a directive or settled question, and choose where it reaches.' : section === 'import' ? 'Preview and stage incoming Mentis archive files (.zip) before applying them to this Brain.' : activeKinds[0]?.meaning ?? ''
  // A DECLARED SECTION SAYS WHAT IT RECORDS IN ITS KINDS' OWN NAMES.
  const createLabel = section === 'personas' ? '+ Create persona' : section === 'instructions' ? '+ Add instruction' : section === 'rules' ? '+ Record a rule or decision' : `+ Record ${activeKinds.map(k => k.kind).join(' or ')}`
  const added = tabs.filter(([s]) => s !== 'start' && !known(s))
  return <div className="ws-gov r2-workspace">
    <header className="r2-header"><div className="r2-header-top">
      <h1>{title}</h1>
      {(onExit ?? onLeave) && <button className="r2-exit" onClick={onExit ?? onLeave}>‹ {exitLabel ?? 'Back to the work'}</button>}
      </div><p className="r2-description r2-dim">{description}</p>
      <nav className="r2-tabs" aria-label="Governance sections">{tabs.map(([tab, label]) => <button key={tab} aria-pressed={tab === section} className={tab === section ? 'on' : ''} onClick={() => setTab(tab)}>{label}</button>)}</nav>
    </header>
    <div className="r2-layout"><main className="r2-main">
      {landed && <p role="status" className="r2-effect">{landed}</p>}
      {preview ? <PreviewSheet conversation={conversation} conversationName={conversationName} participant={me}
        persona={previewPersona} onClose={() => setPreview(false)} onInspect={inspect} /> : <>
      {section === 'import' && <ImportArchiveTab />}
      {section !== 'start' && section !== 'import' && <>
        {conversation && section !== 'personas' && <div className="r2-lens"><div className="r2-segment"><button aria-pressed={here} onClick={() => onGov({ whole: false })}>Here</button><button aria-pressed={!here} onClick={() => onGov({ whole: true })}>Whole brain</button></div>{here && onOpenConversation && <button className="r2-go" onClick={onOpenConversation}>Open conversation ›</button>}</div>}
        <div className="r2-section-head"><h2>{here ? 'In force here' : title}</h2>{activeKinds.length > 0 && <button className="r2-primary" disabled={!me} onClick={() => setCreate(activeKinds.find(k => k.authoring?.door !== 'entry')?.kind ?? activeKinds[0].kind)}>{createLabel}</button>}</div>
        <div className="r2-filters"><input aria-label="Search governed material" placeholder={section === 'personas' ? 'Search names and behaviour…' : 'Search text…'} value={gov.filters.q} onChange={e => onGov({ filters: { ...gov.filters, q: e.target.value } })} />
          <select aria-label="Status" value={state} onChange={e => onGov({ filters: { ...gov.filters, state: e.target.value } })}>{[['standing', 'In force'], ['proposed', 'Proposed'], ['disputed', 'Disputed'], ['history', 'Ended or deleted'], ['any', 'Any status']].map(([v, s]) => <option key={v} value={v}>Status: {s}</option>)}</select>
          {section === 'instructions' && !here && <select aria-label="Conversation filter" value={gov.conversationFilter ?? ''} onChange={e => onGov({ conversationFilter: e.target.value })}><option value="">Conversation: any</option>{Object.entries(choices).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select>}
          {section !== 'instructions' && section !== 'personas' && <><select aria-label="Kind filter" value={gov.filters.kind} onChange={e => onGov({ filters: { ...gov.filters, kind: e.target.value } })}><option value="">Kind: any</option>{activeKinds.map(k => <option key={k.kind}>{k.kind}</option>)}</select><select aria-label="Reach" value={gov.filters.applies} onChange={e => onGov({ filters: { ...gov.filters, applies: e.target.value } })}><option value="">Reach: any</option><option value="placed">Placed in a conversation</option><option value="when_named">Only when named</option></select></>}
        </div><div className="r2-results"><span>{filtered.length} records</span><div className="r2-segment"><button aria-pressed={!expanded} onClick={() => setExpanded(false)}>Compact</button><button aria-pressed={expanded} onClick={() => setExpanded(true)}>Expanded</button></div></div>
        {corpus.loading && !corpus.data && <p>Reading material…</p>}{corpus.error && <p role="alert">{corpus.error}</p>}{definitions.error && <p role="alert">{definitions.error}</p>}
        {renderRows(filtered)}
        {here && state === 'standing' && <>
          {section === 'instructions' && <section className="r2-block"><h2>Rules placed here</h2>{renderRows(filterRows(rows, kinds, 'rules', { ...rowFilters, kind: '', applies: '', state: 'standing' }, conversation))}</section>}
          {section === 'instructions' && <section className="r2-block"><h2>Depends on who’s working</h2><p className="r2-dim">Personas apply to the run that selects them. Preview a conversation and persona without starting work.</p><button onClick={() => openPreview()}>Preview what an agent receives</button></section>}
          {fold('Only when named', filterRows(rows, kinds, 'rules', { ...rowFilters, kind: '', state: 'standing', applies: 'when_named' }, null))}
          {fold('Proposed here', filterRows(rows, kinds, section, { ...rowFilters, state: 'proposed' }, conversation))}
          {fold('Ended here', filterRows(rows, kinds, section, { ...rowFilters, state: 'history' }, conversation))}
        </>}
        {section === 'personas' && <div className="r2-block"><button onClick={() => openPreview()}>Preview a role</button></div>}
      </>}
      {section === 'start' && <>
        <section className="r2-block"><h2>Waiting on you</h2><p className="r2-dim">Only explicit asks and challenges to material in force.</p>
          {owed.loading && !owed.data && <p>Reading asks…</p>}{owed.error && <p role="alert">{owed.error}</p>}
          {onePerForm(asks).map(ask => <AskCard key={ask.form ?? ask.expectation} ask={ask} showConversation me={me} onInspect={inspect} onChanged={changed} onProposeNewVersion={id => { setEdit(id); onGov({ item: id }) }} onCompare={(left, right) => right ? onGov({ centre: { view: 'compare', left, right } }) : inspect(left)} />)}
          {challenged.map(row => <Challenge key={row.entry} row={row} me={me} onInspect={() => inspect(row.entry)} onEdit={() => { setEdit(row.entry); onGov({ item: row.entry }) }} onChanged={changed} />)}
          {owed.data && corpus.data && !asks.length && !challenged.length && <p className="r2-empty">Nothing here waits on you.</p>}
          {!!owed.data?.omitted && <p>More asks exist than this read returned. Use the app’s asks view to inspect them.</p>}
        </section><section className="r2-block"><h2>What do you want to do?</h2><div className="r2-flows">{[['instructions', 'Tell everyone in a conversation something', 'Write an instruction and place it in its conversation.'], ['personas', 'Create a persona', 'Describe how someone wearing it should behave.'], ['rules', 'Record a rule or decision', 'Choose where it reaches, or leave it for runs that name it.']].map(([tab, label, desc]) => <button key={tab} className="r2-flow" disabled={!kinds.some(k => k.authoring?.section === tab)} onClick={() => { setTab(tab as typeof section); setCreate(kinds.find(k => k.authoring?.section === tab)!.kind) }}><strong>{label} →</strong><span>{desc}</span><small>3 steps</small></button>)}{added.map(([tab, label]) => <button key={tab} className="r2-flow" disabled={!me} onClick={() => { setTab(tab); setCreate(kinds.find(k => k.authoring?.section === tab)!.kind) }}><strong>Record {label.toLowerCase()} →</strong><span>{kinds.find(k => k.authoring?.section === tab)?.meaning}</span><small>3 steps</small></button>)}<button className="r2-flow" onClick={() => openPreview()}><strong>See what an agent will receive →</strong><span>Pick a conversation and a persona; read the guidance it would get now.</span><small>Writes nothing</small></button></div></section>
        {coverage.known && fold('Proposed, nobody asked you', scoped.filter(r => r.state === 'candidate' && !coverage.named.has(r.entry)))}
      </>}
      {!!corpus.data && Object.values(corpus.data.omitted).some(n => n > 0) && <p className="r2-dim">This read is bounded to 500 records per status group. Search or select a Kind to find older material; search runs before the result limit.</p>}
      </>}
    </main>
    {(gov.item || create) && <aside className="r2-panel" aria-label="Governed record"><div className="r2-panel-head"><span className="r2-tag">{create ? 'Create governed material' : 'Record'}</span><button aria-label="Close record panel" onClick={() => { setCreate(null); onGov({ item: null }) }}>×</button></div>
      <div className="r2-panel-body">{create ? <R2Create key={create} kinds={creationKinds} initial={create} conversation={conversation} names={choices} me={me} onCancel={() => setCreate(null)} onDone={id => { setCreate(null); setLanded('Recorded in this Brain.'); changed(); inspect(id) }} /> : <R2Record key={`${gov.item}-${edit === gov.item}`} id={gov.item!} initialEdit={edit === gov.item} conversation={conversation} conversationName={conversationName} kinds={kinds} names={choices} me={me} onInspect={inspect} onPreview={() => openPreview(gov.item)} onChanged={changed} onGoToTurn={onGoToTurn} />}
    </div></aside>}
    </div>
  </div>
}
