import type { CentreAt, Place } from '../address'
import type { MagnetResource } from './contract'

/** Only ids and origin references travel in browser history. Reads, drafts,
 * positions and DOM focus stay in the common registry's disposable resource. */
export interface MagnetIntent {
  brainKey: string; resourceId: string; magnetId: string;
  origin: { conversation: string; post?: string; thread?: string };
  phase: 'details' | 'inspect';
  target?: { conversation: string; post?: string };
}
export interface MagnetOrigin {
  place: Place; thread: string | null; at: string | null;
  scroll: number; anchor: string | null; anchorOffset: number | null;
  draftTarget: string | null; focus: HTMLElement | null;
  replyId?: string;
}
export interface QuietMagnetResource extends MagnetResource { origin: MagnetOrigin }
export function magnetIntent(r: QuietMagnetResource, target?: MagnetIntent['target']): CentreAt {
  return { magnet: { brainKey: r.brainKey, resourceId: r.id, magnetId: r.saved.id,
    origin: { conversation: r.origin.place.c!, ...(r.origin.anchor ? { post: r.origin.anchor } : {}), ...(r.origin.thread ? { thread: r.origin.thread } : {}) },
    phase: target ? 'inspect' : 'details', ...(target ? { target } : {}) } }
}
export function resumeMagnet(to: MagnetIntent, key: string | null, find: (id: string) => QuietMagnetResource | null) {
  if (!key || key !== to.brainKey) return { how: 'other-brain' as const }
  const resource = find(to.resourceId)
  return resource && resource.brainKey === key && resource.saved.id === to.magnetId
    ? { how: 'live' as const, resource }
    : { how: 'expired' as const, origin: to.origin.conversation }
}
