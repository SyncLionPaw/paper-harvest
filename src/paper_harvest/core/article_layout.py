from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class ArticleLayout:
    article_id: str
    target_dir: Path
    article_dir: Path
    pdf_dir: Path
    md_dir: Path
    tex_dir: Path


def normalize_article_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    if not normalized:
        raise ValueError("article id is empty")
    return normalized


def build_article_layout(output_root: str | Path, article_id: str) -> ArticleLayout:
    normalized_id = normalize_article_id(article_id)
    target_dir = Path(output_root).expanduser().resolve()
    article_dir = target_dir / normalized_id
    return ArticleLayout(
        article_id=normalized_id,
        target_dir=target_dir,
        article_dir=article_dir,
        pdf_dir=article_dir / "pdf",
        md_dir=article_dir / "md",
        tex_dir=article_dir / "tex",
    )


def ensure_variant_dir(layout: ArticleLayout, variant: str) -> Path:
    if variant == "pdf":
        target_dir = layout.pdf_dir
    elif variant == "md":
        target_dir = layout.md_dir
    elif variant == "tex":
        target_dir = layout.tex_dir
    else:
        raise ValueError(f"Unsupported article variant: {variant}")

    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


def ensure_article_layout(layout: ArticleLayout) -> ArticleLayout:
    layout.article_dir.mkdir(parents=True, exist_ok=True)
    layout.pdf_dir.mkdir(parents=True, exist_ok=True)
    layout.md_dir.mkdir(parents=True, exist_ok=True)
    layout.tex_dir.mkdir(parents=True, exist_ok=True)
    return layout


def to_public_path(path: str | Path, target_dir: str | Path) -> str:
    resolved_path = Path(path).expanduser().resolve()
    resolved_target_dir = Path(target_dir).expanduser().resolve()
    try:
        return str(resolved_path.relative_to(resolved_target_dir))
    except ValueError:
        return str(resolved_path)
