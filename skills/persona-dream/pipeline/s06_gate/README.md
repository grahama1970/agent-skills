# s06 Gate

Validates step outputs against their contracts. On failure, forces the offending step to course-correct.

## Input

- Run root containing all produced contracts and receipts

## Output

Gate validation receipt (`gate_validation.json`)

## Usage

```bash
python pipeline/s06_gate/validate_gate.py --gate all --run-root /path/to/run
```
