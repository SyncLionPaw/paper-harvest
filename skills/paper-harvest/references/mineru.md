# MinerU Markdown extraction

Markdown generation is optional and uses [MinerU](https://mineru.net/) APIs.

## Token (precision API)

Set any one of:

```text
MINERU_API_TOKEN
./.mineru_token
~/.mineru_token
~/.config/mineru/token
```

With a token, the tool uses the precision API (better quality, larger files, zip output).

## No token (lightweight API)

Without a token, the tool tries MinerU Agent lightweight parsing:

- Single file only
- PDF must be **≤ 10 MB**
- Output is Markdown only (no full zip)
- Rate-limited by IP

If the PDF is too large or the call fails, `md` is marked `skipped` or `failed`; `pdf` and `tex` are kept.

## Agent follow-up

When `md.status` is `skipped`:

1. Check `message` for size limit vs missing token
2. If size: use `pdf/` or `tex/source/` directly, or ask user for MinerU token
3. If token missing: user can set `MINERU_API_TOKEN` and re-run with `--force`

Re-run Markdown only (keep existing pdf/tex):

```bash
uvx paper-harvest '<same-arxiv-url>' --skip-tex --force --json
```
