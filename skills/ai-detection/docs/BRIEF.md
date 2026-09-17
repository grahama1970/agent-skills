# Source brief and interpretation

The owner requested a zip project named **ai-detection** for browser-based AI-generated
code detection in timed coding assessments, using `setup-project`, `agentic-evals`,
`best-practices-python`, and `best-practices-skills`, informed by current arXiv research.

`specs/requirements.json` records the domain invariants and `specs/policy.json` the
machine-readable limits. These requirements are not a declaration of what already
passes. REQ-14 is deliberately unproven until independent real-world data exists.

The implemented detector baseline supports **Python**. Browser capture also accepts
JavaScript, Java and Go, for which this detector abstains. “Provider-agnostic” describes
the input interface and held-out-family protocol, not a measured all-provider guarantee.
The local application is a research workbench, not a production hiring decision service.

The immutable goal is a draft, not a forged owner approval. Policy mutation checks
exercise a real acceptance boundary: the same edit must be accepted under a larger
source limit and rejected under a smaller declared limit.
