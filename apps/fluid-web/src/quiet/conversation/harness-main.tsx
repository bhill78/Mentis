import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QuietConversationHarness } from './QuietConversationHarness'

/* Dev-only entry for `quiet-postview.html` (project root), served only by
 * `npm run dev` -- not part of the real app's bundle (`index.html` still
 * loads `src/fluid/main.tsx`), and not referenced by anything under
 * `quiet/shell/`. Exists so Track C's component is viewable before Track
 * A's shell is. */
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QuietConversationHarness />
  </StrictMode>,
)
