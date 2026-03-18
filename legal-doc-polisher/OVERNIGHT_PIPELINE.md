# Overnight Autonomous Testing & Self-Improvement Pipeline

## Mission Statement
While you sleep, Claude works all night processing 100 legal documents through
an iterative improvement loop. For each document, Claude Vision compares the
before and after, identifies what the polisher got right, what it missed, and
what it broke. The program is then automatically updated and the document is
re-processed until vision confirms it's clean. By morning, you wake up to a
battle-tested, high-precision formatting tool with a full report of every
fix made overnight.

---

## Pipeline Architecture

```
FOR EACH DOCUMENT (1-100):
  ┌─────────────────────────────────────────────┐
  │  1. Render ORIGINAL document to page images  │
  │  2. Run polisher on the document              │
  │  3. Render POLISHED document to page images   │
  │  4. Send BOTH to Claude Vision side-by-side   │
  │  5. Vision reviews against 120-point checklist │
  │  6. Vision returns structured verdict:         │
  │     - PASS items (formatting fixed correctly)  │
  │     - FAIL items (formatting still broken)     │
  │     - REGRESSION items (new bugs introduced)   │
  │  7. For each FAIL/REGRESSION:                  │
  │     - Auto-generate a code patch               │
  │     - Apply the patch                          │
  │     - Re-run polisher on this document         │
  │     - Re-check with Vision (max 3 retries)     │
  │  8. Run regression tests on prior documents    │
  │  9. Log everything to the morning report       │
  └─────────────────────────────────────────────┘
  NEXT DOCUMENT (carrying all improvements forward)
```

---

## The 120-Point Vision Review Checklist

### A. HEADING CONSISTENCY (15 checks)
- [ ] A1. All Heading 1s use identical font family
- [ ] A2. All Heading 1s use identical font size
- [ ] A3. All Heading 1s have consistent bold/underline treatment
- [ ] A4. All Heading 2s use identical font family
- [ ] A5. All Heading 2s use identical font size
- [ ] A6. All Heading 2s have consistent bold/underline treatment
- [ ] A7. All Heading 3s use identical formatting
- [ ] A8. Heading hierarchy is visually clear (H1 > H2 > H3)
- [ ] A9. No heading uses a different font from the document standard
- [ ] A10. Section numbering format is consistent (1. vs 1) vs (1))
- [ ] A11. Article numbering is consistent (I, II, III or 1, 2, 3 — not mixed)
- [ ] A12. Heading alignment is consistent within each level
- [ ] A13. Space before headings is consistent
- [ ] A14. Space after headings is consistent
- [ ] A15. No orphan headings (heading at bottom of page with no body text following)

### B. BODY TEXT CONSISTENCY (15 checks)
- [ ] B1. All body paragraphs use the same font family
- [ ] B2. All body paragraphs use the same font size
- [ ] B3. All body paragraphs have consistent alignment (left/justify)
- [ ] B4. Line spacing is uniform across all body paragraphs
- [ ] B5. Space before paragraphs is consistent
- [ ] B6. Space after paragraphs is consistent
- [ ] B7. First-line indentation is consistent (or consistently absent)
- [ ] B8. No stray font color changes in body text
- [ ] B9. No accidental bold/italic in body text
- [ ] B10. No mixed font sizes within a single paragraph
- [ ] B11. Text is not cut off at margins
- [ ] B12. No rivers of white space in justified text
- [ ] B13. No orphan lines (single line at top of page)
- [ ] B14. No widow lines (single line at bottom of page)
- [ ] B15. Paragraph spacing doesn't vary between sections

### C. QUOTE & PUNCTUATION CONSISTENCY (12 checks)
- [ ] C1. All double quotes are smart (curly) quotes
- [ ] C2. All single quotes/apostrophes are smart
- [ ] C3. No straight quotes remain in the document
- [ ] C4. Opening quotes face the right direction
- [ ] C5. Closing quotes face the right direction
- [ ] C6. Apostrophes in contractions use right single quote
- [ ] C7. Em dashes are consistent (— not --)
- [ ] C8. En dashes are consistent in ranges (2024–2029)
- [ ] C9. Ellipses are consistent (… not ...)
- [ ] C10. No double punctuation (.., ;;, etc.)
- [ ] C11. Period/semicolon consistency in enumerated lists
- [ ] C12. Oxford comma usage is consistent throughout

### D. LIST & NUMBERING CONSISTENCY (12 checks)
- [ ] D1. No duplicate list labels ((a), (a) → (a), (b))
- [ ] D2. No gaps in list numbering sequences
- [ ] D3. List label format is consistent within each list
- [ ] D4. Nested list indentation increases properly
- [ ] D5. List labels align vertically
- [ ] D6. Hanging indent is consistent across all lists
- [ ] D7. Bullet style is consistent (if bullets are used)
- [ ] D8. Numbered list restarts are intentional
- [ ] D9. Sub-list format is consistent ((i), (ii) or (a), (b) — not mixed)
- [ ] D10. List item text alignment is consistent
- [ ] D11. No phantom numbering (visible numbers without list formatting)
- [ ] D12. Terminal punctuation in list items is consistent

### E. CROSS-REFERENCE INTEGRITY (10 checks)
- [ ] E1. All "Section X.X" references point to existing sections
- [ ] E2. All "Article X" references point to existing articles
- [ ] E3. All "Exhibit X" references match existing exhibit labels
- [ ] E4. Section reference format is consistent (Section vs Sec. vs §)
- [ ] E5. No stale references to renamed/renumbered sections
- [ ] E6. Parenthetical descriptions match actual section titles
- [ ] E7. "Above"/"below" directional references are correct
- [ ] E8. No self-referential sections
- [ ] E9. Schedule/Appendix references match actual labels
- [ ] E10. Page number references (if any) are correct

### F. DEFINITION FORMATTING (10 checks)
- [ ] F1. Defined terms use consistent formatting (bold, quotes, or both)
- [ ] F2. All defined terms are actually defined in the definitions section
- [ ] F3. Definitions are in alphabetical order
- [ ] F4. Definition entries use consistent phrasing ("means" vs "shall mean")
- [ ] F5. No duplicate definitions
- [ ] F6. Defined terms used in body maintain their formatting
- [ ] F7. No circular definitions
- [ ] F8. Terminal punctuation in definition entries is consistent
- [ ] F9. Nested quotes within definitions are properly differentiated
- [ ] F10. Capitalization of defined terms is consistent throughout

### G. HEADER & FOOTER CONSISTENCY (10 checks)
- [ ] G1. Header font is consistent across all pages
- [ ] G2. Header content is consistent (or intentionally varies by section)
- [ ] G3. Footer font is consistent across all pages
- [ ] G4. Page numbering format is consistent
- [ ] G5. Page numbers are sequential (no unexpected restarts)
- [ ] G6. No "DRAFT" watermark on final documents
- [ ] G7. Confidentiality labels are consistent
- [ ] G8. No stale dates in headers/footers
- [ ] G9. Party names in headers match document body
- [ ] G10. Header/footer margins are consistent

### H. SIGNATURE BLOCK FORMATTING (10 checks)
- [ ] H1. All signature blocks use the same structure
- [ ] H2. "By:", "Name:", "Title:", "Date:" fields are consistent
- [ ] H3. Signature line formatting is consistent
- [ ] H4. Alignment of signature blocks is consistent
- [ ] H5. Entity names match the preamble exactly
- [ ] H6. Entity type (LLC, Corp, etc.) matches throughout
- [ ] H7. All required parties have signature blocks
- [ ] H8. No duplicate signature blocks
- [ ] H9. Date lines use consistent format
- [ ] H10. Spacing within signature blocks is uniform

### I. EXHIBIT & SCHEDULE FORMATTING (10 checks)
- [ ] I1. Exhibit labels are sequential (A, B, C — no gaps)
- [ ] I2. Exhibit title formatting is consistent (case, bold, underline)
- [ ] I3. Exhibit headers reference the parent document
- [ ] I4. No placeholder text in exhibits ([TO BE ATTACHED])
- [ ] I5. Multi-page exhibits have consistent continuation headers
- [ ] I6. Exhibit page numbering is consistent
- [ ] I7. Legal descriptions use consistent formatting
- [ ] I8. Exhibit fonts match the main document
- [ ] I9. Schedule formatting matches exhibit formatting
- [ ] I10. Attachment/addendum labels are consistent

### J. TEMPLATE & BOILERPLATE ARTIFACTS (8 checks)
- [ ] J1. No placeholder text remains ([INSERT], [TBD], ________)
- [ ] J2. No conflicting governing law clauses
- [ ] J3. No duplicate boilerplate sections
- [ ] J4. No wrong party-type language (Seller in a Lease)
- [ ] J5. No conditional/instructional text ([If guarantor...])
- [ ] J6. Property address is consistent throughout
- [ ] J7. No tracked changes artifacts (red text, strikethrough)
- [ ] J8. No hidden comments remaining

### K. OVERALL VISUAL QUALITY (8 checks)
- [ ] K1. Document looks professionally formatted at first glance
- [ ] K2. No visual "jarring" transitions between sections
- [ ] K3. Consistent visual weight across the document
- [ ] K4. Tables (if any) have consistent formatting
- [ ] K5. No awkward page breaks mid-sentence
- [ ] K6. Margins are consistent throughout
- [ ] K7. No visible formatting artifacts (boxes, borders, shading)
- [ ] K8. Overall document is visually cohesive

---

## Overnight Schedule (8 hours)

### Hour 1: Setup & First 10 Documents (Chunk 1)
- Download and convert documents
- Process docs 1-10 with current rules
- Vision reviews each before/after
- Generate first round of code patches
- Apply patches, re-test, confirm fixes
- Run regression on docs 1-10

### Hour 2: Documents 11-20 (Chunk 2) + Patch Cycle
- Process docs 11-20 (carrying chunk 1 improvements)
- Vision reviews, generates feedback
- Apply new patches (building on chunk 1 fixes)
- Re-test any docs that had regressions
- Regression test against docs 1-20

### Hour 3: Documents 21-30 (Chunk 3) + Patch Cycle
- Process docs 21-30
- By now, common patterns should be well-handled
- Focus on edge cases and rare formatting issues
- Update rules config thresholds based on data

### Hour 4: Documents 31-40 (Chunk 4) + Patch Cycle
- Process docs 31-40
- Mid-point analysis: review improvement trajectory
- Identify any systematic false positives
- Adjust tolerance thresholds if needed

### Hour 5: Documents 41-60 (Chunks 5-6) + Patch Cycle
- Process docs 41-60 (accelerating — fewer new issues expected)
- Focus on header/footer and exhibit edge cases
- Deep-dive on any recurring failure patterns

### Hour 6: Documents 61-80 (Chunks 7-8) + Patch Cycle
- Process docs 61-80
- Cross-reference and definition rules should be mature
- Focus on visual quality and subtle spacing issues

### Hour 7: Documents 81-100 (Chunks 9-10) + Final Patches
- Process final 20 documents
- Apply any remaining patches
- These docs should see minimal issues (proof of improvement)

### Hour 8: Regression Sweep + Morning Report
- Full regression test: re-run ALL 100 documents with final code
- Vision spot-check 10 random documents
- Generate comprehensive morning report
- Compile improvement statistics
- Write the "Changes Made Tonight" changelog

---

## Morning Report Contents

When you wake up, you'll find:

1. **SUMMARY.md** — One-page overview: docs processed, pass rate, total fixes
2. **CHANGELOG.md** — Every code change made overnight with rationale
3. **CHECKLIST_RESULTS.md** — 120-point checklist scored across all 100 docs
4. **REGRESSION_REPORT.md** — Proof that fixes didn't break prior docs
5. **IMPROVEMENT_TRAJECTORY.png** — Graph of pass rate improving over 100 docs
6. **REMAINING_ISSUES.md** — Any items that couldn't be auto-fixed (need human review)
7. **pipeline_report.json** — Full machine-readable data for every document
