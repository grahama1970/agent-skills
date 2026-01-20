---
name: pdf-screenshot
description: Render PDF pages or cropped regions to PNG images for visual verification.
---

# PDF Screenshot

This skill renders pages or specific regions (bounding boxes) of a PDF into PNG images. It is designed for human-agent collaboration workflows where the agent needs to show the human what it has detected (e.g., tables, figures) for verification or calibration.

## Usage

### Full Page Screenshot

```bash
/pdf-screenshot /path/to/doc.pdf --page 5
```

Saves to `/tmp/pdf-screenshot/doc_page5.png` (or custom path).

### Cropped Region (Bounding Box)

```bash
/pdf-screenshot /path/to/doc.pdf --page 5 --bbox "72,200,540,400"
```

Saves to `/tmp/pdf-screenshot/doc_page5_crop.png`.
Bounding box format: `x0, y0, x1, y1`.
A default padding of 20px is added to the crop.

### Custom Output Path

```bash
/pdf-screenshot /path/to/doc.pdf --page 5 --out /tmp/my_screenshot.png
```

## Arguments

- `pdf_path`: Path to the input PDF file.
- `--page`: Page number (integer, 0-indexed).
- `--bbox`: Optional bounding box to crop `x0,y0,x1,y1`.
- `--out`: Optional output path.
- `--dpi`: Rendering DPI (default 150).

## Dependencies

- `pymupdf` (fitz)
