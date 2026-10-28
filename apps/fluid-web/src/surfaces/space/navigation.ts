/* The 3D Brain keeps Mark IV's address inside Fluid, `#/brain/space`, beside
 * Manage Sources' `#/brain/sources`. Browser-free so the address is testable. */

export const SPACE_HASH = '#/brain/space'

/** Whether this hash is the 3D Brain. */
export function atSpace(hash: string): boolean {
  return hash === SPACE_HASH || hash === SPACE_HASH + '/'
}
