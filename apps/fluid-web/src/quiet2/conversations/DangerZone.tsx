/* THE DANGER ZONE: permanent deletion's full-screen confirmation (the
 * owner-approved design). Drawn above the whole workspace, which is inert
 * behind it. It names the conversation, says plainly that it cannot be
 * undone and what is removed, kept and not reached; the delete button is
 * enabled only once `delete` is typed; Cancel has focus first; Esc or Cancel
 * goes back to the list.
 *
 * REACHABLE ONLY WHEN THE SERVER SAYS PERMANENT DELETION IS AVAILABLE
 * (`store.conversationDeletion`, `manage.menuFor`). Today it is not: the
 * Trash menu's item is disabled with the reason, and no deletion code exists
 * to call. Its behaviour is `manage.dangerStep`, checked without a browser. */
import { useEffect, useReducer, useRef } from 'react'
import { DANGER_CONFIRM_WORD, DANGER_HEADLINE, DELETION_EFFECTS, canConfirm, dangerStart, dangerStep } from './manage'

const Warn = () => (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M8 2 15 14H1z" /><path d="M8 6.5v3.5M8 12v.1" /></svg>
)

export default function DangerZone({ name, files, onBack, onConfirm }: {
  /** the conversation's title */
  name: string
  /** files removed and shared files kept, where the server can say */
  files?: { removed: number; shared: number } | null
  /** Cancel or Esc: back to the list */
  onBack: () => void
  /** only ever called once `delete` is typed and the button pressed */
  onConfirm: () => void
}) {
  const [s, send] = useReducer(dangerStep, undefined, dangerStart)
  const cancel = useRef<HTMLButtonElement>(null)
  useEffect(() => { cancel.current?.focus() }, [])
  useEffect(() => {
    if (s.done === 'back') onBack()
    if (s.done === 'confirmed') onConfirm()
  }, [s.done]) // eslint-disable-line react-hooks/exhaustive-deps
  const ok = canConfirm(s.typed)
  return (
    <div className="q2-danger-veil" onKeyDown={(e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); send({ type: 'escape' }) } }}>
      <div className="q2-danger" role="alertdialog" aria-modal="true" aria-labelledby="q2-dz-title" aria-describedby="q2-dz-warn">
        <p className="q2-danger-zone"><Warn />Danger Zone</p>
        <h2 id="q2-dz-title">Permanently delete “{name}”</h2>
        <p className="q2-danger-warn" id="q2-dz-warn">{DANGER_HEADLINE}</p>
        <div className="q2-danger-effects">
          {DELETION_EFFECTS.map((g) => (
            <section key={g.heading}><h3>{g.heading}</h3><ul>{g.lines.map((l) => <li key={l}>{l}</li>)}</ul></section>
          ))}
        </div>
        {files && (files.removed || files.shared) ? (
          <p className="q2-danger-files">{files.removed} {files.removed === 1 ? 'file' : 'files'} will be removed · {files.shared} shared {files.shared === 1 ? 'file stays' : 'files stay'}</p>
        ) : null}
        <label className="q2-danger-confirm">
          <span>Type <code>{DANGER_CONFIRM_WORD}</code> to confirm</span>
          <input autoComplete="off" spellCheck={false} aria-label={`Type ${DANGER_CONFIRM_WORD} to confirm`} value={s.typed}
            onChange={(e) => send({ type: 'type', text: e.target.value })} />
        </label>
        <div className="q2-danger-acts">
          <button ref={cancel} type="button" className="q2-danger-cancel" autoFocus onClick={() => send({ type: 'cancel' })}>Cancel</button>
          <button type="button" className="q2-danger-delete" disabled={!ok} onClick={() => send({ type: 'confirm' })}>Delete permanently</button>
        </div>
      </div>
    </div>
  )
}
