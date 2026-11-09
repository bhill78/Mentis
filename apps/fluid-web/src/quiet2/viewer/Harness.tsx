/* A bare stage for each renderer, so it can be built and checked on its own:
 * /quiet2?harness=pdf[&placement=column] or /quiet2?harness=gallery.
 * Real content from the dev Brain: the test PDFs posted as #749 in "Markdown
 * Renderer Maturation", and the fourteen pictures of #569 in "Mentis UI/UX".
 * Not part of the product; the viewer frame (Viewer.tsx) is. */
import { useEffect, useState } from 'react'
import { CLIENT_HEADERS, type Conversation } from '../../api'
import { itemOf } from '../../quiet/media/view'
import GalleryView from './GalleryView'
import PdfView from './PdfView'
import { GALLERY_START, PDF_START, type GalleryState, type PdfState, type ViewImage } from './types'
import './viewer.css'

export const TEST_PDFS = [
  { url: '/api/artifacts/adm-f08af15bacac', name: 'mentis-viewer-test-report.pdf' },
  { url: '/api/artifacts/adm-9762b9cb41e9', name: 'mentis-viewer-test-landscape.pdf' },
]

export default function Harness({ kind }: { kind: string }) {
  const q = new URLSearchParams(location.search)
  const placement = q.get('placement') === 'column' ? 'column' : 'max'
  const which = Number(q.get('pdf') ?? 0)
  const [pdf, setPdf] = useState<PdfState>(PDF_START)
  const [gal, setGal] = useState<GalleryState>(GALLERY_START(0))
  const [images, setImages] = useState<ViewImage[]>([])
  useEffect(() => {
    if (kind !== 'gallery') return
    fetch('/api/conversations/ent-0a1a163beb3a?batch=1&around=569', { headers: CLIENT_HEADERS })
      .then((r) => r.json() as Promise<Conversation>)
      .then((c) => {
        const t = c.turns.find((x) => x.number === 569)
        setImages((t?.parts ?? []).map((p) => itemOf(p)).filter((i) => i && i.kind === 'image').map((i) => ({ url: i!.url, name: i!.name, alt: i!.alt })))
      })
  }, [kind])
  return (
    <div className="q2 fx" style={{ display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', width: placement === 'column' ? 520 : '100%', margin: '0 auto', border: '1px solid var(--line)' }}>
        {kind === 'pdf'
          ? <PdfView url={TEST_PDFS[which]?.url ?? TEST_PDFS[0].url} name={TEST_PDFS[which]?.name ?? ''} state={pdf} onState={setPdf} placement={placement} />
          : images.length ? <GalleryView images={images} state={gal} onState={setGal} placement={placement} /> : <p>Reading the pictures…</p>}
      </div>
    </div>
  )
}
