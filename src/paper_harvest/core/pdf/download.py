from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import urllib.request

from paper_harvest.core.article_layout import ArticleLayout
from paper_harvest.core.models import ParsedSource


@dataclass(frozen=True)
class PdfDownloadResult:
    article_id: str
    article_dir: Path
    pdf_dir: Path
    pdf_path: Path
    final_url: str


def download_pdf(
    source: ParsedSource,
    layout: ArticleLayout,
    *,
    timeout: int = 120,
) -> PdfDownloadResult:
    pdf_dir = layout.pdf_dir
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"{layout.article_id}.pdf"
    if not source.pdf_url:
        raise ValueError("parsed source does not contain a pdf url")

    request = urllib.request.Request(
        source.pdf_url,
        headers={"User-Agent": "paper-harvest/0.2"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        content_type = response.headers.get_content_type().lower()
        temp_path = pdf_path.with_suffix(".pdf.part")
        with temp_path.open("wb") as file:
            shutil.copyfileobj(response, file)
        if content_type != "application/pdf" and not looks_like_pdf(temp_path):
            temp_path.unlink(missing_ok=True)
            raise ValueError(f"URL does not look like a PDF response: {source.pdf_url}")
        temp_path.replace(pdf_path)

    return PdfDownloadResult(
        article_id=layout.article_id,
        article_dir=layout.article_dir,
        pdf_dir=pdf_dir,
        pdf_path=pdf_path,
        final_url=final_url,
    )


def looks_like_pdf(path: Path) -> bool:
    with path.open("rb") as handle:
        return handle.read(5) == b"%PDF-"
