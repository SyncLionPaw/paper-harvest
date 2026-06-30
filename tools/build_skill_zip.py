#!/usr/bin/env python3
"""Build paper-harvest skill zip for Cursor skills directory."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_SRC = ROOT / "skill"
DIST = ROOT / "dist"
SKILL_NAME = "paper-harvest"


def read_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    if not match:
        raise SystemExit("cannot find version in pyproject.toml")
    return match.group(1)


def build_skill_zip() -> Path:
    version = read_version()
    DIST.mkdir(parents=True, exist_ok=True)
    out_path = DIST / f"{SKILL_NAME}-{version}-skill.zip"

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SKILL_SRC.rglob("*")):
            if not path.is_file():
                continue
            arcname = f"{SKILL_NAME}/{path.relative_to(SKILL_SRC)}"
            archive.write(path, arcname)

    print(out_path)
    return out_path


if __name__ == "__main__":
    build_skill_zip()
