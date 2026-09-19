/** Emit deterministic conformance records for Python/TypeScript parity tests. */
import { readFileSync } from "node:fs";
import { Jev } from "../typescript/runtime.ts";
const cases=JSON.parse(readFileSync(new URL("../contracts/conformance.json",import.meta.url),"utf8"));
const out=[];
for(const c of cases){const r=await new Jev(c.policy,async()=>structuredClone(c.response)).ask(c.request);
  out.push({status:r.status,confident:r.confident,request_hash:r.request_hash,policy_hash:r.policy_hash});}
console.log(JSON.stringify(out));
