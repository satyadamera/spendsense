import pytest

from app import retriever


@pytest.fixture(autouse=True)
def no_vector_store_by_default():
    """Tests run without the real embedding model; RAG tests install their own retriever."""
    retriever.set_retriever(None)
    yield
    retriever.set_retriever(None)
