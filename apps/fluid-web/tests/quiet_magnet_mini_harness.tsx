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
/* AS THE SERVER'S OWN TURN VIEW GIVES IT (`mentis/web/__init__.py`
   `_turn_view`): `topics`, `root`, `written_by` and `addressees` come with
   every Turn, and the card now draws the Turn with Mentis's own post, which
   reads them. A fixture that left them out was not a smaller read, it was a
   shape the server never answers. */
const turn=(n:number,text=n===2?'Synthetic post 2, with **strong** words.':`Synthetic post ${n}.`)=>({id:`ent-reviewpost${n}11`,number:n,author:ME,author_alias:'@fixture',written_by:null,at:1795000000,parts:[{type:'text',text}],topics:[],root:`ent-reviewpost${n}11`,addressees:[],replies:[],thread_replies:1,deleted:null,
 expectations:n===1?[{id:'opr-fixture',expects:'Synthetic request',of:null,of_alias:null,by_alias:'@fixture',unassigned:true,response_present:false,live_execution:false}]:[]})
/* What a Conversation search result does to the card (`MagnetSearchTarget`):
    the exact message it meant. The index and the search overlay are not in
    this fixture; the target they write is. */
const api:any={target:(message:string)=>r.update({searchTarget:{kind:'Conversation',message}}),snapshot:()=>state,calls:[],records:new Map(),resolve:null,mode:'immediate',brain:'review-instance',reply:false,canWrite:true,reads:0,threadReads:0}
;(window as any).review=api
window.fetch=async(input:any,init:any={})=>{
 const path=String(input), response=(body:any)=>new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
 if(path.startsWith('/api/pulse'))return response({token:api.reply?'2/1':'1/1',moved:api.reply?{conversations:[OWN],executions:[],governed:false,people:false,loose:false}:null})
 if(path==='/fluid/api/needs-you/brain')return response({brain:{corpus_id:'review-corpus',instance:api.brain}})
 if(path.startsWith('/fluid/api/participants'))return response({me:ME,participants:[{id:ME,alias:'@Owner',default_runtime:null,runtime_mode:'undeclared'},{id:AGENT,alias:'@FixtureAgent',default_runtime:null,runtime_mode:'undeclared'}]})
 if(path==='/api/personas')return response({personas:[]})
 /* WHAT A REFERENCE AN AGENT TYPED RESOLVES TO. Mentis's own reference
    component reads this once its explanation is asked for, and the card draws
    a post's words with it now, so the fixture answers it as the server does. */
 if(path.startsWith('/api/entries/'))return response({id:path.slice('/api/entries/'.length),missing:false,kind:'conversation post',author_alias:'@fixture',at:1795000000,stands:true,meaning:'a post captured in this fixture'})
 if(path.startsWith('/api/references'))return response({known:false,why_not:'the fixture holds no acquired provenance'})
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
 /* A thread read names its root and answers with that Turn and the posts under
    it, which is what the server answers (`/api/conversations/<c>/thread/<id>`)
    and what the shared thread reader reads. */
 if(path.includes('/thread/')){
  api.threadReads++
  const asked=path.split('/thread/')[1].split('?')[0]
  /* THE SERVER NAMES A REPLY'S ROOT when asked for that reply's thread, which
     is how a message found in the search is opened where it actually is: post
     3 is the reply under post 1 and is in no page the card has read. */
  const replyId='ent-reviewpost311'
  const root=asked===replyId?'ent-reviewpost111':asked
  const n=Number(/ent-reviewpost(\d+)11/.exec(root)?.[1] ?? 1)
  const reply={...turn(3,'Actual fixture thread reply adm-cccc2222dddd'),answering:root,answering_number:n,root,thread_replies:0,replies:[]}
  /* The root names what answers it, as the server's Turn view does (`replies`):
     the shared thread reader draws the posts under a root from that list. */
  return response({conversation:OWN,root,turn:{...turn(n),id:root,replies:[reply.id],thread_replies:1},replies_total:1,replies:[reply]})
 }
 if(path.startsWith(`/api/conversations/${OWN}`)){
  api.reads++
  return response({id:OWN,name:'Synthetic Magnet conversation',participants:[{participant:AGENT,alias:'@FixtureAgent',default_runtime:null,runtime_mode:'undeclared'}],topics:[],turns:[turn(1),turn(2),...(api.reply?[turn(3,'Fixture agent reply ent-aaaa1111bbbb adm-cccc2222dddd')]:[])],turns_total:api.reply?3:2,owed:[{}],batch:{older:0,first:1}})
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
