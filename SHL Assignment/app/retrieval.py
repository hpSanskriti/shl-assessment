"""Retrieval module: loads catalog, builds embeddings, provides semantic search."""
import json
import os
import numpy as np
from sentence_transformers import SentenceTransformer

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
CATALOG_PATH = os.path.join(DATA_DIR, "catalog.json")
EMBEDDINGS_PATH = os.path.join(DATA_DIR, "catalog_embeddings.npy")

# Singleton instances
_model = None
_catalog = None
_embeddings = None


def get_model() -> SentenceTransformer:
    """Load sentence transformer model (singleton)."""
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def get_catalog() -> list[dict]:
    """Load catalog data (singleton)."""
    global _catalog
    if _catalog is None:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            _catalog = json.load(f)
    return _catalog


def build_search_text(item: dict) -> str:
    """Build a text representation of a catalog item for embedding."""
    parts = [
        item.get("name", ""),
        item.get("description", ""),
        f"Test type: {item.get('test_type', '')}",
    ]
    if item.get("remote_testing"):
        parts.append("Supports remote testing")
    if item.get("adaptive_irt"):
        parts.append("Adaptive/IRT enabled")
    return " | ".join(p for p in parts if p)


def get_embeddings() -> np.ndarray:
    """Get or build catalog embeddings (singleton)."""
    global _embeddings
    if _embeddings is not None:
        return _embeddings

    if os.path.exists(EMBEDDINGS_PATH):
        _embeddings = np.load(EMBEDDINGS_PATH)
        return _embeddings

    # Build embeddings
    catalog = get_catalog()
    model = get_model()
    texts = [build_search_text(item) for item in catalog]
    _embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    np.save(EMBEDDINGS_PATH, _embeddings)
    return _embeddings


def search_catalog(query: str, top_k: int = 20, type_filter: list[str] | None = None) -> list[dict]:
    """
    Semantic search over the catalog.
    
    Args:
        query: Natural language search query
        top_k: Number of results to return
        type_filter: Optional list of test type codes to filter by (e.g. ["K", "A"])
    
    Returns:
        List of catalog items sorted by relevance
    """
    model = get_model()
    catalog = get_catalog()
    embeddings = get_embeddings()

    # Encode query
    query_embedding = model.encode([query], normalize_embeddings=True)

    # Compute cosine similarity (embeddings are normalized, so dot product = cosine sim)
    similarities = np.dot(embeddings, query_embedding.T).flatten()

    # Apply type filter if provided
    if type_filter:
        for i, item in enumerate(catalog):
            item_types = set(item.get("test_type", ""))
            if not item_types.intersection(set(type_filter)):
                similarities[i] = -1  # Exclude from results

    # Get top-k indices
    top_indices = np.argsort(similarities)[::-1][:top_k]

    results = []
    for idx in top_indices:
        if similarities[idx] <= 0:
            break
        item = catalog[idx].copy()
        item["score"] = float(similarities[idx])
        results.append(item)

    return results


def get_assessment_by_name(name: str) -> dict | None:
    """Look up an assessment by exact or partial name match."""
    catalog = get_catalog()
    name_lower = name.lower().strip()
    
    # Exact match
    for item in catalog:
        if item["name"].lower() == name_lower:
            return item
    
    # Partial match
    for item in catalog:
        if name_lower in item["name"].lower():
            return item
    
    return None


def get_assessments_by_names(names: list[str]) -> list[dict]:
    """Look up multiple assessments by name."""
    results = []
    for name in names:
        item = get_assessment_by_name(name)
        if item:
            results.append(item)
    return results
