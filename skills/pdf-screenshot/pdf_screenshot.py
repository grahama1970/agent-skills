
import fitz
import argparse
import sys
from pathlib import Path

def screenshot_page(
    pdf_path: str, 
    page_num: int, 
    crop_bbox: list[float] | None = None, 
    highlight_bbox: list[float] | None = None,
    out_path: str | None = None, 
    dpi: int = 150
) -> str:
    """
    Render a single page to PNG.
    page_num: 0-indexed page number.
    """
    doc = fitz.open(pdf_path)
    
    try:
        page = doc[page_num]
    except IndexError:
        print(f"Error: Page {page_num} not found in document (max index: {len(doc)-1})")
        sys.exit(1)

    # Apply Highlight if requested
    if highlight_bbox:
        rect = fitz.Rect(highlight_bbox)
        # Draw red rectangle: stroke only, width 3
        # color is (r, g, b) floats 0-1
        page.draw_rect(rect, color=(1, 0, 0), width=3)

    # Render
    if crop_bbox:
        rect = fitz.Rect(crop_bbox)
        rect = rect + (-20, -20, 20, 20) # Padding
        pix = page.get_pixmap(clip=rect, dpi=dpi)
    else:
        pix = page.get_pixmap(dpi=dpi)

    # Determine Output Path
    if not out_path:
        out_path = _generate_default_path(pdf_path, page_num, crop_bbox)
    else:
        # If out_path is a directory (ends in / or exists as dir), append filename
        p_out = Path(out_path)
        if out_path.endswith("/") or (p_out.exists() and p_out.is_dir()):
            filename = Path(_generate_default_path(pdf_path, page_num, crop_bbox)).name
            out_path = str(p_out / filename)

    out_path_obj = Path(out_path)
    out_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    pix.save(out_path_obj)
    doc.close()
    return str(out_path_obj)

def _generate_default_path(pdf_path: str, page_num: int, bbox: list[float] | None) -> str:
    stem = Path(pdf_path).stem
    suffix = "_crop" if bbox else ""
    return f"/tmp/pdf-screenshot/{stem}_page{page_num}{suffix}.png"

def parse_bbox(s: str) -> list[float]:
    try:
        return [float(x.strip()) for x in s.split(',')]
    except ValueError:
        raise argparse.ArgumentTypeError("BBox must be 'x0,y0,x1,y1' floats")

def parse_pages(s: str) -> list[int]:
    try:
        return [int(x.strip()) for x in s.split(',')]
    except ValueError:
        raise argparse.ArgumentTypeError("Pages must be comma-separated ints")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Screenshot a PDF page or region.")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    
    # Page selection (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--page", type=int, help="Single page number (0-indexed)")
    group.add_argument("--pages", type=parse_pages, help="Comma-separated page numbers (e.g. 1,3,5)")
    group.add_argument("--all", action="store_true", help="Process all pages")

    parser.add_argument("--bbox", type=parse_bbox, help="Crop BBox 'x0,y0,x1,y1'")
    parser.add_argument("--highlight", type=parse_bbox, help="Highlight BBox 'x0,y0,x1,y1' (red box)")
    parser.add_argument("--out", dest="out_path", help="Output path or directory")
    parser.add_argument("--dpi", type=int, default=150, help="DPI for rendering")

    args = parser.parse_args()

    # Determine pages to process
    pages_to_process = []
    if args.page is not None:
        pages_to_process = [args.page]
    elif args.pages:
        pages_to_process = args.pages
    elif args.all:
        try:
            doc = fitz.open(args.pdf_path)
            pages_to_process = list(range(len(doc)))
            doc.close()
        except Exception as e:
            print(f"Error opening PDF: {e}")
            sys.exit(1)

    # Process
    try:
        results = []
        for p in pages_to_process:
            saved = screenshot_page(
                args.pdf_path, 
                p, 
                crop_bbox=args.bbox, 
                highlight_bbox=args.highlight, 
                out_path=args.out_path, 
                dpi=args.dpi
            )
            print(f"Saved: {saved}")
            results.append(saved)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
