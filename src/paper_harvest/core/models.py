from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ParsedSource:
    raw_input: str
    normalized_input: str
    input_kind: str
    source_kind: str
    article_id_candidate: str
    pdf_url: str | None = None
    tex_url: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class StepResult:
    status: str
    message: str
    path: str | None = None
    artifacts: list[str] = field(default_factory=list)
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class HarvestResult:
    tool_name: str
    article_id: str
    article_dir: str
    source: ParsedSource
    pdf: StepResult
    tex: StepResult
    md: StepResult
    manifest_path: str

    def to_dict(self) -> dict[str, object]:
        return {
            "tool_name": self.tool_name,
            "article_id": self.article_id,
            "article_dir": self.article_dir,
            "source": self.source.to_dict(),
            "pdf": self.pdf.to_dict(),
            "tex": self.tex.to_dict(),
            "md": self.md.to_dict(),
            "manifest_path": self.manifest_path,
        }
