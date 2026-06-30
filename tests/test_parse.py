import pytest

from paper_harvest.core.article_layout import build_article_layout, normalize_article_id
from paper_harvest.core.url.parse import parse_source


def test_normalize_article_id():
    assert normalize_article_id("2403.18074") == "2403_18074"
    assert normalize_article_id("  arXiv:2403.18074v2  ") == "arxiv_2403_18074v2"


def test_parse_abs_url():
    source = parse_source("https://arxiv.org/abs/2403.18074")
    assert source.source_kind == "arxiv"
    assert source.article_id_candidate == "2403_18074"
    assert source.pdf_url == "https://arxiv.org/pdf/2403.18074.pdf"
    assert source.tex_url == "https://arxiv.org/src/2403.18074"
    assert source.metadata["arxiv_id"] == "2403.18074"


def test_parse_pdf_url_strips_version():
    source = parse_source("https://arxiv.org/pdf/2403.18074v2.pdf")
    assert source.metadata["arxiv_id"] == "2403.18074"
    assert source.metadata["arxiv_id_with_version"] == "2403.18074v2"


def test_reject_non_arxiv():
    with pytest.raises(ValueError, match="only arXiv"):
        parse_source("https://example.com/paper.pdf")


def test_build_article_layout():
    layout = build_article_layout("/tmp/out", "2403_18074")
    assert layout.article_id == "2403_18074"
    assert layout.pdf_dir.name == "pdf"
    assert layout.article_dir == layout.target_dir / "2403_18074"
