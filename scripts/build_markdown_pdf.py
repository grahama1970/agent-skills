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
    omit_sections: tuple[str, ...]
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
        "--omit-section",
        action="append",
        default=[],
        dest="omit_sections",
        metavar="HEADING",
        help=(
            "Drop this level-2 section from the PDF only (repeatable). Lets one "
            "Markdown source produce a short attachable PDF and a fuller web page "
            "without maintaining two documents that can drift."
        ),
    )
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
        omit_sections=tuple(args.omit_sections),
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


def drop_sections(markdown_text: str, headings: tuple[str, ...]) -> str:
    """Remove named level-2 sections, failing closed if one is not present.

    A silent no-op here would ship a PDF quietly longer than intended, so a
    heading that does not match is an error rather than a shrug.
    """
    if not headings:
        return markdown_text
    wanted = {h.strip().casefold() for h in headings}
    seen: set[str] = set()
    kept: list[str] = []
    dropping = False
    for line in markdown_text.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            dropping = title.casefold() in wanted
            if dropping:
                seen.add(title.casefold())
        elif line.startswith("# ") and not line.startswith("##"):
            dropping = False
        if not dropping:
            kept.append(line)
    missing = sorted(wanted - seen)
    if missing:
        raise ValueError(f"--omit-section heading not found: {', '.join(missing)}")
    return "\n".join(kept)


def preserve_contact_hard_breaks(markdown_text: str) -> str:
    """Add render-only Markdown hard breaks inside the top contact block.

    The source Markdown should not carry trailing spaces just to shape the PDF.
    markdown-pdf still needs hard breaks to keep location and contact on
    separate lines under the name, so apply them only to the temporary input
    handed to the PDF renderer.
    """
    lines = markdown_text.splitlines()
    contact_indexes: list[int] = []
    saw_title = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("##"):
            saw_title = True
            continue
        if not saw_title:
            continue
        if not stripped or stripped.startswith("> ") or stripped.startswith("## "):
            break
        contact_indexes.append(index)

    for index in contact_indexes[:-1]:
        lines[index] = lines[index].rstrip() + "  "
    return "\n".join(lines)


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
    markdown_text = drop_sections(markdown_text, config.omit_sections)
    markdown_text = preserve_contact_hard_breaks(markdown_text)

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
