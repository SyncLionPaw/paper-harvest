#!/usr/bin/env python3
"""Submit long-running jobs to compute backends (SLURM or plain SSH).

Minimal interface: submit / status / logs / cancel / collect / list / probe.
All commands except `logs` print a single JSON object to stdout.
Job state is stored per job in .submit-job/<name>.json under the cwd;
run status/logs/cancel/collect from the same directory used at submit time.
Targets (clusters / nodes) are defined in submit-job.json (project root)
or ~/.config/submit-job/config.json.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import time
from pathlib import Path

STATE_DIR = Path(".submit-job")
CONFIG_PATHS = [
    Path("submit-job.json"),
    Path.home() / ".config" / "submit-job" / "config.json",
]
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]


def ok(**fields):
    print(json.dumps({"status": "ok", **fields}, ensure_ascii=False))


def fail(message, **fields):
    print(json.dumps({"status": "failed", "error": message, **fields},
                     ensure_ascii=False))
    raise SystemExit(1)


def q(value):
    return shlex.quote(str(value))


def qr(path):
    """Quote a remote path, keeping ~/ and $VARS expandable by the remote shell."""
    p = str(path)
    if p.startswith("~/"):
        p = "$HOME/" + p[2:]
    return '"' + p.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`") + '"'


def ssh(host, remote_cmd, check=True):
    result = subprocess.run(
        ["ssh", *SSH_OPTS, host, remote_cmd],
        capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        fail(f"ssh {host} failed: {result.stderr.strip() or result.stdout.strip()}")
    return result


def rsync_up(host, src, workdir, excludes=()):
    cmd = ["rsync", "-az"]
    for pattern in excludes:
        cmd += ["--exclude", pattern]
    cmd += [src.rstrip("/") + "/", f"{host}:{workdir}/"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        fail(f"rsync to {host}:{workdir} failed: {result.stderr.strip()}")


def load_targets():
    for path in CONFIG_PATHS:
        if path.is_file():
            try:
                config = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                fail(f"invalid JSON in {path}: {exc}")
            return config.get("targets", {}), path
    return {}, None


def resolve_target(args):
    cfg = {}
    if args.target:
        targets, path = load_targets()
        if args.target not in targets:
            known = ", ".join(sorted(targets)) or "(none configured)"
            fail(f"unknown target '{args.target}' (known: {known}; "
                 f"config: {path or 'no submit-job.json found'})")
        cfg = dict(targets[args.target])
    for key in ("backend", "host", "base_dir", "time", "partition",
                "cpus", "mem", "gpus", "gres"):
        value = getattr(args, key, None)
        if value is not None:
            cfg[key] = value
    if not cfg.get("backend") or not cfg.get("host"):
        fail("backend and host are required (via --target config or --backend/--host)")
    return cfg


def state_path(name):
    return STATE_DIR / f"{name}.json"


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path(state["name"]).write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_state(name):
    path = state_path(name)
    if not path.is_file():
        fail(f"no state for job '{name}' (expected {path}); jobs are tracked by name. "
             f"Run from the same directory used at submit time.")
    return json.loads(path.read_text(encoding="utf-8"))


def render_sbatch(name, cmd, res):
    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={name}",
        "#SBATCH --output=logs/%x-%j.out",
        "#SBATCH --error=logs/%x-%j.err",
    ]
    if res.get("time"):
        lines.append(f"#SBATCH --time={res['time']}")
    if res.get("partition"):
        lines.append(f"#SBATCH --partition={res['partition']}")
    if res.get("cpus"):
        lines.append(f"#SBATCH --cpus-per-task={res['cpus']}")
    if res.get("mem"):
        lines.append(f"#SBATCH --mem={res['mem']}")
    if res.get("gres"):
        lines.append(f"#SBATCH --gres={res['gres']}")
    elif res.get("gpus"):
        lines.append(f"#SBATCH --gres=gpu:{res['gpus']}")
    lines += ["", "set -euo pipefail", cmd, ""]
    return "\n".join(lines)


def build_plan(name, cmd, cfg):
    workdir = cfg.get("workdir") or f"{cfg.get('base_dir', '~/submit-jobs')}/{name}"
    plan = {"backend": cfg["backend"], "host": cfg["host"], "workdir": workdir}
    if cfg["backend"] == "slurm":
        plan["script"] = render_sbatch(name, cmd, cfg)
    else:
        plan["remote_command"] = cmd
    return workdir, plan


def cmd_submit(args):
    if not NAME_RE.match(args.name):
        fail(f"invalid job name '{args.name}' (allowed: [A-Za-z0-9._-])")
    if state_path(args.name).is_file():
        fail(f"job '{args.name}' already submitted; use another name, "
             f"or cancel it first")
    cfg = resolve_target(args)
    if args.workdir:
        cfg["workdir"] = args.workdir
    workdir, plan = build_plan(args.name, args.cmd, cfg)
    if args.src:
        plan["sync"] = f"{args.src} -> {cfg['host']}:{workdir}"
        if args.exclude:
            plan["sync_excludes"] = args.exclude

    if args.dry_run:
        ok(dry_run=True, name=args.name, plan=plan)
        return

    host = cfg["host"]
    ssh(host, f"mkdir -p {qr(workdir)}/logs")
    if args.src:
        rsync_up(host, args.src, workdir, excludes=args.exclude)

    state = {
        "name": args.name, "backend": cfg["backend"], "host": host,
        "workdir": workdir, "cmd": args.cmd,
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    if cfg["backend"] == "slurm":
        result = subprocess.run(
            ["ssh", *SSH_OPTS, host, f"cat > {qr(workdir)}/submit.sh"],
            input=plan["script"], text=True, capture_output=True,
        )
        if result.returncode != 0:
            fail(f"cannot write submit.sh: {result.stderr.strip()}")
        out = ssh(host, f"cd {qr(workdir)} && sbatch submit.sh").stdout
        match = re.search(r"Submitted batch job (\d+)", out)
        if not match:
            fail(f"unexpected sbatch output: {out.strip()}")
        state["job_id"] = match.group(1)
        state["log"] = f"{workdir}/logs/{args.name}-{state['job_id']}.out"
    else:
        log = f"{workdir}/logs/{args.name}.log"
        exit_file = f"{workdir}/logs/{args.name}.exit"
        inner = f"cd {qr(workdir)} && ( {args.cmd} ) > {qr(log)} 2>&1; echo $? > {qr(exit_file)}"
        if ssh(host, "command -v tmux", check=False).returncode == 0:
            ssh(host, f"tmux new-session -d -s {q(args.name)} {q(inner)}")
            state["session"] = args.name
        else:
            pid = ssh(host, f"nohup bash -c {q(inner)} >/dev/null 2>&1 & echo $!").stdout.strip()
            state["pid"] = pid
        state["log"] = log
        state["exit_file"] = exit_file

    save_state(state)
    ok(name=args.name, **{k: v for k, v in state.items() if k not in ("name", "cmd")})


def slurm_state(state):
    host, jid = state["host"], state["job_id"]
    queued = ssh(host, f"squeue -j {jid} -h -o %T", check=False).stdout.strip()
    if queued:
        return queued.lower(), None
    # sacct lags behind job completion; retry briefly before giving up
    out = ""
    for _ in range(3):
        out = ssh(host, f"sacct -j {jid} -X -n -P --format=State,ExitCode",
                  check=False).stdout.strip()
        if out:
            break
        time.sleep(2)
    if not out:
        return "unknown", None
    raw, exit_code = (out.split("|") + ["", ""])[:2]
    raw = raw.strip().split()[0] if raw.strip() else "UNKNOWN"
    code = exit_code.strip().split(":")[0]
    if raw == "COMPLETED" and code == "0":
        return "completed", 0
    if raw in ("PENDING", "RUNNING", "CONFIGURING"):
        return raw.lower(), None
    if raw.startswith("CANCELLED"):
        return "cancelled", code or None
    return "failed", code or None


def ssh_state(state):
    host = state["host"]
    exit_out = ssh(host, f"cat {qr(state['exit_file'])} 2>/dev/null",
                   check=False).stdout.strip()
    if exit_out:
        code = int(exit_out)
        return ("completed" if code == 0 else "failed"), code
    if state.get("session"):
        alive = ssh(host, f"tmux has-session -t {q(state['session'])}",
                    check=False).returncode == 0
    else:
        alive = ssh(host, f"kill -0 {q(state['pid'])}",
                    check=False).returncode == 0
    return ("running" if alive else "unknown"), None


def query_state(state):
    return (slurm_state if state["backend"] == "slurm" else ssh_state)(state)


def cmd_status(args):
    state = load_state(args.job)
    job_state, exit_code = query_state(state)
    ok(name=args.job, backend=state["backend"], state=job_state,
       exit_code=exit_code, workdir=state["workdir"], log=state["log"])


def cmd_logs(args):
    state = load_state(args.job)
    paths = [("stdout", state["log"])]
    if state["backend"] == "slurm" and state["log"].endswith(".out"):
        paths.append(("stderr", state["log"][:-len(".out")] + ".err"))
    parts = []
    for label, path in paths:
        parts.append(f"echo '== {label}: {path} =='")
        parts.append(f"tail -n {args.lines} {qr(path)} 2>/dev/null"
                     f" || echo '(no output yet)'")
    result = ssh(state["host"], "; ".join(parts), check=False)
    if result.returncode != 0:
        fail(f"cannot read logs: {result.stderr.strip()}", log=state["log"])
    print(result.stdout, end="")


def cmd_cancel(args):
    state = load_state(args.job)
    host = state["host"]
    if state["backend"] == "slurm":
        ssh(host, f"scancel {q(state['job_id'])}")
    elif state.get("session"):
        ssh(host, f"tmux kill-session -t {q(state['session'])}", check=False)
    else:
        ssh(host, f"kill {q(state['pid'])}", check=False)
    ok(name=args.job, cancelled=True)


def cmd_collect(args):
    state = load_state(args.job)
    job_state, exit_code = query_state(state)
    if job_state in ("running", "pending"):
        fail(f"job '{args.job}' is still {job_state}; collect after it finishes",
             state=job_state)
    dest = args.dest or f"./{args.job}"
    Path(dest).expanduser().parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["rsync", "-az", f"{state['host']}:{state['workdir']}/", dest.rstrip("/") + "/"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        fail(f"rsync failed: {result.stderr.strip()}")
    ok(name=args.job, state=job_state, exit_code=exit_code, dest=dest)


def cmd_probe(args):
    """Read-only cluster probe; prints raw sinfo/squeue/scontrol output."""
    host = args.host
    check = ssh(host, "true", check=False)
    if check.returncode != 0:
        fail(f"cannot reach '{host}': "
             f"{check.stderr.strip() or 'ssh failed'}; "
             f"timeout/no-route = not on intranet; "
             f"otherwise check ssh config (alias may not be named ikkem)")
    script = [
        "echo '== sinfo -s =='; sinfo -s",
        "echo; echo '== squeue =='; squeue",
    ]
    if args.partition:
        p = q(args.partition)
        script.append(f"echo; echo '== scontrol show partition {args.partition} =='; "
                      f"scontrol show partition {p}")
        script.append(
            f"echo; echo '== gres of first node in {args.partition} =='; "
            f"n=$(sinfo -p {p} -h -N -o %n | head -1); "
            'echo "node: $n"; '
            'scontrol show node "$n" | grep -E \'Gres|CfgTRES\' || true')
    result = ssh(host, "; ".join(script), check=False)
    if result.returncode != 0:
        fail(f"probe failed: {result.stderr.strip()}")
    print(result.stdout, end="")


def cmd_list(args):
    jobs = []
    if STATE_DIR.is_dir():
        for path in sorted(STATE_DIR.glob("*.json")):
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            jobs.append({"name": state.get("name"),
                         "backend": state.get("backend"),
                         "host": state.get("host"),
                         "submitted_at": state.get("submitted_at"),
                         "workdir": state.get("workdir")})
    ok(jobs=jobs)


def main():
    parser = argparse.ArgumentParser(
        prog="submit.py",
        description="Submit long-running jobs to compute backends (SLURM / SSH).")
    sub = parser.add_subparsers(dest="command", required=True)

    p_submit = sub.add_parser("submit", help="submit a job")
    p_submit.add_argument("--target", help="named target from submit-job.json")
    p_submit.add_argument("--backend", choices=["slurm", "ssh"])
    p_submit.add_argument("--host", help="ssh destination, e.g. user@login.cluster")
    p_submit.add_argument("--base-dir", dest="base_dir",
                          help="remote base directory (default: ~/submit-jobs)")
    p_submit.add_argument("--name", required=True, help="job name; this is the handle")
    p_submit.add_argument("--cmd", required=True, help="command to run remotely")
    p_submit.add_argument("--workdir", help="remote workdir (default: <base-dir>/<name>)")
    p_submit.add_argument("--src", help="local directory to rsync into the workdir")
    p_submit.add_argument("--exclude", action="append", default=[], metavar="PATTERN",
                          help="rsync exclude pattern for --src, repeatable "
                               "(e.g. --exclude .venv --exclude '__pycache__')")
    p_submit.add_argument("--time", help="slurm wall limit, e.g. 24:00:00 "
                          "(QOS default on ikkem is 2-00:00:00)")
    p_submit.add_argument("--partition", help="slurm partition")
    p_submit.add_argument("--cpus", type=int, help="slurm cpus-per-task")
    p_submit.add_argument("--mem", help="slurm memory, e.g. 32G")
    p_submit.add_argument("--gpus", type=int, help="slurm GPUs (--gres=gpu:N)")
    p_submit.add_argument("--gres", help="slurm raw gres spec, e.g. gpu:tesla:1 "
                          "(overrides --gpus; needed on clusters with typed/MIG gres)")
    p_submit.add_argument("--dry-run", action="store_true",
                          help="print the plan (incl. sbatch script) without executing")
    p_submit.set_defaults(func=cmd_submit)

    p_status = sub.add_parser("status", help="job state + exit code")
    p_status.add_argument("--job", required=True)
    p_status.set_defaults(func=cmd_status)

    p_logs = sub.add_parser("logs", help="print stdout+stderr log tails")
    p_logs.add_argument("--job", required=True)
    p_logs.add_argument("--lines", type=int, default=50)
    p_logs.set_defaults(func=cmd_logs)

    p_cancel = sub.add_parser("cancel", help="cancel a running/pending job")
    p_cancel.add_argument("--job", required=True)
    p_cancel.set_defaults(func=cmd_cancel)

    p_collect = sub.add_parser("collect", help="rsync remote workdir back locally")
    p_collect.add_argument("--job", required=True)
    p_collect.add_argument("--dest", help="local destination (default: ./<name>)")
    p_collect.set_defaults(func=cmd_collect)

    p_list = sub.add_parser("list", help="list locally tracked jobs (cached info)")
    p_list.set_defaults(func=cmd_list)

    p_probe = sub.add_parser("probe", help="read-only cluster probe "
                             "(sinfo/squeue/scontrol via ssh)")
    p_probe.add_argument("--host", required=True,
                         help="ssh destination (alias or user@host; do not assume 'ikkem')")
    p_probe.add_argument("--partition",
                         help="also show partition details and node gres")
    p_probe.set_defaults(func=cmd_probe)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
