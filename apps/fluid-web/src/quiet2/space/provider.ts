/* WHERE THE GRAPH SESSION COMES FROM: one seam, set once.
 *
 * Quiet Chat never builds a session or a reader. Part A's module supplies
 * both; this holds it, so the registry and the host can be written, checked
 * and built before that module exists. At integration one call wires it:
 *
 *     import { createSpaceSession } from '../../surfaces/space/session'
 *     import SpaceSessionReader from '../../surfaces/space/SpaceSessionReader'
 *     provideSpaceSessions({ createSpaceSession, SpaceSessionReader })
 *
 * Until it is wired, asking for it REFUSES in the reader's words rather than
 * standing in for it: a stand-in session would be the "alternative session"
 * the contract forbids, and a graph drawn by nothing would look like a defect
 * in A's work rather than an unwired seam. */
import type { ComponentType } from 'react'
import type { CreateSpaceSession, SpaceSessionReaderProps } from './contract'

export interface SpaceSessionModule {
  createSpaceSession: CreateSpaceSession
  /** mounted once per live session; it owns the read (addendum §1) */
  SpaceSessionReader: ComponentType<SpaceSessionReaderProps>
}

let held: SpaceSessionModule | null = null

/** Part A's module, given to Quiet Chat once. */
export function provideSpaceSessions(mod: SpaceSessionModule) { held = mod }
/** What is wired now, or null. */
export const spaceSessions = (): SpaceSessionModule | null => held
/** Only for a check: forget it again. */
export function forgetSpaceSessions() { held = null }

/** What the reader is told where the graph module is not wired into this
 *  build. It is a build fact, not a Brain fact: it says so. */
export const NO_SESSIONS = 'The 3D Brain is not part of this build yet.'
