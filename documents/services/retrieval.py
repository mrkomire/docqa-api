"""Find the chunks most relevant to a question.

Keyword scoring (TF-IDF style), no extra infrastructure. Good for legal text,
where exact terms matter ("indemnity", "termination", party names).
Next step for scale: embeddings in PostgreSQL with pgvector, combined with this
keyword score (hybrid search).
"""
import math
import re
from collections import Counter

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "be", "by",
    "with", "this", "that", "what", "which", "who", "when", "how", "does", "do", "shall",
    "it", "its", "as", "at", "from", "any", "under", "there", "can", "will",
}


def stem(word: str) -> str:
    """Very light stemming so "governs"/"governed" and "indemnifies"/"indemnify" match."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [stem(w) for w in words if w not in STOPWORDS and len(w) > 1]


def top_chunks(question: str, chunks: list, k: int = 4) -> list:
    """chunks: objects with .text. Returns up to k best matches, best first."""
    query = set(tokenize(question))
    if not query or not chunks:
        return []

    chunk_tokens = [Counter(tokenize(c.text)) for c in chunks]
    n = len(chunks)
    # Rare words matter more: "indemnity" beats "agreement"
    idf = {t: math.log((n + 1) / (1 + sum(1 for ct in chunk_tokens if t in ct))) + 1 for t in query}

    scored = []
    for chunk, counts in zip(chunks, chunk_tokens):
        length = sum(counts.values()) or 1
        score = sum((counts[t] / length) * idf[t] for t in query if t in counts)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _, chunk in scored[:k]]
