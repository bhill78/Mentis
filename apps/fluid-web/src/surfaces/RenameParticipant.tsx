import { useState } from 'react'
import { post, type Id } from '../api'
import { useMe } from '../identity'

/* ------------------------------------------------------------------------ *
 * RENAME THIS NAME, KEEPING WHO IT IS. The owner's act.
 *
 * `POST /api/participants/<id>/rename`. The Participant stays the one every
 * post, act and delegation already names; the new alias is its next version
 * and the old one stays in History. Afterwards the old alias is refused for
 * new addressing, with the new one named. A name that reads as a runtime or
 * a model (codex, Claude Code, gpt ...) is refused: a name never chooses
 * where work runs. The server's refusal is shown as it was said.
 * ------------------------------------------------------------------------ */

export default function RenameParticipant({
  participant,
  alias,
  onChanged,
}: {
  participant: Id
  alias: string | null
  onChanged?: () => void
}) {
  const { me } = useMe()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [because, setBecause] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!me) return null
  if (!open)
    return (
      <p className="wp-rename">
        <button type="button" onClick={() => { setName((alias ?? '').replace(/^@/, '')); setOpen(true) }}>
          Rename
        </button>
      </p>
    )

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await post(`/api/participants/${encodeURIComponent(participant)}/rename`, {
        alias: name.trim(),
        because: because.trim() || undefined,
        attributed_to: me,
      })
      setOpen(false)
      setBecause('')
      onChanged?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="wp-rename"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <label>
        New name @
        <input value={name} disabled={busy} autoFocus onChange={(e) => setName(e.target.value)} />
      </label>{' '}
      <label>
        Why <input value={because} disabled={busy} onChange={(e) => setBecause(e.target.value)} />
      </label>{' '}
      <button type="submit" disabled={busy || !name.trim()}>
        Rename
      </button>{' '}
      <button type="button" disabled={busy} onClick={() => { setOpen(false); setError(null) }}>
        Cancel
      </button>
      <span className="wp-runtime-why">
        Keeps who this is: every post and piece of work still names them, and the old name stays in
        History. The old name is then refused for new addressing.
      </span>
      {error && <span className="wp-error"> {error}</span>}
    </form>
  )
}
