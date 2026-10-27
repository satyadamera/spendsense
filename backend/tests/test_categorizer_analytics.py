import pytest

from app import analytics
from app.categorizer import llm_categorise, rule_category


@pytest.mark.parametrize("narration, amount, category", [
    ("UPI-SWIGGY-swiggy@axb-1-Payment", -300, "Food & Dining"),
    ("UPI-BLINKIT-blinkit@ybl-1-Payment", -500, "Groceries"),
    ("UPI-UBER INDIA-uber@axis-1-Payment", -200, "Transport"),
    ("UPI-NETFLIX-netflix@icici-1-Payment", -199, "Subscriptions & Entertainment"),
    ("ACH D-ZERODHA BROKING-SIP-1", -3000, "Investments & Savings"),
    ("ATW-5123XXXX6789-NEW DELHI", -2000, "Cash Withdrawal"),
    ("NEFT CR-ACME LABS-STIPEND", 35000, "Income"),
    ("UPI-AMAZON REFUND-amazon@apl-1-REFUND", 899, "Refunds"),
    ("UPI-COCA COLA STORE-x@ybl-1", -60, None),      # "OLA" must not match inside "COLA"
    ("UPI-RAHUL VERMA-rahul@okicici-1-Sent", -400, None),
])
def test_rule_category(narration, amount, category):
    assert rule_category(narration, amount) == category


def test_llm_disabled_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm_categorise(["Rahul Verma"]) == {}


def _rows():
    tx = [
        ("2026-07-01", "Acme", 35000, "Income"),
        ("2026-07-02", "Netflix", -199, "Subscriptions & Entertainment"),
        ("2026-07-05", "Swiggy", -400, "Food & Dining"),
        ("2026-07-06", "Zerodha", -3000, "Investments & Savings"),
        ("2026-08-01", "Acme", 35000, "Income"),
        ("2026-08-02", "Netflix", -199, "Subscriptions & Entertainment"),
        ("2026-08-05", "Swiggy", -800, "Food & Dining"),
        ("2026-08-09", "Rahul Verma", -500, "Transfers"),
    ]
    return [{"id": i, "date": d, "description": m, "merchant": m, "amount": a, "category": c}
            for i, (d, m, a, c) in enumerate(tx)]


def test_summary_excludes_transfers_and_investments_from_spend():
    s = analytics.summarise(analytics.transactions_frame(_rows()))
    t = s["totals"]
    assert t["income"] == 70000
    assert t["spend"] == 199 * 2 + 400 + 800
    assert t["invested"] == 3000
    assert {c["category"] for c in s["by_category"]} == {"Food & Dining", "Subscriptions & Entertainment"}
    assert [m["month"] for m in s["monthly"]] == ["2026-07", "2026-08"]


def test_recurring_detection_and_insights():
    s = analytics.summarise(analytics.transactions_frame(_rows()))
    assert [r["merchant"] for r in s["recurring"]] == ["Netflix"]   # Swiggy amount varies too much
    assert any("up" in line and "Aug 2026" in line for line in s["insights"])


def test_empty_summary():
    s = analytics.summarise(analytics.transactions_frame([]))
    assert s["totals"] is None


def test_llm_response_is_validated(monkeypatch):
    """Mocked API: only known merchants and known categories are accepted."""
    import httpx
    from app import categorizer

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["prompt"] = json["messages"][0]["content"]
        body = {"content": [{"type": "text", "text":
            '{"Rahul Verma": "Transfers", "Chai Point": "Snacks", "Invented Co": "Shopping"}'}]}
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(categorizer.httpx, "post", fake_post)
    result = categorizer.llm_categorise(["Rahul Verma", "Chai Point"])
    assert result == {"Rahul Verma": "Transfers"}      # "Snacks" isn't a category; "Invented Co" wasn't asked
    assert "Rahul Verma" in captured["prompt"] and "₹" not in captured["prompt"]   # names only, no amounts
