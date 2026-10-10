"""Retrieving generated certificates (list, single PDF, ZIP)."""
import io
import zipfile

from app.services import certificate as cert_module


def test_list_certificates_with_pagination_and_filter(client, submit):
    job = submit(5)
    base = f"/api/v1/jobs/{job['id']}/certificates"

    page = client.get(base, params={"limit": 2, "offset": 1}).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    assert [i["row_index"] for i in page["items"]] == [2, 3]

    assert client.get(base, params={"status": "SUCCESS"}).json()["total"] == 5
    assert client.get(base, params={"status": "FAILED"}).json()["total"] == 0
    assert client.get(base, params={"status": "NOPE"}).status_code == 422


def test_download_single_certificate(client, submit):
    job = submit(2)
    item = client.get(f"/api/v1/jobs/{job['id']}/certificates").json()["items"][0]
    assert item["download_url"]

    resp = client.get(item["download_url"])
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert "Person_1_certificate.pdf" in resp.headers["content-disposition"]


def test_download_unknown_certificate_404(client, submit):
    job = submit(1)
    assert client.get(f"/api/v1/jobs/{job['id']}/certificates/nope/download").status_code == 404


def test_certificate_cannot_be_downloaded_through_another_job(client, submit):
    a, b = submit(1), submit(1)
    cert = client.get(f"/api/v1/jobs/{a['id']}/certificates").json()["items"][0]
    assert client.get(f"/api/v1/jobs/{b['id']}/certificates/{cert['id']}/download").status_code == 404


def test_download_zip_contains_only_successful_certificates(client, make_payload, monkeypatch):
    real = cert_module.render_certificate

    def fake(**kwargs):
        if kwargs["recipient_name"] == "Person 2":
            raise RuntimeError("nope")
        return real(**kwargs)

    monkeypatch.setattr("app.services.certificate.render_certificate", fake)
    job_id = client.post("/api/v1/jobs", json=make_payload(3)).json()["id"]

    resp = client.get(f"/api/v1/jobs/{job_id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert zf.namelist() == ["0001_Person_1.pdf", "0003_Person_3.pdf"]
        assert all(zf.read(n).startswith(b"%PDF") for n in zf.namelist())


def test_zip_not_available_until_job_finished(client, make_payload, monkeypatch):
    monkeypatch.setattr("app.routers.jobs.process_job", lambda job_id: None)
    job_id = client.post("/api/v1/jobs", json=make_payload(2)).json()["id"]
    assert client.get(f"/api/v1/jobs/{job_id}/download").status_code == 409


def test_zip_404_when_nothing_was_generated(client, make_payload):
    body = make_payload(0, recipients=[{"name": "", "email": "bad"}])
    job_id = client.post("/api/v1/jobs", json=body).json()["id"]
    assert client.get(f"/api/v1/jobs/{job_id}/download").status_code == 404
