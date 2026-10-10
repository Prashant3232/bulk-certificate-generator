"""Certificate generation (PDF rendering and files on disk)."""
from datetime import date
from pathlib import Path

from app.models import Certificate
from app.database import SessionLocal
from app.services.certificate import render_certificate, safe_filename


def _render(**kw):
    args = dict(recipient_name="Asha Rao", event_name="Python Bootcamp", issuer="Acme",
                issue_date=date(2026, 10, 7), certificate_id="abc123")
    args.update(kw)
    return render_certificate(**args)


def test_render_returns_a_valid_pdf():
    pdf = _render()
    assert pdf.startswith(b"%PDF")
    assert pdf.rstrip().endswith(b"%%EOF")


def test_render_handles_very_long_values_without_error():
    pdf = _render(recipient_name="N" * 100, event_name="Long event " * 20, achievement="Merit " * 20)
    assert pdf.startswith(b"%PDF")


def test_render_includes_optional_achievement():
    assert len(_render(achievement="Distinction")) != len(_render())


def test_safe_filename():
    assert safe_filename("Asha Rao") == "Asha_Rao"
    assert safe_filename("../../etc/passwd") == "etc_passwd"
    assert safe_filename("???") == "certificate"
    assert safe_filename(None) == "certificate"


def test_job_writes_one_pdf_per_valid_recipient(submit):
    job = submit(5)
    with SessionLocal() as db:
        certs = db.query(Certificate).filter_by(job_id=job["id"]).all()
    assert len(certs) == 5
    for cert in certs:
        assert cert.status == "SUCCESS"
        path = Path(cert.file_path)
        assert path.is_file()
        assert path.read_bytes().startswith(b"%PDF")
