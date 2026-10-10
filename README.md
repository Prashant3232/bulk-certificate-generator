# Bulk Certificate Generator

A backend API that accepts **one request containing many recipients**, validates every recipient, generates a PDF certificate for each valid one from a single predefined template, tracks progress, and lets the client download the results (one by one or as a ZIP).

**Tech stack:** Python 3.10+, FastAPI, SQLAlchemy 2 (SQLite by default, PostgreSQL-ready), Pydantic v2, ReportLab (PDF generation), pytest.

## Features

- Bulk request: many recipients in a single `POST`
- Per-recipient validation: a bad row is recorded as failed with a reason, and the other rows still generate
- Background processing with live progress tracking
- One failing certificate never blocks the others
- Download a single PDF or a ZIP of all successful certificates
- 41 automated tests

---

## 1. Setup

Requires **Python 3.10 or newer**. No database server is needed, because SQLite is used by default and tables are created automatically on startup.

### Windows (PowerShell)

```powershell
cd certgen
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

If activation is blocked by "running scripts is disabled", run this once and activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

### Linux / macOS

```bash
cd certgen
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Configuration (optional environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./certgen.db` | Any SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@localhost/certgen` (also `pip install psycopg2-binary`) |
| `CERT_STORAGE_DIR` | `./storage` | Folder where generated PDFs are stored |
| `MAX_RECIPIENTS_PER_JOB` | `1000` | Maximum recipients per request (more returns HTTP 422) |

## 2. Run the application

```bash
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Interactive docs (Swagger UI): http://localhost:8000/docs
- Health check: http://localhost:8000/health

Docker alternative:

```bash
docker build -t certgen .
docker run -p 8000:8000 -v certgen-data:/data certgen
```

## 3. Run the tests

```bash
pytest -v
```

Tests use their own temporary SQLite database and storage folder, so they never touch real data.

| Required area | Test file |
|---|---|
| Creating a generation job | `tests/test_create_job.py` |
| Input validation | `tests/test_validation.py` |
| Certificate generation | `tests/test_generation.py` |
| Job status / progress | `tests/test_progress.py` |
| Single certificate failure | `tests/test_failure_handling.py` |
| Retrieving certificates | `tests/test_retrieval.py` |

---

## 4. API usage

The easiest way to try the API is the Swagger page at http://localhost:8000/docs (click an endpoint, then **Try it out**). Command-line examples are below.

### Submit a bulk request: `POST /api/v1/jobs`

Request body:

```json
{
  "event_name": "Python Bootcamp 2026",
  "issuer": "Acme Academy",
  "issue_date": "2026-10-07",
  "recipients": [
    {"name": "Asha Rao", "email": "asha@example.com"},
    {"name": "Ravi Kumar", "email": "ravi@example.com", "achievement": "with Distinction"},
    {"name": "", "email": "not-an-email"}
  ]
}
```

| Field | Rules |
|---|---|
| `event_name` | required, max 200 characters |
| `issuer` | optional, printed as the signatory |
| `issue_date` | optional, defaults to today |
| `recipients` | 1 to `MAX_RECIPIENTS_PER_JOB` items |
| `recipients[].name` | required, max 100 characters |
| `recipients[].email` | required, valid email, unique within the job (case-insensitive) |
| `recipients[].achievement` | optional, printed under the event name |

**PowerShell** (uses the included `samples/request.json`):

```powershell
$job = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/jobs -ContentType "application/json" -InFile samples\request.json
$job
```

**Linux / macOS / Git Bash:**

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d @samples/request.json
```

Response `202 Accepted` (generation continues in the background):

```json
{
  "id": "d1141f43ff4a46f6bb00a61b4a15ca28",
  "status": "PENDING",
  "total": 4, "succeeded": 0, "failed": 2, "pending": 2,
  "progress_percent": 50.0,
  "failures": [
    {"certificate_id": "...", "row_index": 3, "recipient_name": "", "recipient_email": "not-an-email",
     "error": "Invalid recipient data - name: String should have at least 1 character; email: ..."},
    {"certificate_id": "...", "row_index": 4, "recipient_name": "Asha Again", "recipient_email": "ASHA@example.com",
     "error": "Duplicate email in this job (first used in row 1)"}
  ],
  "certificates_url": "/api/v1/jobs/d1141f43ff4a46f6bb00a61b4a15ca28/certificates",
  "download_all_url": "/api/v1/jobs/d1141f43ff4a46f6bb00a61b4a15ca28/download"
}
```

### Check progress: `GET /api/v1/jobs/{job_id}`

Poll this endpoint. It returns `status`, counters (`total`, `succeeded`, `failed`, `pending`), `progress_percent`, timestamps, and the `failures` list with a reason for every failed row.

Job statuses: `PENDING` -> `PROCESSING` -> `COMPLETED` (all succeeded) | `COMPLETED_WITH_ERRORS` (some failed) | `FAILED` (none generated).

```powershell
# PowerShell
Invoke-RestMethod http://localhost:8000/api/v1/jobs/$($job.id)
```

```bash
# Linux / macOS
curl http://localhost:8000/api/v1/jobs/<job_id>
```

### Retrieve certificates

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/jobs/{job_id}/certificates?status=SUCCESS&limit=100&offset=0` | Paginated list; each item has `status`, `error`, and a `download_url` when successful |
| `GET /api/v1/jobs/{job_id}/certificates/{certificate_id}/download` | One certificate as a PDF |
| `GET /api/v1/jobs/{job_id}/download` | ZIP of all successful certificates (only after the job finished, otherwise `409`) |

```powershell
# PowerShell
Invoke-WebRequest http://localhost:8000/api/v1/jobs/$($job.id)/download -OutFile certs.zip
Expand-Archive certs.zip -DestinationPath certs -Force
```

```bash
# Linux / macOS
curl -o certs.zip http://localhost:8000/api/v1/jobs/<job_id>/download
```

HTTP errors: `404` unknown job or certificate, `409` certificate unavailable or job not finished, `422` invalid request envelope.

### Try a large batch

```powershell
python scripts\make_bulk_payload.py 500 | Out-File -Encoding ascii bulk.json
$big = Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/jobs -ContentType "application/json" -InFile bulk.json
Invoke-RestMethod http://localhost:8000/api/v1/jobs/$($big.id)
```

```bash
python scripts/make_bulk_payload.py 500 > bulk.json
curl -X POST http://localhost:8000/api/v1/jobs -H "Content-Type: application/json" -d @bulk.json
```

---

## 5. Project structure

```
app/
  main.py            FastAPI app, startup (creates tables and storage folder)
  config.py          environment-based settings
  database.py        engine and sessions (SQLite WAL mode so reads work during writes)
  models.py          Job and Certificate tables
  schemas.py         request validation and response models
  routers/jobs.py    HTTP endpoints
  services/
    job_service.py   validates recipients and creates the job
    processor.py     background worker (generation loop)
    certificate.py   PDF template (ReportLab)
tests/               pytest suite
scripts/             helper to build large sample payloads
samples/             example request body
```

## 6. Design decisions

**Background processing instead of synchronous generation.** `POST` validates rows, stores the job, returns `202` immediately, and generates PDFs with FastAPI `BackgroundTasks`. A synchronous design would keep the HTTP connection open for the whole batch and risk timeouts. `BackgroundTasks` needs no extra infrastructure (no Redis or Celery), so the project runs with one command. Trade-off: the queue lives inside the server process, so a restart in the middle of a job leaves that job unfinished.

**Two-level validation.**
1. Request level (invalid JSON, missing `event_name`, empty list, too many recipients) returns `422` and nothing is stored.
2. Row level (bad email, missing name, duplicate email, unsupported characters) stores the row as a `FAILED` certificate with a readable reason, and all other rows still proceed.

**Failure isolation.** Each certificate is generated in its own `try/except` and committed on its own (the certificate row and the job counters in one transaction). One failure cannot affect other rows, clients see live progress, and if the whole worker crashes the job is marked `FAILED` with an `error` instead of staying `PROCESSING` forever. The worker only handles `PENDING` rows, so running it again never double counts.

**Data model.** `jobs` (1) to `certificates` (many). There is one certificate row per submitted recipient, valid or not, which gives a full audit trail. Counters are stored on the job so status checks stay cheap for large jobs, and a `(job_id, status)` index supports filtering.

**File storage.** PDFs are written to `storage/<job_id>/<certificate_id>.pdf` (temp file, then rename), and only the path is stored in the database. File names use generated IDs, never user input, so there is no path traversal; download names are sanitised separately.

**Certificate template.** One fixed landscape A4 design drawn with ReportLab (pure Python, no system dependencies). Long names shrink to fit and long event names wrap.

**Duplicate emails** within one job are rejected (first occurrence wins) to avoid issuing the same certificate twice by accident.

**Alternatives considered:** Celery + Redis (more robust, but needs extra services for a small project), WeasyPrint/HTML templates (nicer styling, but heavy system dependencies), and synchronous generation (simplest, but poor for large batches).

## 7. Known limitations

- The template uses the built-in Helvetica font, so only Latin characters (including accents such as "José") are supported. Other scripts such as Devanagari or CJK are rejected with a clear error instead of being printed as garbage.
- Background jobs are not durable across server restarts and run one certificate at a time in the same process.
- No authentication (out of scope for this exercise).
- Tables are created with `create_all`; there are no migrations.

## 8. Learnings and future scope

**Learnings**
- Designing a bulk API so partial failure is a normal outcome, not an error.
- Committing progress per item so status is accurate at any moment.
- Testing background work deterministically (FastAPI's `TestClient` finishes background tasks before returning) and injecting failures with `monkeypatch`.
- Catching silent failures: the PDF library produced garbage for non-Latin names without raising, so validation had to be added.

**Future scope**
- Celery/RQ with Redis for durability, retries and horizontal scaling, or resuming unfinished jobs on startup
- Embed a Unicode font (for example Noto) with text shaping for Indic and CJK names
- Alembic migrations and PostgreSQL through docker-compose
- Authentication or API keys, rate limiting, per-client job ownership
- Email delivery of certificates and a QR code or verification URL on each certificate
- Webhook callback when a job finishes instead of polling
