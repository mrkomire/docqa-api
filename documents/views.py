from django.db import transaction
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Document, Matter
from .serializers import DocumentDetailSerializer, DocumentSerializer, MatterSerializer
from .tasks import process_document


class MatterViewSet(viewsets.ModelViewSet):
    """/api/matters/  -> list, create, retrieve, update, delete"""

    serializer_class = MatterSerializer
    search_fields = ["name", "client"]

    def get_queryset(self):
        return Matter.objects.annotate(document_count=Count("documents")).order_by("-created_at")


class DocumentViewSet(viewsets.ModelViewSet):
    """/api/documents/  (filter by matter: ?matter=1, search: ?search=nda)"""

    search_fields = ["title"]

    def get_queryset(self):
        qs = Document.objects.select_related("matter")  # avoids N+1 for matter_name
        if self.action == "retrieve":
            qs = qs.prefetch_related("chunks")
        matter_id = self.request.query_params.get("matter")
        if matter_id:
            qs = qs.filter(matter_id=matter_id)
        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return DocumentDetailSerializer
        return DocumentSerializer

    def perform_create(self, serializer):
        doc = serializer.save()
        # Queue only after the row is committed, so the worker can always find it
        transaction.on_commit(lambda: process_document.delay(doc.id))

    @action(detail=True, methods=["post"])
    def reprocess(self, request, pk=None):
        """POST /api/documents/5/reprocess/ -> run the background job again"""
        doc = self.get_object()
        doc.status = Document.Status.PENDING
        doc.save(update_fields=["status", "updated_at"])
        transaction.on_commit(lambda: process_document.delay(doc.id))
        return Response({"id": doc.id, "status": doc.status}, status=status.HTTP_202_ACCEPTED)
