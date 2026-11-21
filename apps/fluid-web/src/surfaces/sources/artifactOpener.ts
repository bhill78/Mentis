/* OPENING A HELD ARTIFACT, WHERE THE HOST CAN (result navigation, part N-B).
 *
 * A reference to held bytes is drawn the same way everywhere -- in Fluid, in
 * archived Quiet, in Quiet2, in a fixture harness -- by one chip. Only some
 * of those hosts have a viewer to open it in. So the chip asks, through this
 * context, and when nobody answers it stays what it has always been: the
 * record's own account of the reference, with no action it cannot perform.
 *
 * It carries no navigation, no history and no viewer: a host lends one
 * function. That is deliberate. A chip in Fluid must not reach into Quiet2's
 * places, and a host that cannot open a file must not pretend it can.
 *
 * WHETHER THE BYTES ARE THERE IS THE RECORD'S ANSWER, not this context's: a
 * caller offers the action only for an Admission the record currently says
 * is `held`, and says what it is instead when it is not. */
import { createContext, useContext } from 'react'

export interface ArtifactOpener {
  /** open these exact held bytes; the label is what the words called it */
  open(ref: string, label?: string | null): void
}

export const ArtifactOpenerContext = createContext<ArtifactOpener | null>(null)

/** The host's opener, or null -- an ordinary, supported state. */
export const useArtifactOpener = (): ArtifactOpener | null => useContext(ArtifactOpenerContext)

/** What the record's state for held bytes means, in a person's words. An
 *  unknown state is said as itself rather than guessed at or hidden, so a
 *  future state never reads as "available". */
export function stateWords(state: string | null | undefined): string {
  switch (state) {
    case 'held':
    case 'ok':
      return 'held'
    case 'missing':
      return 'the record holds it, the bytes are missing'
    case 'held-but-missing':
      return 'held by the record, its bytes are gone'
    case 'held-but-corrupt':
      return 'held by the record, its bytes do not match'
    case 'not-held':
      return 'this Brain does not hold its bytes'
    case 'deleted':
      return 'deleted'
    case 'erased':
      return 'erased'
    case 'purged':
      return 'purged'
    case 'unreadable':
      return 'it could not be read'
    default:
      return state ? `its state is "${state}"` : 'its state is unknown'
  }
}

/** Whether a host may offer to open these bytes now: an opener was lent, and
 *  the record says the bytes are held. Nothing else qualifies. */
export const mayOpen = (opener: ArtifactOpener | null, state: string | null | undefined): boolean =>
  !!opener && state === 'held'
