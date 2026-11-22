/* WHAT A NEEDS YOU ITEM IS ABOUT, UNDER ITS ROW: what would be approved,
 * what supports it, where it was asked and what its words name -- each a
 * link to the exact thing, or the plain reason it cannot be opened.
 *
 * Drawn before the answer form, always: a summary never stands in for the
 * subject, so the link to the subject is beside every line that describes
 * it, and a subject that cannot be opened is said first (`gaps`). */
import { useState } from 'react'
import type { RefWords } from '../../experimental/refWords'
import { gaps, goneWords, openLabel, plain, questionsOf, refName, refsOf, segments, subjectHeading, subjectWords, whereWords, type About, type Ref } from './inspect'
import './needs.css'

/** Opens one exact reference; false where this page has no way to. */
export type OpenRefFn = (r: Ref) => boolean
/** Whether this page can open such a reference at all. */
export type CanOpen = (r: Ref) => boolean

const SHOWN = 4

/** One reference: a link to the thing where it can be opened, and what it is
 *  in words where it cannot. Its id is on its title, never its name. */
export function RefLink({ r, here, open, can, words }: { r: Ref; here?: string | null; open: OpenRefFn; can: CanOpen; words?: string }) {
  const where = whereWords(r, here)
  if (r.state !== 'ok') {
    return <span className="q2-ny-ref q2-ny-gone" data-ref-id={r.id} data-ref-state={r.state} title={`Exact reference: ${r.id}`}>
      {words ?? goneWords(r)}<span className="q2-ny-why"> — {r.why ?? 'It could not be read.'}</span>
    </span>
  }
  const name = words ?? refName(r)
  if (!r.opens || !r.available || !can(r)) {
    return <span className="q2-ny-ref q2-ny-still" data-ref-id={r.id} data-ref-state="ok" title={`Exact reference: ${r.id}`}>
      {name}{where ? <span className="q2-ny-where"> {where}</span> : null}
      {r.why ? <span className="q2-ny-why"> — {r.why}</span> : r.opens ? <span className="q2-ny-why"> — It cannot be opened from here.</span> : null}
    </span>
  }
  return <button type="button" className="q2-ny-ref q2-ny-link" data-ref-id={r.id} data-ref-state="ok" data-ref-opens={r.opens}
    title={`${openLabel(r)}\nExact reference: ${r.id}`} aria-label={openLabel(r) + (where ? ` ${where}` : '')}
    onClick={() => { open(r) }}>
    {name}{where ? <span className="q2-ny-where"> {where}</span> : null}
  </button>
}

function Group({ label, refs, here, open, can, mark }: { label: string; refs: Ref[]; here?: string | null; open: OpenRefFn; can: CanOpen; mark: string }) {
  const [all, setAll] = useState(false)
  if (!refs.length) return null
  const shown = all ? refs : refs.slice(0, SHOWN)
  return (
    <div className="q2-ny-group" data-role={mark}>
      <span className="q2-ny-label">{label}</span>
      <ul className="q2-ny-refs">
        {shown.map((r) => <li key={r.id}><RefLink r={r} here={here} open={open} can={can} /><span className="q2-ny-rel">{r.relation}</span></li>)}
        {refs.length > SHOWN && (
          <li><button type="button" className="q2-ny-all" aria-expanded={all} onClick={() => setAll(!all)}>{all ? 'Show fewer' : `Show all ${refs.length}`}</button></li>
        )}
      </ul>
    </div>
  )
}

/** The item's subject, evidence, context and references. */
export function NeedsAbout({ about, error, rereading, here, open, can, questionWords, asking }: {
  about: About | null; error: string | null
  /** a later read is on its way: what is drawn is being read again, not current */
  rereading?: boolean
  here?: string | null; open: OpenRefFn; can: CanOpen
  /** each question's own recorded wording, by its exact expectation id */
  questionWords?: ReadonlyMap<string, string | null>
  /** how many questions this item asks, as the list read says */
  asking?: number
}) {
  const missing = gaps(about, error, questionWords)
  if (!about || about.error) {
    return <div className="q2-ny-about" data-about="unread">
      {missing.map((g, i) => <p key={i} className="q2-ny-gap" role="note">{g}</p>)}
      {!missing.length && <p className="q2-ny-reading">Reading what this is about…</p>}
    </div>
  }
  const said = subjectWords(about)
  const op = about.operation
  /* SEVERAL QUESTIONS: each one's own subject under that question, and no
     union over them -- one question's primary source must never appear to
     belong to another (contract ent-40166218c575 §3). */
  const questions = questionsOf(about, questionWords)
  const refs = refsOf(about)
  /* SEVERAL QUESTIONS, AND NO MAPPING FROM THE SERVER: then what the form
     names belongs to the form, and the record does not say which question each
     of them is for. It is headed as that, never as "what you are deciding on",
     which would read as every question's own subject. */
  const several = questions.length > 0 || (asking ?? 0) > 1
  return (
    <div className="q2-ny-about" data-about={about.kind} data-rereading={rereading || undefined} aria-busy={rereading || undefined}>
      {rereading && <p className="q2-ny-reading" role="status">Reading these details again…</p>}
      {missing.map((g, i) => <p key={i} className="q2-ny-gap" role="note" data-gap>{g}</p>)}
      {questions.length > 0 && (
        <div className="q2-ny-questions" data-questions={questions.length}>
          {questions.map((q, i) => (
            <div key={q.id} className="q2-ny-question" data-question={q.id} data-presentation={q.presentation_state ?? undefined}>
              <span className="q2-ny-label">{`${i + 1}. ${q.question ? plain(q.question, refs) : 'This question, as the form below asks it'}`}</span>
              <ul className="q2-ny-refs">
                {(q.subject ?? []).map((r) => <li key={r.id}><RefLink r={r} here={here} open={open} can={can} /><span className="q2-ny-rel">{r.relation}</span></li>)}
                {!(q.subject ?? []).length && <li className="q2-ny-said">The record names no item for this question.</li>}
              </ul>
            </div>
          ))}
        </div>
      )}
      {/* With each question's own subject shown above, a pooled list is drawn
          only where the form itself names something, and never as "what you
          are deciding on". */}
      {(!questions.length || about.subject.length > 0) && (
      <div className="q2-ny-group" data-role="subject" data-pooled={several ? 'several' : 'one'}>
        <span className="q2-ny-label">{questions.length ? 'Named across these questions'
          : several ? 'Named by this form' : subjectHeading(about)}</span>
        <ul className="q2-ny-refs">
          {about.subject.map((r) => <li key={r.id}><RefLink r={r} here={here} open={open} can={can} /><span className="q2-ny-rel">{r.relation}</span></li>)}
          {said && !questions.length && <li className="q2-ny-said">{said}</li>}
          {several && !questions.length && about.subject.length > 0 && (
            <li className="q2-ny-said">The record does not say which of these questions each of them belongs to.</li>
          )}
          {about.kind === 'adoption' && about.subject.some((r) => r.available && r.opens === 'record') && (
            <li className="q2-ny-hint">Adopt or decline it on the record itself, where its full wording and standing are.</li>
          )}
          {about.kind === 'permission' && op && <>
            {(op.resources ?? []).length > 0 && <li className="q2-ny-said">Affects {(op.resources ?? []).join(' · ')}</li>}
            {op.within === false && <li className="q2-ny-said q2-ny-outside">Outside this task{op.outside?.length ? ': ' + op.outside.join('; ') : ''}</li>}
            {op.command && (
              <li><details className="q2-ny-command"><summary>The exact command</summary>
                <pre>{op.command}</pre>
                {(op.tool_label || op.tool || op.cwd) && <span className="q2-ny-rel">{[op.tool_label || op.tool, op.cwd && `in ${op.cwd}`].filter(Boolean).join(' · ')}</span>}
              </details></li>
            )}
          </>}
        </ul>
      </div>
      )}
      <Group label="Supporting material" refs={about.evidence} here={here} open={open} can={can} mark="evidence" />
      <Group label="Where it comes from" refs={about.context} here={here} open={open} can={can} mark="context" />
      <Group label="Also named in its words" refs={about.referenced} here={here} open={open} can={can} mark="referenced" />
    </div>
  )
}

/** How the decision form draws its own words for this item (`RefWordsContext`):
 *  each id as a link to the exact thing, or as its name inside a control. */
export function refWordsFor(about: About | null, here: string | null | undefined, open: OpenRefFn, can: CanOpen): RefWords | null {
  if (!about || about.error) return null
  const refs = refsOf(about)
  return {
    names: (text) => plain(text, refs),
    links: (text) => segments(text, refs).map((s, i) => 'text' in s ? <span key={i}>{s.text}</span>
      : 'ref' in s ? <RefLink key={i} r={s.ref} here={here} open={open} can={can} />
        : <span key={i} className="q2-ny-ref q2-ny-gone" title={`Exact reference: ${s.unknown}`}>a reference that could not be read</span>),
    open: (id, words) => {
      const r = refs.get(id)
      return r ? <span className="q2-ny-openref"><RefLink r={r} here={here} open={open} can={can} words={r.state === 'ok' ? `${words}${r.number != null ? ` (#${r.number})` : ''}` : undefined} /></span> : null
    },
    /* HOW THIS EXACT ID STANDS NOW, as the server resolved it and as this panel
       already draws it: the same resolution, by the same id, so what the form
       offers and what the panel shows cannot say different things about the
       same reference (review finding F2, ent-4ca09a1119c8). An id this read
       resolved nothing for is answered null, and nothing is claimed about it. */
    standing: (id) => {
      const r = refs.get(id)
      return r ? { available: r.available, state: r.state, why: r.why } : null
    },
  }
}
