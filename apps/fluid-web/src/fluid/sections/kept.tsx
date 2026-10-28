/* -- Section: Kept ---------------------------------------------------------
 *
 * A zone showing `kept` keeps what is put in it, as a workspace zone that
 * keeps does (its `slot`, by live address, drawn through ../present): a post
 * dragged by its head, a picture from a post, a card from another kept zone,
 * or ◆ Keep. */

import { useEffect, useRef } from 'react'
import { liveRoot, store, type Id } from '../store'
import { Present, useBox } from '../present'
import BrainKept from '../brain/BrainKept'
import { isBrainRef } from '../brain/address'
import { askKeep, useKeeping, useLanded } from '../workspace/keep'
import { keepSlot, type Slot, type Zone } from '../workspace/tree'
import { registerSection, type SectionBodyProps } from './registry'

/** A kept zone's body: what was put in it, drawn as the workspace draws a
 *  zone's objects; empty, how to fill it, and only while empty (#568 3.3). */
function KeptBody({ z, onOpenPost, setSlot }: {
  z: Zone
  onOpenPost: (c: Id, p: Id) => void
  setSlot: (f: (s: Slot) => Slot, words?: string) => void
}) {
  const slot = z.slot ?? keepSlot()
  const body = useRef<HTMLDivElement | null>(null)
  const box = useBox(body)
  const keeping = useKeeping()
  const landed = useLanded(z.id)
  useEffect(() => {
    if (!landed) return
    const t = setTimeout(() => {
      const el = body.current?.querySelector(`[data-address="${CSS.escape(landed.address)}"]`) as HTMLElement | null
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }, 80)
    return () => clearTimeout(t)
  }, [landed])
  const fromBrain = slot.items.filter(isBrainRef)
  const items = slot.items.filter((a) => !isBrainRef(a)).map((address) => ({ address, kept: true, zone: z.id, page: 'home' }))
  /* Opened from Home, an object opens in its post's conversation, as every
     Home item does; a picture opens in the viewer, out of its card. */
  const open = (address: string) => {
    const post = liveRoot(address)
    const p = post ? store.posts.get(post) : undefined
    if (post && p?.home) onOpenPost(p.home, post)
    else if (post) void store.loadPosts([post]).then(() => { const q = store.posts.get(post); if (q?.home) onOpenPost(q.home, post) })
  }
  return (
    <div className="fw-kept-body" ref={body}>
      {fromBrain.length > 0 && (
        <BrainKept refs={fromBrain} zone={z.id} page="home"
          onRemove={(a) => setSlot((s) => ({ ...s, items: s.items.filter((x) => x !== a) }), `${z.name ?? 'Kept'} no longer keeps it.`)} />
      )}
      {items.length > 0 ? (
        <Present items={items} mode={slot.present} width={Math.max(0, box.w - 4)} height={Math.max(0, box.h - 4)}
          onOpen={(it) => open(it.address)} onKeep={(it, from) => askKeep(it, from)}
          onRemove={(it) => setSlot((s) => ({ ...s, items: s.items.filter((a) => a !== it.address) }), `${z.name ?? 'Kept'} no longer keeps it.`)} />
      ) : fromBrain.length === 0 ? (
        <div className="wk-empty" data-empty="kept">
          <span className="wk-empty-mark" aria-hidden="true">{'◆'}</span>
          <span>{keeping ? `Into ${z.name ?? 'Kept'}` : 'Drag a post or a picture here, or ◆ keep one from a post.'}</span>
        </div>
      ) : null}
    </div>
  )
}

function KeptZone({ z, onOpenPost, setSlot, chrome }: SectionBodyProps) {
  return chrome({ count: z.slot?.items.length, children: <KeptBody z={z} onOpenPost={onOpenPost} setSlot={setSlot} /> })
}

registerSection({ show: 'kept', name: 'Kept', body: KeptZone, kept: true })
