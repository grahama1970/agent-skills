## Federated Taxonomy Integration

Personas have bridge weights that influence recall and synthesis:

| Bridge | High Weight Means |
|--------|-------------------|
| Precision | Values accuracy, technical detail |
| Resilience | Focuses on robustness, reliability |
| Fragility | Concerned about risks, edge cases |
| Corruption | Deals with adversarial scenarios |
| Loyalty | Values consistency, trust |
| Stealth | Prefers subtlety, discretion |

### Relationship Edges

Relationships are stored as graph edges with bridge attributes:

```json
{
  "from": "Robert Sapolsky",
  "to": "Bruce McEwen",
  "relationship": "mentor",
  "bridges": ["Resilience", "Precision"],
  "context": "McEwen pioneered allostatic load concept"
}
```

This enables multi-hop traversal:
```
Q: "What do stress researchers say about cortisol?"
→ Direct: Sapolsky
→ Via mentor edge + Resilience bridge: McEwen
→ Synthesis includes both perspectives
```
