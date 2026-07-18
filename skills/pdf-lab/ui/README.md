# PDF Lab UX — thin launcher

The canonical PDF Lab UX (including the transparent tau-loop viewer at
`#pdf-lab/loop`) lives in the pdf_oxide repository under `ui/`. This
directory is a thin launcher only, following the ux-lab ownership
pattern: pdf_oxide owns its transparency UI so the project is
self-contained.

Usage:

    PDF_OXIDE_ROOT=/path/to/pdf_oxide skills/pdf-lab/ui/run.sh

The UI's cross-repo contract is the versioned artifact schemas
(pdf-lab.comparison.v2, pdf_lab.second_pass_backlog.v1,
pdf_lab.page_terminal_ledger.v1, tau.gs001_ticket_projection.v1,
tau.gs001_closure_report.v1) — never internal imports.
