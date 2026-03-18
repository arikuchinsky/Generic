"""OS detection and Word automation path selection."""

from __future__ import annotations

import platform
import shutil
import subprocess
from enum import Enum
from pathlib import Path


class Platform(str, Enum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


def detect_platform() -> Platform:
    """Detect the current operating system."""
    system = platform.system().lower()
    if system == "windows":
        return Platform.WINDOWS
    elif system == "darwin":
        return Platform.MACOS
    return Platform.LINUX


def is_word_available() -> bool:
    """Check if Microsoft Word is available for rendering."""
    plat = detect_platform()

    if plat == Platform.WINDOWS:
        try:
            import win32com.client
            word = win32com.client.gencache.EnsureDispatch("Word.Application")
            word.Quit()
            return True
        except Exception:
            return False

    elif plat == Platform.MACOS:
        # Check if Word is in /Applications
        return Path("/Applications/Microsoft Word.app").exists()

    else:
        # Linux: check for LibreOffice as fallback
        return shutil.which("libreoffice") is not None


def get_libreoffice_path() -> str | None:
    """Find the LibreOffice binary path."""
    for name in ("libreoffice", "soffice"):
        path = shutil.which(name)
        if path:
            return path
    return None


def docx_to_pdf_libreoffice(docx_path: Path, output_dir: Path) -> Path:
    """Convert a .docx to PDF using LibreOffice (Linux/fallback)."""
    lo_path = get_libreoffice_path()
    if not lo_path:
        raise RuntimeError("LibreOffice not found. Install it for PDF conversion.")

    subprocess.run(
        [lo_path, "--headless", "--convert-to", "pdf", "--outdir", str(output_dir), str(docx_path)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    pdf_name = docx_path.stem + ".pdf"
    pdf_path = output_dir / pdf_name
    if not pdf_path.exists():
        raise RuntimeError(f"PDF conversion failed: {pdf_path} not created")
    return pdf_path


def docx_to_pdf_word_windows(docx_path: Path, output_path: Path) -> Path:
    """Convert .docx to PDF using Word COM automation (Windows)."""
    import win32com.client

    word = win32com.client.gencache.EnsureDispatch("Word.Application")
    word.Visible = False
    try:
        doc = word.Documents.Open(str(docx_path.resolve()))
        doc.SaveAs(str(output_path.resolve()), FileFormat=17)  # wdFormatPDF
        doc.Close()
    finally:
        word.Quit()
    return output_path


def docx_to_pdf_word_mac(docx_path: Path, output_path: Path) -> Path:
    """Convert .docx to PDF using AppleScript/Word on macOS."""
    script = f'''
    tell application "Microsoft Word"
        open POSIX file "{docx_path.resolve()}"
        set theDoc to active document
        save as theDoc file name POSIX file "{output_path.resolve()}" file format format PDF
        close theDoc saving no
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=120)
    return output_path


def docx_to_pdf(docx_path: Path, output_dir: Path) -> Path:
    """Convert .docx to PDF using the best available method for the platform."""
    plat = detect_platform()
    output_path = output_dir / (docx_path.stem + ".pdf")

    if plat == Platform.WINDOWS:
        try:
            return docx_to_pdf_word_windows(docx_path, output_path)
        except Exception:
            return docx_to_pdf_libreoffice(docx_path, output_dir)

    elif plat == Platform.MACOS:
        try:
            return docx_to_pdf_word_mac(docx_path, output_path)
        except Exception:
            return docx_to_pdf_libreoffice(docx_path, output_dir)

    else:
        return docx_to_pdf_libreoffice(docx_path, output_dir)
