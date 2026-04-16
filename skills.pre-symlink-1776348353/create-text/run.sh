#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

CMD="${1:-help}"
shift || true

case "$CMD" in
  build)
    python3 -c "
import typer, sys
sys.path.insert(0, '.')
from build_bank import build

app = typer.Typer()

@app.command()
def main(
    source: str = typer.Option('corpus', help='corpus, wikipedia, or all'),
    categories: list[str] = typer.Option([], help='Wikipedia categories (repeatable)'),
):
    build(source=source, categories=categories or None)

app()
" "$@"
    ;;

  select)
    python3 -c "
import typer, json, sys
sys.path.insert(0, '.')
from create_text import create_text

app = typer.Typer()

@app.command()
def main(
    content_type: str = typer.Option(None, '--content-type', '-t', help='prose, bullet_list, requirement, heading, table_cell, glossary, footnote'),
    domain: str = typer.Option(None, '--domain', '-d', help='arxiv, defense, nist, wikipedia, ...'),
    count: int = typer.Option(10, '--count', '-n'),
    seed: int = typer.Option(42, '--seed', '-s'),
    corrupt: str = typer.Option(None, '--corrupt', '-c', help='Corruption: ligature, ocr, whitespace, homoglyph, header_bleed, all, ...'),
    json_out: bool = typer.Option(False, '--json', help='Output as JSON'),
):
    chunks = create_text(content_type=content_type, domain=domain, count=count, seed=seed, corrupt=corrupt)
    if json_out:
        print(json.dumps(chunks, indent=2))
    else:
        for i, c in enumerate(chunks, 1):
            print(f'--- [{i}] {c[\"content_type\"]} | {c[\"domain\"]} | {c[\"source_doc\"]} ---')
            print(c['text'][:500])
            print()

app()
" "$@"
    ;;

  list)
    python3 -c "
import sys
sys.path.insert(0, '.')
from create_text import list_banks
banks = list_banks()
if not banks:
    print('No banks found. Run: ./run.sh build')
    sys.exit(1)
for domain, info in banks.items():
    print(f'{domain}: {info[\"total\"]} chunks')
    for t, c in sorted(info['types'].items()):
        print(f'  {t}: {c}')
"
    ;;

  help|*)
    cat <<'EOF'
Usage: ./run.sh <command> [options]

Commands:
  build     Build text banks from datalake corpus and/or Wikipedia
  select    Select text chunks (deterministic, seeded)
  list      List available domains and content type counts

Build options:
  --source TEXT       corpus, wikipedia, or all (default: corpus)
  --categories TEXT   Wikipedia categories (repeatable)

Select options:
  --content-type/-t   prose, bullet_list, requirement, heading, table_cell, glossary, footnote
  --domain/-d         arxiv, defense, nist, wikipedia, ...
  --count/-n          Number of chunks (default: 10)
  --seed/-s           Random seed (default: 42)
  --json              Output as JSON
EOF
    ;;
esac
