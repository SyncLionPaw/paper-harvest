"""Harvest arXiv papers into organized article directories."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paper_harvest.core.article_layout import build_article_layout
from paper_harvest.core.models import HarvestResult, StepResult
from paper_harvest.core.url.parse import parse_source


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="paper-harvest",
        description="Harvest arXiv papers into organized article directories.",
    )
    parser.add_argument(
        "source",
        help="arXiv URL",
    )
    parser.add_argument(
        "--target-dir",
        default=".",
        help="Output root directory (default: current directory)",
    )
    parser.add_argument(
        "--skip-tex",
        action="store_true",
        help="Skip TeX source download",
    )
    parser.add_argument(
        "--skip-md",
        action="store_true",
        help="Skip Markdown extraction",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing md/ output",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON result to stdout",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Download timeout in seconds (default: 120)",
    )

    args = parser.parse_args(argv)
    return run(args)


def run(args: argparse.Namespace) -> int:
    try:
        source = parse_source(args.source)
    except ValueError as exc:
        sys.stderr.write(f"paper-harvest: {exc}\n")
        return 1

    layout = build_article_layout(args.target_dir, source.article_id_candidate)

    pdf_result = step_download_pdf(source, layout, timeout=args.timeout)

    tex_result: StepResult
    if args.skip_tex:
        tex_result = StepResult(status="skipped", message="--skip-tex")
    else:
        tex_result = step_fetch_tex(source, layout, timeout=args.timeout)

    md_result: StepResult
    if args.skip_md:
        md_result = StepResult(status="skipped", message="--skip-md")
    else:
        md_result = step_extract_md(
            source,
            layout,
            pdf_path=Path(pdf_result.path) if pdf_result.path else None,
            force=args.force,
        )

    result = HarvestResult(
        tool_name="paper-harvest",
        article_id=layout.article_id,
        article_dir=str(layout.article_dir),
        source=source,
        pdf=pdf_result,
        tex=tex_result,
        md=md_result,
        manifest_path=str(layout.article_dir / "harvest_result.json"),
    )

    manifest = result.to_dict()
    layout.article_dir.mkdir(parents=True, exist_ok=True)
    (layout.article_dir / "harvest_result.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print_summary(result)

    failed = any(s.status == "failed" for s in [result.pdf, result.tex, result.md])
    return 1 if failed else 0


def step_download_pdf(
    source,
    layout,
    *,
    timeout: int,
) -> StepResult:
    try:
        from paper_harvest.core.pdf.download import download_pdf

        dl_result = download_pdf(source, layout, timeout=timeout)
        return StepResult(
            status="ok",
            message="pdf downloaded",
            path=str(dl_result.pdf_path),
        )
    except Exception as exc:
        return StepResult(
            status="failed",
            message=str(exc),
            error_code=exc_to_code(exc),
        )


def step_fetch_tex(
    source,
    layout,
    *,
    timeout: int,
) -> StepResult:
    try:
        from paper_harvest.core.tex.arxiv import fetch_arxiv_source

        tex_result = fetch_arxiv_source(source, layout, timeout=timeout)
        return StepResult(
            status="ok",
            message="tex source fetched",
            path=str(tex_result.extracted_dir),
            artifacts=[str(tex_result.archive_path)],
        )
    except Exception as exc:
        return StepResult(
            status="failed",
            message=str(exc),
            error_code=exc_to_code(exc),
        )


def step_extract_md(
    source,
    layout,
    *,
    pdf_path: Path | None,
    force: bool,
) -> StepResult:
    if pdf_path is None or not pdf_path.exists():
        return StepResult(
            status="failed",
            message="no PDF available for Markdown extraction",
        )

    try:
        from paper_harvest.core.md.mineru import MineruError, extract_markdown

        md_result = extract_markdown(
            pdf_path,
            layout,
            source,
            force=force,
        )
        return StepResult(
            status="ok",
            message="markdown extracted",
            path=str(md_result.markdown_path),
            artifacts=[str(md_result.markdown_path)],
        )
    except MineruError as exc:
        code = exc.error_code or exc_to_code(exc)
        if code in ("-30001",):
            return StepResult(
                status="skipped",
                message=f"lightweight API not applicable: {exc}",
                error_code=code,
            )
        return StepResult(
            status="failed",
            message=str(exc),
            error_code=code,
        )
    except Exception as exc:
        return StepResult(
            status="failed",
            message=str(exc),
            error_code=exc_to_code(exc),
        )


def exc_to_code(exc: Exception) -> str:
    return type(exc).__name__


def print_summary(result: HarvestResult) -> None:
    print(f"article  : {result.article_id}")
    print(f"directory: {result.article_dir}")
    print(f"pdf      : [{result.pdf.status}] {result.pdf.message}")
    if result.pdf.path:
        print(f"           {result.pdf.path}")
    print(f"tex      : [{result.tex.status}] {result.tex.message}")
    if result.tex.path:
        print(f"           {result.tex.path}")
    print(f"md       : [{result.md.status}] {result.md.message}")
    if result.md.path:
        print(f"           {result.md.path}")
    print(f"manifest : {result.manifest_path}")


if __name__ == "__main__":
    raise SystemExit(main())
