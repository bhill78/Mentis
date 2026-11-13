/* THE DANGER ZONE: permanent deletion's full-screen confirmation (the
 * owner-approved design). Drawn above the whole workspace, which is inert
 * behind it. It names the conversation, says plainly that it cannot be
 * undone, and shows the deletion's ACTUAL impact as the server reads it now
 * (`store.deletionImpact`): what is removed, what is kept, what is not
 * reached. Cancel has focus first; the delete button is enabled only once
 * `delete` is typed and the impact is read; Esc or Cancel goes back to the
 * list with nothing done.
 *
 * The deletion presents the impact's token: if what would be deleted moved
 * since it was shown, the server refuses (impact-changed), the impact is read
 * again and the word must be typed again. Every refusal is said here, in
 * plain words, and nothing is deleted. Its behaviour is `manage.dangerStep`,
 * checked without a browser.
 *
 * REACHABLE ONLY WHEN THE SERVER SAYS PERMANENT DELETION IS AVAILABLE and
 * Trash's work check passes (`store.conversationDeletion`, `manage.menuFor`). */
import { useEffect, useReducer, useRef, useState } from 'react'
import { store, type Conversation, type DeletionDone, type DeletionImpact } from '../../fluid/store'
import { DANGER_CONFIRM_WORD, DANGER_HEADLINE, canConfirm, dangerStart, dangerStep, deletionRefusal, impactGroups } from './manage'

const Warn = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 2 15 14H1z" /><path d="M8 6.5v3.5M8 12v.1" /></svg>
)

/** The impact, as the overlay lists it (exported for the unit check). */
export function ImpactList({ impact }: { impact: DeletionImpact }) {
  return (
    <div className="q2-danger-effects" data-impact={impact.token}>
      {impactGroups(impact).map((g) => (
        <section key={g.heading}><h3>{g.heading}</h3><ul>{g.lines.map((l) => (
          g.heading === 'Not reached'
            ? <li key={l.text}>{l.text}{l.sub && <span className="q2-danger-why"> {l.sub.join('; ')}</span>}</li>
            : <li key={l.text}>{l.text}
                {l.sub && <ul className="q2-danger-sub">{l.sub.map((x) => <li key={x}>{x}</li>)}</ul>}
              </li>
        ))}</ul></section>
      ))}
    </div>
  )
}

export default function DangerZone({ conversation, name, onBack, onDeleted, initial }: {
  conversation: Conversation
  /** the conversation's title */
  name: string
  /** Cancel or Esc: back to the list, nothing done */
  onBack: () => void
  /** the deletion is done: what the server answered */
  onDeleted: (done: DeletionDone) => void
  /** an impact already read (the unit check); otherwise it is read here */
  initial?: DeletionImpact
}) {
  const [s, send] = useReducer(dangerStep, undefined, dangerStart)
  const [impact, setImpact] = useState<DeletionImpact | null>(initial ?? null)
  const [readError, setReadError] = useState<string | null>(null)
  const [refused, setRefused] = useState<string | null>(null)
  const [reads, setReads] = useState(0)
  const cancel = useRef<HTMLButtonElement>(null)
  useEffect(() => { cancel.current?.focus() }, [])

  /* THE IMPACT, read now and again after a refusal that may have moved it */
  useEffect(() => {
    if (initial && !reads) return
    let live = true
    setReadError(null)
    store.deletionImpact(conversation.id).then((got) => { if (live) setImpact(got) },
      (e: unknown) => { if (live) { setImpact(null); setReadError(deletionRefusal(e).words.replace(/^Nothing was deleted: /, '')) } })
    return () => { live = false }
  }, [conversation.id, reads]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (s.done === 'back') { onBack(); return }
    if (s.done !== 'confirmed' || !impact) return
    let live = true
    setRefused(null)
    void (async () => {
      try {
        const author = store.me ?? await store.loadMe()
        const done = await store.deleteConversation(conversation.id, author, impact.token)
        if (live) onDeleted(done)
      } catch (e: unknown) {
        if (!live) return
        const r = deletionRefusal(e)
        setRefused(r.words)
        if (r.reread) setReads((n) => n + 1)
        send({ type: 'refused', again: r.again })
      }
    })()
    return () => { live = false }
  }, [s.done]) // eslint-disable-line react-hooks/exhaustive-deps

  const deleting = s.done === 'confirmed'
  const ok = canConfirm(s.typed) && !!impact && !deleting
  return (
    <div className="q2-danger-veil" onKeyDown={(e) => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); if (!deleting) send({ type: 'escape' }); return }
      /* MODAL: Tab and Shift+Tab go round inside it, never to the page behind */
      if (e.key !== 'Tab') return
      const all = [...e.currentTarget.querySelectorAll<HTMLElement>('input:not(:disabled), button:not(:disabled)')]
      if (!all.length) { e.preventDefault(); return }
      const i = all.indexOf(document.activeElement as HTMLElement)
      const n = e.shiftKey ? (i <= 0 ? all.length - 1 : i - 1) : (i === -1 || i === all.length - 1 ? 0 : i + 1)
      e.preventDefault(); all[n].focus()
    }}>
      <div className="q2-danger" role="alertdialog" aria-modal="true" aria-labelledby="q2-dz-title" aria-describedby="q2-dz-warn" aria-busy={deleting || undefined}>
        <p className="q2-danger-zone"><Warn />Danger Zone</p>
        <h2 id="q2-dz-title">Permanently delete “{name}”</h2>
        <p className="q2-danger-warn" id="q2-dz-warn">{DANGER_HEADLINE}</p>
        {impact
          ? <ImpactList impact={impact} />
          : readError
            ? <p className="q2-danger-refused" role="alert">Could not read what would be deleted: {readError}</p>
            : <p className="q2-danger-reading" role="status">Reading what would be deleted…</p>}
        {refused && <p className="q2-danger-refused" role="alert">{refused}</p>}
        <label className="q2-danger-confirm">
          <span>Type <code>{DANGER_CONFIRM_WORD}</code> to confirm</span>
          <input autoComplete="off" spellCheck={false} aria-label={`Type ${DANGER_CONFIRM_WORD} to confirm`} value={s.typed} disabled={deleting}
            onChange={(e) => send({ type: 'type', text: e.target.value })} />
        </label>
        <div className="q2-danger-acts">
          <button ref={cancel} type="button" className="q2-danger-cancel" autoFocus disabled={deleting} onClick={() => send({ type: 'cancel' })}>Cancel</button>
          <button type="button" className="q2-danger-delete" disabled={!ok} onClick={() => send({ type: 'confirm' })}>{deleting ? 'Deleting…' : 'Delete permanently'}</button>
        </div>
      </div>
    </div>
  )
}
