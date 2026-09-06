#!/usr/bin/env node
// Fault injection against the production extension/checker. Pi event driver is synthetic.
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
const dir=mkdtempSync(join(tmpdir(),'shame-hardening-'));
const packet=join(dir,'pending.json');
process.env.LAZY_REPORT_SHAME_FAILURE_LOG=join(dir,'failures.jsonl');
Object.assign(process.env,{LAZY_REPORT_SHAME_AUDIO_ENABLED:'0',LAZY_REPORT_SHAME_MEMORY_ENABLED:'0',LAZY_REPORT_SHAME_DEFAULT_MODE:'strict',LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET:packet,LAZY_REPORT_SHAME_TRAINING_JSONL:join(dir,'training.jsonl'),LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE:join(dir,'ledger.json')});
const root='/home/graham/workspace/experiments/agent-skills';
const index=process.env.LAZY_REPORT_SHAME_INDEX||`${root}/extensions/pi/lazy-report-shame-shame-shame/index.ts`;
const extension=(await import(pathToFileURL(index).href)).default;
function instance(id) {
 const handlers={},commands={},sent=[],notices=[];
 const ctx={isIdle:()=>true,hasPendingMessages:()=>false,hasUI:false,ui:{notify:t=>notices.push(t),setStatus(){}},sessionManager:{getSessionId:()=>id,getSessionFile:()=>join(dir,id+'.jsonl'),getBranch:()=>[]}};
 extension({on:(n,f)=>(handlers[n]??=[]).push(f),registerCommand:(n,c)=>commands[n]=c,sendUserMessage:t=>sent.push(t)});
 return {handlers,commands,sent,notices,ctx};
}
async function emit(x,n,e={}){let r;for(const f of x.handlers[n]||[])r=await f(e,x.ctx);return r;}
function event(text,id){return {message:{role:'assistant',stopReason:'stop',...(id?{id}:{}),content:[{type:'text',text}]}};}
const failures=[];
async function check(name,fn){try{await fn();}catch(e){failures.push({name,error:String(e)});}}
await check('repeated-continuation',async()=>{
 const x=instance('repeat');await emit(x,'input',{text:'poll the pending job',source:'interactive'});
 const text='```json\n'+JSON.stringify({schema:'pi.agent_status.v1',goal:'poll',state:'continuing',changed:['no change: pending job'],not_done:[{item:'await job',next_command:'check-job-status'}]})+'\n```';
 for(let i=0;i<6;i++){
  if(i)await emit(x,'input',{text:x.sent.at(-1),source:'extension'});
  await emit(x,'tool_result',{toolName:'bash',isError:false,input:{command:'check-job-status'},content:[{type:'text',text:`pending ${i}`}]});
  const e=event(text); // Native Pi messages need not carry an id.
  await emit(x,'message_end',e);await emit(x,'agent_end');
  assert.equal(x.sent.length,i+1,'distinct stops with identical valid text must continue');
  await emit(x,'message_end',e);await emit(x,'agent_end');
  assert.equal(x.sent.length,i+1,'replayed same event must not duplicate dispatch');
 }
});
await check('proof-validation',()=>{
 const good=join(dir,'proof.txt');writeFileSync(good,'real-command actual-result');
 const empty=join(dir,'empty.txt');writeFileSync(empty,'');
 for(const [proof,want] of [['https://shame.invalid/nonexistent.json','reject'],['sha256:'+'0'.repeat(64),'reject'],[empty,'reject'],[dir,'reject'],[good,'pass']]){
  const status={schema:'pi.agent_status.v1',goal:'proof probe',state:'done',changed:['synthetic probe'],verified:[{command:'real-command',result:'actual-result'}],proof:[proof]};
  const r=spawnSync('node',[join(dirname(index),'status-json-check.mjs')],{input:'```json\n'+JSON.stringify(status)+'\n```',encoding:'utf8',timeout:10000,env:{...process.env,LRSSS_FORCE_STATUS:'1'}});
  assert.equal(JSON.parse(r.stdout).decision,want,`wrong proof decision: ${proof}`);
 }
});
await check('session-isolation',async()=>{
 for(const id of ['A','B']){
  const x=instance(id);await emit(x,'input',{text:`task ${id}`,source:'interactive'});
  await emit(x,'message_end',event(`candidate ${id}`,`final-${id}`));
 }
 for(const id of ['A','B']){
  const x=instance(id);await x.commands.shame.handler('show',x.ctx);
  assert.match(x.notices.join('\n'),new RegExp(`candidate ${id}`));
  assert.ok(!x.notices.join('\n').includes(`candidate ${id==='A'?'B':'A'}`),'loaded another session candidate');
  await x.commands.shame.handler('reject session_isolation -- synthetic label test',x.ctx);
  const row=JSON.parse(readFileSync(join(dir,'training.jsonl'),'utf8').trim().split('\n').at(-1));
  assert.equal(row.session_id,id);assert.equal(row.assistant_text,`candidate ${id}`);
 }
 const other=instance('C');await other.commands.shame.handler('show',other.ctx);
 assert.ok(other.notices.join('\n').includes('No candidate captured'),'unrelated session inherited candidate');
 // A legacy single-file packet may only be read by its recorded owner.
 const text='legacy A';const hash='sha256:'+createHash('sha256').update(text).digest('hex');
 writeFileSync(packet,JSON.stringify({candidate:{session_id:'legacy-A',assistant_text:text,response_sha256:hash}}));
 const owner=instance('legacy-A');await owner.commands.shame.handler('show',owner.ctx);
 assert.match(owner.notices.join('\n'),/legacy A/);
 const stranger=instance('legacy-B');await stranger.commands.shame.handler('show',stranger.ctx);
 assert.ok(stranger.notices.join('\n').includes('No candidate captured'),'legacy packet leaked across sessions');
});
const report={proof_boundary:'Synthetic lifecycle events, production extension/Pydantic checker, isolated temporary files, no Memory/audio writes',failures,passed:failures.length===0};
writeFileSync(join(dir,'report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({...report,report:join(dir,'report.json')}));
if(failures.length)process.exit(1);
console.log('HARDENING_REPRO_PASS');
