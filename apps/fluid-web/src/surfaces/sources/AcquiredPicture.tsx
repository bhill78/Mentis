import { useEffect, useState } from 'react'
import { read, type Id } from '../../api'
import { Floating } from '../../bits'
import './sources.css'

/* ------------------------------------------------------------------------ *
 * AN ACQUIRED IMAGE, DRAWN (Sources B, B2 and B3).
 *
 * A thumbnail you click to enlarge. The bytes come only from the existing
 * verified route, `/api/artifacts/<adm>`, which serves a held Admission to
 * the owner -- an image only by its own signature, never on a name -- and
 * refuses a worker grant. There is no other byte route, and nothing here
 * reads the bound folder or anything on the web.
 *
 * NEVER A BROKEN IMAGE. Bytes that are purged, missing or corrupt are a
 * labelled placeholder saying which: when the caller already knows the
 * state it is drawn at once; when the picture fails to load, the route's
 * own verified description is asked and its state is said.
 * ------------------------------------------------------------------------ */

const STATE_WORDS: Record<string, string> = {
  purged: 'purged · Mentis no longer holds these bytes',
  'held-but-missing': 'missing · the held bytes are not there',
  'held-but-corrupt': 'corrupt · the held bytes do not match their digest',
  'not-held': 'not held',
  unknown: 'not in this record',
}

export const pictureState = (state: string) => STATE_WORDS[state] ?? state

export function PicturePlaceholder({ label, state, placed }: { label?: string | null; state: string; placed?: boolean }) {
  return (
    <span className={'acq-placeholder' + (placed ? ' acq-placeholder-placed' : '')} role="img" aria-label={`${label ?? 'image'}: ${pictureState(state)}`}>
      <span className="acq-placeholder-kind">image</span>
      {label && <span className="acq-placeholder-label">{label}</span>}
      <span className="acq-placeholder-state">{pictureState(state)}</span>
    </span>
  )
}

export default function AcquiredPicture({
  id,
  label,
  state,
  placed = false,
}: {
  id: Id
  /** what it is called: the acquired object's key or label */
  label?: string | null
  /** the record's state for these bytes, when the caller already has it */
  state?: string | null
  /** a figure placed in the post: drawn at its own size within the column */
  placed?: boolean
}) {
  const [failed, setFailed] = useState<string | null>(null)
  const [big, setBig] = useState(false)
  useEffect(() => setFailed(null), [id])
  useEffect(() => {
    if (!big) return
    const off = (e: KeyboardEvent) => e.key === 'Escape' && setBig(false)
    window.addEventListener('keydown', off)
    return () => window.removeEventListener('keydown', off)
  }, [big])
  const known = state && state !== 'held' ? state : failed
  if (known) return <PicturePlaceholder label={label} state={known} placed={placed} />
  const src = `/api/artifacts/${encodeURIComponent(id)}`
  const broke = () => {
    setFailed('could not be shown')
    read<{ state?: string }>(`${src}?describe=1`).then(
      (d) => setFailed(d.state && d.state !== 'held' ? d.state : 'could not be shown'),
      () => setFailed('could not be shown'),
    )
  }
  return (
    <>
      <button
        type="button"
        className={'acq-thumb' + (placed ? ' acq-placed-img' : '')}
        title={`${label ?? 'acquired image'} · click to enlarge`}
        onClick={(e) => {
          e.stopPropagation()
          setBig(true)
        }}
      >
        <img src={src} alt={label ?? 'acquired image'} loading="lazy" onError={broke} />
      </button>
      {big && (
        <Floating>
          <div
            className="acq-lightbox"
            role="dialog"
            aria-label={label ?? 'acquired image'}
            onClick={() => setBig(false)}
          >
            <img src={src} alt={label ?? 'acquired image'} onError={broke} />
            <span className="acq-lightbox-cap">
              {label ?? id} · <span className="src-mono">{id}</span> · click or Esc to close
            </span>
          </div>
        </Floating>
      )}
    </>
  )
}
