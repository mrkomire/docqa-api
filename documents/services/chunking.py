"""Split a document into overlapping chunks.

Paragraph-aware: we try not to cut a clause in half. Overlap keeps context
that sits across a chunk boundary (e.g. a definition used in the next clause).
"""


def chunk_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        # A single very long paragraph: hard-split it
        while len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:max_chars])
            para = para[max_chars - overlap:]

        if len(current) + len(para) + 1 <= max_chars:
            current = f"{current}\n{para}" if current else para
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n{para}" if tail else para

    if current:
        chunks.append(current)
    return chunks
