/* PACKAGE A owns this module: the conversation's eyebrow, title and the topic
   it is focused on. At P0 it renders what Quiet rendered before the split, in
   the same place. A moves this into the header's centre cell
   (.qc-cell-title) and gives title, eyebrow and controls three distinct
   --qc-type-* steps; this file's props are the whole of what it needs. */
import './chrome.css'

export default function Heading({ name, topic }: {
  name: string | null
  /** the addressed topic's name; null while it is still being read, and
   *  undefined when no topic is addressed at all */
  topic?: string | null
}) {
  return <div>
    <p className="qc-eyebrow">Conversation</p>
    <h1>{name ?? 'Opening conversation…'}</h1>
    {topic !== undefined && <p className="qc-focus">{topic ? `# ${topic}` : 'Opening topic…'}</p>}
  </div>
}
