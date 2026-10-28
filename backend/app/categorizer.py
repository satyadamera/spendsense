"""Transaction categorisation.

Order of precedence for each transaction:
1. a category the user (or the LLM) previously assigned to this merchant (learned),
2. keyword rules below,
3. for merchants nothing else recognised, retrieval-augmented categorisation: similar merchants
   the user already labelled are fetched from a vector store (``retriever.py``) and passed to
   an optional LLM call as examples; with no LLM, a very close user-labelled match is used,
4. "Other".

Only merchant names are ever sent to the LLM: no amounts, dates or raw narrations.
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

log = logging.getLogger(__name__)

CATEGORIES = [
    "Food & Dining", "Groceries", "Shopping", "Transport", "Travel", "Bills & Utilities",
    "Rent & Housing", "Subscriptions & Entertainment", "Education", "Health",
    "Investments & Savings", "Transfers", "Cash Withdrawal", "Income", "Refunds", "Other",
]

# (category, keywords) checked in order against the upper-cased narration.
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Refunds", ("REFUND", "REVERSAL", "CASHBACK", "REVERSED")),
    ("Cash Withdrawal", ("ATM", "CASH WDL", "NWD", "ATW", "CASH WITHDRAWAL")),
    ("Investments & Savings", ("ZERODHA", "GROWW", "UPSTOX", "MUTUAL FUND", "SIP", "KUVERA",
                               "COIN BY", "PPF", "RD INSTALLMENT", "FD BOOKING", "NPS")),
    ("Food & Dining", ("SWIGGY", "ZOMATO", "DOMINOS", "MCDONALD", "KFC", "STARBUCKS", "CAFE",
                       "RESTAURANT", "PIZZA", "BURGER", "CHAAYOS", "EATCLUB", "BIRYANI", "CANTEEN", "MESS")),
    ("Groceries", ("BLINKIT", "ZEPTO", "BIGBASKET", "INSTAMART", "DMART", "GROFERS", "JIOMART",
                   "MORE RETAIL", "RELIANCE FRESH", "SPENCERS", "KIRANA", "DUNZO")),
    ("Transport", ("UBER", "OLA", "RAPIDO", "METRO", "DMRC", "IRCTC", "FASTAG", "PETROL",
                   "FUEL", "HPCL", "BPCL", "INDIAN OIL", "PARKING", "BLUSMART", "NAMMA YATRI")),
    ("Travel", ("MAKEMYTRIP", "GOIBIBO", "INDIGO", "AIR INDIA", "VISTARA", "AKASA", "CLEARTRIP",
                "OYO", "AIRBNB", "BOOKING.COM", "REDBUS", "IXIGO", "HOTEL")),
    ("Subscriptions & Entertainment", ("NETFLIX", "SPOTIFY", "PRIME VIDEO", "HOTSTAR", "YOUTUBE",
                                       "BOOKMYSHOW", "PVR", "INOX", "STEAM", "PLAYSTATION",
                                       "APPLE.COM", "GOOGLE PLAY", "OPENAI", "CHATGPT", "ANTHROPIC")),
    ("Bills & Utilities", ("AIRTEL", "JIO", "VODAFONE", " VI ", "BSNL", "ELECTRICITY", "BESCOM",
                           "TATA POWER", "BSES", "ADANI ELEC", "WATER BILL", "GAS BILL", "BROADBAND",
                           "ACT FIBERNET", "RECHARGE", "INSURANCE", "LIC ", "CREDIT CARD", "CC PAYMENT")),
    ("Rent & Housing", ("RENT", "NOBROKER", "MAINTENANCE", "SOCIETY", "PG ", "HOSTEL")),
    ("Shopping", ("AMAZON", "FLIPKART", "MYNTRA", "AJIO", "NYKAA", "MEESHO", "DECATHLON",
                  "CROMA", "RELIANCE DIGITAL", "IKEA", "UNIQLO", "H&M", "ZARA", "TATA CLIQ")),
    ("Education", ("COURSERA", "UDEMY", "UNACADEMY", "BYJU", "COLLEGE", "UNIVERSITY", "SCHOOL",
                   "IIIT", "FEES", "LEETCODE", "BOOKS")),
    ("Health", ("PHARMACY", "APOLLO", "1MG", "PHARMEASY", "NETMEDS", "HOSPITAL", "CLINIC",
                "MEDPLUS", "PRACTO", "DIAGNOSTIC", "LAB ")),
    ("Income", ("SALARY", "SAL CREDIT", "STIPEND", "INTEREST CREDIT", "INT.PD", "DIVIDEND")),
    ("Transfers", ("NEFT", "IMPS", "RTGS", "SELF TRANSFER", "OWN ACCOUNT")),
]


def _keyword_pattern(keyword: str) -> str:
    # Short keywords ("OLA", "JIO", "SIP") must be whole words so "COLA" or "GOSSIP" don't match;
    # longer ones only need a word start so "MCDONALD" also matches "MCDONALDS".
    k = re.escape(keyword.strip())
    return rf"(?<![A-Z0-9]){k}(?![A-Z0-9])" if len(keyword.strip()) <= 4 else rf"(?<![A-Z0-9]){k}"


_COMPILED_RULES = [
    (category, re.compile("|".join(_keyword_pattern(k) for k in keywords)))
    for category, keywords in RULES
]


def rule_category(description: str, amount: float) -> str | None:
    """Keyword-rule category, or None if no rule matched a money-out transaction."""
    text = str(description).upper()
    for category, pattern in _COMPILED_RULES:
        if pattern.search(text):
            # A rule like "Transfers" shouldn't turn an incoming salary into a transfer.
            if amount > 0 and category not in {"Refunds", "Income", "Transfers", "Investments & Savings"}:
                return "Refunds"
            return category
    if amount > 0:
        return "Income"
    return None


def normalise_merchant(merchant: str) -> str:
    return re.sub(r"\s+", " ", str(merchant)).strip().lower()


def llm_enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def nearest_user_label(neighbours: list, threshold: float | None = None) -> str | None:
    """Category of the closest *user-confirmed* neighbour, if it is similar enough to trust.

    Used when no LLM is configured: a k-NN classifier over the user's own corrections.
    """
    if threshold is None:
        threshold = float(os.getenv("SPENDSENSE_KNN_THRESHOLD", "0.8"))
    for n in neighbours:
        if n.source == "user" and n.similarity >= threshold:
            return n.category
    return None


def build_prompt(merchants: list[str], context: dict[str, list] | None = None) -> str:
    """LLM prompt; retrieved neighbours are added as few-shot examples per merchant."""
    context = context or {}
    lines = []
    for m in merchants:
        lines.append(f"- {m}")
        for n in context.get(m, []):
            tag = "user-confirmed" if n.source == "user" else "earlier guess"
            lines.append(f"    similar: \"{n.merchant}\" -> {n.category} "
                         f"({tag}, similarity {n.similarity:.2f})")
    grounding = ""
    if any(context.get(m) for m in merchants):
        grounding = (
            "Some merchants list similar merchants this user has already categorised. Use them as "
            "evidence of how this user labels things, and prefer user-confirmed examples, but only "
            "follow an example if it really is the same kind of business.\n"
        )
    return (
        "Categorise each merchant name from an Indian bank/UPI statement into exactly one of "
        f"these categories: {', '.join(CATEGORIES)}.\n"
        "If a name looks like a private person (a UPI transfer to an individual), use \"Transfers\". "
        "If unsure, use \"Other\".\n"
        + grounding
        + "Reply with only a JSON object mapping each merchant name exactly as given to its category.\n\n"
        "Merchants:\n" + "\n".join(lines)
    )


def llm_categorise(merchants: list[str], context: dict[str, list] | None = None,
                   timeout: float = 30.0) -> dict[str, str]:
    """Ask Claude to categorise merchant names, grounded in retrieved examples when given.

    Returns {} if disabled or on any failure.
    """
    merchants = sorted({m for m in merchants if m})
    if not merchants or not llm_enabled():
        return {}
    prompt = build_prompt(merchants, context)
    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": os.getenv("SPENDSENSE_LLM_MODEL", "claude-haiku-5-5"),
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        text = "".join(b.get("text", "") for b in resp.json().get("content", []))
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0)) if match else {}
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        log.warning("LLM categorisation skipped: %s", exc)
        return {}
    return {m: c for m, c in data.items() if m in merchants and c in CATEGORIES}
