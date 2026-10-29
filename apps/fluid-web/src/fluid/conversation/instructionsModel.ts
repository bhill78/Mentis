import type { Id } from '../store'

export interface ConversationInstructionRow {
  entry: Id
  kind: string
  text: string
  placed: ('conversation' | 'whole-brain')[]
  attributed_to?: Id | null
  written_by?: string | null
  proposed?: {
    successors: {
      items: { entry: Id; summary: string | null; by_alias: string | null }[]
    }
  } | null
}

export interface ConversationInstructionsRead {
  conversation: Id
  governing: ConversationInstructionRow[]
  candidates: ConversationInstructionRow[]
  ended: ConversationInstructionRow[]
  replaced: ConversationInstructionRow[]
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
): ConversationInstructionGroups {
  const local = (rows: ConversationInstructionRow[] = []) => rows.filter((row) =>
    row.kind === 'conversation-instruction' && row.placed.includes('conversation'))
  const current = local(read?.governing)
  const proposedEdits: ConversationInstructionRow[] = current.flatMap((row) =>
    row.proposed?.successors.items.map((item) => ({
      entry: item.entry,
      kind: 'conversation-instruction',
      text: item.summary ?? 'Instruction with no display text',
      placed: [],
      written_by: item.by_alias,
    })) ?? [])
  return {
    current,
    pending: [...local(read?.candidates), ...proposedEdits],
    history: [...local(read?.ended), ...local(read?.replaced)],
  }
}

export const instructionsPath = (conversation: Id) =>
  `/api/conversations/${encodeURIComponent(conversation)}/governs`

export function establishInstructionBody(text: string, attributedTo: Id) {
  return { text: text.trim(), attributed_to: attributedTo, establish: true as const }
}
