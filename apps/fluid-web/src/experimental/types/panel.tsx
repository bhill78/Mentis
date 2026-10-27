/* EXPERIMENTAL: composition without an application language.

   A panel is a CONTAINER: its body is ordinary Markdown, and any marked
   blocks inside it (fenced with a SHORTER fence than the panel's own, as
   CommonMark requires) are drawn by their own types with their own state.
   The panel adds only what a composite needs: one heading, one arrangement
   choice, and one send-back that gathers every child's state together.

   The author writes blocks they already know, inside one more fence. There is
   no layout language, no wiring between children, no expressions. */
import type { TypeDef } from '../api'
import { blocksAt } from '../../blocks'
import { q } from '../util'
import { panelSpec } from '../spec/panel'

export const panel: TypeDef<string, never> = {
  ...panelSpec,
  Rich({ data, attrs, help, labelled }) {
    /* Where the host draws the leading heading as the label, it is drawn
       there once and not again here. The conversation draws it here. */
    let src = data
    if (labelled) {
      const first = blocksAt(data)[0]
      if (first?.kind === 'heading') src = data.replace(/\r\n?/g, '\n').split('\n').slice(first.end).join('\n')
    }
    return (
      <div className={'rb-panel' + (attrs.arrange === 'side-by-side' ? ' rb-panel-side' : '')}>
        <help.Nested src={src} scope={help.key} />
      </div>
    )
  },
  readable(data, a, _s, help) {
    /* Its own words stay, in order, with each part in its readable form where
       it sits: the readable form is what a reader gets when nothing can draw
       the panel, so it may not drop the prose (opr-f8fe9495d90f). */
    const out = a.title ? [`title: ${q(a.title)}`] : []
    out.push(`contains (its own text, and each part in its own readable form, current state included):`)
    out.push(help.nestedText(data, help.key))
    return out.join('\n')
  },
  handoff(data, _a, _s, help) {
    return { parts: help.nestedHandoff(data, help.key) }
  },
}
