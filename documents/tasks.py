import logging

import anthropic
from celery import shared_task
from django.db import transaction

from .models import Chunk, Document
from .services.chunking import chunk_text
from .services.llm import summarise

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError),
    retry_backoff=True,   # wait 1s, 2s, 4s... between retries
    max_retries=3,
)
def process_document(self, document_id: int) -> None:
    """Chunk the document, then ask the LLM for a cited summary.
    Safe to re-run: old chunks are replaced (idempotent)."""
    doc = Document.objects.get(pk=document_id)
    doc.status = Document.Status.PROCESSING
    doc.error = ""
    doc.save(update_fields=["status", "error", "updated_at"])

    try:
        pieces = chunk_text(doc.text)
        with transaction.atomic():
            doc.chunks.all().delete()
            Chunk.objects.bulk_create(
                Chunk(document=doc, index=i, text=t) for i, t in enumerate(pieces)
            )

        doc.summary = summarise(doc.title, pieces)
        doc.status = Document.Status.DONE
        doc.save(update_fields=["summary", "status", "updated_at"])
        logger.info("Processed document %s into %s chunks", doc.pk, len(pieces))

    except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError):
        raise  # temporary problem: let Celery retry
    except Exception as exc:
        logger.exception("Processing failed for document %s", doc.pk)
        doc.status = Document.Status.FAILED
        doc.error = str(exc)[:1000]
        doc.save(update_fields=["status", "error", "updated_at"])
