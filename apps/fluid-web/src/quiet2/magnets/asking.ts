/* The real Composer owns addressing, split send and Work permissions. This
 * adapter owns only the Magnet's isolated draft, the destination of send, and
 * the attached discussion reference it carries onto the submitted message. */
import type { WorkspaceAsking } from '../../fluid/Composer'
import type { MagnetResource } from './contract'
import { carryContext, miniComposerDraft, miniComposerWhere, saveMiniComposer, subscribeMiniComposer,
  type MiniConversation } from './conversation'

export function miniAsking(resource: MagnetResource, conversation: MiniConversation): WorkspaceAsking {
  const where = miniComposerWhere(resource)
  return {
    where, key: where, heading: 'Message this Magnet',
    magnetAuthorization: { allowed: () => resource.snapshot().context?.kind !== 'perspective' },
    drafts: {
      load: () => miniComposerDraft(resource),
      save: (draft) => saveMiniComposer(resource, draft),
      subscribe: (changed) => subscribeMiniComposer(resource, changed),
    },
    /* Exact authored parts and separately versioned selectors are frozen
       together under this operation key. No generated context becomes prose. */
    send: async (post, op, brain) => {
      if (post.magnet_authorization && !conversation.conversation) {
        await conversation.createOwn()
        if (!conversation.conversation) throw new Error(conversation.snapshot().sendError
          ?? 'The Magnet Conversation must be confirmed before authorizing this exchange.')
      }
      carryContext(resource, op)
      await conversation.submit(post, op, brain)
      // submit reports refusal/uncertainty in its store. The Composer must keep
      // this explicit choice until the store confirms this exact send.
      if (post.magnet_authorization && conversation.snapshot().sent?.op !== op)
        throw new Error(conversation.snapshot().sendError ?? 'This exchange is not confirmed. Keep the original choice and retry unchanged.')
    },
  }
}
