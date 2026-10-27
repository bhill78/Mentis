/* Where work stands, in the owner's words. The server derives the stage and
   says its words (`stage_words`); this only names each stage for a heading
   or a filter, orders them, and cuts the server's phrase into its leading
   word and the detail after it. Nothing is reworded. */
import type { WorkItem, WorkStage } from './contract'

/** The order stages are listed in: what needs attention first. */
export const STAGE_ORDER: WorkStage[] = [
  'blocked', 'awaiting_owner', 'building', 'awaiting_review', 'parked', 'ready_to_deploy',
  'deployed', 'ended', 'not_started', 'unknown',
]

export const STAGE_LABEL: Record<WorkStage, string> = {
  blocked: 'Blocked',
  awaiting_owner: 'Needs your decision',
  building: 'Building',
  awaiting_review: 'Awaiting review',
  parked: 'Parked',
  ready_to_deploy: 'Ready to deploy',
  deployed: 'Deployed',
  ended: 'Answered',
  not_started: 'Not started',
  unknown: 'Unknown',
}

/** The server's stage words cut into the leading word and what follows:
 *  "Blocked: the review found problems" is "Blocked" and "the review found
 *  problems"; "Repaired · re-review needed" is "Repaired" and "re-review
 *  needed". Null when the item carries no stage (an older server). */
export function stageParts(item: WorkItem): { stage: WorkStage; word: string; detail: string } | null {
  if (!item.stage || !item.stage_words) return null
  const words = item.stage_words
  const m = /^(.*?)(?::\s+|\s+·\s+|\s+—\s+)(.*)$/.exec(words)
  return { stage: item.stage, word: m ? m[1] : words, detail: m ? m[2] : '' }
}

/** The stages present in a read, with their counts, in STAGE_ORDER. */
export function stagesPresent(counts: Partial<Record<WorkStage, number>> | null | undefined): [WorkStage, number][] {
  if (!counts) return []
  return STAGE_ORDER.filter((s) => (counts[s] ?? 0) > 0).map((s) => [s, counts[s] ?? 0])
}
