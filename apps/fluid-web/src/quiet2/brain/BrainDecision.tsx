/* AN OWNER DECISION (mockup 4-decision.html): Adopt, Decline, or Edit wording
 * first -- exactly, never a fourth choice -- with where it applies and the
 * reason. "An owner decision appears only when the record asks one of you"
 * (DESIGN-r2.md): `BrainRecord.tsx` draws this only while an adoption
 * request is open on the record AND the reader is the Brain's owner.
 *
 * THIS IS THE ADOPTION FLOW Governance's For adoption card already is, drawn
 * to this mockup -- not a second decision mechanism. It reads the same
 * request card (`GET /api/ladder/adoption`), builds the payload with the same
 * function (`buildAdoptPayload`), and posts to the same routes
 * (`/api/entries/<id>/adopt|decline`). So an edited wording keeps every
 * other field of the proposed body, a Kind that owes a falsifier is asked
 * for one, and the scope can be changed -- as there. The server decides who
 * may adopt; this only asks. */
import { useState } from 'react'
import { announceAdvance, post, useApi, type Id } from '../../api'
import { buildAdoptPayload, computeWordDiff, formatScopeLabel, type LadderAdoptionResponse } from '../../fluid/governance/ladderTypes'
import { adoptRefusal, declineRefusal } from './logic'
import './brainRecord.css'

export function BrainDecision({ entry, kind, me, onDecided }: {
  entry: Id
  kind: string
  me: Id | null
  onDecided: (said: string) => void
}) {
  const cards = useApi<LadderAdoptionResponse>('/api/ladder/adoption')
  const convs = useApi<{ conversations: { id: Id; name: string }[] }>('/api/conversations')
  const req = cards.data?.requests.find((r) => r.entry === entry) ?? null
  const [editOpen, setEditOpen] = useState(false)
  const [editedText, setEditedText] = useState<string | null>(null)
  const [because, setBecause] = useState('')
  const [scope, setScope] = useState('')
  const [falsifier, setFalsifier] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (cards.error && !req) return <div className="rv-decide"><p role="alert">The adoption request could not be read: {cards.error} <button type="button" className="rv-link" onClick={cards.reload}>Retry</button></p></div>
  if (!req) return <div className="rv-decide"><p role="status">{cards.loading || !cards.data ? 'Reading the request…' : 'This request is no longer open.'}</p></div>

  const proposed = req.wording.proposed
  const edited = editedText ?? proposed
  const diff = req.wording.current ? computeWordDiff(req.wording.current, proposed) : null
  const run = async (fn: () => Promise<void>) => {
    if (!me) { setError('Mentis could not say who you are.'); return }
    if (busy) return
    setBusy(true)
    setError(null)
    try { await fn() } catch (e) { setError((e as Error).message || String(e)) } finally { setBusy(false) }
  }
  const adopt = (withEditedWording: boolean) => {
    const refusal = adoptRefusal(req, falsifier)
    if (refusal) { setError(refusal); return }
    void run(async () => {
      await post(`/api/entries/${encodeURIComponent(entry)}/adopt`, buildAdoptPayload(req, {
        me: me!,
        because: because.trim() || req.because || 'Adopted from the record.',
        editedText: withEditedWording ? edited : null,
        scope: scope || null,
        falsifier: req.expects_falsifier ? falsifier : null,
      }))
      announceAdvance()
      onDecided(`Adopted. The ${kind} is in effect.`)
    })
  }
  const decline = () => {
    const refusal = declineRefusal(because)
    if (refusal) { setError(refusal); return }
    void run(async () => {
      await post(`/api/entries/${encodeURIComponent(entry)}/decline`, { attributed_to: me, because: because.trim(), request: req.request })
      announceAdvance()
      onDecided(`Declined. The ${kind} stays recorded as experience.`)
    })
  }

  return (
    <div className="rv-decide" role="group" aria-label="Your decision">
      <p>Adopt this {kind.replace(/[-_]/g, ' ')}?</p>
      {req.replaces.length > 0 && (
        <p className="rv-decide-note">
          It would replace {req.replaces.length === 1 ? 'the version in effect' : `${req.replaces.length} records in effect`}
          {diff && diff.hasDiff ? <>: <span className="rv-diff">{diff.prefix}{diff.removed && <del>{diff.removed}</del>}{diff.added && <ins>{diff.added}</ins>}{diff.suffix}</span></> : '.'}
        </p>
      )}
      <div className="row">
        <button type="button" className="rv-btn go" disabled={busy} onClick={() => adopt(false)}>Adopt</button>
        <button type="button" className="rv-btn" disabled={busy} onClick={decline}>Decline</button>
        <button type="button" className="rv-btn rv-btn-quiet" disabled={busy} aria-expanded={editOpen} onClick={() => setEditOpen((o) => !o)}>Edit wording first</button>
        <label className="rv-scope">Applies to{' '}
          <select aria-label="Where it applies" value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="">{formatScopeLabel(req.scope, req.governs)}</option>
            <option value="whole_brain">All conversations (Brain-wide)</option>
            <option value="when_named">Only when named</option>
            {(convs.data?.conversations ?? []).map((c) => <option key={c.id} value={c.id}>Conversation: {c.name}</option>)}
          </select>
        </label>
      </div>
      {editOpen && (
        <div className="rv-edit">
          <textarea className="rv-why" rows={4} value={edited} onChange={(e) => setEditedText(e.target.value)} aria-label="Edited wording" />
          <button type="button" className="rv-btn go" disabled={busy || !edited.trim()} onClick={() => adopt(true)}>Adopt with this wording</button>
        </div>
      )}
      {req.expects_falsifier && (
        <label className="rv-why-label">
          What would show it wrong (needed to adopt a {req.kind})
          <textarea className="rv-why" value={falsifier} onChange={(e) => setFalsifier(e.target.value)} aria-label="Falsifier" />
        </label>
      )}
      <label className="rv-why-label">
        Why (kept with your decision; needed to decline)
        <textarea className="rv-why" value={because} onChange={(e) => setBecause(e.target.value)} aria-label="Why, kept with your decision" />
      </label>
      {error && <p className="rv-error" role="alert">{error}</p>}
    </div>
  )
}
