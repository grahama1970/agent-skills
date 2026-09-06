#!/usr/bin/env node
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {pathToFileURL} from 'node:url';
const dir=mkdtempSync(join(tmpdir(),'shame-conversation-'));
Object.assign(process.env,{LAZY_REPORT_SHAME_DEFAULT_MODE:'normal',LAZY_REPORT_SHAME_AUDIO_ENABLED:'0',LAZY_REPORT_SHAME_MEMORY_ENABLED:'0',LAZY_REPORT_SHAME_FAILURE_LOG:join(dir,'failures.jsonl'),LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET:join(dir,'pending.json'),LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE:join(dir,'ledger.json')});
delete process.env.SHAME_TASK_BUDGET;
const index=process.env.LAZY_REPORT_SHAME_INDEX||'/home/graham/workspace/experiments/agent-skills/extensions/pi/lazy-report-shame-shame-shame/index.ts';
const handlers={},sent=[];
const ctx={isIdle:()=>true,hasPendingMessages:()=>false,ui:{setStatus(){},notify(){}},sessionManager:{getSessionId:()=>dir,getSessionFile:()=>join(dir,'session.jsonl')}};
(await import(pathToFileURL(index).href)).default({on:(n,f)=>(handlers[n]??=[]).push(f),registerCommand(){},registerTool(){},sendUserMessage:(text)=>sent.push(text)});
async function emit(n,e={}){let result;for(const fn of handlers[n]||[]){const r=await fn(e,ctx);if(r!==undefined)result=r;if(r?.block)break;}return result;}
const final=text=>({message:{role:'assistant',stopReason:'stop',content:[{type:'text',text}]}});
for(const text of ['why is $shame ecosystem in a shame spiral','should the $shame ecosystem leverage $project-watchdog and $ticket?','Explain acceptance ledger and UNLAZY_FORCED_RETRY without doing work.']){
 await emit('input',{text,source:'interactive'});await emit('before_agent_start',{prompt:text});
 assert.equal(await emit('message_end',final('A plain advisory answer.')),undefined,'advisory mention must not become execution report');
 await emit('agent_end');assert.equal(sent.length,0);
}
// Explicit correction remains guarded; history remains readable.
await emit('input',{text:'$shame correct the report',source:'interactive'});
assert.equal(await emit('tool_call',{toolName:'shame_failures',input:{}}),undefined,'read-only history should be accessible');
assert.equal((await emit('tool_call',{toolName:'bash',input:{command:'true'}})).block,true,'explicit correction still requires the skill read');
await emit('message_end',final('Missing status block'));
await emit('agent_end');assert.equal(sent.length,1);
await emit('input',{text:sent[0],source:'extension'});
for(const name of ['read','bash','write','task_check','shame_failures']){
 const blocked=await emit('tool_call',{toolName:name,input:{path:'x'}});
 assert.equal(blocked?.block,true,`format correction allowed ${name}`);
 assert.equal(blocked?.terminate,true,`format correction did not terminate ${name}`);
}
await emit('message_end',final('Still missing the block'));await emit('agent_end');
assert.equal(sent.length,1,'a correction failure must not request another correction');
// A fresh human question clears correction/read requirements without arming a task.
await emit('input',{text:'What caused the failure?',source:'interactive'});
assert.equal(await emit('tool_call',{toolName:'read',input:{path:'x'}}),undefined);
assert.equal(await emit('message_end',final('Plain explanation')),undefined);
await emit('agent_end');assert.equal(sent.length,1);
// Real mutation still requires status, and a new human task gets its own repair allowance.
await emit('input',{text:'Make the approved change',source:'interactive'});
await emit('tool_call',{toolName:'write',input:{path:'x'}});
assert.match(JSON.stringify(await emit('message_end',final('Changed it'))),/missing_agent_status_json/);
await emit('agent_end');assert.equal(sent.length,2);
const report={advisory_questions_pass:true,explicit_guard_preserved:true,mutation_guard_preserved:true,one_output_only_correction:true,fresh_input_clears_flags:true};
writeFileSync(join(dir,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({...report,report:join(dir,'report.json')}));console.log('CONVERSATION_GUARD_PASS');
