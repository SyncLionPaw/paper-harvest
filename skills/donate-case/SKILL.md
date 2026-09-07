---
name: donate-case
version: "0.1.0"
description: 用户自愿把本地编程 agent（Kimi Code / Claude Code / Codex 等）的对话轨迹打包上传到对象存储服务器，用于捐赠案例。当用户说"捐赠这个对话"、"上传这个 case"、"donate this conversation"、"分享这次对话轨迹"时使用。上传前必须向用户展示打包内容并征得明确同意。
---

# Donate Case — 自愿捐赠对话轨迹

把一次编程 agent 会话的轨迹（完整对话与工具调用记录）打成 tar.gz，HTTP PUT 到捐赠服务器（对象存储）。所有操作通过 `scripts/donate.py` 完成。

支持的 agent 及本地轨迹位置（脚本自动探测，也可用 `--agent <name>` 限定）：

| agent | 轨迹位置 |
|-------|---------|
| `kimi-code` | `~/.kimi-code/sessions/<wd_*>/session_<uuid>/`（state.json + agents/**/wire.jsonl） |
| `claude-code` | `~/.claude/projects/<目录名>/<uuid>.jsonl`（含同名 sidecar 目录） |
| `codex` | `~/.codex/sessions/<年>/<月>/<日>/rollout-*.jsonl` |

## 铁律（先读这个）

1. **自愿原则：没有用户明确要求，绝不上传。** 即使用户提过"之后可以捐赠"，每次上传前仍须当场确认。
2. **上传前必须展示清单**：运行 `upload --dry-run`，把 agent、会话标题、包含文件、总大小给用户看，并提醒轨迹里可能含有对话中贴过的敏感内容（路径、密钥、代码、个人信息），请用户确认后再传。
3. **只碰轨迹目录**：只读上述 agent 的会话存储目录，不翻用户其他文件。kimi-code 默认不含 `logs/`，用户明确要求时才加 `--include-logs`。
4. 上传成功后把对象 key / URL 报告给用户。

## 1. 定位会话

脚本按 cwd 匹配各 agent 的会话记录（kimi-code 读 state.json，claude-code / codex 读 jsonl 头部）：

```bash
python3 "$SKILL_DIR/scripts/donate.py" list            # 当前目录的会话（所有 agent，按更新时间倒序）
python3 "$SKILL_DIR/scripts/donate.py" list --all      # 所有目录的会话
python3 "$SKILL_DIR/scripts/donate.py" --agent codex list --all   # 只看某个 agent
```

- 不传 `--session` 时，默认取**当前工作目录下最近更新**的会话（通常就是正在进行的这次对话）。
- 用户要捐赠别的会话：从 `list` 输出里取 session id（前缀即可），传 `--session <id>`；跨 agent 撞前缀时用 `--session <agent>:<id>` 消歧。

## 2. 预览并征得同意（每次必做）

```bash
python3 "$SKILL_DIR/scripts/donate.py" upload --dry-run [--session <id>]
```

把输出的 agent、文件清单和大小原样展示给用户，并明确询问："确认上传这次对话轨迹吗？其中包含完整对话内容和工具输出。" 得到肯定答复才继续；犹豫或拒绝就停，不劝说。

## 3. 上传

```bash
python3 "$SKILL_DIR/scripts/donate.py" upload [--session <id>] [--note "一句话说明这个 case 的价值"]
```

- `--note` 会写进压缩包里的 `donate-meta.json`（agent、捐赠时间、session id、cwd、备注），方便服务端整理；鼓励让用户补一句。
- 上传方式：`PUT <endpoint>/<agent>/<YYYY-MM-DD>/<session-id>.tar.gz`，`Content-Type: application/gzip`；配置了 token 时带 `Authorization: Bearer <token>`。

## 4. 配置 endpoint

服务器未部署或未配置时，脚本会报错退出——如实告诉用户"捐赠服务还没配置好"，**不要**自己搭服务或改协议。配置方式（任选其一）：

```bash
export DONATE_CASE_ENDPOINT='https://donate.example.com/cases'
export DONATE_CASE_TOKEN='...'        # 如需鉴权
```

或 `~/.config/donate-case/config.json`：

```json
{"endpoint": "https://donate.example.com/cases", "token": "..."}
```

## 备注

- 轨迹根目录可用 `--agent <name> --sessions-root <dir>` 覆盖（如 agent 装在非默认位置）。
- 其他 agent（Gemini CLI 等）的轨迹布局不同，不要猜路径硬传；有需求时在脚本里加一个 iterator。
- 打包产物在系统临时目录（`donate-case-*`），上传完无需清理。
