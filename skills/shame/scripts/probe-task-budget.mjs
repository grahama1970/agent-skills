#!/usr/bin/env node
// Synthetic Pi events; real filesystem, approved subprocesses and elapsed timers.
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
const root='/home/graham/workspace/experiments/agent-skills';
const index=process.env.LAZY_REPORT_SHAME_INDEX || `${root}/extensions/pi/lazy-report-shame-shame-shame/index.ts`;
const {TaskBudget,runApprovedCommand}=await import(pathToFileURL(join(index,'..','task-budget.ts')).href);
const dir=mkdtempSync(join(tmpdir(),'task-budget-'));
process.env.LAZY_REPORT_SHAME_FAILURE_LOG=join(dir,'failures.jsonl');
let executions=0, aborts=0;
const ctx={cwd:dir,abort(){aborts++;},ui:{notify(){},setStatus(){}}};
async function execute(cmd,args,opt){
 executions++;
 return runApprovedCommand(cmd,args,opt);
}
function budget(extra={}){
 const c={schema:'pi.task_budget.v1',mode:'task',deliverable:'produce result',allowed_paths:['input.txt'],elapsed_ms:30000,checks:[{id:'test',argv:['/bin/true'],inputs:['input.txt'],timeout_ms:1000},{id:'deliver',argv:['/bin/true'],inputs:['input.txt'],kind:'delivery',timeout_ms:1000}],...extra};
 const file=join(dir,`contract-${Math.random()}.json`);writeFileSync(file,JSON.stringify(c));
 return new TaskBudget(JSON.stringify(c),file,dir,ctx);
}
writeFileSync(join(dir,'input.txt'),'one');
let b=budget();
assert.equal(b.tool({toolName:'write',toolCallId:'w',input:{path:'input.txt'}}),null);
await assert.rejects(()=>b.run('test',execute),/batched_edits/);
b.toolResult({toolCallId:'w'});
assert.equal(b.tool({toolName:'write',input:{path:'outside.txt'}}),'task_write_path_not_allowed');
assert.equal(b.tool({toolName:'bash',input:{command:'echo extra test'}}),'task_tool_not_approved_use_named_check');
assert.equal(b.tool({toolName:'subagent',input:{}}),'task_tool_not_approved_use_named_check');
symlinkSync('/tmp',join(dir,'escape'));
assert.throws(()=>budget({allowed_paths:['escape/']}),/outside_project/);
await assert.rejects(()=>b.run('undeclared',execute),/not_approved/);
const first=await b.run('test',execute);assert.equal(first.passed,true);
const count=executions;assert.equal((await b.run('test',execute)).cached,true);assert.equal(executions,count);
assert.equal(b.tool({toolName:'edit',input:{path:'input.txt'}}),'task_edits_require_editing_or_failed_check');
writeFileSync(join(dir,'input.txt'),'two'); // External input changes permit revalidation.
assert.equal((await b.run('test',execute)).attempts,2);
await b.run('deliver',execute);assert.equal(b.phase,'accepted');
assert.equal(b.tool({toolName:'read',input:{path:'input.txt'}}),'task_already_accepted');
assert.equal(b.requestFormatRepair(),true);assert.equal(b.phase,'accepted');
assert.equal(b.tool({toolName:'task_check',input:{id:'test'}}),'task_format_repair_is_output_only');
assert.equal(b.requestFormatRepair(),false);assert.equal(b.validReport('continuing'),'task_already_accepted');
b.dispose();
writeFileSync(join(dir,'gate.py'),'original gate');
b=budget({checks:[{id:'frozen',argv:['/bin/true'],inputs:[],definition_files:['gate.py'],timeout_ms:1000}]});
assert.equal(b.tool({toolName:'write',input:{path:'gate.py'}}),'task_check_definition_is_frozen');
writeFileSync(join(dir,'gate.py'),'modified gate');
await assert.rejects(()=>b.run('frozen',execute),/definition_changed_requires_approval/);b.dispose();
b=budget({checks:[{id:'fail',argv:['/bin/false'],inputs:[],timeout_ms:1000}]});
for(let i=0;i<3;i++) await b.run('fail',execute);
assert.equal(b.runs.get('fail').attempts,3);assert.equal(b.phase,'exhausted');
await assert.rejects(()=>b.run('fail',execute),/not_active/);b.dispose();
b=budget({checks:[{id:'review',argv:['/bin/sleep','1'],inputs:[],kind:'review',timeout_ms:40}]});
const review=await b.run('review',execute);assert.equal(review.passed,false);assert.equal(b.phase,'exhausted');
assert.equal(JSON.parse(readFileSync(b.receipt,'utf8')).reason,'task_check_deadline_exceeded');
await assert.rejects(()=>b.run('review',execute),/not_active/);b.dispose();
b=budget({elapsed_ms:40,checks:[{id:'x',argv:['/bin/true'],inputs:[],timeout_ms:20}]});
await new Promise(r=>setTimeout(r,70));assert.equal(b.phase,'exhausted');assert.ok(aborts>=1);b.dispose();
b=budget({mode:'question',allowed_paths:[],checks:[]});
assert.equal(b.tool({toolName:'read',input:{path:'input.txt'}}),null);
assert.equal(b.tool({toolName:'write',input:{path:'input.txt'}}),'task_question_is_read_only');
assert.equal(b.tool({toolName:'task_check',input:{id:'test'}}),'task_question_is_read_only');
b.questionAnswered();assert.equal(b.phase,'accepted');b.dispose();

// Integration: one format-only correction cannot reopen an accepted task.
process.env.LAZY_REPORT_SHAME_AUDIO_ENABLED='0';process.env.LAZY_REPORT_SHAME_MEMORY_ENABLED='0';
process.env.LAZY_REPORT_SHAME_CONTINUATION_GUARD_FILE=join(dir,'no-ledger');
process.env.LAZY_REPORT_SHAME_PENDING_REVIEW_PACKET=join(dir,'pending');
const config=join(dir,'integration.json');writeFileSync(config,JSON.stringify({schema:'pi.task_budget.v1',mode:'task',deliverable:'finish one approved check',allowed_paths:[],elapsed_ms:30000,checks:[{id:'finish',argv:['/bin/true'],inputs:[],timeout_ms:1000}]}));
process.env.SHAME_TASK_BUDGET=config;
const handlers={},tools={},sent=[];
const pi={on:(n,f)=>(handlers[n]??=[]).push(f),registerCommand(){},registerTool:t=>tools[t.name]=t,exec:execute,sendUserMessage:t=>sent.push(t)};
const c={...ctx,isIdle:()=>true,hasPendingMessages:()=>false,sessionManager:{getSessionId:()=>dir,getSessionFile:()=>join(dir,'session.jsonl')}};
(await import(pathToFileURL(index).href)).default(pi);
async function emit(n,e={}){let result;for(const f of handlers[n]||[]){const r=await f(e,c);if(r!==undefined)result=r;if(r?.block)break;}return result;}
await emit('session_start');await emit('input',{text:'perform the approved task',source:'interactive'});
await tools.task_check.execute('one',{id:'finish'},undefined);
const final={message:{role:'assistant',stopReason:'stop',content:[{type:'text',text:'Finished, footer missing'}]}};
const rejected=await emit('message_end',final);assert.match(JSON.stringify(rejected),/missing_agent_status_json/);
await emit('agent_end');assert.equal(sent.length,1);
const blocked=await emit('tool_call',{toolName:'read',input:{path:'input.txt'}});
assert.equal(blocked.block,true);assert.equal(blocked.terminate,true);
await emit('message_end',{message:{...final.message,content:[{type:'text',text:'Still no footer'}]}});await emit('agent_end');assert.equal(sent.length,1);
await emit('input',{text:'Explain the result',source:'interactive'});
const answer=await emit('message_end',{message:{role:'assistant',stopReason:'stop',content:[{type:'text',text:'Plain explanation; no new work.'}]}});
assert.equal(answer,undefined,'a follow-up explanatory question must not trigger a report gate');
assert.equal((await emit('tool_call',{toolName:'write',input:{path:'input.txt'}})).block,true);
await emit('session_shutdown');
const report={schema:'task_budget.probe.v1',path_checks:true,approved_checks:true,input_cache:true,two_repairs:true,review_deadline:true,elapsed_abort:true,accepted_terminal:true,one_output_only_repair:true,question_read_only:true,executions};
const path=join(dir,'report.json');writeFileSync(path,JSON.stringify(report,null,2));
console.log(JSON.stringify({...report,report:path}));console.log('TASK_BUDGET_PROBE_PASS');
