"""Load bank / UPI statement exports (CSV or Excel) into one clean, validated DataFrame.

Bank exports differ a lot: junk rows above the header, different column names,
separate debit/credit columns vs. one signed amount column, Indian number
formatting ("1,23,456.00"), "Dr"/"Cr" suffixes and footer rows. This module
normalises all of that into:

    date (datetime64) | description (str) | merchant (str) | amount (float, -ve = out)
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

import pandas as pd

COLUMN_ALIASES: dict[str, list[str]] = {
    "date": ["date", "txn date", "transaction date", "value date", "value dt", "tran date", "posting date"],
    "description": ["narration", "description", "particulars", "remarks", "details",
                    "transaction details", "transaction remarks"],
    "debit": ["withdrawal amt.", "withdrawal amt", "withdrawal", "withdrawals", "debit",
              "debit amount", "dr", "withdrawal amount", "debit amt"],
    "credit": ["deposit amt.", "deposit amt", "deposit", "deposits", "credit",
               "credit amount", "cr", "deposit amount", "credit amt"],
    "amount": ["amount", "amount (inr)", "transaction amount", "amt", "amount(inr)"],
    "type": ["type", "dr/cr", "cr/dr", "debit/credit", "transaction type", "txn type"],
    "balance": ["balance", "closing balance", "balance (inr)", "available balance"],
}

# Tokens that are payment-rail noise rather than the merchant's name.
NOISE_TOKENS = {
    "UPI", "POS", "NEFT", "IMPS", "RTGS", "ACH", "NACH", "ECS", "DR", "CR", "P2A", "P2M",
    "PAYMENT", "PAYMENTS", "TXN", "TRANSFER", "REF", "INB", "MB", "IB", "ATW", "NWD",
    "BIL", "BILLPAY", "ONL", "VPS", "VIN", "PCD", "TO", "FROM", "BY", "PAY", "PAID",
    "SENT", "RECEIVED", "COLLECT", "REQUEST", "DEBIT", "CREDIT", "CARD", "PURCHASE",
}


@dataclass
class ParseResult:
    df: pd.DataFrame
    rows_read: int = 0
    rows_kept: int = 0
    duplicates_removed: int = 0
    invalid_rows: int = 0
    warnings: list[str] = field(default_factory=list)


class StatementFormatError(ValueError):
    """Raised when a file does not look like a statement we can read."""


def _norm(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _read_raw_rows(content: bytes, filename: str) -> list[list[str]]:
    """Read every row as strings, tolerating ragged rows above the real header."""
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        raw = pd.read_excel(io.BytesIO(content), header=None, dtype=str)
        return raw.fillna("").astype(str).values.tolist()
    if name.endswith(".csv") or name.endswith(".txt"):
        text = content.decode("utf-8-sig", errors="replace")
        return [row for row in csv.reader(io.StringIO(text))]
    raise StatementFormatError("Unsupported file type. Upload a .csv or .xlsx statement.")


def _find_header(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    """Return the index of the header row and a mapping canonical_name -> column index."""
    for i, row in enumerate(rows[:40]):
        cells = [_norm(c) for c in row]
        mapping: dict[str, int] = {}
        for canonical, aliases in COLUMN_ALIASES.items():
            for j, cell in enumerate(cells):
                if cell in aliases and j not in mapping.values():
                    mapping[canonical] = j
                    break
        has_amount = "amount" in mapping or "debit" in mapping or "credit" in mapping
        if "date" in mapping and "description" in mapping and has_amount:
            return i, mapping
    raise StatementFormatError(
        "Couldn't find a header row with date, description and amount columns."
    )


def clean_amount(value: object) -> float | None:
    """Parse '1,23,456.50', '₹ 500', '(250.00)', '300 Dr', '' -> float (sign only from brackets/Dr)."""
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "-", "--"}:
        return None
    sign = 1.0
    if text.startswith("(") and text.endswith(")"):
        sign, text = -1.0, text[1:-1]
    upper = text.upper()
    if upper.endswith("DR"):
        sign, text = -1.0, text[:-2]
    elif upper.endswith("CR"):
        text = text[:-2]
    text = re.sub(r"(?i)inr|rs\.?|₹|,|\s", "", text)
    if text.startswith("-"):
        sign, text = -sign, text[1:]
    try:
        return sign * float(text)
    except ValueError:
        return None


def parse_dates(raw: pd.Series) -> pd.Series:
    """ISO dates (2026-10-01) are year-first; everything else (01/10/26, 01-Oct-2026) is day-first,
    as in Indian bank exports. Parsing both with dayfirst=True would turn 2026-10-01 into 10 Jan."""
    raw = raw.astype(str).str.strip()
    iso = raw.str.match(r"^\d{4}-\d{1,2}-\d{1,2}")
    out = pd.Series(pd.NaT, index=raw.index, dtype="datetime64[ns]")
    if iso.any():
        out[iso] = pd.to_datetime(raw[iso].str[:10], format="%Y-%m-%d", errors="coerce")
    if (~iso).any():
        out[~iso] = pd.to_datetime(raw[~iso], format="mixed", dayfirst=True, errors="coerce")
    return out


def _title(words: list[str]) -> str:
    # Keep vowel-less acronyms (DMRC, PG, HDFC) upper-case; title-case the rest.
    return " ".join(w if not re.search(r"[AEIOU]", w) and len(w) <= 5 else w.title() for w in words)


def extract_merchant(description: str) -> str:
    """Best-effort merchant name from a raw narration, e.g.
    'UPI-SWIGGY-swiggy.stores@axb-AXIS0000-412345678901-Payment' -> 'Swiggy'.
    """
    text = str(description or "").upper()
    if re.match(r"\s*(ATW|ATM|NWD|CASH WDL)\b", text):
        return "ATM Withdrawal"
    tokens = re.split(r"[/\-*|:]+", text)
    for tok in tokens:
        tok = re.sub(r"\s+", " ", tok).strip(" .")
        if not tok or "@" in tok:
            continue
        # Keep words that are mostly letters: drops card numbers, IFSC codes, reference numbers.
        words = [w for w in tok.split()
                 if w not in NOISE_TOKENS and sum(ch.isalpha() for ch in w) >= 0.6 * len(w)]
        if sum(len(w) for w in words) < 3:
            continue
        return _title(words[:3])
    return re.sub(r"\s+", " ", str(description)).strip()[:30].title() or "Unknown"


def parse_statement(content: bytes, filename: str) -> ParseResult:
    rows = _read_raw_rows(content, filename)
    header_idx, cols = _find_header(rows)
    body = [r for r in rows[header_idx + 1:] if any(str(c).strip() for c in r)]

    def col(row: list[str], key: str) -> str:
        j = cols.get(key)
        return row[j] if j is not None and j < len(row) else ""

    records = []
    for r in body:
        records.append({
            "date_raw": col(r, "date"),
            "description": re.sub(r"\s+", " ", col(r, "description")).strip(),
            "debit": clean_amount(col(r, "debit")) if "debit" in cols else None,
            "credit": clean_amount(col(r, "credit")) if "credit" in cols else None,
            "amount_raw": clean_amount(col(r, "amount")) if "amount" in cols else None,
            "type": _norm(col(r, "type")) if "type" in cols else "",
            "balance": clean_amount(col(r, "balance")) if "balance" in cols else None,
        })
    df = pd.DataFrame.from_records(records)
    result = ParseResult(df=df, rows_read=len(df))
    if df.empty:
        raise StatementFormatError("The statement has a header but no transaction rows.")

    # --- signed amount -----------------------------------------------------
    if "debit" in cols or "credit" in cols:
        debit = df["debit"].fillna(0.0).abs()
        credit = df["credit"].fillna(0.0).abs()
        df["amount"] = credit - debit
        df.loc[df["debit"].isna() & df["credit"].isna(), "amount"] = float("nan")
    else:
        amount = df["amount_raw"]
        if "type" in cols:
            # Only rows that actually say Dr/Cr get their sign from the type column.
            has_type = ~df["type"].isin(["", "nan"])
            is_debit = has_type & df["type"].str.startswith(("d", "w"))
            is_credit = has_type & ~is_debit
            amount = amount.mask(is_debit, -amount.abs()).mask(is_credit, amount.abs())
        df["amount"] = amount

    # --- dates -------------------------------------------------------------
    df["date"] = parse_dates(df["date_raw"])

    # --- validation --------------------------------------------------------
    valid = df["date"].notna() & df["amount"].notna() & (df["amount"] != 0) & (df["description"] != "")
    result.invalid_rows = int((~valid).sum())
    df = df[valid].copy()

    dedupe_keys = ["date", "description", "amount"] + (["balance"] if "balance" in cols else [])
    before = len(df)
    df = df.drop_duplicates(subset=dedupe_keys)
    result.duplicates_removed = before - len(df)

    if df.empty:
        raise StatementFormatError("No valid transactions found after cleaning.")

    df["merchant"] = df["description"].map(extract_merchant)
    df = df.sort_values("date").reset_index(drop=True)
    result.df = df[["date", "description", "merchant", "amount"]]
    result.rows_kept = len(result.df)

    if result.invalid_rows:
        result.warnings.append(
            f"Skipped {result.invalid_rows} row(s) with a missing date, amount or description "
            "(often opening/closing balance or footer lines)."
        )
    if result.duplicates_removed:
        result.warnings.append(f"Removed {result.duplicates_removed} duplicate row(s).")
    return result
