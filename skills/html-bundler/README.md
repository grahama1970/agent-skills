# html-bundler

Bundle any web page (local HTML, localhost, or external URL) into one WebGPT-ready zip.

## Quick start

```bash
cd skills/html-bundler
./run.sh capture --url http://localhost:3000 --clipboard
```

Default artifact path:

```text
/tmp/html-bundler-<timestamp>.zip
```

## Dependencies

- `skills/surf/run.sh` for browser capture
- `skills/clipboard/run.sh` when using `--clipboard`
- Python 3.11+ with `typer` (`uv sync` in this directory if needed)
