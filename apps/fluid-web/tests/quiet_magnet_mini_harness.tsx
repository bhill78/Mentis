/* Synthetic HTTP only; the UI is the real Composer, the real mini store and the
   real persistent composer bar. The card is drawn as the frame draws it: the
   Conversation view in the scrolling view area, the one composer in the footer
   slot below it. */
import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import MiniConversation from '../src/quiet2/magnets/MiniConversation'
import ComposerBar from '../src/quiet2/magnets/ComposerBar'
import Composer from '../src/fluid/Composer'
import { Layer } from '../src/fluid/frame/layer'
import { page } from '../src/brainBinding'
import { emptyPlaces } from '../src/quiet2/magnets/places'
import '../src/fluid/fluid.css'
import '../src/fluid/frame/frame.css'
import '../src/quiet2/quiet2.css'
import '../src/quiet2/magnets/magnet.css'
const OWN='ent-reviewown111', ME='ent-reviewowner1', AGENT='ent-reviewagent1'
page.saw('review-corpus@review-instance')
const noOwn = new URLSearchParams(location.search).has('no-own')
/* A whole resource: the card's working state is real state, because the chip,
   the reading choice and the way back are all written to it. */
let state:any={title:'Synthetic Magnet',loading:false,results:[],x:12,y:12,open:true,wide:false,tab:'Conversation',overlay:null,
 places:emptyPlaces(),query:'',searchType:'All',searchTarget:null,searchListScroll:0,lens:null,
 returnRoute:null,settingsReturn:null,context:null,contextSuppressed:false}
const heard=new Set<() => void>()
const r:any={id:'review-browser',brainKey:'http://synthetic.invalid||review-corpus',saved:{id:'mag-review',name:'Synthetic Magnet',config:{conversation:noOwn?null:OWN,sources:[{kind:'conversation',conversation:'ent-reviewsource'}]}},
 snapshot:()=>state,subscribe:(fn:()=>void)=>{heard.add(fn);return ()=>heard.delete(fn)},
 update:(change:any)=>{state={...state,...change};heard.forEach(fn=>fn());(window as any).review?.notify?.()},
 read:async()=>{},cancel:()=>{},dispose:()=>{}}
const turn=(n:number,text=`Synthetic post ${n}.`)=>({id:`ent-reviewpost${n}11`,number:n,author:ME,author_alias:'@fixture',at:1795000000,parts:[{type:'text',text}],replies:[],thread_replies:1,expectations:n===1?[{id:'opr-fixture',expects:'Synthetic request',of:null,by_alias:'@fixture',unassigned:true}]:[]})
const api:any={calls:[],records:new Map(),resolve:null,mode:'immediate',brain:'review-instance',reply:false,canWrite:true,reads:0,threadReads:0}
;(window as any).review=api
window.fetch=async(input:any,init:any={})=>{
 const path=String(input), response=(body:any)=>new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
 if(path.startsWith('/api/pulse'))return response({token:api.reply?'2/1':'1/1',moved:api.reply?{conversations:[OWN],executions:[],governed:false,people:false,loose:false}:null})
 if(path==='/fluid/api/needs-you/brain')return response({brain:{corpus_id:'review-corpus',instance:api.brain}})
 if(path.startsWith('/fluid/api/participants'))return response({me:ME,participants:[{id:ME,alias:'@Owner',default_runtime:null,runtime_mode:'undeclared'},{id:AGENT,alias:'@FixtureAgent',default_runtime:null,runtime_mode:'undeclared'}]})
 if(path==='/api/personas')return response({personas:[]})
 if(path.startsWith('/api/who/'))return response({designated_persona:null})
 if(path==='/api/execution')return response({runtimes:[],running:[],default_runtime:null})
 if(path==='/api/capacity')return response({runtimes:[]})
 /* The Perspectives seam the bar reads a durable lens through: none selected,
    so an ordinary message carries the ordinary marker and no lens. */
 if(path.includes('/perspectives'))return response({brain:'review-corpus@review-instance',magnet:r.saved.id,perspectives:[],selected:null,next:null})
 if(path.endsWith('/collection'))return response({magnet:r.saved.id,config:r.saved.config,activation:{post:'ent-reviewcollect',at:1795000000,artifact:{ref:'adm-reviewbatch1',digest:'captured',size:42,media_type:'application/json'}},page:{sources:[]}})
 if(path.endsWith('/conversation')&&init.method==='POST'){api.create={body:JSON.parse(init.body),headers:init.headers};r.saved.config.conversation=OWN;return response({conversation:OWN})}
 if(path==='/fluid/api/posts'||path==='/fluid/api/requests'){
  const body=JSON.parse(init.body);api.calls.push({path,body,headers:init.headers})
  if(!api.records.has(body.op))api.records.set(body.op,{post:`ent-reviewrecord${api.records.size+1}`,number:api.records.size+1})
  const answer=api.records.get(body.op)
  if(api.mode==='hold')return new Promise(resolve=>{api.resolve=()=>resolve(response(answer))})
  return response({...answer,replayed:api.calls.filter((c:any)=>c.body.op===body.op).length>1})
 }
 if(path.includes('/thread/')){api.threadReads++;return response({replies:[turn(3,'Actual fixture thread reply adm-reviewbatch1')]})}
 if(path.startsWith(`/api/conversations/${OWN}`)){
  api.reads++
  return response({id:OWN,name:'Synthetic Magnet conversation',participants:[{participant:AGENT,alias:'@FixtureAgent',default_runtime:null,runtime_mode:'undeclared'}],topics:[],turns:[turn(1),turn(2),...(api.reply?[turn(3,'Fixture agent reply ent-reviewpost111 adm-reviewbatch1')]:[])],turns_total:api.reply?3:2,owed:[{}],batch:{older:0,first:1}})
 }
 if(path.startsWith('/fluid/api/search'))return response({hits:[],more:false})
 throw Error(`Fixture refused unexpected fetch: ${path}`)
}
function App(){const[show,setShow]=useState(true);const[,bump]=useState(0);api.notify=()=>bump(n=>n+1);return <main className="q2" style={{fontFamily:'sans-serif',background:'#191b1f',minHeight:'100vh',padding:20,color:'#eee8e6'}}>
 <Layer/>
 <div id="main-composer" style={{width:'min(620px, 95vw)'}}><Composer conversation={OWN} replyTo={null} onClearReply={()=>{}} operations/></div>
 <button id="toggle" onClick={()=>setShow(!show)}>{show?'Collapse fixture':'Reopen fixture'}</button>
 <div className="q2-magnet" style={{position:'relative',width:'min(620px,95vw)',height:760,marginTop:20}}><button className="q2-magnet-puck">M</button>
 {show&&<div className="q2-magnet-card" style={{top:30,left:0,width:'min(560px, calc(100vw - 48px))',maxHeight:700}}>
  <header><h2>Synthetic Magnet</h2></header>
  <div className="q2-magnet-view"><MiniConversation resource={r} canWrite={api.canWrite} onFull={()=>{api.full=true}} onEvidence={(ref)=>{api.evidence=ref}}/></div>
  <ComposerBar resource={r} canWrite={api.canWrite}/>
 </div>}</div>
 </main>}
createRoot(document.getElementById('root')!).render(<App/> )
