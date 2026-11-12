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
