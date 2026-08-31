---
name: terraform
description: >
  Make Terraform easy end to end: scaffold a best-practice .tf project layout
  (main/variables/outputs/versions split, envs/ tfvars, modules/, state-safe
  .gitignore), audit an existing root's organization, run fmt/validate checks,
  interview the human about deployment decisions, and run gated
  init/plan/apply. Use for "write terraform", "scaffold terraform project",
  "organize my .tf files", "terraform deploy interview", "terraform apply".
  For HCP Terraform / Terraform Cloud API operations, pair with the tfctl CLI
  (hashicorp/tfctl-cli) — this is a CLI skill, not an MCP server.
triggers:
  - write terraform
  - scaffold terraform project
  - terraform project layout
  - organize terraform files
  - terraform best practices
  - terraform deploy
  - terraform apply
  - terraform interview
provides:
  - terraform-scaffold
  - terraform-layout-audit
  - terraform-deploy-gated
composes:
  - ops-terraform
  - interview
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
runtime_self_improvement: basic
taxonomy:
  - precision
  - infrastructure
  - human-in-the-loop
disciplines:
  - developer-tooling
---

# terraform — Terraform made easy

Typer CLI (`run.sh`) with typed JSON outcomes (`PASS|FAIL|NOT_CONFIGURED` +
`failure_code` on every non-PASS). Detection and scaffolding are free; anything
that mutates real infrastructure is gated behind an explicit human `--yes`.

```bash
./run.sh doctor                          # terraform binary/version + delegate posture
./run.sh scaffold <dir> [--force]        # best-practice project layout in <dir>
./run.sh organize <dir>                  # audit existing layout; violations + fixes (dry-run)
./run.sh check <dir>                     # fmt -check + validate — delegates to /ops-terraform
./run.sh interview [--no-launch]         # deployment Q&A via /interview (backend, envs, apply gate, secrets)
./run.sh deploy <dir> --plan-only        # init + plan, writes deploy.tfplan
./run.sh deploy <dir> --var-file envs/dev.tfvars --yes   # apply — human gate required
```

## Workflow for "help me use Terraform"

1. `scaffold` a fresh root (or `organize` an existing one and apply its fixes).
2. Author resources in `main.tf`, variables in `variables.tf`, pins in
   `versions.tf`; reusable pieces go under `modules/<name>/`.
3. `check` until fmt/validate pass.
4. `interview` the human — backend choice, environments, apply approval,
   secrets source. Answers land in the interview session output.
5. `deploy --plan-only`, have the human review `deploy.tfplan`, then
   `deploy --yes` to apply.

## Layout the scaffold/audit enforce

Standard HashiCorp module structure: `main.tf` (composition), `variables.tf`,
`outputs.tf`, `versions.tf` (required_version + provider pins + backend),
`providers.tf` (no credentials), `envs/*.tfvars` (gitignored; `.example`
committed), `modules/` for children, `.gitignore` excluding state, tfvars, and
plan files. `organize` also flags state files in VCS and >300-line monolith
.tf files.

## Teaching the human to prompt this skill

When a human invokes /terraform vaguely, do NOT guess — show them this prompt
contract and ask for the missing piece. Good prompts name **a verb + a target
directory + (for deploys) an environment**:

| Say this | Skill runs | Notes |
|---|---|---|
| "scaffold a terraform project in `infra/`" | `scaffold infra/` | add "for AWS/GCP" so main/versions get the right provider pin comments |
| "organize / audit my terraform in `infra/`" | `organize infra/` | dry-run report only; say "apply the fixes" to act on them |
| "check my terraform" | `check <dir>` | needs the module dir if not cwd |
| "interview me about deployment" | `interview` | opens the /interview UI; answer all 5 tabs |
| "plan `infra/` with dev vars" | `deploy infra/ --plan-only --var-file envs/dev.tfvars` | safe, no changes |
| "apply it" (after reviewing the plan) | `deploy infra/ --var-file ... --yes` | the human saying "apply"/"yes" IS the gate |

Prompts to redirect, with the correction to give the human:

- "just deploy my infra" with no reviewed plan → run `--plan-only` first and
  reply: "here is the plan summary; say 'apply' to proceed."
- "make terraform work" (no directory) → ask which directory is the project
  root, or offer to `scaffold` a new one.
- "manage my HCP workspace/runs/variables" → that is `tfctl`
  (hashicorp/tfctl-cli), not this skill; point them there.

## Hard rules

1. **Never run `deploy --yes` on your own.** Plan first, hand the plan to the
   human, and apply only after they approve. `APPLY_NOT_CONFIRMED` is the
   skill telling you to stop and ask — relay the printed `next` command.
2. **State files are secrets.** Never commit, print, or copy `*.tfstate`.
3. **Don't reimplement checks** — `check` delegates to /ops-terraform; keep it
   that way.
4. **HCP Terraform work** (workspaces, runs, remote vars) goes through the
   `tfctl` CLI and its own skill, not raw API calls from here.

## Receipts

Every command prints a `terraform_skill.outcome.v1` JSON envelope; `scaffold`
read-backs written files (`missing_after_write`) before claiming PASS. Run
`./sanity.sh` for the behavioral gate; `fixtures/agentic_eval.json` +
`/agentic-evals` is the readiness gate.
