/* MAKING A BRAIN RECORD: a compact modal over whatever the reader was doing.
 *
 * Opened from Brain management ("New" in the Brain browser, a record's
 * "Propose a rule from it…", a conversation's Instructions). It is never part
 * of the conversation composer. The workspace behind it is not touched: the
 * conversation, its reading position, the browser and any open record are
 * exactly as they were when it closes.
 *
 * The modal is only a frame. What is asked, checked and sent is the shared
 * editor (`Editor.tsx`) over the shared model (`model.ts`), the same ones
 * the record page revises with.
 *
 * AFTER RECORDING it says what was recorded and that it is a proposal, and
 * offers the record. Establishing is done there, as its own act with its own
 * reason: nothing here puts anything in effect. */
import { useEffect, useRef, useState } from 'react'
import { useApi, type Id } from '../../../api'
import type { KindAuthoring } from '../../../surfaces/governance/r2Model'
import { authoring, useUnfinished } from '../../leaving'
import BrainEditor, { type EditorHandle, type Recorded } from './Editor'
import { resolvePasted } from './Finder'
import { kindTitle, type Draft, type Ref } from './model'
import './author.css'

export interface AuthorRequest {
  kind: string
  /** a held record this is being written from, already chosen as its basis */
  basis?: Id
  /** the conversation the reader is in, where there is one */
  conversation?: { id: Id; name: string } | null
}

const STOPS = 'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [href], [tabindex]:not([tabindex="-1"])'

export default function AuthorModal({ request, me, onClose, onOpenRecord }: {
  request: AuthorRequest
  me: Id | null
  /** closed with nothing more to do: back to what was there before */
  onClose: () => void
  /** the record just made, opened in Brain management */
  onOpenRecord: (id: Id) => void
}) {
  const definitions = useApi<{ kinds: KindAuthoring[]; capabilities?: string[] }>('/api/governance/authoring')
  const k = definitions.data?.kinds.find((x) => x.kind === request.kind && x.authoring) ?? null
  const [basis, setBasis] = useState<Ref[] | null>(request.basis ? null : [])
  const [done, setDone] = useState<Recorded | null>(null)
  const [held, setHeld] = useState(false)
  const editor = useRef<EditorHandle>(null)
  const box = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLElement | null>(document.activeElement as HTMLElement | null)

  /* the record the door named, in words: never its reference */
  useEffect(() => {
    if (!request.basis) return
    let stale = false
    resolvePasted(request.basis).then((r) => { if (!stale) setBasis([r]) }, () => { if (!stale) setBasis([{ ref: request.basis!, label: 'The record you came from', kind: 'Record' }]) })
    return () => { stale = true }
  }, [request.basis])

  /* THE PAGE'S OWN WAYS OUT ASK TOO (the browser's Back, a conversation
     press that somehow reaches the page): the one question in `leaving.ts`. */
  useUnfinished(() => (held && !done ? authoring(`this new ${kindTitle(request.kind)}`) : null))

  /* FOCUS GOES BACK WHERE IT CAME FROM: the control that opened this, or --
     where that was a menu entry that no longer exists -- Brain management's
     own menu button, so the keyboard is never left on nothing. */
  const close = () => {
    const to = opener.current?.isConnected ? opener.current : document.querySelector<HTMLElement>('.q2-brain-veil:not([hidden]) .q2-brain-more')
    onClose()
    to?.focus()
    window.setTimeout(() => { if (to?.isConnected && !document.activeElement?.closest('.q2-brain-card, [data-author-modal]')) to.focus() }, 0)
  }
  const leave = () => { if (done || !editor.current) close(); else editor.current.leave() }

  /* ESCAPE AND TAB BELONG TO THE MODAL WHILE IT IS OPEN. Taken before
     anything behind it hears them, so Escape never also closes the browser
     or a popover underneath; left alone while the page's own leave question
     is up, which is in front of this. */
  const live = useRef({ leave })
  live.current = { leave }
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (document.querySelector('.q2-leave')) return
      if (e.key === 'Escape') {
        e.preventDefault(); e.stopPropagation()
        if (!editor.current?.escape()) live.current.leave()
        return
      }
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

  const seed: Partial<Draft> = { basis: basis ?? [], conversation: request.conversation ?? null,
    open: basis?.length ? ['basis'] : [] }
  const noun = kindTitle(request.kind)

  return (
    <div className="ba-veil" data-author-modal onPointerDown={(e) => { if (e.target === e.currentTarget) { e.preventDefault(); leave() } }}>
      <div ref={box} className="ba-modal" role="dialog" aria-modal="true" aria-label={done ? `${noun} recorded` : `New ${noun}`}>
        {definitions.error && <p className="ba-err" role="alert">Could not read what can be made: {definitions.error} <button type="button" className="ba-link" onClick={definitions.reload}>Retry</button>
          {' '}<button type="button" className="ba-link" onClick={close}>Close</button></p>}
        {!definitions.data && !definitions.error && <p className="ba-none" role="status">Reading…</p>}
        {definitions.data && !k && <p className="ba-err" role="alert">This Brain does not offer making a {noun} here. <button type="button" className="ba-link" autoFocus onClick={close}>Close</button></p>}
        {k && basis && !done && (
          <BrainEditor key={request.kind + ':' + (request.basis ?? '')} mode="create" k={k} capabilities={definitions.data?.capabilities ?? []} me={me}
            seed={seed} here={request.conversation ?? null} handle={editor}
            onDirty={setHeld} onCancel={close} onRecorded={setDone} />
        )}
        {done && (
          <div className="ba ba-done" role="status" data-author-done={done.id}>
            <h2>Recorded</h2>
            <p className="ba-done-words"><span className="ba-chip-k">{kindTitle(done.kind)}</span> {done.words.length > 220 ? done.words.slice(0, 219).trimEnd() + '…' : done.words}</p>
            <p className="ba-note">{done.standingApt
              ? 'It is a proposal. It is not in effect, and nobody has been asked to approve it. Establish it from its record when you decide to.'
              : 'It is recorded. Standing does not apply to this kind.'}</p>
            <div className="ba-foot">
              <span className="ba-sp" />
              <button type="button" className="ba-btn" data-open-record onClick={() => { const id = done.id; onClose(); onOpenRecord(id) }}>Open the record</button>
              <button type="button" className="ba-btn go" autoFocus data-done onClick={close}>Done</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
