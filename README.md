# paper-harvest

Collect arXiv papers into a unified article directory: PDF, TeX source, optional Markdown, and a structured manifest.

Python 3.9+, stdlib only at runtime. Two ways to use it:

| Audience | How |
|----------|-----|
| Terminal / automation | `uvx paper-harvest` (PyPI) |
| Cursor / Agent | Install the [skill zip](#cursor-skill) |

## Quick start

```bash
uvx paper-harvest 'https://arxiv.org/abs/2403.18074' --json
```

From a local checkout:

```bash
uvx --from . paper-harvest 'https://arxiv.org/abs/2403.18074' --json
```

Install permanently:

```bash
uv tool install paper-harvest
paper-harvest 'https://arxiv.org/abs/2403.18074' --json
```

**Input:** arXiv URLs only (`arxiv.org`, `abs` / `pdf` / `src`).

## Output

```text
<article_id>/
  pdf/<article_id>.pdf
  tex/
    arXiv-<id>.tar.gz
    source/
  md/
    <article_id>.md
    assets/
    mineru_result.json
  harvest_result.json
```

Each step reports `ok`, `skipped`, or `failed` in `harvest_result.json`. Failed steps do not remove earlier artifacts.

## CLI flags

| Flag | Effect |
|------|--------|
| `--target-dir <dir>` | Output root (default: `.`) |
| `--skip-tex` | Skip TeX source download |
| `--skip-md` | Skip Markdown extraction |
| `--force` | Overwrite existing `md/` |
| `--json` | Print structured JSON to stdout |
| `--timeout <sec>` | Download timeout (default: 120) |

## Markdown (MinerU)

Markdown is optional and uses [MinerU](https://mineru.net/).

1. **With token** → precision API (better quality, larger PDFs)
2. **Without token** → lightweight API (PDFs ≤ 10 MB)
3. **Otherwise** → `md` is `skipped` or `failed`; PDF and TeX are kept

Configure a token via any one of:

```bash
export MINERU_API_TOKEN='your-token'
echo 'your-token' > ~/.mineru_token && chmod 600 ~/.mineru_token
```

Also checked: `./.mineru_token`, `~/.config/mineru/token`. Never commit token files.

Re-run Markdown only after adding a token:

```bash
uvx paper-harvest '<same-arxiv-url>' --skip-tex --force --json
```

## Cursor Skill

The skill is Agent instructions only; execution still goes through the CLI.

**Install** — download `paper-harvest-<version>-skill.zip` from releases:

```bash
unzip paper-harvest-0.2.0-skill.zip -d ~/.cursor/skills/
```

**Build locally:**

```bash
uv build
python tools/build_skill_zip.py
# → dist/paper-harvest-0.2.0-skill.zip
```

Skill sources live in `skill/` (`SKILL.md`, `references/`, `scripts/harvest.sh`).

## Project layout

```text
paper-harvest/
  pyproject.toml
  src/paper_harvest/     # CLI + core
  skill/                   # Agent skill (shipped as zip)
  docs/spec.md             # product specification
  tools/build_skill_zip.py
  tests/
```

## Development

```bash
uv sync --extra dev
uv run pytest
uv build
uvx --from . paper-harvest --help
```

## Publish

1. Bump `version` in `pyproject.toml` and `src/paper_harvest/__init__.py`
2. `uv run pytest && uv build && python tools/build_skill_zip.py`
3. Tag `v0.x.y`, push, attach `dist/*-skill.zip` to GitHub Release
4. `uv publish` for PyPI (`uvx paper-harvest`)

## Docs

- `docs/spec.md` — product / engineering specification
- `skill/references/` — Agent-facing reference (manifest schema, MinerU setup)
