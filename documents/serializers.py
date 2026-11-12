from rest_framework import serializers

from .models import Chunk, Document, Matter


class MatterSerializer(serializers.ModelSerializer):
    # Filled in by the view with .annotate(), so no extra query per matter
    document_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Matter
        fields = ["id", "name", "client", "document_count", "created_at"]


class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ["id", "index", "text"]


class DocumentSerializer(serializers.ModelSerializer):
    """Used for list + create. The client sends matter, title, text.
    status / summary / error are set by the background job, never by the client."""

    matter_name = serializers.CharField(source="matter.name", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "matter", "matter_name", "title", "text",
            "status", "summary", "error", "created_at", "updated_at",
        ]
        read_only_fields = ["status", "summary", "error", "created_at", "updated_at"]
        extra_kwargs = {"text": {"write_only": True}}  # keep list responses small

    def validate_text(self, value):
        if len(value.strip()) < 20:
            raise serializers.ValidationError("Document text is too short (min 20 characters).")
        return value


class DocumentDetailSerializer(DocumentSerializer):
    """Single document: also returns the full text and its chunks."""

    chunks = ChunkSerializer(many=True, read_only=True)

    class Meta(DocumentSerializer.Meta):
        fields = DocumentSerializer.Meta.fields + ["chunks"]
        extra_kwargs = {}


class AskSerializer(serializers.Serializer):
    """Input for POST /api/documents/<id>/ask/"""

    question = serializers.CharField(min_length=3, max_length=1000)


class CitationSerializer(serializers.ModelSerializer):
    chunk_id = serializers.IntegerField(source="id")

    class Meta:
        model = Chunk
        fields = ["chunk_id", "index", "text"]
