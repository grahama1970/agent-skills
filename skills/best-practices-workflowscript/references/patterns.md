# Annotated canonical patterns

Each pattern is shown in the exact portable syntax. Each carries the failure
that produced it.

## Gate child with structured verdict (fail-closed)

```js
const gate=await runs.run('gate',{agent:'scout',worktree:false,acceptance:false,
  output:false,timeoutMs:900000,toolBudget:{hard:30},
  outputSchema:{type:'object',additionalProperties:false,
    properties:{phase:{type:'string',enum:['ready','blocked_human','continue']}},
    required:['phase']},
  task:'...'});
if(gate.structuredOutput.phase!=='continue'){break;}
```

Failure prevented: an LLM child returning prose ("looks good") that the script
cannot branch on, or a missing verdict silently treated as success.

## Config via gate child (scripts cannot read files)

```text
task: 'Read <repo>/.pi/<workflow>.json: max_iterations (clamp 1..20, default 5),
       mode, readiness_command, focus. Report them in structured output.'
```

Failure prevented: workflowScript trying `require('fs')` (no host globals) or
hardcoding caps so the project agent cannot tune a run.

## Per-item failure isolation

```js
for(const t of targets){
  try{ /* recover -> review -> publish -> post -> close */ }
  catch(e){ results.push({issue:t.issue,state:'infrastructure_failure',error:String(e)}); }
}
```

Failure prevented: one provider abort killing a whole ticket queue after six
hours of processed work.

## Bounded repair loop

```js
for(let round=1;round<=2&&review.structuredOutput.verdict==='changes_requested';round++){
  await runs.run('repair-'+issue+'-'+round,{...});
  review=await runs.run('review-'+issue+'-'+round,{...});
}
```

Failure prevented: infinite repair/review ping-pong burning provider quota
overnight.

## The CRIT method note (verbatim, include in every mutating child)

```text
CRITICAL method notes: (1) the local checkout HEAD may be intentionally stale
because work lands by plumbing; compare bytes against origin/main via
git show/ls-tree/diff origin/main and git merge-base --is-ancestor, never
against local HEAD or bare git status; (2) untracked candidate files live in the
working tree: check git status --porcelain before claiming a candidate does not
exist; (3) chunk every command, each under timeout 300; (4) work ONLY in the
primary checkout of this repo: no worktrees, no branch switching, no
stash/reset, preserve unrelated dirty bytes.
```

Failures prevented: stale-HEAD false blockers (a reviewer "verified" work was
unpublished because it compared against a 33-behind local HEAD); "no candidate
exists" against untracked files; single 20-minute pipelines hitting tool
timeouts; children stashing or resetting other lanes' dirty state.

## Repo pinning warning (include in every gate/scout child that queries issues)

```text
REPO WARNING: the repository is <owner/name> ONLY; never query <lookalikes>.
```

Failure prevented: two independent scouts confidently classified the wrong
project's issues (`alejandro-ao/tau` → `huggingface/tau`) and nearly blocked a
ticket on a different project's merged PR.

## Preflight-first and degrade

```js
const workerModel=(available.find(function(m){return m.indexOf('gpt-5.5')>=0;})
                   ||available[0]||undefined);
```

Failure prevented: launching a full round onto exhausted providers — observed
in one session: gpt-5.5 quota, kimi 403 (5h), glm 429, claude 429, and one
invalid registry id, each discovered only mid-round.

## Model-id discipline

Only ids verified in the live registry (`~/.pi/agent/settings.json`,
`pi-subagents docs/models.md`, or an error message that lists valid ids).
Disclose every substitution of worker or reviewer model in the run report.

Failure prevented: `anthropic/claude-sonnet-4:high` "Unknown subagent model" —
whole review lanes failed to launch.

## Honest terminal state

```js
finalState={status:'blocked_human',detail:gate.structuredOutput.detail,
            humanActions:gate.structuredOutput.humanActions};
```

Failure prevented: closing a qualification ticket while its verdict artifact
said NOT_READY — the exact class a watchdog closure audit reopened (#329).
