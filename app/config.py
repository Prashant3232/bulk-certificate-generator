"""Application settings, read from environment variables with sane defaults."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'certgen.db'}")
STORAGE_DIR: Path = Path(os.getenv("CERT_STORAGE_DIR", str(BASE_DIR / "storage")))
# Upper bound on recipients in one request. Protects the server from huge payloads.
MAX_RECIPIENTS_PER_JOB: int = int(os.getenv("MAX_RECIPIENTS_PER_JOB", "1000"))
API_PREFIX: str = "/api/v1/jobs"
