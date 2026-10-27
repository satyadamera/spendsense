import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

SAMPLES = Path(__file__).resolve().parents[2] / "sample_data"


@pytest.fixture()
def client(monkeypatch):
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


def upload(client, name):
    with open(SAMPLES / name, "rb") as f:
        return client.post("/api/statements", files={"file": (name, f, "text/csv")})


def test_upload_and_summary(client):
    r = upload(client, "bank_statement_sample.csv")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["statement"]["duplicates_removed"] == 1
    assert body["statement"]["rows_kept"] > 100
    assert "Other" not in body["categorised_by"] or body["categorised_by"].get("default", 0) < 10

    s = client.get("/api/summary").json()
    assert s["totals"]["income"] > 0
    assert s["by_category"][0]["category"] in {"Rent & Housing", "Food & Dining"}
    assert any(r["merchant"] == "Netflix" for r in s["recurring"])


def test_bad_file_is_rejected(client):
    r = client.post("/api/statements", files={"file": ("notes.csv", b"hello,world\n", "text/csv")})
    assert r.status_code == 422


def test_user_correction_is_learned(client):
    upload(client, "bank_statement_sample.csv")
    tx = client.get("/api/transactions", params={"category": "Other"}).json()
    assert tx, "sample data should contain uncategorised UPI transfers to friends"
    merchant = tx[0]["merchant"]
    r = client.patch(f"/api/transactions/{tx[0]['id']}", json={"category": "Transfers"})
    assert r.status_code == 200 and r.json()["category"] == "Transfers"

    # Other transactions from the same merchant follow, and the next upload remembers it.
    same = [t for t in client.get("/api/transactions").json() if t["merchant"] == merchant]
    assert all(t["category"] == "Transfers" for t in same)
    upload(client, "upi_export_sample.csv")
    oct_same = [t for t in client.get("/api/transactions", params={"month": "2026-10"}).json()
                if t["merchant"] == merchant]
    assert all(t["category"] == "Transfers" and t["category_source"] == "learned" for t in oct_same)


def test_invalid_category_rejected(client):
    upload(client, "bank_statement_sample.csv")
    tx_id = client.get("/api/transactions").json()[0]["id"]
    assert client.patch(f"/api/transactions/{tx_id}", json={"category": "Snacks"}).status_code == 422


@pytest.mark.parametrize("fmt", ["docx", "pptx"])
def test_reports_are_valid_office_files(client, fmt):
    upload(client, "bank_statement_sample.csv")
    r = client.get(f"/api/reports/{fmt}")
    assert r.status_code == 200
    assert f".{fmt}" in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert any(n.startswith("word/" if fmt == "docx" else "ppt/") for n in z.namelist())


def test_report_without_data_is_404(client):
    assert client.get("/api/reports/docx").status_code == 404
