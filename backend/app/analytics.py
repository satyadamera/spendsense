"""Summary statistics and plain-language insights computed with Pandas."""
from __future__ import annotations

import pandas as pd

EXCLUDED_FROM_SPEND = {"Transfers", "Investments & Savings"}


def format_inr(x: float | None, decimals: int = 0) -> str:
    """Indian digit grouping: 1234567 -> '₹12,34,567'."""
    if x is None:
        return "–"
    sign = "-" if x < 0 else ""
    whole, _, frac = f"{abs(x):.{decimals}f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + groups + [tail])
    return f"{sign}₹{whole}" + (f".{frac}" if frac else "")


def transactions_frame(rows) -> pd.DataFrame:
    """Build a DataFrame from ORM Transaction objects (or dicts)."""
    records = [
        r if isinstance(r, dict) else {
            "id": r.id, "date": r.date, "description": r.description,
            "merchant": r.merchant, "amount": r.amount, "category": r.category,
        }
        for r in rows
    ]
    df = pd.DataFrame.from_records(
        records, columns=["id", "date", "description", "merchant", "amount", "category"]
    )
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    return df


def _spend(df: pd.DataFrame) -> pd.DataFrame:
    """Money out that counts as spending (not transfers to yourself or investments)."""
    out = df[(df["amount"] < 0) & ~df["category"].isin(EXCLUDED_FROM_SPEND)].copy()
    out["spend"] = -out["amount"]
    return out


def summarise(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"totals": None, "by_category": [], "monthly": [], "top_merchants": [],
                "largest_expenses": [], "recurring": [], "insights": []}

    spend = _spend(df)
    income = df.loc[df["category"].isin(["Income", "Refunds"]), "amount"].clip(lower=0).sum()
    invested = -df.loc[(df["category"] == "Investments & Savings") & (df["amount"] < 0), "amount"].sum()
    total_spend = spend["spend"].sum()

    totals = {
        "period_start": df["date"].min().date().isoformat(),
        "period_end": df["date"].max().date().isoformat(),
        "transactions": int(len(df)),
        "income": round(float(income), 2),
        "spend": round(float(total_spend), 2),
        "invested": round(float(invested), 2),
        "net": round(float(income - total_spend - invested), 2),
        "savings_rate": round(float((income - total_spend) / income * 100), 1) if income else None,
    }

    by_cat = (spend.groupby("category")["spend"].agg(total="sum", n="count")
              .sort_values("total", ascending=False).reset_index())
    by_category = [
        {"category": r.category, "amount": round(float(r.total), 2), "count": int(r.n),
         "share": round(float(r.total / total_spend * 100), 1) if total_spend else 0.0}
        for r in by_cat.itertuples()
    ]

    df_m = df.assign(month=df["date"].dt.to_period("M"))
    spend_m = spend.assign(month=spend["date"].dt.to_period("M"))
    months = sorted(df_m["month"].unique())
    monthly = []
    for m in months:
        inc = df_m.loc[(df_m["month"] == m) & df_m["category"].isin(["Income", "Refunds"]), "amount"].clip(lower=0).sum()
        sp = spend_m.loc[spend_m["month"] == m, "spend"].sum()
        monthly.append({"month": str(m), "label": m.strftime("%b %Y"), "income": round(float(inc), 2),
                        "spend": round(float(sp), 2), "net": round(float(inc - sp), 2)})

    top = (spend.groupby("merchant")["spend"].agg(total="sum", n="count")
           .sort_values("total", ascending=False).head(8).reset_index())
    top_merchants = [{"merchant": r.merchant, "amount": round(float(r.total), 2), "count": int(r.n)}
                     for r in top.itertuples()]

    largest = spend.sort_values("spend", ascending=False).head(5)
    largest_expenses = [
        {"date": r.date.date().isoformat(), "merchant": r.merchant, "category": r.category,
         "amount": round(float(r.spend), 2)}
        for r in largest.itertuples()
    ]

    recurring = find_recurring(spend_m)
    return {
        "totals": totals,
        "by_category": by_category,
        "monthly": monthly,
        "top_merchants": top_merchants,
        "largest_expenses": largest_expenses,
        "recurring": recurring,
        "insights": build_insights(totals, by_category, monthly, recurring),
    }


def find_recurring(spend_m: pd.DataFrame) -> list[dict]:
    """Merchants charged in 2+ different months with a near-constant amount (likely subscriptions/EMIs)."""
    out = []
    for merchant, g in spend_m.groupby("merchant"):
        if g["month"].nunique() < 2 or (g["category"] == "Cash Withdrawal").all():
            continue
        median = g["spend"].median()
        if median and (g["spend"].sub(median).abs() <= 0.1 * median).mean() >= 0.8:
            out.append({"merchant": merchant, "category": g["category"].mode().iat[0],
                        "typical_amount": round(float(median), 2), "months": int(g["month"].nunique())})
    return sorted(out, key=lambda r: -r["typical_amount"])


def _inr(x: float) -> str:
    return format_inr(x)


def build_insights(totals: dict, by_category: list[dict], monthly: list[dict], recurring: list[dict]) -> list[str]:
    insights = []
    if by_category:
        top = by_category[0]
        insights.append(f"{top['category']} is your largest spending category at {_inr(top['amount'])} "
                        f"({top['share']}% of spending).")
    if len(monthly) >= 2:
        prev, last = monthly[-2], monthly[-1]
        if prev["spend"]:
            change = (last["spend"] - prev["spend"]) / prev["spend"] * 100
            amounts = f"({_inr(prev['spend'])} → {_inr(last['spend'])})"
            if abs(change) < 3:
                insights.append(f"Spending in {last['label']} was about the same as {prev['label']} {amounts}.")
            else:
                direction = "up" if change > 0 else "down"
                insights.append(f"Spending in {last['label']} was {direction} {abs(change):.0f}% "
                                f"from {prev['label']} {amounts}.")
    if recurring:
        monthly_total = sum(r["typical_amount"] for r in recurring)
        names = ", ".join(r["merchant"] for r in recurring[:4])
        insights.append(f"{len(recurring)} recurring payment(s) detected ({names}), "
                        f"about {_inr(monthly_total)} a month.")
    if totals.get("savings_rate") is not None:
        insights.append(f"Savings rate for the period: {totals['savings_rate']}% of income.")
    return insights
