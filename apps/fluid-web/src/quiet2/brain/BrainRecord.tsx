/* THE RECORD, READ (manage-brain round 2): full-page, opened from the Brain
 * browser, and beside a conversation, opened from a post's existing record
 * mark -- the SAME component, told apart only by `variant`. Matches
 * DESIGN-r2.md "The record, at rest" and mockups 2/3 (full), 4 (an owner
 * decision), 5 (beside), 6 (phone) under
 * `mockups/manage-brain-r2/`.
 *
 * DATA: `GET /api/ladder/items/<id>`, read the same way Governance's
 * `GovItem` reads it (`useApi`, reread on `announceAdvance`) -- not through
 * `brain/data.ts`'s hookless `fetchBrainRecord`, which exists for callers
 * with no React tree to share a read through.
 *
 * ACTS: the ⋯ menu (`BrainRecordMenu`, exported for `Surface.tsx`'s own
 * header to place beside its × on the beside variant) and the owner decision
 * (`BrainDecision.tsx`) call only routes Governance already calls --
 * `/adopt`, `/decline`, `/dispute`, `/place`, `/unplace`, `supersede`,
 * `proposeSupersession` (`surfaces/standing.ts`) -- reusing their payload
 * shapes exactly. Nothing here is a second way to do any of this.
 *
 * DEFERRED (noted, not guessed at): "Open in full" and "Show all Brain
 * records" need the Brain browser's own navigation (Workstream A, a
 * different worktree); "Propose a rule from it…" needs the authoring UI
 * DESIGN-r2.md itself defers ("Preserved but not drawn"). All three are
 * disabled with a reason rather than silently doing nothing. */
import { type ReactNode, useState } from 'react'
import { announceAdvance, post, useApi, when, type Id } from '../../api'
import {
  attemptedLabel,
  basisVerb,
  challengeResolvedLine,
  citeView,
  splitChallenges,
  whoOf,
  type CitedByRecord,
  type LadderItemDetail,
  type OutcomeSummary,
} from '../../fluid/governance/ladderTypes'
import { usePage } from '../Post'
import { postOf } from '../real'
import { repairText } from '../text'
import { proposeSupersession, supersede } from '../../surfaces/standing'
import { BrainDecision } from './BrainDecision'
import { standingPillLabel, verdictLabel } from './data'
import { actWords, challengedFlagWords, countWords, evidenceLabel, proposedSentence, standingDot, standingSentence, sublineWords, toggleFold } from './recordWords'
import './brainRecord.css'

const cap = (s: string): string => (s ? s[0].toUpperCase() + s.slice(1).replace(/[-_]/g, ' ') : s)

function normalizeOutcomes(raw: LadderItemDetail['outcomes'] | undefined): OutcomeSummary[] {
  if (!raw) return []
  if (Array.isArray(raw)) return raw
  return raw.all ?? raw.latest ?? []
}
function normalizeCitedBy(raw: LadderItemDetail['cited_by'] | undefined): CitedByRecord[] {
  if (!raw || typeof raw === 'number') return []
  return raw
}

const SECTIONS = ['stands', 'gone', 'challenges', 'related', 'history'] as const
type Section = typeof SECTIONS[number]

/* -- the ⋯ menu: every other act ------------------------------------------- */

interface Placement { where: Id; name: string | null; whole_brain: boolean; persona?: boolean; reason: string | null; at: number | null }

/** The record's ⋯ menu, usable either inside `BrainRecord`'s own header
 *  (full variant) or beside `Surface.tsx`'s generic header (beside variant,
 *  where it sits next to the existing ×). */
export function BrainRecordMenu({ entry, onChanged }: {
  entry: Id
  onChanged: () => void
}) {
  const page = usePage()
  const me = page.me
  const [open, setOpen] = useState(false)
  const [act, setAct] = useState<'challenge' | 'revise' | 'replace' | 'place' | null>(null)
  const [reason, setReason] = useState('')
  const [evidence, setEvidence] = useState('')
  const [replacement, setReplacement] = useState('')
  const [wording, setWording] = useState('')
  const [where, setWhere] = useState('')
  const [unplacing, setUnplacing] = useState<Placement | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [said, setSaid] = useState<string | null>(null)

  const placeInfo = useApi<{ governance_actions?: { placements?: Placement[] } }>(
    act === 'place' ? `/api/entries/${encodeURIComponent(entry)}` : null,
  )

  const openAct = (a: typeof act) => { setAct(a); setReason(''); setEvidence(''); setReplacement(''); setWording(''); setWhere(''); setUnplacing(null); setError(null) }
  const close = () => { setOpen(false); setAct(null); setError(null) }
  const run = async (fn: () => Promise<void>) => {
    if (!me) { setError('Mentis could not say who you are.'); return }
    if (busy) return
    setBusy(true)
    setError(null)
    try { await fn(); onChanged() } catch (e) { setError((e as Error).message || String(e)) } finally { setBusy(false) }
  }

  const copyLink = () => {
    try { void navigator.clipboard?.writeText(entry) } catch { /* clipboard may be unavailable in a non-secure context */ }
    setSaid(`Copied ${entry}.`)
    setTimeout(() => setSaid(null), 2000)
    setOpen(false)
  }

  return (
    <div className="rv-menu-wrap">
      <button type="button" className="rv-head-menu" aria-haspopup="menu" aria-expanded={open} aria-label="More on this record" onClick={() => setOpen((o) => !o)}>⋯</button>
      {said && <span className="rv-menu-said" role="status">{said}</span>}
      {open && (
        <div className="rv-menu" role="menu">
          {!act && (
            <>
              <button type="button" role="menuitem" onClick={() => openAct('challenge')}>Challenge…</button>
              <button type="button" role="menuitem" disabled title="Authoring a new rule from this is not built yet here (DESIGN-r2.md, &quot;Preserved but not drawn&quot;)">Propose a rule from it…</button>
              <button type="button" role="menuitem" onClick={() => openAct('revise')}>Propose a revision…</button>
              <hr />
              <button type="button" role="menuitem" disabled title="Deferred to the Brain browser's own open action (a separate worktree)">Open in full</button>
              <button type="button" role="menuitem" disabled title="Deferred to the Brain browser (a separate worktree)">Show all Brain records</button>
              <button type="button" role="menuitem" onClick={copyLink}>Copy link</button>
              <hr />
              <button type="button" role="menuitem" className="sub" onClick={() => openAct('replace')}>Replace with another…</button>
              <button type="button" role="menuitem" className="sub" onClick={() => openAct('place')}>Where it applies…</button>
            </>
          )}
          {act === 'challenge' && (
            <div className="rv-menu-form">
              <label>Why<textarea value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Why this is challenged" /></label>
              <label>Evidence entry IDs (optional)<input value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="e.g. ent-63b40a119d04" /></label>
              {error && <p className="rv-error" role="alert">{error}</p>}
              <div className="row">
                <button type="button" disabled={busy || !reason.trim()} onClick={() => void run(async () => {
                  const payload: Record<string, unknown> = { attributed_to: me, because: reason.trim() }
                  const ev = evidence.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean)
                  if (ev.length) payload.evidence = ev
                  await post(`/api/entries/${encodeURIComponent(entry)}/dispute`, payload)
                  setSaid('Challenge recorded.'); close()
                })}>{busy ? 'Recording…' : 'Record challenge'}</button>
                <button type="button" onClick={close}>Cancel</button>
              </div>
            </div>
          )}
          {act === 'revise' && (
            <div className="rv-menu-form">
              <label>New wording<textarea value={wording} onChange={(e) => setWording(e.target.value)} aria-label="New wording" /></label>
              <label>Why<textarea value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Why this revision" /></label>
              <p className="rv-effect">Writes a candidate beside this one. Nothing is replaced until it is established.</p>
              {error && <p className="rv-error" role="alert">{error}</p>}
              <div className="row">
                <button type="button" disabled={busy || !wording.trim() || !reason.trim()} onClick={() => void run(async () => {
                  await proposeSupersession(entry, me, { body: { text: wording.trim() }, because: reason.trim() })
                  setSaid('Revision proposed; the current wording still stands until it is established.'); close()
                })}>{busy ? 'Proposing…' : 'Propose revision'}</button>
                <button type="button" onClick={close}>Cancel</button>
              </div>
            </div>
          )}
          {act === 'replace' && (
            <div className="rv-menu-form">
              <label>Existing successor reference<input value={replacement} onChange={(e) => setReplacement(e.target.value)} placeholder="ent-…" /></label>
              <label>Why<textarea value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Why this replacement" /></label>
              <p className="rv-effect">The successor must already stand, be the same Kind, and cover every existing placement.</p>
              {error && <p className="rv-error" role="alert">{error}</p>}
              <div className="row">
                <button type="button" disabled={busy || !replacement.trim() || !reason.trim()} onClick={() => void run(async () => {
                  await supersede(entry, replacement.trim(), me, reason.trim())
                  setSaid('Replaced; this record is now read-only.'); close()
                })}>{busy ? 'Recording…' : 'Replace now'}</button>
                <button type="button" onClick={close}>Cancel</button>
              </div>
            </div>
          )}
          {act === 'place' && (
            <div className="rv-menu-form">
              {(placeInfo.data?.governance_actions?.placements ?? []).map((p) => (
                <div key={p.where} className="rv-place-row">
                  <span>{p.whole_brain ? 'Whole Brain' : (p.name ?? p.where)}</span>
                  <button type="button" onClick={() => { setUnplacing(p); setReason('') }}>End…</button>
                </div>
              ))}
              {unplacing ? (
                <>
                  <p className="rv-effect">End placement in {unplacing.whole_brain ? 'the Whole Brain' : (unplacing.name ?? unplacing.where)}?</p>
                  <label>Why (required)<textarea value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Why end this placement" /></label>
                  {error && <p className="rv-error" role="alert">{error}</p>}
                  <div className="row">
                    <button type="button" disabled={busy || !reason.trim()} onClick={() => void run(async () => {
                      await post(`/api/entries/${encodeURIComponent(entry)}/unplace`, unplacing.whole_brain
                        ? { attributed_to: me, whole_brain: true, because: reason.trim() }
                        : { attributed_to: me, where: unplacing.where, because: reason.trim() })
                      setSaid('Placement ended.'); setUnplacing(null); placeInfo.reload()
                    })}>{busy ? 'Ending…' : 'End placement'}</button>
                    <button type="button" onClick={() => setUnplacing(null)}>Cancel</button>
                  </div>
                </>
              ) : (
                <>
                  <label>Place where<input value={where} onChange={(e) => setWhere(e.target.value)} placeholder="whole-brain, or a conversation id" aria-label="Place where" /></label>
                  <label>Why (required)<textarea value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Why this placement" /></label>
                  {error && <p className="rv-error" role="alert">{error}</p>}
                  <div className="row">
                    <button type="button" disabled={busy || !where.trim() || !reason.trim()} onClick={() => void run(async () => {
                      await post(`/api/entries/${encodeURIComponent(entry)}/place`, where.trim() === 'whole-brain'
                        ? { attributed_to: me, whole_brain: true, because: reason.trim() }
                        : { attributed_to: me, where: where.trim(), because: reason.trim() })
                      setSaid('Placed.'); setWhere(''); placeInfo.reload()
                    })}>{busy ? 'Placing…' : 'Place'}</button>
                    <button type="button" onClick={close}>Cancel</button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* -- one collapsible section ------------------------------------------------ */

function Fold({ label, summary, open, onToggle, children }: {
  label: string; summary: string | null; open: boolean; onToggle: () => void; children: ReactNode
}) {
  return (
    <div className={'rv-d' + (open ? ' open' : '')}>
      <button type="button" aria-expanded={open} onClick={onToggle}>
        <span className="c" aria-hidden="true">{open ? '▾' : '▸'}</span>{label}
        {summary != null && <span className="s">{summary}</span>}
      </button>
      {open && <div className="rv-body">{children}</div>}
    </div>
  )
}

/* -- the record's body: kind, words, standing, subline, sections ----------- */

function BrainRecordBody({ d, variant, me, onChanged, onSaid }: {
  d: LadderItemDetail; variant: 'full' | 'beside'; me: Id | null
  onChanged: () => void; onSaid: (said: string) => void
}) {
  const page = usePage()
  const [openSections, setOpenSections] = useState<Set<Section>>(() => new Set())
  const toggle = (s: Section) => setOpenSections((o) => toggleFold(o, s))

  const kind = d.kind || 'record'
  const governs = !!d.governs
  const status = d.status
  const outcomes = normalizeOutcomes(d.outcomes)
  const citedList = normalizeCitedBy(d.cited_by)
  const citedCount = typeof d.cited_by === 'number' ? d.cited_by : (d.usage?.cited ?? citedList.length)
  const { open: openCh, resolved: resolvedCh } = splitChallenges(d.challenges)
  const up = (d.lineage?.up ?? []).filter((n) => (n.depth ?? 1) === 1)
  const down = (d.lineage?.down ?? []).filter((n) => (n.depth ?? 1) === 1)
  const openRequest = (d.adoption?.requests ?? []).find((r) => !r.closed) ?? null
  const needsDecision = status === 'adoption_requested' && !!openRequest
  const sentence = needsDecision
    ? proposedSentence(openRequest!.by_alias, openRequest!.by)
    : standingSentence(kind, status, governs)
  const scopeLabel = d.adoption?.adopted?.scope || null
  const sub = sublineWords({
    status, governs,
    adoptedBy: d.adoption?.adopted?.by, adoptedAt: d.adoption?.adopted?.at,
    scopeLabel,
    recordedBy: d.recorded_by?.alias, recordedAt: d.recorded_at,
  })
  const words = repairText((d.text || '').trim())
  const delivered = d.usage?.delivered ?? d.delivered?.length ?? d.delivered_to ?? 0

  return (
    <div className={'rv rv-' + variant}>
      <p className="rv-kind">{cap(kind)}{status === 'adoption_requested' ? ' · proposed' : ''}</p>
      <p className="rv-words">{words || <i>No words recorded</i>}</p>
      <p className="rv-state">
        <span className={'dot' + (standingDot(status) ? ' ' + standingDot(status) : '')} aria-hidden="true" />
        <span>
          <span className={'q2e-status q2e-status-' + status} title="Ladder status">{standingPillLabel(status, kind, governs)}</span>
          {sentence}
        </span>
      </p>
      <p className="rv-sub">{sub}</p>
      {/* "challenged: a separate quiet flag, never a status" (DESIGN-r2.md) --
          said beside the standing line, not folded into the status pill. */}
      {challengedFlagWords(d.challenged) && <p className="rv-flag">{challengedFlagWords(d.challenged)}</p>}

      {needsDecision && (
        <BrainDecision entry={d.id} kind={kind} text={d.text} governs={governs} request={openRequest!} me={me}
          onDecided={(said) => { onChanged(); onSaid(said) }} />
      )}

      <div className="rv-more">
        <Fold label="Why it stands" summary={countWords(d.basis.length, 'source')} open={openSections.has('stands')} onToggle={() => toggle('stands')}>
          {d.basis.length === 0 ? <p className="q2m-faint">No basis recorded.</p> : d.basis.map((b, i) => {
            const c = citeView(b)
            return (
              <p key={b.ref + ':' + i} className="q">
                {c.quote ? `“${c.quote}”` : c.link}
                <span className="m">{basisVerb(b.relation)}{b.label && b.label !== c.link ? ` · ${b.label}` : ''}</span>
              </p>
            )
          })}
        </Fold>

        <Fold label="How it has gone" summary={countWords(outcomes.length, 'outcome')} open={openSections.has('gone')} onToggle={() => toggle('gone')}>
          {outcomes.length === 0 ? <p className="q2m-faint">No outcomes recorded yet.</p> : (
            <>
              {outcomes.map((o) => {
                const label = verdictLabel(o.result ?? '')
                const tone = o.result === 'worked' ? 'rv-helped' : o.result === 'failed' ? 'rv-hurt' : 'rv-unclear'
                /* the Turn this outcome was observed in: a real evidence
                   link where it is already loaded (mockup
                   3-record-details.html: "#5, round 3 check"), else its own
                   number/short id, same gating `RecordsView`'s "Show the
                   post it is from" already uses -- never the verdict word
                   alone. */
                const ctxPost = o.in_context ? postOf(o.in_context) : undefined
                const evidence = evidenceLabel(ctxPost?.number ?? null, o.in_context)
                return (
                  <p key={o.id}>
                    <b className={tone}>{label}</b> <span className="rv-verdict">{o.result}</span>{attemptedLabel(o.attempted)}
                    {o.text ? ` — ${repairText(o.text)}` : ''}
                    <span className="m">
                      Learning evaluation{o.recorded_at ? ` · ${when(o.recorded_at)}` : ''}
                      {evidence && (
                        <>
                          {' · '}
                          {ctxPost
                            ? <button type="button" className="rv-link" onClick={() => page.onBeside?.({ kind: 'post', id: o.in_context! })}>{evidence}</button>
                            : evidence}
                        </>
                      )}
                    </span>
                  </p>
                )
              })}
              <p className="m" style={{ margin: 0 }}>
                Given to {delivered} {delivered === 1 ? 'run' : 'runs'}. Being given a {kind} doesn't mean a run used it; these outcomes say where it was used and how it went.
              </p>
            </>
          )}
        </Fold>

        <Fold label="Challenges" summary={openCh.length === 0 ? 'none' : countWords(openCh.length, 'open challenge', 'open challenges')} open={openSections.has('challenges')} onToggle={() => toggle('challenges')}>
          {openCh.length === 0 && resolvedCh.length === 0 ? <p className="q2m-faint">No challenges.</p> : (
            <>
              {openCh.map((c) => <p key={c.link}><b>Open</b> · {whoOf(c)}: {repairText(c.because)}</p>)}
              {resolvedCh.map((c) => <p key={c.link} className="q2m-faint">{whoOf(c)}: {repairText(c.because)} · {challengeResolvedLine(c)}</p>)}
            </>
          )}
        </Fold>

        <Fold label="Related" summary={countWords(up.length + down.length, 'related record')} open={openSections.has('related')} onToggle={() => toggle('related')}>
          {up.length === 0 && down.length === 0 ? <p className="q2m-faint">Nothing else rests on this, or that this rests on.</p> : (
            <ul>
              {up.map((n) => <li key={n.id}>{basisVerb(n.relation)} {n.label}</li>)}
              {down.map((n) => <li key={n.id}>{basisVerb(n.relation)}: {n.label}{n.result ? ` (${verdictLabel(n.result)})` : ''}</li>)}
            </ul>
          )}
          {citedCount > 0 && <p className="m">{citedCount} later {citedCount === 1 ? 'record cites' : 'records cite'} it.</p>}
        </Fold>

        <Fold label="History" summary={null} open={openSections.has('history')} onToggle={() => toggle('history')}>
          {(d.history ?? []).length === 0 ? <p className="q2m-faint">No history recorded.</p> : (
            <ul className="rv-hist">
              {(d.history ?? []).map((h, i) => (
                <li key={i}>
                  {/* the server sends `by_alias` too (investigation.md §6.2);
                      `HistoryRecord` (ladderTypes.ts) does not declare it
                      (§6.4's caveat), so `whoOf` reads it structurally */}
                  <b>{actWords(h.act)}</b> by {whoOf(h, 'unattributed')}{h.at ? ` · ${when(h.at)}` : ''}{h.because ? ` — “${repairText(h.because)}”` : ''}
                </li>
              ))}
            </ul>
          )}
        </Fold>
      </div>
    </div>
  )
}

/* -- the component: reads the record, then draws full or beside ------------ */

export default function BrainRecord({ entry, variant, post: postId, backLabel, onBack }: {
  entry: Id
  variant: 'full' | 'beside'
  /** the post this record was opened from, where it was -- used only to
   *  word the full variant's own Back button; the beside variant's header
   *  and × are `Surface.tsx`'s, which already has the post and conversation */
  post?: Id | null
  /** full variant's own Back words; defaults to the originating post's title */
  backLabel?: string | null
  onBack?: () => void
}) {
  const page = usePage()
  const me = page.me
  const read = useApi<LadderItemDetail>('/api/ladder/items/' + encodeURIComponent(entry))
  const d = read.data
  const changed = () => { read.reload(); announceAdvance() }

  const originPost = postId ? postOf(postId) : undefined
  const words = originPost ? (originPost.title || (originPost.number ? `#${originPost.number}` : 'the post')) : 'Brain'
  const back = backLabel ?? words
  void back; void onBack
  /* `Surface.tsx`'s own pane header (back/id/menu/close) is the ONLY chrome
   * for both variants -- an inner header here duplicated it (review finding,
   * manage-brain-record workstream, fixed at integration). */

  return (
    <>
      {read.error && !d && (
        <div className="rv">
          <p className="q2m-faint" role="alert">Could not read this record: {read.error} <button type="button" className="q2e-link" onClick={read.reload}>Retry</button></p>
        </div>
      )}
      {!d && !read.error && <div className="rv"><p className="q2m-faint" role="status">Reading…</p></div>}
      {d && (
        <BrainRecordBody d={d} variant={variant} me={me} onChanged={changed}
          onSaid={(said) => { page.say(said) }} />
      )}
    </>
  )
}
