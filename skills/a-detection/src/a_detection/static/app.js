"use strict";
// No global keylogger, clipboard reader, visibility classifier, remote script, or persisted token.
const el = (id) => document.getElementById(id);
const editor = el("editor");
const state = {session: null, revision: 0, prior: "", ackSource: "", queue: Promise.resolve(),
  failed: false, started: 0, nextSeq: 0, composing: false, submitted: false, kind: "unknown"};
const sha256 = async (text) => Array.from(new Uint8Array(await crypto.subtle.digest(
  "SHA-256", new TextEncoder().encode(text)))).map((b) => b.toString(16).padStart(2,"0")).join("");
const status = (text) => {el("status").textContent = text;};
const uid = () => crypto.randomUUID().replaceAll("-", "");
function patch(before, after) {
  // Array.from counts Unicode code points, unlike JavaScript UTF-16 string offsets.
  const a = Array.from(before), b = Array.from(after);
  let start = 0, suffix = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) start++;
  while (suffix < a.length-start && suffix < b.length-start &&
         a[a.length-1-suffix] === b[b.length-1-suffix]) suffix++;
  return {start, delete_count: a.length-start-suffix,
          insert_text: b.slice(start,b.length-suffix).join("")};
}
async function request(path, method = "GET", data = null) {
  const headers = {"Content-Type":"application/json"};
  if(state.session) headers.Authorization = `Bearer ${state.session.token}`;
  let lastError;
  for(let attempt = 0; attempt < 3; attempt++) {
    const controller = new AbortController(), timeout = setTimeout(()=>controller.abort(),10000);
    try {
      const response = await fetch(path,{method,headers,body:data === null ? null : JSON.stringify(data),
                                        signal:controller.signal,cache:"no-store"});
      const result = await response.json();
      if(!response.ok) {
        const error = new Error(result.cause || "Operation rejected.");
        error.serverRejected = true; throw error;
      }
      return result;
    } catch(error) {
      lastError = error;
      // Session creation cannot be retried without risking an orphan; event retries reuse exact IDs.
      if(error.serverRejected || (path === "/api/sessions" && method === "POST")) throw error;
      if(attempt < 2) await new Promise((resolve)=>setTimeout(resolve,250*(attempt+1)));
    } finally {clearTimeout(timeout);}
  }
  throw lastError;
}
const sessionPath = (suffix="") => `/api/sessions/${state.session.session_id}${suffix}`;
function fatal(error) {
  state.failed = true; editor.readOnly = true; el("submit").disabled = true;
  status(`Capture stopped: ${error.message} Export the acknowledged server record; it is not an authorship finding.`);
}
el("consent").addEventListener("change",()=>{el("start").disabled = !el("consent").checked;});
el("start").addEventListener("click",async()=>{
  el("start").disabled = true;
  try {
    state.session = await request("/api/sessions","POST",{consent:el("consent").checked,language:el("language").value});
    state.started = performance.now(); editor.readOnly = false;
    el("language").disabled = true; el("consent").disabled = true;
    ["submit","export","delete"].forEach((id)=>{el(id).disabled=false;});
    status("Session active. Edits are acknowledged by the local server.");editor.focus();
  } catch(error) {status(error.message);el("start").disabled = !el("consent").checked;}
});
editor.addEventListener("paste",()=>{state.kind="paste";});
editor.addEventListener("compositionstart",()=>{state.composing=true;});
editor.addEventListener("compositionend",()=>{state.composing=false;});
editor.addEventListener("beforeinput",(event)=>{
  if(event.inputType === "insertFromPaste") state.kind="paste";
  else if(event.inputType === "historyUndo") state.kind="undo";
  else if(event.inputType === "historyRedo") state.kind="redo";
  else if(event.isComposing || state.composing) state.kind="composition";
  else if(state.kind !== "paste") state.kind="input";
});
editor.addEventListener("input",(event)=>{
  if(!state.session || state.failed || state.submitted) return;
  const source = editor.value;
  if(source === state.prior) return;
  const change = patch(state.prior,source), seq = ++state.nextSeq;
  const kind = event.isComposing ? "composition" : state.kind;
  const elapsed = performance.now() - state.started;
  state.prior = source; state.kind="unknown";
  const eventId = uid();
  state.queue = state.queue.then(async()=>{
    if(state.failed) return;
    const payload = {...change,event_id:eventId,seq,base_revision:seq-1,
      after_sha256:await sha256(source),kind,client_elapsed_ms:elapsed};
    const receipt = await request(sessionPath("/events"),"POST",payload);
    if(receipt.revision !== seq || receipt.event.after_sha256 !== payload.after_sha256)
      throw new Error("Acknowledgement binding mismatch.");
    state.revision = seq;state.ackSource = source;el("revision").textContent=String(seq);
    status(`Revision ${seq} acknowledged. Events are observations, not authorship evidence.`);
  }).catch(fatal);
});
el("submit").addEventListener("click",async()=>{
  editor.readOnly = true;el("submit").disabled=true;
  try {
    await state.queue;
    if(state.failed) return;
    if(editor.value !== state.ackSource) throw new Error("Editor differs from the durable server revision.");
    const result=await request(sessionPath("/submit"),"POST",{
      revision:state.revision,source_sha256:await sha256(state.ackSource)});
    state.submitted=true;
    el("verdict").textContent=result.disposition.replaceAll("_"," ");
    el("verdict-detail").textContent=result.reasons.join(" ");
    status("Submission frozen. Export the evidence or delete this session.");
  } catch(error) {fatal(error);}
});
el("export").addEventListener("click",async()=>{
  try {
    await state.queue;
    const result = await request(sessionPath("/export"));
    const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:"application/json"}));
    const anchor=document.createElement("a");anchor.href=url;anchor.download="a-detection-session.json";
    // No early revokeObjectURL: revoking while the download stream is still being
    // consumed aborts the artifact (observed empty exports). The blob is released
    // when the document unloads.
    anchor.click();
    status("Exported server-received evidence. A failed capture may leave unacknowledged local edits outside this record.");
  } catch(error) {status(error.message);}
});
el("delete").addEventListener("click",async()=>{
  editor.readOnly=true;
  try {
    await state.queue;await request(sessionPath(),"DELETE");state.session=null;state.failed=true;
    ["submit","export","delete"].forEach((id)=>{el(id).disabled=true;});editor.value="";
    status("Session rows deleted and deletion checked. Disk or backup erasure is not guaranteed.");
  } catch(error) {status(error.message);}
});
setInterval(()=>{
  if(!state.session || state.submitted) return;
  const left=Math.max(0,Math.ceil(state.session.expires_at-state.session.server_now-
                                   (performance.now()-state.started)/1000));
  el("timer").textContent=`${String(Math.floor(left/60)).padStart(2,"0")}:${String(left%60).padStart(2,"0")}`;
  if(left===0){editor.readOnly=true;el("submit").disabled=true;status("Assessment time ended. The server enforces its own deadline; export remains available.");}
},500);
