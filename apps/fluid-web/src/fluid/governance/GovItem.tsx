/* ONE GOVERNED OR RECORDED ITEM, OPEN ON STAGE: Contract §6 & mockup adm-d4f3ea138d43.
 *
 * Opens as a tab beside This post (its originating conversation in the column,
 * with that Turn highlighted), or on Governance's own Stage when the record
 * names no conversation for it.
 *
 * Combines the Epistemic Ladder Item & Evidence view (`/api/ladder/items/<id>`:
 * status pills, limits, recorded-by attribution, `evidence | by reply | history`
 * toggle, lineage strip, basis with cite quotes, challenges, used-by-later-work
 * delivery/citation/outcome stats, history, and Request adoption / Open adoption
 * card / Challenge… / Copy reference / Open in Learning) with Classic's
 * (challenges show their resolution -- open, withdrawn, set aside -- and offer
 * Withdraw only on your own challenge, Set aside only to the owner, on
 * somebody else's) `useRecordActs` and `RecordPanel` so every existing
 * governance act and record inspection works in place -- for material that
 * stands and governs. Ladder material is said and acted on in the Ladder's
 * vocabulary only (`isLadderMaterial`). */

import { useCallback, useState } from 'react'
import { announceAdvance, post, useApi, when, type Id } from '../../api'
import { Prose } from '../../prose'
import { useRecordActs } from '../../surfaces/governance/R2Record'
import type { KindAuthoring } from '../../surfaces/governance/r2Model'
import { useGovNav } from './context'
import FluidPreviewSheet from './FluidPreviewSheet'
import {
  artifactUrl,
  atAlias,
  attemptedLabel,
  basisVerb,
  challengeActsFor,
  citeView,
  formatStatusLabel,
  isArtifactRef,
  isLadderMaterial,
  resolutionOf,
  whoOf,
  type CitedByRecord,
  type LadderItemDetail,
  type OutcomeSummary,
} from './ladderTypes'
import { restOf, type Source } from './model'
import RecordPanel, { standingSaid, type EntryFull } from './RecordPanel'
import './governance.css'

function normalizeOutcomes(raw: LadderItemDetail['outcomes'] | undefined): OutcomeSummary[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  return raw.all ?? raw.latest ?? []
}

function normalizeCitedBy(raw: LadderItemDetail['cited_by'] | undefined): CitedByRecord[] {
  if (!raw || typeof raw === 'number') return []
  return raw
}

const relationLabel = (rel: string) => basisVerb(rel).toUpperCase()

/** A Turn is an entry of Kind `contribution`; it opens in its conversation. */
const isTurn = (kind: string | null | undefined) => kind === 'turn' || kind === 'contribution'

/** Held bytes open as Fluid opens any held artifact: the verified route, in
 *  a tab of its own. They are not an entry, so never opened as an item. */
const openArtifact = (ref: Id) => { window.open(artifactUrl(ref), '_blank', 'noopener') }

export default function GovItem({ entry, onBack, onClose, source }: {
  entry: Id
  /** back to the Governance list */
  onBack: () => void
  /** close the item's page, as its tab's × does: given where it is a page */
  onClose?: () => void
  /** how it came to open where it did, where that needs saying */
  source?: Source | null
}) {
  const g = useGovNav()
  const where = source !== undefined ? source : g.sourceOf(entry)
  const definitions = useApi<{ kinds: KindAuthoring[] }>('/api/governance/authoring')
  const [preview, setPreview] = useState(false)
  const [rev, setRev] = useState(0)
  const [edit] = useState(() => g.takeEdit(entry))
  const [viewMode, setViewMode] = useState<'evidence' | 'by_reply' | 'history'>('evidence')
  const [ladderAct, setLadderAct] = useState<'request-adoption' | 'challenge' | null>(null)
  const [actReason, setActReason] = useState('')
  const [actEvidence, setActEvidence] = useState('')
  const [setAsideLink, setSetAsideLink] = useState<Id | null>(null)
  const [setAsideReason, setSetAsideReason] = useState('')
  const [withdrawLink, setWithdrawLink] = useState<Id | null>(null)
  const [withdrawReason, setWithdrawReason] = useState('')
  const [actBusy, setActBusy] = useState(false)
  const [actMsg, setActMsg] = useState<string | null>(null)
  const [actErr, setActErr] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const ladderRead = useApi<LadderItemDetail>(
    '/api/ladder/items/' + encodeURIComponent(entry),
  )
  const changed = useCallback(() => {
    setRev((n) => n + 1)
    announceAdvance()
  }, [])
  const r = useRecordActs({
    id: entry, conversation: null, me: g.me, kinds: definitions.data?.kinds ?? [], names: {},
    initialEdit: edit, inline: true, oneRow: true,
    onInspect: (id) => g.openItem(id), onPreview: () => setPreview(true), onChanged: changed,
  })
  const ladder = ladderRead.data

  const d = r.entry.data as unknown as (EntryFull & { fields: string[]; body: Record<string, unknown> }) | null
  const principal = d?.fields?.find((f) => typeof d.body[f] === 'string' && String(d.body[f]).trim())
  const text = (d && principal ? String(d.body[principal]) : '') || ladder?.text || ''
  const kind = d?.kind ?? ladder?.kind ?? 'governed item'
  const ladderStatus = ladder ? formatStatusLabel(ladder.status) : null
  /* ONE VOCABULARY. Ladder material -- everything but adopted governing
     material -- is said only in the Ladder's words and acted on only by the
     Ladder's acts; the pre-ladder standing pill, Standing line and
     Establish / Dispute / More are for material that stands and governs.
     Until the ladder read answers, neither is drawn; where it fails, the
     record's own vocabulary is what there is. */
  const ladderMaterial: boolean | null = ladder ? isLadderMaterial(ladder)
    : ladderRead.error ? false : null
  const legacy = ladderMaterial === false
  const pill = legacy && d && !d.missing ? standingSaid(d) : null
  const acting = r.acting != null || preview || ladderAct != null

  const origConv = ladder?.originating?.conversation ?? ladder?.recorded_by?.conversation ?? where?.conversation ?? null
  const origConvName = ladder?.originating?.conversation_name
    ?? ladder?.recorded_by?.conversation_name
    ?? where?.conversationName
    ?? origConv
  const origTurn = ladder?.originating?.turn ?? ladder?.recorded_by?.turn ?? where?.turn ?? null
  const origNum = ladder?.originating?.number ?? ladder?.recorded_by?.number ?? null

  const outcomes = normalizeOutcomes(ladder?.outcomes)
  const citedList = normalizeCitedBy(ladder?.cited_by)
  const citedCount = typeof ladder?.cited_by === 'number'
    ? ladder.cited_by
    : (ladder?.usage?.cited ?? citedList.length)
  const deliveredCount = ladder?.usage?.delivered ?? ladder?.delivered?.length ?? ladder?.delivered_to ?? 0

  const submitRequestAdoption = async () => {
    if (!g.me) {
      setActErr('Mentis could not say who you are.')
      return
    }
    if (!actReason.trim()) {
      setActErr('Please state why this item should be adopted.')
      return
    }
    setActBusy(true)
    setActErr(null)
    try {
      await post(`/api/entries/${encodeURIComponent(entry)}/request-adoption`, {
        attributed_to: g.me,
        because: actReason.trim(),
      })
      setLadderAct(null)
      setActReason('')
      setActMsg('Requested adoption.')
      changed()
      ladderRead.reload()
    } catch (e) {
      setActErr((e as Error).message || String(e))
    } finally {
      setActBusy(false)
    }
  }

  const submitChallenge = async () => {
    if (!g.me) {
      setActErr('Mentis could not say who you are.')
      return
    }
    if (!actReason.trim()) {
      setActErr('Please state the reason or counter-evidence for this challenge.')
      return
    }
    setActBusy(true)
    setActErr(null)
    try {
      const payload: Record<string, unknown> = {
        attributed_to: g.me,
        because: actReason.trim(),
      }
      const evIds = actEvidence.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean)
      if (evIds.length > 0) payload.evidence = evIds
      await post(`/api/entries/${encodeURIComponent(entry)}/dispute`, payload)
      setLadderAct(null)
      setActReason('')
      setActEvidence('')
      setActMsg('Challenge recorded.')
      changed()
      ladderRead.reload()
    } catch (e) {
      setActErr((e as Error).message || String(e))
    } finally {
      setActBusy(false)
    }
  }

  const submitSetAside = async (disputeLink: Id) => {
    if (!g.me) {
      setActErr('Mentis could not say who you are.')
      return
    }
    if (!setAsideReason.trim()) {
      setActErr('A reason is required to set aside a challenge.')
      return
    }
    setActBusy(true)
    setActErr(null)
    try {
      await post(`/api/entries/${encodeURIComponent(entry)}/set-aside`, {
        attributed_to: g.me,
        dispute: disputeLink,
        because: setAsideReason.trim(),
      })
      setSetAsideLink(null)
      setSetAsideReason('')
      setActMsg('Challenge set aside.')
      changed()
      ladderRead.reload()
    } catch (e) {
      setActErr((e as Error).message || String(e))
    } finally {
      setActBusy(false)
    }
  }

  /* WITHDRAWING IS THE CHALLENGER'S OWN ACT (addendum 1, D7): offered only on
   * a challenge the record attributes to you, and the server refuses anyone
   * else. Both the challenge and the withdrawal stay in the record. */
  const submitWithdraw = async (disputeLink: Id) => {
    if (!g.me) {
      setActErr('Mentis could not say who you are.')
      return
    }
    if (!withdrawReason.trim()) {
      setActErr('Say why you are withdrawing your challenge.')
      return
    }
    setActBusy(true)
    setActErr(null)
    try {
      await post(`/api/entries/${encodeURIComponent(entry)}/withdraw-challenge`, {
        attributed_to: g.me,
        dispute: disputeLink,
        because: withdrawReason.trim(),
      })
      setWithdrawLink(null)
      setWithdrawReason('')
      setActMsg('Challenge withdrawn.')
      changed()
      ladderRead.reload()
    } catch (e) {
      setActErr((e as Error).message || String(e))
    } finally {
      setActBusy(false)
    }
  }

  const copyReference = () => {
    try {
      void navigator.clipboard?.writeText(entry)
    } catch {
      /* clipboard may be unavailable in non-secure context */
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <article className={'fg-item' + (acting ? ' fg-acting' : '')} data-entry={entry} aria-label="governed item">
      <div className="fg-crumb fg-stagehead">
        <span>
          <button className="fg-link fg-back-gov" onClick={onBack}>‹ Back to Governance</button>
          {onClose && <> · <button className="fg-link fg-close-item" onClick={onClose}>Close</button></>}
          <span className="fg-faint">
            {' · '}Stage · {origNum != null ? `following ${kind} from #${origNum}` : `${kind}`}{' '}
            <span className="fg-mono">{entry}</span>
          </span>
        </span>
        {ladder && (
          <span className="fg-seg2" role="group" aria-label="Item view mode">
            <button
              type="button"
              aria-pressed={viewMode === 'evidence'}
              className={viewMode === 'evidence' ? 'on' : ''}
              onClick={() => setViewMode('evidence')}
            >
              evidence
            </button>
            <button
              type="button"
              aria-pressed={viewMode === 'by_reply'}
              className={viewMode === 'by_reply' ? 'on' : ''}
              onClick={() => setViewMode('by_reply')}
            >
              by reply
            </button>
            <button
              type="button"
              aria-pressed={viewMode === 'history'}
              className={viewMode === 'history' ? 'on' : ''}
              onClick={() => setViewMode('history')}
            >
              history
            </button>
          </span>
        )}
      </div>

      <div className="fg-item-body">
        <div className="fg-item-main">
          <header className="fg-item-head">
            <span className="r2-tag">{kind}</span>
            {pill && <span className={`r2-status ${pill.tone}`}>{pill.words}</span>}
            {ladder && ladderStatus && (
              <span className={`fg-l-pill ${ladder.status === 'adoption_requested' ? 'p-req' : ladder.status === 'adopted' ? 'p-ado' : ladder.status === 'declined' ? 'p-dec' : 'p-rec'}`}>
                {ladderStatus.label}
              </span>
            )}
            {ladder && ladder.status !== 'adopted' && (
              <span className="fg-l-pill p-rec">Not adopted · reaches later work as evidence</span>
            )}
            {ladder && ladder.status === 'adopted' && ladder.governs && (
              <span className="fg-l-pill p-gov">Governs work</span>
            )}
            {d && !d.missing && (
              <span className="fg-faint">
                {d.author_alias ?? ladder?.recorded_by?.alias ?? 'unattributed'}
                {(d.at ?? ladder?.recorded_at) ? ` · ${when((d.at ?? ladder?.recorded_at)!)}` : ''}
              </span>
            )}
          </header>

          {r.entry.loading && !d && !ladder && <p className="fg-faint">Reading the record…</p>}
          {/* The entry's own read failing is said even when the ladder read
              answered: the record panel and the acts depend on it. */}
          {r.entry.error && !d && (
            <p className="fg-field-error" role="alert">
              Couldn’t read this item: {r.entry.error}{' '}
              <button className="fg-link" onClick={r.entry.reload}>Retry</button>
            </p>
          )}
          {d?.missing && !ladder && <p className="fg-faint">This Brain does not hold {entry}.</p>}

          {text && (
            <div className="fg-item-text">
              <Prose src={text} scope={`entry:${entry}:${principal ?? 'text'}`} />
            </div>
          )}
          {d && restOf(d.fields, d.body, principal).map((x) => (
            <div key={x.field} className="fg-item-field" data-field={x.field}>
              <div className="fg-lbl">{x.field}</div>
              <Prose src={x.text} scope={`entry:${entry}:${x.field}`} />
            </div>
          ))}

          {ladder?.limits && (
            <p className="fg-item-limits">
              <b>Limits:</b> {ladder.limits}
            </p>
          )}

          {ladder?.recorded_by && (
            <p className="fg-item-recorded-by">
              Recorded by <b>{atAlias(ladder.recorded_by.alias, 'unattributed')}</b>
              {ladder.recorded_by.runtime && (
                <>
                  {' · '}{ladder.recorded_by.runtime}
                  {ladder.recorded_by.model ? ` (${ladder.recorded_by.model})` : ''}
                </>
              )}
              {ladder.recorded_by.persona && <> · wearing {ladder.recorded_by.persona_name ?? ladder.recorded_by.persona}</>}
              {origConvName && (
                <>
                  {' · '}in{' '}
                  {origConv && origTurn ? (
                    <button
                      type="button"
                      className="fg-link"
                      onClick={() => g.readTurn(origConv, origTurn)}
                    >
                      {origConvName}{origNum != null ? ` #${origNum}` : ''}
                    </button>
                  ) : (
                    <span>{origConvName}{origNum != null ? ` #${origNum}` : ''}</span>
                  )}
                </>
              )}
              {ladder.recorded_at != null && <> · {when(ladder.recorded_at)}</>}
              {ladder.recorded_by.execution && (
                <> · during work <span className="fg-mono">{ladder.recorded_by.execution}</span></>
              )}
            </p>
          )}

          {where?.why === 'placed' && (
            <p className="fg-faint fg-note">
              Opened beside {where.conversationName ?? 'the conversation'} because it is placed there; the record names no Turn it was proposed in.
            </p>
          )}
          {where === null && !origConv && (
            <p className="fg-faint fg-note">
              The record names no conversation this was proposed in, so it opens here on Governance.
            </p>
          )}

          {ladder && (
            <div className="fg-item-ladder-panel" data-testid="ladder-item-detail">
              <div className="fg-lineage" aria-label="Epistemic lineage">
                {(ladder.lineage?.up ?? []).map((node) => (
                  <span key={`up-${node.id}`} className="fg-lineage-step">
                    <button
                      type="button"
                      className="fg-lineage-node"
                      onClick={() => {
                        if (isArtifactRef(node.id)) {
                          openArtifact(node.id)
                        } else if (isTurn(node.kind) && origConv) {
                          g.readTurn(origConv, node.id)
                        } else {
                          g.openItem(node.id)
                        }
                      }}
                    >
                      {isArtifactRef(node.id) ? `ARTIFACT · ${citeView(node).link}`
                        : `${(node.kind ?? 'source').toUpperCase()} · ${node.label || node.id}`}
                    </button>
                    <span className="fg-lineage-arr">→</span>
                  </span>
                ))}
                <span className="fg-lineage-node me">
                  {kind.toUpperCase()} (this)
                </span>
                {(ladder.lineage?.down ?? []).map((node) => (
                  <span key={`down-${node.id}`} className="fg-lineage-step">
                    <span className="fg-lineage-arr">→</span>
                    <button
                      type="button"
                      className="fg-lineage-node"
                      onClick={() => isArtifactRef(node.id) ? openArtifact(node.id) : g.openItem(node.id)}
                    >
                      {isArtifactRef(node.id) ? `ARTIFACT · ${citeView(node).link}`
                        : `${(node.kind ?? 'source').toUpperCase()} · ${node.label || node.id}`}
                    </button>
                  </span>
                ))}
              </div>

              <div className="fg-item-two">
                <div className="fg-item-col-left">
                  {(viewMode === 'evidence' || viewMode === 'by_reply') && (
                    <div className="fg-item-blk">
                      <div className="fg-lbl">Basis · what it was concluded from</div>
                      {!ladder.basis || ladder.basis.length === 0 ? (
                        <p className="fg-faint fg-mt-xs">No basis recorded.</p>
                      ) : (
                        ladder.basis.map((b) => {
                          const cv = citeView(b)
                          return (
                          <div key={b.ref + b.relation} className="fg-item-ln">
                            <span className="fg-item-ln-k">{relationLabel(b.relation)}</span>
                            <div>
                              <button
                                type="button"
                                className="fg-link"
                                onClick={() => {
                                  if (cv.artifact) {
                                    openArtifact(b.ref)
                                  } else if (isTurn(b.kind) && origConv) {
                                    g.readTurn(origConv, b.ref)
                                  } else {
                                    g.openItem(b.ref)
                                  }
                                }}
                              >
                                {cv.link}
                              </button>
                              {cv.note && <span className="fg-faint"> · {cv.note}</span>}
                              {cv.quote && <div className="fg-quote">{cv.quote}</div>}
                            </div>
                          </div>
                          )
                        })
                      )}
                    </div>
                  )}

                  {outcomes.length > 0 && (
                    <div className="fg-item-blk">
                      <div className="fg-lbl">Outcomes · {outcomes.length}</div>
                      {outcomes.map((o) => (
                        <div key={o.id} className="fg-item-ln">
                          <span className="fg-item-ln-k">{(o.result || 'OUTCOME').toUpperCase()}</span>
                          <div>
                            <span>{o.text}</span>
                            {attemptedLabel(o.attempted)}
                            {' · '}
                            <button type="button" className="fg-link" onClick={() => g.openItem(o.id)}>
                              {o.id}
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="fg-item-blk">
                    <div className="fg-lbl">Challenges</div>
                    {(!ladder.challenges || ladder.challenges.length === 0) ? (
                      <p className="fg-faint fg-mt-xs">
                        None.{' '}
                        <button
                          type="button"
                          className="fg-link"
                          onClick={() => setLadderAct(ladderAct === 'challenge' ? null : 'challenge')}
                        >
                          Challenge with evidence…
                        </button>
                      </p>
                    ) : (
                      <div className="fg-item-challenges">
                        {ladder.challenges.map((ch) => {
                          const res = resolutionOf(ch)
                          /* Withdraw on your own open challenge; Set aside
                             only for the owner, on somebody else's. */
                          const can = challengeActsFor(ch, g.me, g.owner)
                          return (
                          <div key={ch.link} className={'fg-item-ln fg-chal-' + res} data-challenge={ch.link} data-resolution={res}>
                            <span className="fg-item-ln-k">{res === 'set_aside' ? 'SET ASIDE' : res === 'withdrawn' ? 'WITHDRAWN' : 'OPEN'}</span>
                            <div>
                              <div>
                                <b>{whoOf(ch)}</b>: “{ch.because}”{ch.at != null ? ` · ${when(ch.at)}` : ''}
                              </div>
                              {res === 'withdrawn' && ch.withdrawn ? (
                                <div className="fg-faint">
                                  Withdrawn by {whoOf(ch.withdrawn)}: “{ch.withdrawn.because}”
                                  {ch.withdrawn.at != null ? ` · ${when(ch.withdrawn.at)}` : ''}
                                </div>
                              ) : res === 'set_aside' && ch.set_aside ? (
                                <div className="fg-faint">
                                  Set aside by {whoOf(ch.set_aside)}: “{ch.set_aside.because}”
                                  {ch.set_aside.at != null ? ` · ${when(ch.set_aside.at)}` : ''}
                                </div>
                              ) : can.withdraw ? (
                                <div className="fg-mt-xs">
                                  {withdrawLink === ch.link ? (
                                    <div className="fg-inline-mini-form">
                                      <input
                                        aria-label="Reason to withdraw your challenge"
                                        placeholder="Why are you withdrawing it?"
                                        value={withdrawReason}
                                        onChange={(e) => setWithdrawReason(e.target.value)}
                                      />
                                      <button
                                        type="button"
                                        className="fg-btn-primary"
                                        disabled={actBusy || !withdrawReason.trim()}
                                        onClick={() => void submitWithdraw(ch.link)}
                                      >
                                        Withdraw
                                      </button>
                                      <button
                                        type="button"
                                        className="fg-btn-secondary"
                                        onClick={() => setWithdrawLink(null)}
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  ) : (
                                    <button
                                      type="button"
                                      className="fg-link fg-withdraw"
                                      onClick={() => {
                                        setWithdrawLink(ch.link)
                                        setWithdrawReason('')
                                      }}
                                    >
                                      Withdraw…
                                    </button>
                                  )}
                                </div>
                              ) : can.setAside && (
                                <div className="fg-mt-xs">
                                  {setAsideLink === ch.link ? (
                                    <div className="fg-inline-mini-form">
                                      <input
                                        aria-label="Reason to set aside challenge"
                                        placeholder="Reason to set aside…"
                                        value={setAsideReason}
                                        onChange={(e) => setSetAsideReason(e.target.value)}
                                      />
                                      <button
                                        type="button"
                                        className="fg-btn-primary"
                                        disabled={actBusy || !setAsideReason.trim()}
                                        onClick={() => void submitSetAside(ch.link)}
                                      >
                                        Set aside
                                      </button>
                                      <button
                                        type="button"
                                        className="fg-btn-secondary"
                                        onClick={() => setSetAsideLink(null)}
                                      >
                                        Cancel
                                      </button>
                                    </div>
                                  ) : (
                                    <button
                                      type="button"
                                      className="fg-link fg-set-aside"
                                      onClick={() => {
                                        setSetAsideLink(ch.link)
                                        setSetAsideReason('')
                                      }}
                                    >
                                      Set aside…
                                    </button>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </div>

                <div className="fg-item-col-right">
                  {(viewMode === 'evidence' || viewMode === 'by_reply') && (
                    <div className="fg-item-blk">
                      <div className="fg-lbl">Used by later work</div>
                      <div className="fg-item-ln">
                        <span className="fg-item-ln-k">DELIVERED</span>
                        <span>
                          to {deliveredCount} {deliveredCount === 1 ? 'run' : 'runs'} as{' '}
                          <i>{ladder.governs && ladder.status === 'adopted' ? 'governing material' : ladder.status === 'adopted' ? 'adopted knowledge' : 'relevant experience'}</i>
                        </span>
                      </div>
                      {viewMode === 'by_reply' && (ladder.delivered ?? []).map((del) => (
                        <div key={del.execution} className="fg-item-ln">
                          <span className="fg-item-ln-k">RUN</span>
                          <span>
                            <b>{atAlias((del as { participant_alias?: string | null }).participant_alias ?? del.participant, 'agent')}</b>
                            {del.runtime ? ` · ${del.runtime}` : ''}
                            {del.conversation_name ? ` in ${del.conversation_name}` : ''}
                            {del.number != null ? ` #${del.number}` : ''}
                            {del.at != null ? ` · ${when(del.at)}` : ''}
                          </span>
                        </div>
                      ))}
                      {citedList.length > 0 ? (
                        citedList.map((c) => (
                          <div key={c.entry + c.relation} className="fg-item-ln">
                            <span className="fg-item-ln-k">CITED</span>
                            <span>
                              <b>{whoOf(c as { by?: string | null; by_alias?: string | null }, 'agent')}</b>
                              {c.conversation_name ? ` in ${c.conversation_name}` : ''}
                              {c.number != null ? ` #${c.number}` : ''}
                              {c.text ? `: “${c.text}”` : ''}{' '}
                              <button type="button" className="fg-link" onClick={() => g.openItem(c.entry)}>
                                {c.kind} {c.entry}
                              </button>
                            </span>
                          </div>
                        ))
                      ) : (
                        <div className="fg-item-ln">
                          <span className="fg-item-ln-k">CITED</span>
                          <span>{citedCount > 0 ? `Cited by ${citedCount} items` : 'Not cited yet'}</span>
                        </div>
                      )}
                      {deliveredCount > citedCount && (
                        <div className="fg-item-ln">
                          <span className="fg-item-ln-k">NOT USED</span>
                          <span>
                            Delivered to {deliveredCount - citedCount} {deliveredCount - citedCount === 1 ? 'run' : 'runs'} without citation
                          </span>
                        </div>
                      )}
                      {ladder.usage?.outcomes_after_delivery && (
                        (ladder.usage.outcomes_after_delivery.worked > 0 ||
                          ladder.usage.outcomes_after_delivery.failed > 0 ||
                          ladder.usage.outcomes_after_delivery.other > 0) && (
                          <div className="fg-item-ln">
                            <span className="fg-item-ln-k">OUTCOMES</span>
                            <span>
                              After delivery: {ladder.usage.outcomes_after_delivery.worked} worked ·{' '}
                              {ladder.usage.outcomes_after_delivery.failed} failed
                              {/* results are free text: "helped", "succeeded" are neither, and are still outcomes */}
                              {ladder.usage.outcomes_after_delivery.other > 0 &&
                                ` · ${ladder.usage.outcomes_after_delivery.other} other`}
                            </span>
                          </div>
                        )
                      )}
                    </div>
                  )}

                  {(viewMode === 'evidence' || viewMode === 'history') && (
                    <div className="fg-item-blk">
                      <div className="fg-lbl">History</div>
                      <div className="fg-item-hist">
                        {(ladder.history ?? []).map((h, i) => (
                          <div key={i} className="fg-item-hist-line">
                            <b>{h.at != null ? when(h.at) : 'recorded'}</b> {h.act}
                            {h.by ? ` by ${atAlias((h as { by_alias?: string | null }).by_alias ?? h.by)}` : ''}
                            {h.because ? `: “${h.because}”` : ''}
                          </div>
                        ))}
                        {ladder.status === 'adoption_requested' && (
                          <div className="fg-faint">waiting on you · nothing else recorded</div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {actMsg && <p role="status" className="r2-effect">{actMsg}</p>}
              {actErr && <p role="alert" className="fg-field-error">{actErr}</p>}

              {ladderAct === 'request-adoption' && (
                <div className="fg-adopt-inline-form" role="group" aria-label="Request adoption">
                  <label className="fg-lbl" htmlFor={`req-adopt-${entry}`}>Why should the owner adopt this?</label>
                  <input
                    id={`req-adopt-${entry}`}
                    aria-label="Reason to request adoption"
                    placeholder="State the evidence and why this should become an adopted position or rule…"
                    value={actReason}
                    onChange={(e) => setActReason(e.target.value)}
                  />
                  <div className="fg-adopt-foot">
                    <button
                      type="button"
                      className="fg-btn-primary"
                      disabled={actBusy || !actReason.trim()}
                      onClick={() => void submitRequestAdoption()}
                    >
                      {actBusy ? 'Requesting…' : 'Send adoption request'}
                    </button>
                    <button type="button" className="fg-btn-secondary" onClick={() => setLadderAct(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              {ladderAct === 'challenge' && (
                <div className="fg-adopt-inline-form" role="group" aria-label="Challenge item">
                  <label className="fg-lbl" htmlFor={`chal-reason-${entry}`}>Challenge reason</label>
                  <input
                    id={`chal-reason-${entry}`}
                    aria-label="Challenge reason"
                    placeholder="What counter-evidence or defect challenges this item?"
                    value={actReason}
                    onChange={(e) => setActReason(e.target.value)}
                  />
                  <label className="fg-lbl fg-mt" htmlFor={`chal-ev-${entry}`}>Evidence entry IDs (optional)</label>
                  <input
                    id={`chal-ev-${entry}`}
                    aria-label="Challenge evidence IDs"
                    placeholder="e.g. ent-63b40a119d04"
                    value={actEvidence}
                    onChange={(e) => setActEvidence(e.target.value)}
                  />
                  <div className="fg-adopt-foot">
                    <button
                      type="button"
                      className="fg-btn-primary"
                      disabled={actBusy || !actReason.trim()}
                      onClick={() => void submitChallenge()}
                    >
                      {actBusy ? 'Recording challenge…' : 'Record challenge'}
                    </button>
                    <button type="button" className="fg-btn-secondary" onClick={() => setLadderAct(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              <div className="fg-item-ladder-foot" role="group" aria-label="Ladder item actions">
                {ladder.status === 'adoption_requested' ? (
                  <button
                    type="button"
                    className="fg-btn-primary"
                    onClick={() => g.openGov('adoption', { card: entry })}
                  >
                    Open adoption card
                  </button>
                ) : ladder.adoptable && (ladder.status === 'recorded' || ladder.status === 'declined') ? (
                  <button
                    type="button"
                    className="fg-btn-primary"
                    onClick={() => {
                      setActErr(null)
                      setLadderAct(ladderAct === 'request-adoption' ? null : 'request-adoption')
                    }}
                  >
                    Request adoption
                  </button>
                ) : null}
                <button
                  type="button"
                  className="fg-btn-secondary"
                  onClick={() => {
                    setActErr(null)
                    setLadderAct(ladderAct === 'challenge' ? null : 'challenge')
                  }}
                >
                  Challenge…
                </button>
                <button
                  type="button"
                  className="fg-btn-secondary"
                  onClick={copyReference}
                >
                  {copied ? `Copied ${entry}` : 'Copy reference'}
                </button>
                <button
                  type="button"
                  className="fg-btn-secondary"
                  onClick={() => g.openGov('learning')}
                >
                  Open in Learning
                </button>
              </div>
            </div>
          )}

          {r.error}
          {r.said}
          {legacy && r.actions && (
            <div className="fg-acts" onClickCapture={(e) => {
              const t = e.target as HTMLElement
              const more = t.closest('details.r2-more')
              if (more && t.closest('button')) more.removeAttribute('open')
            }}>{r.actions}</div>
          )}
          {!r.actions && d && !d.missing && !g.me && <p className="fg-faint">Acts need somebody to act as; Mentis could not say who you are.</p>}
          {legacy && r.proposed}
          <div className="fg-act-slot">
            {r.form}
            {r.dialog}
            {preview && (
              <FluidPreviewSheet
                conversation={null}
                participant={g.me}
                persona={entry}
                onClose={() => setPreview(false)}
                onInspect={(id) => g.openItem(id)}
              />
            )}
          </div>
          {r.placements}
          {r.warnings}
          {r.carries}
        </div>
        <RecordPanel
          entry={entry}
          d={d}
          entryRead={r.entry}
          rev={rev}
          onOpenItem={(id) => g.openItem(id)}
          onReadTurn={g.readTurn}
          ladderStatus={ladderMaterial === false ? undefined
            : ladder ? { label: ladderStatus!.label, challenged: ladder.challenged } : null}
        />
      </div>
    </article>
  )
}
