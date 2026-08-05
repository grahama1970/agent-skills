# Google Slides handoff

1. Build and verify the PPTX locally.
2. Render the PDF/contact sheet and resolve visible defects.
3. Upload the PPTX to Google Drive and open it with Google Slides.
4. Inspect every slide for font substitution, line wrapping, image conversion, and object
   movement.
5. Preserve source/claim IDs in speaker notes.
6. Make visual edits in Google Slides only after the manifest is stable.
7. When factual content changes, update the claim ledger/deck manifest first and rebuild;
   do not let the cloud deck become the only source of truth.
8. Export public PDF and PPTX variants from the reviewed cloud deck when needed.

Use fonts widely available in Google Slides. The default builder uses Arial and Courier
New. Avoid complex animations, embedded video, and editor-specific effects in the
source-controlled version.
