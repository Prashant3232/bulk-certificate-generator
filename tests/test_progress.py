"""Job status / progress tracking."""
from app.database import SessionLocal
from app.services.processor import process_job


def test_status_before_processing_shows_pending_work(client, make_payload, monkeypatch):
    # Disable the background worker to observe the intermediate state.
    monkeypatch.setattr("app.routers.jobs.process_job", lambda job_id: None)
    job = client.post("/api/v1/jobs", json=make_payload(4)).json()

    status = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert status["status"] == "PENDING"
    assert status["total"] == 4
    assert status["pending"] == 4
    assert status["progress_percent"] == 0.0


def test_progress_reaches_100_percent_after_processing(client, make_payload, monkeypatch):
    monkeypatch.setattr("app.routers.jobs.process_job", lambda job_id: None)
    job = client.post("/api/v1/jobs", json=make_payload(4)).json()

    process_job(job["id"])  # run the worker manually

    status = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert status["status"] == "COMPLETED"
    assert status["succeeded"] == 4
    assert status["pending"] == 0
    assert status["progress_percent"] == 100.0
    assert status["started_at"] and status["completed_at"]


def test_progress_is_visible_while_processing(client, make_payload, monkeypatch):
    """Counters are committed per certificate, so a poll in the middle sees partial progress."""
    monkeypatch.setattr("app.routers.jobs.process_job", lambda job_id: None)
    job = client.post("/api/v1/jobs", json=make_payload(3)).json()

    from app.services import certificate as cert_module
    real = cert_module.render_certificate
    seen = []

    def spy(**kwargs):
        seen.append(client.get(f"/api/v1/jobs/{job['id']}").json())
        return real(**kwargs)

    monkeypatch.setattr("app.services.certificate.render_certificate", spy)
    process_job(job["id"])

    assert [s["succeeded"] for s in seen] == [0, 1, 2]
    assert all(s["status"] == "PROCESSING" for s in seen)


def test_process_job_is_safe_to_run_twice(client, make_payload, monkeypatch):
    monkeypatch.setattr("app.routers.jobs.process_job", lambda job_id: None)
    job = client.post("/api/v1/jobs", json=make_payload(2)).json()
    process_job(job["id"])
    process_job(job["id"])  # nothing PENDING left -> counters must not double
    status = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert status["succeeded"] == 2 and status["total"] == 2
