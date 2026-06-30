from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import gzip
import shutil
import tarfile
import urllib.parse
import urllib.request
import zipfile

from paper_harvest.core.article_layout import ArticleLayout
from paper_harvest.core.models import ParsedSource


@dataclass(frozen=True)
class ArxivSourceResult:
    arxiv_id: str
    tex_dir: Path
    source_url: str
    archive_path: Path
    extracted_dir: Path


def fetch_arxiv_source(
    source: ParsedSource,
    layout: ArticleLayout,
    *,
    timeout: int = 120,
) -> ArxivSourceResult:
    if source.source_kind != "arxiv":
        raise ValueError("tex collection only supports arXiv sources")

    source_url = source.tex_url or ""
    if not source_url:
        raise ValueError("parsed source does not contain a tex url")

    arxiv_id = source.metadata.get("arxiv_id", layout.article_id)
    tex_dir = layout.tex_dir
    tex_dir.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "paper-harvest/0.2"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        archive_name = resolve_archive_name(
            response.headers,
            response.geturl(),
            arxiv_id,
        )
        archive_path = tex_dir / archive_name
        temp_path = archive_path.with_suffix(f"{archive_path.suffix}.part")
        with temp_path.open("wb") as file:
            shutil.copyfileobj(response, file)
        temp_path.replace(archive_path)

    extracted_dir = tex_dir / "source"
    if extracted_dir.exists():
        shutil.rmtree(extracted_dir)
    extracted_dir.mkdir(parents=True, exist_ok=True)
    extract_source_archive(archive_path, extracted_dir, arxiv_id)

    return ArxivSourceResult(
        arxiv_id=arxiv_id,
        tex_dir=tex_dir,
        source_url=source_url,
        archive_path=archive_path,
        extracted_dir=extracted_dir,
    )


def resolve_archive_name(
    headers: urllib.request.HTTPMessage,
    final_url: str,
    arxiv_id: str,
) -> str:
    content_disposition = headers.get("Content-Disposition", "")
    marker = 'filename="'
    if marker in content_disposition:
        return content_disposition.split(marker, 1)[1].split('"', 1)[0]

    path_name = Path(urllib.parse.urlparse(final_url).path).name
    if path_name and "." in path_name:
        return path_name

    content_type = headers.get_content_type().lower()
    if content_type in {"application/gzip", "application/x-gzip"}:
        return f"arXiv-{arxiv_id}.tar.gz"
    if content_type == "application/zip":
        return f"arXiv-{arxiv_id}.zip"
    return f"arXiv-{arxiv_id}.src"


def extract_source_archive(
    archive_path: Path, extracted_dir: Path, arxiv_id: str
) -> None:
    if tarfile.is_tarfile(archive_path):
        with tarfile.open(archive_path, "r:*") as archive:
            extract_tar_safely(archive, extracted_dir)
        return

    if zipfile.is_zipfile(archive_path):
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(extracted_dir)
        return

    if archive_path.suffix == ".gz":
        target_name = derive_gzip_target_name(archive_path, arxiv_id)
        with gzip.open(archive_path, "rb") as source_file:
            with (extracted_dir / target_name).open("wb") as target_file:
                shutil.copyfileobj(source_file, target_file)
        return

    shutil.copy2(archive_path, extracted_dir / archive_path.name)


def extract_tar_safely(archive: tarfile.TarFile, extracted_dir: Path) -> None:
    base_dir = extracted_dir.resolve()
    for member in archive.getmembers():
        member_path = (base_dir / member.name).resolve()
        try:
            member_path.relative_to(base_dir)
        except ValueError as error:
            raise ValueError(f"unsafe archive member: {member.name}") from error
    archive.extractall(extracted_dir)


def derive_gzip_target_name(archive_path: Path, arxiv_id: str) -> str:
    stem = archive_path.stem
    if stem.endswith(".tar") or "." in stem:
        return stem
    return f"{arxiv_id.replace('.', '_')}.tex"
