"""HTTP endpoints for bulk certificate jobs."""
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from app import config
from app.database import get_db
from app.models import Certificate, CertificateStatus, Job, JobStatus
from app.schemas import CertificateOut, CertificatePage, FailureOut, JobCreate, JobOut
from app.services import job_service
from app.services.certificate import safe_filename
from app.services.processor import process_job

router = APIRouter(prefix=config.API_PREFIX, tags=["certificate jobs"])

FINISHED = {JobStatus.COMPLETED.value, JobStatus.COMPLETED_WITH_ERRORS.value, JobStatus.FAILED.value}


# ----------------------------------------------------------------- helpers
def _get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _job_out(db: Session, job: Job) -> JobOut:
    out = JobOut.model_validate(job)
    failed_rows = db.scalars(
        select(Certificate)
        .where(Certificate.job_id == job.id, Certificate.status == CertificateStatus.FAILED.value)
        .order_by(Certificate.row_index)
    ).all()
    out.failures = [FailureOut.model_validate(c) for c in failed_rows]
    return out


# --------------------------------------------------------------- endpoints
@router.post("", response_model=JobOut, status_code=202, summary="Create a bulk certificate job")
def create_job(payload: JobCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Accepts many recipients in ONE request.

    Each recipient is validated; invalid rows are recorded as failures (with a reason) and do
    not block the rest. Valid rows are generated in the background - poll `GET /{job_id}`.
    """
    job = job_service.create_job(db, payload)
    if job.status not in FINISHED:  # at least one valid recipient -> there is work to do
        background_tasks.add_task(process_job, job.id)
    return _job_out(db, job)


@router.get("/{job_id}", response_model=JobOut, summary="Job status, progress and failures")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return _job_out(db, _get_job_or_404(db, job_id))


@router.get(
    "/{job_id}/certificates",
    response_model=CertificatePage,
    summary="List certificates of a job (paginated, filterable by status)",
)
def list_certificates(
    job_id: str,
    status: CertificateStatus | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    _get_job_or_404(db, job_id)
    where = [Certificate.job_id == job_id]
    if status is not None:
        where.append(Certificate.status == status.value)
    total = db.scalar(select(func.count()).select_from(Certificate).where(*where)) or 0
    items = db.scalars(
        select(Certificate).where(*where).order_by(Certificate.row_index).limit(limit).offset(offset)
    ).all()
    return CertificatePage(
        total=total, limit=limit, offset=offset, items=[CertificateOut.model_validate(c) for c in items]
    )


@router.get("/{job_id}/certificates/{certificate_id}/download", summary="Download one certificate (PDF)")
def download_certificate(job_id: str, certificate_id: str, db: Session = Depends(get_db)):
    _get_job_or_404(db, job_id)
    cert = db.scalar(select(Certificate).where(Certificate.id == certificate_id, Certificate.job_id == job_id))
    if cert is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if cert.status != CertificateStatus.SUCCESS.value:
        raise HTTPException(status_code=409, detail=f"Certificate is not available (status: {cert.status})")
    if not cert.file_path or not Path(cert.file_path).is_file():
        raise HTTPException(status_code=410, detail="Certificate file is missing from storage")
    return FileResponse(
        cert.file_path,
        media_type="application/pdf",
        filename=f"{safe_filename(cert.recipient_name)}_certificate.pdf",
    )


@router.get("/{job_id}/download", summary="Download all successful certificates as a ZIP")
def download_all(job_id: str, db: Session = Depends(get_db)):
    job = _get_job_or_404(db, job_id)
    if job.status not in FINISHED:
        raise HTTPException(status_code=409, detail=f"Job is still {job.status}; try again when it has finished")

    certs = db.scalars(
        select(Certificate)
        .where(Certificate.job_id == job_id, Certificate.status == CertificateStatus.SUCCESS.value)
        .order_by(Certificate.row_index)
    ).all()
    if not certs:
        raise HTTPException(status_code=404, detail="This job has no generated certificates")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_STORED) as zf:  # PDFs are already compressed
        for cert in certs:
            if cert.file_path and Path(cert.file_path).is_file():
                zf.write(cert.file_path, f"{cert.row_index:04d}_{safe_filename(cert.recipient_name)}.pdf")
    return FileResponse(
        tmp.name,
        media_type="application/zip",
        filename=f"certificates_{job_id}.zip",
        background=BackgroundTask(os.unlink, tmp.name),  # delete the temp ZIP after sending
    )
