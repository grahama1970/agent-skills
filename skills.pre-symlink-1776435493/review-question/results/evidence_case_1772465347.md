# Evidence Case: "What countermeasures protect the F-36 avionics from CWE-287?"

## Entity Graph

```mermaid
graph LR
  subgraph Datalake["Datalake"]
    Text["Text<br/>Fragility, Loyalty, Resilience"]:::f36
  end
  subgraph SPARTA
    CWE_287["CWE-287<br/>4 QRAs"]
  end
  Text -->|Fragility, Loyalty | graph=0.00| CWE_1022
  Text -->|Fragility, Loyalty | graph=0.00| CWE_1079
  Text -->|Fragility, Loyalty | graph=0.00| CWE_1094
  Text -->|Fragility, Loyalty | graph=0.00| CWE_190
  Text -->|Fragility, Loyalty | graph=0.00| CWE_30
  classDef invalid fill:#f99,stroke:#c00
  classDef f36 fill:#bbf,stroke:#33c
```

## Datalake Context

| Category | Recall Conf | Avg Graph | Shared Bridges | Connected Controls |
|----------|-------------|-----------|----------------|-------------------|
| Text | 0.42 | - | Fragility 0.71, Loyalty 0.71, Resilience 0.71 | 9 controls |

### Taxonomy Bridge Overlap

**Text**

| Bridge Tag | Datalake | SPARTA | Shared |
|------------|----------|--------|--------|
| Fragility | 0.42 | 1.00 | 0.71 |
| Loyalty | 0.42 | 1.00 | 0.71 |
| Resilience | 0.41 | 1.00 | 0.71 |
| Stealth | - | 1.00 | - |
| Corruption | - | 1.00 | - |
| Precision | - | 1.00 | - |
| Intimacy | 0.41 | - | - |

## Metrics

| Entity | Exists | QRAs | Grounding | Path |
|--------|--------|------|-----------|------|
| CWE-287 | Y | 4 | 0.80 | - |

## Gates

| # | Gate | Result | Time |
|---|------|--------|------|
| 1 | Extract entities | Y | 19043ms |
| 2 | Verify existence | Y | 6445ms |
| 6 | Datalake connection | Y | 4067ms |
| 3 | Check relations | Y | <1ms |
| 4 | Decompose | Y | <1ms |
| 5 | Formalize + QRAs | Y | 112ms |

**Classification: ANSWERABLE** (29668ms total)