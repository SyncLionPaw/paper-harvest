#!/usr/bin/env python3
"""Pack and donate a coding-agent conversation trace to the donate-case object store.

Supported agents (local trace layouts):
    kimi-code    ~/.kimi-code/sessions/<wd_*>/session_<uuid>/{state.json,agents/**}
    claude-code  ~/.claude/projects/<encoded-cwd>/<uuid>.jsonl (+ <uuid>/ sidecar dir)
    codex        ~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<ts>-<uuid>.jsonl
    opencode     ${XDG_DATA_HOME:-~/.local/share}/opencode/opencode.db (SQLite, read-only;
                 only the target session's rows are exported), plus legacy
                 .../opencode/storage/{session,message,part}/**.json on old installs

Subcommands:
    list     List local sessions (default: current working directory only).
    pack     Pack a session's trace into a .tar.gz and print the manifest.
    upload   Pack, then HTTP PUT the archive to the configured endpoint.

Endpoint resolution order: --endpoint > $DONATE_CASE_ENDPOINT >
~/.config/donate-case/config.json ({"endpoint": ..., "token": ...}).
Auth token likewise: $DONATE_CASE_TOKEN or config "token" -> "Authorization: Bearer".
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "donate-case" / "config.json"

_XDG_DATA = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")

DEFAULT_ROOTS = {
    "kimi-code": Path.home() / ".kimi-code" / "sessions",
    "claude-code": Path.home() / ".claude" / "projects",
    "codex": Path.home() / ".codex" / "sessions",
    "opencode": _XDG_DATA / "opencode",
}

AGENTS = list(DEFAULT_ROOTS)


@dataclass
class SessionInfo:
    agent: str
    session_id: str
    path: Path  # session dir / .jsonl file / .db file, depending on agent
    cwd: str
    updated_ms: float
    title: str
    extra: dict = field(default_factory=dict)


def die(msg: str, code: int = 1) -> "SystemExit":
    print(f"donate-case: error: {msg}", file=sys.stderr)
    raise SystemExit(code)


def fmt_time(epoch_ms) -> str:
    try:
        return datetime.fromtimestamp(float(epoch_ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OSError):
        return str(epoch_ms or "?")


def human_size(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n} B"


def head_jsonl(path: Path, max_lines: int = 200):
    """Yield parsed JSON objects from the first max_lines of a .jsonl file."""
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def text_of_content(content) -> str:
    """Extract plain text from an agent message content field (str or typed list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [str(item.get("text", "")) for item in content
                 if isinstance(item, dict) and "text" in item]
        return " ".join(parts)
    return ""


def as_title(text: str) -> str:
    """Collapse whitespace; reject system-injected pseudo-messages wrapped in <tags>."""
    text = " ".join(text.split())
    if not text or text.startswith("<"):
        return ""
    return text[:80]


# --- per-agent discovery -----------------------------------------------------

def iter_kimi_code(root: Path):
    for state_path in sorted(root.glob("*/session_*/state.json")):
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        session_dir = state_path.parent
        yield SessionInfo(
            agent="kimi-code",
            session_id=session_dir.name.removeprefix("session_"),
            path=session_dir,
            cwd=state.get("cwd") or "",
            updated_ms=float(state.get("updatedAt") or 0),
            title=state.get("title") or "",
        )


def iter_claude_code(root: Path):
    for jsonl in sorted(root.glob("*/*.jsonl")):
        cwd, title = "", ""
        for entry in head_jsonl(jsonl):
            if not cwd and isinstance(entry.get("cwd"), str):
                cwd = entry["cwd"]
            if not title and entry.get("type") == "user" and not entry.get("isMeta"):
                title = as_title(text_of_content((entry.get("message") or {}).get("content")))
            if cwd and title:
                break
        try:
            updated_ms = jsonl.stat().st_mtime * 1000
        except OSError:
            continue
        yield SessionInfo(
            agent="claude-code",
            session_id=jsonl.stem,
            path=jsonl,
            cwd=cwd,
            updated_ms=updated_ms,
            title=title,
        )


def iter_codex(root: Path):
    for jsonl in sorted(root.rglob("rollout-*.jsonl")):
        session_id, cwd, title = "", "", ""
        for entry in head_jsonl(jsonl):
            if entry.get("type") == "session_meta":
                payload = entry.get("payload") or {}
                session_id = str(payload.get("id") or "")
                cwd = str(payload.get("cwd") or "")
            elif not title and entry.get("type") == "response_item":
                payload = entry.get("payload") or {}
                if payload.get("type") == "message" and payload.get("role") == "user":
                    title = as_title(text_of_content(payload.get("content")))
            if session_id and cwd and title:
                break
        if not session_id:
            continue
        try:
            updated_ms = jsonl.stat().st_mtime * 1000
        except OSError:
            continue
        yield SessionInfo(
            agent="codex",
            session_id=session_id,
            path=jsonl,
            cwd=cwd,
            updated_ms=updated_ms,
            title=title,
        )


def iter_opencode_sqlite(db: Path):
    """Current opencode: one global SQLite DB (WAL). Open read-only; fail soft on schema drift."""
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute("SELECT * FROM session WHERE parent_id IS NULL").fetchall()
    except sqlite3.Error:
        con.close()
        return
    for row in rows:
        d = dict(row)
        yield SessionInfo(
            agent="opencode",
            session_id=str(d.get("id") or ""),
            path=db,
            cwd=str(d.get("directory") or ""),
            updated_ms=float(d.get("time_updated") or 0),
            title=str(d.get("title") or ""),
            extra={"storage": "sqlite"},
        )
    con.close()


def iter_opencode_legacy(storage: Path):
    """Legacy opencode (pre-SQLite): file-per-entity JSON under storage/."""
    for session_json in sorted(storage.glob("session/*/*.json")):
        try:
            d = json.loads(session_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        time_info = d.get("time") or {}
        updated_ms = time_info.get("updated") or session_json.stat().st_mtime * 1000
        yield SessionInfo(
            agent="opencode",
            session_id=str(d.get("id") or session_json.stem),
            path=session_json,
            cwd=str(d.get("directory") or ""),
            updated_ms=float(updated_ms),
            title=str(d.get("title") or ""),
            extra={"storage": "legacy"},
        )


def iter_opencode(root: Path):
    db = root / "opencode.db"
    if db.is_file():
        yield from iter_opencode_sqlite(db)
    legacy = root / "storage"
    if legacy.is_dir():
        yield from iter_opencode_legacy(legacy)


ITERATORS = {
    "kimi-code": iter_kimi_code,
    "claude-code": iter_claude_code,
    "codex": iter_codex,
    "opencode": iter_opencode,
}


def iter_sessions(agents: list[str], root_override: Path | None):
    for agent in agents:
        root = root_override if root_override else DEFAULT_ROOTS[agent]
        root = root.expanduser()
        if root.is_dir():
            yield from ITERATORS[agent](root)


# --- packing -----------------------------------------------------------------

def trace_files(session: SessionInfo, include_logs: bool) -> list[tuple[Path, str]]:
    """Return [(absolute path, archive name)] for a session's trace.

    Not applicable to opencode SQLite sessions (rows live in a shared DB);
    those are exported row-wise in pack() instead.
    """
    files: list[tuple[Path, str]] = []
    if session.agent == "kimi-code":
        d = session.path
        for name in ("state.json",):
            if (d / name).is_file():
                files.append((d / name, name))
        agents_dir = d / "agents"
        if agents_dir.is_dir():
            files.extend((p, str(p.relative_to(d)))
                         for p in sorted(agents_dir.rglob("*")) if p.is_file())
        if include_logs:
            logs_dir = d / "logs"
            if logs_dir.is_dir():
                files.extend((p, str(p.relative_to(d)))
                             for p in sorted(logs_dir.rglob("*")) if p.is_file())
    elif session.agent == "opencode":
        if session.extra.get("storage") != "legacy":
            return []
        # legacy: storage/{session,message,part,session_diff}/...
        storage = session.path.parents[2]
        sid = session.session_id
        files.append((session.path, "opencode/session.json"))
        msg_dir = storage / "message" / sid
        message_ids = []
        if msg_dir.is_dir():
            for p in sorted(msg_dir.glob("*.json")):
                files.append((p, f"opencode/messages/{p.name}"))
                message_ids.append(p.stem)
        for mid in message_ids:
            part_dir = storage / "part" / mid
            if part_dir.is_dir():
                files.extend((p, f"opencode/parts/{mid}/{p.name}")
                             for p in sorted(part_dir.glob("*.json")))
        diff = storage / "session_diff" / f"{sid}.json"
        if diff.is_file():
            files.append((diff, "opencode/session_diff.json"))
    else:
        files.append((session.path, session.path.name))
        sidecar = session.path.with_suffix("")
        if sidecar.is_dir():
            files.extend((p, str(p.relative_to(session.path.parent)))
                         for p in sorted(sidecar.rglob("*")) if p.is_file())
    return files


def export_opencode_sqlite(session: SessionInfo) -> list[tuple[str, bytes]]:
    """Export the target session (plus sub-agent child sessions) from the shared DB.

    Only rows belonging to this session tree are read — the DB is global across
    projects, so nothing else may leak into the archive.
    """
    entries: list[tuple[str, bytes]] = []
    con = sqlite3.connect(f"file:{session.path}?mode=ro", uri=True)
    try:
        con.row_factory = sqlite3.Row
        sessions: dict[str, dict] = {}
        stack = [session.session_id]
        while stack:
            sid = stack.pop()
            if sid in sessions:
                continue
            row = con.execute("SELECT * FROM session WHERE id = ?", (sid,)).fetchone()
            if row is None:
                continue
            sessions[sid] = dict(row)
            stack.extend(r[0] for r in con.execute(
                "SELECT id FROM session WHERE parent_id = ?", (sid,)))
        ids = list(sessions)
        marks = ",".join("?" * len(ids))
        messages = [dict(r) for r in con.execute(
            f"SELECT * FROM message WHERE session_id IN ({marks})", ids)]
        parts = [dict(r) for r in con.execute(
            f"SELECT * FROM part WHERE session_id IN ({marks})", ids)]
    except sqlite3.Error as e:
        con.close()
        die(f"failed to read opencode db {session.path}: {e}")
    con.close()

    def dump(name: str, rows: list[dict]) -> None:
        blob = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n"
                       for r in rows).encode("utf-8")
        entries.append((name, blob))

    dump("opencode/sessions.jsonl", list(sessions.values()))
    dump("opencode/messages.jsonl", messages)
    dump("opencode/parts.jsonl", parts)
    return entries


def pack(session: SessionInfo, include_logs: bool, note: str | None) -> tuple[Path, list[tuple[str, int]]]:
    if session.agent == "opencode" and session.extra.get("storage") == "sqlite":
        entries = export_opencode_sqlite(session)
    else:
        files = trace_files(session, include_logs)
        if not files:
            die(f"no trace files found for session {session.session_id} ({session.path})")
        entries = [(arcname, src.read_bytes()) for src, arcname in files]

    meta = {
        "tool": "donate-case",
        "agent": session.agent,
        "donatedAt": datetime.now(timezone.utc).isoformat(),
        "sessionId": session.session_id,
        "cwd": session.cwd,
        "note": note or "",
    }
    entries.append(("donate-meta.json",
                    (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")))

    out = Path(tempfile.mkdtemp(prefix="donate-case-")) / f"{session.session_id}.tar.gz"
    manifest: list[tuple[str, int]] = []
    with tarfile.open(out, "w:gz") as tar:
        for arcname, blob in entries:
            info = tarfile.TarInfo(arcname)
            info.size = len(blob)
            info.mtime = int(time.time())
            tar.addfile(info, fileobj=io.BytesIO(blob))
            manifest.append((arcname, len(blob)))
    return out, manifest


# --- session resolution ------------------------------------------------------

def resolve_session(sessions: list[SessionInfo], session_id: str | None, cwd: Path) -> SessionInfo:
    if session_id:
        if ":" in session_id:  # allow "agent:<id>" to disambiguate
            agent, _, session_id = session_id.partition(":")
            sessions = [s for s in sessions if s.agent == agent]
        matches = [s for s in sessions if s.session_id.startswith(session_id)]
        if not matches:
            die(f"no session matching '{session_id}'")
        if len(matches) > 1:
            die(f"ambiguous session id '{session_id}', matches: "
                + ", ".join(f"{s.agent}:{s.session_id[:8]}" for s in matches))
        return matches[0]

    cwd = cwd.resolve()
    here = [s for s in sessions if s.cwd and Path(s.cwd).expanduser() == cwd]
    if not here:
        die(f"no session found for cwd {cwd}\n"
            "run from the directory the conversation was in, or pass --session <id> / --cwd <dir>")
    here.sort(key=lambda s: s.updated_ms)
    return here[-1]


def load_endpoint(cli_endpoint: str | None) -> tuple[str | None, str | None]:
    cfg = {}
    if CONFIG_PATH.is_file():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            die(f"unreadable config file: {CONFIG_PATH}")
    endpoint = cli_endpoint or os.environ.get("DONATE_CASE_ENDPOINT") or cfg.get("endpoint")
    token = os.environ.get("DONATE_CASE_TOKEN") or cfg.get("token")
    return endpoint, token


def select_agents(args) -> list[str]:
    if args.agent == "all":
        if getattr(args, "sessions_root", None):
            die("--sessions-root requires --agent <name> (not 'all')")
        return AGENTS
    return [args.agent]


# --- subcommands ---------------------------------------------------------------

def cmd_list(args) -> None:
    agents = select_agents(args)
    root_override = Path(args.sessions_root) if getattr(args, "sessions_root", None) else None
    cwd = Path(args.cwd).resolve() if getattr(args, "cwd", None) else Path.cwd().resolve()
    rows = []
    for s in iter_sessions(agents, root_override):
        if not args.all and (not s.cwd or Path(s.cwd).expanduser() != cwd):
            continue
        if s.agent == "opencode" and s.extra.get("storage") == "sqlite":
            size = None  # rows live in the shared DB; no per-session file size
        else:
            size = sum(f.stat().st_size for f, _ in trace_files(s, include_logs=False))
        rows.append((s.updated_ms, s.agent, s.session_id, s.title, s.cwd, size))
    if not rows:
        print("no sessions found" + ("" if args.all else f" for cwd {cwd} (try --all)"))
        return
    rows.sort(key=lambda r: r[0], reverse=True)
    for updated, agent, sid, title, scwd, size in rows[: args.limit]:
        size_str = human_size(size) if size is not None else "-"
        print(f"{agent:11}  {sid[:8]}  {fmt_time(updated)}  {size_str:>10}  "
              f"{title[:40]:40}  {scwd}")


def resolve_from_args(args) -> SessionInfo:
    agents = select_agents(args)
    root_override = Path(args.sessions_root) if getattr(args, "sessions_root", None) else None
    sessions = list(iter_sessions(agents, root_override))
    cwd = Path(args.cwd) if args.cwd else Path.cwd()
    return resolve_session(sessions, args.session, cwd)


def print_manifest(session: SessionInfo, manifest: list[tuple[str, int]]) -> int:
    print(f"agent:    {session.agent}")
    print(f"session:  {session.session_id}")
    total = 0
    for arcname, size in manifest:
        print(f"  {human_size(size):>10}  {arcname}")
        total += size
    print(f"  {human_size(total):>10}  total (uncompressed)")
    return total


def cmd_pack(args) -> None:
    session = resolve_from_args(args)
    out, manifest = pack(session, args.include_logs, args.note)
    print_manifest(session, manifest)
    print(f"archive:  {out}")


def cmd_upload(args) -> None:
    endpoint, token = load_endpoint(args.endpoint)
    if not endpoint:
        if not args.dry_run:
            die("upload endpoint is not configured (service not deployed yet?).\n"
                "set one of: --endpoint <url>, $DONATE_CASE_ENDPOINT, or "
                f"{CONFIG_PATH} with {{\"endpoint\": \"...\", \"token\": \"...\"}}")
        endpoint = "<endpoint-not-configured>"
        print("note: endpoint not configured, showing preview only")

    session = resolve_from_args(args)
    out, manifest = pack(session, args.include_logs, args.note)
    print_manifest(session, manifest)

    key = (f"{session.agent}/{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
           f"/{session.session_id}.tar.gz")
    url = f"{endpoint.rstrip('/')}/{key}"

    if args.dry_run:
        print(f"dry-run: would PUT {human_size(out.stat().st_size)} (gzip) to {url}")
        return

    req = urllib.request.Request(url, data=out.read_bytes(), method="PUT")
    req.add_header("Content-Type", "application/gzip")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", "replace")[:500]
            print(f"uploaded: HTTP {resp.status} -> {url}")
            if body.strip():
                print(f"server response: {body}")
    except urllib.error.HTTPError as e:
        die(f"upload failed: HTTP {e.code} {e.reason}\n{e.read().decode('utf-8', 'replace')[:500]}")
    except urllib.error.URLError as e:
        die(f"upload failed: {e.reason}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--agent", choices=["all"] + AGENTS, default="all",
                   help="which agent's traces to consider (default: all)")
    p.add_argument("--sessions-root",
                   help="override the trace root directory (requires --agent <name>)")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--session", metavar="ID",
                        help="session id (unique prefix ok, optionally 'agent:<id>'); "
                             "default: latest session for cwd")
        sp.add_argument("--cwd", help="resolve session for this directory instead of the current one")
        sp.add_argument("--include-logs", action="store_true",
                        help="kimi-code only: also pack logs/ (verbose, off by default)")
        sp.add_argument("--note", help="short note stored in donate-meta.json (why this case is worth donating)")

    sp = sub.add_parser("list", help="list local sessions")
    sp.add_argument("--all", action="store_true", help="list sessions for all directories")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("pack", help="pack a trace without uploading")
    common(sp)
    sp.set_defaults(func=cmd_pack)

    sp = sub.add_parser("upload", help="pack and upload a trace")
    common(sp)
    sp.add_argument("--endpoint", help="base URL of the donate-case object store")
    sp.add_argument("--dry-run", action="store_true", help="show what would be uploaded, send nothing")
    sp.set_defaults(func=cmd_upload)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
