import { createRoot } from 'react-dom/client'
import Magnet from '../src/quiet2/magnets/Magnet'
import { createMagnetResource } from '../src/quiet2/magnets/state'
import '../src/quiet2/magnets/host.css'

const source = 'ent-source123456', id = 'mag-cohesive'
const config = { id, sources: [{ kind: 'conversation', conversation: source }], conversation: 'ent-own123456', selection: {}, collection: { mode: 'one-time' }, synthesis: { mode: 'manual' }, notifications: { newItems: false, changes: false, failures: false }, presentation: { renderer: 'disc' } } as const
const results = Array.from({length:35}, (_,i) => ({ kind: 'post', id: `ent-post12345${i}`, version: `ent-post12345${i}`, conversation: source, number:i+1, value: { text:`Retained item ${i+1}: captured words belonging to this batch.\n`.repeat(10) } }))
results[0].value = { ...results[0].value, ...{parts:[{type:'text',text:results[0].value.text},{type:'file',ref:'adm-file123456',alt:'Retained file'}]} }
const resource = createMagnetResource({ id:'mg1', brainKey:'fixture|test|brain', saved: { id, name:'A long Magnet title that keeps its full accessible title while staying compact', config: config as any }, get: async () => ({status:200,body: {magnet:id,config,activation:{post:'ent-batch123456',artifact:{ref:'adm-batch123456'},at:1,state:'complete'},page:{sources:[{key:`conversation:${source}`,source:config.sources[0],status:'ok',results}]}}}) })
resource.update({pinned:true,x:32,y:32})
Object.assign(window,{cohesive:{resource}})
createRoot(document.getElementById('root')!).render(<div className="q2 q2-arr-one">
  <div className="q2-work-row" style={{height:'100vh',overflow:'auto',boxSizing:'border-box',background:'#ddd'}}><div style={{height:1800,width:'100%'}}>Surrounding Conversation</div></div>
  <div className="q2-magnet-canvas"><Magnet resource={resource} onExpand={()=>resource.update({expanded:true,pinned:true})} onCollapse={()=>resource.update({expanded:false,pinned:true})} onClose={()=>{}} onPost={()=>{throw new Error('unexpected main navigation')}} onFile={()=>{throw new Error('unexpected main navigation')}} onSource={()=>{}} onConversation={()=>{}} onOrigin={()=>{}} /></div>
</div>)
