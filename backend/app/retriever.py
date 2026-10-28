"""Retrieval layer for categorisation (the "R" in RAG).

Every merchant whose category we know (from a user correction or an earlier LLM answer) is
embedded with a sentence-transformer and stored in a persistent ChromaDB collection. When a
new, unrecognised merchant shows up, we look up its nearest labelled neighbours by cosine
similarity. Those neighbours are then used in two ways:

* as few-shot context in the LLM prompt, so Claude's answer is grounded in how *this* user
  labels things (see ``categorizer.llm_categorise``);
* with no LLM key, a very close match to a merchant the *user* labelled is applied directly,
  which makes it a nearest-neighbour classifier over the user's own corrections.

Only user-confirmed labels are trusted for direct assignment, so the LLM can't reinforce its
own mistakes. The whole layer is optional: if ``chromadb`` / ``sentence-transformers`` aren't
installed, or ``SPENDSENSE_RAG=0``, ``get_retriever()`` returns ``None`` and categorisation
behaves exactly as before.
"""
from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

log = logging.getLogger(__name__)

Embedder = Callable[[Sequence[str]], list[list[float]]]

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "merchant_labels"


@dataclass(frozen=True)
class Neighbour:
    merchant: str
    category: str
    source: str          # "user" | "llm"
    similarity: float    # cosine similarity, 1.0 = identical direction


def embedding_text(merchant: str) -> str:
    """Strip the noise bank exports add (UPI handles, reference numbers, punctuation)."""
    text = str(merchant).lower()
    text = re.sub(r"\S+@\S+", " ", text)          # upi handles like swiggy@axb
    text = re.sub(r"\d+", " ", text)              # reference numbers, store ids
    text = re.sub(r"[^a-z&]+", " ", text)
    return re.sub(r"\s+", " ", text).strip() or str(merchant).strip().lower()


def sentence_transformer_embedder(model_name: str = DEFAULT_MODEL) -> Embedder:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    def embed(texts: Sequence[str]) -> list[list[float]]:
        return model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False).tolist()

    return embed


class MerchantRetriever:
    """Vector store of labelled merchants, backed by a persistent ChromaDB collection."""

    def __init__(self, path: str, embedder: Embedder):
        import chromadb

        self._embed = embedder
        self._client = chromadb.PersistentClient(path=path)
        self._col = self._client.get_or_create_collection(
            COLLECTION, embedding_function=None, metadata={"hnsw:space": "cosine"}
        )

    def count(self) -> int:
        return self._col.count()

    def upsert(self, items: Iterable[tuple[str, str, str]]) -> int:
        """Add or update (merchant, category, source) labels. Merchant is the id."""
        rows = {}
        for merchant, category, source in items:
            key = re.sub(r"\s+", " ", str(merchant)).strip().lower()
            if key:
                rows[key] = (category, source)
        if not rows:
            return 0
        ids = list(rows)
        self._col.upsert(
            ids=ids,
            embeddings=self._embed([embedding_text(m) for m in ids]),
            documents=ids,
            metadatas=[{"category": c, "source": s} for c, s in rows.values()],
        )
        return len(ids)

    def sync(self, items: Iterable[tuple[str, str, str]]) -> int:
        """Bring the store in line with the database, embedding only new or changed labels."""
        wanted = {m: (c, s) for m, c, s in items}
        if not wanted:
            return 0
        existing = self._col.get(ids=list(wanted), include=["metadatas"])
        have = {i: (md["category"], md["source"]) for i, md in zip(existing["ids"], existing["metadatas"])}
        stale = [(m, c, s) for m, (c, s) in wanted.items() if have.get(m) != (c, s)]
        return self.upsert(stale)

    def similar(self, merchants: Sequence[str], k: int = 5,
                min_similarity: float = 0.35) -> dict[str, list[Neighbour]]:
        """Top-k labelled neighbours for each merchant, closest first."""
        merchants = [m for m in dict.fromkeys(merchants) if m]
        total = self.count()
        if not merchants or total == 0:
            return {m: [] for m in merchants}
        res = self._col.query(
            query_embeddings=self._embed([embedding_text(m) for m in merchants]),
            n_results=min(k + 1, total),           # +1: the merchant itself may already be stored
            include=["metadatas", "distances", "documents"],
        )
        out: dict[str, list[Neighbour]] = {}
        for merchant, docs, metas, dists in zip(merchants, res["documents"], res["metadatas"],
                                                res["distances"]):
            self_key = re.sub(r"\s+", " ", merchant).strip().lower()
            hits = [
                Neighbour(doc, md["category"], md["source"], round(1.0 - float(d), 4))
                for doc, md, d in zip(docs, metas, dists)
                if doc != self_key and 1.0 - float(d) >= min_similarity
            ]
            out[merchant] = hits[:k]
        return out


# ------------------------------------------------------------------ singleton

_lock = threading.Lock()
_retriever: MerchantRetriever | None = None
_initialised = False


def rag_enabled_by_env() -> bool:
    return os.getenv("SPENDSENSE_RAG", "1").lower() not in {"0", "false", "no", "off"}


def get_retriever() -> MerchantRetriever | None:
    """The app-wide retriever, built lazily. None if RAG is off or its dependencies are missing."""
    global _retriever, _initialised
    if _initialised:
        return _retriever
    with _lock:
        if not _initialised:
            if rag_enabled_by_env():
                try:
                    _retriever = MerchantRetriever(
                        path=os.getenv("SPENDSENSE_VECTOR_DIR", "./vector_store"),
                        embedder=sentence_transformer_embedder(
                            os.getenv("SPENDSENSE_EMBED_MODEL", DEFAULT_MODEL)),
                    )
                except Exception as exc:  # missing packages, model download failure, etc.
                    log.warning("Retrieval disabled: %s", exc)
                    _retriever = None
            _initialised = True
    return _retriever


def set_retriever(retriever: MerchantRetriever | None) -> None:
    """Swap the app-wide retriever (used by tests)."""
    global _retriever, _initialised
    with _lock:
        _retriever, _initialised = retriever, True
