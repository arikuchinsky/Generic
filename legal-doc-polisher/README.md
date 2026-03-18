# Legal Document Polisher

AI-powered tool that automatically detects and fixes formatting inconsistencies in legal documents (.docx). Uses a hybrid approach: fast deterministic rules for known patterns + Claude Vision for catching subtle visual issues.

## Architecture

```
React UI (Vite + TypeScript + Tailwind)
    ↕ REST API (polling for job status)
FastAPI Backend (Python)
    ├── Style Profiler (majority-vote style inference)
    ├── Deterministic Rules Engine (8 rules)
    ├── Vision Pipeline (render → Claude Vision → parse → fix)
    ├── Learning System (SQLite examples DB)
    └── EDGAR Self-Test Pipeline (100-doc recursive testing)
```

## Formatting Rules

### Base Rules
- **Heading Style** — Bold, underline, font, size, alignment consistency per heading level
- **Quote Style** — Straight → smart quote conversion with context-aware apostrophe handling
- **List Labels** — Duplicate labels, sequence gaps, format consistency
- **Paragraph Format** — Alignment, spacing, indentation deviations from dominant style

### CRE-Specific Rules (Commercial Real Estate)
- **Cross References** — Dangling section/exhibit references, format consistency (Section vs Sec. vs §)
- **Definition Format** — Defined term consistency (bold/quoted), alphabetical order, undefined terms
- **Signature Blocks** — Field formatting, alignment, spacing consistency across blocks
- **Headers/Footers** — Font consistency, page number format consistency across sections

## Quick Start

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Environment
```
LDP_ANTHROPIC_API_KEY=sk-ant-...   # Required for vision pass
LDP_VISION_ENABLED=true             # Toggle vision pipeline
```

## EDGAR Self-Test Pipeline

Run 100 real legal documents through the polisher in 10 chunks:
```bash
cd backend
python -m app.engine.edgar_sampler --chunks 10 --per-chunk 10
```

This downloads documents from SEC EDGAR, processes them, analyzes patterns, and generates recommendations for rule improvements. Results are saved to `data/self_test/`.

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | /api/polish | Upload .docx + options |
| GET | /api/polish/{id}/status | Poll job progress |
| GET | /api/polish/{id}/result | Get change report |
| GET | /api/polish/{id}/download | Download polished .docx |
| GET/POST/DELETE | /api/examples | Learning examples CRUD |
| GET/PUT | /api/rules | Rule configuration |
