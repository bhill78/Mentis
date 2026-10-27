import type { WorkItem } from './contract'

/** Preserve the server's phrase; only the part asking for the viewer gets coral. */
export default function StatusWords({ item }: { item: WorkItem }) {
  return <>{item.status_words.split(/(·)/).map((part, i) =>
    <span key={i} className={item.group === 'needs_you' && /\byou\b|\byour\b|\bdecisions?\b|\bquestions?\b|\bapproval\b/i.test(part) ? 'work-attention' : undefined}>{part}</span>)}</>
}
