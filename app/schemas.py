"""Pydantic schemas: request validation and API responses."""
from datetime import date, datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    computed_field,
    field_validator,
)

from app import config
from app.models import CertificateStatus, JobStatus


# ---------------------------------------------------------------- requests
def ensure_printable(value: str | None) -> str | None:
    """The template uses ReportLab's built-in Helvetica (Latin-1/WinAnsi only). Characters outside
    that set would be drawn as garbage without any error, so reject them explicitly instead."""
    if value is None:
        return value
    try:
        value.encode("cp1252")
    except UnicodeEncodeError:
        raise ValueError("contains characters the certificate font cannot render (Latin characters only)")
    return value


class RecipientIn(BaseModel):
    """One recipient. Validated per row (NOT at request level) so that one bad row
    does not reject the whole bulk request - it is recorded as a failed row instead."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    achievement: str | None = Field(default=None, max_length=200)

    @field_validator("name", "achievement")
    @classmethod
    def _printable(cls, v):
        return ensure_printable(v)


class JobCreate(BaseModel):
    """Bulk request. Only the envelope is validated strictly; each recipient is validated
    individually by the service layer."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "event_name": "Python Bootcamp 2026",
                "issuer": "Acme Academy",
                "issue_date": "2026-10-07",
                "recipients": [
                    {"name": "Asha Rao", "email": "asha@example.com"},
                    {"name": "Ravi Kumar", "email": "ravi@example.com", "achievement": "Distinction"},
                ],
            }
        },
    )

    event_name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(default="", max_length=200)
    issue_date: date | None = None  # defaults to today
    recipients: list[Any] = Field(min_length=1, max_length=config.MAX_RECIPIENTS_PER_JOB)

    @field_validator("event_name", "issuer")
    @classmethod
    def _printable(cls, v):
        return ensure_printable(v)


# --------------------------------------------------------------- responses
class FailureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    certificate_id: str = Field(validation_alias="id")
    row_index: int
    recipient_name: str | None
    recipient_email: str | None
    error: str | None


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_name: str
    issuer: str
    issue_date: date
    status: JobStatus
    total: int
    succeeded: int
    failed: int
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failures: list[FailureOut] = []

    @computed_field
    @property
    def pending(self) -> int:
        return max(self.total - self.succeeded - self.failed, 0)

    @computed_field
    @property
    def progress_percent(self) -> float:
        if self.total == 0:
            return 100.0
        return round((self.succeeded + self.failed) * 100 / self.total, 1)

    @computed_field
    @property
    def certificates_url(self) -> str:
        return f"{config.API_PREFIX}/{self.id}/certificates"

    @computed_field
    @property
    def download_all_url(self) -> str:
        return f"{config.API_PREFIX}/{self.id}/download"


class CertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    row_index: int
    recipient_name: str | None
    recipient_email: str | None
    status: CertificateStatus
    error: str | None
    generated_at: datetime | None

    @computed_field
    @property
    def download_url(self) -> str | None:
        if self.status != CertificateStatus.SUCCESS:
            return None
        return f"{config.API_PREFIX}/{self.job_id}/certificates/{self.id}/download"


class CertificatePage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[CertificateOut]
