import type { Dangling } from './linked'
export default function LinkWarning({ links, onFix }: { links: Dangling[]; onFix: (link:Dangling)=>void }) {
  if(!links.length)return null
  return <div className="linkwarn"><b>🔗 Links to rows Mentis won't hold</b>{links.map((l,i)=><p key={i}>
    {l.kind==='filtered'?<>Some <code>{l.child}</code> rows link to <code>{l.parent}</code> rows that your <code>{l.parent}</code> rule leaves out. Mentis records those links as pointing into this collection, but it does not hold those rows, so following such a link finds nothing.</>
      :l.kind==='untaken'?<>Some <code>{l.child}</code> rows link to <code>{l.parent}</code>, which you aren't taking. Mentis does not hold those rows.</>
      :<><code>{l.child}.{l.column}</code> is left out, so Mentis won't record which <code>{l.parent}</code> row each <code>{l.child}</code> row links to.</>}{' '}
    <button className="link" onClick={()=>onFix(l)}>{l.kind==='filtered'?`Check ${l.parent}'s filters`:l.kind==='untaken'?`Take ${l.parent}`:`Take ${l.column} again`}</button>
  </p>)}</div>
}
