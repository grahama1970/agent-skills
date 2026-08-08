# Graham Anderson
Buffalo, NY · Buffalo-area hybrid/onsite or remote  
[graham@grahama.co](mailto:graham@grahama.co) · [grahama.co](https://grahama.co) · [linkedin.com/in/grahamanderson](https://www.linkedin.com/in/grahamanderson/) · [github.com/grahama1970](https://github.com/grahama1970)

> I build agent systems that can prove what they did.

**Principal AI Engineer · AI Architect · Machine Learning Engineer**  
Agentic AI · LLM/RAG · Knowledge Graphs · Defense & Aerospace · Founder, grahamaco

U.S. citizen. Extensive experience delivering under export-controlled (ITAR) constraints.

<!-- pdf-only -->
This is the two-page version. The longer one — full project detail and the live capability inventory — is at [grahama.co/resume](https://grahama.co/resume).

## ABOUT
I build agentic pipelines that run in production, not prototypes: multi-agent orchestration with typed DAG contracts and state tracking, tool calling and MCP, RAG and knowledge-graph retrieval, and the unglamorous half that keeps them alive — evaluation harnesses, regression gates, observability, and guardrails. I build the shared runtime other teams consume, and I operate it.

Defense, aerospace, and compliance, where an answer has to be traceable to evidence. On DARPA ARCOS I was Principal Data Scientist and ACERT Technical Lead on the prime-contractor team; presented agentic cybersecurity research to AFRL and received a "Hacker" challenge coin.

Self-contained: research, back end, front end, and the briefing. 15+ years hand-coding, today primarily agentic coding across many harnesses and models, including my own (tau). I design and build my own interfaces — React/D3 graph explorers over knowledge-graph data, agent workspaces, and grahama.co itself — and present the work myself.

Open to contract engagements and full-time Principal/Staff AI Engineer, AI Architect, Machine Learning Engineer, LLM Platform, and Security/Compliance AI roles.

## EXPERIENCE

### Founder & Principal AI Engineer / Architect | grahamaco | Buffalo–Niagara Falls Area · Remote
Feb 2025 - Present
Independent AI engineering practice. Clients are primarily export-controlled (ITAR) defense/aerospace — names withheld; publicly releasable engineering is at github.com/grahama1970.
- Built tau, a receipt-gated multi-agent orchestration harness: goals compile to typed DAG contracts; every agent handoff must produce a schema-valid receipt, hashed evidence artifact, or validator result — no receipt, no action.
- Develop a heavily diverged fork of pdf_oxide (origin: yfedoseev/pdf_oxide, MIT/Apache-2.0; independent since Mar 2026): 430 commits, ~137K lines added — Rust-core changes, full Python pipeline/plugin system, PDF-cloning fixture generation, extraction calibration, and NIST document-validation tooling.
- Authored agent-skills: 340+ reusable agent capabilities (compliance evidence mapping, document AI, LLM evaluation, retrieval) and 90+ bounded worker roles, ~85% of them gated by deterministic sanity checks — public repo, private runtime.
- Built an ArangoDB agent-memory platform (private, regulated): ~219K evidence-grounded QRA records across 7K+ security-control records; hybrid BM25 + vector + multi-hop graph recall over 2.2M source chunks; ~94K Lean 4 theorem statements indexed for requirements-to-proof retrieval.
- Core contributor to pi-mono (open-source agent framework/TUI): extension system, agent runtime, and TUI harness work, Feb–Jul 2026.

### Lead Research Scientist, Agentic Formal Methods | grahamaco (independent practice) | Buffalo, NY
Jan 2024 - Feb 2025
- Designed verifiable agentic systems: a process-driven autoformalization workflow translating engineering requirements into Lean 4 proofs for safety-critical workflows.
- Built probabilistic-deterministic self-correcting loops where LLM generation is validated by compiler/prover feedback.
- Consulted in aerospace/defense settings under export-controlled / ITAR constraints.
- Presented agentic cybersecurity research at venues across the country, including to the Air Force Research Laboratory; received an AFRL "Hacker" challenge coin. Authored the talks and decks myself.

### Principal Data Scientist & ACERT Technical Lead | CS Group (DARPA ARCOS)
Sep 2020 - Dec 2023
- Joined CS Group specifically for the 4-year DARPA ARCOS program (Automated Rapid Certification of Software), on the prime-contractor team, working alongside Honeywell, Lockheed Martin, MIT, GE Research, SRI, and other program collaborators.
- Led design and delivery of ACERT (Automated Certification of Requirements Tool): architected the ArangoDB knowledge-graph schema and LLM-assisted reasoning pipeline for multi-hop compliance verification of mission-critical software against complex certification standards.
- Briefed the program and its collaborators at reviews and conferences nationally; split time roughly 50/50 between executive/technical briefings and hands-on architecture and code, authoring the decks and demos myself.

### Data Scientist | grahamaco (independent practice) | NYC · Remote
Sep 2011 - Sep 2020
- Freelance data science practice across gaming, manufacturing, entertainment, education, health, and e-commerce; ITAR-rated work included.
- Clients included Toyota, Sony, Fox, Boehringer Ingelheim, UCLA Med, Dartmouth (edu-tech prediction), and Domain Industries (manufacturing intelligence).

### Earlier: Interactive Executive Producer & Composer | Los Angeles, CA
2005 - 2011
- Director of Interactive Services at Dentsu America (LA division; 50% internal labor reduction, budgets $10K–$1M, teams of 3–50); Executive Producer, God of War: Ascension campaign for Sony (Webby-recognized, 80+ person productions); commercial composer for Adidas, Pepsi, and X-Games.

## PUBLIC WORK (non-ITAR) — github.com/grahama1970
Client work is mostly export-controlled, so here is the public, verifiable side — including the fun stuff:
- [agent-skills](https://github.com/grahama1970/agent-skills) — my living resume: 340+ reusable agent skills, 90+ worker roles, ~85% with sanity gates. Public repo, private runtime.
- [tau](https://github.com/grahama1970/tau) — receipt-gated multi-agent harness. "Agents hallucinate. Tau contains them."
- [pdf_oxide](https://github.com/grahama1970/pdf_oxide) — heavily diverged fork of yfedoseev's Rust PDF toolkit (430 commits, ~137K lines added: Rust-core changes, Python pipeline, PDF cloning, NIST validation).
- scillm — LLM gateway/proxy: provider routing and fallback across hosted and local models, batch pools, structured-output repair, and streaming transport for agent runtimes.
- [grahama.co](https://grahama.co) — this site, built and designed by me: Next.js static export, self-hosted variable type, a live d3-force capability graph, and generated surfaces that fail the build if any count drifts from the repo.
- extractor, anvil, fetcher, chatterbox voice-agent fork — supporting cast, all public.

## EDUCATION
- Metis Data Science Fellowship | 2016
- Trinity University | BS, Finance, Marketing, and Economics

## CORE COMPETENCIES
- Evals & Quality: LLM Evaluation, Agentic Evaluation Harnesses, Adversarial/Blind Testing, Regression Gates, Ground-Truth Fixtures, Judge Panels
- Observability & LLMOps: AI Observability, Drift Detection, Health Monitoring, Audit Trails & Receipts, Scheduled Pipelines, LLMOps
- Agentic Orchestration: Multi-Agent Systems, AI Agents, DAG Contracts, State Tracking, Tool Calling, Model Context Protocol (MCP), Bounded Agent Roles, Prompt Engineering
- LLM Platform: Large Language Models (LLM), Generative AI, LLM Gateway/Routing, Provider Fallback, Structured Outputs, Batch Inference, Guardrails
- Retrieval & Knowledge: Retrieval-Augmented Generation (RAG), GraphRAG, Knowledge Graphs, ArangoDB, Vector Databases, Hybrid BM25 + Vector Search
- Verification & Compliance: Formal Verification, Lean 4, NIST 800-53/171, MITRE ATT&CK, AI Governance
- Document AI: PDF Extraction, Layout & Table Extraction, Fixture Generation, Extraction Calibration
- Interfaces & Visualization: React, TypeScript, D3, Data-Dense & Graph UI, Design Systems, Deterministic UI Interaction Testing
- Briefing & Communication: Conference Speaking, Executive & Technical Briefings, Slide Decks & Demos, Technical Writing
- ML & Platform: Machine Learning, Model Fine-Tuning, Classifier Training, Python, Rust, Docker, Linux

## DEEPER DETAIL
Omitted from the two-page PDF; kept here for anyone who wants to dig.

- tau — receipt-gated multi-agent harness: agent work compiles to typed DAG contracts with state tracking; every handoff needs a schema-valid receipt or validator result before the next step runs. No receipt, no action.
- ArangoDB agent-memory platform (private, regulated): ~219K evidence-grounded question–reasoning–answer records across 7K+ security-control records (NIST 800-53/171, CWE, MITRE ATT&CK, D3FEND, SPARTA), hybrid BM25 + vector + graph recall over 2.2M source chunks, and ~94K Lean 4 theorem statements indexed for requirements-to-proof retrieval.
- Much of my current client work is export-controlled, so client and program details are withheld; the publicly releasable engineering is at github.com/grahama1970.
- Live capability inventory — skills, sanity coverage, bounded agents, and the research-area map — is generated from the repository at each deploy and published on grahama.co, so the numbers on this page are checkable rather than asserted.
