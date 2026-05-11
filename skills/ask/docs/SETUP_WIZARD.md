# Ask Setup Wizard

Installing `/ask` does not start containers. Setup is a separate operator action and local containers start only with explicit consent, such as:

```bash
./run.sh setup --profile local-dev --start-missing --yes --json
```

The wizard supports `local-dev` and `shared-stack` profiles. `local-dev` plans the required Docker stack; `shared-stack` validates externally supplied service URLs without starting local containers.

Core setup layers:

- `arangodb` for memory and scillm persistence.
- `qdrant` or the configured vector store for dense recall.
- A multimodal embedder with the expected vector dimension.
- `memory` for `upsert` and `recall`.
- `scillm` for model proxy health and JSON response checks.
- `ask` for config doctor and setup readiness reporting.

Machine-readable setup output includes `ready`, `missing`, `actions`, `start_missing_services`, `repair_command`, and `safe_default`. The setup E2E sanity checks include `memory_upsert_recall`, dense recall, scillm JSON health, and ask config doctor readiness.
