"""Generate realistic *fake* statements for demos and tests (no real account data).

Creates two files in this folder, deliberately in different formats:
  bank_statement_sample.csv  - bank-style: junk header rows, Withdrawal/Deposit columns,
                               Indian number formatting, a duplicate row, footer lines
  upi_export_sample.csv      - app-style: one Amount column with a DR/CR type column
                               (covers the following month, so both files can be uploaded together)
Run:  python generate_samples.py
"""
import csv
import random
from datetime import date
from pathlib import Path

random.seed(7)
OUT = Path(__file__).parent
START, MONTHS = date(2026, 7, 1), 3


def inr(x: float) -> str:
    """Indian digit grouping: 123456.5 -> '1,23,456.50'."""
    whole, frac = f"{x:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join([head] + groups + [tail]) if head else ",".join(groups + [tail])
    return f"{whole}.{frac}"


def ref() -> str:
    return str(random.randint(10**11, 10**12 - 1))


def month_txns(month_start: date) -> list[tuple[date, str, float]]:
    """(date, narration, signed amount) for one month."""
    d = lambda day: month_start.replace(day=min(day, 28))  # noqa: E731
    tx = [
        (d(1), f"NEFT CR-HDFC0001234-ACME LABS PVT LTD-STIPEND-{ref()}", 35000.0),
        (d(2), f"UPI-SHARMA PG RENT-sharmapg@okaxis-UTIB0000123-{ref()}-RENT", -9000.0),
        (d(5), f"ACH D-ZERODHA BROKING-SIP-{ref()}", -3000.0),
        (d(7), f"UPI-NETFLIX-netflix@icici-ICIC0000001-{ref()}-Payment", -199.0),
        (d(9), f"UPI-SPOTIFY INDIA-spotify@hdfcbank-HDFC0000001-{ref()}-Payment", -119.0),
        (d(12), f"UPI-AIRTEL PREPAID-airtel@ybl-YESB0000001-{ref()}-Recharge", -349.0),
        (d(20), f"ATW-512345XXXXXX6789-S1ANDL04-NEW DELHI", -2000.0),
    ]
    for _ in range(random.randint(9, 14)):
        merchant, handle = random.choice([("SWIGGY", "swiggy.stores@axb"), ("ZOMATO", "zomato@hdfcbank"),
                                          ("DOMINOS PIZZA", "dominos@ybl"), ("CHAAYOS", "chaayos@icici")])
        tx.append((d(random.randint(1, 28)), f"UPI-{merchant}-{handle}-{ref()}-Payment",
                   -round(random.uniform(150, 650), 2)))
    for _ in range(random.randint(4, 7)):
        merchant, handle = random.choice([("BLINKIT", "blinkit@ybl"), ("ZEPTO", "zepto@axl")])
        tx.append((d(random.randint(1, 28)), f"UPI-{merchant}-{handle}-{ref()}-Payment",
                   -round(random.uniform(200, 900), 2)))
    for _ in range(random.randint(5, 9)):
        merchant, handle, lo, hi = random.choice([("UBER INDIA", "uber@axisbank", 120, 420),
                                                  ("DMRC METRO", "dmrc@sbi", 50, 300),
                                                  ("RAPIDO", "rapido@ybl", 40, 160)])
        tx.append((d(random.randint(1, 28)), f"UPI-{merchant}-{handle}-{ref()}-Payment",
                   -round(random.uniform(lo, hi), 2)))
    for _ in range(random.randint(1, 3)):
        merchant = random.choice(["AMAZON PAY INDIA", "FLIPKART INTERNET", "MYNTRA DESIGNS"])
        tx.append((d(random.randint(1, 28)), f"POS 4123XXXXXXXX9876 {merchant}", -round(random.uniform(400, 3500), 2)))
    # Friends splitting bills: unknown to the rules (LLM or "Other").
    for name in random.sample(["RAHUL VERMA", "ANANYA GUPTA", "KARTIK SINGH"], 2):
        tx.append((d(random.randint(1, 28)), f"UPI-{name}-{name.split()[0].lower()}@okicici-{ref()}-Sent",
                   -float(random.choice([250, 400, 600, 1200]))))
    tx.append((d(random.randint(10, 25)), f"UPI-BOOKMYSHOW-bms@icici-{ref()}-Payment", -round(random.uniform(300, 700), 2)))
    if month_start.month == 8:
        tx.append((d(14), f"UPI-MAKEMYTRIP-mmt@icici-{ref()}-Payment", -4820.0))
        tx.append((d(18), f"UPI-AMAZON REFUND-amazon@apl-{ref()}-REFUND", 899.0))
    if month_start.month == 9:
        tx.append((d(3), f"UPI-COURSERA-coursera@hdfc-{ref()}-Payment", -2499.0))
    return sorted(tx, key=lambda t: t[0])


def all_txns():
    out = []
    for i in range(MONTHS):
        m = START.month + i
        out += month_txns(date(START.year + (m - 1) // 12, (m - 1) % 12 + 1, 1))
    return out


def write_bank_csv(txns):
    balance = 42500.0
    rows = [["XYZ BANK LTD"], ["Statement of account"], ["Account No :", "XXXXXXXX4321"],
            ["Statement From :", "01/07/2026", "To :", "30/09/2026"], [],
            ["Date", "Narration", "Chq./Ref.No.", "Value Dt", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
            ["", "OPENING BALANCE", "", "", "", "", inr(balance)]]
    for i, (day, text, amt) in enumerate(txns):
        balance += amt
        row = [day.strftime("%d/%m/%y"), text, f"{ref()[:10]}", day.strftime("%d/%m/%y"),
               inr(-amt) if amt < 0 else "", inr(amt) if amt > 0 else "", inr(balance)]
        rows.append(row)
        if i == 15:
            rows.append(list(row))  # exported twice: the parser should drop it
    rows += [[], ["", "*** End of statement ***"], ["", "This is a computer generated statement."]]
    with open(OUT / "bank_statement_sample.csv", "w", newline="") as f:
        csv.writer(f).writerows(rows)


def write_upi_csv(txns):
    with open(OUT / "upi_export_sample.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Transaction Date", "Description", "Amount (INR)", "Type"])
        for day, text, amt in txns:
            w.writerow([day.isoformat(), text, f"{abs(amt):.2f}", "DR" if amt < 0 else "CR"])


if __name__ == "__main__":
    bank = all_txns()  # Jul-Sep
    write_bank_csv(bank)
    upi = [t for t in month_txns(date(2026, 10, 1)) if t[0] <= date(2026, 10, 25)]  # Oct, no overlap
    write_upi_csv(upi)
    print(f"Wrote {len(bank)} bank rows and {len(upi)} UPI rows")
