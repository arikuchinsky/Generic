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
the anchor-driven instructions **on top of the Modified document**, preserving
its existing formatting (styles, fonts, numbering, tables, headers/footers).
Each anchor becomes a tracked revision so the user can accept/reject in Word.

**Base document is locked to Modified.docx.** The Original is used only as a
*source of truth* for `INS` operations (so we can pull the exact original
phrasing back in) and as a sanity check on alignment.

---

## PDF Expert Markup Rules (strict — typed annotations only)

To make parsing reliable, the app supports a **fixed set of typed annotations**
only. Freehand drawing, highlights without notes, and ad-hoc shapes are
ignored. If you follow these rules, the app can handle the markup
deterministically.

### Required annotation type
Use **PDF Expert's "Note" / "Text Comment" annotation** (the speech-bubble
icon) anchored next to the text you want to act on. The note's *body text*
must start with one of the commands below.

### Command syntax (always uppercase command, then a colon, then args)

| Command | Body text the user types | Effect on Modified.docx |
|---------|--------------------------|-------------------------|
| `INS` | `INS: "<exact text from Original>"` | Insert that text at the anchor point as a tracked insertion |
| `DEL` | `DEL: "<text to remove>"` | Delete that text at the anchor point as a tracked deletion |
| `REPL` | `REPL: "<old text>" -> "<new text>"` | Tracked delete of `<old>` + tracked insert of `<new>` |
| `KEEP` | `KEEP` (no args) | Accept the nearest redline change in the Modified doc as-is (no edit emitted) |
| `REJ` | `REJ` (no args) | Reject the nearest redline change — emit edits that restore the Original wording |
| `CMT` | `CMT: "<note text>"` | Attach a Word comment at the anchor point; no text change |

### Placement rules
1. **One command per note.** Don't combine.
2. **Anchor the note next to the affected text** in the redline PDF — within
   the same line if possible. The note's coordinates locate the edit; the
   quoted text disambiguates within that paragraph.
3. **Quoted text must match the redline verbatim** (copy-paste from the PDF
   when possible). Whitespace and punctuation matter; case does not.
4. For `INS`, the quoted text must match a span found in the Original document
   (this is how the app pulls formatting and exact wording back in).
5. For ambiguous matches (same phrase appears multiple times in the
   paragraph), add a short context prefix:
   `DEL: "...prior 5 words... <text to remove>"`.

### What the app ignores
- Freehand strikethrough, underline, highlight, shapes, stamps
- Notes whose body doesn't start with a known command
- Notes on pages that are not part of the redline content (e.g. cover pages)

Unrecognized notes are surfaced in the results UI as "skipped — unknown
command" so nothing is silently dropped.

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
   `/Text` annotation's `/Contents`, `/Rect`, page number, and the text under
   the rect (for context). Non-Text annotations are ignored.
3. **Parse** — `anchor_parser.py` matches the body against the strict command
   regex set and returns typed `EditOp(kind, target_text, new_text?,
   location_hint)`. Unknown bodies become `SkippedOp(reason)`.
4. **Align on Modified.docx** — `doc_aligner.py` builds an index of
   `(para_idx, run_idx, text)` for the **Modified** doc and locates
   `target_text` by exact match first, then fuzzy fallback constrained to the
   paragraph nearest the PDF anchor's page/coordinates.
5. **Apply preserving formatting** — `redline_writer.py` splits the target run
   so adjacent formatting (bold, italic, font, style) is preserved on both
   sides of the edit, then injects `w:ins` / `w:del` (and `w:comment` for
   `CMT`) authored as "Legal Assistant".
6. **Download** — Flask serves the resulting `.docx`; the results page lists
   applied, skipped, and unmatched ops.

---

## UI (single page, Chrome)

- Three drag-and-drop zones (Original / Modified / Annotated PDF).
- "Generate Track-Changes Doc" button.
- Result panel: download link + table of operations
  (`anchor`, `target snippet`, `status: applied | unmatched | ambiguous`).
- No accounts, no DB — runs locally on `127.0.0.1:5000`.

---

## Decisions locked

- **Base document = Modified.docx.** All edits are tracked changes layered on
  top of it; the Modified doc's formatting is preserved verbatim.
- **PDF Expert markup = typed Note annotations only**, following the strict
  command grammar above. Freehand strokes and unrecognized notes are ignored
  (and surfaced as "skipped" in the results UI).

## Remaining risks

- **Word track-changes authoring** — python-docx has no first-class API; we
  must inject `w:ins`/`w:del` elements directly. Spike in Phase 0 before the
  full build.
- **Ambiguous targets** — if quoted text appears multiple times in the
  paragraph nearest the PDF anchor, fall back to PDF page/coordinate
  proximity, then surface as "needs review" in the UI so the user can add a
  context prefix and re-run.
- **Run splitting** — to preserve formatting, the writer must split docx runs
  cleanly at the edit boundary; covered in the Phase 0 spike.

---

## Build Checklist

### Phase 0 — Spikes (de-risk)
- [ ] Confirm PyMuPDF reads PDF Expert `/Text` Note annotations end-to-end on
      a sample file (body text + rect + page)
- [ ] Spike: split a docx run, write `w:ins` + `w:del` into the gap, verify
      Word shows native track changes and surrounding formatting is preserved
- [x] Base document decision: **Modified.docx** (locked)
- [x] Markup scope decision: **typed Note annotations, strict grammar** (locked)

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
- [ ] `services/anchor_parser.py` matches the strict command set:
      `INS:"..."`, `DEL:"..."`, `REPL:"..." -> "..."`, `KEEP`, `REJ`,
      `CMT:"..."`
- [ ] Returns typed `EditOp` objects (pydantic); unknown bodies become
      `SkippedOp(reason)` and flow through to the results UI
- [ ] Unit tests covering each command, malformed quotes, and unknown bodies

### Phase 5 — Alignment to Modified.docx
- [ ] `services/doc_aligner.py` builds a flat `(para_idx, run_idx, text)`
      index over the Modified doc
- [ ] Exact-match lookup for quoted `target_text`
- [ ] `rapidfuzz` fallback above a threshold, scoped to the paragraph nearest
      the PDF anchor's page+coords; ambiguity → "needs review"
- [ ] For `INS`, also locate the quoted text in the Original doc to copy
      exact wording (and optionally inherit run formatting from Original)

### Phase 6 — Track-changes writer
- [ ] `services/redline_writer.py` injects `w:ins` / `w:del` with
      `w:author="Legal Assistant"` and current `w:date`
- [ ] Implements: `INS`, `DEL`, `REPL` (= del + ins), `KEEP` (no-op),
      `REJ` (restore from Original), `CMT`
      (`w:commentRangeStart` / `w:commentRangeEnd` / `w:commentReference`
      + `comments.xml` part)
- [ ] **Run-splitting** preserves Modified.docx run formatting on both sides
      of every edit (bold, italic, font, color, style)

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
