# Resume PDF

This directory is reserved for the generated public resume PDF.

Canonical source and generated artifact:

```text
RESUME.md
docs/resume/graham-anderson-resume.pdf
```

Build the PDF from Markdown with the repo script:

```bash
uv run --with markdown-pdf==1.13.2 python scripts/build_markdown_pdf.py \
  RESUME.md \
  docs/resume/graham-anderson-resume.pdf \
  --title "Graham Anderson Resume" \
  --author "Graham Anderson"
```

`markdown-pdf` is intentionally optional rather than a repository dependency.
It is pulled only for this build command, pinned to the version used by CI.

## Automation

`.github/workflows/resume-pdf.yml` runs on pull requests and on pushes to
`main` when the resume source, optional CSS, converter, or workflow changes.
On `main`, it rebuilds `docs/resume/graham-anderson-resume.pdf` from `RESUME.md`
and commits the generated PDF back to `main` when the rendered artifact changed.
