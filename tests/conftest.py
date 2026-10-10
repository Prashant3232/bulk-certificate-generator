"""Test setup: an isolated SQLite DB + storage dir per test session, clean tables per test."""
import os
import shutil
import tempfile

_TMP = tempfile.mkdtemp(prefix="certgen-tests-")
# Must be set BEFORE the app is imported (settings are read at import time).
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["CERT_STORAGE_DIR"] = f"{_TMP}/storage"
os.environ["MAX_RECIPIENTS_PER_JOB"] = "50"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    shutil.rmtree(config.STORAGE_DIR, ignore_errors=True)
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture
def client():
    # Background tasks run to completion before TestClient returns, so tests are deterministic.
    return TestClient(app)


@pytest.fixture
def make_payload():
    def _make(n=3, **overrides):
        body = {
            "event_name": "Python Bootcamp",
            "issuer": "Acme Academy",
            "recipients": [{"name": f"Person {i}", "email": f"p{i}@example.com"} for i in range(1, n + 1)],
        }
        body.update(overrides)
        return body

    return _make


@pytest.fixture
def submit(client, make_payload):
    def _submit(n=3, **overrides):
        resp = client.post("/api/v1/jobs", json=make_payload(n, **overrides))
        assert resp.status_code == 202, resp.text
        return resp.json()

    return _submit
