# Resume PDF

This directory is reserved for the generated public resume PDF and DOCX.

Canonical source and generated artifact:

```text
RESUME.md
docs/resume/graham-anderson-resume.pdf
docs/resume/graham-anderson-resume.docx
```

Build the PDF from Markdown with the repo script:

```bash
uv run --with markdown-pdf==1.13.2 python scripts/build_markdown_pdf.py \
  RESUME.md \
  docs/resume/graham-anderson-resume.pdf \
  --css docs/resume/resume.css \
  --font-dir docs/resume/fonts \
  --no-default-css \
  --title "Graham Anderson Resume" \
  --author "Graham Anderson"
```

Build the ATS-oriented DOCX from the same Markdown with:

```bash
uv run --with python-docx python scripts/build_resume_docx.py \
  RESUME.md \
  docs/resume/graham-anderson-resume.docx \
  --omit-section "DEEPER DETAIL"
```

`markdown-pdf` is intentionally optional rather than a repository dependency.
It is pulled only for this build command, pinned to the version used by CI.

## Design

`resume.css` is a print adaptation of the grahama.co design system in
`site/app/globals.css`. The site is a dark editorial surface; the resume
inverts the ground for print and ATS parsing but keeps the same display face,
hue family, and type roles (Fraunces for display, system sans for prose,
monospace reserved for machine-produced text).

Accents are darkened only where WCAG AA requires it on a light ground, measured
against `#ffffff`: ink `#0c0908` (19.84:1) for body, slate `#5d5147` (7.68:1)
for meta, ember `#a8501f` (5.48:1) for links, and brass `#e2ac62` (2.04:1) for
rules only — never text.

`fonts/` holds static TrueType cuts of the site's own variable Fraunces. PyMuPDF
embeds static TTFs but cannot read the variable WOFF2 the site serves, so the
faces are instanced from `site/public/fonts/fraunces-var.woff2`:

```bash
uv run --with fonttools --with brotli python scripts/build_resume_fonts.py
```

Regenerate them after changing the site font. Because the display face is cut
from the file grahama.co actually serves, the PDF and the site cannot drift into
different typefaces.

## Automation

`.github/workflows/resume-pdf.yml` runs on pull requests and on pushes to
`main` when the resume source, optional CSS, converter, or workflow changes.
On `main`, it rebuilds the generated PDF and DOCX from `RESUME.md` and commits
the generated artifacts back to `main` when either rendered artifact changed.
