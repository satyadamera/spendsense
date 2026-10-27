"""SpendSense REST API."""
from __future__ import annotations

import os
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import analytics, categorizer, reports
from .database import Base, engine, get_db
from .models import MerchantCategory, Statement, Transaction
from .parser import StatementFormatError, parse_statement
from .schemas import CategoryUpdate, StatementOut, TransactionOut, UploadResult

MAX_UPLOAD_BYTES = 5 * 1024 * 1024

@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SpendSense API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("SPENDSENSE_CORS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------------------------------- helpers

def _filtered(db: Session, statement_id: int | None, month: str | None, category: str | None):
    stmt = select(Transaction).order_by(Transaction.date.desc(), Transaction.id.desc())
    if statement_id is not None:
        stmt = stmt.where(Transaction.statement_id == statement_id)
    if category:
        stmt = stmt.where(Transaction.category == category)
    if month:
        try:
            year, mon = map(int, month.split("-"))
            start = date(year, mon, 1)
            end = date(year + (mon == 12), mon % 12 + 1, 1)
        except ValueError:
            raise HTTPException(422, "month must look like YYYY-MM")
        stmt = stmt.where(Transaction.date >= start, Transaction.date < end)
    return db.scalars(stmt).all()


def _summary(db: Session, statement_id: int | None) -> dict:
    rows = _filtered(db, statement_id, None, None)
    if not rows:
        raise HTTPException(404, "No transactions yet. Upload a statement first.")
    return analytics.summarise(analytics.transactions_frame(rows))


# ----------------------------------------------------------------- routes

@app.get("/api/health")
def health():
    return {"status": "ok", "llm_categorisation": categorizer.llm_enabled()}


@app.get("/api/categories")
def list_categories():
    return categorizer.CATEGORIES


@app.post("/api/statements", response_model=UploadResult, status_code=201)
async def upload_statement(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (5 MB max).")
    try:
        parsed = parse_statement(content, file.filename or "statement.csv")
    except StatementFormatError as exc:
        raise HTTPException(422, str(exc))

    learned = {m.merchant: m.category for m in db.scalars(select(MerchantCategory))}
    df = parsed.df
    categories, sources = [], []
    for row in df.itertuples():
        key = categorizer.normalise_merchant(row.merchant)
        if key in learned:
            categories.append(learned[key]); sources.append("learned")
        elif (cat := categorizer.rule_category(row.description, row.amount)) is not None:
            categories.append(cat); sources.append("rule")
        else:
            categories.append(None); sources.append(None)

    unknown = [m for m, c in zip(df["merchant"], categories) if c is None]
    llm_map = categorizer.llm_categorise(unknown)
    for i, merchant in enumerate(df["merchant"]):
        if categories[i] is None:
            if merchant in llm_map:
                categories[i], sources[i] = llm_map[merchant], "llm"
            else:
                categories[i], sources[i] = "Other", "default"
    for merchant, cat in llm_map.items():
        db.merge(MerchantCategory(merchant=categorizer.normalise_merchant(merchant), category=cat, source="llm"))

    statement = Statement(
        filename=file.filename or "statement",
        period_start=df["date"].min().date(),
        period_end=df["date"].max().date(),
        rows_read=parsed.rows_read,
        rows_kept=parsed.rows_kept,
        duplicates_removed=parsed.duplicates_removed,
        invalid_rows=parsed.invalid_rows,
    )
    statement.transactions = [
        Transaction(date=row.date.date(), description=row.description, merchant=row.merchant,
                    amount=round(float(row.amount), 2), category=cat, category_source=src)
        for row, cat, src in zip(df.itertuples(), categories, sources)
    ]
    db.add(statement)
    db.commit()
    db.refresh(statement)
    return UploadResult(statement=StatementOut.model_validate(statement), warnings=parsed.warnings,
                        categorised_by=dict(Counter(sources)))


@app.get("/api/statements", response_model=list[StatementOut])
def list_statements(db: Session = Depends(get_db)):
    return db.scalars(select(Statement).order_by(Statement.id.desc())).all()


@app.delete("/api/statements/{statement_id}", status_code=204)
def delete_statement(statement_id: int, db: Session = Depends(get_db)):
    statement = db.get(Statement, statement_id)
    if not statement:
        raise HTTPException(404, "Statement not found")
    db.delete(statement)
    db.commit()


@app.get("/api/transactions", response_model=list[TransactionOut])
def list_transactions(statement_id: int | None = None, month: str | None = None,
                      category: str | None = None, db: Session = Depends(get_db)):
    return _filtered(db, statement_id, month, category)


@app.patch("/api/transactions/{tx_id}", response_model=TransactionOut)
def update_category(tx_id: int, body: CategoryUpdate, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(404, "Transaction not found")
    tx.category, tx.category_source = body.category, "user"
    if body.apply_to_merchant:
        # Remember the correction and apply it to this merchant's other transactions.
        db.merge(MerchantCategory(merchant=categorizer.normalise_merchant(tx.merchant),
                                  category=body.category, source="user"))
        for other in db.scalars(select(Transaction).where(Transaction.merchant == tx.merchant,
                                                          Transaction.category_source != "user")):
            other.category, other.category_source = body.category, "learned"
    db.commit()
    db.refresh(tx)
    return tx


@app.get("/api/summary")
def get_summary(statement_id: int | None = None, db: Session = Depends(get_db)):
    return _summary(db, statement_id)


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@app.get("/api/reports/{fmt}")
def download_report(fmt: str, statement_id: int | None = Query(None), db: Session = Depends(get_db)):
    summary = _summary(db, statement_id)
    stamp = f"{summary['totals']['period_start']}_to_{summary['totals']['period_end']}"
    if fmt == "docx":
        data, media = reports.build_docx(summary), DOCX
    elif fmt == "pptx":
        data, media = reports.build_pptx(summary), PPTX
    else:
        raise HTTPException(404, "Report format must be docx or pptx")
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="spendsense_{stamp}.{fmt}"'})
