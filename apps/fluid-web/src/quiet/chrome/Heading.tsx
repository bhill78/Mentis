/* PACKAGE A owns this module: the conversation's eyebrow, title and the topic
   it is focused on, mounted in the header's centre cell (.qc-cell-title).
   chrome.css gives title, eyebrow and header controls three distinct
   --qc-type-* steps -- title largest, controls no larger than the eyebrow --
   so this file's props are the whole of what it needs. */
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
