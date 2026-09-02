---
name: best-practices-fastapi
description: >
  FastAPI best practices for Python control-plane services, async eval APIs,
  Pydantic contracts, OpenAPI surfaces, security dependencies, deployment
  handoffs, and Flask fallback adapters. Use when building, reviewing, or
  converting FastAPI/Flask services, especially skill-backed cyber-safety eval
  control planes.
triggers:
  - best practices fastapi
  - best-practices-fast-api
  - fastapi service
  - fastapi control plane
  - fastapi deployment
  - flask fallback
  - convert fastapi to flask
  - pydantic api contract
provides:
  - fastapi-service-standards
  - pydantic-api-contracts
  - flask-fallback-adapter
  - deployment-question-contract
composes:
  - best-practices-python
  - best-practices-security
  - terraform
  - ops-terraform
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
  - best-practices-security
runtime_self_improvement: basic
taxonomy:
  - python
  - api
  - security
  - deployment
  - evaluation
disciplines:
  - engineering-standards
  - developer-tooling
  - compliance-security
---

# FastAPI Best Practices

Use this when building Python API services where the real product is a typed,
auditable control plane, not framework ceremony.

## Default architecture

Keep the core framework-neutral:

```text
contracts.py          # Pydantic request/response/receipt models
service.py            # business logic and skill orchestration
adapters/fastapi.py   # primary async HTTP adapter
adapters/flask.py     # fallback sync adapter over the same core
```

FastAPI is the primary adapter for async jobs, OpenAPI, dependency injection,
streaming status, and Pydantic validation. Flask is a fallback adapter only when
a team requires Flask.

## Required rules

- Pydantic models define every request, response, receipt, and error boundary.
- No loose `dict` contracts below the adapter layer.
- Endpoints call service functions; service functions do not import FastAPI.
- Async endpoints must not run blocking subprocess or network calls in the event
  loop; use a bounded worker, task queue, or explicit thread/process boundary.
- Auth is a dependency, not repeated route code. Start with API key for demos;
  upgrade to OAuth2 scopes when the environment requires it.
- Every external tool/skill call returns a receipt path or typed result object.
- Use `$memory` as the default persistence boundary for agent evidence, receipts,
  source packs, eval results, and retrieval state. That means writes go through
  `/memory` `/store` or `/upsert`; do not write raw AQL from the app, do not call
  Qdrant directly, and do not store embedding arrays in ArangoDB. ArangoDB holds
  canonical documents/edges; Qdrant holds vectors via Memory semantic sync.
- Do not add a second database for this demo. The point is to show Graham's
  Memory-native method, not a generic web-app storage pattern.
- Terraform stays outside the app: use `$terraform` for scaffold/plan/apply and
  `$ops-terraform` for detection/check/plan summaries. Never reimplement
  Terraform inside FastAPI.
- `/docs` is acceptable for an interview demo; lock it down or disable it for a
  production deployment.
- When `/docs` is the demo surface, make OpenAPI carry the story: concise
  Markdown `description`, purpose-named `openapi_tags`, route `summary` and
  `description`, reusable request examples, `tryItOutEnabled`, request duration
  display, and a real API-key security scheme so Swagger has one **Authorize**
  flow instead of repeated header fields.

## Swagger/OpenAPI as a demo harness

Use standard Swagger UI before building a custom frontend when the audience
needs to inspect and execute API contracts. The minimum useful layer is:

1. `FastAPI(description=...)` with a short mission, quickstart, skill chain, and
   explicit non-claims.
2. `openapi_tags` that group routes by user meaning, not default module names.
3. Route-level `summary` and `description` that state what skill boundary is
   crossed and what the endpoint deliberately does not prove.
4. `Body(..., openapi_examples={...})` for every non-trivial request body so a
   live demo uses named dropdown scenarios instead of hand-typed JSON.
5. `swagger_ui_parameters={"tryItOutEnabled": True, "displayRequestDuration": True,
   "docExpansion": "list"}` for low-friction interview walkthroughs.
6. A dependency-backed API-key scheme, such as `APIKeyHeader` plus `Security`, so
   Swagger exposes one **Authorize** button.
7. One optional zero-body readiness route, for example `/v1/eval/test-all`, only
   when it composes already-existing checks. Do not add a new backend subsystem
   just to make a demo button.
8. If a project agent must operate Swagger, inject stable `data-qid` attributes
   into the generated page and keep the injector tiny: authorize input/button,
   operation blocks, summaries, and the visible Execute/Try-it-out controls.
9. If a human must jump from Swagger to code, use FastAPI/OpenAPI's built-in
   `externalDocs` route metadata for a stable GitHub/source link.
10. If a project agent must jump from a route to local code, add
   `x-code-location` to each OpenAPI operation with `file`, `line`, `symbol`,
   and a `$debugger open ... --function ... --bridge` command.
11. If an endpoint returns a generated artifact such as SVG, HTML, JSON, or a
   report, also add `x-artifact-location` with the artifact file, line, source
   link, and `$debugger open ... --line ... --bridge` command. The endpoint
   handler and the returned artifact both need a local code jump.
12. If live editing matters, add a small `/docs` polling script that fetches
    `/openapi.json` with `cache: 'no-store'` and reloads only when that schema
    changes. Uvicorn reload restarts the server; it does not refresh an already
    open Swagger browser tab.

Do not build a bespoke dashboard until standard OpenAPI cannot answer the
interview question. The machine-facing contract is `/openapi.json`; Tau, MCP
bridges, OpenAI Actions, or other agent harnesses can consume that schema
directly. Swagger is for humans, OpenAPI is for agents.

## Cyber-safety eval control-plane slice

For an OpenAI-relevant prep artifact, v1 should do only this:

1. `POST /eval/batch` accepts a Pydantic batch request.
2. The service runs one authorized skill path, such as bounded `$hack` probe or
   Tau-owned model-review lane.
3. Each item returns request hash, response/finding, provider or skill identity,
   placement/deployment decision, status/error, timing, monitor events, and
   receipt/proof refs.
4. Durable artifacts are stored through `$memory`: ArangoDB for canonical
   documents/edges, Qdrant for semantic retrieval metadata managed by Memory.
5. At least one success and one forced failure both produce schema-valid
   receipts.
6. `$agentic-evals` retains the live-path proof.

Add extra endpoints only after that vertical slice works.

## Persistence boundary

For Graham's OpenAI prep artifact, the persistence answer is the existing
Memory stack:

- Authorization manifests, workload records, permits, monitor events, eval runs,
  and receipt envelopes are graph-shaped audit records. Store them as ArangoDB
  documents plus edge collections through `$memory`.
- Retrieval over prior evals, sources, findings, and interview prep should use
  `$memory recall`, which combines BM25, graph traversal, and Qdrant dense
  search.
- Qdrant is not the app database. It stores vectors and payload metadata through
  Memory semantic sync.
- Do not spend interview scope explaining or maintaining an unrelated relational
  datastore. Show the graph/evidence system Graham already uses.

## Deployment questions to ask first

Ask the team before writing infrastructure:

- Where should the service run: local, Azure Container Apps, AKS, internal
  Kubernetes, VM, or another platform?
- What network boundary is required: public, private ingress, VNet/VPC-only, or
  existing internal gateway?
- Which secrets store owns credentials?
- Is `/docs` allowed in the target environment?
- Who can submit eval jobs, read results, run `$hack`, and request deploy plans?
- Is deployment plan-only, human-approved apply, or handed to an internal
  platform team?

## Flask fallback / conversion feature

Do not rewrite business logic for Flask. Convert only the adapter:

```bash
./run.sh convert-to-flask fixtures/route_manifest.json --out /tmp/flask_app.py
```

The route manifest declares HTTP routes and Pydantic model names. The generated
Flask adapter imports the same `contracts.py` and `service.py`, validates input
with Pydantic, calls the same service function, and serializes the same response
model.

Use Flask fallback when:

- the team already standardizes on Flask;
- the service must fit a Flask monolith; or
- FastAPI is rejected for deployment policy reasons.

Do not promise full async parity in Flask. If the service function is async,
provide a deliberate sync facade or keep FastAPI.

## Interview wording

Say:

> I do not know your internal Astra architecture. I built this to show how I
> work: typed Python contracts, authorized cyber probes, governed model-review
> lanes, retained eval proof, and deployment kept as a Terraform handoff.

Do not say this matches OpenAI internals, evaluates Astra directly, or proves a
production deployment until those facts are verified in the target environment.
