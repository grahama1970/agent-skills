"""Fixture app for question-first explain-project eval."""

from pathlib import Path


def transform(source: Path, out: Path) -> None:
    out.write_text(source.read_text().upper())


def publish(out: Path, report: Path) -> None:
    """Publish waits for the marker so readers never treat partial output as ready."""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("data")
    report.write_text('{"status":"ready"}')


def main() -> None:
    root = Path("/tmp/explain-project-question-first-fixture")
    publish(root / "out.txt", root / "report.json")


if __name__ == "__main__":
    main()
