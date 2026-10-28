# SpendSense

Upload a bank or UPI statement export and SpendSense turns it into a clean, categorised ledger, a dashboard, and shareable Word and PowerPoint reports.

Bank exports are messy. Every bank uses different column names, puts junk rows above the header, writes amounts as `1,23,456.00` or `300 Dr`, and sometimes exports the same row twice. SpendSense handles all of that with Pandas before anything is analysed.

## What it does

- **Reads real-world statement formats** (CSV or Excel): it finds the header row, maps column aliases (`Narration`/`Particulars`/`Description`…), handles separate Withdrawal/Deposit columns *or* one Amount + Dr/Cr column, parses Indian number formats, and reads day-first and ISO dates correctly.
- **Validates the data**: it drops footer and opening-balance rows and removes exact duplicates. The running balance is part of the duplicate check, so two identical coffees on the same day are kept. It reports what it changed after every upload.
- **Categorises transactions** in this order: a category you set earlier for that merchant, then keyword rules, then retrieval-augmented categorisation for merchants nothing else recognised (see below). Only merchant names are sent to the API: no amounts, dates or account details.
- **Learns from corrections**: change one transaction's category and the rest of that merchant's transactions follow, now and in future uploads. The correction is also embedded into the vector store, so *similar* merchants benefit too.
- **Analyses**: income, spending and savings rate, category breakdown, month-by-month trend, top merchants, and recurring payments (subscriptions and rent).
- **Generates reports**: a Word report (python-docx) and a PowerPoint summary (python-pptx), both with matplotlib charts, built straight from the data.

## Stack

| Layer | Tools |
|---|---|
| API | Python, FastAPI, SQLAlchemy 2 (SQLite by default) |
| Data | Pandas |
| Retrieval (optional) | sentence-transformers (all-MiniLM-L6-v2), ChromaDB |
| Reports | python-docx, python-pptx, matplotlib |
| Frontend | React 19 (hooks), Vite, Recharts |
| Tests | pytest (50 tests: parsing, validation, categorisation, retrieval, analytics, API, reports) |

## Run it

**Backend** (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload            # http://localhost:8000/docs for the API explorer
```

**Frontend** (Node 20+), in a second terminal:

```bash
cd frontend
npm install
npm run dev                              # http://localhost:5173
```

Then upload `sample_data/bank_statement_sample.csv` and `sample_data/upi_export_sample.csv`. Both are generated, fake data in two different formats. To regenerate them, run `python sample_data/generate_samples.py`.

**Tests:**

```bash
cd backend && pytest
```

### Optional: LLM categorisation

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export SPENDSENSE_LLM_MODEL=claude-haiku-5-5   # optional, this is the default
```

Without a key, unrecognised merchants go to "Other" (unless retrieval finds a very close match, below) and you can sort them from the dashboard's "Needs a category" filter.

### Optional: retrieval-augmented categorisation (RAG)

```bash
pip install -r requirements-rag.txt
```

How it works, for a merchant that no learned label or keyword rule recognises:

1. **Embed.** Every merchant whose category is known (your corrections and earlier LLM answers) is embedded with a sentence-transformer (`all-MiniLM-L6-v2`, runs locally) after stripping statement noise like UPI handles and reference numbers.
2. **Retrieve.** The vectors live in a persistent ChromaDB collection (`./vector_store`, cosine similarity). An unknown merchant is embedded and its top-5 nearest labelled merchants are fetched.
3. **Generate.** Those neighbours go into the Claude prompt as examples ("`thirdwave coffee` -> Food & Dining, user-confirmed, similarity 0.92"), so the answer follows how *you* categorise things rather than a generic guess.
4. **No API key?** If the closest neighbour is a merchant *you* labelled and it is very similar (cosine ≥ 0.8, `SPENDSENSE_KNN_THRESHOLD`), its category is used directly: a nearest-neighbour classifier over your own corrections. LLM labels are never trusted this way, so the model can't reinforce its own mistakes.

The store updates live: every correction in the dashboard is embedded and upserted immediately, and on startup it is synced with the database (only new or changed labels are re-embedded). Transactions categorised this way show `category_source = "similar"`.

| Variable | Default | Purpose |
|---|---|---|
| `SPENDSENSE_RAG` | `1` | Set to `0` to turn retrieval off |
| `SPENDSENSE_VECTOR_DIR` | `./vector_store` | Where ChromaDB persists vectors |
| `SPENDSENSE_EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `SPENDSENSE_KNN_THRESHOLD` | `0.8` | Similarity needed to reuse a user label without the LLM |

Without the optional packages, the retrieval step is skipped and everything else works as before. `GET /api/health` reports whether retrieval is active and how many merchants are indexed.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/statements` | Upload a CSV/XLSX statement (multipart `file`) |
| `GET` | `/api/statements` | List uploads with their cleaning stats |
| `DELETE` | `/api/statements/{id}` | Remove a statement and its transactions |
| `GET` | `/api/transactions?month=YYYY-MM&category=…` | List transactions |
| `PATCH` | `/api/transactions/{id}` | Change a category (learned for that merchant) |
| `GET` | `/api/summary` | Totals, categories, monthly trend, insights |
| `GET` | `/api/reports/docx` · `/api/reports/pptx` | Download the generated report |

## Project layout

```
backend/
  app/
    parser.py       # load + clean + validate statements (Pandas)
    categorizer.py  # keyword rules + retrieval-grounded Claude API fallback
    retriever.py    # embeddings + ChromaDB vector store of labelled merchants
    analytics.py    # summaries, recurring-payment detection, insights
    charts.py       # matplotlib charts for the reports
    reports.py      # Word + PowerPoint generation
    models.py       # SQLAlchemy models
    main.py         # FastAPI routes
  tests/
frontend/src/
  useSpendData.js   # all server state in one hook
  components/       # Headline + category ribbon, monthly chart, ledger, reports
sample_data/        # fake statements + generator
```

## Ideas for next steps

- PDF statement import (pdfplumber table extraction)
- Budgets per category, with alerts in the report when one is exceeded
- Scheduled monthly report emailed automatically
- Docker Compose for one-command setup
