// Independent wiring: expressions read from the candidate handoff, baseline
// prelude retained by its 'unchanged' instruction; real history and binding.
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {M,historyFixture,variable,property,evaluate} from './fixture.mjs'
import ts from '../node_modules/typescript/lib/typescript.js'
export const baseline=readFileSync(new URL('../src/quiet2/Quiet2.tsx',import.meta.url),'utf8')
export function exactHost({overlay=false}={}) {
 const x=historyFixture({unfinished:false}), calls=[], state={conversation:'ent-origin',content:'real',pending:null,question:null,thread:null,reply:'draft-reply',surfaces:{s1:null,s2:null}}, asking={current:0}, pendingPost={current:null}
 const setter=name=>v=>{calls.push([name,v]);state[name]=v}
 const guarded=evaluate(variable('guarded'),{leaving:()=>({ask:{title:'synthetic unfinished'}}),unfinished:()=>null,setLeave:q=>{state.question=q},setNotice:setter('notice'),CENTRE:'centre'})
 const arrive=evaluate(variable('arrive',baseline),{setBrainOpen:setter('brain'),setSourcesOpen:setter('sources'),setBrainReturn:setter('return'),realId:'ent-origin',brainLeft:{current:42},centre:x.centre,setRealId:setter('conversation'),setContent:setter('content'),saveWorkspace:setter('workspace')})
 // The documented pickConversationFor omits only the existing sample/beside prelude.
 // Splice exactly that prelude into the exact documented function, not a fake route.
 const old=variable('pickConversation',baseline)
 const prelude=old.slice(old.indexOf('{')+1,old.indexOf('guarded(() => arrive(k, then))'))
 let pickExpr=variable('pickConversationFor')
 const omitted=/\/\*[^*]*unchanged: the sample refusal, the surface beside, its notice[^*]*\*\//
 assert.match(pickExpr,omitted);pickExpr=pickExpr.replace(omitted,prelude)
 const pickFor=evaluate(pickExpr,{isReal:true,CONVERSATIONS:[],setNotice:setter('notice'),surfacePanes:[],placeOf:()=>null,surfaces:{},setSurfaces:setter('surfaces'),guarded,arrive,CENTRE:'centre'})
 const pick=evaluate(variable('pickConversation'),{pickConversationFor:pickFor})
 let rootResolve,readResolve
 const document={querySelector:()=>null}
 const sf=ts.createSourceFile('baseline.tsx','const p = '+variable('page',baseline),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX)
 const obj=sf.statements[0].declarationList.declarations[0].initializer
 const onEnterExpr=obj.properties.find(p=>p.name?.getText(sf)==='onEnter').initializer.getText(sf)
 const onEnter=evaluate(onEnterExpr,{postOf:()=>({conversation:'ent-origin'}),surfacePanes:[],document,entered:null,left:{current:null},replyTo:null,setEntered:setter('thread'),setEnteredAt:setter('at'),setReplyTo:setter('reply'),setSurfaces:f=>{calls.push(['surfaces']);state.surfaces=f(state.surfaces)},holds:()=>false,setNotice:setter('notice')})
 const now={current:{realId:'ent-origin',page:{onEnter}}}
 const showPost=evaluate(variable('showPost'),{document,revealPost:p=>calls.push(['reveal',p]),asking,threadRootOf:()=>new Promise(r=>{rootResolve=r}),readThread:()=>new Promise(r=>{readResolve=r}),now,setNotice:setter('notice')})
 const openFromDock=evaluate(variable('openFromDock'),{isReal:true,content:'real',realId:'ent-origin',brainMain:overlay,sourceMain:false,brainOpen:false,sourcesOpen:false,pickConversationFor:pickFor,pickConversation:pick,showPost,pendingPost})
 Object.assign(x.page,{serving:undefined,conversation:()=>state.conversation,
  backTo:evaluate(property('backTo'),{guarded,centre:x.centre,CENTRE:'centre'}),
  record:evaluate(property('record'),{guarded,setBrainReturn:setter('return'),centre:x.centre,CENTRE:'centre'}),
  pickConversation:evaluate(property('pickConversation'),{pickConversationFor:pickFor}),
  openPost:evaluate(property('openPost'),{openFromDock}),
  putBack:evaluate(property('putBack'),{setEntered:setter('thread'),setEnteredAt:setter('at'),document,setReplyTo:setter('reply'),postOf:p=>({id:p,conversation:'ent-origin'})}),
 })
 x.m=M.mountResults(x.page)
 return Object.assign(x,{calls,state,asking,pendingPost,now,document,showPost,
  answer:how=>{const q=state.question;state.question=null;assert.ok(q);q[how]?.()},
  root:r=>{assert.equal(typeof rootResolve,'function');rootResolve(r)},
  read:()=>{assert.equal(typeof readResolve,'function');readResolve()},
  // CORRECTION (adm-33bc95d78f7a, F5): the documented effect now passes the
  // launch identity through with the callback, exactly as §1.2 patch 3 says.
  pendingEffect:()=>{const want=pendingPost.current;if(!want)return;pendingPost.current=null;showPost(want.conversation,want.post,want.done,want.may)},
 })
}
