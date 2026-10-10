"""Input validation: request-level (422) and recipient-level (recorded as failed rows)."""
import pytest


def test_empty_recipient_list_rejected(client, make_payload):
    assert client.post("/api/v1/jobs", json=make_payload(1, recipients=[])).status_code == 422


def test_missing_event_name_rejected(client, make_payload):
    body = make_payload(1)
    del body["event_name"]
    assert client.post("/api/v1/jobs", json=body).status_code == 422


def test_too_many_recipients_rejected(client, make_payload):
    # MAX_RECIPIENTS_PER_JOB is 50 in tests
    assert client.post("/api/v1/jobs", json=make_payload(51)).status_code == 422


def test_bad_issue_date_rejected(client, make_payload):
    assert client.post("/api/v1/jobs", json=make_payload(1, issue_date="not-a-date")).status_code == 422


@pytest.mark.parametrize(
    "bad_recipient, expected_in_error",
    [
        ({"name": "No Email"}, "email"),
        ({"email": "noname@example.com"}, "name"),
        ({"name": "Bad Email", "email": "not-an-email"}, "email"),
        ({"name": "   ", "email": "blank@example.com"}, "name"),
        ({"name": "x" * 101, "email": "long@example.com"}, "name"),
        ({"name": "राहुल", "email": "hindi@example.com"}, "name"),
        ("just a string", "recipient"),
        (None, "recipient"),
    ],
)
def test_invalid_recipient_is_recorded_as_failure_not_request_error(client, make_payload, bad_recipient, expected_in_error):
    body = make_payload(1)
    body["recipients"].append(bad_recipient)
    resp = client.post("/api/v1/jobs", json=body)
    assert resp.status_code == 202  # the bulk request itself is accepted

    job = client.get(f"/api/v1/jobs/{resp.json()['id']}").json()
    assert job["status"] == "COMPLETED_WITH_ERRORS"
    assert job["succeeded"] == 1  # the valid recipient still got a certificate
    assert job["failed"] == 1
    failure = job["failures"][0]
    assert failure["row_index"] == 2
    assert expected_in_error in failure["error"]


def test_duplicate_email_in_same_job_is_rejected_case_insensitively(client, make_payload):
    body = make_payload(0, recipients=[
        {"name": "First", "email": "same@example.com"},
        {"name": "Second", "email": "SAME@example.com"},
    ])
    job = client.get(f"/api/v1/jobs/{client.post('/api/v1/jobs', json=body).json()['id']}").json()
    assert (job["succeeded"], job["failed"]) == (1, 1)
    assert "Duplicate" in job["failures"][0]["error"]


def test_all_invalid_recipients_job_fails_immediately(client, make_payload):
    body = make_payload(0, recipients=[{"name": "", "email": "x"}, {"foo": "bar"}])
    resp = client.post("/api/v1/jobs", json=body)
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "FAILED"
    assert data["failed"] == 2 and data["succeeded"] == 0
    assert data["completed_at"] is not None


def test_names_are_whitespace_trimmed(client, make_payload):
    body = make_payload(0, recipients=[{"name": "  Asha Rao  ", "email": "a@example.com"}])
    job_id = client.post("/api/v1/jobs", json=body).json()["id"]
    items = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"]
    assert items[0]["recipient_name"] == "Asha Rao"


def test_accented_latin_names_are_supported(client, make_payload):
    body = make_payload(0, recipients=[{"name": "José Peña", "email": "j@example.com"}])
    job = client.get(f"/api/v1/jobs/{client.post('/api/v1/jobs', json=body).json()['id']}").json()
    assert job["status"] == "COMPLETED"


def test_unrenderable_event_name_rejected(client, make_payload):
    assert client.post("/api/v1/jobs", json=make_payload(1, event_name="कार्यशाला")).status_code == 422
