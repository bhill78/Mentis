import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import MiniConversation from '../src/quiet2/magnets/MiniConversation'
import { page } from '../src/brainBinding'
import '../src/quiet2/magnets/magnet.css'

const OWN='ent-reviewown111', ME='ent-reviewowner1'
page.saw('review-corpus@review-instance')
const r:any={id:'review-browser',brainKey:'http://synthetic.invalid||review-corpus',saved:{id:'mag-review',name:'Synthetic Magnet',config:{conversation:OWN,sources:[{kind:'conversation',conversation:'ent-reviewsource'}]}}}
const turn=(n:number)=>({id:`ent-reviewpost${n}11`,number:n,author:ME,author_alias:'@fixture',at:1795000000,parts:[{type:'text',text:`Synthetic post ${n}.`}],replies:[],thread_replies:1,expectations:n===1?[{id:'opr-fixture',expects:'Synthetic request',of:null,by_alias:'@fixture',unassigned:true}]:[]})
const api:any={calls:[],records:new Map(),resolve:null,holdOlder:null,olderCalls:0,threadCalls:0,threadResolvers:[],mode:'send'}
;(window as any).review=api
window.fetch=async(input:any,init:any={})=>{
  const path=String(input)
  const response=(body:any)=>new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
  if(path==='/fluid/api/needs-you/brain')return response({brain:{corpus_id:'review-corpus',instance:'review-instance'}})
  if(path.includes('participants'))return response({me:ME,participants:[{id:'ent-reviewagent1',alias:'@FixtureAgent',default_runtime:'codex',runtime_mode:'default'}]})
  if(path.endsWith('/collection'))return response({magnet:r.saved.id,config:r.saved.config,activation:{post:'ent-reviewcollect',at:1795000000,state:'retained',artifact:{ref:'adm-reviewbatch1',digest:'captured',size:42,media_type:'application/json'}},page:{sources:[]}})
  if(path==='/fluid/api/posts'||path==='/fluid/api/requests'){
    const body=JSON.parse(init.body);api.calls.push({path,body,headers:init.headers})
    if(!api.records.has(body.op))api.records.set(body.op,{post:`ent-reviewrecord${api.records.size+1}`,number:api.records.size+1})
    const answer=api.records.get(body.op)
    if(api.calls.length===1)return new Promise(resolve=>{api.resolve=()=>resolve(response(answer))})
    return response({...answer,replayed:api.calls.filter((c:any)=>c.body.op===body.op).length>1})
  }
  if(path.includes('/thread/')){
    const index=api.threadCalls++
    return new Promise(resolve=>{api.threadResolvers[index]=(text:string)=>resolve(response({replies:[{...turn(3),parts:[{type:'text',text}]}]}))})
  }
  if(path.startsWith(`/api/conversations/${OWN}`)){
    const body={id:OWN,name:'Synthetic Magnet conversation',turns:[turn(1),turn(2)],turns_total:32,owed:[{}],batch:{older:30,first:31}}
    if(path.includes('before=')){api.olderCalls++;return new Promise(resolve=>{api.holdOlder=()=>resolve(response({...body,batch:{older:0,first:1}}))})}
    return response(body)
  }
  throw Error(`Fixture refused unexpected fetch: ${path}`)
}
function App(){const[show,setShow]=useState(true);return <main className="q2" style={{fontFamily:'sans-serif',background:'#191b1f',minHeight:'100vh',padding:20,color:'#eee8e6'}}>
  <button id="toggle" onClick={()=>setShow(!show)}>{show?'Collapse fixture':'Reopen fixture'}</button>
  <div className="q2-magnet" style={{position:'relative',width:620,height:760,marginTop:20}}><button className="q2-magnet-puck">M</button>
  {show&&<div className="q2-magnet-card" style={{top:30,left:30,width:560,maxHeight:700}}><header><h2>Synthetic Magnet</h2></header><MiniConversation resource={r} canWrite={true} onFull={()=>{api.full=true}} onEvidence={(ref)=>{api.evidence=ref}}/></div>}</div>
  </main>}
createRoot(document.getElementById('root')!).render(<App/> )
