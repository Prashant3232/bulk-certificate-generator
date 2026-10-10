"""One failing certificate must not stop the others."""
from app.services import certificate as cert_module


def _fail_for(names):
    real = cert_module.render_certificate

    def fake(**kwargs):
        if kwargs["recipient_name"] in names:
            raise RuntimeError("renderer exploded")
        return real(**kwargs)

    return fake


def test_single_generation_failure_does_not_block_others(client, make_payload, monkeypatch):
    monkeypatch.setattr("app.services.certificate.render_certificate", _fail_for({"Person 2"}))
    job_id = client.post("/api/v1/jobs", json=make_payload(4)).json()["id"]

    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "COMPLETED_WITH_ERRORS"
    assert (job["succeeded"], job["failed"], job["pending"]) == (3, 1, 0)

    assert len(job["failures"]) == 1
    failure = job["failures"][0]
    assert failure["recipient_name"] == "Person 2"
    assert failure["row_index"] == 2
    assert "renderer exploded" in failure["error"]

    items = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"]
    assert [i["status"] for i in items] == ["SUCCESS", "FAILED", "SUCCESS", "SUCCESS"]


def test_all_generations_failing_marks_job_failed(client, make_payload, monkeypatch):
    monkeypatch.setattr("app.services.certificate.render_certificate", _fail_for({"Person 1", "Person 2"}))
    job_id = client.post("/api/v1/jobs", json=make_payload(2)).json()["id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "FAILED"
    assert job["failed"] == 2


def test_failed_certificate_is_not_downloadable(client, make_payload, monkeypatch):
    monkeypatch.setattr("app.services.certificate.render_certificate", _fail_for({"Person 1"}))
    job_id = client.post("/api/v1/jobs", json=make_payload(2)).json()["id"]
    bad = client.get(f"/api/v1/jobs/{job_id}/certificates", params={"status": "FAILED"}).json()["items"][0]
    assert bad["download_url"] is None
    assert client.get(f"/api/v1/jobs/{job_id}/certificates/{bad['id']}/download").status_code == 409


def test_unexpected_job_crash_does_not_leave_job_processing(client, make_payload, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db went away")

    monkeypatch.setattr("app.services.processor._generate_one", boom)
    job_id = client.post("/api/v1/jobs", json=make_payload(2)).json()["id"]
    job = client.get(f"/api/v1/jobs/{job_id}").json()
    assert job["status"] == "FAILED"
    assert "db went away" in job["error"]
