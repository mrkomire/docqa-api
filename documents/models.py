from django.db import models


class Matter(models.Model):
    """A legal matter (case/deal). Documents belong to a matter."""

    name = models.CharField(max_length=200)
    client = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Document(models.Model):
    """An uploaded document. Processing (chunking + LLM summary) runs in the background."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    text = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    summary = models.TextField(blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Chunk(models.Model):
    """A piece of a document. Answers cite chunks so a lawyer can check the source."""

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField()  # position in the document: 0, 1, 2...
    text = models.TextField()

    class Meta:
        ordering = ["document", "index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "index"], name="unique_chunk_position"),
        ]

    def __str__(self):
        return f"{self.document.title} #{self.index}"
