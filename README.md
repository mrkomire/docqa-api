# DocQA API — Legal document Q&A with citations

A Django REST API where lawyers upload documents, get an AI summary, and ask questions.
Every answer cites the exact part of the document it came from, and made-up citations are flagged.

Built with **Python, Django 5.2 (LTS), Django REST Framework, Celery, Redis** and the **Anthropic Claude API**.

## What it does

| Endpoint | Method | What happens |
|---|---|---|
| `/api/matters/` | GET, POST | List or create matters (a case or deal). Each shows its `document_count`. |
| `/api/documents/` | GET, POST | Upload a document. Returns `201` right away with `status: "pending"`; a background job processes it. Filter with `?matter=1`, search with `?search=nda`. |
| `/api/documents/<id>/` | GET | Document with status, summary, full text and chunks. |
| `/api/documents/<id>/reprocess/` | POST | Run the background job again. Returns `202 Accepted`. |
| `/api/documents/<id>/ask/` | POST | `{"question": "..."}` → answer + cited chunks. `409` if the document is not processed yet. |

All endpoints need a login (`IsAuthenticated`), and lists are paginated (20 per page).

## How it works

```
                        ┌──────────────────────── Django + DRF ─────────────────────────┐
 POST /documents/  ───► │ serializer validates → save (status=pending) → 201            │
                        │      └─ transaction.on_commit → queue job                     │
                        └──────────────────────────────┬────────────────────────────────┘
                                                       ▼  Redis
                        ┌────────────────────── Celery worker ──────────────────────────┐
                        │ status=processing → split into chunks → LLM summary with [n]  │
                        │ citations → status=done   (or failed + error message)         │
                        └───────────────────────────────────────────────────────────────┘

 POST /documents/5/ask/ → find the best chunks (keyword scoring) → LLM answers ONLY from them
                        → check every [n] citation was really given → save to audit trail
```

### Data model
- **Matter** → has many **Documents** → each has many **Chunks** (ordered, unique position)
- **Question**: who asked, the question, the answer, the chunks it cited, and whether any citation was invalid (audit trail)

## Design decisions

- **Background jobs, not long requests.** LLM calls can take seconds or fail. The upload returns at once; Celery does the work. The job is queued with `transaction.on_commit`, so the worker never runs before the row is saved.
- **Reliable jobs.** Temporary API errors (rate limits, network, 5xx) are retried with exponential backoff. Other errors mark the document `failed` and keep the message. Jobs are **idempotent**: re-running replaces chunks and never duplicates them. `ACKS_LATE` re-queues a job if a worker crashes.
- **Citations you can check.** Chunks are numbered with their real position, and the model must cite them. The API checks every `[n]` against the chunks the model was actually given. Anything else is returned in `invalid_citations` and flagged in the audit trail.
- **"The document does not say."** The prompt tells the model not to guess, and retrieval returns nothing when no chunk matches.
- **Keyword retrieval (TF-IDF style + light stemming).** It needs no extra infrastructure, and exact terms matter in legal text ("indemnity", party names). Next step: embeddings in PostgreSQL with **pgvector**, combined with keyword scores (hybrid search).
- **LLM code in one place** (`documents/services/llm.py`). It is easy to swap provider or model, and easy to mock in tests. `LLM_PROVIDER=fake` runs everything offline.
- **No N+1 queries.** `select_related` / `prefetch_related` / `annotate(Count)`. A test asserts that listing documents takes exactly 2 queries.
- **Secrets from environment** (`.env`, git-ignored), never in code.

## Run it locally

Needs Python 3.12+ and Redis (`brew install redis && brew services start redis`).

```bash
git clone https://github.com/mrkomire/docqa-api.git && cd docqa-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # add ANTHROPIC_API_KEY, or set LLM_PROVIDER=fake
python manage.py migrate
python manage.py createsuperuser
```

Run these in two terminals:

```bash
celery -A config worker -l info
python manage.py runserver
```

Open http://127.0.0.1:8000/api/ (browsable API) or http://127.0.0.1:8000/admin/.

No Redis? Set `CELERY_TASK_ALWAYS_EAGER=1` and jobs run inline.

### Example

```bash
curl -u user:pass -H "Content-Type: application/json" \
  -d '{"question": "How much notice is needed to terminate?"}' \
  http://127.0.0.1:8000/api/documents/1/ask/
```

```json
{
  "question_id": 1,
  "answer": "Either party may terminate this Agreement on 90 days written notice. [0]",
  "citations": [{"chunk_id": 4, "index": 0, "text": "..."}],
  "invalid_citations": []
}
```

## Tests

```bash
LLM_PROVIDER=fake python manage.py test documents
```

There are 20 tests, and the LLM is mocked, so they never call a real API. They cover:
- login required
- read-only fields
- validation
- filtering
- the N+1 query count
- chunking
- job success, failure and idempotency
- the job being queued after commit
- retrieval ranking and stemming
- cited answers
- flagging invented citations
- `409` when a document is not ready

## Project layout

```
config/             settings, URLs, Celery app
documents/
  models.py         Matter, Document, Chunk, Question
  serializers.py    validation + JSON shape
  views.py          viewsets, /reprocess/, /ask/
  tasks.py          Celery job: chunk + summarise
  services/
    chunking.py     paragraph-aware chunks with overlap
    retrieval.py    keyword scoring + stemming
    llm.py          Claude calls (summary, answer) + offline mode
    qa.py           retrieve → answer → citation check
  tests.py
```

## Next steps
- PostgreSQL + pgvector embeddings for hybrid search
- Streaming answers (server-sent events)
- PDF/DOCX upload with text extraction
- Per-matter permissions (only the lawyers on a matter can see its documents)
- Docker Compose and CI
