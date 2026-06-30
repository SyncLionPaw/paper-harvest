from __future__ import annotations

import re
import urllib.parse

from paper_harvest.core.article_layout import normalize_article_id
from paper_harvest.core.models import ParsedSource


ARXIV_HOSTS = {"arxiv.org", "www.arxiv.org"}
ARXIV_ID_PATTERN = re.compile(
    r"(?P<id>(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)",
    re.IGNORECASE,
)


def parse_source(value: str) -> ParsedSource:
    raw_input = value.strip()
    if not raw_input:
        raise ValueError("source is empty")

    if not is_url(raw_input):
        raise ValueError("only arXiv URLs are supported")

    return parse_arxiv_source(raw_input)


def parse_arxiv_source(value: str) -> ParsedSource:
    normalized_input = normalize_url(value)
    parsed = urllib.parse.urlparse(normalized_input)
    if parsed.netloc.lower() not in ARXIV_HOSTS:
        raise ValueError("only arXiv links are supported")

    arxiv_id = parse_arxiv_id(normalized_input)
    canonical_arxiv_id = strip_arxiv_version(arxiv_id)
    article_id = normalize_article_id(canonical_arxiv_id.replace(".", "_"))

    return ParsedSource(
        raw_input=value,
        normalized_input=normalized_input,
        input_kind="url",
        source_kind="arxiv",
        article_id_candidate=article_id,
        pdf_url=f"https://arxiv.org/pdf/{canonical_arxiv_id}.pdf",
        tex_url=f"https://arxiv.org/src/{canonical_arxiv_id}",
        metadata={
            "arxiv_id": canonical_arxiv_id,
            "arxiv_id_with_version": arxiv_id,
        },
    )


def is_url(value: str) -> bool:
    parsed = urllib.parse.urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"unsupported url: {url}")
    return urllib.parse.urlunparse(parsed._replace(fragment=""))


def parse_arxiv_id(value: str) -> str:
    match = ARXIV_ID_PATTERN.search(value)
    if not match:
        raise ValueError(f"cannot parse arXiv id from input: {value}")
    return match.group("id")


def strip_arxiv_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id, flags=re.IGNORECASE)
