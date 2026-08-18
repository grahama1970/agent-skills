# Workstation contract

A Herdr workstation is one live task runtime:

```json
{
  "kind": "herdr-workstation",
  "run_id": "20260701T120000Z-ms-qra-gap-1842",
  "workspace_id": "w1",
  "tabs": {
    "agents": "t1",
    "logs": "t2",
    "receipts": "t3"
  },
  "agents": {
    "qbert-codex": {
      "role": "qbert",
      "command": "codex"
    }
  }
}
```

The manifest records Herdr ids for live control. It does not prove task success.
Task success must come from project-specific receipts and reviewers.
