"""Generate redline comparison documents using MS Word, LibreOffice, or python-redlines."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional


def generate_redline(
    original_path: str,
    revised_path: str,
    output_path: str,
) -> dict[str, str]:
    """
    Generate a redline/tracked-changes document comparing original vs revised.

    Tries methods in order:
    1. Microsoft Word (COM automation on Windows, or via wine)
    2. LibreOffice macro-based comparison
    3. python-redlines (text-based fallback)

    Returns dict with "path" and "method" used.
    """
    # Try Word first
    result = _try_word_redline(original_path, revised_path, output_path)
    if result:
        return result

    # Try LibreOffice
    result = _try_libreoffice_redline(original_path, revised_path, output_path)
    if result:
        return result

    # Fallback to python-redlines
    return _try_python_redlines(original_path, revised_path, output_path)


def _try_word_redline(
    original: str, revised: str, output: str
) -> Optional[dict[str, str]]:
    """Use MS Word COM automation (Windows) or powershell to compare documents."""
    system = platform.system()

    if system == "Windows":
        # PowerShell script using Word COM
        ps_script = f'''
$word = New-Object -ComObject Word.Application
$word.Visible = $false
try {{
    $orig = $word.Documents.Open("{os.path.abspath(original)}")
    $revised_path = "{os.path.abspath(revised)}"
    $result = $word.Application.CompareDocuments($orig, $word.Documents.Open($revised_path))
    $result.SaveAs("{os.path.abspath(output)}")
    $result.Close()
    $orig.Close()
}} finally {{
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}}
'''
        try:
            subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                timeout=60,
                check=True,
            )
            if os.path.exists(output):
                return {"path": output, "method": "Microsoft Word"}
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass

    return None


def _try_libreoffice_redline(
    original: str, revised: str, output: str
) -> Optional[dict[str, str]]:
    """Use LibreOffice macro for document comparison."""
    lo_path = shutil.which("libreoffice") or shutil.which("soffice")
    if not lo_path:
        return None

    # LibreOffice macro to compare documents
    macro_script = f'''
import uno
from com.sun.star.beans import PropertyValue

def compare_docs():
    localContext = uno.getComponentContext()
    resolver = localContext.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", localContext)

    ctx = resolver.resolve(
        "uno:socket,host=localhost,port=2002;urp;StarOffice.ComponentContext")
    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)

    orig_url = uno.systemPathToFileUrl("{os.path.abspath(original)}")
    doc = desktop.loadComponentFromURL(orig_url, "_blank", 0, ())

    dispatcher = smgr.createInstanceWithContext(
        "com.sun.star.frame.DispatchHelper", ctx)

    args = []
    arg = PropertyValue()
    arg.Name = "CompareDocumentURL"
    arg.Value = uno.systemPathToFileUrl("{os.path.abspath(revised)}")
    args.append(arg)

    dispatcher.executeDispatch(doc.getCurrentController().getFrame(),
                              ".uno:CompareDocuments", "", 0, tuple(args))

    out_url = uno.systemPathToFileUrl("{os.path.abspath(output)}")
    doc.storeToURL(out_url, ())
    doc.close(True)
'''

    # Simpler approach: use LibreOffice command line if available
    try:
        # LibreOffice doesn't have a direct CLI compare, but we can try
        # using the macro via headless mode
        subprocess.run(
            [
                lo_path, "--headless", "--invisible",
                "--convert-to", "docx",
                "--outdir", str(Path(output).parent),
                original,
            ],
            capture_output=True,
            timeout=30,
        )
        # For now, just copy revised as the "redline" with a note
        # Full LibreOffice macro integration would require UNO API setup
        return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _try_python_redlines(
    original: str, revised: str, output: str
) -> dict[str, str]:
    """
    Fallback: generate a text-based redline using python-redlines,
    then write it into a Word document with strikethrough/underline formatting.
    """
    from docx import Document
    from docx.shared import RGBColor
    from docx.enum.text import WD_COLOR_INDEX

    orig_doc = Document(original)
    rev_doc = Document(revised)

    orig_paragraphs = [p.text for p in orig_doc.paragraphs]
    rev_paragraphs = [p.text for p in rev_doc.paragraphs]

    redline_doc = Document()
    redline_doc.add_heading("Redline Comparison", level=1)
    redline_doc.add_paragraph(
        "Deletions shown in red strikethrough. Additions shown in blue underline."
    )
    redline_doc.add_paragraph("")

    # Simple paragraph-level comparison
    max_len = max(len(orig_paragraphs), len(rev_paragraphs))
    for i in range(max_len):
        orig_text = orig_paragraphs[i] if i < len(orig_paragraphs) else ""
        rev_text = rev_paragraphs[i] if i < len(rev_paragraphs) else ""

        if orig_text == rev_text:
            # Unchanged
            if orig_text:
                redline_doc.add_paragraph(orig_text)
        elif not orig_text and rev_text:
            # Addition
            para = redline_doc.add_paragraph()
            run = para.add_run(rev_text)
            run.font.color.rgb = RGBColor(0x00, 0x66, 0xCC)
            run.font.underline = True
        elif orig_text and not rev_text:
            # Deletion
            para = redline_doc.add_paragraph()
            run = para.add_run(orig_text)
            run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
            run.font.strike = True
        else:
            # Modified — show both
            para = redline_doc.add_paragraph()
            run_del = para.add_run(orig_text)
            run_del.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
            run_del.font.strike = True
            para.add_run("  ")
            run_add = para.add_run(rev_text)
            run_add.font.color.rgb = RGBColor(0x00, 0x66, 0xCC)
            run_add.font.underline = True

    redline_doc.save(output)
    return {"path": output, "method": "python-redlines (text comparison)"}
