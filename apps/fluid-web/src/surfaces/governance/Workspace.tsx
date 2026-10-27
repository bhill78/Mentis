import { useCallback, useEffect, useMemo, useRef } from 'react'
import {
  post,
  useApi,
  type ContextPayload,
  type Id,
} from '../../api'
import { GOV_HOME, type GovState, type GovView, type Lens, type TraceSubject } from '../../address'
import EntryInspect from '../EntryInspect'
import { placedHere } from './r2Model'
import LensStanding from './LensStanding'
import WorkspaceParticipant from './WorkspaceParticipant'
import InUseLens from './InUseLens'
import WhereMeetsWho from './WhereMeetsWho'
import ExecutionSheet from './ExecutionSheet'
import Compare, { type CompareAsk } from './Compare'
import PreviewSheet from './PreviewSheet'
import HistoryAnswer, { HistoryMenu, QUESTIONS, type Question } from './HistoryQuestions'
import { answerAsk, answeredSaid } from './ActDialogs'
import { FormHere } from './Asks'
import { useAskAbout, type DrivingAsk } from './askCoverage'
import { COMPARE_EVENT, INSPECT_EVENT } from './InSituGovernance'
import './Workspace.css'
import R2Workspace from './R2Workspace'

/* ------------------------------------------------------------------------ *
 * THE GOVERNANCE WORKSPACE.
 *
 * ONE CORPUS AT TWO LENSES, NOT TWO APPLICATIONS. Conversation Governance and
 * Brain Governance are the same governed material read through a narrower or
 * a wider lens. Which is why the scope lives OUTSIDE this component, in the
 * address, and why changing it carries the lens, the facets and the open
 * folds across unchanged: a Conversation is a lens, and you do not lose your
 * place by looking through a different one.
 *
 * STANDING / IN USE / HISTORY, and they are not three tabs of equal weight.
 * Standing and In use are two questions about the corpus in front of you, so
 * they are lenses with their own attention counts. HISTORY IS A QUESTION
 * SOMEBODY ASKS. It is never a mode the page is in and never a column beside
 * the work: it opens on request, it is marked as history while it is open,
 * and the way out names where it was asked from.
 *
 * AN INVESTIGATION IS A PLACE YOU WENT TO. Where meets Who, an execution
 * sheet, a comparison, a preview and each historical answer each replace the
 * centre and each push a browser history entry, so Back — the app's, the
 * device's, and Escape — walks out of them in the order they were entered.
 * The breadcrumb names the origin BY ITS OWN NAME rather than saying "Back".
 *
 * ESCAPE HAS ONE FIXED ORDER and it is the order things are stacked in:
 * dialog, then popover, then inspector, then the history menu, then the
 * current investigation. The first two belong to packages that own their own
 * dismissal and handle it first; this one takes what is left, and looks for
 * them in the document rather than being told about them, because a shell
 * that tracked another surface's open state would eventually be wrong.
 * ------------------------------------------------------------------------ */

const LENSES: { lens: Lens; label: string; title: string }[] = [
  {
    lens: 'standing',
    label: 'Standing',
    title:
      'What the record says about the material: standing, authority, disputes, proposals, asks',
  },
  {
    lens: 'use',
    label: 'In use',
    title: 'How the same material acts on work now, computed from current standing',
  },
]

/** What a view is called when something else has to name where you came from.
 *  Every one of these is the surface's own name — never "Back", never "the
 *  previous page". */
function labelOf(g: GovState): string {
  const c = g.centre
  if (c.view === 'lens') return g.lens === 'standing' ? 'Standing' : 'In use'
  if (c.view === 'history')
    return QUESTIONS.find((q) => q.q === c.question)?.title ?? 'a historical question'
  if (c.view === 'trace') return 'Where meets Who'
  if (c.view === 'execution') return 'the execution record'
  if (c.view === 'compare') return 'Compare'
  return 'the preview'
}

/** Is this centre an investigation — something entered from somewhere, which
 *  therefore has to say how to get back out of it? */
const isInvestigation = (c: GovView) => c.view !== 'lens'

/** The driving ask, as Compare speaks about one. The alias is the record's;
 *  where the record does not name the asker, that is said rather than left
 *  blank or filled in from anything else. */
const askOf = (a: DrivingAsk): CompareAsk => ({
  by_alias: a.asked_by_alias ?? 'somebody the record does not name',
  at: a.at,
  conversation_name: a.conversation_name,
  question: a.question,
})

export interface WorkspaceProps {
  /** the Conversation this workspace is read through, or null for the Brain */
  conversation: Id | null
  conversationName?: string | null
  gov: GovState
  /** move to another governance state. A patch, because most movements change
   *  one thing and must leave the rest of the lens alone. */
  onGov: (patch: Partial<GovState>) => void
  /** leave Governance for the work itself AT WHICHEVER SCOPE THIS IS. There
   *  are no Turns at Brain scope, so the door cannot be called Turns there —
   *  but a door there must exist: `#/brain/gov/…` is a linkable state (I-11),
   *  and without one a reader who arrived on that link could leave only
   *  through the browser's own Back. */
  onLeave?: () => void
  /** what leaving lands on, by its own name. The approved way out never says
   *  just "Back" (I-9). */
  leaveLabel?: string
  /** THE WAY OUT, SAID PROMINENTLY (polish1/topics B, owner's answer #136):
   *  "Back to <Conversation>", or "Leave Brain view" at Brain scope. Its
   *  own words, because the small "‹ Turns" tab was the complaint. */
  exitLabel?: string
  exitTitle?: string
  /** leave by the prominent exit; `onLeave` when absent */
  onExit?: () => void
  /** CLEAR THE CONVERSATION FILTER: the same lens over the whole Brain */
  onClearScope?: () => void
  /** open the Conversation this lens is narrowed to, leaving Governance */
  onOpenConversation?: () => void
  me: Id | null
  names?: Record<string, string>
  onChanged?: () => void
  /** take the reader to a Turn and flash it — the provenance link */
  onGoToTurn?: (turn: Id) => void
}

export default function Workspace(props: WorkspaceProps) {
  const onGov = props.onGov
  /* "INSPECT IN GOVERNANCE", ANSWERED. A Turn's in-situ card announces where
     it wants to go and does not know whether anybody is listening; this is
     the listener, and calling `preventDefault` is how it says it took it. The
     landing is the approved one: Standing, filters cleared, the item in the
     inspector, and the Proposed fold opened by name. */
  useEffect(() => {
    const onAsk = (e: Event) => {
      const entry = (e as CustomEvent<{ entry: Id }>).detail?.entry
      if (!entry) return
      e.preventDefault()
      onGov({
        lens: 'standing',
        centre: { view: 'lens' },
        item: entry,
        participant: null,
        filters: { q: '', state: '', kind: '', applies: '' },
        open: ['proposed'],
      })
    }
    /* AND THE SAME ARRANGEMENT FOR TWO ITEMS. A card in a Turn can show two
       texts side by side; it cannot show the provenance, the delivery
       evidence and the consequence block, which is what Compare is for. */
    const onPair = (e: Event) => {
      const d = (e as CustomEvent<{ left: Id; right: Id }>).detail
      if (!d?.left || !d?.right) return
      e.preventDefault()
      onGov({
        lens: 'standing',
        centre: { view: 'compare', left: d.left, right: d.right },
        item: null,
        participant: null,
        filters: { q: '', state: '', kind: '', applies: '' },
        open: [],
      })
    }
    window.addEventListener(INSPECT_EVENT, onAsk)
    window.addEventListener(COMPARE_EVENT, onPair)
    return () => {
      window.removeEventListener(INSPECT_EVENT, onAsk)
      window.removeEventListener(COMPARE_EVENT, onPair)
    }
  }, [onGov])

  return props.gov.centre.view === 'lens' ? <R2Workspace {...props} /> : <LegacyWorkspace {...props} />
}

function LegacyWorkspace({
  conversation,
  conversationName,
  gov,
  onGov,
  onLeave,
  leaveLabel = 'the work',
  exitLabel,
  exitTitle,
  onExit,
  onClearScope,
  onOpenConversation,
  me,
  names = {},
  onChanged,
  onGoToTurn,
}: WorkspaceProps) {
  const here = conversationName ?? conversation
  const centre = gov.centre

  /* THE LAST LOOK IS AN ARRIVAL, and this is the arrival. Recorded once per
     mount, per person, per scope: there is no mark-as-read anywhere, and
     nothing can be set to a time somebody did not actually arrive at. Without
     a person there is no last look, so nothing is written. */
  const scope = conversation ?? null
  useEffect(() => {
    if (!me) return
    void post('/api/governance/arrive', { participant: me, conversation: scope }).catch(() => {
      /* An arrival that could not be recorded is not worth interrupting
         anybody over: the catch-up simply has one fewer bound, and says so. */
    })
  }, [me, scope])

  /* THE ATTENTION COUNT ON EACH TAB, and they count different things. Standing
     counts conditions that are not overlaps — open challenges on material in
     scope. In use counts overlaps, which are the one condition that is about
     how material ACTS rather than about what the record says. Neither is a
     count of what is owed: only an ask is owed, and that count lives in the
     app bar. */
  const corpus = useApi<{
    groups: Record<string, { entry: Id; state: string | null; disputed_by: Id[]; placed_at: { conversation: Id; whole_brain?: boolean }[]; proposed_by: { conversation: Id | null }[] }[]>
  }>('/api/governed?limit=500')
  const disputes = useMemo(() => {
    const g = corpus.data?.groups
    if (!g) return 0
    const all = [...(g.standing ?? []), ...(g.proposed ?? []), ...(g.history ?? [])]
    return all.filter(
      (r) =>
        r.disputed_by.length > 0 &&
        (!conversation ||
          r.placed_at.some((p) => placedHere(p, conversation)) ||
          r.proposed_by.some((p) => p.conversation === conversation)),
    ).length
  }, [corpus.data, conversation])
  const ctx = useApi<ContextPayload>(
    '/api/context' + (conversation ? '?conversation=' + encodeURIComponent(conversation) : ''),
  )
  const overlaps = ctx.data?.conflicts?.length ?? 0

  /* WHERE YOU CAME FROM, remembered as its own name. An investigation is
     always entered from something; a cold deep link was entered from nothing,
     and then the honest answer is the lens it belongs to. */
  const origin = useRef<string>(labelOf({ ...GOV_HOME, lens: gov.lens }))
  const wasLens = useRef(true)
  useEffect(() => {
    if (!isInvestigation(centre)) {
      origin.current = gov.lens === 'standing' ? 'Standing' : 'In use'
      wasLens.current = true
    } else if (wasLens.current) {
      wasLens.current = false
    }
  }, [centre, gov.lens])
  const backLabel = origin.current

  const toLens = useCallback(() => onGov({ centre: { view: 'lens' } }), [onGov])
  const inspect = useCallback(
    (entry: Id) => onGov({ item: entry, participant: null }),
    [onGov],
  )
  const openExecution = useCallback(
    (execution: Id) => onGov({ centre: { view: 'execution', execution } }),
    [onGov],
  )
  const trace = useCallback(
    (subject: TraceSubject | null) => onGov({ centre: { view: 'trace', subject } }),
    [onGov],
  )
  const compare = useCallback(
    (left: Id, right: Id) => onGov({ centre: { view: 'compare', left, right } }),
    [onGov],
  )

  /* WHO IS WAITING ON THE COMPARISON THAT IS OPEN, IF ANYBODY. Compare is
     reached from an ask, from an overlap condition, from a row, from the
     inspector and from a Turn, and only the first of those leaves somebody
     owed an answer. The surface says which it is out loud, so the shell has
     to actually go and find out rather than leaving it to be inferred from a
     missing card — which is what it was doing: no `ask` was ever passed, so
     an open ask about these two read as "nobody is asking", and the three
     controls the consequence block described did not exist. */
  const pair = useMemo(
    () => (centre.view === 'compare' ? [centre.left, centre.right] : []),
    [centre],
  )
  const driving = useAskAbout(me, pair)

  /* ESCAPE, IN THE ONE ORDER. A dialog and the asks popover dismiss
     themselves and are looked for rather than tracked; the history menu is
     asked to close by the same means. What is left is the inspector, and then
     the investigation. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (document.querySelector('.act-dialog')) return
      if (document.querySelector('.asks-pop')) return
      if (gov.item || gov.participant) {
        onGov({ item: null, participant: null })
        return
      }
      const menu = document.querySelector<HTMLElement>('.hq-menu-btn[aria-expanded="true"]')
      if (menu) {
        menu.click()
        return
      }
      if (isInvestigation(gov.centre)) {
        toLens()
        return
      }
      /* AND THEN, WITH NOTHING LEFT OPEN, ESCAPE LEAVES (polish1/topics B).
         Not while somebody is typing -- Escape in a field belongs to the
         field -- and not while any popover or sheet is up: every one of
         them draws a scrim, so its presence is the question. */
      if (e.defaultPrevented || document.querySelector('.scrim, [role="dialog"]')) return
      const el = e.target as HTMLElement | null
      if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return
      const out = onExit ?? onLeave
      if (out) {
        e.preventDefault()
        out()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [gov.item, gov.participant, gov.centre, onGov, toLens, onExit, onLeave])

  /* WHERE THE INSPECTOR IS UNDER THE CORPUS, OPENING ONE GOES TO IT (I-138).
     Below the workspace's two-column width the inspector stacks beneath the
     register, so landing on an item -- from "Inspect in Governance" or a row
     -- would otherwise change nothing on screen. Side by side it is already
     in view, and the register marks the row instead. */
  const side = useRef<HTMLElement | null>(null)
  useEffect(() => {
    const el = side.current
    const body = el?.parentElement
    if (!el || !body || !(gov.item || gov.participant)) return
    const stacked = () => getComputedStyle(body).flexDirection === 'column'
    if (!stacked()) return
    const to = () => el.scrollIntoView({ block: 'start' })
    to()
    /* AND IT STAYS THERE WHILE THE REGISTER ABOVE IT ARRIVES. The register
       reads after the inspector mounts and grows above it, and a browser does
       not anchor scrolling at the top of a scroller -- so without this the
       landing is pushed back down the page by what loads after it. Only
       briefly, and never once the reader has moved the page themselves. */
    const centre = body.querySelector('.ws-gov-centre')
    const follow = new ResizeObserver(() => stacked() && to())
    if (centre) follow.observe(centre)
    const stop = () => follow.disconnect()
    const quit = window.setTimeout(stop, 4000)
    const moved = ['wheel', 'touchstart', 'keydown', 'mousedown'] as const
    moved.forEach((ev) => window.addEventListener(ev, stop, { once: true, passive: true }))
    return () => {
      stop()
      window.clearTimeout(quit)
      moved.forEach((ev) => window.removeEventListener(ev, stop))
    }
  }, [gov.item, gov.participant])

  const changed = useCallback(() => {
    corpus.reload()
    ctx.reload()
    onChanged?.()
  }, [corpus, ctx, onChanged])

  return (
    <div className="ws-gov">
      <header className="ws-gov-head">
        {/* WHERE YOU ARE AND HOW TO LEAVE, IN ONE BAR (polish1/topics B).
            "Governance – <Conversation> – Open conversation": the lens, the
            Conversation it is narrowed to as a chip that clears, and the
            door into that Conversation. The exit leads, in words, because
            the way out used to be a small tab at the far end of the lenses. */}
        <div className="ws-scopebar">
          {(onExit ?? onLeave) && (
            <button
              className="ws-exit"
              onClick={onExit ?? onLeave}
              title={exitTitle ?? `leave Governance for ${leaveLabel}`}
              aria-keyshortcuts="Escape"
            >
              <span aria-hidden="true">‹</span> {exitLabel ?? leaveLabel}
            </button>
          )}
          <span className="ws-scopebar-what">
            <span className="ws-scopebar-word">Governance</span>
            <span className="ws-scopebar-sep" aria-hidden="true">
              –
            </span>
            {conversation ? (
              <>
                <span className="ws-scope-chip" title={`Governance is narrowed to ${here}`}>
                  <span className="ws-scope-chip-name">{here}</span>
                  {onClearScope && (
                    <button
                      className="ws-scope-chip-x"
                      aria-label={`Clear the conversation filter: show Governance for the whole Brain`}
                      title="clear: the whole Brain"
                      onClick={onClearScope}
                    >
                      ×
                    </button>
                  )}
                </span>
                {onOpenConversation && (
                  <>
                    <span className="ws-scopebar-sep" aria-hidden="true">
                      –
                    </span>
                    <button className="ws-open-conv" onClick={onOpenConversation}>
                      Open conversation
                    </button>
                  </>
                )}
              </>
            ) : (
              <span className="ws-scope-all">
                the whole Brain
                <span className="ws-scope-hint"> · choose a conversation on the left to narrow it</span>
              </span>
            )}
          </span>
        </div>
        <p className="ws-eyebrow">
          <span className="ws-scope">
            {/* THE ONE PLACE THAT STATES THE RELATIONSHIP. Two scopes, one
                corpus. Everything else in here depends on this being true. */}
            {conversation ? (
              <>
                the governed corpus through the lens of <b>{here}</b>
              </>
            ) : (
              <>the whole governed corpus</>
            )}
          </span>
        </p>

        <nav className="ws-tabs" aria-label="lenses over the governed corpus">
          {LENSES.map((l) => {
            const n = l.lens === 'standing' ? disputes : overlaps
            return (
              <button
                key={l.lens}
                className={'ws-tab' + (gov.lens === l.lens && !isInvestigation(centre) ? ' on' : '')}
                aria-pressed={gov.lens === l.lens && !isInvestigation(centre)}
                title={l.title}
                onClick={() => onGov({ lens: l.lens, centre: { view: 'lens' } })}
              >
                {l.label}
                {n > 0 && (
                  <i
                    className="ws-tab-n"
                    title={
                      l.lens === 'standing'
                        ? 'open challenges on material in scope. Nobody asked you about them.'
                        : 'standing items that speak to one subject. Composition includes both.'
                    }
                  >
                    {n}
                  </i>
                )}
              </button>
            )
          })}
          <HistoryMenu
            lens={gov.lens === 'standing' ? 'Standing' : 'In use'}
            onAsk={(q: Question) => onGov({ centre: { view: 'history', question: q } })}
          />
          {/* The old small door stays only where it goes somewhere the
              prominent exit does not: Brain home, from Brain scope. */}
          {onLeave && onExit && !conversation && (
            <button
              className="ws-tab ws-turns"
              onClick={onLeave}
              title={`leave Governance for ${leaveLabel}`}
            >
              {leaveLabel}
            </button>
          )}
        </nav>

        {/* THE BREADCRUMB FOR AN INVESTIGATION, which names where it was
            entered from. History carries its own marker inside its answer, so
            this one says "Investigating" and leaves that to it. */}
        {isInvestigation(centre) && centre.view !== 'history' && (
          <p className="ws-crumb">
            <button className="ws-crumb-back" onClick={toLens}>
              ‹ Back to {backLabel}
            </button>
            <span className="ws-crumb-what">Investigating · {labelOf(gov)}</span>
          </p>
        )}
      </header>

      <div className="ws-gov-body">
        <div className="ws-gov-centre">
          {centre.view === 'lens' &&
            (gov.lens === 'standing' ? (
              <LensStanding
                conversation={conversation}
                conversationName={conversationName}
                filters={gov.filters}
                onFilters={(filters) => onGov({ filters })}
                me={me}
                onOpenEntry={inspect}
                onCompare={compare}
                onInUse={() => onGov({ lens: 'use' })}
                names={names}
                onChanged={changed}
                inspected={gov.item}
              />
            ) : (
              <InUseLens
                conversation={conversation}
                conversationName={conversationName}
                participant={me}
                /* THE SAME QUERY, WHICHEVER LENS IS READING IT. Each lens
                   offers only its own facet — Standing asks what the record
                   says about material, In use asks how material reaches work —
                   but the search and the Kind are one query held in the
                   address, so switching lens keeps them and a link carries
                   whichever facet was set. */
                filters={gov.filters}
                onFilters={(filters) => onGov({ filters })}
                me={me}
                onWhy={() => trace(null)}
                onPreview={() => onGov({ centre: { view: 'preview' } })}
                onInspect={inspect}
                onCompare={compare}
              />
            ))}

          {centre.view === 'history' && (
            <HistoryAnswer
              question={centre.question as Question}
              conversation={conversation}
              me={me}
              lens={backLabel}
              onBack={toLens}
              onOpenExecution={openExecution}
              onInspect={inspect}
            />
          )}

          {centre.view === 'trace' && (
            <WhereMeetsWho
              conversation={conversation}
              conversationName={conversationName}
              subject={centre.subject}
              onBack={toLens}
              backLabel={backLabel}
              onPreview={() => onGov({ centre: { view: 'preview' } })}
              onOpenExecution={openExecution}
              onInspect={inspect}
            />
          )}

          {centre.view === 'execution' && (
            <ExecutionSheet
              execution={centre.execution}
              backLabel={backLabel}
              onBack={toLens}
              onClose={toLens}
              onOpenEntry={inspect}
              onTrace={(execution) => trace({ kind: 'execution', id: execution })}
              onPreview={() => onGov({ centre: { view: 'preview' } })}
            />
          )}

          {centre.view === 'compare' && (
            <Compare
              left={centre.left}
              right={centre.right}
              conversation={conversation}
              participant={me}
              origin={backLabel}
              onBack={toLens}
              onOpenEntry={inspect}
              onTrace={(entry) => trace({ kind: 'material', id: entry })}
              /* THE DELIVERY RECORDS, WHERE THE COUNT IS READ FROM (I-116).
                 The inspector's own "What executions actually received it?"
                 fold is that list; opening it by name is a door to the
                 records themselves rather than a second copy of them. */
              onDeliveryEvidence={(entry) =>
                onGov({ item: entry, participant: null, open: ['received'] })
              }
              ask={driving.known ? driving.ask && askOf(driving.ask) : undefined}
              /* ANSWERING IS A REPLY AND NOTHING ELSE. The same mechanism
                 every other answer uses: a Turn addressed to whoever asked.
                 No governed material is touched, which is exactly what the
                 consequence block promised before the click. */
              /* A FORM OR AN INPUT IS NOT ANSWERED BY A REPLY. A form
                 question is answered at its form, drawn here; an input by
                 Done at its block. Neither is offered "Answer … & close". */
              answerHere={
                driving.ask?.form ? (
                  <FormHere ask={driving.ask} me={me} onChanged={changed} />
                ) : driving.ask?.expects === 'input' ? (
                  <p className="xs-note">
                    This asks for your input at a block on its post. Done at that block closes
                    it; a reply does not.
                  </p>
                ) : undefined
              }
              onAnswer={
                driving.ask && !driving.ask.form && driving.ask.expects !== 'input'
                  ? async (answer) => {
                      const closed = await answerAsk(
                        {
                          expectation: driving.ask!.expectation,
                          turn: driving.ask!.turn,
                          conversation: driving.ask!.conversation,
                          asked_by: driving.ask!.asked_by,
                          asked_by_alias: driving.ask!.asked_by_alias,
                          question: driving.ask!.question,
                        },
                        answer,
                        me,
                      )
                      changed()
                      /* CLOSED ONLY WHEN THE RECORD SAYS SO; otherwise it is
                         said here, and the reader stays where they are. */
                      if (closed !== true)
                        throw new Error(
                          answeredSaid(answer, driving.ask!.asked_by_alias ?? 'the asker', closed),
                        )
                      toLens()
                    }
                  : undefined
              }
              /* AND LEAVING IT OPEN RECORDS NOTHING, which is why this writes
                 nothing and only closes the investigation. It stays owed. */
              onLeaveOpen={driving.ask ? toLens : undefined}
              onEstablish={inspect}
              /* WHO THE ONE-ACT APPROVAL IS ATTRIBUTED TO. Compare offers it
                 where the record holds a proposal; an act with nobody to
                 attribute it to is not offered at all. */
              me={me}
            />
          )}

          {centre.view === 'preview' && (
            <PreviewSheet
              conversation={conversation}
              conversationName={conversationName}
              participant={me}
              onClose={toLens}
              onInspect={inspect}
            />
          )}
        </div>

        {/* THE ONE SHARED INSPECTOR, reached from every reference anywhere. It
            is an aside and never the page: what is being read stays on screen
            behind it, because an item is read ABOUT something. */}
        {(gov.item || gov.participant) && (
          <aside ref={side} className="ws-gov-side" aria-label="Inspector">
            <div className="ws-side-head">
              <span className="ws-side-eyebrow">Inspector</span>
              <span className="ws-side-scope">{conversation ? here : 'Brain'}</span>
              <button
                className="ws-side-close"
                title="Close the inspector"
                aria-label="Close the inspector"
                onClick={() => onGov({ item: null, participant: null })}
              >
                ×
              </button>
            </div>
            <div className="ws-side-body">
              {gov.participant ? (
                <WorkspaceParticipant
                  participant={gov.participant}
                  conversation={conversation}
                  conversationName={conversationName}
                  onOpenExecution={openExecution}
                  onTrace={(id) => trace({ kind: 'participant', id })}
                  onPreview={() => onGov({ centre: { view: 'preview' } })}
                  onInspect={inspect}
                />
              ) : (
                <EntryInspect
                  id={gov.item as Id}
                  conversation={conversation}
                  conversationName={conversationName}
                  governance
                  openFolds={gov.open}
                  onOpenEntry={inspect}
                  onGoToTurn={onGoToTurn}
                  onOpenExecution={openExecution}
                  onTrace={(id) => trace({ kind: 'material', id })}
                  onCompare={compare}
                  onPreview={() => onGov({ centre: { view: 'preview' } })}
                  onOpenParticipant={(participant) => onGov({ participant, item: null })}
                />
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  )
}
