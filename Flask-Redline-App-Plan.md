# Legal Redline Assistant — Flask App Plan

## Purpose

A locally-run Flask web app (used in Google Chrome) that acts as a stand-in
legal assistant. The user uploads three files; the app reads anchor markers the
user has hand-written on a PDF redline (in PDF Expert), translates those
anchors into edit operations, and returns a Word `.docx` file with native
**track changes** showing the resulting revisions.

## Inputs (three uploads)

| # | File | Format | Role |
|---|------|--------|------|
| 1 | Original document | `.docx` | Baseline / "clean" version |
| 2 | Modified document | `.docx` | Counterparty's or current working version |
| 3 | Annotated redline | `.pdf` | A Word Compare or Litera redline that the user further marked up in PDF Expert with anchor instructions |

## Output

A single `.docx` file containing **Word-native track changes**
(`w:ins` / `w:del` revisions authored as "Legal Assistant"), built by applying
the anchor-driven instructions on top of the **modified** document so the user
can accept/reject each change in Word.

---

## Anchor Grammar (handwritten / typed on the PDF in PDF Expert)

Anchors are short tokens placed in PDF Expert annotations (text notes,
callouts, or stamps) directly adjacent to the affected text in the redline.

| Anchor | Meaning | Operand |
|--------|---------|---------|
| `INS` | Re-insert / restore a provision that the redline removed | The struck-through text the anchor points to (or quoted text in the note) |
| `DEL` | Delete the adjacent text | The underlined/inserted or existing text the anchor points to |
| `KEEP` | Accept the redline change as-is (no further edit) | Nearest revision |
| `REJ` | Reject the redline change (revert to original) | Nearest revision |
| `REPL: "<new text>"` | Replace adjacent text with the quoted text | Adjacent run + new text from note |
| `MOVE → §X.Y` | Move the adjacent block to the cited section | Adjacent block + target heading |
| `CMT: "<note>"` | Attach a Word comment, no text change | Anchor location |

Conventions:
- Anchors are case-insensitive but stored uppercase internally.
- The note's *anchor point* in the PDF (its `/Rect` or popup target) identifies
  the location; the note's text body carries the operand.
- Free-hand strikethrough/underline drawn in PDF Expert is also parsed as
  `DEL` / `INS` respectively.

---

## Architecture

```
Chrome ──HTTP──▶ Flask (app.py)
                  ├─ routes/upload.py   (multipart form, validation)
                  ├─ services/pdf_anchors.py    (PyMuPDF: extract annots + text-under-rect)
                  ├─ services/anchor_parser.py  (tokenize + validate anchor grammar)
                  ├─ services/doc_aligner.py    (align PDF spans → docx runs in Modified.docx)
                  ├─ services/redline_writer.py (emit w:ins / w:del / w:comment OOXML)
                  └─ routes/download.py (returns generated .docx)
```

### Key libraries
- `Flask` — web server
- `PyMuPDF` (`fitz`) — read PDF annotations + text geometry
- `python-docx` — read/write `.docx` structure
- `lxml` — direct OOXML manipulation for `w:ins` / `w:del` / `w:comment`
  (python-docx alone can't author track changes)
- `rapidfuzz` — fuzzy match PDF text spans → docx runs
- `pydantic` — validate parsed anchor objects

### Data flow
1. **Upload** — user posts the three files; server stores them in a per-session
   temp dir.
2. **Anchor extraction** — `pdf_anchors.py` walks every page, pulls each
   annotation's `/Contents`, `/Rect`, `/Subtype`, popup target, and the text
   under the rect.
3. **Parse** — `anchor_parser.py` converts each annotation into an
   `EditOp(kind, target_text, new_text?, location_hint)`.
4. **Align** — `doc_aligner.py` locates `target_text` inside the **Modified**
   `.docx` (paragraph + run indices) using exact match, then fuzzy fallback.
5. **Apply** — `redline_writer.py` writes the change as an OOXML revision so
   Word renders it as a native track-change authored by "Legal Assistant".
6. **Download** — Flask serves the resulting `.docx`; a small results page
   lists every applied op and any that failed to align.

---

## UI (single page, Chrome)

- Three drag-and-drop zones (Original / Modified / Annotated PDF).
- "Generate Track-Changes Doc" button.
- Result panel: download link + table of operations
  (`anchor`, `target snippet`, `status: applied | unmatched | ambiguous`).
- No accounts, no DB — runs locally on `127.0.0.1:5000`.

---

## Risks / Open Questions

- **PDF Expert annotation fidelity** — confirm that text notes, freehand
  strikethrough, and stamps all serialize as standard PDF annotations
  (`/Text`, `/StrikeOut`, `/Stamp`) readable by PyMuPDF. If freehand isn't
  reliable, require typed `INS`/`DEL` notes only.
- **Original vs. Modified as base** — plan applies edits on top of Modified.
  Confirm with user; alternative is to re-derive a clean diff from
  Original→Modified first, then layer anchor edits.
- **Word track-changes authoring** — python-docx has no first-class API; we
  must inject `w:ins`/`w:del` elements directly. Worth a spike before full
  build.
- **Ambiguous targets** — if anchor text appears multiple times, fall back to
  PDF page/coordinate proximity, then surface as "needs review" in the UI.

---

## Build Checklist

### Phase 0 — Spikes (de-risk)
- [ ] Confirm PyMuPDF reads PDF Expert annotations end-to-end on a sample file
- [ ] Spike: write a `w:ins` + `w:del` revision into a `.docx` and verify Word
      shows native track changes
- [ ] Decide base document for edits (Modified vs. derived diff) with user

### Phase 1 — Project skeleton
- [ ] `app.py` Flask entry, `127.0.0.1:5000`
- [ ] `requirements.txt` (Flask, PyMuPDF, python-docx, lxml, rapidfuzz, pydantic)
- [ ] `templates/index.html` with three upload zones + submit
- [ ] `static/` minimal CSS
- [ ] `run.sh` to launch in dev mode

### Phase 2 — Upload + storage
- [ ] `routes/upload.py` accepts multipart POST of 3 files
- [ ] Validate MIME / extensions (`.docx`, `.docx`, `.pdf`)
- [ ] Per-request temp dir under `./tmp/<uuid>/`
- [ ] Size cap + friendly error messages

### Phase 3 — PDF anchor extraction
- [ ] `services/pdf_anchors.py`: iterate pages, collect annotations
- [ ] For each annotation capture: subtype, rect, contents, popup parent,
      page number, and text-under-rect via `page.get_text("words")`
- [ ] Unit tests with a fixture PDF

### Phase 4 — Anchor grammar parser
- [ ] `services/anchor_parser.py` tokenizes `INS | DEL | KEEP | REJ | REPL: "..."
      | MOVE → §X.Y | CMT: "..."`
- [ ] Returns typed `EditOp` objects (pydantic)
- [ ] Friendly errors for malformed anchors

### Phase 5 — Alignment to Modified.docx
- [ ] `services/doc_aligner.py` builds a flat `(para_idx, run_idx, text)` index
- [ ] Exact-match lookup for `target_text`
- [ ] `rapidfuzz` fallback above a threshold; ambiguity → "needs review"

### Phase 6 — Track-changes writer
- [ ] `services/redline_writer.py` injects `w:ins` / `w:del` with
      `w:author="Legal Assistant"` and current `w:date`
- [ ] Implements: insert, delete, replace (= del + ins), comment
      (`w:commentRangeStart` / `w:commentRangeEnd` / `w:commentReference`)
- [ ] Preserves run formatting at the edit site

### Phase 7 — Results UI + download
- [ ] `routes/download.py` streams the generated `.docx`
- [ ] Results table: anchor, snippet, status, page/section
- [ ] Show unmatched anchors prominently so user can fix the PDF and re-run

### Phase 8 — Hardening
- [ ] Clean up temp dirs on success/error
- [ ] Logging to `./logs/app.log`
- [ ] README with install + run steps
- [ ] Smoke test on a real redline + PDF Expert markup

---

## Out of scope (v1)

- Multi-user / auth
- Cloud deployment
- Re-running Word/Litera compare inside the app
- OCR of handwritten anchors (typed PDF Expert notes only)
