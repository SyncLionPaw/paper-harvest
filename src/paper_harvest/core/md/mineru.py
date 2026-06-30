from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paper_harvest.core.article_layout import ArticleLayout, to_public_path
from paper_harvest.core.models import ParsedSource


PRECISION_API_BASE = "https://mineru.net/api/v4"
LIGHTWEIGHT_API_BASE = "https://mineru.net/api/v1/agent"
LIGHTWEIGHT_FILE_SIZE_LIMIT = 10 * 1024 * 1024
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HTML_IMAGE_PATTERN = re.compile(r'<img\b[^>]*\bsrc="([^"]+)"[^>]*>', re.IGNORECASE)


@dataclass(frozen=True)
class MarkdownExtractResult:
    article_dir: Path
    md_dir: Path
    markdown_path: Path
    metadata_path: Path
    provider: str
    zip_path: Path | None = None


class MineruError(RuntimeError):
    def __init__(self, message: str, *, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code


def extract_markdown(
    pdf_path: Path,
    layout: ArticleLayout,
    source: ParsedSource,
    *,
    token: str = "",
    force: bool = False,
    poll_interval: int = 5,
    timeout: int = 1800,
) -> MarkdownExtractResult:
    resolved_token = load_token(token)
    prepare_output_dir(layout.md_dir, force)

    if resolved_token:
        return extract_markdown_with_precision_api(
            pdf_path,
            layout,
            source,
            token=resolved_token,
            poll_interval=poll_interval,
            timeout=timeout,
        )

    return extract_markdown_with_lightweight_api(
        pdf_path,
        layout,
        source,
        poll_interval=poll_interval,
        timeout=timeout,
    )


def get_default_token_paths() -> list[Path]:
    current_dir = Path.cwd().resolve()
    return [
        current_dir / ".mineru_token",
        Path.home() / ".mineru_token",
        Path.home() / ".config" / "mineru" / "token",
    ]


def load_token(explicit_token: str) -> str:
    if explicit_token.strip():
        return explicit_token.strip()

    env_token = os.environ.get("MINERU_API_TOKEN", "").strip()
    if env_token:
        return env_token

    for path in get_default_token_paths():
        if not path.exists():
            continue
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    return ""


def extract_markdown_with_precision_api(
    pdf_path: Path,
    layout: ArticleLayout,
    source: ParsedSource,
    *,
    token: str,
    poll_interval: int,
    timeout: int,
) -> MarkdownExtractResult:
    result = create_precision_task_for_local_pdf(
        pdf_path,
        token=token,
        poll_interval=poll_interval,
        timeout=timeout,
        data_id=f"{layout.article_id}_{int(time.time())}",
    )
    zip_url = result.get("full_zip_url")
    if not zip_url:
        raise MineruError("MinerU precision result does not contain full_zip_url")

    zip_path = layout.md_dir / "mineru.zip"
    download_file(zip_url, zip_path)

    with tempfile.TemporaryDirectory(prefix="mineru_precision_") as temp_dir:
        extracted_root = Path(temp_dir) / "unzipped"
        extracted_root.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(extracted_root)
        markdown_path = find_full_markdown(extracted_root)
        target_markdown = normalize_markdown(markdown_path, layout.md_dir, layout.article_id)

    metadata_path = layout.md_dir / "mineru_result.json"
    metadata_path.write_text(
        json.dumps(
            {
                "provider": "precision",
                "source": source.to_dict(),
                "pdf_path": to_public_path(pdf_path, layout.target_dir),
                "result": result,
                "zip_path": to_public_path(zip_path, layout.target_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return MarkdownExtractResult(
        article_dir=layout.article_dir,
        md_dir=layout.md_dir,
        markdown_path=target_markdown,
        metadata_path=metadata_path,
        provider="precision",
        zip_path=zip_path,
    )


def extract_markdown_with_lightweight_api(
    pdf_path: Path,
    layout: ArticleLayout,
    source: ParsedSource,
    *,
    poll_interval: int,
    timeout: int,
) -> MarkdownExtractResult:
    file_size = pdf_path.stat().st_size
    if file_size > LIGHTWEIGHT_FILE_SIZE_LIMIT:
        raise MineruError(
            "lightweight MinerU API only supports files up to 10MB",
            error_code="-30001",
        )

    result = create_lightweight_task_for_local_pdf(
        pdf_path,
        poll_interval=poll_interval,
        timeout=timeout,
    )
    markdown_url = result.get("markdown_url")
    if not markdown_url:
        raise MineruError("MinerU lightweight result does not contain markdown_url")

    markdown_path = layout.md_dir / f"{layout.article_id}.md"
    download_text(markdown_url, markdown_path)

    metadata_path = layout.md_dir / "mineru_result.json"
    metadata_path.write_text(
        json.dumps(
            {
                "provider": "lightweight",
                "source": source.to_dict(),
                "pdf_path": to_public_path(pdf_path, layout.target_dir),
                "result": result,
                "markdown_url": markdown_url,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return MarkdownExtractResult(
        article_dir=layout.article_dir,
        md_dir=layout.md_dir,
        markdown_path=markdown_path,
        metadata_path=metadata_path,
        provider="lightweight",
    )


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json"}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    else:
        body = None
    if headers:
        request_headers.update(headers)

    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise MineruError(
            f"HTTP {error.code} for {url}: {error_body}",
            error_code=str(error.code),
        ) from error
    except urllib.error.URLError as error:
        raise MineruError(f"request failed for {url}: {error}") from error

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise MineruError(f"invalid JSON response from {url}: {content[:500]}") from error

    if parsed.get("code", 0) != 0:
        raise MineruError(
            f"MinerU API error at {url}: {parsed.get('msg') or parsed}",
            error_code=str(parsed.get("code")),
        )
    return parsed


def upload_file(upload_url: str, file_path: Path, timeout: int = 300) -> None:
    data = file_path.read_bytes()
    parsed = urllib.parse.urlparse(upload_url)
    if parsed.scheme not in {"http", "https"}:
        raise MineruError(f"unsupported upload url scheme: {parsed.scheme}")

    target = parsed.path or "/"
    if parsed.query:
        target = f"{target}?{parsed.query}"

    connection_cls = (
        http.client.HTTPSConnection
        if parsed.scheme == "https"
        else http.client.HTTPConnection
    )
    connection = connection_cls(parsed.netloc, timeout=timeout)
    try:
        connection.request("PUT", target, body=data, headers={"Content-Length": str(len(data))})
        response = connection.getresponse()
        response.read()
    except OSError as error:
        raise MineruError(f"upload failed: {error}") from error
    finally:
        connection.close()

    if response.status not in {200, 201}:
        raise MineruError(f"upload failed: HTTP {response.status}")


def download_file(url: str, destination: Path, timeout: int = 300) -> None:
    request = urllib.request.Request(url, headers={"Accept": "*/*"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            temp_path = destination.with_suffix(f"{destination.suffix}.part")
            with temp_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            temp_path.replace(destination)
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise MineruError(
            f"download failed: HTTP {error.code}: {error_body}",
            error_code=str(error.code),
        ) from error
    except urllib.error.URLError as error:
        raise MineruError(f"download failed: {error}") from error


def download_text(url: str, destination: Path, timeout: int = 300) -> None:
    request = urllib.request.Request(url, headers={"Accept": "text/markdown,*/*"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")
        raise MineruError(
            f"download failed: HTTP {error.code}: {error_body}",
            error_code=str(error.code),
        ) from error
    except urllib.error.URLError as error:
        raise MineruError(f"download failed: {error}") from error

    destination.write_text(content, encoding="utf-8")


def create_precision_task_for_local_pdf(
    pdf_path: Path,
    *,
    token: str,
    poll_interval: int,
    timeout: int,
    data_id: str,
) -> dict[str, Any]:
    response = request_json(
        "POST",
        f"{PRECISION_API_BASE}/file-urls/batch",
        payload={
            "files": [{"name": pdf_path.name, "data_id": data_id}],
            "model_version": "vlm",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    batch_data = response.get("data", {})
    file_urls = batch_data.get("file_urls", [])
    if not file_urls:
        raise MineruError("MinerU precision batch response does not contain file_urls")

    upload_file(file_urls[0], pdf_path)
    batch_id = batch_data.get("batch_id", "")
    if not batch_id:
        raise MineruError("MinerU precision batch response does not contain batch_id")
    return poll_precision_batch_result(
        token,
        batch_id,
        data_id=data_id,
        poll_interval=poll_interval,
        timeout=timeout,
    )


def poll_precision_batch_result(
    token: str,
    batch_id: str,
    *,
    data_id: str,
    poll_interval: int,
    timeout: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last_state = ""
    while time.time() < deadline:
        result = request_json(
            "GET",
            f"{PRECISION_API_BASE}/extract-results/batch/{batch_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        records = collect_result_records(result.get("data"))
        record = pick_matching_record(records, data_id)
        if not record:
            time.sleep(poll_interval)
            continue

        state = record.get("state", "")
        if state == "done":
            return record
        if state == "failed":
            raise MineruError(
                f"MinerU precision parse failed: {record.get('err_msg') or record}"
            )
        if state != last_state:
            last_state = state
        time.sleep(poll_interval)

    raise MineruError(f"timed out waiting for MinerU precision batch {batch_id}")


def create_lightweight_task_for_local_pdf(
    pdf_path: Path,
    *,
    poll_interval: int,
    timeout: int,
) -> dict[str, Any]:
    response = request_json(
        "POST",
        f"{LIGHTWEIGHT_API_BASE}/parse/file",
        payload={
            "name": pdf_path.name,
            "enable_formula": True,
            "enable_table": True,
        },
    )
    task_data = response.get("data", {})
    file_url = task_data.get("file_url", "")
    task_id = task_data.get("task_id", "")
    if not file_url or not task_id:
        raise MineruError("MinerU lightweight response does not contain file_url or task_id")

    upload_file(file_url, pdf_path)
    return poll_lightweight_result(
        task_id,
        poll_interval=poll_interval,
        timeout=timeout,
    )


def poll_lightweight_result(
    task_id: str,
    *,
    poll_interval: int,
    timeout: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = request_json("GET", f"{LIGHTWEIGHT_API_BASE}/parse/{task_id}")
        data = result.get("data", {})
        state = data.get("state", "")
        if state == "done":
            return data
        if state == "failed":
            raise MineruError(
                f"MinerU lightweight parse failed: {data.get('err_msg') or data}",
                error_code=str(data.get("code") or ""),
            )
        time.sleep(poll_interval)

    raise MineruError(f"timed out waiting for MinerU lightweight task {task_id}")


def collect_result_records(node: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "state" in value or "full_zip_url" in value or "task_id" in value:
                records.append(value)
            for nested in value.values():
                visit(nested)
            return
        if isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(node)
    return records


def pick_matching_record(
    records: list[dict[str, Any]], data_id: str
) -> dict[str, Any] | None:
    for record in records:
        if record.get("data_id") == data_id:
            return record
    for record in records:
        if record.get("full_zip_url") or record.get("state"):
            return record
    return None


def find_full_markdown(extracted_root: Path) -> Path:
    matches = sorted(extracted_root.rglob("full.md"))
    if matches:
        return matches[0]

    markdown_files = sorted(extracted_root.rglob("*.md"))
    if not markdown_files:
        raise MineruError("no markdown file found in MinerU zip output")
    return markdown_files[0]


def normalize_markdown(markdown_path: Path, output_dir: Path, base_name: str) -> Path:
    text = markdown_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rewritten_lines: list[str] = []
    assets_dir = output_dir / "assets"
    pending_moves: list[tuple[Path, Path]] = []
    used_names: set[str] = set()

    for index, line in enumerate(lines, start=1):
        markdown_match = MARKDOWN_IMAGE_PATTERN.search(line)
        if markdown_match:
            relative_ref = markdown_match.group(2).strip()
            parsed_ref = urllib.parse.urlparse(relative_ref)
            if parsed_ref.scheme or relative_ref.startswith("#"):
                rewritten_lines.append(line)
                continue

            source_image = (markdown_path.parent / urllib.parse.unquote(relative_ref)).resolve()
            if not source_image.exists():
                rewritten_lines.append(line)
                continue

            assets_dir.mkdir(parents=True, exist_ok=True)
            target_name = ensure_unique_name(f"image_{index:02d}", source_image.suffix.lower(), used_names)
            target_image = assets_dir / target_name
            pending_moves.append((source_image, target_image))
            rewritten_lines.append(f"![image_{index:02d}](./assets/{target_name})")
            continue

        html_match = HTML_IMAGE_PATTERN.search(line)
        if html_match:
            relative_ref = html_match.group(1).strip()
            parsed_ref = urllib.parse.urlparse(relative_ref)
            if parsed_ref.scheme or relative_ref.startswith("#"):
                rewritten_lines.append(line)
                continue

            source_image = (markdown_path.parent / urllib.parse.unquote(relative_ref)).resolve()
            if not source_image.exists():
                rewritten_lines.append(line)
                continue

            assets_dir.mkdir(parents=True, exist_ok=True)
            target_name = ensure_unique_name(f"image_{index:02d}", source_image.suffix.lower(), used_names)
            target_image = assets_dir / target_name
            pending_moves.append((source_image, target_image))
            rewritten_lines.append(line.replace(relative_ref, f"./assets/{target_name}"))
            continue

        rewritten_lines.append(line)

    for source_image, target_image in pending_moves:
        if target_image.exists():
            continue
        shutil.copy2(source_image, target_image)

    target_markdown = output_dir / f"{base_name}.md"
    target_markdown.write_text("\n".join(rewritten_lines) + "\n", encoding="utf-8")
    return target_markdown


def ensure_unique_name(file_stem: str, suffix: str, used_names: set[str]) -> str:
    candidate = f"{file_stem}{suffix}"
    serial = 2
    while candidate in used_names:
        candidate = f"{file_stem}_{serial}{suffix}"
        serial += 1
    used_names.add(candidate)
    return candidate


def prepare_output_dir(output_dir: Path, force: bool) -> None:
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        return

    if force:
        shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        return

    if any(output_dir.iterdir()):
        raise MineruError(
            f"Markdown directory already exists and is not empty: {output_dir}"
        )
