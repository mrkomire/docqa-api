"""Question answering over one document: retrieve -> ask LLM -> verify citations."""
import re

from .llm import answer
from .retrieval import top_chunks

CITATION = re.compile(r"\[(\d+)\]")


def ask_document(document, question: str) -> dict:
    chunks = list(document.chunks.all())
    relevant = top_chunks(question, chunks, k=4)
    text = answer(question, relevant)

    # Citation check: only keep citations to chunks we actually gave the model.
    # A citation to anything else is a hallucination and gets flagged, not shown as proof.
    given = {c.index: c for c in relevant}
    cited_numbers = [int(n) for n in CITATION.findall(text)]
    valid = sorted({n for n in cited_numbers if n in given})
    invalid = sorted({n for n in cited_numbers if n not in given})

    return {
        "answer": text,
        "citations": [given[n] for n in valid],
        "invalid_citations": invalid,
        "retrieved_chunk_indexes": [c.index for c in relevant],
    }
