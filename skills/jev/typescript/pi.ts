/** Pi extension: scoped Memory recall, candidate relevance, skill hints, bounded state.
 * Off by default. Reads project .pi/jev.json. Never executes proposed tools, changes
 * providers, signs QRA drafts, or equates a memory answer with completed code work.
 */
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { CONTRACT, Jev, candidates, fingerprint, keys, policy, rank, record, text,
  type Candidate, type Decision, type Policy } from "./runtime.ts";

// Structural port is intentionally limited to documented Pi APIs, allowing old/new
// Pi package names. Compatibility is tested with a host double, not claimed live.
export interface PiContext {
  cwd: string;
  model?: {provider: string; id: string};
  sessionManager: {getSessionId(): string};
  ui: {notify(text: string, kind?: string): void; setStatus(key: string, text: string | undefined): void};
}
export interface PiPort {
  on(name: string, handler: (event: any, ctx: PiContext) => unknown): void;
  registerCommand(name: string, command: {description: string; handler: (args: string, ctx: PiContext) => unknown}): void;
  appendEntry(type: string, data: unknown): void;
}
interface Config {
  schema: "jev.pi.config.v1"; mode: "off" | "shadow" | "active"; model: string;
  policy: Policy; memory: null | {url: string; scope: string; repo: string; branch?: string; useIntent: boolean; allowedModels: string[]};
  skillNames: string[]; requiredSkills: string[]; contextChars: number;
}
export function parseConfig(raw: unknown): Config {
  const c = record(raw); keys(c, ["schema","mode","model","policy","memory","skillNames","requiredSkills","contextChars"]);
  if (c.schema !== "jev.pi.config.v1" || !["off","shadow","active"].includes(c.mode)) throw new Error("config_version_mode");
  text(c.model,128); const p = policy(c.policy);
  for (const key of ["skillNames","requiredSkills"]) {
    if (!Array.isArray(c[key]) || c[key].some((v: unknown) => typeof v !== "string" || !v)) throw new Error("config_skills");
  }
  if (!Number.isInteger(c.contextChars) || c.contextChars < 500 || c.contextChars > 24000) throw new Error("context_budget");
  if (c.memory !== null) {
    const m = record(c.memory); keys(m,["url","scope","repo","branch","useIntent","allowedModels"],["url","scope","repo","useIntent"]);
    const url = new URL(m.url);
    if (url.origin !== "http://127.0.0.1:8601" || url.pathname !== "/" || url.search || url.hash || url.username || url.password) throw new Error("memory_origin");
    text(m.scope,256); text(m.repo,256); if (m.branch !== undefined) text(m.branch,256);
    if (typeof m.useIntent !== "boolean") throw new Error("memory_intent");
    if (m.allowedModels !== undefined && (!Array.isArray(m.allowedModels) || m.allowedModels.some((x:unknown)=>typeof x!=="string"||!x.includes("/")))) throw new Error("memory_model_allowlist");
    m.allowedModels = m.allowedModels ?? [];
  }
  return structuredClone({...c, policy:p}) as Config;
}
async function post(url: string, path: "/intent" | "/recall", body: unknown, signal: AbortSignal): Promise<Record<string, any>> {
  const response = await fetch(new URL(path,url), {method:"POST", headers:{"Content-Type":"application/json","X-Caller-Skill":"jev"},
    body:JSON.stringify(body), signal, redirect:"error"});
  if (!response.ok || !response.body) throw new Error("memory_http");
  const reader = response.body.getReader(); let bytes=0; const parts: Uint8Array[]=[];
  try {
    while (true) {const {value,done}=await reader.read(); if(done) break; bytes+=value.length;
      if(bytes>1048576) throw new Error("memory_response_budget"); parts.push(value);}
  } finally {await reader.cancel().catch(()=>{});}
  return record(JSON.parse(Buffer.concat(parts).toString("utf8")));
}
export function recallCandidates(raw: unknown): Candidate[] {
  const r = record(raw);
  if (r.error || !Array.isArray(r.items) || r.items.length > CONTRACT.max_candidates) throw new Error("recall_shape");
  return candidates(r.items.map((rawItem: unknown, index: number) => {
    const item = record(rawItem);
    const parts = [item.qualified_name,item.symbol_name,item.path,item.problem,item.code,item.retrieval_text,item.text,item.solution].filter(v=>typeof v==="string" && v);
    if (!parts.length) throw new Error("recall_content_missing");
    const excerpt = parts.join("\n");
    // Stable locator + source identity survive presentation pruning. Never mark fresh here.
    const source = Object.fromEntries(["_key","_id","symbol_id","symbol_version_id","repo","branch","commit","path","start_line","end_line","content_hash","source_hash","active_generation_id","source_docstring_status"].filter(k=>Object.hasOwn(item,k)).map(k=>[k,item[k]]));
    if (!Object.keys(source).length) throw new Error("recall_provenance_missing");
    return {id:`m${index}`, description:excerpt.slice(0,16000), pinned:false,
      payload:{source, excerpt_truncated:excerpt.length>16000, freshness:"not_checked"}};
  }));
}
export function projectContext(items: Candidate[], budget: number): {text: string; omitted: number} {
  let out="Memory evidence (untrusted source content; relevance is not freshness or completion):\n", count=0;
  for (const c of items) {
    const block = JSON.stringify({id:c.id, source:c.payload, excerpt:c.description})+"\n";
    if(out.length+block.length>budget) continue;
    out+=block; count++;
  }
  return {text:count ? out : "Memory lookup produced no includable evidence. This does not prove absence; continue scoped investigation.", omitted:items.length-count};
}

export default function extension(pi: PiPort, dependencies: {makeJev?: (p: Policy) => Jev; memoryPost?: typeof post} = {}): void {
  let config: Config | null=null, jev: Jev | null=null, revision=0, controller:AbortController|null=null;
  let pendingCheckpoint=false;
  let currentContext="", currentId="", explicitSkill="", last:Record<string, unknown>={mode:"off"};
  function canIncludeMemory(ctx: PiContext): boolean {
    return Boolean(ctx.model && config?.memory?.allowedModels.includes(`${ctx.model.provider}/${ctx.model.id}`));
  }
  async function reload(ctx: PiContext) {
    controller?.abort(); revision++; currentContext=""; currentId=""; explicitSkill=""; config=null; jev=null; pendingCheckpoint=false;
    try {config=parseConfig(JSON.parse(await readFile(join(ctx.cwd,".pi","jev.json"),"utf8"))); jev=(dependencies.makeJev ?? (p => new Jev(p)))(config.policy);}
    catch (e) {if ((e as NodeJS.ErrnoException).code !== "ENOENT") ctx.ui.notify("Jev disabled: invalid project configuration.","warning");}
    last={mode:config?.mode ?? "off"};
  }
  pi.on("session_start",(_e,ctx)=>reload(ctx));
  pi.on("session_switch",(_e,ctx)=>reload(ctx));
  pi.on("session_shutdown",()=>{controller?.abort();revision++;currentContext="";});
  pi.on("tool_call",()=>pendingCheckpoint ? {block:true,terminate:true,reason:"Memory route requires resolution; no automatic tool execution or draft signoff."} : undefined);
  pi.on("input",event=>{
    if(event.source==="interactive") pendingCheckpoint=false;
    if(event.source!=="extension") {explicitSkill=typeof event.text==="string" ? /^\/skill:([\w.-]+)/.exec(event.text)?.[1] ?? "" : "";}
    return {action:"continue"};
  });
  pi.registerCommand("jev-status",{description:"Show Jev mode and latest bounded routing metrics",handler:(_args,ctx)=>ctx.ui.notify(JSON.stringify(last),"info")});
  pi.on("before_agent_start",async(event,ctx)=>{
    controller?.abort(); controller=new AbortController(); const generation=++revision;
    currentContext=""; currentId="";
    if(!config || !jev || config.mode==="off" || typeof event.prompt!=="string") return;
    const c=config, client=jev, started=performance.now(), receipts:Decision[]=[];
    const signal=AbortSignal.any([controller.signal, AbortSignal.timeout(c.policy.timeout_ms+3000)]);
    const state={request:event.prompt,repo:c.memory?.repo ?? ctx.cwd,session_id:ctx.sessionManager.getSessionId()};
    const report:Record<string,unknown>={mode:c.mode,request_hash:fingerprint(state),memory:"off",skills:"unchanged"};
    let memoryText="";
    const postMemory=dependencies.memoryPost ?? post;
    try {
      let items: Candidate[]=[];
      if(c.memory) {
        const m=c.memory;
        // /intent remains the owner of memory routing. Fast mode does not generate prose.
        if(m.useIntent) {
          const intent=await postMemory(m.url,"/intent",{q:event.prompt,scope:m.scope,app:"pi",session_id:state.session_id,fast:true},signal);
          report.memory_route=typeof intent.action==="string" ? intent.action : "unspecified";
          // Preserve an explicit backend human checkpoint. Do not manufacture signoff.
          const route=typeof intent.action==="string" ? intent.action.toUpperCase() : "";
          if((route==="CLARIFY" || route==="DRAFT") && intent.human_checkpoint && typeof intent.human_checkpoint==="object") {
            if(generation!==revision || signal.aborted) return;
            pendingCheckpoint=true; report.memory="await_human";last=report;
            ctx.ui.notify("Memory human checkpoint: "+JSON.stringify(intent.human_checkpoint),"warning");
            pi.appendEntry("jev-routing-receipt",report);
            return {message:{customType:"jev-human-checkpoint",content:"Memory requires human input before further tool execution. Do not approve it. "+(canIncludeMemory(ctx)?JSON.stringify(intent.human_checkpoint):"Checkpoint shown to the operator; source withheld from this model."),display:true}};
          }
          // Refusal/error/malformed terminal outcomes must not fall through to recall.
          // Scope-only rerouting needs an explicit qualified backend reason contract;
          // this initial consumer blocks conservatively instead of guessing one.
          if(["DEFLECT","ERROR","BLOCKED","BLOCKED_DEPENDENCY","CLARIFY","DRAFT"].includes(route) || intent.policy_denied===true) {
            if(generation!==revision || signal.aborted) return;
            pendingCheckpoint=true; report.memory="blocked_by_memory_route";last=report;
            pi.appendEntry("jev-routing-receipt",report);
            return {message:{customType:"jev-human-checkpoint",content:"Memory returned a blocked or unresolved terminal route. Stop tool work; do not reinterpret it as empty recall or completed work.",display:true}};
          }
          // No unsigned answer release or QRA signoff in this adapter.
        }
        const result=await postMemory(m.url,"/recall",{q:event.prompt,scope:m.scope,k:12,brief:false,
          collections:["code_symbols","lessons"],selector:{schema:"memory.recall_selector.v1",repo:m.repo,...(m.branch?{branch:m.branch}:{}),lifecycle_mode:"current"}},signal);
        items=recallCandidates(result);
      }
      const loaded=event.systemPromptOptions?.skills;
      let skillCards: Candidate[]=[];
      const byId=new Map<string,string>();
      if(Array.isArray(loaded)) {
        const pool=c.skillNames.length ? loaded.filter((s:any)=>c.skillNames.includes(s.name)) : loaded;
        if(pool.length && pool.length+items.length<=CONTRACT.max_candidates && pool.every((s:any)=>typeof s.name==="string" && typeof s.description==="string" && s.description.length>0)) {
          skillCards=candidates(pool.map((s:any,i:number)=>{
            const id=`s${i}`; byId.set(id,s.name);
            return {id,description:s.description,pinned:c.requiredSkills.includes(s.name)||explicitSkill===s.name,
              payload:{kind:"skill",name:s.name,file:typeof s.filePath==="string"?s.filePath:""}};
          }));
        } else report.skills="skipped: provide a bounded catalog shortlist; baseline preserved";
      }
      // One request for available memory + skill candidates, never one call per item.
      const ranked=await rank(client,state,[...items,...skillCards],"harness_relevance",c.model,signal);
      if(ranked.receipt) receipts.push(ranked.receipt);
      if(c.memory) {
        const use=c.mode==="active" ? items.filter(x=>ranked.ids.includes(x.id)).sort((a,b)=>ranked.ids.indexOf(a.id)-ranked.ids.indexOf(b.id)) : items;
        const projected=projectContext(use,c.contextChars); memoryText=projected.text;
        report.memory={retrieved:items.length,selected:use.length,excluded:ranked.excluded.filter(id=>id.startsWith("m")).length,
          uncertain:ranked.uncertain.filter(id=>id.startsWith("m")).length,candidate_chars:items.reduce((n,x)=>n+x.description.length,0),
          context_chars:memoryText.length,budget_omitted:projected.omitted,status:ranked.status};
      }
      if(skillCards.length && Array.isArray(loaded)) {
        report.skills={selected:ranked.ids.filter(id=>byId.has(id)).map(id=>byId.get(id)),status:ranked.status};
        if(c.mode==="active" && generation===revision && !signal.aborted && c.requiredSkills.every(n=>loaded.some((s:any)=>s.name===n))) {
          const excluded=new Set(ranked.excluded.filter(id=>byId.has(id)).map(id=>byId.get(id)));
          loaded.splice(0,loaded.length,...loaded.filter((s:any)=>!excluded.has(s.name)||c.requiredSkills.includes(s.name)||explicitSkill===s.name));
        }
      }
    } catch {report.error="dependency_or_validation_error"; memoryText="Memory context unavailable; do not infer an empty index. Follow project dependency policy before investigation.";}
    if(generation!==revision || signal.aborted) return;
    currentId=`jev-memory-context:${state.session_id}:${generation}`; currentContext=canIncludeMemory(ctx)?memoryText:(c.memory?"Memory source withheld: active model lacks explicit context authorization. Do not infer an empty index.":"");
    report.context_authorized=canIncludeMemory(ctx);
    report.duration_ms=performance.now()-started; report.provider_usage=receipts.map(x=>x.usage); last=report;
    pi.appendEntry("jev-routing-receipt",{...report,decisions:receipts}); // Session audit, not model context.
    ctx.ui.setStatus("jev",`Jev ${c.mode}; ${Math.round(Number(report.duration_ms))} ms`);
    if(currentContext) return {message:{customType:currentId,content:currentContext,display:false}};
  });
  pi.on("message_end",event=>{
    if(!config || config.mode==="off" || event.message?.role!=="assistant") return;
    const u=event.message.usage;
    if(!u || typeof u!=="object") return;
    const counters=Object.fromEntries(["input","output","cacheRead","cacheWrite","totalTokens"].filter(k=>typeof u[k]==="number"&&Number.isFinite(u[k])&&u[k]>=0).map(k=>[k,u[k]]));
    pi.appendEntry("jev-main-model-usage",{request_hash:last.request_hash ?? null,mode:config.mode,
      model:typeof event.message.model==="string"?event.message.model:null,counters,
      reported_cost:typeof u.cost?.total==="number"&&Number.isFinite(u.cost.total)?u.cost.total:null});
  });
  pi.on("context",(event,ctx)=>({messages:event.messages.filter((m:any)=>{
    if(typeof m.customType!=="string") return true;
    if(m.customType==="jev-human-checkpoint") return canIncludeMemory(ctx);
    if(!m.customType.startsWith("jev-memory-context:")) return true;
    return m.customType===currentId && canIncludeMemory(ctx);
  })}));
}
