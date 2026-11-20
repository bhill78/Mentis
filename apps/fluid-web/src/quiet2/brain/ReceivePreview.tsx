/* WHAT AN AGENT WOULD BE GIVEN: Quiet Chat's own reading of the composing
 * preview (`GET /api/context`), in place of the Fluid sheet it used to host.
 *
 * WHAT IT IS. A preview, not an inspection of anything that happened: the
 * server works out, from the Brain as it stands at this moment, everything a
 * run started here would be handed -- the Persona, the records it must
 * follow (and why each reaches it), the knowledge matched to the work, and
 * the orientation every run is sent. It starts nothing and records nothing;
 * every control here only changes the question asked of that one GET.
 *
 * HOW IT READS. A sentence saying what this is, a light row of four
 * controls, then an outline: one line per piece, grouped by why it is given
 * and where it comes from, with counts. A piece's full words open in place;
 * "Open record" goes to the record itself, by its id. Nothing the old sheet
 * showed is gone -- the words, the reason, the trailer (why it holds, who
 * recorded it, its basis, limits, outcomes, challenges) and what was left
 * out are all one press away.
 *
 * The Fluid sheet (`fluid/governance/FluidPreviewSheet.tsx`) is untouched
 * and still serves `/fluid`. The sorting and the words are `receive.ts`. */
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { qs, useApi, when, type Id } from '../../api'
import { allRows, indexBy, type GovernedAnswer, type GovernedRow } from '../../surfaces/governance/InUseContext'
import { kindWords } from './logic'
import {
  countItems, engineReason, firstSentence, kindOf, outline, plural, trailerLines, withheldReason,
  type OutlineItem, type ReceiveAnswer,
} from './receive'
import './receive.css'

interface PersonaRow { persona: string; name: string; stands: boolean }

const STOPS = 'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [href], [tabindex]:not([tabindex="-1"])'

/** `/api/context` for this selection. Records named for the run go as
 *  `behavioural`, once each: that is the list the server reads for records
 *  named by reference (`previewContext.ts`). Null: nothing to ask yet. */
export function receivePath(sel: { conversation: Id | null; participant: Id | null; persona: Id | null; named: Id[]; work: string }): string | null {
  const work = sel.work.trim()
  if (!sel.conversation && !sel.participant && !sel.persona && !work && sel.named.length === 0) return null
  const p = new URLSearchParams(qs({ conversation: sel.conversation, participant: sel.participant, persona: sel.persona, work }).replace(/^\?/, ''))
  for (const id of sel.named) p.append('behavioural', id)
  return '/api/context?' + p.toString()
}

/** The Persona that stands now for one that has since been replaced. */
function standingPersona(persona: string, index: Record<string, GovernedRow>): string {
  let at: string | null = persona || null
  const seen = new Set<string>()
  while (at && !seen.has(at)) {
    seen.add(at)
    const row: GovernedRow | undefined = index[at]
    const next: string | undefined = row?.superseded_by?.[row.superseded_by.length - 1]
    if (!next) return row?.state === 'stands' ? at : ''
    at = next
  }
  return ''
}

export default function ReceivePreview({ conversation, conversationName, participant: openWith, persona: openAs, onClose, onOpenRecord }: {
  conversation: Id | null
  conversationName?: string | null
  participant?: Id | null
  persona?: Id | null
  onClose: () => void
  /** the record itself, in Brain management; the preview closes first */
  onOpenRecord: (id: Id) => void
}) {
  const people = useApi<{ participants: { participant: string; alias: string }[] }>('/api/participants' + qs({ limit: 200 }))
  const personas = useApi<{ personas: PersonaRow[] }>('/api/personas')
  const governed = useApi<GovernedAnswer>('/api/governed' + qs({ limit: 200 }))

  const [participant, setParticipant] = useState<string>(openWith ?? '')
  const [persona, setPersona] = useState<string>(openAs ?? '')
  const [named, setNamed] = useState<string[]>([])
  const [work, setWork] = useState('')
  const [asked, setAsked] = useState('')
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [leftOut, setLeftOut] = useState(false)

  /* the work is asked about once typing rests, not on every letter */
  useEffect(() => {
    const t = window.setTimeout(() => setAsked(work), 350)
    return () => window.clearTimeout(t)
  }, [work])

  const offered = personas.data?.personas ?? []
  const index = useMemo(() => indexBy(allRows(governed.data)), [governed.data])
  const chosen = persona && offered.some((p) => p.persona === persona) ? persona : standingPersona(persona, index)
  const personaNames = useMemo(() => Object.fromEntries(offered.map((p) => [p.persona, p.name])), [personas.data]) // eslint-disable-line react-hooks/exhaustive-deps
  const personaName = chosen ? personaNames[chosen] ?? null : null

  const path = receivePath({ conversation, participant: participant || null, persona: chosen || null, named, work: asked })
  const ctx = useApi<ReceiveAnswer>(path)

  const nameable = allRows(governed.data).filter((r) => r.state === 'stands' && !named.includes(r.entry))
  const recordName = (id: string) => index[id]?.summary ? firstSentence(index[id].summary, 80) : 'A record'

  const sections = useMemo(() => outline(ctx.data?.components ?? [], { personas: personaNames, inConversation: !!conversation }), [ctx.data, personaNames, conversation])
  const total = countItems(sections)
  const keys = useMemo(() => sections.flatMap((s) => s.groups.flatMap((g) => g.items.map((i) => i.key))), [sections])
  const allOpen = keys.length > 0 && keys.every((k) => open.has(k))
  const toggle = (k: string) => setOpen((was) => { const next = new Set(was); if (next.has(k)) next.delete(k); else next.add(k); return next })

  /* FOCUS: taken on opening, kept inside while open, and given back on
     closing to whatever opened this -- or, where that was a menu entry that
     is gone by then, to the Brain button, so the keyboard is never left on
     nothing. */
  const box = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLElement | null>(typeof document === 'undefined' ? null : document.activeElement as HTMLElement | null)
  const heading = useId()
  const close = (then?: () => void) => {
    const shown = (el: HTMLElement | null | undefined) => !!el && el.isConnected && el.offsetParent !== null
    const to = shown(opener.current) ? opener.current
      : [...document.querySelectorAll<HTMLElement>('.q2-rail-brain:not(.q2-rail-sources):not(.q2-rail-space), .q2-top-brain:not(.q2-top-sources):not(.q2-top-space)')].find(shown) ?? null
    onClose()
    if (then) { then(); return }
    to?.focus()
    window.setTimeout(() => { if (shown(to) && (!document.activeElement || document.activeElement === document.body)) to!.focus() }, 0)
  }
  const live = useRef({ close })
  live.current = { close }
  useEffect(() => {
    box.current?.querySelector<HTMLElement>('[data-rp-close]')?.focus()
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); live.current.close(); return }
      if (e.key !== 'Tab' || !box.current) return
      const stops = [...box.current.querySelectorAll<HTMLElement>(STOPS)].filter((el) => el.offsetParent !== null)
      if (!stops.length) return
      const first = stops[0], last = stops[stops.length - 1], at = document.activeElement as HTMLElement | null
      if (!box.current.contains(at)) { e.preventDefault(); first.focus() }
      else if (e.shiftKey && at === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus() }
    }
    window.addEventListener('keydown', key, true)
    return () => window.removeEventListener('keydown', key, true)
  }, [])

  const where = conversation ? conversationName ?? 'this conversation' : null
  const withheld = ctx.data?.withheld ?? []
  const conflicts = ctx.data?.conflicts ?? []

  return (
    <div className="q2-brain-preview-veil" onPointerDown={(e) => { if (e.target === e.currentTarget) close() }}>
      <div className="q2-brain-preview rp" role="dialog" aria-modal="true" aria-labelledby={heading} ref={box} data-receive-preview>
        <header className="rp-head">
          <div>
            <p className="rp-eyebrow">Preview</p>
            <h2 id={heading}>What an agent would be given</h2>
          </div>
          <button type="button" className="rp-close" data-rp-close onClick={() => close()}>Close</button>
        </header>

        <p className="rp-lead">
          Everything an agent started {where ? <>in <b>{where}</b></> : 'outside any conversation'}{personaName ? <> as <b>{personaName}</b></> : ''} would
          be handed right now: the records it must follow, the knowledge matched to its work, and why each one reaches it.
          Use it to check a Persona or a placement before any work starts.
        </p>
        <p className="rp-note">
          Worked out from the Brain as it stands. Nothing runs and nothing is recorded.
          To see which past runs a record was really given to, open the record and look under “How it has gone”.
        </p>

        <div className="rp-controls">
          <label className="rp-field">
            <span className="rp-label">Who</span>
            <select aria-label="Who would do the work" value={participant} onChange={(e) => setParticipant(e.target.value)}>
              <option value="">Nobody in particular</option>
              {(people.data?.participants ?? []).map((p) => <option key={p.participant} value={p.participant}>{p.alias.replace(/^@/, '')}</option>)}
            </select>
            <small>The participant doing the work.</small>
          </label>
          <label className="rp-field">
            <span className="rp-label">Persona</span>
            <select aria-label="Persona it is started as" value={chosen} onChange={(e) => setPersona(e.target.value)}>
              <option value="">No Persona</option>
              {offered.map((p) => <option key={p.persona} value={p.persona}>{p.name}</option>)}
            </select>
            <small>The role it is started as.</small>
          </label>
          <label className="rp-field">
            <span className="rp-label">Also give it</span>
            <select aria-label="Also give it a record, for this one run" value=""
              onChange={(e) => { const v = e.target.value; if (v) setNamed((n) => (n.includes(v) ? n : [...n, v])) }}>
              <option value="">Add a record…</option>
              {nameable.map((r) => <option key={r.entry} value={r.entry}>{kindWords(r.kind)}: {firstSentence(r.summary || 'untitled', 80)}</option>)}
            </select>
            <small>As if named for this one run.</small>
          </label>
          <label className="rp-field rp-work">
            <span className="rp-label">The work</span>
            <input aria-label="The work it would be asked to do" placeholder="Describe the task or question…" value={work} onChange={(e) => setWork(e.target.value)} />
            <small>Knowledge is matched to these words. Leave it empty and none is given.</small>
          </label>
        </div>

        {named.length > 0 && (
          <ul className="rp-chips" aria-label="Records added for this one run">
            {named.map((id) => (
              <li key={id}>
                <span>{recordName(id)}</span>
                <button type="button" aria-label={`Remove ${recordName(id)}`} onClick={() => setNamed((n) => n.filter((x) => x !== id))}>×</button>
              </li>
            ))}
          </ul>
        )}

        <p className="rp-where">
          {where ? <>Counted for the conversation <b>{where}</b>.</> : <>No conversation is open, so records placed on a conversation are not counted.</>}{' '}
          It is the same whichever runtime does the work.
        </p>

        {ctx.error ? <p className="rp-error" role="alert">This could not be worked out: {ctx.error}</p>
          : !path ? <p className="rp-faint">Choose a participant or a Persona, or describe the work, to see what would be given.</p>
          : !ctx.data ? <p className="rp-faint" role="status">Working it out…</p>
          : (
            <div className="rp-result" data-rp-result>
              <div className="rp-sum">
                <p role="status">
                  <b>{plural(total, 'item')}</b> would be given: {sections.map((s) => `${s.count} ${s.label.toLowerCase()}`).join(' · ')}
                  {ctx.data.payload_chars != null && <span className="rp-dim"> · about {ctx.data.payload_chars.toLocaleString()} characters in all</span>}
                </p>
                {keys.length > 0 && (
                  <button type="button" className="rp-quiet" data-rp-all aria-pressed={allOpen} onClick={() => setOpen(allOpen ? new Set() : new Set(keys))}>
                    {allOpen ? 'Collapse all' : 'Expand all'}
                  </button>
                )}
              </div>

              {sections.map((s) => (
                <section key={s.key} className={'rp-section rp-' + s.key} aria-label={s.label} data-rp-section={s.key}>
                  <div className="rp-sh">
                    <h3>{s.label} <span className="rp-n">{s.count}</span></h3>
                    <p>{s.hint}</p>
                  </div>
                  {s.count === 0 && (
                    <p className="rp-empty">
                      {s.key === 'governing' ? 'No governing record reaches this selection.'
                        : s.key === 'knowledge' ? (asked.trim() ? 'Nothing in the Brain matched this work.' : 'Describe the work above to see which knowledge would be matched to it.')
                        : 'Nothing else would be sent.'}
                    </p>
                  )}
                  {s.groups.map((g) => (
                    <div key={g.key} className="rp-group" role="group" aria-label={g.label} data-rp-group={g.key}>
                      <h4>{g.label} <span className="rp-n">{g.items.length}</span><span className="rp-gh">{g.hint}</span></h4>
                      <ul>
                        {g.items.map((it) => <Piece key={it.key} item={it} open={open.has(it.key)} onToggle={() => toggle(it.key)}
                          onOpenRecord={(id) => close(() => onOpenRecord(id))} />)}
                      </ul>
                    </div>
                  ))}
                </section>
              ))}

              <section className="rp-section rp-out" aria-label="Left out" data-rp-section="left-out">
                <button type="button" className="rp-fold" aria-expanded={leftOut} onClick={() => setLeftOut((v) => !v)}>
                  <span className="c" aria-hidden="true">{leftOut ? '▾' : '▸'}</span>
                  Left out, and why <span className="rp-n">{withheld.length}</span>
                </button>
                {leftOut && (withheld.length === 0
                  ? <p className="rp-empty">Nothing was left out. Knowledge is limited to the few most relevant records; anything cut for that reason is listed here.</p>
                  : (
                    <ul className="rp-outlist">
                      {withheld.map((w, i) => (
                        <li key={(w.source_id ?? '') + w.why + i}>
                          <span className="rp-kind">{w.source_kind ? kindOf({ source_kind: w.source_kind }) : 'Unknown'}</span>
                          <span className="rp-outname">{w.source_id ? recordName(w.source_id) : ''}</span>
                          <span className="rp-because">{withheldReason(w)}</span>
                          {w.source_id && w.why !== 'not in this record' && w.source_kind !== 'conversation' && w.source_kind !== 'contribution' && (
                            <button type="button" className="rp-openrec" data-open-record={w.source_id} onClick={() => close(() => onOpenRecord(w.source_id!))}>Open record</button>
                          )}
                        </li>
                      ))}
                    </ul>
                  ))}
              </section>

              {conflicts.length > 0 && (
                <section className="rp-section" aria-label="Same subject">
                  <div className="rp-sh"><h3>Same subject <span className="rp-n">{conflicts.length}</span></h3><p>More than one item speaks to the same subject. All are given; Mentis does not choose between them.</p></div>
                  <ul className="rp-outlist">{conflicts.map((k) => <li key={k.about}><span className="rp-outname">{plural(k.components.length, 'item')} on “{k.about}”</span></li>)}</ul>
                </section>
              )}
            </div>
          )}
      </div>
    </div>
  )
}

function Piece({ item, open, onToggle, onOpenRecord }: { item: OutlineItem; open: boolean; onToggle: () => void; onOpenRecord: (id: Id) => void }) {
  const c = item.component
  const body = useId()
  const fullTitle = (c.title ?? '').trim()
  const facts = trailerLines(c, when)
  const reason = engineReason(c)
  const paras = (c.text ?? '').split(/\n\s*\n/).filter((p) => p.trim())
  return (
    <li className={'rp-item' + (open ? ' open' : '')} data-entry={c.source_id ?? undefined} data-rp-item={item.key}>
      <button type="button" className="rp-row" aria-expanded={open} aria-controls={body} onClick={onToggle}>
        <span className="c" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="rp-kind">{item.kind}</span>
        <span className="rp-title">{item.title}</span>
        <span className="rp-because">{item.because}</span>
      </button>
      {open && (
        <div className="rp-body" id={body} data-rp-body>
          {fullTitle && fullTitle !== item.title && <p className="rp-named">{fullTitle}</p>}
          <div className="rp-text" data-rp-text>
            {paras.length ? paras.map((p, i) => <p key={i}>{p}</p>) : <p className="rp-dim">It has no words of its own.</p>}
          </div>
          {(facts.length > 0 || reason) && (
            <ul className="rp-facts">
              {reason && <li>Reason on record: {reason}</li>}
              {facts.map((f, i) => <li key={i} className={f.warn ? 'warn' : undefined}>{f.text}</li>)}
            </ul>
          )}
          {item.record && (
            <p className="rp-acts">
              <button type="button" className="rp-openrec" data-open-record={item.record} onClick={() => onOpenRecord(item.record!)}>Open record</button>
            </p>
          )}
        </div>
      )}
    </li>
  )
}
