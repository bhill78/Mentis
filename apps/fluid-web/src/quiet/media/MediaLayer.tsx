/* PACKAGE F owns this module: the gallery overlay, mounted once beside the
   shell so it can sit above everything without any package being inside
   another's markup. It renders nothing at P0: before F, Quiet had no
   lightbox, and a seam commit adds no interface of its own. */
export default function MediaLayer() {
  return null
}
