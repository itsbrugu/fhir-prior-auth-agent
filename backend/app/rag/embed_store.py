"""RAG layer: indexes a patient's FHIR evidence items into an embedded Chroma
vector store (Chroma's bundled ONNX MiniLM embedding function -- open-source,
runs locally, no external embeddings API) and retrieves the passages most
relevant to a query.
"""

import chromadb

from app.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_path)
    return _client


def _collection_name(patient_id: str) -> str:
    return f"patient_{patient_id}".replace("-", "_")


def index_patient(patient_id: str, evidence_items: list[dict]) -> None:
    client = _get_client()
    name = _collection_name(patient_id)
    try:
        client.delete_collection(name)
    except Exception:
        pass
    collection = client.create_collection(name)

    if not evidence_items:
        return

    documents = [item["text"] for item in evidence_items]
    ids = [f"{item['resource_type']}-{item['resource_id']}-{i}" for i, item in enumerate(evidence_items)]
    metadatas = [
        {"resource_type": item["resource_type"], "resource_id": item["resource_id"], "date": item.get("date") or ""}
        for item in evidence_items
    ]
    collection.add(documents=documents, ids=ids, metadatas=metadatas)


def retrieve(patient_id: str, query: str, k: int = 5) -> list[str]:
    client = _get_client()
    name = _collection_name(patient_id)
    try:
        collection = client.get_collection(name)
    except Exception:
        return []

    count = collection.count()
    if count == 0:
        return []

    result = collection.query(query_texts=[query], n_results=min(k, count))
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    citations = []
    for doc, meta in zip(documents, metadatas):
        citations.append(f"{meta.get('resource_type', '')}/{meta.get('resource_id', '')}: {doc}")
    return citations
