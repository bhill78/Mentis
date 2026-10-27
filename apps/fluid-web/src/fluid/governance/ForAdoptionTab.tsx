/* FOR ADOPTION TAB (?gov=1&s=adoption): Contract §6 & mockup adm-5f164374a792.
 *
 * Explicit requests for the owner's adoption decision. Recording something never
 * puts it here; an agent or the owner has to ask. Calls GET /api/ladder/adoption
 * and wires Adopt, Edit wording then adopt, Decline… (reason required), and
 * Not now to POST /api/entries/{id}/{adopt|decline}. */

import { useEffect, useState } from 'react'
import { announceAdvance, post, useApi, when, type Id } from '../../api'
import { useGovNav } from './context'
import {
  artifactUrl,
  askedByOf,
  buildAdoptPayload,
  challengeResolvedLine,
  citeView,
  computeWordDiff,
  evidenceText,
  formatScopeLabel,
  hintOfLadderItem,
  resolutionOf,
  splitChallenges,
  type LadderAdoptionRequest,
  type LadderAdoptionResponse,
  whoOf,
} from './ladderTypes'

function cap(s: string): string {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}

export default function ForAdoptionTab({
  conversations,
  focusEntry,
  onChanged,
  onDismissAsk,
}: {
  conversations: Record<Id, string>
  focusEntry?: Id | null
  onChanged?: () => void
  onDismissAsk?: (entry: Id) => void
}) {
  const g = useGovNav()
  const me = g.me
  const read = useApi<LadderAdoptionResponse>('/api/ladder/adoption')
  const [notNowIds, setNotNowIds] = useState<Set<Id>>(() => new Set())
  const [activeMode, setActiveMode] = useState<Record<Id, 'edit' | 'decline' | null>>({})
  const [editedText, setEditedText] = useState<Record<Id, string>>({})
  const [becauseText, setBecauseText] = useState<Record<Id, string>>({})
  const [scopeOverride, setScopeOverride] = useState<Record<Id, string>>({})
  const [falsifierText, setFalsifierText] = useState<Record<Id, string>>({})
  const [busyId, setBusyId] = useState<Id | null>(null)
  const [errorById, setErrorById] = useState<Record<Id, string>>({})
  const [banner, setBanner] = useState<string | null>(null)

  const requests = (read.data?.requests ?? []).filter((r) => !notNowIds.has(r.entry))
  const focusShown = !!focusEntry && requests.some((r) => r.entry === focusEntry)

  /* THE CARD ASKED FOR IS BROUGHT INTO VIEW: on a phone the Stage is below
     the column, and "Open adoption card" otherwise changes nothing seen. */
  useEffect(() => {
    if (!focusEntry) return
    const card = document.querySelector<HTMLElement>('.fg-adopt-card.focused')
    const target = card ?? document.querySelector<HTMLElement>('.fg-stage')
    target?.scrollIntoView?.({ block: 'start', behavior: 'smooth' })
  }, [focusEntry, focusShown])

  const handleAdopt = async (req: LadderAdoptionRequest, withEditedWording: boolean) => {
    if (!me) {
      setErrorById((prev) => ({ ...prev, [req.entry]: 'Mentis could not say who you are.' }))
      return
    }
    /* A KIND THAT OWES A FALSIFIER is adopted with one: what would show it
       wrong. The server refuses without it; asking first says so here, and
       any refusal it does give is said on the card. */
    const falsifier = (falsifierText[req.entry] ?? '').trim()
    if (req.expects_falsifier && !falsifier) {
      setErrorById((prev) => ({ ...prev, [req.entry]: `A ${req.kind} is adopted with a falsifier: say what would show it wrong.` }))
      return
    }
    setBusyId(req.entry)
    setErrorById((prev) => ({ ...prev, [req.entry]: '' }))
    try {
      const payload = buildAdoptPayload(req, {
        me,
        because: (becauseText[req.entry] ?? '').trim() || req.because || 'Adopted from For adoption review.',
        editedText: withEditedWording ? editedText[req.entry] ?? req.wording.proposed : null,
        scope: scopeOverride[req.entry] || null,
        falsifier: req.expects_falsifier ? falsifier : null,
      })
      await post(`/api/entries/${encodeURIComponent(req.entry)}/adopt`, payload)
      setActiveMode((prev) => ({ ...prev, [req.entry]: null }))
      setBanner(`Adopted ${req.kind} ${req.entry}.`)
      announceAdvance()
      read.reload()
      onChanged?.()
    } catch (e) {
      setErrorById((prev) => ({ ...prev, [req.entry]: (e as Error).message || String(e) }))
    } finally {
      setBusyId(null)
    }
  }

  const handleDecline = async (req: LadderAdoptionRequest) => {
    if (!me) {
      setErrorById((prev) => ({ ...prev, [req.entry]: 'Mentis could not say who you are.' }))
      return
    }
    const reason = (becauseText[req.entry] ?? '').trim()
    if (!reason) {
      setErrorById((prev) => ({ ...prev, [req.entry]: 'A reason is required to decline an adoption request.' }))
      return
    }
    setBusyId(req.entry)
    setErrorById((prev) => ({ ...prev, [req.entry]: '' }))
    try {
      await post(`/api/entries/${encodeURIComponent(req.entry)}/decline`, {
        attributed_to: me,
        because: reason,
        request: req.request,
      })
      setActiveMode((prev) => ({ ...prev, [req.entry]: null }))
      setBanner(`Declined adoption request for ${req.entry}; material stays recorded as experience.`)
      announceAdvance()
      read.reload()
      onChanged?.()
    } catch (e) {
      setErrorById((prev) => ({ ...prev, [req.entry]: (e as Error).message || String(e) }))
    } finally {
      setBusyId(null)
    }
  }

  const handleNotNow = (req: LadderAdoptionRequest) => {
    setNotNowIds((prev) => {
      const next = new Set(prev)
      next.add(req.entry)
      return next
    })
    onDismissAsk?.(req.entry)
  }

  return (
    <div className="fg-adoption-tab" data-testid="for-adoption-tab">
      {banner && <p role="status" className="r2-effect">{banner}</p>}
      {read.loading && !read.data && <p className="fg-faint">Reading adoption requests…</p>}
      {read.error && (
        <p className="fg-field-error" role="alert">
          Couldn’t read adoption requests: {read.error}{' '}
          <button type="button" className="fg-link" onClick={read.reload}>Retry</button>
        </p>
      )}
      {read.data && requests.length === 0 && (
        <p className="fg-empty">
          No adoption requests are waiting on you right now.
          {notNowIds.size > 0 && (
            <>
              {' '}
              <button type="button" className="fg-link" onClick={() => setNotNowIds(new Set())}>
                Show {notNowIds.size} deferred {notNowIds.size === 1 ? 'request' : 'requests'}
              </button>
            </>
          )}
        </p>
      )}

      {requests.map((req) => {
        const isRevision = Boolean(req.wording.current || (req.replaces && req.replaces.length > 0))
        const diff = computeWordDiff(req.wording.current, req.wording.proposed)
        const mode = activeMode[req.entry] ?? null
        const err = errorById[req.entry]
        const convName = req.conversation_name
          ?? req.asked_by?.conversation_name
          ?? (req.conversation ? conversations[req.conversation] : null)
          ?? req.conversation
        const itemHint = hintOfLadderItem({
          id: req.entry,
          kind: req.kind,
          text: req.wording.proposed,
          recorded_by: req.asked_by,
        })
        const isFocused = focusEntry === req.entry
        const asker = askedByOf(req.asked_by)
        const chals = splitChallenges(req.challenges)

        return (
          <article
            key={req.request || req.entry}
            className={'fg-adopt-card' + (isFocused ? ' focused' : '')}
            data-entry={req.entry}
            aria-label={`Adoption request for ${req.kind} ${req.entry}`}
          >
            <header className="fg-adopt-head">
              <span className="fg-l-kind">
                {isRevision ? `Revision · ${cap(req.kind)}` : `${cap(req.kind)} · ${req.governs ? 'governing' : 'working position'}`}
              </span>
              <span className="fg-l-pill p-req">Adoption requested</span>
              {req.governs && <span className="fg-l-pill p-gov">Governs work</span>}
              <span className="fg-adopt-who">
                asked by <b>{asker.who}</b>
                {asker.migratedBy && <span className="fg-faint"> (migrated by {asker.migratedBy})</span>}
                {req.asked_by?.runtime && <> · {req.asked_by.runtime}</>}
                {convName && (
                  <>
                    {' · '}
                    <button
                      type="button"
                      className="fg-link"
                      onClick={() => g.openItem(req.entry, itemHint)}
                    >
                      {convName}{req.number != null ? ` #${req.number}` : ''}
                    </button>
                  </>
                )}
                {req.asked_at != null && <> · {when(req.asked_at)}</>}
              </span>
            </header>

            <div className="fg-adopt-grid">
              <div className="fg-adopt-col-main">
                <div className="fg-lbl">Wording</div>
                <div className="fg-adopt-box">
                  {req.wording.current && (
                    <div className="fg-diff-was" data-testid="wording-was">
                      {req.wording.current}
                    </div>
                  )}
                  <div className="fg-diff-now" data-testid="wording-now">
                    {diff.hasDiff ? (
                      <>
                        {diff.prefix}
                        {diff.added ? <ins>{diff.added}</ins> : null}
                        {diff.suffix}
                      </>
                    ) : (
                      req.wording.proposed
                    )}
                  </div>
                </div>

                {req.limits && (
                  <p className="fg-adopt-subline">
                    <b>Limits:</b> {req.limits}
                  </p>
                )}

                <div className="fg-lbl fg-mt">Scope · where it will apply</div>
                <div className="fg-adopt-scope-row">
                  <select
                    aria-label={`Scope for ${req.entry}`}
                    value={scopeOverride[req.entry] ?? ''}
                    onChange={(e) => setScopeOverride((prev) => ({ ...prev, [req.entry]: e.target.value }))}
                  >
                    <option value="">Reach: {formatScopeLabel(req.scope, req.governs)}</option>
                    <option value="whole_brain">All conversations (Brain-wide)</option>
                    <option value="when_named">Only when named</option>
                    {Object.entries(conversations).map(([cid, cname]) => (
                      <option key={cid} value={cid}>Conversation: {cname}</option>
                    ))}
                  </select>
                  <span className="fg-adopt-scope-note">
                    {isRevision ? 'Unchanged from the version in force unless you change it' : formatScopeLabel(req.scope, req.governs)}
                  </span>
                </div>

                <div className="fg-lbl fg-mt">Replaces</div>
                {req.replaces && req.replaces.length > 0 ? (
                  <div className="fg-adopt-replaces">
                    {req.replaces.map((rep) => (
                      <p key={rep.id} className="fg-adopt-subline">
                        “{rep.text}”
                        {rep.since ? ` · in force since ${when(rep.since)}` : ''}
                        {' · '}
                        <button type="button" className="fg-link" onClick={() => g.openItem(rep.id)}>
                          open
                        </button>
                        . It stays readable as history; nothing is deleted.
                      </p>
                    ))}
                  </div>
                ) : (
                  <p className="fg-adopt-subline">Replaces nothing (new material).</p>
                )}
              </div>

              <div className="fg-adopt-col-side">
                <div className="fg-lbl">Evidence · {req.evidence.length} {req.evidence.length === 1 ? 'item' : 'items'}</div>
                <div className="fg-adopt-box">
                  {req.evidence.length === 0 ? (
                    <p className="fg-faint">No linked basis items recorded.</p>
                  ) : (
                    req.evidence.map((ev) => {
                      /* the words once: beside the label only where they say
                         more than it, and an artifact as its excerpt or range */
                      const cv = citeView(ev)
                      const words = cv.artifact ? null : evidenceText(ev)
                      return (
                        <div key={ev.id} className="fg-adopt-ev">
                          <span className="fg-adopt-ev-k">{(cv.artifact ? 'artifact' : ev.kind || 'source').toUpperCase()}</span>
                          <span>
                            {words && <>{words}{' '}</>}
                            {cv.artifact ? (
                              <a className="fg-link" href={artifactUrl(ev.id)} target="_blank" rel="noopener">{cv.link}</a>
                            ) : (
                              <button type="button" className="fg-link" onClick={() => g.openItem(ev.id)}>
                                {cv.link}
                              </button>
                            )}
                            {cv.quote && <span className="fg-faint"> — “{cv.quote}”</span>}
                            {cv.note && <span className="fg-faint"> · {cv.note}</span>}
                          </span>
                        </div>
                      )
                    })
                  )}
                </div>

                <div className="fg-lbl fg-mt">Challenges</div>
                {/* ONLY OPEN CHALLENGES WARN. Withdrawn and set-aside ones stay
                    listed, muted, with how they were answered. */}
                {chals.open.length === 0 ? (
                  <p className="fg-adopt-subline">None open against the version in force or this request.</p>
                ) : (
                  <div className="fg-adopt-challenges">
                    {chals.open.map((ch) => (
                      <div key={ch.link} className="fg-adopt-challenge-item" data-resolution="open">
                        <span className="fg-warn">{whoOf(ch, 'Participant')}:</span> “{ch.because}”
                      </div>
                    ))}
                  </div>
                )}
                {chals.resolved.length > 0 && (
                  <div className="fg-adopt-challenges fg-adopt-challenges-resolved">
                    {chals.resolved.map((ch) => (
                      <div key={ch.link} className="fg-adopt-challenge-item fg-faint" data-resolution={resolutionOf(ch)}>
                        {whoOf(ch, 'Participant')}: “{ch.because}” · {challengeResolvedLine(ch)}
                      </div>
                    ))}
                  </div>
                )}

                {req.expects_falsifier && (
                  <>
                    <label className="fg-lbl fg-mt" htmlFor={`falsifier-${req.entry}`}>
                      Falsifier · what would show this wrong (needed to adopt a {req.kind})
                    </label>
                    <input
                      id={`falsifier-${req.entry}`}
                      aria-label="Falsifier"
                      className="fg-adopt-falsifier"
                      placeholder="e.g. A run that followed this and still failed the same way…"
                      value={falsifierText[req.entry] ?? ''}
                      onChange={(e) => setFalsifierText((prev) => ({ ...prev, [req.entry]: e.target.value }))}
                    />
                  </>
                )}

                <div className="fg-lbl fg-mt">If you adopt</div>
                <p className="fg-adopt-subline">
                  {req.governs
                    ? 'The next run where this applies receives the adopted wording under GOVERNING, with a one-line “why this holds” pointing at the evidence above.'
                    : 'This becomes an adopted working position under ADOPTED KNOWLEDGE and is delivered to relevant runs with its basis and limits.'}
                </p>
              </div>
            </div>

            {mode === 'edit' && (
              <div className="fg-adopt-inline-form" role="group" aria-label="Edit wording and adopt">
                <label className="fg-lbl" htmlFor={`edit-wording-${req.entry}`}>Wording to adopt</label>
                <textarea
                  id={`edit-wording-${req.entry}`}
                  aria-label="Wording to adopt"
                  rows={3}
                  value={editedText[req.entry] ?? req.wording.proposed}
                  onChange={(e) => setEditedText((prev) => ({ ...prev, [req.entry]: e.target.value }))}
                />
                <label className="fg-lbl fg-mt" htmlFor={`edit-because-${req.entry}`}>Why you are adopting this (optional)</label>
                <input
                  id={`edit-because-${req.entry}`}
                  aria-label="Reason for adopting"
                  placeholder="Why this holds…"
                  value={becauseText[req.entry] ?? ''}
                  onChange={(e) => setBecauseText((prev) => ({ ...prev, [req.entry]: e.target.value }))}
                />
                <div className="fg-adopt-foot">
                  <button
                    type="button"
                    className="fg-btn-primary"
                    disabled={busyId === req.entry}
                    onClick={() => void handleAdopt(req, true)}
                  >
                    {busyId === req.entry ? 'Adopting…' : 'Save wording & adopt'}
                  </button>
                  <button
                    type="button"
                    className="fg-btn-secondary"
                    onClick={() => setActiveMode((prev) => ({ ...prev, [req.entry]: null }))}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {mode === 'decline' && (
              <div className="fg-adopt-inline-form" role="group" aria-label="Decline adoption request">
                <label className="fg-lbl" htmlFor={`decline-because-${req.entry}`}>
                  Why you are declining adoption (required — material stays recorded as experience)
                </label>
                <input
                  id={`decline-because-${req.entry}`}
                  aria-label="Reason for declining adoption"
                  placeholder="e.g. One run is not a pattern yet; keep as recorded experience…"
                  value={becauseText[req.entry] ?? ''}
                  onChange={(e) => setBecauseText((prev) => ({ ...prev, [req.entry]: e.target.value }))}
                />
                <div className="fg-adopt-foot">
                  <button
                    type="button"
                    className="fg-btn-primary"
                    disabled={busyId === req.entry || !(becauseText[req.entry] ?? '').trim()}
                    onClick={() => void handleDecline(req)}
                  >
                    {busyId === req.entry ? 'Declining…' : 'Confirm decline'}
                  </button>
                  <button
                    type="button"
                    className="fg-btn-secondary"
                    onClick={() => setActiveMode((prev) => ({ ...prev, [req.entry]: null }))}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {err && <p className="fg-field-error" role="alert">{err}</p>}

            <footer className="fg-adopt-foot">
              <button
                type="button"
                className="fg-btn-primary"
                disabled={busyId === req.entry}
                onClick={() => void handleAdopt(req, false)}
              >
                {busyId === req.entry ? 'Adopting…' : 'Adopt'}
              </button>
              <button
                type="button"
                className="fg-btn-secondary"
                disabled={busyId === req.entry}
                onClick={() => {
                  setEditedText((prev) => ({ ...prev, [req.entry]: prev[req.entry] ?? req.wording.proposed }))
                  setActiveMode((prev) => ({ ...prev, [req.entry]: prev[req.entry] === 'edit' ? null : 'edit' }))
                }}
              >
                Edit wording, then adopt
              </button>
              <button
                type="button"
                className="fg-btn-secondary"
                disabled={busyId === req.entry}
                onClick={() => setActiveMode((prev) => ({ ...prev, [req.entry]: prev[req.entry] === 'decline' ? null : 'decline' }))}
              >
                Decline…
              </button>
              <button
                type="button"
                className="fg-btn-secondary"
                onClick={() => handleNotNow(req)}
              >
                Not now
              </button>
              <button
                type="button"
                className="fg-link fg-adopt-inspect"
                onClick={() => g.openItem(req.entry, itemHint)}
              >
                Open item & evidence →
              </button>
              <span className="fg-adopt-note">
                Adopt is one act: it establishes this version, supersedes the one it replaces and keeps its scope. Decline closes the request and says nothing about whether it is true; the material stays recorded.
              </span>
            </footer>
          </article>
        )
      })}
    </div>
  )
}
