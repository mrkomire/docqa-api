from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Document, Matter


class DocumentAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("lawyer", password="pass12345")
        self.matter = Matter.objects.create(name="Project Falcon", client="Acme Ltd")

    def test_requires_login(self):
        res = self.client.get("/api/documents/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_document_starts_pending(self):
        self.client.force_authenticate(self.user)
        res = self.client.post("/api/documents/", {
            "matter": self.matter.id,
            "title": "NDA",
            "text": "This NDA is between Acme Ltd and Beta LLP for 2 years.",
            "status": "done",  # client must NOT be able to set this
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], "pending")
        self.assertEqual(res.data["matter_name"], "Project Falcon")

    def test_rejects_short_text(self):
        self.client.force_authenticate(self.user)
        res = self.client.post("/api/documents/", {
            "matter": self.matter.id, "title": "x", "text": "too short",
        }, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("text", res.data)

    def test_filter_by_matter_and_count(self):
        other = Matter.objects.create(name="Other")
        Document.objects.create(matter=self.matter, title="A", text="a" * 30)
        Document.objects.create(matter=other, title="B", text="b" * 30)
        self.client.force_authenticate(self.user)

        res = self.client.get(f"/api/documents/?matter={self.matter.id}")
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["title"], "A")

        res = self.client.get("/api/matters/?search=falcon")
        self.assertEqual(res.data["results"][0]["document_count"], 1)

    def test_list_has_no_n_plus_1(self):
        for i in range(10):
            Document.objects.create(matter=self.matter, title=f"D{i}", text="x" * 30)
        self.client.force_authenticate(self.user)
        # 1 count query + 1 page query (with JOIN), however many documents
        with self.assertNumQueries(2):
            self.client.get("/api/documents/")


# ---------- Step 3: background processing ----------
from unittest.mock import patch

from django.test import TestCase

from .services.chunking import chunk_text
from .tasks import process_document

LONG_TEXT = "\n".join(f"Clause {i}. The Supplier shall deliver item {i} within 30 days." for i in range(60))


class ChunkingTests(TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(chunk_text("Hello world"), ["Hello world"])

    def test_long_text_is_split_with_limit(self):
        chunks = chunk_text(LONG_TEXT, max_chars=500, overlap=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 500 for c in chunks))
        self.assertIn("Clause 0.", chunks[0])
        self.assertIn("Clause 59.", chunks[-1])


class ProcessDocumentTaskTests(TestCase):
    def setUp(self):
        matter = Matter.objects.create(name="Falcon")
        self.doc = Document.objects.create(matter=matter, title="Supply Agreement", text=LONG_TEXT)

    @patch("documents.tasks.summarise", return_value="Supplier delivers within 30 days [0].")
    def test_success_creates_chunks_and_summary(self, mock_summarise):
        process_document(self.doc.id)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "done")
        self.assertEqual(self.doc.summary, "Supplier delivers within 30 days [0].")
        self.assertGreater(self.doc.chunks.count(), 1)
        mock_summarise.assert_called_once()

    @patch("documents.tasks.summarise", return_value="ok [0]")
    def test_rerun_is_idempotent(self, _):
        process_document(self.doc.id)
        first = self.doc.chunks.count()
        process_document(self.doc.id)
        self.assertEqual(self.doc.chunks.count(), first)  # no duplicates

    @patch("documents.tasks.summarise", side_effect=ValueError("bad response"))
    def test_failure_marks_document_failed(self, _):
        process_document(self.doc.id)
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.status, "failed")
        self.assertIn("bad response", self.doc.error)


class UploadQueuesJobTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("lawyer", password="pass12345")
        self.matter = Matter.objects.create(name="Falcon")
        self.client.force_authenticate(self.user)

    @patch("documents.views.process_document.delay")
    def test_upload_queues_job_after_commit(self, mock_delay):
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post("/api/documents/", {
                "matter": self.matter.id, "title": "NDA", "text": LONG_TEXT,
            }, format="json")
        self.assertEqual(res.status_code, 201)
        mock_delay.assert_called_once_with(res.data["id"])

    @patch("documents.views.process_document.delay")
    def test_reprocess_returns_202(self, mock_delay):
        doc = Document.objects.create(matter=self.matter, title="NDA", text=LONG_TEXT, status="failed")
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(f"/api/documents/{doc.id}/reprocess/")
        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.data["status"], "pending")
        mock_delay.assert_called_once_with(doc.id)
