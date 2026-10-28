/* AN OBJECT REFERENCE, DRAWN (Fluid final W4; DROP.md, owner decisions of
 * 2026-10-28). A post that carries an `object` part shows THAT object --
 * the original, in its originating post, drawn by the same MIUI renderer
 * every object is drawn by (workspace/ObjectBody.tsx) -- under a provenance
 * header, "▥ Adjusted XP · from Dungeons and Dragons #4 · claude", with the
 * one object action row and Open original. Nothing is copied: what is drawn
 * is read by its live address, as a kept object is.
 *
 * When the original no longer resolves (its post deleted, its key gone)
 * the reference still reads, from its own caption: "▥ Chart · Adjusted XP —
 * from Dungeons and Dragons #4 · claude · no longer available". Never a
 * substitute: nothing near it is drawn in its place.
 *
 * `draft`: a chip in the composer, before it is sent -- the same card,
 * compact, saying "added when you send". */

import { useContext, useEffect } from 'react'
import { store, type Post } from '../store'
import { useObject } from '../workspace/hooks'
import ObjectBody from '../workspace/ObjectBody'
import { ObjectActions } from '../objects/ObjectActions'
import { Actions } from './post'
import { isObjectPart, liveOf, provenance, whereOf, type ObjectRefPart } from './objectRef'
import './objectref.css'

export function ObjectRefCard({ part, draft, onRemove }: {
  part: ObjectRefPart
  /** drawn in a draft: compact, "added when you send" */
  draft?: boolean
  onRemove?: () => void
}) {
  const live = liveOf(part)
  const st = useObject(live)
  const actions = useContext(Actions)
  useEffect(() => {
    if (!store.objects.has(live)) void store.loadObject(live).catch(() => {})
    /* the renderer reads a block's names from its post */
    if (!store.posts.has(part.ref)) void store.loadPosts([part.ref]).catch(() => {})
  }, [live, part.ref])
  const gone = !!st && 'unresolved' in st
  const o = st && 'object' in st ? st.object : null
  const a = part.about ?? {}
  const home = a.home
  const openOriginal = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!home || e.ctrlKey || e.metaKey || e.shiftKey) return
    e.preventDefault()
    if (actions) actions.goHome(home, part.ref)
    else location.assign(`/fluid?c=${encodeURIComponent(home)}&t=${encodeURIComponent(part.ref)}`)
  }
  return (
    <section className={'or-card' + (draft ? ' or-draft' : '') + (gone ? ' or-gone' : '')}
      data-reference-state={gone ? 'unavailable' : o ? 'available' : 'reading'}
      data-address={o ? live : undefined} aria-label={provenance(part, !gone)}>
      <header className="or-head">
        <span className="or-prov" title={gone && st && 'unresolved' in st ? `${provenance(part, false)} (${st.unresolved})` : `${live}\n${part.exact}`}>
          {provenance(part, !gone)}
        </span>
        {!gone && !draft && (
          <span className="or-acts">
            <ObjectActions compact target={{ address: live, title: a.title ?? part.text, kind: a.kind ?? undefined, from: whereOf(a) }} />
            {home && (
              <a className="ob-act or-open" href={`/fluid?c=${encodeURIComponent(home)}&t=${encodeURIComponent(part.ref)}`}
                title={`Open original: ${whereOf(a)}`} aria-label={`Open the original in ${whereOf(a)}`} onClick={openOriginal}>
                <span aria-hidden="true">⇱</span>
              </a>
            )}
          </span>
        )}
        {onRemove && (
          <button type="button" className="or-remove" aria-label={`remove the reference to ${a.title ?? part.text}`} title="Remove this reference from the draft"
            onClick={(e) => { e.stopPropagation(); onRemove() }}>×</button>
        )}
      </header>
      {o && !gone && <div className={'or-body' + (draft ? ' or-mini' : '')}><ObjectBody o={o} size="compact" still={draft} /></div>}
      {!st && <div className="or-body or-wait" aria-busy="true" />}
      {draft && <small className="or-draft-status">added when you send</small>}
    </section>
  )
}

/** Every object reference a post carries, in order, each drawn. */
export function ObjectRefs({ post }: { post: Post }) {
  if (post.deleted) return null
  const refs = post.parts.filter(isObjectPart) as unknown as ObjectRefPart[]
  if (!refs.length) return null
  return <div className="or-refs">{refs.map((p, i) => <ObjectRefCard key={liveOf(p) + i} part={p} />)}</div>
}
