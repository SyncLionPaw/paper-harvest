---
name: paper-harvest
version: "0.2.0"
description: Harvest arXiv papers into organized directories with PDF, TeX source, and optional MinerU Markdown. Use when downloading or collecting paper assets, processing arxiv.org URLs (abs/pdf/src), reading or surveying a paper, or when the user gives an arXiv-style ID such as 2403.18074 or 2204.01018v1.
---

# Paper Harvest

Fetch arXiv papers into `<article_id>/` with `pdf/`, `tex/`, `md/`, and `harvest_result.json`.

## Workflow

1. Run the CLI with `--json` (see below).
2. Read `harvest_result.json`; check each step `status` (`ok`, `skipped`, `failed`).
3. To answer questions about the paper, read `md/<article_id>.md` when `md` is ok; otherwise use `pdf/` or `tex/source/`.

## Run

Prefer zero-install:

```bash
uvx paper-harvest '<arxiv-url>' --json
```

If `paper-harvest` is already on PATH (pip/uv tool install):

```bash
paper-harvest '<arxiv-url>' --json
```

From this skill directory only, you may execute `./scripts/harvest.sh` (wrapper around `uvx paper-harvest`).

| Flag | Effect |
|---|---|
| `--target-dir <dir>` | Output root (default: `.`) |
| `--skip-tex` | Skip TeX source |
| `--skip-md` | Skip Markdown |
| `--force` | Overwrite existing `md/` |
| `--json` | Structured stdout (always use for agents) |
| `--timeout <sec>` | Download timeout (default: 120) |

**Input:** arXiv URLs only (`arxiv.org`, `abs` / `pdf` / `src`). Other sources are rejected.

## Examples

```bash
uvx paper-harvest 'https://arxiv.org/abs/2403.18074' --json
uvx paper-harvest 'https://arxiv.org/abs/2403.18074' --skip-tex --skip-md --json
uvx paper-harvest 'https://arxiv.org/abs/2403.18074' --target-dir ./papers --json
```

## Reference

- [harvest-result.md](references/harvest-result.md) — manifest schema, output layout, exit codes
- [mineru.md](references/mineru.md) — Markdown token, lightweight API limits, retries
