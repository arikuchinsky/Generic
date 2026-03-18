"""Document renderer — converts .docx to page images for vision analysis.

Supports multiple platforms:
- Windows: Word COM automation → PDF → PyMuPDF
- macOS: AppleScript → PDF → PyMuPDF
- Linux: LibreOffice → PDF → PyMuPDF
"""

from __future__ import annotations

import logging
from pathlib import Path

from ...utils.platform import docx_to_pdf

logger = logging.getLogger(__name__)


def render_to_images(
    docx_path: Path,
    output_dir: Path,
    dpi: int = 200,
    max_pages: int = 100,
) -> list[Path]:
    """Render a .docx file to page images via PDF intermediate.

    Args:
        docx_path: Path to the .docx file.
        output_dir: Directory to write page images.
        dpi: Resolution for page rendering (default 200).
        max_pages: Maximum number of pages to render.

    Returns:
        List of paths to rendered page PNG images, in order.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(exist_ok=True)

    # Step 1: Convert docx to PDF
    logger.info(f"Converting {docx_path.name} to PDF...")
    try:
        pdf_path = docx_to_pdf(docx_path, output_dir)
    except Exception as e:
        logger.error(f"PDF conversion failed: {e}")
        raise RuntimeError(
            f"Could not convert document to PDF. Ensure LibreOffice or "
            f"Microsoft Word is installed. Error: {e}"
        )

    # Step 2: Render PDF pages to PNG images using PyMuPDF
    logger.info(f"Rendering PDF pages to images at {dpi} DPI...")
    image_paths = _pdf_to_images(pdf_path, pages_dir, dpi, max_pages)

    logger.info(f"Rendered {len(image_paths)} pages")
    return image_paths


def _pdf_to_images(
    pdf_path: Path,
    output_dir: Path,
    dpi: int,
    max_pages: int,
) -> list[Path]:
    """Convert PDF pages to PNG images using PyMuPDF (fitz)."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError(
            "PyMuPDF is required for PDF rendering. Install it with: pip install PyMuPDF"
        )

    image_paths = []
    doc = fitz.open(str(pdf_path))

    try:
        page_count = min(doc.page_count, max_pages)
        zoom = dpi / 72  # PDF default is 72 DPI
        matrix = fitz.Matrix(zoom, zoom)

        for page_num in range(page_count):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix)

            image_filename = f"page_{page_num + 1:03d}.png"
            image_path = output_dir / image_filename
            pix.save(str(image_path))
            image_paths.append(image_path)

    finally:
        doc.close()

    return image_paths
