"""Creating jobs: validate every recipient row and persist the job + certificate rows."""
from datetime import date

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import Certificate, CertificateStatus, Job, JobStatus, new_id, utcnow
from app.schemas import JobCreate, RecipientIn


def format_validation_error(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        field = ".".join(str(p) for p in err["loc"]) or "recipient"
        parts.append(f"{field}: {err['msg']}")
    return "Invalid recipient data - " + "; ".join(parts)


def _display(value, limit: int = 255) -> str | None:
    """Best-effort text of a raw value so failed rows are still identifiable."""
    return str(value)[:limit] if isinstance(value, (str, int, float)) else None


def final_job_status(job: Job) -> JobStatus:
    if job.failed == 0:
        return JobStatus.COMPLETED
    if job.succeeded == 0:
        return JobStatus.FAILED
    return JobStatus.COMPLETED_WITH_ERRORS


def create_job(db: Session, payload: JobCreate) -> Job:
    """Validate each recipient and store the job.

    * Valid rows   -> Certificate(status=PENDING), picked up by the background worker.
    * Invalid rows -> Certificate(status=FAILED, error=<reason>) immediately.
      They never block the valid rows.
    * Duplicate e-mails inside one job are rejected (the first occurrence wins).
    """
    job = Job(
        id=new_id(),
        event_name=payload.event_name,
        issuer=payload.issuer,
        issue_date=payload.issue_date or date.today(),
        status=JobStatus.PENDING.value,
        total=len(payload.recipients),
        succeeded=0,
        failed=0,
    )

    seen_emails: dict[str, int] = {}
    rows: list[Certificate] = []

    for index, raw in enumerate(payload.recipients, start=1):
        cert = Certificate(id=new_id(), job_id=job.id, row_index=index)
        if isinstance(raw, dict):
            cert.recipient_name = _display(raw.get("name"))
            cert.recipient_email = _display(raw.get("email"))

        error: str | None = None
        try:
            recipient = RecipientIn.model_validate(raw)
            cert.recipient_name = recipient.name
            cert.recipient_email = str(recipient.email)
            cert.achievement = recipient.achievement

            key = cert.recipient_email.lower()
            if key in seen_emails:
                error = f"Duplicate email in this job (first used in row {seen_emails[key]})"
            else:
                seen_emails[key] = index
        except ValidationError as exc:
            error = format_validation_error(exc)

        if error:
            cert.status = CertificateStatus.FAILED.value
            cert.error = error
            job.failed += 1
        rows.append(cert)

    # Nothing valid -> no work for the worker, close the job right away.
    if job.failed == job.total:
        job.status = final_job_status(job).value
        job.completed_at = utcnow()

    db.add(job)
    db.add_all(rows)
    db.commit()
    db.refresh(job)
    return job
