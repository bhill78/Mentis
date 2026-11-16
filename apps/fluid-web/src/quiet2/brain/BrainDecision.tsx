/* AN OWNER DECISION (manage-brain round 2, mockup 4-decision.html):
 * Adopt, Decline, or Edit wording first -- exactly, never a fourth choice --
 * with where it applies and an optional reason. "An owner decision appears
 * only when the record asks one of you" (DESIGN-r2.md): `BrainRecord.tsx`
 * renders this only while an adoption request is open on the record it is
 * showing.
 *
 * THIS IS THE SAME ADOPTION FLOW Governance's `ForAdoptionTab` already
 * offers, drawn to this mockup -- not a second decision mechanism. Adopt and
 * Decline call the exact routes and payload shapes `ForAdoptionTab.tsx`
 * calls (`POST /api/entries/<id>/adopt|decline`); "Edit wording first" sends
 * the edited text as `body.text`, the same fallback `buildAdoptPayload`
 * (`ladderTypes.ts`) uses when a request carries no `proposed_body` to key
 * the edit into. */
import { useState } from 'react'
import { post, type Id } from '../../api'
import { formatScopeLabel, type AdoptionRequestSummary } from '../../fluid/governance/ladderTypes'
import './brainRecord.css'

export function BrainDecision({ entry, kind, text, governs, request, me, onDecided }: {
  entry: Id
  kind: string
  /** the proposed wording, offered back unedited for "Edit wording first" */
  text: string
  governs: boolean
  request: AdoptionRequestSummary
  me: Id | null
  onDecided: (said: string) => void
}) {
  const [editOpen, setEditOpen] = useState(false)
  const [editedText, setEditedText] = useState(text)
  const [because, setBecause] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scopeLabel = formatScopeLabel(request.scope, governs)

  const run = async (fn: () => Promise<void>) => {
    if (!me) { setError('Mentis could not say who you are.'); return }
    if (busy) return
    setBusy(true)
    setError(null)
    try { await fn() } catch (e) { setError((e as Error).message || String(e)) } finally { setBusy(false) }
  }

  const adopt = (withEditedWording: boolean) => void run(async () => {
    const edited = withEditedWording ? editedText.trim() : ''
    const payload: Record<string, unknown> = { attributed_to: me, because: because.trim() || request.because || 'Adopted from the record view.' }
    if (edited && edited !== text.trim()) payload.body = { text: edited }
    if (request.scope) payload.scope = request.scope
    if (request.replaces.length) payload.replaces = request.replaces.map((r) => r.id)
    await post(`/api/entries/${encodeURIComponent(entry)}/adopt`, payload)
    onDecided(`Adopted ${kind} ${entry}.`)
  })

  const decline = () => void run(async () => {
    const reason = because.trim()
    if (!reason) { setError('A reason is required to decline an adoption request.'); return }
    await post(`/api/entries/${encodeURIComponent(entry)}/decline`, { attributed_to: me, because: reason, request: request.request })
    onDecided(`Declined; ${kind} stays recorded as experience.`)
  })

  return (
    <div className="rv-decide">
      <p>Adopt this {kind}?</p>
      <div className="row">
        <button type="button" className="rv-btn go" disabled={busy} onClick={() => adopt(false)}>Adopt</button>
        <button type="button" className="rv-btn" disabled={busy} onClick={decline}>Decline</button>
        <button type="button" className="rv-btn rv-btn-quiet" disabled={busy} aria-expanded={editOpen} onClick={() => setEditOpen((o) => !o)}>Edit wording first</button>
        <span className="rv-scope">Applies to <b>{scopeLabel}</b></span>
      </div>
      {editOpen && (
        <div className="rv-edit">
          <textarea className="rv-why" rows={3} value={editedText} onChange={(e) => setEditedText(e.target.value)} aria-label="Edited wording" />
          <button type="button" className="rv-btn go" disabled={busy} onClick={() => adopt(true)}>Adopt with this wording</button>
        </div>
      )}
      <label className="rv-why-label">
        Why (optional, kept with your decision)
        <textarea className="rv-why" value={because} onChange={(e) => setBecause(e.target.value)} aria-label="Why (optional, kept with your decision)" />
      </label>
      {error && <p className="rv-error" role="alert">{error}</p>}
    </div>
  )
}
