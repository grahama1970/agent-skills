
import fitz
import argparse
import sys
from pathlib import Path

def screenshot_page(pdf_path: str, page_num: int, bbox: list[float] | None = None, out_path: str | None = None, dpi: int = 150) -> str:
    doc = fitz.open(pdf_path)
    # PyMuPDF is 0-indexed, but user interface is usually 1-indexed?
    # CLI usually implies user-facing logic.
    # The user example: "--page 5". Usually means page 5 (physically).
    # If the user says "Page 5", they might mean the 5th page (index 4) or usually index 5 if they are a developer?
    # The prompt user implementation says: `page = doc[page_num]`.
    # Docs are usually 0-indexed in code.
    # Let's assume the input `page_num` is the INDEX for now, unless specified otherwise.
    # User's Example: "/pdf-screenshot ... --page 5".
    # I will assume 0-based index to match the provided code snippet `doc[page_num]`.
    # If user wants 1-based, they'll need to adjust or I'll ask.
    # Given this is a low-level tool, 0-based is safer assumption for "page_num".
    
    try:
        page = doc[page_num]
    except IndexError:
        print(f"Error: Page {page_num} not found in document (max index: {len(doc)-1})")
        sys.exit(1)

    if bbox:
        rect = fitz.Rect(bbox)
        # Add padding as requested
        rect = rect + (-20, -20, 20, 20)
        pix = page.get_pixmap(clip=rect, dpi=dpi)
    else:
        pix = page.get_pixmap(dpi=dpi)

    if not out_path:
        stem = Path(pdf_path).stem
        bbox_suffix = "_crop" if bbox else ""
        # Ensure directory exists
        out_dir = Path("/tmp/pdf-screenshot")
        out_path = str(out_dir / f"{stem}_page{page_num}{bbox_suffix}.png")

    out_path_obj = Path(out_path)
    out_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    pix.save(out_path_obj)
    doc.close()
    return str(out_path_obj)

def parse_bbox(s: str) -> list[float]:
    try:
        return [float(x.strip()) for x in s.split(',')]
    except ValueError:
        raise argparse.ArgumentTypeError("BBox must be 'x0,y0,x1,y1' floats")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screenshot a PDF page or region.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--page", type=int, required=True, help="Page number (0-indexed)")
    parser.add_argument("--bbox", type=parse_bbox, help="Bounding box 'x0,y0,x1,y1'")
    parser.add_argument("--out", dest="out_path", help="Output path for PNG")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for rendering")

    args = parser.parse_args()

    try:
        # Note: The user requested `/pdf-screenshot path ...` style.
        # This script expects arguments via argparse.
        saved_path = screenshot_page(args.pdf_path, args.page, args.bbox, args.out_path, args.dpi)
        print(f"Saved: {saved_path}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
