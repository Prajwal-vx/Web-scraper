import re
import math
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

class RAGPipelineEngine:
    """
    Transforms extracted web datasets into clean, chunked, source-attributed RAG documents
    ready for Vector DB ingestion and semantic search.
    """

    @staticmethod
    def chunk_text(
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ) -> List[str]:
        """
        Splits text into overlapping sliding-window passages by words.
        """
        words = text.split()
        if not words:
            return []

        chunks = []
        step = max(1, chunk_size - chunk_overlap)
        for i in range(0, len(words), step):
            chunk = " ".join(words[i : i + chunk_size])
            if chunk.strip():
                chunks.append(chunk.strip())
            if i + chunk_size >= len(words):
                break
        return chunks

    @staticmethod
    def compute_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def text_to_term_vector(text: str) -> Dict[str, float]:
        """Creates normalized term frequency vector for lightweight zero-dependency similarity."""
        tokens = re.findall(r"\b\w{2,}\b", text.lower())
        if not tokens:
            return {}
        counts = Counter(tokens)
        norm = math.sqrt(sum(v * v for v in counts.values()))
        return {w: c / norm for w, c in counts.items()}

    @staticmethod
    def cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Computes cosine similarity between two term frequency vectors."""
        if not vec1 or not vec2:
            return 0.0
        # Dot product
        dot = sum(v * vec2.get(k, 0.0) for k, v in vec1.items())
        return max(0.0, min(1.0, dot))

    @classmethod
    def process_record_for_rag(
        cls,
        record_id: str,
        source_url: str,
        data: Dict[str, Any],
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Extracts narrative text from record fields and produces chunked documents.
        """
        # Combine text fields
        text_parts = []
        for k, v in data.items():
            if v and isinstance(v, str):
                text_parts.append(f"{k}: {v}")
            elif isinstance(v, list):
                text_parts.append(f"{k}: {', '.join(str(i) for i in v)}")

        full_text = "\n".join(text_parts)
        text_chunks = cls.chunk_text(full_text, chunk_size, chunk_overlap)

        results = []
        for idx, chunk in enumerate(text_chunks):
            results.append({
                "record_id": record_id,
                "source_url": source_url,
                "chunk_index": idx,
                "text_content": chunk,
                "metadata": {
                    "source_url": source_url,
                    "record_id": record_id,
                    "chunk_index": idx,
                    "total_chunks": len(text_chunks),
                },
                "content_hash": cls.compute_hash(chunk)
            })

        return results

    @classmethod
    def query_chunks(
        cls,
        chunks: List[Dict[str, Any]],
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Executes semantic keyword & cosine similarity search across chunks,
        returning top matches with citations and scores.
        """
        query_vec = cls.text_to_term_vector(query)
        scored_chunks = []

        for chunk in chunks:
            content = chunk.get("text_content", "")
            chunk_vec = cls.text_to_term_vector(content)
            score = cls.cosine_similarity(query_vec, chunk_vec)
            if score > 0.01:
                chunk_copy = dict(chunk)
                chunk_copy["similarity_score"] = round(score, 4)
                scored_chunks.append(chunk_copy)

        scored_chunks.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored_chunks[:top_k]
