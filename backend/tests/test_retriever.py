"""Retrieval-augmented categorisation: vector store, prompt grounding, API flow.

A small deterministic character-trigram embedder stands in for the sentence-transformer so the
tests run offline and fast; ChromaDB itself is real.
"""
import hashlib
import json
import math

import pytest

chromadb = pytest.importorskip("chromadb")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import categorizer, retriever  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.retriever import MerchantRetriever, Neighbour, embedding_text  # noqa: E402

DIM = 256


class TrigramEmbedder:
    """Hashed character-trigram vectors, L2-normalised. Counts calls so tests can check caching."""

    def __init__(self):
        self.embedded = 0

    def __call__(self, texts):
        self.embedded += len(texts)
        out = []
        for t in texts:
            v = [0.0] * DIM
            s = f"  {t} "
            for i in range(len(s) - 2):
                v[int(hashlib.md5(s[i:i + 3].encode()).hexdigest(), 16) % DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


@pytest.fixture()
def store(tmp_path):
    embedder = TrigramEmbedder()
    r = MerchantRetriever(path=str(tmp_path / "vectors"), embedder=embedder)
    r.embedder = embedder
    retriever.set_retriever(r)
    return r


# ----------------------------------------------------------------- retrieval

def test_embedding_text_strips_statement_noise():
    assert embedding_text("SWIGGY*INSTAMART  blr-882301 swiggy@axb") == "swiggy instamart blr"
    assert embedding_text("1234") == "1234"     # never returns an empty string


def test_similar_returns_closest_labels_first(store):
    store.upsert([("Lazy Bear Coffee Co", "Food & Dining", "user"),
                  ("Sharma Hardware", "Shopping", "user"),
                  ("City Dental Care", "Health", "llm")])
    hits = store.similar(["LAZY BEAR COFFEE"])["LAZY BEAR COFFEE"]
    assert hits[0].merchant == "lazy bear coffee co"
    assert hits[0].category == "Food & Dining"
    assert hits[0].similarity > 0.8
    assert all(a.similarity >= b.similarity for a, b in zip(hits, hits[1:]))


def test_similar_skips_the_merchant_itself_and_weak_matches(store):
    store.upsert([("Lazy Bear Coffee Co", "Food & Dining", "user"),
                  ("Zebra Tyres", "Transport", "user")])
    hits = store.similar(["lazy bear coffee co"], min_similarity=0.35)["lazy bear coffee co"]
    assert [h.merchant for h in hits] == []      # itself excluded, Zebra Tyres too dissimilar


def test_empty_store_returns_no_neighbours(store):
    assert store.similar(["Anything"]) == {"Anything": []}


def test_sync_only_reembeds_new_or_changed_labels(store):
    labels = [("a mart", "Groceries", "user"), ("b cafe", "Food & Dining", "llm")]
    assert store.sync(labels) == 2
    before = store.embedder.embedded
    assert store.sync(labels) == 0                       # nothing changed
    assert store.embedder.embedded == before
    assert store.sync([("b cafe", "Food & Dining", "user")]) == 1   # user confirmed it
    assert store.count() == 2


# ----------------------------------------------------------------- augmentation

def test_nearest_user_label_trusts_only_close_user_corrections():
    close_user = Neighbour("lazy bear coffee co", "Food & Dining", "user", 0.91)
    close_llm = Neighbour("lazy bear bakery", "Groceries", "llm", 0.95)
    far_user = Neighbour("bear grylls store", "Shopping", "user", 0.5)
    assert categorizer.nearest_user_label([close_llm, close_user], threshold=0.8) == "Food & Dining"
    assert categorizer.nearest_user_label([close_llm, far_user], threshold=0.8) is None


def test_prompt_includes_retrieved_examples():
    ctx = {"LAZY BEAR COFFEE": [Neighbour("lazy bear coffee co", "Food & Dining", "user", 0.93)]}
    prompt = categorizer.build_prompt(["LAZY BEAR COFFEE", "Rahul Verma"], ctx)
    assert '"lazy bear coffee co" -> Food & Dining (user-confirmed, similarity 0.93)' in prompt
    assert "already categorised" in prompt
    assert "already categorised" not in categorizer.build_prompt(["Rahul Verma"], {})


def test_llm_call_is_grounded_in_retrieved_context(monkeypatch):
    sent = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text",
                                 "text": json.dumps({"LAZY BEAR COFFEE": "Food & Dining"})}]}

    def fake_post(url, headers, json, timeout):
        sent["prompt"] = json["messages"][0]["content"]
        return FakeResponse()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setattr(categorizer.httpx, "post", fake_post)
    ctx = {"LAZY BEAR COFFEE": [Neighbour("lazy bear coffee co", "Food & Dining", "user", 0.93)]}
    assert categorizer.llm_categorise(["LAZY BEAR COFFEE"], context=ctx) == {"LAZY BEAR COFFEE": "Food & Dining"}
    assert "lazy bear coffee co" in sent["prompt"]


# ----------------------------------------------------------------- end to end

def _csv(*rows):
    lines = ["Transaction Date,Description,Amount (INR),Type"]
    lines += [f"2026-10-0{i + 1},UPI-{m}-x{i}@ybl-90000{i}-Payment,{amt:.2f},DR"
              for i, (m, amt) in enumerate(rows)]
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture()
def client(monkeypatch, store):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_user_correction_is_indexed_and_reused_for_similar_merchant(client, store):
    r = client.post("/api/statements", files={"file": ("a.csv", _csv(("THIRDWAVE COFFEE", 240)), "text/csv")})
    assert r.status_code == 201
    tx = client.get("/api/transactions").json()[0]
    assert tx["category"] == "Other"

    client.patch(f"/api/transactions/{tx['id']}", json={"category": "Food & Dining"})
    assert store.count() == 1
    assert client.get("/api/health").json()["indexed_merchants"] == 1

    # A merchant never seen before, but close to one the user labelled.
    r = client.post("/api/statements",
                    files={"file": ("b.csv", _csv(("THIRDWAVE COFFEE GK", 180), ("ZEBRA TYRES", 900)), "text/csv")})
    assert r.json()["categorised_by"] == {"similar": 1, "default": 1}
    got = {t["merchant"]: (t["category"], t["category_source"])
           for t in client.get("/api/transactions", params={"statement_id": r.json()["statement"]["id"]}).json()}
    assert got["Thirdwave Coffee GK"] == ("Food & Dining", "similar")
    assert got["Zebra Tyres"] == ("Other", "default")
