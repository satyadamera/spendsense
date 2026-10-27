import pandas as pd
import pytest

from app.parser import StatementFormatError, clean_amount, extract_merchant, parse_statement


@pytest.mark.parametrize("raw, expected", [
    ("1,23,456.50", 123456.5),
    ("₹ 500", 500.0),
    ("(250.00)", -250.0),
    ("300.00 Dr", -300.0),
    ("300.00 Cr", 300.0),
    ("-4,191.61", -4191.61),
    ("", None),
    ("abc", None),
])
def test_clean_amount(raw, expected):
    assert clean_amount(raw) == expected


@pytest.mark.parametrize("narration, merchant", [
    ("UPI-SWIGGY-swiggy.stores@axb-AXIS0000-412345678901-Payment", "Swiggy"),
    ("POS 4123XXXXXXXX9876 AMAZON PAY INDIA", "Amazon India"),
    ("ACH D-ZERODHA BROKING-SIP-123456789012", "Zerodha Broking"),
    ("ATW-512345XXXXXX6789-S1ANDL04-NEW DELHI", "ATM Withdrawal"),
    ("NEFT CR-HDFC0001234-ACME LABS PVT LTD-STIPEND", "Acme Labs PVT"),
    ("UPI-DMRC METRO-dmrc@sbi-1-Payment", "DMRC Metro"),
])
def test_extract_merchant(narration, merchant):
    assert extract_merchant(narration) == merchant


BANK_CSV = b"""XYZ BANK LTD
Account No :,XXXX4321

Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance
,OPENING BALANCE,,,,,"10,000.00"
01/07/26,UPI-ZOMATO-zomato@hdfcbank-41839-Payment,1,01/07/26,350.00,,"9,650.00"
01/07/26,UPI-ZOMATO-zomato@hdfcbank-41839-Payment,1,01/07/26,350.00,,"9,650.00"
02/07/26,NEFT CR-ACME LABS-STIPEND,2,02/07/26,,"35,000.00","44,650.00"
15/07/26,UPI-ZOMATO-zomato@hdfcbank-41840-Payment,3,15/07/26,350.00,,"44,300.00"
,*** End of statement ***
"""


def test_bank_csv_cleaning_and_validation():
    result = parse_statement(BANK_CSV, "statement.csv")
    df = result.df
    assert list(df.columns) == ["date", "description", "merchant", "amount"]
    assert result.rows_kept == 3
    assert result.duplicates_removed == 1          # exact repeat incl. balance
    assert result.invalid_rows == 2                # opening balance + footer
    assert df["amount"].tolist() == [-350.0, 35000.0, -350.0]
    assert df["date"].iloc[0] == pd.Timestamp("2026-07-01")   # dd/mm/yy read day-first
    assert df["date"].iloc[2] == pd.Timestamp("2026-07-15")


def test_same_amount_different_balance_is_not_a_duplicate():
    # Two identical coffees on the same day are real: the running balance differs.
    csv_bytes = b"""Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance
01/07/26,UPI-CHAAYOS-x@icici-1-Payment,120.00,,"880.00"
01/07/26,UPI-CHAAYOS-x@icici-1-Payment,120.00,,"760.00"
"""
    assert parse_statement(csv_bytes, "s.csv").rows_kept == 2


def test_single_amount_column_with_type():
    csv_bytes = b"""Transaction Date,Description,Amount (INR),Type
2026-10-01,UPI-DOMINOS PIZZA-dominos@ybl-1-Payment,319.14,DR
2026-10-02,NEFT CR-ACME LABS-STIPEND,35000.00,CR
"""
    df = parse_statement(csv_bytes, "upi.csv").df
    assert df["amount"].tolist() == [-319.14, 35000.0]
    # Regression: ISO dates must not be read day-first (2026-10-01 is 1 Oct, not 10 Jan).
    assert df["date"].tolist() == [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-02")]


def test_rejects_files_without_a_header():
    with pytest.raises(StatementFormatError):
        parse_statement(b"foo,bar\n1,2\n", "x.csv")


def test_rejects_unsupported_type():
    with pytest.raises(StatementFormatError):
        parse_statement(b"%PDF-1.4", "statement.pdf")
