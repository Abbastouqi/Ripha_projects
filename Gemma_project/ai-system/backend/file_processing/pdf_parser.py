"""
PDF text extraction with automatic OCR fallback.

Strategy:
1. Try PyMuPDF (`fitz`) native text extraction - fast, perfect for born-digital PDFs.
2. For each page, count the extracted characters. If a page has fewer than
   `MIN_CHARS_PER_PAGE`, render that page as an image and run Tesseract OCR
   on it. This handles scanned PDFs and image-heavy pages without paying the
   OCR cost on born-digital documents.
3. If `pytesseract` / Tesseract isn't installed, the OCR step is skipped and
   we return whatever native extraction produced (with a one-line warning).

The function signature is unchanged from the previous version.
"""

import os
import io
import shutil

MIN_CHARS_PER_PAGE = 40
OCR_DPI = 200
OCR_LANG = os.getenv("TESSERACT_LANG", "eng")


def _ocr_available() -> bool:
    """Return True if pytesseract is importable and the tesseract binary exists."""
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return False
    cmd = os.getenv("TESSERACT_CMD")
    if cmd:
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = cmd
            return os.path.exists(cmd)
        except Exception:
            return False
    return shutil.which("tesseract") is not None


def _ocr_page(page) -> str:
    """Render a PyMuPDF page to a PIL image and run Tesseract."""
    import pytesseract
    from PIL import Image

    mat_scale = OCR_DPI / 72.0
    try:
        import fitz
        pix = page.get_pixmap(matrix=fitz.Matrix(mat_scale, mat_scale), alpha=False)
    except Exception:
        pix = page.get_pixmap(alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    text = pytesseract.image_to_string(img, lang=OCR_LANG)
    return text or ""


def extract_text(file_path: str) -> str:
    """Extract text from a PDF, OCR-ing pages that look scanned."""
    try:
        import fitz  # PyMuPDF
    except Exception as e:
        raise ValueError(f"PyMuPDF not installed: {e}")

    ocr_on = _ocr_available()
    pages_out: list[str] = []
    ocr_used_count = 0

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise ValueError(f"Failed to open PDF: {e}")

    try:
        for page in doc:
            native = page.get_text() or ""
            if len(native.strip()) >= MIN_CHARS_PER_PAGE:
                pages_out.append(native)
                continue

            if ocr_on:
                try:
                    ocr_text = _ocr_page(page)
                    if len(ocr_text.strip()) > len(native.strip()):
                        pages_out.append(ocr_text)
                        ocr_used_count += 1
                        continue
                except Exception as e:
                    print(f"[pdf_parser] OCR failed on page {page.number}: {e}")
            pages_out.append(native)
    finally:
        doc.close()

    if ocr_used_count:
        print(f"[pdf_parser] OCR used on {ocr_used_count} page(s) of {file_path}")
    elif not ocr_on:
        total_chars = sum(len(p.strip()) for p in pages_out)
        if total_chars < MIN_CHARS_PER_PAGE * max(1, len(pages_out) // 2):
            print(
                "[pdf_parser] Document appears scanned but Tesseract is not "
                "available - install tesseract and pytesseract for OCR support."
            )

    return "\n\n".join(pages_out).strip()
