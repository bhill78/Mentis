/* PACKAGE G owns this module. Its mount is in the header's right cell, where
   Chrome.tsx renders it, so G adds a background control without editing A's
   file. It renders nothing at P0: before G, Quiet offered no such control,
   and a seam commit adds no interface of its own. */
export default function BackgroundControl() {
  return null
}
