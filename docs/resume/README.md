# Resume PDF

This directory is reserved for the public resume source and generated PDF.

Recommended files:

```text
docs/resume/graham-anderson-resume.md
docs/resume/graham-anderson-resume.pdf
```

Build the PDF from Markdown with the repo script:

```bash
uv run --with markdown-pdf==1.13.2 python scripts/build_markdown_pdf.py \
  docs/resume/graham-anderson-resume.md \
  docs/resume/graham-anderson-resume.pdf \
  --title "Graham Anderson Resume" \
  --author "Graham Anderson"
```

`markdown-pdf` is intentionally optional rather than a repository dependency.
It is pulled only for this build command, pinned to the version used by CI.

## Automation

`.github/workflows/resume-pdf.yml` runs on pull requests and on pushes to
`main` when the resume source, optional CSS, converter, or workflow changes.
Until `docs/resume/graham-anderson-resume.md` exists, the workflow skips
cleanly. On `main`, it rebuilds `docs/resume/graham-anderson-resume.pdf` and
commits the generated PDF back to `main` when the rendered artifact changed.
