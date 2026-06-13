# local-page-analysis-capture

Capture a local HTML page or localhost URL into one WebGPT-ready zip.

## Quick start

```bash
cd skills/local-page-analysis-capture
./run.sh capture --url http://localhost:3000 --clipboard
```

Default artifact path:

```text
/tmp/local-page-analysis-<timestamp>.zip
```

## Dependencies

- `skills/surf/run.sh` for browser capture
- `skills/clipboard/run.sh` when using `--clipboard`
- Python 3.11+ with `typer` (`uv sync` in this directory if needed)
