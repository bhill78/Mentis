/* THE RECORD, READ (Manage Brain in Quiet Chat): in the main reading area,
 * opened from the Brain browser, and beside a conversation, opened from a
 * post's record mark -- the SAME component, told apart only by `variant`.
 * DESIGN-r2.md "The record, at rest": the Kind, the words, one line that says
 * whether it is in effect, one small line of who and when, and everything
 * else folded away until asked for.
 *
 * DATA: `GET /api/ladder/items/<id>` through the one normaliser
 * (`data.ts`, `mapBrainDetail`); re-read when the record moves.
 *
 * ACTS: nothing here is a second way to do anything.
 *  - The owner's decision is `BrainDecision` (the For adoption card's own
 *    routes and payload).
 *  - Revise, Establish, Replace, Place, End placement, Set aside, Delete and
 *    Preview are `useRecordActs` (`surfaces/governance/R2Record.tsx`): the
 *    same forms and dialogs Governance draws, offered exactly when the
 *    server's `governance_actions` says this reader may, listed here in the
 *    ⋯ menu instead of a button row.
 *  - Challenge, Withdraw, Set aside (per challenge) and Request adoption are
 *    the Ladder's own routes, with the payloads Governance's item view sends.
 * The server decides every act whatever is offered. */
import { type ReactNode, useEffect, useRef, useState } from 'react'
import { announceAdvance, post, useApi, when, type Id } from '../../api'
import { artifactUrl, attemptedLabel, basisVerb, citeView, isArtifactRef } from '../../fluid/governance/ladderTypes'
import { useRecordActs } from '../../surfaces/governance/R2Record'
import type { KindAuthoring } from '../../surfaces/governance/r2Model'
import { usePage } from '../Post'
import { repairText } from '../text'
import { BrainDecision } from './BrainDecision'
import { useBeat } from './beat'
import { fetchBrainRecord, isVerdict, recordUrl, standingPillLabel, verdictLabel, type BrainChallenge, type BrainLineageNode, type BrainRecordDetail, type Where } from './data'
import { useBrainNav } from './nav'
import { actWords, challengedFlagWords, countWords, standingDot, stripAt, sublineWords, tierWords, toggleFold, usageWords } from './recordWords'
import './brainRecord.css'
import '../../surfaces/governance/ActDialogs.css'

const cap = (s: string): string => (s ? s[0].toUpperCase() + s.slice(1).replace(/[-_]/g, ' ') : s)
const short = (s: string, n = 140): string => { const t = repairText(s).replace(/\s+/g, ' ').trim(); return t.length > n ? t.slice(0, n - 1).trimEnd() + '…' : t }

const SECTIONS = ['stands', 'details', 'gone', 'challenges', 'related', 'applies', 'history'] as const
type Section = typeof SECTIONS[number]

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

/* -- links: to a post, to another record, to held bytes --------------------- */

function PostLink({ where, children }: { where: Where | null; children?: ReactNode }) {
  const nav = useBrainNav()
  if (!where) return <>{children}</>
  const words = children ?? <>{where.conversation_name ? short(where.conversation_name, 48) : 'a conversation'}{where.number ? `, #${where.number}` : ''}</>
  return <button type="button" className="rv-link" title="Go to this post" onClick={() => nav.goToPost(where.conversation, where.turn)}>{words}</button>
}

function RecordLink({ id, children }: { id: string; children: ReactNode }) {
  const nav = useBrainNav()
  return <button type="button" className="rv-link" title={`Open this record (${id})`} onClick={() => nav.openRecord(id)}>{children}</button>
}

/** A lineage node as a link: a post is gone to, held bytes open, anything
 *  else is a record read here. */
function NodeLink({ node }: { node: BrainLineageNode }) {
  const words = short(node.label || node.id, 120)
  if (isArtifactRef(node.id)) return <a className="rv-link" href={artifactUrl(node.id)} target="_blank" rel="noreferrer">{words}</a>
  if (node.kind === 'contribution') return node.where ? <PostLink where={node.where}>{words}</PostLink> : <>{words}</>
  return <RecordLink id={node.id}>{words}</RecordLink>
}

/* -- the ⋯ menu ------------------------------------------------------------- */

interface MenuItem { key: string; label: string; note?: string; quiet?: boolean; run: () => void }

function RecordMenu({ groups, label }: { groups: MenuItem[][]; label: string }) {
  const [open, setOpen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const button = useRef<HTMLButtonElement>(null)
  /* an outside press closes it; Escape closes it and gives focus back */
  useEffect(() => {
    if (!open) return
    const out = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('pointerdown', out, true)
    requestAnimationFrame(() => wrap.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus())
    return () => document.removeEventListener('pointerdown', out, true)
  }, [open])
  const shown = groups.filter((g) => g.length)
  const key = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); setOpen(false); button.current?.focus(); return }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const items = [...(wrap.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])]
    const at = items.indexOf(document.activeElement as HTMLElement)
    items[(at + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]?.focus()
  }
  return (
    <div className="rv-menu-wrap" ref={wrap} onKeyDown={open ? key : undefined}>
      <button ref={button} type="button" className="rv-head-menu" aria-haspopup="menu" aria-expanded={open} aria-label={label} title={label} onClick={() => setOpen((o) => !o)}>⋯</button>
      {open && (
        <div className="rv-menu" role="menu" aria-label={label}>
          {shown.map((group, i) => (
            <div key={i} className="rv-menu-group">
              {i > 0 && <hr />}
              {group.map((it) => (
                <button key={it.key} type="button" role="menuitem" className={it.quiet ? 'sub' : undefined}
                  onClick={() => { setOpen(false); button.current?.focus(); it.run() }}>
                  {it.label}{it.note && <small>{it.note}</small>}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* -- the Ladder's own small acts, as one inline form ------------------------ */

type LadderAct =
  | { act: 'challenge' }
  | { act: 'request-adoption' }
  | { act: 'withdraw'; challenge: BrainChallenge }
  | { act: 'set-aside'; challenge: BrainChallenge }

function LadderActForm({ entry, doing, me, onDone, onCancel }: {
  entry: Id; doing: LadderAct; me: Id | null; onDone: (said: string) => void; onCancel: () => void
}) {
  const [reason, setReason] = useState('')
  const [evidence, setEvidence] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const first = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { first.current?.focus() }, [])
  const words = doing.act === 'challenge' ? { title: 'Challenge this record', why: 'What is wrong with it', go: 'Record challenge', effect: 'A challenge is recorded beside it. Its standing does not change.' }
    : doing.act === 'request-adoption' ? { title: 'Ask the owner to adopt it', why: 'Why it should be adopted', go: 'Request adoption', effect: 'The owner is asked. Nothing is in effect until they adopt it.' }
      : doing.act === 'withdraw' ? { title: 'Withdraw your challenge', why: 'Why you withdraw it', go: 'Withdraw challenge', effect: 'The challenge stays in the history, marked withdrawn.' }
        : { title: 'Set this challenge aside', why: 'Why it is set aside', go: 'Set aside', effect: 'The challenge stays in the history, marked set aside.' }
  const send = async () => {
    if (!me) { setError('Mentis could not say who you are.'); return }
    if (!reason.trim()) { setError('Say why first.'); return }
    setBusy(true); setError(null)
    try {
      const base = `/api/entries/${encodeURIComponent(entry)}`
      if (doing.act === 'challenge') {
        const payload: Record<string, unknown> = { attributed_to: me, because: reason.trim() }
        const ev = evidence.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean)
        if (ev.length) payload.evidence = ev
        await post(`${base}/dispute`, payload)
        onDone('Challenge recorded.')
      } else if (doing.act === 'request-adoption') {
        await post(`${base}/request-adoption`, { attributed_to: me, because: reason.trim() })
        onDone('Adoption requested. The owner is asked.')
      } else if (doing.act === 'withdraw') {
        await post(`${base}/withdraw-challenge`, { attributed_to: me, dispute: doing.challenge.link, because: reason.trim() })
        onDone('Challenge withdrawn.')
      } else {
        await post(`${base}/set-aside`, { attributed_to: me, dispute: doing.challenge.link, because: reason.trim() })
        onDone('Challenge set aside.')
      }
    } catch (e) { setError((e as Error).message || String(e)) } finally { setBusy(false) }
  }
  return (
    <section className="rv-act" role="group" aria-label={words.title}>
      <h3>{words.title}</h3>
      {'challenge' in doing && <p className="rv-effect">“{short(doing.challenge.because, 160)}”</p>}
      <label>{words.why}<textarea ref={first} value={reason} onChange={(e) => setReason(e.target.value)} aria-label={words.why} /></label>
      {doing.act === 'challenge' && <label>Evidence: record ids, if any<input value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="ent-…" aria-label="Evidence record ids" /></label>}
      <p className="rv-effect">{words.effect}</p>
      {error && <p className="rv-error" role="alert">{error}</p>}
      <div className="row">
        <button type="button" className="rv-btn go" disabled={busy} onClick={() => void send()}>{busy ? 'Recording…' : words.go}</button>
        <button type="button" className="rv-btn" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </section>
  )
}

/* -- the record's body ------------------------------------------------------ */

function BrainRecordBody({ d, variant, me, onChanged }: {
  d: BrainRecordDetail; variant: 'full' | 'beside'; me: Id | null; onChanged: () => void
}) {
  const nav = useBrainNav()
  const [openSections, setOpenSections] = useState<Set<Section>>(() => new Set())
  const toggle = (s: Section) => setOpenSections((o) => toggleFold(o, s))
  const [ladderAct, setLadderAct] = useState<LadderAct | null>(null)
  const [said, setSaid] = useState<string | null>(null)
  const [allWords, setAllWords] = useState(false)
  const [allRuns, setAllRuns] = useState(false)
  const panel = useRef<HTMLDivElement>(null)
  const definitions = useApi<{ kinds: KindAuthoring[] }>(nav.canWrite ? '/api/governance/authoring' : null)
  const changed = (words?: string | null) => { if (words) setSaid(words); onChanged() }
  /* THE EXISTING RECORD ACTS, with their own forms and the server's word on
     which are allowed: listed in the ⋯ menu, drawn in the panel below */
  const r = useRecordActs({
    id: d.id, conversation: null, me: nav.canWrite ? me : null, kinds: definitions.data?.kinds ?? [], names: {},
    inline: true, oneRow: true,
    onInspect: (id) => { if (id !== d.id) nav.openRecord(id) }, onPreview: () => nav.preview?.(d.id), onChanged: () => changed(null),
  })
  /* an act opened from the menu is brought into view, where it is drawn */
  const acting = r.acting ?? (ladderAct ? ladderAct.act : null)
  useEffect(() => { if (acting) panel.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [acting])

  const kind = d.kind || 'record'
  const status = d.status
  const isOwner = !!me && !!d.owner && me === d.owner
  const openRequest = d.adoption.requests.find((q) => !q.closed) ?? null
  const needsDecision = status === 'adoption_requested' && !!openRequest
  const openCh = d.challenges.filter((c) => c.resolution === 'open')
  const resolvedCh = d.challenges.filter((c) => c.resolution !== 'open')
  const up = d.lineage.up.filter((n) => n.depth === 1)
  const down = d.lineage.down.filter((n) => n.depth === 1)
  const sub = sublineWords({
    status, governs: d.governs,
    adoptedBy: d.adoption.adopted?.by_alias ?? d.adoption.adopted?.by, adoptedAt: d.adoption.adopted?.at,
    scopeLabel: d.adoption.adopted?.scopeLabel ?? null,
    recordedBy: d.by, recordedAt: d.recordedAt,
  })
  const words = repairText(d.text.trim())
  const long = words.length > 900
  const usage = d.usage
  const delivered = usage?.delivered ?? d.deliveredTotal
  const runs = allRuns ? d.delivered : d.delivered.slice(0, 5)
  const related = up.length + down.length + d.supersededBy.length + d.citedTotal
  const standsLabel = status === 'adopted' ? 'Why it stands' : status === 'adoption_requested' ? 'Why it was proposed' : 'What it rests on'

  const copyLink = () => {
    const url = recordUrl(d.id)
    const done = () => setSaid('Link copied.')
    try { void navigator.clipboard.writeText(url).then(done, () => setSaid(url)) } catch { setSaid(url) }
  }
  const canAct = nav.canWrite && !!me
  const menu: MenuItem[][] = [
    [
      ...(canAct ? [{ key: 'challenge', label: 'Challenge…', run: () => { r.cancel(); setLadderAct({ act: 'challenge' }) } }] : []),
      ...(canAct && d.adoptable && (status === 'recorded' || status === 'declined')
        ? [{ key: 'request', label: 'Request adoption…', run: () => { r.cancel(); setLadderAct({ act: 'request-adoption' }) } }] : []),
      ...(canAct && nav.newRecord && !d.governs ? [{ key: 'rule', label: 'Propose a rule from it…', run: () => nav.newRecord!('rule', d.id) }] : []),
      ...r.acts.filter((a) => a.key !== 'dispute' && !a.key.startsWith('set-aside:') && !a.key.startsWith('unplace:') && a.key !== 'place' && a.key !== 'replace' && a.key !== 'delete')
        .map((a) => ({ key: a.key, label: a.label, note: a.note, run: () => { setLadderAct(null); a.run() } })),
    ],
    [
      ...(variant === 'beside' && nav.openFull ? [{ key: 'full', label: 'Open in full', run: () => nav.openFull!(d.id) }] : []),
      ...(nav.openBrowser ? [{ key: 'all', label: 'Show all Brain records', run: () => nav.openBrowser!() }] : []),
      ...(d.originating.conversation && d.originating.turn ? [{ key: 'origin', label: 'Go to the post it was recorded in', run: () => nav.goToPost(d.originating.conversation!, d.originating.turn!) }] : []),
      { key: 'copy', label: 'Copy link', run: copyLink },
    ],
    r.acts.filter((a) => a.key === 'replace' || a.key === 'place' || a.key.startsWith('unplace:') || a.key === 'delete')
      .map((a) => ({ key: a.key, label: a.label, note: a.note, quiet: true, run: () => { setLadderAct(null); if (a.key === 'place' || a.key.startsWith('unplace:')) setOpenSections((o) => new Set(o).add('applies')); a.run() } })),
  ]

  return (
    <div className={'rv rv-' + variant} data-record={d.id}>
      <div className="rv-top">
        <p className="rv-kind">{cap(kind)}{status === 'adoption_requested' ? ' · proposed' : ''}</p>
        <RecordMenu groups={menu} label="More on this record" />
      </div>
      <p className={'rv-words' + (long ? ' rv-words-long' : '')}>
        {words ? (long && !allWords ? words.slice(0, 700).trimEnd() + '…' : words) : <i>No words recorded</i>}
        {long && <> <button type="button" className="rv-link" onClick={() => setAllWords((v) => !v)}>{allWords ? 'Show less' : 'Show all of it'}</button></>}
      </p>
      <p className="rv-state">
        <span className={'dot' + (standingDot(status) ? ' ' + standingDot(status) : '')} aria-hidden="true" />
        <span>
          <span className={'q2e-status q2e-status-' + status} title="Its status on the Ladder">{standingPillLabel(status, kind, d.governs)}</span>
          {d.standingPlain}.
        </span>
      </p>
      <p className="rv-sub">{sub}</p>
      {/* "challenged: a separate quiet flag, never a status" (DESIGN-r2.md) */}
      {challengedFlagWords(d.challenged) && (
        <p className="rv-flag"><button type="button" className="rv-link rv-flag-link" onClick={() => setOpenSections((o) => new Set(o).add('challenges'))}>{challengedFlagWords(d.challenged)}</button></p>
      )}
      {said && <p className="rv-said" role="status">{said}</p>}
      {r.said}{r.error}{r.proposed}

      <div ref={panel}>
        {ladderAct && (
          <LadderActForm key={ladderAct.act + ('challenge' in ladderAct ? ladderAct.challenge.link : '')} entry={d.id} doing={ladderAct} me={me}
            onCancel={() => setLadderAct(null)} onDone={(words) => { setLadderAct(null); announceAdvance(); changed(words) }} />
        )}
        {(r.form || r.dialog) && <div className="rv-act rv-act-host">{r.form}{r.dialog}</div>}
      </div>

      {needsDecision && (isOwner
        ? <BrainDecision entry={d.id} kind={kind} me={me} onDecided={(words) => changed(words)} />
        : <p className="rv-sub rv-waiting">Only the Brain’s owner can adopt or decline it.</p>)}

      <div className="rv-more">
        <Fold label={standsLabel} summary={countWords(d.basis.length, 'source')} open={openSections.has('stands')} onToggle={() => toggle('stands')}>
          {d.basis.length === 0 ? <p className="q2m-faint">No basis recorded: nothing says what it was concluded from.</p> : d.basis.map((b, i) => {
            const c = citeView({ ref: b.ref, label: b.label, cite: b.cite, excerpt: b.excerpt, artifact: b.artifact as never })
            const link = repairText(c.link)
            return (
              <p key={b.ref + ':' + i} className="q">
                {c.quote ? `“${repairText(c.quote)}”` : short(link, 220)}
                <span className="m">
                  {cap(basisVerb(b.relation))}{' '}
                  {c.artifact ? <a className="rv-link" href={artifactUrl(b.ref)} target="_blank" rel="noreferrer">{short(link, 60)}</a>
                    : b.kind === 'contribution' ? (b.where ? <PostLink where={b.where} /> : 'a post')
                      : <RecordLink id={b.ref}>{b.kind ? `this ${b.kind.replace(/[-_]/g, ' ')}` : 'this record'}</RecordLink>}
                  {c.note ? ` · ${c.note}` : ''}
                </span>
              </p>
            )
          })}
          <p className="m rv-prov">
            Recorded by {stripAt(d.by, 'an unattributed author')}
            {d.recordedBy.runtime ? ` on ${d.recordedBy.runtime}${d.recordedBy.model ? ` (${d.recordedBy.model})` : ''}` : ''}
            {d.recordedBy.personaName ? `, as ${d.recordedBy.personaName}` : ''}
            {d.recordedAt ? ` · ${when(d.recordedAt)}` : ''}
            {d.originating.conversation && d.originating.turn && <>{' · in '}<PostLink where={{ conversation: d.originating.conversation, conversation_name: d.originating.conversation_name, turn: d.originating.turn, number: d.originating.number }} /></>}
          </p>
          {/* the adoption requests and what became of them: the old item view
              was sent these and never showed them (investigation.md §3) */}
          {d.adoption.requests.map((q) => (
            <p key={q.request} className="m rv-prov">
              <b>Adoption requested</b> by {stripAt(q.by_alias || q.by, 'somebody')}{q.migrated_by_alias ? ` (carried over by ${stripAt(q.migrated_by_alias)})` : ''}{q.at ? ` · ${when(q.at)}` : ''}
              {q.because ? ` — “${short(q.because, 220)}”` : ''}
              {q.replaces.length > 0 && <>{' · would replace '}{q.replaces.map((x, i) => <span key={x.id}>{i > 0 && ', '}<RecordLink id={x.id}>{short(x.text || x.id, 60)}</RecordLink></span>)}</>}
              {' · '}{q.closed ? (q.closed_by === 'adopted' ? 'adopted' : 'declined') : 'open'}
            </p>
          ))}
          {d.adoption.declines.map((x, i) => (
            <p key={'decline' + i} className="m rv-prov"><b>Declined</b> by {stripAt(x.by_alias || x.by, 'the owner')}{x.at ? ` · ${when(x.at)}` : ''}{x.because ? ` — “${short(x.because, 220)}”` : ''}</p>
          ))}
          {d.adoption.adopted && (
            <p className="m rv-prov"><b>{d.governs ? 'Put in effect' : 'Adopted'}</b> by {stripAt(d.adoption.adopted.by_alias ?? d.adoption.adopted.by, 'the owner')}{d.adoption.adopted.at ? ` · ${when(d.adoption.adopted.at)}` : ''}{d.adoption.adopted.because ? ` — “${short(d.adoption.adopted.because, 220)}”` : ''}</p>
          )}
        </Fold>

        {(d.fields.length > 0 || d.limits) && (
          <Fold label="Details" summary={countWords(d.fields.length + (d.limits ? 1 : 0), 'field')} open={openSections.has('details')} onToggle={() => toggle('details')}>
            {d.limits && <p><span className="rv-field">Limits</span>{repairText(d.limits)}</p>}
            {d.fields.map((f) => <p key={f.name} className="rv-fieldrow"><span className="rv-field">{cap(f.name)}</span><span className="rv-fieldval">{repairText(f.value)}</span></p>)}
          </Fold>
        )}

        <Fold label="How it has gone" summary={d.outcomes.length ? countWords(d.outcomes.length, 'outcome') : delivered ? `given to ${delivered} ${delivered === 1 ? 'run' : 'runs'}` : 'not used yet'} open={openSections.has('gone')} onToggle={() => toggle('gone')}>
          {d.outcomes.length === 0 && <p className="q2m-faint">No outcomes recorded: nothing says yet how it went when it was used.</p>}
          {d.outcomes.map((o) => {
            const verdict = isVerdict(o.result)
            const tone = /^worked$/i.test(o.result.trim()) ? 'rv-helped' : /^failed$/i.test(o.result.trim()) ? 'rv-hurt' : 'rv-unclear'
            return (
              <p key={o.id}>
                {o.result && <><b className={tone}>{verdict ? verdictLabel(o.result) : cap(short(o.result, 60))}</b>{' '}</>}
                {verdict && <span className="rv-verdict" title="The verdict as it is recorded">{o.result.trim().toLowerCase()}</span>}
                {attemptedLabel(o.attempted)}
                {o.text ? ` — ${short(o.text, 400)}` : ''}
                <span className="m">
                  {verdict ? 'Learning evaluation' : 'Outcome'}{o.recorded_at ? ` · ${when(o.recorded_at)}` : ''}
                  {o.where && <>{' · '}<PostLink where={o.where} /></>}
                  {' · '}<RecordLink id={o.id}>open</RecordLink>
                </span>
              </p>
            )
          })}
          <p className="m rv-prov">{usageWords(kind, usage, d.citedTotal)}</p>
          {d.delivered.length > 0 && (
            <>
              <ul className="rv-runs">
                {runs.map((x, i) => (
                  <li key={x.execution + ':' + i}>{x.at ? when(x.at) : ''} · {stripAt(x.participant_alias, 'a run')}{x.runtime ? ` on ${x.runtime}` : ''}{tierWords(x.tier) ? ` · ${tierWords(x.tier)}` : ''}</li>
                ))}
              </ul>
              <p className="m rv-prov">
                {d.delivered.length > 5 && <button type="button" className="rv-link" onClick={() => setAllRuns((v) => !v)}>{allRuns ? 'Show fewer' : `Show the latest ${d.delivered.length}`}</button>}
                {d.deliveredTotal > d.delivered.length && <>{d.delivered.length > 5 ? ' · ' : ''}the latest {d.delivered.length} of {d.deliveredTotal} runs it was given to</>}
              </p>
            </>
          )}
        </Fold>

        <Fold label="Challenges" summary={openCh.length === 0 ? (resolvedCh.length ? `none open · ${resolvedCh.length} answered` : 'none') : countWords(openCh.length, 'open challenge', 'open challenges')} open={openSections.has('challenges')} onToggle={() => toggle('challenges')}>
          {d.challenges.length === 0 && <p className="q2m-faint">No challenges.</p>}
          {openCh.map((c) => {
            const mine = !!me && c.by === me
            return (
              <p key={c.link}>
                <b>Open</b> · {stripAt(c.by_alias || c.by, 'somebody')}: {repairText(c.because)}
                <span className="m">
                  {c.at ? when(c.at) : ''}
                  {c.evidence.map((e) => <span key={e}>{' · '}<RecordLink id={e}>evidence</RecordLink></span>)}
                  {canAct && mine && <>{' · '}<button type="button" className="rv-link" onClick={() => { r.cancel(); setLadderAct({ act: 'withdraw', challenge: c }) }}>Withdraw…</button></>}
                  {canAct && !mine && isOwner && <>{' · '}<button type="button" className="rv-link" onClick={() => { r.cancel(); setLadderAct({ act: 'set-aside', challenge: c }) }}>Set aside…</button></>}
                </span>
              </p>
            )
          })}
          {resolvedCh.map((c) => (
            <p key={c.link} className="q2m-faint">
              {stripAt(c.by_alias || c.by, 'somebody')}: {repairText(c.because)}
              <span className="m">{c.resolution === 'withdrawn' ? 'Withdrawn' : 'Set aside'}{c.answer ? ` by ${stripAt(c.answer.by_alias || c.answer.by, 'somebody')}${c.answer.at ? ` · ${when(c.answer.at)}` : ''}${c.answer.because ? ` — “${short(c.answer.because, 200)}”` : ''}` : ''}</span>
            </p>
          ))}
        </Fold>

        <Fold label="Related" summary={related ? countWords(related, 'record') : 'none'} open={openSections.has('related')} onToggle={() => toggle('related')}>
          {related === 0 && <p className="q2m-faint">Nothing else rests on this, or that this rests on.</p>}
          {d.supersededBy.map((s, i) => (
            <p key={'sup' + i}>{s.deleted ? 'Ended: it was deleted.' : <>Replaced by {s.id ? <RecordLink id={s.id}>{short(s.label || s.id, 120)}</RecordLink> : 'a later version'}</>}</p>
          ))}
          {up.length > 0 && <ul>{up.map((n) => <li key={'u' + n.id}><span className="rv-rel">{cap(basisVerb(n.relation))}</span> <NodeLink node={n} /></li>)}</ul>}
          {down.length > 0 && <ul>{down.map((n) => <li key={'d' + n.id}><span className="rv-rel">{n.relation === 'outcome-of' ? 'Outcome' : n.relation.startsWith('proposes') ? 'Proposed to replace it' : 'Concluded from it'}</span> <NodeLink node={n} />{n.result ? ` (${isVerdict(n.result) ? verdictLabel(n.result) : short(n.result, 40)})` : ''}</li>)}</ul>}
          {d.citedTotal > 0 && (
            <>
              <p className="m rv-prov">{d.citedTotal} later {d.citedTotal === 1 ? 'record cites' : 'records cite'} it{d.citedBy.length < d.citedTotal ? ` (the latest ${d.citedBy.length} shown)` : ''}:</p>
              <ul>{d.citedBy.map((c) => <li key={c.entry + c.relation}><span className="rv-rel">{cap(c.kind || 'record')}</span> <RecordLink id={c.entry}>{short(c.label || c.entry, 120)}</RecordLink>{c.by_alias ? ` · ${stripAt(c.by_alias)}` : ''}</li>)}</ul>
            </>
          )}
        </Fold>

        {(d.governs || status === 'adopted') && (
          <Fold label="Where it applies" summary={d.adoption.adopted?.scopeLabel ?? null} open={openSections.has('applies')} onToggle={() => toggle('applies')}>
            {r.placements ?? <p className="q2m-faint">{r.d ? (d.governs ? 'Placed nowhere: it reaches a run only when it is named.' : 'Adopted knowledge is the Brain’s position: agents are told it when it is relevant.') : 'Reading…'}</p>}
            {r.carries}{r.warnings}
            {r.acts.filter((a) => a.key === 'place' || a.key.startsWith('unplace:')).length > 0 && (
              <p className="m rv-prov">{r.acts.filter((a) => a.key === 'place' || a.key.startsWith('unplace:')).map((a, i) => (
                <span key={a.key}>{i > 0 && ' · '}<button type="button" className="rv-link" onClick={() => { setLadderAct(null); a.run() }}>{a.label}</button></span>
              ))}</p>
            )}
          </Fold>
        )}

        <Fold label="History" summary={d.history.length ? countWords(d.history.length, 'act') : null} open={openSections.has('history')} onToggle={() => toggle('history')}>
          {d.history.length === 0 ? <p className="q2m-faint">No history recorded.</p> : (
            <ul className="rv-hist">
              {d.history.map((h, i) => (
                <li key={i}><b>{actWords(h.act)}</b> by {stripAt(h.by_alias || h.by, 'unattributed')}{h.at ? ` · ${when(h.at)}` : ''}{h.because ? ` — “${short(h.because, 240)}”` : ''}</li>
              ))}
            </ul>
          )}
          <p className="m rv-prov"><code title="This record's identity in Mentis">{d.id}</code></p>
        </Fold>
      </div>
    </div>
  )
}

/* -- the component: reads the record, then draws it ------------------------- */

export default function BrainRecord({ entry, variant }: {
  entry: Id
  variant: 'full' | 'beside'
}) {
  const page = usePage()
  const me = page.me
  const beat = useBeat()
  const [d, setD] = useState<BrainRecordDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  useEffect(() => {
    const ctl = new AbortController()
    fetchBrainRecord(entry, ctl.signal).then((got) => { setD(got); setError(null) },
      (e: unknown) => { if (!ctl.signal.aborted) setError(e instanceof Error ? e.message : String(e)) })
    return () => ctl.abort()
  }, [entry, nonce, beat])
  /* another record asked for in the same place: the last one is not shown under its name */
  const shown = d && d.id === entry ? d : null
  return (
    <>
      {error && !shown && (
        <div className={'rv rv-' + variant}>
          <p className="q2m-faint" role="alert">Could not read this record: {error} <button type="button" className="rv-link" onClick={() => setNonce((n) => n + 1)}>Retry</button></p>
        </div>
      )}
      {!shown && !error && <div className={'rv rv-' + variant}><p className="q2m-faint" role="status">Reading…</p></div>}
      {shown && <BrainRecordBody key={shown.id} d={shown} variant={variant} me={me} onChanged={() => setNonce((n) => n + 1)} />}
    </>
  )
}
