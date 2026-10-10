"""PDF rendering from the single predefined certificate template (ReportLab)."""
import re
from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = landscape(A4)
GOLD = colors.HexColor("#B8860B")
NAVY = colors.HexColor("#1F3A5F")
GREY = colors.HexColor("#555555")


def _fit_size(text: str, font: str, max_size: int, max_width: float, min_size: int = 8) -> int:
    """Largest font size (<= max_size) at which `text` fits on one line."""
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def _centered_wrapped(c: canvas.Canvas, text: str, y: float, font: str, size: int, max_width: float) -> float:
    """Draw wrapped, centered text starting at y. Returns the y below the last line."""
    leading = size * 1.3
    for line in simpleSplit(text, font, size, max_width):
        c.setFont(font, size)
        c.drawCentredString(PAGE_W / 2, y, line)
        y -= leading
    return y


def render_certificate(
    *,
    recipient_name: str,
    event_name: str,
    issuer: str,
    issue_date: date,
    certificate_id: str,
    achievement: str | None = None,
) -> bytes:
    """Render one certificate and return the PDF bytes.

    The template is fixed: only the recipient-specific values change.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Certificate - {recipient_name}")
    c.setAuthor(issuer or "Certificate Generator")

    # Decorative double border
    c.setStrokeColor(GOLD)
    c.setLineWidth(6)
    c.rect(25, 25, PAGE_W - 50, PAGE_H - 50)
    c.setLineWidth(1.5)
    c.rect(38, 38, PAGE_W - 76, PAGE_H - 76)

    content_w = PAGE_W - 160

    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 46)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 125, "CERTIFICATE")
    c.setFillColor(GOLD)
    c.setFont("Helvetica", 18)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 155, "OF COMPLETION")

    c.setFillColor(GREY)
    c.setFont("Helvetica-Oblique", 14)
    c.drawCentredString(PAGE_W / 2, PAGE_H - 205, "This certificate is proudly presented to")

    # Recipient name: shrink to fit so long names never overflow the page.
    name_font = "Helvetica-Bold"
    name_size = _fit_size(recipient_name, name_font, 40, content_w)
    c.setFillColor(NAVY)
    c.setFont(name_font, name_size)
    name_y = PAGE_H - 265
    c.drawCentredString(PAGE_W / 2, name_y, recipient_name)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1)
    c.line(PAGE_W / 2 - 220, name_y - 10, PAGE_W / 2 + 220, name_y - 10)

    c.setFillColor(GREY)
    c.setFont("Helvetica-Oblique", 14)
    c.drawCentredString(PAGE_W / 2, name_y - 45, "for successfully completing")

    c.setFillColor(NAVY)
    y = _centered_wrapped(c, event_name, name_y - 80, "Helvetica-Bold", 24, content_w)

    if achievement:
        c.setFillColor(GOLD)
        y = _centered_wrapped(c, achievement, y - 8, "Helvetica-Oblique", 16, content_w)

    # Footer: date (left), issuer (right), certificate id (center)
    base_y = 95
    c.setStrokeColor(GREY)
    c.setLineWidth(0.8)
    c.line(90, base_y + 18, 270, base_y + 18)
    c.line(PAGE_W - 270, base_y + 18, PAGE_W - 90, base_y + 18)
    c.setFillColor(GREY)
    c.setFont("Helvetica", 12)
    c.drawCentredString(180, base_y, f"Date: {issue_date.strftime('%d %B %Y')}")
    c.drawCentredString(PAGE_W - 180, base_y, issuer or "Authorized Signatory")
    c.setFont("Helvetica", 8)
    c.drawCentredString(PAGE_W / 2, 52, f"Certificate ID: {certificate_id}")

    c.showPage()
    c.save()
    return buf.getvalue()


def safe_filename(name: str | None, fallback: str = "certificate") -> str:
    """Filesystem/ZIP-safe slug derived from a recipient name."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name or "").strip("_")
    return slug[:60] or fallback
