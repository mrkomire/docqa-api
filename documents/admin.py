from django.contrib import admin

from .models import Chunk, Document, Matter


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
