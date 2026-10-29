/* GOVERNANCE, AS A FLUID PAGE (owner's decision: Claude's layout with Codex's
 * Record panel and More menu, extended with Contract §6 Epistemic Ladder).
 *
 * THE COLUMN is what is owed: "Waiting on you" -- explicit asks, adoption
 * requests, and challenges to material in force -- and compact "What do you
 * want to do?" cards.
 * STAGE holds the Epistemic Ladder tabs (`Learning`, `For adoption`, `Adopted`)
 * alongside the authoring tabs (`Start`, `Instructions`, `Personas`,
 * `Rules & decisions`, `Disciplines`, `Workflows`). Selecting any row opens the
 * item in the Stage beside the conversation it originated or was proposed from. */

import { useEffect, useMemo, useRef, useState } from 'react'
import { post, read, useApi, when, type DisputeRead, type Id } from '../../api'
import type { GovFilters } from '../../address'
import type { Row } from '../../surfaces/Register'
import ActDialog from '../../surfaces/governance/ActDialogs'
import { AskCard, onePerForm, type ActRequest, type AskRow } from '../../surfaces/governance/Asks'
import { landOn } from '../../needsItems'
import R2Create from '../../surfaces/governance/R2Forms'
import { Challenge, Pills } from '../../surfaces/governance/R2Workspace'
import { useAskCoverage } from '../../surfaces/governance/askCoverage'
import { filterRows, IMPORT_TAB, KNOWN_TABS, waitingChallenges, type KindAuthoring } from '../../surfaces/governance/r2Model'
import { ColumnFrame } from '../conversation/Column'
import { useNav } from '../conversation/hooks'
import AdoptedTab from './AdoptedTab'
import { useGovNav } from './context'
import FluidPreviewSheet from './FluidPreviewSheet'
import ForAdoptionTab from './ForAdoptionTab'
import ImportArchiveTab from './ImportArchiveTab'
import GovItem from './GovItem'
import {
  govTabsOf,
  normalizeGovSection,
  type LadderAdoptionResponse,
  askedByOf,
} from './ladderTypes'
import LearningTab from './LearningTab'
import { hintOfRow } from './model'
import './governance.css'

const known = (section: string) =>
  KNOWN_TABS.some(([s]) => s === section) ||
  section === IMPORT_TAB[0] ||
  section === 'learning' ||
  section === 'adoption' ||
  section === 'adopted'
const NO_FILTERS: GovFilters = { q: '', state: 'standing', kind: '', applies: '' }
type CorpusPage = { groups: Record<string, Row[]>; omitted: Record<string, number>; next_cursor?: string | null }

/* COMPARE was a Classic investigation, opened there in its own tab. Fluid is
   the only interface and has no Compare yet, so an ask offers none
   (`onCompare` left out). */

export default function GovPage({ section: rawSection, onSection, focus, onFocus, card, onCard, onOpenPost }: {
  section: string
  onSection: (section: string) => void
  /** an item the record names no conversation for, open here on Stage */
  focus: Id | null
  onFocus: (entry: Id | null) => void
  /** the adoption card For adoption brings into view (the shell's, so an
   *  item's "Open adoption card" can name it); kept here where not given */
  card?: Id | null
  onCard?: (entry: Id | null) => void
  /** open a post by its address: where a form or an input is answered */
  onOpenPost?: (conversation: Id, post: Id) => void
}) {
  const section = normalizeGovSection(rawSection)
  const g = useGovNav()
  const me = g.me
  const s = useNav()
  const definitions = useApi<{ kinds: KindAuthoring[] }>('/api/governance/authoring')
  const [filters, setFilters] = useState<GovFilters>(NO_FILTERS)
  const [convFilter, setConvFilter] = useState('')
  const corpusPath = `/api/governed?limit=80&cursor=start${filters.q ? '&q=' + encodeURIComponent(filters.q) : ''}${filters.kind ? '&kind=' + encodeURIComponent(filters.kind) : ''}`
  const firstCorpus = useApi<CorpusPage>(corpusPath)
  const [corpusData, setCorpusData] = useState<CorpusPage | null>(null)
  const [corpusNext, setCorpusNext] = useState<string | null>(null)
  const loadingCorpusPage = useRef(false)
  useEffect(() => {
    if (!firstCorpus.data) return
    setCorpusData(firstCorpus.data)
    setCorpusNext(firstCorpus.data.next_cursor ?? null)
  }, [firstCorpus.data, corpusPath])
  const corpus = { ...firstCorpus, data: corpusData, reload: firstCorpus.reload }
  const loadMoreCorpus = () => {
    if (!corpusNext || loadingCorpusPage.current) return
    loadingCorpusPage.current = true
    const path = corpusPath.replace('cursor=start', 'cursor=' + encodeURIComponent(corpusNext))
    void read<CorpusPage>(path).then((page) => {
      setCorpusData((was) => {
        if (!was) return page
        const groups = { ...was.groups }
        for (const [group, rows] of Object.entries(page.groups)) groups[group] = [...(groups[group] ?? []), ...rows]
        return { ...page, groups }
      })
      setCorpusNext(page.next_cursor ?? null)
    }).catch(() => {}).finally(() => { loadingCorpusPage.current = false })
  }
  const owed = useApi<{ owed: AskRow[]; omitted: number }>(me ? `/api/owed?participant=${me}` : null)
  const adoptionRead = useApi<LadderAdoptionResponse>('/api/ladder/adoption')
  const coverage = useAskCoverage(me)
  const convs = useApi<{ conversations: { id: Id; name: string }[] }>('/api/conversations')
  const choices = useMemo(() => Object.fromEntries((convs.data?.conversations ?? []).map((c) => [c.id, c.name])), [convs.data])
  const [create, setCreate] = useState<string | null>(null)
  const [preview, setPreview] = useState(false)
  const [act, setAct] = useState<(ActRequest & { from: string; key: number }) | null>(null)
  const acts = useRef(0)
  const [landed, setLanded] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [dismissedAdoptionIds, setDismissedAdoptionIds] = useState<Set<Id>>(() => new Set())
  const [localCard, setLocalCard] = useState<Id | null>(null)
  const focusAdoptionEntry = onCard ? card ?? null : localCard
  const setFocusAdoptionEntry = onCard ?? setLocalCard
  const stage = useRef<HTMLDivElement | null>(null)
  const stageScroll = useRef<HTMLDivElement | null>(null)
  const columnScroll = useRef<HTMLDivElement | null>(null)

  const kinds = definitions.data?.kinds ?? []
  const tabs = useMemo(() => govTabsOf(kinds), [kinds])
  const rows = useMemo(() => Object.values(corpus.data?.groups ?? {}).flat(), [corpus.data])
  const activeKinds = kinds.filter((k) => k.authoring?.section === section)
  const adoptionRequests = useMemo(
    () => (adoptionRead.data?.requests ?? []).filter((r) => !dismissedAdoptionIds.has(r.entry)),
    [adoptionRead.data, dismissedAdoptionIds],
  )
  /* AN ADOPTION REQUEST IS SHOWN AS ONE: "asks you to adopt", opening its card
   * (contract §6). Its ask is the same expectation the owed read lists, so that
   * generic ask card is left out rather than shown twice in another shape. */
  const adoptionAskIds = useMemo(
    () => new Set((adoptionRead.data?.requests ?? []).map((r) => r.ask).filter(Boolean) as Id[]),
    [adoptionRead.data],
  )
  const asks = (owed.data?.owed ?? []).filter((a) => !adoptionAskIds.has(a.expectation))
  const standaloneAdoptionRequests = adoptionRequests
  const challenged = waitingChallenges(rows, (entry) => coverage.known && coverage.named.has(entry))
  const state = filters.state || 'standing'
  /* A SECTION OF ONE KIND READS THAT KIND. The page above is every governed
   * Kind together, cut at 80, so a section filtered out of it here -- Personas
   * on a Brain with hundreds of rules and lessons -- could open nearly empty
   * with its own material behind Load more. The Waiting column keeps reading
   * the mixed page: its challenges come from every Kind. */
  const sectionKind = activeKinds.length === 1 && !filters.kind ? activeKinds[0].kind : null
  const sectionRead = useApi<CorpusPage>(sectionKind
    ? `/api/governed?limit=200&cursor=start&kind=${encodeURIComponent(sectionKind)}${filters.q ? '&q=' + encodeURIComponent(filters.q) : ''}`
    : null)
  const sectionRows = useMemo(
    () => (sectionKind && sectionRead.data ? Object.values(sectionRead.data.groups ?? {}).flat() : null),
    [sectionKind, sectionRead.data])
  const filtered = filterRows(sectionRows ?? rows, kinds, section, { ...filters, q: '', state }, null, section === 'instructions' ? convFilter : '')
  const changed = () => {
    corpus.reload()
    sectionRead.reload()
    definitions.reload()
    owed.reload()
    adoptionRead.reload()
  }

  /* THE LAST LOOK IS AN ARRIVAL, as Classic records it. */
  useEffect(() => {
    if (me) void post('/api/governance/arrive', { participant: me, conversation: null }).catch(() => {})
  }, [me])

  /* A section change starts that section clean, as Classic's tabs do. */
  const setTab = (tab: string) => {
    setCreate(null)
    setPreview(false)
    setAct(null)
    setFilters(NO_FILTERS)
    setConvFilter('')
    setFocusAdoptionEntry(null)
    onFocus(null)
    onSection(normalizeGovSection(tab))
  }

  /* What is opened on Stage is brought into view: below the column on a phone. */
  const shown = act ? 'act' : create ? 'create' : preview ? 'preview' : focus ? 'focus' : null
  useEffect(() => {
    if (shown) stage.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
  }, [shown])

  /* EACH ACT A FRESH FORM: another ask's act never inherits this one's words. */
  const runAct = (req: ActRequest, from: string) => {
    setCreate(null)
    setPreview(false)
    setLanded(null)
    setAct({ ...req, from, key: ++acts.current })
  }
  const startCreate = (tab: string, kind?: string) => {
    setTab(tab)
    setCreate(
      kind ??
      kinds.find((k) => k.authoring?.section === tab && k.authoring?.door !== 'entry')?.kind ??
      kinds.find((k) => k.authoring?.section === tab)?.kind ??
      null,
    )
  }

  const title = section === 'start' ? 'Governance' : tabs.find((t) => t[0] === section)?.[1] ?? section
  const description =
    section === 'start' ? 'What is owed to you, and the material that governs work.'
      : section === 'learning' ? 'What agents recorded while working. It may reach later work as evidence. Nothing here needs you unless adoption was requested.'
        : section === 'adoption' ? 'Explicit requests for your decision. Recording something never puts it here; an agent or you has to ask.'
          : section === 'adopted' ? 'Working positions and governing material adopted by the owner and currently in force.'
            : section === 'personas' ? 'Create, change or preview a role for a run.'
              : section === 'instructions' ? 'What everyone working in a conversation is told.'
                : section === 'rules' ? 'Record a directive or settled question, and choose where it reaches.'
                  : section === 'import' ? 'Preview and stage incoming Mentis archive files (.zip) before applying them to this Brain.' : activeKinds[0]?.meaning ?? ''

  const createLabel = section === 'personas' ? '+ Create persona'
    : section === 'instructions' ? '+ Add instruction'
      : section === 'rules' ? '+ Record a rule or decision'
        : `+ Record ${activeKinds.map((k) => k.kind).join(' or ')}`
  const added = tabs.filter(([t]) => t !== 'start' && !known(t) && t !== 'disciplines' && t !== 'workflows')
  const creationKinds = create ? kinds.filter((k) => k.authoring?.section === kinds.find((x) => x.kind === create)?.authoring?.section) : []

  const totalWaitingCount = asks.length + standaloneAdoptionRequests.length + challenged.length
  const isLadderTab = section === 'learning' || section === 'adoption' || section === 'adopted'

  const renderRows = (items: Row[]) => items.length ? (
    <ul className={'fg-rows' + (expanded ? ' expanded' : '')}>
      {items.map((r) => {
        const hint = hintOfRow(r)
        return (
          <li key={r.entry}>
            <button className="fg-row" data-entry={r.entry} onClick={() => g.openItem(r.entry, hint)}>
              <span className="fg-row-top"><span className="r2-tag">{r.kind}</span><Pills row={r} /></span>
              <span className="fg-row-words">{r.summary}</span>
              {expanded && r.secondary && <span className="fg-row-words fg-faint">{r.secondary}</span>}
              <span className="fg-row-meta">
                {r.placed_at.map((p) => p.name ?? choices[p.conversation] ?? p.conversation).join(', ')
                  || (kinds.find((k) => k.kind === r.kind)?.authoring?.door === 'persona' ? 'When selected as a persona' : 'Only when named')}
                {' · '}{r.author_alias ?? 'Unattributed'}{r.at ? ` · ${when(r.at)}` : ''}
              </span>
              <span className="fg-row-opens">
                {hint.source ? `Opens beside ${hint.source.conversationName ?? choices[hint.source.conversation] ?? 'its conversation'}, ${hint.source.why === 'proposed' ? 'the conversation it was proposed in' : 'where it is placed'} →`
                  : 'Opens here: the record names no conversation for it →'}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  ) : (
    <p className="fg-empty">No material matches.{' '}
      <button className="fg-link" onClick={() => { setFilters({ q: '', state: 'any', kind: '', applies: '' }); setConvFilter('') }}>Clear filters</button></p>
  )

  return (
    <>
      <ColumnFrame title="Governance" width={s.width === 'rail' ? 'narrow' : s.width} scroller={columnScroll} label="governance">
        <div className="fg-column">
          <section className="fg-owed" aria-label="Waiting on you">
            <h2 className="fg-h">
              Waiting on you{' '}
              <span className="fg-count">
                {(owed.data || adoptionRead.data) ? totalWaitingCount : ''}
              </span>
            </h2>
            <p className="fg-faint">Only explicit asks, adoption requests and challenges to material in force.</p>
            {!me && <p className="fg-faint">Mentis could not say who you are, so nothing can be owed to you here.</p>}
            {owed.loading && !owed.data && !adoptionRead.data && <p className="fg-faint">Reading asks…</p>}
            {owed.error && (
              <p className="fg-field-error" role="alert">
                Couldn’t read what is owed to you: {owed.error}{' '}
                <button className="fg-link" onClick={owed.reload}>Retry</button>
              </p>
            )}
            {standaloneAdoptionRequests.map((req) => {
              const convName = req.conversation_name
                ?? req.asked_by?.conversation_name
                ?? (req.conversation ? choices[req.conversation] : null)
                ?? req.conversation
              const isRev = Boolean(req.wording.current || (req.replaces && req.replaces.length > 0))
              const asker = askedByOf(req.asked_by)
              return (
                <article key={req.request || req.entry} className="fg-adopt-ask" data-entry={req.entry}>
                  <div className="fg-adopt-ask-who">
                    <b>{asker.who}</b>
                    {asker.migratedBy && <span className="fg-faint"> (migrated by {asker.migratedBy})</span>} asks you to adopt
                    {convName ? ` · ${convName}` : ''}
                    {req.asked_at != null ? ` · ${when(req.asked_at)}` : ''}
                  </div>
                  <div className="fg-adopt-ask-body">
                    {isRev ? `Revise ${req.kind}` : `${req.kind[0].toUpperCase() + req.kind.slice(1)}`}: {req.wording.proposed}
                  </div>
                  <div className="fg-adopt-ask-btns">
                    <button
                      type="button"
                      className="fg-btn-secondary"
                      onClick={() => {
                        /* the tab, not an item still open on Stage over it */
                        setTab('adoption')
                        onFocus(null)
                        setFocusAdoptionEntry(req.entry)
                      }}
                    >
                      Open adoption card →
                    </button>
                    <button
                      type="button"
                      className="fg-btn-secondary"
                      onClick={() => {
                        setDismissedAdoptionIds((prev) => {
                          const next = new Set(prev)
                          next.add(req.entry)
                          return next
                        })
                      }}
                    >
                      Not now
                    </button>
                  </div>
                </article>
              )
            })}
            {onePerForm(asks).map((ask) => (
              <AskCard key={ask.form ?? ask.expectation} ask={ask} showConversation me={me}
                onOpenItem={onOpenPost ? (it) => { if (it.post && it.conversation) { onOpenPost(it.conversation, it.post); void landOn(it) } } : undefined}
                onInspect={(id) => g.openItem(id)} onChanged={changed}
                onProposeNewVersion={(id) => g.openItem(id, null, { edit: true })}
                onAct={(req) => runAct(req, `${ask.asked_by_alias ?? 'Somebody'} asked${ask.conversation_name ? ` in ${ask.conversation_name}` : ''}`)} />
            ))}
            {challenged.map((row) => (
              <Challenge key={row.entry} row={row} me={me} onChanged={changed}
                onInspect={() => g.openItem(row.entry, hintOfRow(row))}
                onEdit={() => g.openItem(row.entry, hintOfRow(row), { edit: true })}
                onSetAside={(d: DisputeRead, done) => runAct({
                  act: 'set-aside',
                  item: { entry: row.entry, kind: row.kind, text: row.summary, stands: true, standing: 'stands' },
                  dispute: d,
                  onDone: () => done(),
                }, 'A challenge to material in force')} />
            ))}
            {(owed.data || adoptionRead.data) && corpus.data && totalWaitingCount === 0 && (
              <p className="fg-empty">Nothing here waits on you.</p>
            )}
            {!!owed.data?.omitted && <p className="fg-faint">More asks exist than this read returned.</p>}
          </section>
          <section className="fg-flows-wrap" aria-label="What do you want to do?">
            <h2 className="fg-h">What do you want to do?</h2>
            <div className="fg-flows">
              {([['instructions', 'Tell everyone in a conversation something'], ['personas', 'Create a persona'], ['rules', 'Record a rule or decision']] as const).map(([tab, label]) => (
                <button key={tab} className="fg-flow" disabled={!me || !kinds.some((k) => k.authoring?.section === tab)}
                  onClick={() => startCreate(tab)}><strong>{label} →</strong><small>3 steps</small></button>
              ))}
              {added.map(([tab, label]) => (
                <button key={tab} className="fg-flow" disabled={!me} onClick={() => startCreate(tab)}>
                  <strong>Record {label.toLowerCase()} →</strong><small>3 steps</small></button>
              ))}
              <button className="fg-flow" onClick={() => setTab('import')}>
                <strong>Import archive →</strong><small>Upload, preview & stage</small></button>
              <button className="fg-flow" onClick={() => { setCreate(null); setAct(null); onFocus(null); setPreview(true) }}>
                <strong>See what an agent will receive →</strong><small>Writes nothing</small></button>
            </div>
            <p className="fg-faint fg-hint">Leave open records nothing: it stays owed. Adopt, Decline, Answer, Establish, Supersede and Set aside each record a response and close the ask.</p>
          </section>
        </div>
      </ColumnFrame>

      <section className="fx-panel fg-stage" aria-label="governance stage">
        <div className="fg-stage-scroll" ref={stageScroll} onScroll={() => {
          const el = stageScroll.current
          if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 240) loadMoreCorpus()
        }}>
          <p className="fg-crumb fg-faint">Stage · Governance</p>
          <header className="fg-head">
            <h1>
              {title}
              {isLadderTab && <span className="fg-new-tag">NEW</span>}
            </h1>
            <p className="fg-faint">{description}</p>
            <nav className="fg-tabs" aria-label="Governance sections">
              {tabs.map(([tab, label]) => {
                const isNew = tab === 'learning' || tab === 'adoption' || tab === 'adopted'
                return (
                  <button
                    key={tab}
                    aria-pressed={tab === section}
                    className={(tab === section ? 'on' : '') + (isNew ? ' fg-tab-new' : '')}
                    onClick={() => setTab(tab)}
                  >
                    {label}
                    {tab === 'adoption' && adoptionRequests.length > 0 && (
                      <sup className="fg-tab-sup">{adoptionRequests.length}</sup>
                    )}
                  </button>
                )
              })}
            </nav>
          </header>
          <div ref={stage} className="fg-stage-top">
            {landed && <p role="status" className="r2-effect">{landed}</p>}
            {act && (
              <div className="fg-act-panel">
                <p className="fg-faint fg-act-from">{act.from}</p>
                <ActDialog key={act.key} inline act={act.act} item={act.item} ends={act.ends} partner={act.partner}
                  dispute={act.dispute} ask={act.ask} me={me}
                  onCancel={() => setAct(null)}
                  onDone={(o) => { act.onDone(o); setAct(null); setLanded(o.said); changed() }} />
              </div>
            )}
            {create && (
              <div className="fg-create" role="group" aria-label="Create governed material">
                <R2Create key={create} kinds={creationKinds} initial={create} conversation={null} names={choices} me={me}
                  onCancel={() => setCreate(null)}
                  onDone={(id) => { setCreate(null); setLanded('Recorded in this Brain.'); changed(); g.openItem(id) }} />
              </div>
            )}
            {preview && <FluidPreviewSheet conversation={null} participant={me} onClose={() => setPreview(false)} onInspect={(id) => g.openItem(id)} />}
            {/* hidden, not unmounted, while an act, the builder or the preview is up:
                a form half-written in the item survives it */}
            {focus && <div hidden={!!(act || create || preview)}><GovItem key={`${focus}:${g.editNonce}`} entry={focus} source={null} onBack={() => onFocus(null)} /></div>}
          </div>

          {!focus && section === 'learning' && (
            <LearningTab
              conversations={choices}
              expanded={expanded}
              onExpanded={setExpanded}
            />
          )}

          {!focus && section === 'adoption' && (
            <ForAdoptionTab
              conversations={choices}
              focusEntry={focusAdoptionEntry}
              onChanged={changed}
              onDismissAsk={(entry) => {
                setDismissedAdoptionIds((prev) => {
                  const next = new Set(prev)
                  next.add(entry)
                  return next
                })
              }}
            />
          )}

          {!focus && section === 'adopted' && (
            <AdoptedTab onSelectTab={setTab} />
          )}

          {!focus && section === 'import' && (
            <ImportArchiveTab />
          )}

          {!focus && section !== 'start' && !isLadderTab && section !== 'import' && (
            <>
              <div className="fg-section-head">
                <h2 className="fg-h">{title}</h2>
                {activeKinds.length > 0 && <button className="fg-primary" disabled={!me}
                  onClick={() => startCreate(section, activeKinds.find((k) => k.authoring?.door !== 'entry')?.kind ?? activeKinds[0].kind)}>{createLabel}</button>}
              </div>
              <div className="fg-filters">
                <input aria-label="Search governed material" placeholder={section === 'personas' ? 'Search names and behaviour…' : 'Search text…'}
                  value={filters.q} onChange={(e) => setFilters({ ...filters, q: e.target.value })} />
                <select aria-label="Status" value={state} onChange={(e) => setFilters({ ...filters, state: e.target.value })}>
                  {[['standing', 'In force'], ['proposed', 'Proposed for adoption'], ['recorded', 'Recorded, not proposed'], ['disputed', 'Disputed'], ['history', 'Ended or deleted'], ['any', 'Any status']].map(([v, w]) => <option key={v} value={v}>Status: {w}</option>)}
                </select>
                {section === 'instructions' && (
                  <select aria-label="Conversation filter" value={convFilter} onChange={(e) => setConvFilter(e.target.value)}>
                    <option value="">Conversation: any</option>
                    {Object.entries(choices).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
                  </select>
                )}
                {section !== 'instructions' && section !== 'personas' && (
                  <>
                    <select aria-label="Kind filter" value={filters.kind} onChange={(e) => setFilters({ ...filters, kind: e.target.value })}>
                      <option value="">Kind: any</option>{activeKinds.map((k) => <option key={k.kind}>{k.kind}</option>)}
                    </select>
                    <select aria-label="Reach" value={filters.applies} onChange={(e) => setFilters({ ...filters, applies: e.target.value })}>
                      <option value="">Reach: any</option><option value="placed">Placed in a conversation</option><option value="when_named">Only when named</option>
                    </select>
                  </>
                )}
                <span className="fg-segment" role="group" aria-label="row size">
                  <button aria-pressed={!expanded} onClick={() => setExpanded(false)}>Compact</button>
                  <button aria-pressed={expanded} onClick={() => setExpanded(true)}>Expanded</button>
                </span>
              </div>
              <p className="fg-faint fg-results">{filtered.length} records</p>
              {corpus.loading && !corpus.data && <p className="fg-faint">Reading material…</p>}
              {corpus.error && <p className="fg-field-error" role="alert">{corpus.error} <button className="fg-link" onClick={corpus.reload}>Retry</button></p>}
              {definitions.error && <p className="fg-field-error" role="alert">{definitions.error}</p>}
              {corpus.data && renderRows(filtered)}
              {corpusNext && <p className="fg-faint"><button className="fg-link" onClick={loadMoreCorpus}>Load more</button></p>}
              {section === 'personas' && <p><button className="fg-link" onClick={() => setPreview(true)}>Preview a role</button></p>}
            </>
          )}
          {!focus && section === 'start' && (
            <>
              <p className="fg-faint">What is owed to you, and what you can start, are in the column beside this.</p>
              {coverage.known && (
                <section aria-label="Proposed, nobody asked you">
                  <h2 className="fg-h">Proposed, nobody asked you</h2>
                  {renderRows(rows.filter((r) => r.state === 'candidate' && !coverage.named.has(r.entry)))}
                </section>
              )}
            </>
          )}
          {!isLadderTab && section !== 'import' && !!corpus.data && corpusNext && (
            <p className="fg-faint">More records load as this list scrolls.</p>
          )}
        </div>
      </section>
    </>
  )
}
