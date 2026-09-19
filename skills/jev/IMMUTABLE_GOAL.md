# Immutable goal: useful decisions, less wasted work

The authoritative target is [immutable_goal.json](immutable_goal.json), revision 1.
Its scope comes from the owner's request to extend Jev across Pi, Tau and the
shared Memory/code-retrieval pipeline. No owner signature has been manufactured.

**Outcome:** reduce unnecessary generative-model token use and elapsed time while
preserving verified task success, source freshness, evidence integrity, data
boundaries and human checkpoints.

## Where Jev belongs

Pi gets a native TypeScript extension. Tau gets a native Python package and
registration decorator. They share question definitions, typed outcomes and tests,
not a service bridge and not two independently drifting policy implementations.

Jev selects intent/capability categories, relevant skills, useful recalled code
and evidence, and already-bound tool candidates. It does not retrieve from a new
memory database, generate arbitrary arguments, invent provider quotas, execute
commands, approve drafts or declare a repair complete.

Memory returns the `ingest-code` projection and related evidence. It owns grounded
intent/answerability and the answer/clarify/deflect/QRA-draft products. Pi and SPARTA
consume those products for different interfaces. Domain no-match, uncertain
retrieval, a policy denial and a service outage must remain distinguishable.

Model selection uses measured qualification, cost, latency, context requirements,
policy and fresh provider capacity. Jev supplies semantic capability judgments;
ordinary code and the owning provider adapter handle the numeric/admission work.

## What proves completion

Every acceptance ID in the JSON needs retained evidence. Native conformance and
fixture tests are necessary but insufficient. Installed Pi, its headless/subagent
launches, Tau, Memory and catalog monitoring must be exercised together.

Use identical retained workloads for three variants: existing behavior,
deterministic cleanup, and cleanup plus Jev. Count all provider input/output/cache
usage and cost, Jev overhead, waiting, retries and complete wall time. Require
better tokens and time than deterministic cleanup with no reduction in required
evidence retention or independently verified task success on that workload.
Generalization beyond that retained workload remains a separate claim.

A model saying "done", an attractive receipt, or fewer context characters is not
proof. No part of this goal is met by deleting required evidence, skipping a
freshness check, treating a failed lookup as empty, using an unqualified cheaper
model, or quietly approving a QRA.

## Current boundary

The new code is an implementation candidate with offline tests. The Pi adapter
currently handles scoped recall/skill context and explicit checkpoints; Python
provides the equivalent primitives for Tau-owned adapters. Automatic provider
switching/reservation, full terminal response/review presentation, monitor catalog
qualification and installed-host efficacy are not established by this change.

**Goal disposition: NOT_ESTABLISHED pending retained live integration and efficacy
evidence.** This is not permission to lower the goal or substitute a fixture suite
for those missing measurements.
