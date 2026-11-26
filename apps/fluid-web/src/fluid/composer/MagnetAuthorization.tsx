import './magnetAuthorization.css'

/** An explicit choice for one send. Never a permission default or saved grant. */
export interface OutsideChoice { web: boolean; collection: string }
export const noOutside: OutsideChoice = { web: false, collection: '' }

export function authorizeMessage(body: Record<string, unknown>, choice: OutsideChoice, allowed: boolean): Record<string, unknown> {
  const opens: Record<string, string>[] = []
  if (choice.web) opens.push({ kind: 'runtime-web-search' })
  if (choice.collection.trim()) opens.push({ kind: 'collection', collection: choice.collection.trim() })
  if (!opens.length) return body
  if (!allowed) throw new Error('A saved question stays grounded in collected information. Remove the outside-source choice or discuss without the saved question.')
  if (body.action !== 'ask-mentis' && body.action !== 'ask-participant')
    throw new Error('Outside sources can be authorized for an asking exchange. Clear the choice to record only.')
  return { ...body, magnet_authorization: { opens } }
}

export default function MagnetAuthorization({ value, change, allowed, busy }: {
  value: OutsideChoice; change(value: OutsideChoice): void; allowed: boolean; busy: boolean
}) {
  return <fieldset disabled={busy} className="fc-magnet-authorization" aria-label="Outside sources for this exchange">
    <legend>Outside sources for this exchange only</legend>
    <label><input type="checkbox" checked={value.web} disabled={!allowed}
      onChange={(e) => change({ ...value, web: e.target.checked })} /> Allow runtime web search</label>
    <label>Allow a named acquired collection <input type="text" value={value.collection} disabled={!allowed}
      placeholder="Collection id" onChange={(e) => change({ ...value, collection: e.target.value })} /></label>
    {!allowed && <span className="fc-hint">Saved questions use collected information only.</span>}
    {!allowed && (value.web || value.collection) && <button type="button" onClick={() => change(noOutside)}>Clear outside sources</button>}
    <span className="fc-hint">The next exchange starts with no outside sources allowed.</span>
  </fieldset>
}
