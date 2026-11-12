from django.contrib import admin

from .models import Chunk, Document, Matter, Question


@admin.register(Matter)
class MatterAdmin(admin.ModelAdmin):
    list_display = ["name", "client", "created_at"]
    search_fields = ["name", "client"]


class ChunkInline(admin.TabularInline):
    model = Chunk
    extra = 0


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "matter", "status", "created_at"]
    list_filter = ["status", "matter"]
    search_fields = ["title", "text"]
    inlines = [ChunkInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["question", "document", "asked_by", "has_invalid_citations", "created_at"]
    list_filter = ["has_invalid_citations"]
    readonly_fields = ["document", "asked_by", "question", "answer", "cited_chunks", "has_invalid_citations"]
