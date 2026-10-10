"""Background worker: generates the PDF for every PENDING certificate of a job.

Design notes
* Every certificate is generated inside its own try/except and committed on its own, so a
  failure affects only that row and clients can watch progress move forward.
* The worker opens its own DB session - it runs after the HTTP response was sent.
* The function is idempotent/resumable: it only looks at rows still PENDING.
"""
import logging
import os
from pathlib import Path

from sqlalchemy import select

from app import config
from app.database import SessionLocal
from app.models import Certificate, CertificateStatus, Job, JobStatus, utcnow
from app.services import certificate  # module import so tests can monkeypatch render_certificate
from app.services.job_service import final_job_status

logger = logging.getLogger(__name__)


def certificate_path(job_id: str, certificate_id: str) -> Path:
    return config.STORAGE_DIR / job_id / f"{certificate_id}.pdf"


def _write_atomically(path: Path, data: bytes) -> None:
    """Write to a temp file then rename, so a crash never leaves a half-written PDF."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _generate_one(db, job: Job, cert: Certificate) -> None:
    try:
        pdf = certificate.render_certificate(
            recipient_name=cert.recipient_name or "",
            event_name=job.event_name,
            issuer=job.issuer,
            issue_date=job.issue_date,
            certificate_id=cert.id,
            achievement=cert.achievement,
        )
        path = certificate_path(job.id, cert.id)
        _write_atomically(path, pdf)
        cert.status = CertificateStatus.SUCCESS.value
        cert.file_path = str(path)
        cert.generated_at = utcnow()
        job.succeeded += 1
    except Exception as exc:  # noqa: BLE001 - isolate ANY per-certificate failure
        logger.exception("Certificate %s (job %s) failed", cert.id, job.id)
        cert.status = CertificateStatus.FAILED.value
        cert.error = f"Generation failed: {exc}"[:1000]
        job.failed += 1
    db.commit()  # certificate row + job counters are saved atomically


def process_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status = JobStatus.PROCESSING.value
        job.started_at = job.started_at or utcnow()
        db.commit()

        pending = db.scalars(
            select(Certificate)
            .where(Certificate.job_id == job_id, Certificate.status == CertificateStatus.PENDING.value)
            .order_by(Certificate.row_index)
        ).all()
        for cert in pending:
            _generate_one(db, job, cert)

        job.status = final_job_status(job).value
        job.completed_at = utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - unexpected crash: never leave a job stuck in PROCESSING
        logger.exception("Job %s crashed", job_id)
        db.rollback()
        job = db.get(Job, job_id)
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.error = f"Job crashed: {exc}"[:1000]
            job.completed_at = utcnow()
            db.commit()
    finally:
        db.close()
