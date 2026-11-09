/* WHO IS WORKING, AND ON WHICH POST (combined refinement).
 *
 * Read from Mentis's own activity, through Fluid's one reader
 * (`fluid/identity/activity.ts`: `/api/activity`, woken by the pulse): a
 * live run, the conversation it runs in, and the post its acts are recorded
 * against (`working_on`) -- the record's association, never a guess. Quiet
 * shows it twice and nowhere else: a line under each composer (who is working
 * in that conversation) and a small mark beside the post being worked on.
 *
 * THE SAMPLE IS NOT A BRAIN. Its conversation shows two agents at work so the
 * presentation can be judged; those rows are made up here and marked as such
 * (`simulated`). Real conversations show only what `/api/activity` says. */
import { live, useActivity, type Activity } from '../fluid/identity/activity'
import { PEOPLE, type Id } from './sample'

export interface Working {
  /** the run, else the participant: what tells two entries apart */
  key: string
  participant: Id
  alias: string
  runtime: string | null
  /** the post its work is recorded against, where the record says */
  post: Id | null
  conversation: Id | null
  /** what the run says it is doing now, in its own words */
  doing: string | null
  simulated?: boolean
}

const of = (a: Activity): Working => ({
  key: a.run ?? a.participant,
  participant: a.participant,
  alias: a.alias,
  runtime: a.runtime ?? null,
  post: a.working_on?.turn ?? null,
  conversation: a.conversation ?? a.working_on?.conversation ?? null,
  doing: a.runs?.[0]?.words ?? a.runs?.[0]?.activity ?? null,
})

/** The sample conversation's made-up work, for judging the presentation. */
const SAMPLE: Working[] = [
  { key: 'sample-quill', participant: PEOPLE.quill.id, alias: PEOPLE.quill.name, runtime: 'claude', post: 'p3', conversation: 'sample', doing: 'drafting three invitations', simulated: true },
  { key: 'sample-reviewer', participant: PEOPLE.reviewer.id, alias: PEOPLE.reviewer.name, runtime: 'codex', post: 'p5', conversation: 'sample', doing: 'checking the site figures', simulated: true },
]

/** Everyone working now, one entry per run (the sample's simulated work
 *  included when `sample` is asked for). */
export function useWorking(sample: boolean): Working[] {
  const all = useActivity()
  const real = live(all).map(of)
  return sample ? [...real, ...SAMPLE] : real
}

/** Who is working in `conversation` ('sample' for the sample). */
export const workingIn = (ws: Working[], conversation: Id | null) =>
  conversation ? ws.filter((w) => w.conversation === conversation) : []

/** Who is working on `post`. */
export const workingOn = (ws: Working[], post: Id) => ws.filter((w) => w.post === post)
