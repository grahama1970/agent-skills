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
| Text | 12.52 | - | Fragility 6.84, Loyalty 6.76, Resilience 6.72 | 9 controls |

### Taxonomy Bridge Overlap

**Text**

| Bridge Tag | Datalake | SPARTA | Shared |
|------------|----------|--------|--------|
| Fragility | 12.68 | 1.00 | 6.84 |
| Loyalty | 12.52 | 1.00 | 6.76 |
| Resilience | 12.44 | 1.00 | 6.72 |
| Intimacy | 12.44 | - | - |
| Stealth | - | 1.00 | - |
| Precision | - | 1.00 | - |
| Corruption | - | 1.00 | - |

## Metrics

| Entity | Exists | QRAs | Grounding | Path |
|--------|--------|------|-----------|------|
| CWE-287 | Y | 4 | 0.80 | - |

## Gates

| # | Gate | Result | Time |
|---|------|--------|------|
| 1 | Extract entities | Y | 7316ms |
| 2 | Verify existence | Y | 2303ms |
| 6 | Datalake connection | Y | 1797ms |
| 3 | Check relations | Y | <1ms |
| 4 | Decompose | Y | <1ms |
| 5 | Formalize + QRAs | Y | 118ms |

**Classification: ANSWERABLE** (11535ms total)