# SpendSense

Upload a bank or UPI statement export and SpendSense turns it into a clean, categorised ledger, a dashboard, and shareable Word and PowerPoint reports.

Bank exports are messy. Every bank uses different column names, puts junk rows above the header, writes amounts as `1,23,456.00` or `300 Dr`, and sometimes exports the same row twice. SpendSense handles all of that with Pandas before anything is analysed.

## What it does

- **Reads real-world statement formats** (CSV or Excel): it finds the header row, maps column aliases (`Narration`/`Particulars`/`Description`…), handles separate Withdrawal/Deposit columns *or* one Amount + Dr/Cr column, parses Indian number formats, and reads day-first and ISO dates correctly.
- **Validates the data**: it drops footer and opening-balance rows and removes exact duplicates. The running balance is part of the duplicate check, so two identical coffees on the same day are kept. It reports what it changed after every upload.
- **Categorises transactions** in this order: a category you set earlier for that merchant, then keyword rules, then an optional Claude API call for merchants nothing else recognised. Only merchant names are sent to the API: no amounts, dates or account details.
- **Learns from corrections**: change one transaction's category and the rest of that merchant's transactions follow, now and in future uploads.
- **Analyses**: income, spending and savings rate, category breakdown, month-by-month trend, top merchants, and recurring payments (subscriptions and rent).
- **Generates reports**: a Word report (python-docx) and a PowerPoint summary (python-pptx), both with matplotlib charts, built straight from the data.

## Stack

| Layer | Tools |
|---|---|
| API | Python, FastAPI, SQLAlchemy 2 (SQLite by default) |
| Data | Pandas |
| Reports | python-docx, python-pptx, matplotlib |
| Frontend | React 19 (hooks), Vite, Recharts |
| Tests | pytest (41 tests: parsing, validation, categorisation, analytics, API, reports) |

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

Without a key, unrecognised merchants go to "Other" and you can sort them from the dashboard's "Needs a category" filter.

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
    categorizer.py  # keyword rules + optional Claude API fallback
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
