"""A dependency-free semantic index (TF-IDF + cosine similarity).

Stands in for Azure AI Search / Qdrant / Pinecone in the knowledge layer. The
Retrieval Improvement Loop (Loop 2) tunes ``top_k``, reranking, and which
metadata fields are folded into the searchable text.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class SemanticIndex:
    def __init__(self, listings: list[dict], metadata_fields: list[str] | None = None) -> None:
        self.metadata_fields = metadata_fields or ["neighborhood", "property_type"]
        self._docs: dict[str, Counter] = {}
        self._idf: dict[str, float] = {}
        self._listings_by_id: dict[str, dict] = {}
        self.build(listings)

    def _doc_text(self, listing: dict) -> str:
        parts = [str(listing.get("description", "")), str(listing.get("address", ""))]
        for field in self.metadata_fields:
            parts.append(str(listing.get(field, "")))
        return " ".join(parts)

    def build(self, listings: list[dict]) -> None:
        """(Re)build the index. Called again by Loop 2 after metadata changes."""
        self._docs.clear()
        self._listings_by_id.clear()
        df: Counter = Counter()
        for listing in listings:
            tokens = _tokenize(self._doc_text(listing))
            tf = Counter(tokens)
            self._docs[listing["id"]] = tf
            self._listings_by_id[listing["id"]] = listing
            for term in tf:
                df[term] += 1
        n = max(1, len(self._docs))
        self._idf = {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}

    def _vector(self, tf: Counter) -> dict[str, float]:
        return {term: freq * self._idf.get(term, 1.0) for term, freq in tf.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        common = set(a) & set(b)
        dot = sum(a[t] * b[t] for t in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        q_vec = self._vector(Counter(_tokenize(query)))
        scored = [
            (lid, self._cosine(q_vec, self._vector(tf))) for lid, tf in self._docs.items()
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s in scored[:top_k] if s[1] > 0.0]
