# Extract-Tables Profiler Report

**PDFs tested**: 9  
**Successful**: 9

## Summary

| Metric | Value |
|--------|-------|
| Avg Native Time | 0.3105s |
| Avg Camelot Time | 0.6096s |
| Avg Speedup | 2.25x |
| Median Speedup | 1.92x |

## Per-PDF Results

| PDF | Native Tbl | Native Time | Camelot Tbl | Camelot Time | Speedup | Shape % | Text % |
|-----|-----------|-------------|------------|--------------|---------|---------|--------|
| column_span_2.pdf | 1 | 0.3673s | 1 | 0.5441s | 1.48x | 0.0% | 6.5% |
| foo.pdf | 1 | 0.1764s | 1 | 0.5311s | 3.01x | 100.0% | 45.8% |
| health.pdf | 1 | 0.383s | 1 | 0.7339s | 1.92x | 0.0% | 0.0% |
| multiple_tables.pdf | 1 | 0.1802s | 1 | 0.4105s | 2.28x | 0.0% | 82.4% |
| row_span_1.pdf | 1 | 0.3761s | 1 | 0.4874s | 1.3x | 0.0% | 20.8% |
| row_span_2.pdf | 1 | 0.1903s | 1 | 0.7137s | 3.75x | 100.0% | 38.7% |
| superscript.pdf | 4 | 0.4817s | 0 | 0.8414s | 1.75x | 0.0% | 0.0% |
| twotables_1.pdf | 2 | 0.4598s | 2 | 0.6106s | 1.33x | 0.0% | 33.3% |
| twotables_2.pdf | 1 | 0.1796s | 2 | 0.6133s | 3.41x | 0.0% | 97.9% |

## Pipeline Stage Breakdown (First Page)

| PDF | render | threshold | morph_h | morph_v | contours | joints | text |
|-----|--------|-----------|---------|---------|----------|--------|------|
| column_span_2.pdf | 0.0001s | 0.0163s | 0.0185s | 0.0271s | -s | -s | 0.0s |
| foo.pdf | 0.0001s | 0.0174s | 0.0194s | 0.0279s | -s | -s | 0.0s |
| health.pdf | 0.0001s | 0.0162s | 0.0189s | 0.0275s | -s | -s | 0.0s |
| multiple_tables.pdf | 0.0001s | 0.0183s | 0.0197s | 0.029s | -s | -s | 0.0s |
| row_span_1.pdf | 0.0001s | 0.0171s | 0.0218s | 0.0192s | -s | -s | 0.0s |
| row_span_2.pdf | 0.0001s | 0.0224s | 0.0254s | 0.0228s | -s | -s | 0.0s |
| superscript.pdf | 0.0001s | 0.0212s | 0.0273s | 0.0313s | -s | -s | 0.0s |
| twotables_1.pdf | 0.0001s | 0.0194s | 0.0253s | 0.0222s | -s | -s | 0.0s |
| twotables_2.pdf | 0.0001s | 0.0167s | 0.0187s | 0.0273s | -s | -s | 0.0s |

## Native Table Details

### column_span_2.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 12 | 1 | 75.0 | network |  |

### foo.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 7 | 7 | 93.88 | lattice | Table 2-1. Simulated fuel savings from i |

### health.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 28 | 8 | 89.29 | hybrid | Table: 5 Public Health Outlay 2012-13 (B |

### multiple_tables.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 6 | 4 | 100.0 | lattice |  |

### row_span_1.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 21 | 2 | 69.05 | stream |  |

### row_span_2.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 7 | 10 | 94.29 | lattice |  |

### superscript.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 6 | 11 | 45.45 | hybrid | TABLE 125: STATE-WISE COMPOSITION OF OUT |
| 1 | 5 | 1 | 100.0 | hybrid | & FIs Banks |
| 1 | 30 | 1 | 100.0 | hybrid |  |
| 1 | 2 | 1 | 100.0 | hybrid |  |

### twotables_1.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 9 | 12 | 57.41 | lattice |  |
| 1 | 1 | 8 | 100.0 | hybrid |  |

### twotables_2.pdf

| Page | Rows | Cols | Accuracy | Strategy | Title |
|------|------|------|----------|----------|-------|
| 1 | 27 | 8 | 90.28 | lattice | Table 6 : DISTRIBUTION (%) OF HOUSEHOLDS |

## Figures

Generate comparison figures with:
```bash
/create-figure /home/graham/workspace/experiments/pi-mono/.pi/skills/extract-tables/reports/profile_data.csv --type bar --x pdf --y native_time_s,camelot_time_s --title 'Extraction Time: Native vs Camelot'
/create-figure /home/graham/workspace/experiments/pi-mono/.pi/skills/extract-tables/reports/profile_data.csv --type bar --x pdf --y speedup --title 'Speedup Factor (Native/Camelot)'
```

Analyze with:
```bash
/analytics /home/graham/workspace/experiments/pi-mono/.pi/skills/extract-tables/reports/profile_data.csv --question 'Compare native vs camelot extraction performance'
```
