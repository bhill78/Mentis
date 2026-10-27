import { useRef, useState } from 'react'
import { announceAdvance } from '../../api'
import type { ActOutcome } from '../standing'
import './InSituGovernance.css'

/* ------------------------------------------------------------------------ *
 * ACTING WHERE THE WORK IS, THROUGH A FIELD AND NOT A DIALOG.
 *
 * NO MODAL. An act taken beside the Turn that occasioned it is part of
 * reading the Turn; a dialog over the top of the Conversation makes it a
 * separate errand, hides the thing being acted on at the moment of deciding,
 * and on a phone takes the whole screen. So each act opens a small form in
 * place, states its effect ABOVE the fields, and is cancelled by a control
 * that is always there.
 *
 * WHAT IT SAYS BEFORE THE CLICK IS THE WHOLE POINT. Every form leads with one
 * sentence saying what will be recorded, and its go control is labelled with
 * the act rather than with "OK" — a person must be able to tell an act that
 * records something from one that records nothing without doing either.
 *
 * IT IS THE SAME ACT GOVERNANCE PERFORMS. Every form here calls the shared
 * helpers in `standing.ts`, which call the same routes the inspector calls.
 * There is no in-situ commit path, and there must never be one.
 * ------------------------------------------------------------------------ */

export type FormKind = 'establish' | 'revise' | 'dispute' | 'respond' | 'set-aside'

/** WHAT EACH FORM SAYS, AND WHAT ITS GO CONTROL IS CALLED.
 *
 *  `needs` is whether the act is meaningless without words. Establish needs
 *  none — the material is already written and the act is the owner's assent.
 *  The other three each carry something a record would be poorer without, and
 *  the server refuses an empty one for exactly that reason. */
const FORM: Record<
  FormKind,
  { placeholder: string; go: string; needs: boolean; blocked: string; rows: number }
> = {
  establish: {
    placeholder: 'Why, in your words (optional)…',
    go: 'Establish now',
    needs: false,
    blocked: '',
    rows: 2,
  },
  revise: {
    placeholder: 'The revised material…',
    go: 'Establish my revision',
    needs: true,
    blocked: 'Change the text first.',
    rows: 4,
  },
  dispute: {
    placeholder: 'What is wrong with it?',
    go: 'Record dispute',
    needs: true,
    blocked: 'Write the challenge first.',
    rows: 3,
  },
  respond: {
    placeholder: 'Answer in your own words',
    go: 'Send',
    needs: true,
    blocked: 'Write your answer first.',
    rows: 3,
  },
  'set-aside': {
    placeholder: 'Why the material held…',
    go: 'Set the dispute aside',
    needs: true,
    blocked: 'Write the answer to the challenge first.',
    rows: 3,
  },
}

export interface InlineFormProps {
  kind: FormKind
  /** the one sentence above the fields, saying what this will record. The
   *  caller writes it because only the caller knows where the material
   *  applies, and where it applies is half of what the act does. */
  intro: React.ReactNode
  /** what the field starts with — the proposal's own words, for a revision */
  initial?: string
  busy?: boolean
  failed?: string | null
  onGo: (said: string) => void
  onCancel: () => void
}

export function InlineForm({ kind, intro, initial = '', busy, failed, onGo, onCancel }: InlineFormProps) {
  const shape = FORM[kind]
  const [said, setSaid] = useState(initial)
  const [blocked, setBlocked] = useState<string | null>(null)
  const box = useRef<HTMLTextAreaElement | null>(null)
  const empty = shape.needs && !said.trim()
  /* A REVISION THAT IS THE SAME WORDS IS NOT A REVISION. The record would
     carry a replacement identical to what it replaced, which says nothing. */
  const unchanged = kind === 'revise' && said.trim() === initial.trim()

  const go = () => {
    if (busy) return
    /* BLOCKED IN PLAIN WORDS, NOT BY A DEAD CONTROL. A control that does
       nothing and says nothing leaves somebody pressing it. */
    if (empty || unchanged) {
      setBlocked(shape.blocked)
      box.current?.focus()
      return
    }
    setBlocked(null)
    onGo(said.trim())
  }

  return (
    <div className="insitu-form">
      <p className="insitu-form-note">{intro}</p>
      <textarea
        ref={box}
        className="insitu-form-field"
        rows={shape.rows}
        value={said}
        placeholder={shape.placeholder}
        autoFocus
        onChange={(e) => {
          setSaid(e.target.value)
          if (blocked) setBlocked(null)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) go()
          if (e.key === 'Escape') onCancel()
        }}
      />
      {blocked && (
        <p className="insitu-blocked" role="alert">
          {blocked}
        </p>
      )}
      {failed && (
        <p className="insitu-failed" role="alert">
          {failed}
        </p>
      )}
      <div className="insitu-form-row">
        <button className="insitu-go" disabled={busy} onClick={go}>
          {busy ? 'Recording…' : shape.go}
        </button>
        {/* ALWAYS THERE, AND IT DOES NOTHING AT ALL. */}
        <button className="insitu-link" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------------ *
 * RUNNING ONE ACT, AND SAYING WHETHER IT LANDED.
 *
 * AN ACT THAT DID NOT LAND MUST NOT LOOK AS THOUGH IT DID, and one that did
 * must say so where the person is looking — on a phone the item's new state
 * may be a scroll away, so the confirmation sits at the act.
 *
 * AND IT TELLS EVERY OTHER READER. The same item may be in the inspector, in
 * the header's lists and on another Turn; one of them still saying "proposed"
 * beside another saying it stands is two readings of one record disagreeing.
 * `announceAdvance` is how the rest of this interface hears, so it is what is
 * used here, exactly as the inspector uses it.
 * ------------------------------------------------------------------------ */

export interface Landed {
  /** what to say happened, in this interface's words */
  said: string
  /** the server's own sentence where the act also answered an open ask */
  answered: string | null
}

export function useAct() {
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const [landed, setLanded] = useState<Landed | null>(null)

  /** `said` is what this interface will report. `run` is the act itself. */
  const run = async (said: string, act: () => Promise<unknown>) => {
    setBusy(true)
    setFailed(null)
    try {
      const out = (await act()) as ActOutcome | null
      setLanded({
        said,
        /* THE SERVER'S OWN SENTENCE, not a guess from here. An act that
           answered a request says so; one that did not stays silent rather
           than saying it answered nothing. */
        answered: out?.answers_a_request ? (out.say ?? 'The request to you is answered.') : null,
      })
      announceAdvance()
      return true
    } catch (e) {
      setFailed(e instanceof Error ? e.message : String(e))
      return false
    } finally {
      setBusy(false)
    }
  }

  return { busy, failed, landed, run, clear: () => setLanded(null), setFailed }
}

/** What an act that landed says, where the act was taken.
 *
 *  IT NAMES THE ITEM GOVERNANCE SHOWS, because that is the point: this was
 *  not an annotation on a Turn, it was the same act, on the same material,
 *  that the workspace would have performed. */
export function Landing({ landed }: { landed: Landed }) {
  return (
    <p className="insitu-landed" role="status" aria-live="polite">
      <span className="insitu-tick" aria-hidden="true">
        ✓
      </span>
      {landed.said} Recorded on the same governed item Governance shows.
      {landed.answered && <span className="insitu-answered"> {landed.answered}</span>}
    </p>
  )
}

/** Something that records nothing, said before the click and after it.
 *
 *  LEAVING IT IS A REAL ANSWER and is not a silent yes: it is offered beside
 *  the acts that do record something, titled with what it does not do, and it
 *  is drawn as a plain link so nothing about it reads as the primary path. */
export function RecordsNothing({
  label,
  title,
  onClick,
  disabled,
}: {
  label: string
  title: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button className="insitu-link insitu-quiet" title={title} disabled={disabled} onClick={onClick}>
      {label}
    </button>
  )
}
