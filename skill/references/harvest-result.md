# harvest_result.json

Authoritative output for each run. Prefer reading this file over parsing terminal text.

## Location

```text
<target-dir>/<article_id>/harvest_result.json
```

The `manifest_path` field in JSON points to this file.

## Top-level fields

| Field | Meaning |
|-------|---------|
| `tool_name` | Always `paper-harvest` |
| `article_id` | Normalized directory name (e.g. `2403_18074`) |
| `article_dir` | Absolute path to the article root |
| `source` | Parsed input (arXiv id, pdf/tex URLs) |
| `pdf` / `tex` / `md` | Per-step results |
| `manifest_path` | Path to this file |

## Step result shape

Each of `pdf`, `tex`, `md` has:

| Field | Meaning |
|-------|---------|
| `status` | `ok`, `skipped`, or `failed` |
| `message` | Human-readable summary |
| `path` | Main artifact path, or `null` |
| `artifacts` | Extra files (optional list) |
| `error_code` | Error hint when present |

## Status semantics

- **ok** — step completed; use `path` for the primary artifact
- **skipped** — intentionally not run (`--skip-md`) or preconditions missing (e.g. lightweight MinerU not applicable)
- **failed** — step ran but errored; earlier steps may still be usable

A run returns exit code `1` if any step is `failed`; `skipped` alone does not fail the run.

## Directory layout

```text
<article_id>/
├── pdf/<article_id>.pdf
├── tex/
│   ├── arXiv-<id>.tar.gz
│   └── source/
├── md/
│   ├── <article_id>.md
│   ├── assets/
│   ├── mineru.zip          # precision API only
│   └── mineru_result.json
└── harvest_result.json
```

After a successful harvest, read `md/<article_id>.md` for paper content, or `pdf/` / `tex/source/` for originals.

## Example

```json
{
  "article_id": "2403_18074",
  "article_dir": "/path/to/2403_18074",
  "pdf": {"status": "ok", "message": "pdf downloaded", "path": "..."},
  "tex": {"status": "ok", "message": "tex source fetched", "path": "..."},
  "md": {"status": "skipped", "message": "lightweight API not applicable: ...", "path": null},
  "manifest_path": "/path/to/2403_18074/harvest_result.json"
}
```
