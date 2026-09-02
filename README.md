# paper-harvest

This repo holds two things:

- **`skills/`** — a collection of agent skills, shipped as per-skill zips via GitHub Releases
- **paper-harvest CLI** — the Python package (`src/`, published to PyPI) that the paper-harvest skill drives

## Skills

| Skill | Version | Summary |
|-------|---------|---------|
| [paper-harvest](skills/paper-harvest/) | 0.2.0 | Harvest arXiv papers into organized directories (PDF, TeX, Markdown) |
| [ikkem-slurm](skills/ikkem-slurm/) | 0.1.0 | 向 ikkem 集群提交 SLURM 作业（实时探测分区/gres，提交+监控+回收） |

**Install** — download `<name>-<version>-skill.zip` from releases, then:

```bash
unzip paper-harvest-0.2.0-skill.zip -d ~/.cursor/skills/
```

**Build locally:**

```bash
python tools/build_skill_zips.py --all              # every skill
python tools/build_skill_zips.py --skill <name>     # one skill
python tools/build_skill_zips.py --list             # name + version only
```

Skill sources live in `skills/<name>/` (`SKILL.md`, `references/`, `scripts/`).
Each skill versions independently via the `version` field in its `SKILL.md`
frontmatter; the build requires the directory name to match `name`.

## paper-harvest CLI

Collect arXiv papers into a unified article directory: PDF, TeX source,
optional Markdown, and a structured manifest. Python 3.9+, stdlib only at runtime.

### Quick start

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

### Output

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

### CLI flags

| Flag | Effect |
|------|--------|
| `--target-dir <dir>` | Output root (default: `.`) |
| `--skip-tex` | Skip TeX source download |
| `--skip-md` | Skip Markdown extraction |
| `--force` | Overwrite existing `md/` |
| `--json` | Print structured JSON to stdout |
| `--timeout <sec>` | Download timeout (default: 120) |

### Markdown (MinerU)

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

The [paper-harvest skill](skills/paper-harvest/) is Agent instructions only;
execution still goes through this CLI.

## Project layout

```text
paper-harvest/
  pyproject.toml
  src/paper_harvest/       # paper-harvest CLI + core
  skills/                  # Agent skills, one directory per skill
    paper-harvest/
    ikkem-slurm/
  docs/spec.md             # product specification
  tools/build_skill_zips.py
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

**Python package** (PyPI, `uvx paper-harvest`):

1. Bump `version` in `pyproject.toml` and `src/paper_harvest/__init__.py`
2. `uv run pytest && uv build`
3. Tag `v0.x.y`, push — the `Publish to PyPI` workflow builds and publishes

**Skills** (GitHub Releases, per-skill):

1. Bump `version` in `skills/<name>/SKILL.md` frontmatter
2. Merge to `main` — the `Release skills` workflow builds
   `<name>-<version>-skill.zip` and creates release `skill-<name>-v<version>`
3. Already-released versions are skipped; bump the version to re-publish

## Docs

- `docs/spec.md` — product / engineering specification
- `skills/paper-harvest/references/` — Agent-facing reference (manifest schema, MinerU setup)
