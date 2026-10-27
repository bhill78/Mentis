import { useRef, useState } from 'react'
import { post, type Id } from '../api'
import { Avatar } from '../bits'
import { useMe } from '../identity'

/* ------------------------------------------------------------------------ *
 * HOW THIS NAME IS PICTURED, AND CHANGING IT.
 *
 * The default needs no record: the interface draws the mark of the runtime
 * this name last ran on, or its initial. Choosing a picture writes one
 * `pictured-by` link to the uploaded image, and choosing again supersedes it,
 * so what it looked like before stays in History. Going back to the default
 * ends the link. PNG, JPEG and GIF only -- what Mentis will serve as an image;
 * the server checks the bytes, not the file name.
 * ------------------------------------------------------------------------ */
export default function PictureChooser({
  participant,
  alias,
  size = 56,
  onChanged,
}: {
  participant: Id
  alias: string | null
  size?: number
  /** anything else on screen that should reread now rather than on the next advance */
  onChanged?: () => void
}) {
  const { me, person } = useMe()
  const chosen = person(participant)?.avatar ?? null
  const input = useRef<HTMLInputElement | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const route = `/api/participants/${encodeURIComponent(participant)}/avatar`

  const act = async (body: () => Promise<Record<string, unknown>>) => {
    setBusy(true)
    setError(null)
    try {
      await post(route, { ...(await body()), attributed_to: me })
      onChanged?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const upload = (f: File) =>
    act(async () => {
      const r = await fetch('/api/artifacts', {
        method: 'POST',
        headers: { 'Content-Type': f.type || 'application/octet-stream', 'X-Mentis-Upload': '1' },
        body: f,
      })
      const j = await r.json()
      if (!r.ok) throw new Error(j.error ?? r.statusText)
      return { staged: j.staged, name: f.name, media_type: f.type || null }
    })

  return (
    <div className="picture-chooser">
      <Avatar id={participant} alias={alias} size={size} />
      <div className="picture-chooser-acts">
        <button className="link" disabled={busy || !me} onClick={() => input.current?.click()}>
          {chosen ? 'Change picture' : 'Choose a picture'}
        </button>
        {chosen && (
          <button className="link" disabled={busy || !me} onClick={() => act(async () => ({ clear: true }))}>
            Use the runtime mark
          </button>
        )}
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/gif"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0]
            e.target.value = ''
            if (f) upload(f)
          }}
        />
        {busy && <span className="faint">saving…</span>}
        {error && <span className="picture-chooser-error">{error}</span>}
      </div>
    </div>
  )
}
