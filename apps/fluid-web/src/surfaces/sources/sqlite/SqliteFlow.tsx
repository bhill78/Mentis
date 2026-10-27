import { useCallback, useEffect, useReducer, useState } from 'react'
import { post, type Id } from '../../../api'
import { Steps } from '../AddSource'
import { Confirm, Result, RunBar } from '../parts'
import PickSource from '../pick/PickSource'
import { baseName, remember, suggestedName } from '../pick/recent'
import { bytes, cancelRun, count, runToEnd, type CollectionView, type Descriptor, type Picker, type Preview, type RunView, type SourcesRoute, type SweepResult } from '../route'
import CheckBuild from './CheckBuild'
import FileCard from './FileCard'
import FolderMatches, { type Matches } from './FolderMatches'
import { consent, initial, reducer, scopeOf, selection, undecided, unchanged } from './flowState'
import LinkWarning from './LinkWarning'
import { danglingLinks, type Dangling } from './linked'
import ReviewSqlite from './ReviewSqlite'
import RunningTotal from './RunningTotal'
import { focusSecret } from './SecretChoice'
import SecretGate, { GateReason } from './SecretGate'
import TablePicker from './TablePicker'
import { config, type Inspect, type Sample } from './types'
import './sqlite.css'

export default function SqliteFlow({ descriptor, picker, me, go, onChanged, onStep, editing }: {
  descriptor: Descriptor; picker?: Picker; me: Id|null; go: (r:SourcesRoute)=>void; onChanged: ()=>void; onStep?: (step:number)=>void; editing?: CollectionView
}) {
  const [s,dispatch]=useReducer(reducer,{...initial,step:editing?2:1}), [name,setName]=useState(editing?.name??''), [nameEdited,setNameEdited]=useState(false)
  const [scan,setScan]=useState<Matches|null>(null), [pick,setPick]=useState(false), [run,setRun]=useState<RunView|null>(null)
  const [pickMode,setPickMode]=useState<'file'|'folder'|undefined>()
  const [error,setError]=useState(''), [busy,setBusy]=useState(false), [confirm,setConfirm]=useState(false), [partial,setPartial]=useState(false)
  const [phase,setPhase]=useState(''), [attempted,setAttempted]=useState('')
  const [result,setResult]=useState<SweepResult|null>(null), [because,setBecause]=useState('')
  const sel=selection(s), pending=undecided(s)
  const step=(n:number)=>{dispatch({type:'go',step:n});onStep?.(n)}
  const work=async<T,>(url:string,body:unknown):Promise<T>=>{
    const end=await runToEnd(post<RunView>(url,body),setRun)
    if(end.state!=='done')throw new Error(end.failure??end.state)
    return end.result as T
  }
  useEffect(()=>{
    if(!editing)return
    let cancelled=false
    setBusy(true)
    void work<Inspect>('/api/sources/sqlite/inspect',{collection:editing.collection}).then(file=>{
      if(!cancelled)dispatch({type:'file',file,scope:editing.scope})
    }).catch(e=>{if(!cancelled)setError(e.message)}).finally(()=>{if(!cancelled){setBusy(false);setRun(null)}})
    return()=>{cancelled=true}
    // The bound collection is fixed for this editor instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[editing?.collection])
  const find=async(folder:string)=>{setError('');setScan(await post<Matches>('/api/sources/sqlite/find',{folder}));remember({path:folder,kind:'folder',purpose:'database'})}
  const inspect=async(root:string)=>{
    setBusy(true);setError('');setPhase('inspect');setAttempted(root)
    try {
      const file=await work<Inspect>('/api/sources/sqlite/inspect',{root})
      dispatch({type:'file',file});setScan(null);setPick(false);onStep?.(1)
      remember({path:file.path,kind:'file',purpose:'database',size:file.size})
      if(!nameEdited)setName(suggestedName(file.path))
      return {kind:'file' as const,size:file.size}
    } catch(e){const message=(e as Error).message
      if(/folder|directory/i.test(message)){try{await find(root);return {kind:'folder' as const}}catch{/* keep the inspect refusal */}}
      setError(message)
      return false as const
    } finally{setRun(null);setBusy(false)}
  }
  const preview=async(review=false)=>{
    if(!s.file)return
    if(!review&&s.snapshot){step(3);return}
    if(review&&editing&&unchanged(s))return
    if(review&&pending.length){dispatch({type:'go',step:4});return}
    setBusy(true);setError('');setPhase(review?'review':'preview')
    try {
      const scope=scopeOf(s)
      const draft={connector:descriptor.id,name,root:s.file.path,include:scope.include,exclude:scope.exclude,
        ...(review?{options:scope.options,sensitive_decisions:consent(s),category_decisions:partial?{partial:'include'}:undefined,decision_plan:s.snapshot?.plan}:{})}
      const p=await work<Preview>('/api/sources/plan',editing ? {collection:editing.collection,scope,...(review?{sensitive_decisions:consent(s),category_decisions:partial?{partial:'include'}:undefined,decision_plan:s.snapshot?.plan}:{})} : {draft})
      dispatch({type:review?'reviewed':'snapshot',preview:p});onStep?.(review&&p.can_confirm!==false?4:3)
      if(review&&p.can_confirm===false)setError('Confirm partial acquisition of the examined tables, and decide every secret-looking column.')
    }catch(e){setError((e as Error).message)}finally{setBusy(false);setRun(null)}
  }
  const onSample=useCallback((table:string,sample:Sample)=>dispatch({type:'sample',table,sample}),[])
  const edit=(table:string)=>{dispatch({type:'active',table});dispatch({type:'back'});onStep?.(3)}
  const fix=(l:Dangling)=>{
    if(l.kind==='filtered')edit(l.parent)
    else if(l.kind==='untaken'){dispatch({type:'tables',chosen:[...new Set([...s.chosen,l.parent])],dismissed:s.dismissed.filter(t=>t!==l.parent)});step(2)}
    else{const c=config(s.cfg,l.child);dispatch({type:'config',table:l.child,cfg:{...c,omit:c.omit.filter(n=>n!==l.column)}});edit(l.child)}
  }
  const acquire=async()=>{
    if(!s.acquire||pending.length||s.acquire.can_confirm===false)return
    setBusy(true);setError('');setPhase('sweep')
    try{const out=await work<SweepResult>(editing?'/api/sources/revise-scope':'/api/sources/sweep',editing?{collection:editing.collection,...scopeOf(s),plan:s.acquire.plan,because:because.trim()||null,by:me,...s.acquire.confirm}:{draft:s.acquire.draft,plan:s.acquire.plan,by:me});setResult(out);setConfirm(false);onChanged()}
    catch(e){setError((e as Error).message)}finally{setBusy(false);setRun(null)}
  }
  const links=s.file?danglingLinks(s.file.tables,sel,s.cfg):[]
  const gate=<SecretGate pending={pending} gate={s.gate} onPick={c=>{dispatch({type:'active',table:c.table});if(s.step!==3)step(3);setTimeout(()=>focusSecret(c.table,c.column),0)}}/>
  return <div className="sql-flow"><Steps editing={!!editing} at={s.step} reachable={pending.length?Math.min(s.snapshot?3:2,s.step):s.acquire?4:s.snapshot?3:s.file?2:1} onGo={busy?undefined:step}/>{editing&&<><p className="src-mono">{s.file?.path}</p><p className="src-note">Mentis asks again each time for SQLite sources.</p>{s.patterns.map(p=><span className="src-chip" key={p}>pattern: <code>{p}</code></span>)}</>}
    {s.step===1&&<><label className="src-field"><span className="src-label">Name</span><input value={name} placeholder="Filled in from the file you pick" onChange={e=>{setNameEdited(true);setName(e.target.value);dispatch({type:'tables',chosen:s.chosen,dismissed:s.dismissed})}}/></label><h2 className="src-h2">Where, on this machine</h2>
      {s.file&&!pick?<FileCard file={s.file} onChange={()=>{setPickMode('file');setPick(true)}} onFolder={()=>{setPickMode('folder');setPick(true)}}/>:<PickSource purpose="database" picker={picker} onPath={inspect} onFolderToSearch={find} autoPick={pickMode}/>}
      {scan&&<FolderMatches scan={scan} onPick={p=>void inspect(p)} onClose={()=>setScan(null)} onFolder={()=>{setPickMode('folder');setPick(true)}}/>}
      <div className="src-actions"><button className="btn primary" disabled={!s.file||!name.trim()||busy} onClick={()=>step(2)}>Choose tables →</button> <span className="src-faint">reads the list of tables; records nothing</span></div></>}
    {s.file&&s.step===2&&!busy&&<>{s.snapshot&&gate}{!s.file.disk.ok&&<div className="linkwarn">{s.file.disk.message}</div>}<TablePicker file={s.file} chosen={s.chosen} dismissed={s.dismissed} samples={s.samples} onChange={(chosen,dismissed)=>dispatch({type:'tables',chosen,dismissed})}/>
      <RunningTotal file={s.file} sel={sel} chosen={s.chosen} cfg={s.cfg} samples={s.samples} onBack={()=>editing?undefined:step(1)} onNext={()=>void preview()}/></>}
    {busy&&phase==='preview'&&s.file&&<section><h2 className="src-h2">Preview: check and build</h2><h3 className="src-label">Taking a private snapshot</h3><p>Copying the whole <b>{s.file.path}</b> ({bytes(s.file.size)}) into private staging with SQLite's backup API, read-only. This happens once. Changing columns or filters later doesn't copy it again; changing which tables you take does.</p></section>}
    {busy&&phase==='review'&&<p>Checking your choices on the private snapshot…</p>}
    {s.file&&s.snapshot&&s.step===3&&!busy&&<><h2 className="src-h2">Preview: check and build</h2><CheckBuild file={s.file} sel={sel} chosen={s.chosen} cfg={s.cfg} samples={s.samples} plan={s.snapshot.plan} active={s.active}
      onActive={table=>dispatch({type:'active',table})} onChange={(table,cfg)=>dispatch({type:'config',table,cfg})} onSample={onSample} onTables={()=>step(2)}
      linkWarning={<LinkWarning links={links.filter(l=>l.child===s.active||l.parent===s.active)} onFix={fix}/>}
      notices={<>{gate}{s.snapshot.partial_required&&<div className="linkwarn"><p>{s.snapshot.unexamined.map(t=>`${t.path}: ${t.reason}`).join(' · ')}</p><label><input type="checkbox" checked={partial} onChange={e=>setPartial(e.target.checked)}/> Acquire only examined tables. Unreadable tables and their reasons stay recorded as not examined; no absence is inferred for them.</label></div>}</>}/>
      <RunningTotal file={s.file} sel={sel} chosen={s.chosen} cfg={s.cfg} samples={s.samples} preview onBack={()=>step(2)} onNext={()=>void preview(true)} disabled={!!pending.length||!!editing&&unchanged(s)}>
        {editing&&unchanged(s)&&<p>Nothing has changed</p>}<GateReason count={pending.length}/>
      </RunningTotal></>}
    {s.file&&s.acquire&&s.step===4&&!result&&<ReviewSqlite file={s.file} sel={sel} chosen={s.chosen} cfg={s.cfg} samples={s.samples} preview={s.acquire} onEdit={edit} onFix={fix} onBack={()=>{dispatch({type:'back'});onStep?.(3)}} editing={!!editing} onAcquire={()=>setConfirm(true)}/>}
    {run&&<RunBar run={run} onCancel={()=>void cancelRun(run.key)}/>}{error&&!confirm&&<div className="act-refused">{phase==='inspect'&&<b>{baseName(attempted)}: </b>}{error}{phase==='inspect'&&<p className="src-mono">{attempted}</p>}</div>}
    {confirm&&s.acquire&&<Confirm title={editing?`Revise the scope of ${name}`:"Acquire into this Brain"} verb={editing?"Revise and sweep":"Acquire now"} busy={busy} refused={error} onCancel={()=>setConfirm(false)} onConfirm={acquire}
      effect={editing?<>1 <code>source-scope-revised</code> act and 1 <code>source-swept</code> act, recorded as yours together. The collection keeps its identity. {s.acquire.counts.new} new rows, {s.acquire.counts.absent} absent, {s.acquire.counts.widened??0} widened.</>:<>1 collection declared, <b>{name}</b> · this database bound on this machine · {s.acquire.admit.length} Admissions recorded · {bytes(s.acquire.bytes_new_to_store)} copied into the held store · 1 <code>source-swept</code> act citing <code>{s.acquire.plan}</code>, recorded as yours. This records the exact private snapshot. The database itself is never modified.</>}>{editing&&<label className="act-field"><span>Why (recorded on the revision, optional)</span><textarea rows={2} value={because} onChange={e=>setBecause(e.target.value)}/></label>}{run&&<RunBar run={run}/>}</Confirm>}
    {result&&<><div className="sql-ok"><b>{name}</b>: {sel.length} tables · {count(s.acquire?.counts.new??0)} rows are now in Mentis.</div><p>A refresh runs the same choices again on a fresh snapshot. You can change them at any time with <b>Edit tables and rules</b>, and nothing already acquired is lost.</p>
      <Result r={result} visible={s.acquire?.visible_not_selected??null}/><button className="btn primary" onClick={()=>result.collection&&go({at:'collection',col:result.collection,tab:'overview'})}>Open {name}</button></>}
  </div>
}
