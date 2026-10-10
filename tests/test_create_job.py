"""Creating a generation job."""


def test_create_job_returns_202_and_job_details(client, make_payload):
    resp = client.post("/api/v1/jobs", json=make_payload(3))
    assert resp.status_code == 202
    body = resp.json()
    assert body["id"]
    assert body["total"] == 3
    assert body["event_name"] == "Python Bootcamp"
    assert body["status"] == "PENDING"  # response is sent before the worker starts
    assert body["certificates_url"].endswith(f"/{body['id']}/certificates")


def test_job_is_processed_in_background(client, submit):
    job = submit(4)
    final = client.get(f"/api/v1/jobs/{job['id']}").json()
    assert final["status"] == "COMPLETED"
    assert final["succeeded"] == 4 and final["failed"] == 0
    assert final["completed_at"] is not None


def test_issue_date_defaults_to_today_and_can_be_set(client, make_payload):
    assert client.post("/api/v1/jobs", json=make_payload(1)).json()["issue_date"]
    body = client.post("/api/v1/jobs", json=make_payload(1, issue_date="2026-01-31")).json()
    assert body["issue_date"] == "2026-01-31"


def test_unknown_job_returns_404(client):
    assert client.get("/api/v1/jobs/doesnotexist").status_code == 404
