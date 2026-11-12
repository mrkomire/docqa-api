"""LLM calls live here, not in views or tasks, so they are easy to swap and to mock in tests.

LLM_PROVIDER=anthropic -> Claude via the official SDK (needs ANTHROPIC_API_KEY)
LLM_PROVIDER=fake      -> no network call; returns a simple extractive summary (local dev, CI)
"""
import os

import anthropic

SUMMARY_SYSTEM = (
    "You summarise legal documents for lawyers. Be accurate and neutral. "
    "Only use facts from the numbered chunks. After every sentence, cite the chunk(s) "
    "it came from like [0] or [1][3]. If something is unclear, say so instead of guessing."
)


def _provider() -> str:
    default = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "fake"
    return os.environ.get("LLM_PROVIDER", default)


def _numbered(chunks: list[str]) -> str:
    return "\n\n".join(f"[{i}]\n{c}" for i, c in enumerate(chunks))


def summarise(title: str, chunks: list[str]) -> str:
    if _provider() == "fake":
        first = " ".join(chunks[0].split()[:40]) if chunks else ""
        return f"(offline summary) {title}: {first}... [0]"

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY; SDK retries 429/5xx itself
    response = client.messages.create(
        model=os.environ.get("LLM_MODEL", "claude-opus-5-5"),
        max_tokens=4000,
        output_config={"effort": "low"},  # summarising is a simple task
        system=SUMMARY_SYSTEM,
        messages=[{
            "role": "user",
            "content": f"Document: {title}\n\n{_numbered(chunks)}\n\n"
                       "Write a 5-8 sentence summary: parties, purpose, key obligations, "
                       "dates/term, and any unusual risks. Cite chunks.",
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined to summarise this document.")
    return "".join(b.text for b in response.content if b.type == "text").strip()


ANSWER_SYSTEM = (
    "You answer questions about a legal document for lawyers. Use ONLY the numbered chunks "
    "provided. Cite the chunk number after each claim, like [3]. If the chunks do not contain "
    "the answer, reply exactly: \"The document does not say.\" Never guess or use outside knowledge."
)


def answer(question: str, chunks: list) -> str:
    """chunks: Chunk objects. They are numbered with their real index so citations map back."""
    if not chunks:
        return "The document does not say."

    if _provider() == "fake":
        from .retrieval import tokenize  # offline: return the best-matching line, cited

        q = set(tokenize(question))
        best = chunks[0]
        lines = [line for line in best.text.split("\n") if line.strip()]
        sentence = max(lines, key=lambda line: len(q & set(tokenize(line))))
        return f"{sentence[:300]} [{best.index}]"

    context = "\n\n".join(f"[{c.index}]\n{c.text}" for c in chunks)
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=os.environ.get("LLM_MODEL", "claude-opus-5-5"),
        max_tokens=4000,
        output_config={"effort": "low"},
        system=ANSWER_SYSTEM,
        messages=[{"role": "user", "content": f"Chunks:\n{context}\n\nQuestion: {question}"}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined to answer this question.")
    return "".join(b.text for b in response.content if b.type == "text").strip()
