"""Build a PDF from a Markdown file with the optional markdown-pdf package.

Inputs are a UTF-8 Markdown source file, an output PDF path, optional CSS, and
basic PDF metadata. The script writes one PDF and validates that the result is a
non-empty PDF file. It fails closed when the input is missing, the optional
dependency is not installed, or the generated file does not look like a PDF.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CSS = """
body {
  color: #14171a;
  font-family: "Inter", "Aptos", "Helvetica Neue", Arial, sans-serif;
  font-size: 10.5pt;
  line-height: 1.34;
}
h1 {
  color: #0b1117;
  font-size: 22pt;
  margin: 0 0 6pt;
}
h2 {
  border-bottom: 0.8pt solid #d3d9df;
  color: #0b1117;
  font-size: 12pt;
  margin: 16pt 0 6pt;
  padding-bottom: 2pt;
}
h3 {
  color: #20252b;
  font-size: 10.5pt;
  margin: 10pt 0 2pt;
}
p {
  margin: 0 0 5pt;
}
ul {
  margin: 4pt 0 8pt 16pt;
  padding: 0;
}
li {
  margin: 1.5pt 0;
}
a {
  color: #0b5cad;
  text-decoration: none;
}
code {
  background: #eef1f4;
  border-radius: 2pt;
  font-family: "SFMono-Regular", "Consolas", monospace;
  font-size: 9pt;
  padding: 0.5pt 2pt;
}
hr {
  border: 0;
  border-top: 0.8pt solid #d3d9df;
  margin: 9pt 0;
}
"""


@dataclass(frozen=True, slots=True)
class PdfBuildConfig:
    markdown_path: Path
    output_path: Path
    css_path: Path | None
    font_dir: Path | None
    title: str
    author: str
    toc_level: int
    paper_size: str
    optimize: bool
    use_default_css: bool


def parse_args(argv: list[str]) -> PdfBuildConfig:
    parser = argparse.ArgumentParser(
        description="Convert Markdown to PDF using the optional markdown-pdf package.",
    )
    parser.add_argument("markdown", type=Path, help="Input Markdown file")
    parser.add_argument("output", type=Path, help="Output PDF file")
    parser.add_argument("--css", type=Path, default=None, help="Optional CSS file")
    parser.add_argument(
        "--font-dir",
        type=Path,
        default=None,
        help="Directory of TTF/OTF files that @font-face rules may reference by filename",
    )
    parser.add_argument("--title", default="", help="PDF metadata title")
    parser.add_argument("--author", default="", help="PDF metadata author")
    parser.add_argument("--toc-level", type=int, default=2, help="Bookmark heading depth")
    parser.add_argument("--paper-size", default="Letter", help="Paper size, e.g. Letter or A4")
    parser.add_argument(
        "--no-optimize",
        action="store_true",
        help="Disable markdown-pdf compression/optimization",
    )
    parser.add_argument(
        "--no-default-css",
        action="store_true",
        help="Use only the provided CSS and markdown-pdf defaults",
    )
    args = parser.parse_args(argv)
    return PdfBuildConfig(
        markdown_path=args.markdown,
        output_path=args.output,
        css_path=args.css,
        font_dir=args.font_dir,
        title=args.title,
        author=args.author,
        toc_level=args.toc_level,
        paper_size=args.paper_size,
        optimize=not args.no_optimize,
        use_default_css=not args.no_default_css,
    )


def read_css(config: PdfBuildConfig) -> str:
    css_parts: list[str] = []
    if config.use_default_css:
        css_parts.append(DEFAULT_CSS)
    if config.css_path is not None:
        if not config.css_path.is_file():
            raise FileNotFoundError(f"CSS file does not exist: {config.css_path}")
        css_parts.append(config.css_path.read_text(encoding="utf-8"))
    return "\n".join(css_parts)


def build_pdf(config: PdfBuildConfig) -> None:
    try:
        from markdown_pdf import MarkdownPdf, Section
    except ImportError as exc:
        raise RuntimeError(
            "Missing optional dependency 'markdown-pdf'. Run:\n"
            "  uv run --with markdown-pdf==1.13.2 python scripts/build_markdown_pdf.py "
            "docs/resume/graham-anderson-resume.md "
            "docs/resume/graham-anderson-resume.pdf"
        ) from exc

    if not config.markdown_path.is_file():
        raise FileNotFoundError(f"Markdown file does not exist: {config.markdown_path}")
    if not 1 <= config.toc_level <= 6:
        raise ValueError("--toc-level must be between 1 and 6")

    markdown_text = config.markdown_path.read_text(encoding="utf-8")
    if not markdown_text.strip():
        raise ValueError(f"Markdown file is empty: {config.markdown_path}")

    pdf = MarkdownPdf(toc_level=config.toc_level, optimize=config.optimize)
    section = Section(
        markdown_text,
        root=str(config.markdown_path.parent),
        paper_size=config.paper_size,
    )
    if config.font_dir is not None:
        if not config.font_dir.is_dir():
            raise FileNotFoundError(f"Font directory does not exist: {config.font_dir}")
        # markdown-pdf hands Section.root straight to fitz.Story(archive=...), so an
        # Archive spanning both roots lets @font-face resolve fonts by bare filename
        # while relative image paths still resolve against the Markdown directory.
        import pymupdf

        archive = pymupdf.Archive()
        archive.add(str(config.markdown_path.parent))
        archive.add(str(config.font_dir))
        section.root = archive
    pdf.add_section(section, user_css=read_css(config))
    if config.title:
        pdf.meta["title"] = config.title
    if config.author:
        pdf.meta["author"] = config.author

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.save(str(config.output_path))
    validate_pdf(config.output_path)


def validate_pdf(output_path: Path) -> None:
    data = output_path.read_bytes()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"Generated file is not a PDF: {output_path}")
    if len(data) < 1_000:
        raise ValueError(f"Generated PDF is unexpectedly small: {output_path}")


def main(argv: list[str] | None = None) -> int:
    try:
        config = parse_args(sys.argv[1:] if argv is None else argv)
        build_pdf(config)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(str(config.output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
