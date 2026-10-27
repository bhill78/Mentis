import { useEffect, useRef, useState } from 'react'
import { read, shortId, useApi, when } from '../../api'
import { anchored, Floating } from '../../bits'
import AcquiredPicture from './AcquiredPicture'
import { bytes, openInSources, reveal, type Provenance } from './route'
import './sources.css'

/* ------------------------------------------------------------------------ *
 * A REFERENCE TO ACQUIRED MATERIAL, IN A TURN (U9).
 *
 * The Turn carries one observation's `adm-`. That reference is PINNED: it is
 * the observation that was cited, and it never moves to the latest on its
 * own (owner decision 3). Opened, the chip says what it is -- collection ›
 * object › this observation, version n of m -- and, when the record holds a
 * newer one, says so with Compare and Go to latest. Open in Sources lands on
 * that observation and Back returns here. Show live file opens Explorer on
 * this machine where the collection is bound, and says why not elsewhere.
 *
 * Nothing but what it is is read until the chip is opened, and what is read
 * is the record: `/api/references?ref=` is the same resolver a worker uses.
 *
 * AN ACQUIRED IMAGE IS DRAWN AS THE IMAGE (Sources B, B2): a thumbnail you
 * click to enlarge, with this chip -- provenance, version n of m, Open in
 * Sources, Show live file -- attached to it. Whether it is an image is the
 * record's answer from the bytes' signature (`artifact.view`), never the
 * name. A structured `acquired` part and an `adm-` an agent typed in its
 * text both arrive here, so both are drawn the same way. Bytes that are
 * purged, missing or corrupt are a labelled placeholder, never a broken
 * image (`AcquiredPicture`). Anything else that is acquired stays a chip.
 *
 * AN IMAGE AN AGENT RETURNED IS DRAWN THE SAME WAY. An ordinary held
 * artifact whose bytes the record says are an image is the same thumbnail,
 * with its chip still a neutral reference: it is not acquired material and
 * is never labelled as such. Anything else held stays a chip.
 *
 * PLACED ON ITS OWN, AN IMAGE IS A FIGURE IN THE POST (`placed`): a
 * paragraph that holds only the image is drawn at the image's own size
 * within the reading column, its words a quiet caption under it, and the
 * reference a small mark on the caption line -- the same reference with the
 * same popover, as neutral or as acquired as the record says. Mid-sentence
 * it stays the compact thumbnail. Not an image, it is the chip either way.
 * ------------------------------------------------------------------------ */

type Resolved = Partial<Provenance> & {
  known: boolean
  what?: string
  why_not?: string
  artifact?: { name?: string | null; state?: string; view?: string | null; claimed_media_type?: string | null }
}

const HELD = 'a held artifact'

/** Whether the record says this Admission is a picture: by the bytes'
 *  signature while they are held, and -- once they are not -- by what the
 *  record says it was, so a purged image is still said to be one (as a
 *  placeholder), never silently dropped to a bare chip. An acquired
 *  observation says so by the type recorded when it was swept; an ordinary
 *  held artifact -- an image an agent returned -- by the signature of any
 *  bytes still there, or else the type recorded when it was admitted. */
export const isPicture = (r: Resolved | null | undefined): boolean => {
  if (!r) return false
  const a = r.artifact
  if (chipKind(r) === 'acquired')
    return a?.state === 'held' ? a?.view === 'image' : (r.payload_type ?? '').startsWith('image/')
  if (r.what !== HELD || !a?.state) return false
  return a.state === 'held'
    ? a.view === 'image'
    : a.view === 'image' || (a.claimed_media_type ?? '').startsWith('image/')
}

/** WHAT KIND OF CHIP AN `adm-` IS, decided by what the record says it
 *  resolves to and never by its shape. Every Admission has the `adm-` shape
 *  -- a spec someone returned, an image posted in a Turn -- and only a Bulk
 *  Source observation is acquired material. Drawing every typed `adm-` as
 *  "acquired material" mislabelled ordinary artifacts until opened (review
 *  note 3), so until the record has answered the chip is a neutral
 *  reference. */
export type ChipKind = 'acquired' | 'reference'

export const chipKind = (r: Pick<Resolved, 'what'> | null | undefined): ChipKind =>
  r?.what === 'an acquired observation' ? 'acquired' : 'reference'

export function chipLook(kind: ChipKind, id: string, said?: string): { className: string; title: string } {
  if (kind === 'acquired')
    return { className: 'ref acq-chip' + (said ? ' said' : ''), title: said ? `acquired material · ${id}` : 'acquired material' }
  return { className: 'ref', title: said ? `reference · ${id}` : 'reference' }
}

/* WHAT AN ADMISSION IS NEVER CHANGES -- it is one immutable entry -- so the
   answer is asked once per reference and kept for the page's life. The
   popover still rereads when opened, because version n of m and "newer
   exists" do change. */
const kinds = new Map<string, Promise<Resolved | null>>()

function resolvedOnce(id: string): Promise<Resolved | null> {
  let k = kinds.get(id)
  if (!k) {
    k = read<Resolved>(`/api/references?ref=${encodeURIComponent(id)}`).catch(() => {
      kinds.delete(id) // a failed read is not an answer; ask again next time
      return null
    })
    kinds.set(id, k)
  }
  return k
}

export default function AcquiredChip({
  id,
  said,
  placed = false,
}: {
  id: string
  said?: string
  /** the image is a paragraph of its own: draw it as a figure in the post */
  placed?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [pin, setPin] = useState(false)
  const at = useRef<HTMLButtonElement | null>(null)
  const shown = open || pin
  const r = useApi<Resolved>(shown ? `/api/references?ref=${encodeURIComponent(id)}` : null, { live: false })
  const p = r.data
  const acquired = p?.what === 'an acquired observation'
  const [first, setFirst] = useState<Resolved | null>(null)
  useEffect(() => {
    let alive = true
    setFirst(null)
    resolvedOnce(id).then((r) => alive && setFirst(r))
    return () => {
      alive = false
    }
  }, [id])
  const kind: ChipKind = p ? chipKind(p) : first ? chipKind(first) : 'reference'
  /* The picture is decided by the first answer and drawn from it; the
     popover's reread may say the bytes have gone since, and then it is. */
  const pic = isPicture(p ?? first) ? (p ?? first) : null
  const name = pic ? (pic.label ?? pic.object ?? (said || pic.artifact?.name)) : undefined
  const figure = placed && !!pic
  /* On a figure's caption line the words are the caption's, so the mark is
     the reference itself, not the alt text a second time. */
  const look = chipLook(kind, id, figure ? undefined : said)
  const [live, setLive] = useState<string | null>(null)
  const show = async () => {
    if (!p?.collection || !p.object) return
    setLive(null)
    try {
      const got = await reveal(p.collection, p.object)
      setLive(got.revealed ? 'shown in Explorer on this machine' : `not shown: ${got.why ?? got.state}`)
    } catch (e) {
      setLive((e as Error).message)
    }
  }
  const chip = (
    <>
      <button
        ref={at}
        className={look.className}
        title={look.title}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.stopPropagation()
          setPin(!pin)
        }}
      >
        {(!figure && said) || shortId(id, id.length)}
      </button>
      {shown && (
        <Floating>
          <span
            className="ref-pop acq-pop"
            role={pin ? 'dialog' : 'tooltip'}
            style={anchored(at.current, 360)}
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => setOpen(false)}
          >
            {r.loading && !p && <span className="ref-title">reading the record…</span>}
            {p && !p.known && <span className="ref-title">nothing recorded under this reference</span>}
            {p && p.known && !acquired && (
              <>
                <span className="ref-kind">{p.what ?? 'an Admission'}</span>
                <span className="ref-title">{p.artifact?.name ?? id}</span>
              </>
            )}
            {p && acquired && (
              <>
                <span className="ref-kind">acquired · {p.connector_label}</span>
                <span className="ref-title">{p.label}</span>
                <span className="ref-meta">
                  <span>{p.collection_name}</span>
                  <span>swept {when(p.sweep?.at ?? p.admitted_at)}</span>
                </span>
                <span className="ref-note">
                  This observation · version {p.version?.n} of {p.version?.of}
                  {p.newer_exists ? '' : ' (the latest)'} · {bytes(p.size)}
                </span>
                {p.newer_exists && (
                  <span className="ref-note acq-newer">
                    Cited version {p.version?.n}; version {p.version?.of} was recorded later.{' '}
                    <button
                      className="link"
                      onClick={() => openInSources({ at: 'compare', a: id, b: p.latest! })}
                    >
                      Compare
                    </button>{' '}
                    ·{' '}
                    <button className="link" onClick={() => openInSources({ at: 'observation', ref: p.latest! })}>
                      Go to latest
                    </button>
                  </span>
                )}
                <span className="acq-actions">
                  <button className="btn" onClick={() => openInSources({ at: 'observation', ref: id })}>
                    Open in Sources
                  </button>
                  {p.live === 'local-reveal' && (
                    <button className="btn" onClick={show}>
                      Show live file
                    </button>
                  )}
                </span>
                {live && <span className="ref-note">{live}</span>}
              </>
            )}
            <span className="ref-id">{id}</span>
          </span>
        </Floating>
      )}
    </>
  )
  if (figure) {
    const caption = said || name
    return (
      <figure className="acq-placed">
        <AcquiredPicture id={id} label={caption} state={pic!.artifact?.state} placed />
        <figcaption className="acq-placed-cap">
          {caption && <span className="acq-placed-words">{caption}</span>}
          <span className="ref-wrap acq-wrap">{chip}</span>
        </figcaption>
      </figure>
    )
  }
  const wrap = (
    <span className={'ref-wrap acq-wrap' + (pic ? ' acq-figure' : '')}>
      {pic && <AcquiredPicture id={id} label={name} state={pic.artifact?.state} />}
      {chip}
    </span>
  )
  return placed ? <p>{wrap}</p> : wrap
}
