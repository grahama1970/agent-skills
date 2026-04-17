---
title: Use Typer for CLIs; keep CLI thin
impact: HIGH
impactDescription: consistent UX and easier testing of core logic
tags: conventions, cli, typer
---

## Use Typer for CLIs; keep CLI thin

**Incorrect:**
```py
import argparse

def main():
    ...
```

**Correct:**
```py
import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

@app.command()
def run(feed_url: str, limit: int = 100) -> None:
    logger.info("run feed_url={} limit={}", feed_url, limit)
    ingest(feed_url=feed_url, limit=limit)

def main() -> None:
    app()

if __name__ == "__main__":
    main()
```

### Notes
- Put business logic in functions so it can be unit-tested without CLI parsing.
