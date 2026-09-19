/** Offline fixtures are transport doubles, not live Jev/Pi performance evidence. */
import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {Jev,rank,candidates,fingerprint,policy} from "../typescript/runtime.ts";
import {chooseModel,memoryDisposition,tool} from "../typescript/routing.ts";
import extension,{parseConfig,recallCandidates,projectContext} from "../typescript/pi.ts";
const cases=JSON.parse(readFileSync(new URL("../contracts/conformance.json",import.meta.url),"utf8"));
for(const c of cases) test(c.name,async()=>{
  let called=0;const r=await new Jev(c.policy,async()=>{called++;return structuredClone(c.response);}).ask(c.request);
  assert.equal(r.status,c.status);assert.deepEqual(r.confident,c.confident);assert.equal(called,c.status==="blocked"?0:1);
});
test("rank retains uncertain/pinned evidence",async()=>{
  const js=new Jev({allow_egress:true,data_class:"public"},async()=>({model:"fixture",answers:Object.fromEntries([.999,.001,.5,.001].map((v,i)=>[`c${i}`,{type:"noul",noul:v}]))}));
  const result=await rank(js,"bug",candidates([0,1,2,3].map(i=>({id:String(i),description:"prior failure",pinned:i===3}))));
  assert.deepEqual(result.ids,["0","2","3"]);assert.deepEqual(result.excluded,["1"]);
});
test("deadline cannot hang on an uncooperative transport",async()=>{
  const js=new Jev({allow_egress:true,data_class:"public",timeout_ms:100},async()=>new Promise(()=>{}));
  // Keep test process alive: AbortSignal.timeout timers are intentionally unref'ed.
  const keep=setTimeout(()=>{},1000);
  try {const r=await js.ask(cases[0].request);assert.equal(r.reason,"deadline");}finally{clearTimeout(keep);}
});
test("cancellation does not become empty recall",async()=>{
  const c=new AbortController();c.abort();
  const js=new Jev({allow_egress:true,data_class:"public"},async()=>{throw Error("must not call");});
  const r=await rank(js,"task",candidates([{id:"a",description:"code"}]),"memory","fixture",c.signal);
  assert.deepEqual(r.ids,["a"]);assert.equal(r.receipt?.reason,"cancelled");
});
test("request hashes bind numeric type and Unicode",()=>{
  assert.notEqual(fingerprint({x:1}),fingerprint({x:"1"}));assert.throws(()=>fingerprint(NaN));assert.throws(()=>policy({threshold:0.5}));
});
test("memory answer is not code completion",()=>{
  assert.equal(memoryDisposition("ANSWER",{work_requested:true,covers_request:true}),"continue_agent");
  assert.equal(memoryDisposition("DRAFT",{work_requested:true,human_checkpoint:true}),"await_human");
  assert.equal(memoryDisposition("DEFLECT",{work_requested:true,scope_only:true,policy_denied:true}),"blocked");
});
test("stale/limited models excluded; explicit pin not overridden",()=>{
  const m={id:"good",capabilities:["code"],qualified:true,authorized:true,available_slots:1,observed_at_ms:0,expires_at_ms:1000,cooldown_until_ms:0,estimated_total_cost:1,estimated_latency_ms:10};
  const opts={required:["code"],now_ms:100,max_cost:2,deadline_ms:200};
  assert.equal(chooseModel([m,{...m,id:"cheap",available_slots:0,estimated_total_cost:0}],opts),"good");
  assert.equal(chooseModel([m],{...opts,pinned:"cheap"}),null);
});
test("tool registration does not execute; strict parser remains host-owned",()=>{
  const t=tool("inspect","Inspect code",{type:"object"},raw=>{const v=raw as any;if(Object.keys(v).join()!=="path"||typeof v.path!=="string")throw Error("invalid");return v;});
  assert.equal(t.candidate({path:"src/a.ts"}).payload.tool,"inspect");assert.throws(()=>t.candidate({path:1}));
});
test("recall needs provenance and preserves source identity",()=>{
  assert.throws(()=>recallCandidates({items:[{text:"unattributed"}]}));
  const cs=recallCandidates({items:[{_key:"k",path:"src/f.py",code:"def f(): pass",content_hash:"abc"}]});
  const context=projectContext(cs,2000);assert.match(context.text,/src\/f.py/);assert.match(context.text,/not_checked/);
  assert.equal(projectContext(cs,10).omitted,1);
});
test("Pi context hook leaves user/tool messages and unrelated memory intact",()=>{
  const hooks=new Map<string,any>();extension({on:(n,h)=>hooks.set(n,h),registerCommand:()=>{},appendEntry:()=>{}});
  const messages=[{role:"user",content:"task"},{role:"toolResult",toolCallId:"x"},{customType:"other-memory",content:"keep"},{customType:"jev-memory-context:old",content:"omit"}];
  assert.deepEqual(hooks.get("context")({messages}).messages,messages.slice(0,3));
});
test("config rejects remote Memory origins and unknown fields",()=>{
  const base={schema:"jev.pi.config.v1",mode:"off",model:"jev-latest",policy:{},memory:null,skillNames:[],requiredSkills:[],contextChars:1000};
  assert.equal(parseConfig(base).mode,"off");assert.throws(()=>parseConfig({...base,other:1}));
  assert.throws(()=>parseConfig({...base,memory:{url:"https://example.com",repo:"demo",scope:"code",useIntent:true}}));
});

test("Pi batches memory and skills; reuses context without additional judgments",async()=>{
  const {mkdtemp,mkdir,writeFile,rm}=await import("node:fs/promises");const {tmpdir}=await import("node:os");
  const root=await mkdtemp(`${tmpdir()}/jev-pi-`);await mkdir(`${root}/.pi`);
  const cfg={schema:"jev.pi.config.v1",mode:"active",model:"fixture",policy:{allow_egress:true,data_class:"public"},
    memory:{url:"http://127.0.0.1:8601",scope:"code",repo:"demo",useIntent:true,allowedModels:["fixture/demo"]},skillNames:["debugger","irrelevant"],requiredSkills:[],contextChars:4000};
  await writeFile(`${root}/.pi/jev.json`,JSON.stringify(cfg));
  const hooks=new Map<string,any>(),calls:any[]=[],audits:any[]=[];
  let requests=0;
  extension({on:(n,h)=>hooks.set(n,h),registerCommand:()=>{},appendEntry:(_n,r)=>audits.push(r)}, {
    makeJev:p=>new Jev(p,async body=>{requests++;return {model:"fixture",answers:Object.fromEntries(Object.keys(body.questions).map((id,i)=>[id,{type:"noul",noul:i===0||i===2?.999:.001}]))};}),
    memoryPost:async(_url,path,body)=>{calls.push({path,body});return path==="/intent"?{action:"implement"}:{items:[{_key:"one",repo:"demo",path:"a.py",code:"the implicated function"},{_key:"two",repo:"demo",path:"b.py",code:"unrelated function"}]};}
  });
  const ctx={cwd:root,model:{provider:"fixture",id:"demo"},sessionManager:{getSessionId:()=>"session-one"},ui:{notify:()=>{},setStatus:()=>{}}};
  try {
    await hooks.get("session_start")({},ctx);
    const skills=[{name:"debugger",description:"Investigate runtime failure"},{name:"irrelevant",description:"Compose unrelated art"}];
    const out=await hooks.get("before_agent_start")({prompt:"Fix the failing function",systemPromptOptions:{skills}},ctx);
    assert.equal(requests,1);assert.deepEqual(skills.map(s=>s.name),["debugger"]);
    assert.match(out.message.content,/a.py/);assert.doesNotMatch(out.message.content,/b.py/);
    assert.equal(calls[1].body.selector.repo,"demo");assert.equal(calls[0].body.session_id,"session-one");
    const msgs=[out.message,{role:"toolResult",toolCallId:"keep"}];
    hooks.get("context")({messages:msgs},ctx);hooks.get("context")({messages:msgs},ctx);assert.equal(requests,1);assert.equal(audits.length,1);
    assert.equal(hooks.get("context")({messages:msgs},{...ctx,model:{provider:"other",id:"model"}}).messages.length,1);
    await hooks.get("session_switch")({},ctx);assert.equal(hooks.get("context")({messages:msgs},ctx).messages.length,1);
  } finally {hooks.get("session_shutdown")({},ctx);await rm(root,{recursive:true,force:true});}
});

test("Pi cancellation cannot publish a late old-turn result",async()=>{
  const {mkdtemp,mkdir,writeFile,rm}=await import("node:fs/promises");const {tmpdir}=await import("node:os");
  const root=await mkdtemp(`${tmpdir()}/jev-pi-`);await mkdir(`${root}/.pi`);
  await writeFile(`${root}/.pi/jev.json`,JSON.stringify({schema:"jev.pi.config.v1",mode:"active",model:"fixture",policy:{allow_egress:true,data_class:"public"},memory:null,skillNames:[],requiredSkills:[],contextChars:1000}));
  const hooks=new Map<string,any>(),audits:any[]=[];
  let resolveFirst:(v:unknown)=>void=()=>{},count=0;
  extension({on:(n,h)=>hooks.set(n,h),registerCommand:()=>{},appendEntry:(_n,r)=>audits.push(r)}, {makeJev:p=>new Jev(p,async()=>{
    count++;if(count===1)return new Promise(r=>{resolveFirst=r;});return {model:"fixture",answers:{c0:{type:"noul",noul:.999}}};
  })});
  const ctx={cwd:root,model:{provider:"fixture",id:"demo"},sessionManager:{getSessionId:()=>"s"},ui:{notify:()=>{},setStatus:()=>{}}};
  try {await hooks.get("session_start")({},ctx);
    const first=hooks.get("before_agent_start")({prompt:"old",systemPromptOptions:{skills:[{name:"a",description:"skill"}]}},ctx);
    await new Promise(r=>setTimeout(r,10));
    await hooks.get("before_agent_start")({prompt:"new",systemPromptOptions:{skills:[{name:"a",description:"skill"}]}},ctx);
    resolveFirst({model:"fixture",answers:{c0:{type:"noul",noul:.001}}});await first;assert.equal(audits.length,1);
  } finally {hooks.get("session_shutdown")({},ctx);await rm(root,{recursive:true,force:true});}
});

test("explicit Memory human checkpoint blocks tool dispatch without signing anything",async()=>{
  const {mkdtemp,mkdir,writeFile,rm}=await import("node:fs/promises");const {tmpdir}=await import("node:os");
  const root=await mkdtemp(`${tmpdir()}/jev-pi-`);await mkdir(`${root}/.pi`);
  await writeFile(`${root}/.pi/jev.json`,JSON.stringify({schema:"jev.pi.config.v1",mode:"active",model:"fixture",policy:{},
    memory:{url:"http://127.0.0.1:8601",scope:"code",repo:"demo",useIntent:true,allowedModels:["fixture/demo"]},skillNames:[],requiredSkills:[],contextChars:1000}));
  const hooks=new Map<string,any>(),paths:string[]=[];
  extension({on:(n,h)=>hooks.set(n,h),registerCommand:()=>{},appendEntry:()=>{}}, {memoryPost:async(_u,path)=>{
    paths.push(path);return {action:"CLARIFY",human_checkpoint:{question:"Which behavior should remain compatible?"}};
  }});
  const ctx={cwd:root,model:{provider:"fixture",id:"demo"},sessionManager:{getSessionId:()=>"s"},ui:{notify:()=>{},setStatus:()=>{}}};
  try {await hooks.get("session_start")({},ctx);
    const out=await hooks.get("before_agent_start")({prompt:"Change compatibility"},ctx);
    assert.match(out.message.content,/Which behavior/);assert.equal(hooks.get("tool_call")({},ctx).block,true);
    assert.deepEqual(paths,["/intent"]);hooks.get("input")({source:"extension",text:"continue"},ctx);
    assert.equal(hooks.get("tool_call")({},ctx).block,true);
  } finally {hooks.get("session_shutdown")({},ctx);await rm(root,{recursive:true,force:true});}
});

test("Memory denials and malformed checkpoints never fall through to recall",async()=>{
  const {mkdtemp,mkdir,writeFile,rm}=await import("node:fs/promises");const {tmpdir}=await import("node:os");
  const root=await mkdtemp(`${tmpdir()}/jev-pi-`);await mkdir(`${root}/.pi`);
  await writeFile(`${root}/.pi/jev.json`,JSON.stringify({schema:"jev.pi.config.v1",mode:"active",model:"fixture",policy:{},
    memory:{url:"http://127.0.0.1:8601",scope:"code",repo:"demo",useIntent:true,allowedModels:["fixture/demo"]},skillNames:[],requiredSkills:[],contextChars:1000}));
  try {for(const action of ["DEFLECT","ERROR","BLOCKED_DEPENDENCY","DRAFT","CLARIFY"]) {
    const hooks=new Map<string,any>(),paths:string[]=[];
    extension({on:(n,h)=>hooks.set(n,h),registerCommand:()=>{},appendEntry:()=>{}},{memoryPost:async(_u,path)=>{paths.push(path);return {action};}});
    const ctx={cwd:root,model:{provider:"fixture",id:"demo"},sessionManager:{getSessionId:()=>"s"},ui:{notify:()=>{},setStatus:()=>{}}};
    await hooks.get("session_start")({},ctx);await hooks.get("before_agent_start")({prompt:"task"},ctx);
    assert.deepEqual(paths,["/intent"]);assert.equal(hooks.get("tool_call")({},ctx).block,true);
    hooks.get("session_shutdown")({},ctx);
  }} finally {await rm(root,{recursive:true,force:true});}
});
