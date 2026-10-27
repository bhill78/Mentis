/* THE DECISIONS ON A POST, UNDER IT (forms build P9). Fluid's conversation
 * column, its thread sheet and full screen draw a post's decision forms
 * with the one form every view uses (experimental/types/decision.tsx),
 * answered there. Read only for a post that carries an ask or a decision
 * form, so a post that asks nothing costs nothing. A click or a key inside
 * the form is the form's: it does not read the post it is on. */
import { DecisionsOn } from '../../experimental/types/decision'
import { store, type Post } from '../store'

export default function PostDecisions({ post }: { post: Post }) {
  if (post.deleted || (!post.expectations?.length && !post.decision_forms?.length)) return null
  return (
    <div className="fx-decisions" data-decisions-on={post.id}
      onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
      {/* READ AGAIN WHEN THE POST'S ASKS CHANGE: the form reads its own
          data once, so a decision form raised on a post already drawn (an
          agent's permission question, a run's decision) keys a fresh read. */}
      <DecisionsOn key={[...(post.expectations ?? []), ...(post.decision_forms ?? [])].join(',')}
        post={post.id} onChanged={() => { void store.step().catch(() => {}) }} />
    </div>
  )
}
