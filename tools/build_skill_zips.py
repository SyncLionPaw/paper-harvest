#!/usr/bin/env python3
"""Build skill zips from skills/<name>/ directories.

Each skill ships as <name>-<version>-skill.zip with a top-level <name>/
directory inside. Name and version come from the SKILL.md frontmatter.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def parse_frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise SystemExit(f"{skill_md}: missing YAML frontmatter")
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip().strip('"').strip("'")
    for required in ("name", "version"):
        if not fields.get(required):
            raise SystemExit(f"{skill_md}: frontmatter missing '{required}'")
    return fields


def discover_skills() -> dict:
    """Return {name: (skill_dir, version)} for every skills/*/SKILL.md."""
    skills = {}
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        fields = parse_frontmatter(skill_md)
        name, version = fields["name"], fields["version"]
        if skill_md.parent.name != name:
            raise SystemExit(
                f"{skill_md}: directory '{skill_md.parent.name}' != frontmatter name '{name}'"
            )
        skills[name] = (skill_md.parent, version)
    return skills


def build_skill_zip(name: str, skill_dir: Path, version: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{name}-{version}-skill.zip"

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file():
                continue
            arcname = f"{name}/{path.relative_to(skill_dir)}"
            archive.write(path, arcname)

    print(out_path)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", action="append", default=[], metavar="NAME",
                        help="build only this skill (repeatable)")
    parser.add_argument("--all", action="store_true", help="build all skills")
    parser.add_argument("--list", action="store_true",
                        help="print '<name> <version>' per skill and exit")
    parser.add_argument("--out", default=str(ROOT / "dist"), help="output directory")
    args = parser.parse_args()

    skills = discover_skills()

    if args.list:
        for name, (_, version) in skills.items():
            print(f"{name} {version}")
        return

    if args.all:
        selected = list(skills)
    elif args.skill:
        unknown = [n for n in args.skill if n not in skills]
        if unknown:
            raise SystemExit(f"unknown skill(s): {', '.join(unknown)}")
        selected = args.skill
    else:
        parser.error("pass --all or --skill NAME")

    out_dir = Path(args.out)
    for name in selected:
        skill_dir, version = skills[name]
        build_skill_zip(name, skill_dir, version, out_dir)


if __name__ == "__main__":
    main()
