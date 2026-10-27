/* Manage Sources keeps its established hash addresses inside Fluid.  These
 * helpers are deliberately browser-free so address behaviour is testable. */

const ROOT = '#/brain/sources'

export function sourcesPath(hash: string): string | null {
  if (hash === ROOT || hash === ROOT + '/') return ''
  return hash.startsWith(ROOT + '/') ? hash.slice(ROOT.length + 1) : null
}

export function sourcesHash(path: string): string {
  return ROOT + (path ? '/' + path : '')
}
