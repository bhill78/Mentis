import type { Id } from '../store'

export interface ConversationInstructionRow {
  entry: Id
  kind: string
  state: 'candidate' | 'stands' | 'ended' | 'replaced' | null
  group: 'proposed' | 'recorded' | 'standing' | 'history' | 'unknown'
  summary: string
  author_alias: string | null
  placed_at: { conversation: Id; whole_brain?: boolean }[]
  proposed_by: { conversation: Id | null }[]
  proposed_reach?: Id[]
}

export interface ConversationInstructionsRead {
  groups: Record<string, ConversationInstructionRow[]>
  omitted?: Record<string, number>
  error?: string
}

export interface ConversationInstructionGroups {
  current: ConversationInstructionRow[]
  pending: ConversationInstructionRow[]
  history: ConversationInstructionRow[]
}

/** One governed read, narrowed to conversation instructions only. Placement,
 * proposal origin and intended reach are all explicit API facts; no text is
 * interpreted to decide whether an instruction belongs here. */
export function instructionGroups(
  read: ConversationInstructionsRead | null,
  conversation: Id,
): ConversationInstructionGroups {
  const seen = new Set<Id>()
  const rows = Object.values(read?.groups ?? {}).flat().filter((row) => {
    if (row.kind !== 'instruction' || seen.has(row.entry)) return false
    seen.add(row.entry)
    return row.placed_at.some((p) => p.conversation === conversation || p.whole_brain === true) ||
      row.proposed_by.some((p) => p.conversation === conversation) ||
      row.proposed_reach?.includes(conversation) === true
  })
  return {
    current: rows.filter((row) => row.state === 'stands'),
    pending: rows.filter((row) => row.state === 'candidate'),
    history: rows.filter((row) => row.state === 'ended' || row.state === 'replaced'),
  }
}

export const instructionsPath = '/api/governed?kind=instruction&limit=500'

export function establishInstructionBody(text: string, attributedTo: Id) {
  return { text: text.trim(), attributed_to: attributedTo, establish: true as const }
}
