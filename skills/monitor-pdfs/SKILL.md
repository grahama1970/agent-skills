---
name: monitor-pdfs
description: >
  Dashboard and monitoring tool for PDF harvesting and classifier training data preparation.
  Tracks downloads (Arxiv, MIC, Industry), batch classification, and image extraction progress.
allowed-tools: Bash, Read
triggers:
  - monitor pdfs
  - pdf status
  - check harvest
  - training data progress
metadata:
  short-description: Monitor PDF harvesting and processing pipeline

provides:
  - monitor-pdfs
composes: [task-monitor]
disciplines:
  - observability-operations
  - extraction
---

# Monitor PDFs - Harvesting & Processing Dashboard

This skill provides a unified dashboard for tracking the diverse data collection and processing jobs required for the S00 Document Type Classifier.

## Features

- **Harvesting Status**: Track Arxiv, MIC (Archive.org/GPO), and Industry sector downloads.
- **Batch Processing**: Monitor the S00 profile detector running across the 11k+ PDF corpus.
- **Vision Data Prep**: Track image extraction progress for training the vision classifier.
- **Log Aggregation**: Quick access to background job logs.

## Quick Start

```bash
cd .pi/skills/monitor-pdfs

# Show the overall dashboard
./run.sh dashboard

# Check specific harvesting sources
./run.sh check-harvest

# Monitor batch classification progress
./run.sh check-batch

# Tail recent logs
./run.sh logs --tail 20
```

## Monitoring Logic

The skill monitors the following locations:

- **Corpus**: `/mnt/storage12tb/extractor_corpus/`
- **Results**: `/mnt/storage12tb/extractor_corpus/results/s00_batch_full/`
- **Training Data**: `$PI_HOME/skills/create-classifier/data/`
- **Logs**: Current working directory of the extractor project.

## Commands

| Command         | Description                                |
| --------------- | ------------------------------------------ |
| `dashboard`     | Show full Rich dashboard of all activities |
| `check-harvest` | Count PDFs downloaded from various sources |
| `check-batch`   | Parse batch logs for progress (X/11394)    |
| `check-images`  | Count extracted training images            |
| `logs`          | View tail of active background task logs   |
