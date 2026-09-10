#!/usr/bin/env python3
"""LLM 网关接入排查：在用户机器上只读探测，产出一份可直接上报的报告。

沿着 DNS → TLS → 网关存活 → 鉴权 逐跳探一遍，把每一跳的原始证据记下来，
最后拼成一段可以整段转发给网关管理员的文本。纯标准库实现，不依赖任何第三方包。
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import socket
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

try:
    import ssl
except ImportError:  # 少数 Python 构建没编 ssl，此时 HTTPS 探测做不了
    ssl = None  # type: ignore[assignment]

DEFAULT_BASE_URL = "https://chenglab.xmu.edu.cn/llm/"
VPN_BASE_URL = "http://10.26.14.77/llm/"
TIMEOUT = 12

# 客户端常用来指向网关的环境变量。url 类记录取值，key 类只记录"在不在"——
# 报告要能转发给别人，明文密钥绝不能进去。
ENV_PROBES = [
    ("ANTHROPIC_BASE_URL", "url"),
    ("ANTHROPIC_AUTH_TOKEN", "secret"),
    ("ANTHROPIC_API_KEY", "secret"),
    ("OPENAI_BASE_URL", "url"),
    ("OPENAI_API_BASE", "url"),
    ("OPENAI_API_KEY", "secret"),
    ("LLM_BASE_URL", "url"),
    ("LLM_API_KEY", "secret"),
]

# 每一跳的原始证据，报告里原样带上——管理员看报文比看结论有用
EVIDENCE: list[tuple[str, str, str, str]] = []  # (请求行, 状态, 响应体, 备注)
ACTIVE_KEY: str | None = None  # 当前探测所用的 key，报告打码时二次兜底


# --------------------------------------------------------------------------
# 探测
# --------------------------------------------------------------------------

class NoRedirect(urllib.request.HTTPRedirectHandler):
    """不要自动跟随重定向：307/302 本身就是排查结论的一部分。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


# 密钥形态不止 "sk- + 字母数字"：OpenAI 的 sk-proj- 带连字符，base64 尾串会带 + / =，
# 有的厂商用点分段。字符类必须放宽，否则只会吃掉 sk- 前缀、把密钥正文原样漏出去。
_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-./+=]{3,}")


def _redact(text: str) -> str:
    """把文本里的密钥明文打掉。上报的报告可能被转发到群里。"""
    if not text:
        return text
    # 1. 匹配常见 sk- 形态的 API Key
    text = _KEY_RE.sub("sk-***REDACTED***", text)
    # 2. 如果用户使用的 key 并非 sk- 开头，但被服务端回显，此处做强制二次抹除
    if ACTIVE_KEY and len(ACTIVE_KEY) >= 4:
        text = text.replace(ACTIVE_KEY, "***REDACTED***")
    return text


def _http(method: str, url: str, api_key: str | None = None):
    """发一个不跟随重定向的请求，返回 (status, reason, body, location)。"""
    req = urllib.request.Request(url, method=method)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=TIMEOUT) as resp:
            body = resp.read(4096).decode("utf-8", "replace")
            return resp.status, resp.reason, body, resp.headers.get("Location")
    except urllib.error.HTTPError as e:
        body = e.read(4096).decode("utf-8", "replace")
        return e.code, e.reason, body, e.headers.get("Location")
    except urllib.error.URLError as e:
        return None, str(e.reason), "", None
    except (TimeoutError, socket.timeout):
        return None, "timeout", "", None


def _probe(method: str, url: str, api_key: str | None = None, note: str = ""):
    """发请求并留证。报告里会带上这次交换的原始报文。"""
    status, reason, body, loc = _http(method, url, api_key)
    shown = f"{status} {reason}" if status else f"失败：{reason}"
    if loc:
        shown += f"  →  {loc}"
    EVIDENCE.append((f"{method} {url}", shown, _redact(body.strip()), note))
    return status, reason, body, loc


def _check_dns(host: str, port: int) -> tuple[bool, str]:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        EVIDENCE.append((f"getaddrinfo({host}:{port})", "失败", str(e), "DNS 解析"))
        return False, f"DNS 解析失败：{e}"
    ips = sorted({i[4][0] for i in infos})
    detail = "解析到 " + ", ".join(ips)
    EVIDENCE.append((f"getaddrinfo({host}:{port})", detail, "", "DNS 解析"))
    return True, detail


def _check_tls(host: str, port: int) -> tuple[bool, str]:
    """取服务器证书，看签发者和剩余有效期（证书过期会让所有客户端一起挂）。"""
    if ssl is None:
        return True, "跳过：本机 python3 没有 _ssl 模块"
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
    except Exception as e:  # noqa: BLE001 - 排查工具，任何 TLS 异常都如实报
        EVIDENCE.append((f"TLS {host}:{port}", "握手失败", str(e), "证书检查"))
        return False, f"TLS 握手失败：{e}"
    issuer = dict(x[0] for x in cert.get("issuer", []))
    not_after = cert.get("notAfter")
    days = None
    if not_after:
        try:
            exp = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(
                tzinfo=timezone.utc
            )
            days = (exp - datetime.now(timezone.utc)).days
        except ValueError:
            pass
    who = issuer.get("organizationName") or issuer.get("commonName") or "?"
    EVIDENCE.append((f"TLS {host}:{port}", f"签发者 {who}",
                     f"notAfter={not_after}", "证书检查"))
    if days is None:
        return True, f"证书由 {who} 签发"
    if days < 0:
        return False, f"证书已过期 {-days} 天（{who}）"
    if days < 21:
        return True, f"证书 {days} 天后过期（{who}）—— 近期会集体报 TLS 错"
    return True, f"证书 {days} 天后过期（{who}）"


# 用户在机器上把 key 放在哪个变量里都算数：客户端实际的取用顺序排在前面。
# 不显式传 --api-key 时按这个顺序找，找到哪个就记进报告（方便管理员判断
# "客户端到底读没读到 key"）。
KEY_SOURCES = [
    "LLM_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
]


def _resolve_key(explicit: str | None) -> tuple[str | None, str | None]:
    """返回 (key, 来源变量名)。显式传入优先。"""
    if explicit and explicit.strip():
        return explicit.strip(), "--api-key"
    for name in KEY_SOURCES:
        val = os.environ.get(name)
        if val and val.strip():
            return val.strip(), name
    return None, None


def _disp_width(text: str) -> int:
    """终端里的显示宽度：CJK 及全角字符占两列，否则报告对不齐。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _collect_env() -> list[tuple[str, bool, str]]:
    """看用户机器上指向网关的环境变量：url 报取值，key 只报在不在。"""
    out = []
    for name, kind in ENV_PROBES:
        val = os.environ.get(name)
        if val is None:
            out.append((name, False, "未设置"))
        elif not val.strip():
            out.append((name, False, "已设置为空字符串"))
        elif kind == "secret":
            out.append((name, True, f"已设置（{len(val.strip())} 字符，值不记录）"))
        else:
            out.append((name, True, val.strip()))
    return out


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def run_probe(base: str, api_key: str | None):
    global ACTIVE_KEY
    ACTIVE_KEY = api_key
    EVIDENCE.clear()

    parsed = urllib.parse.urlparse(base)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    rows: list[tuple[str, bool, str]] = []
    fatal = False

    # 探针一律用规范化地址（结尾必带斜杠），否则会拼出 /llmhealth/... 这种假 404
    probe_base = base if base.endswith("/") else base + "/"

    # 1) base_url 形状：少结尾斜杠是个常见的配置坑，单独探一下裸路径
    if base.endswith("/"):
        rows.append(("base_url 结尾斜杠", True, "ok"))
    else:
        status, _reason, _body, loc = _probe("GET", base, note="裸路径（缺尾斜杠）")
        if status in (301, 302, 307, 308):
            detail = (
                f"缺少结尾 '/'：裸路径返回 {status} → {loc}"
                + ("（降级到明文 http，部分客户端会拒绝）" if loc and loc.startswith("http://") else "")
                + f"，建议写成 {probe_base}"
            )
        else:
            detail = f"缺少结尾 '/'，建议写成 {probe_base}"
        rows.append(("base_url 结尾斜杠", False, detail))

    # 2) DNS
    ok, detail = _check_dns(host, port)
    rows.append((f"DNS 解析 {host}", ok, detail))
    if not ok:
        fatal = True

    # 3) TLS（仅 https 有意义）
    if ok and parsed.scheme == "https":
        tls_ok, tls_detail = _check_tls(host, port)
        rows.append(("TLS 证书", tls_ok, tls_detail))

    # 4) 网关存活探针（免鉴权）
    if not fatal:
        status, reason, body, loc = _probe("GET", probe_base + "health/liveliness",
                                           note="存活探针（免鉴权）")
        if status == 200 and "alive" in body:
            rows.append(("网关存活 /health/liveliness", True, f"200 {body.strip()}"))
        elif status in (301, 302, 307, 308):
            rows.append((
                "网关存活 /health/liveliness",
                False,
                f"{status} 重定向到 {loc} —— 请求没落到网关，检查 base_url 路径前缀（应为 /llm/）",
            ))
            fatal = True
        elif status is None:
            rows.append(("网关存活 /health/liveliness", False, f"连不上：{reason}"))
            fatal = True
        else:
            rows.append((
                "网关存活 /health/liveliness",
                False,
                f"HTTP {status}（预期 200 'I'm alive!'，说明流量没到 LiteLLM）",
            ))
            fatal = True

    # 5) 鉴权（需要 key；无 key 时只报"未检测"）
    if not fatal:
        if api_key:
            status, _reason, body, _loc = _probe("GET", probe_base + "health", api_key,
                                                 note="鉴权探针（带 key）")
            if status == 200:
                rows.append(("API Key 鉴权 /health", True, "200，key 有效"))
            elif status == 401:
                low = body.lower()
                if "no api key passed" in low:
                    hint = "请求没带上 Authorization 头（客户端没读到 key 环境变量）"
                elif "invalid proxy server token" in low:
                    hint = "key 本身无效（被吊销 / 抄错 / 不是这个网关签发的）"
                else:
                    hint = "401，见下方原始报文"
                rows.append(("API Key 鉴权 /health", False, f"401 —— {hint}"))
            else:
                rows.append(("API Key 鉴权 /health", False, f"HTTP {status}"))
        else:
            rows.append((
                "API Key 鉴权 /health",
                True,
                "未检测：--api-key 和环境变量（"
                + " / ".join(KEY_SOURCES)
                + "）里都没有 key —— 无法区分「没带 key」和「key 无效」",
            ))

    return rows, fatal


def _conclusion(rows, fatal) -> str:
    failed = [name for name, ok, _ in rows if not ok]
    if fatal:
        return (
            f"公网入口这条链路断了（{len(failed)} 项异常）。"
            "可先走 VPN 备用链路：连接校园网 VPN 后，"
            f"把 base_url 改成直连内网 {VPN_BASE_URL}。"
        )
    if failed:
        return (
            f"网关本身可达，但有 {len(failed)} 项异常：{', '.join(failed)}。"
            "这些都发生在客户端侧，改配置即可；改完重跑确认。"
        )
    return "网关可达，接入链路正常。请求级报错请转网关管理员看在线日志。"


def _report(base: str, client: str | None, rows, fatal,
            key_source: str | None) -> str:
    """拼一份可以直接整段转发的报告。"""
    lines = [
        "===== LLM 网关接入体检报告 =====",
        f"时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"机器：{platform.system()} {platform.release()} / Python {platform.python_version()}",
        f"探测地址：{base}",
    ]
    if client:
        lines.append(f"客户端：{client}")
    lines.append(
        f"携带 API Key：{'是，来源 ' + key_source + '（仅用于鉴权探测，值不记录）' if key_source else '否'}"
    )

    lines.append("")
    lines.append("-- 本机相关环境变量 --")
    for name, is_set, detail in _collect_env():
        lines.append(f"  {'✓' if is_set else '·'}  {name} = {detail}")

    lines.append("")
    lines.append("-- 逐跳探测结果 --")
    width = max(_disp_width(name) for name, _, _ in rows)
    for name, ok, detail in rows:
        pad = " " * (width - _disp_width(name))
        lines.append(f"  {'✓' if ok else '✗'}  {name}{pad}  {detail}")

    lines.append("")
    lines.append("-- 原始证据 --")
    for req, status, body, note in EVIDENCE:
        lines.append(f"  {req}")
        lines.append(f"    {status}" + (f"   [{note}]" if note else ""))
        if body:
            for ln in body.splitlines()[:8]:
                lines.append(f"    | {ln}")

    lines.append("")
    lines.append(f"-- 结论 --\n  {_conclusion(rows, fatal)}")
    lines.append("")
    lines.append("（报告不含 API Key 明文；报文里的 sk- 已打码。"
                 "管理员可用上面的 Key Hash 定位具体是哪把 key。）")
    # 最后整体再过一遍打码：环境变量、URL、客户端名等入口也可能混进密钥形态的串，
    # 出网前统一兜一次。
    return _redact("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LLM 网关接入排查：只读探测并产出一份可上报的报告"
    )
    parser.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL),
                        help=f"网关地址，默认 {DEFAULT_BASE_URL}")
    parser.add_argument("--api-key", default=None,
                        help="网关 API Key；不给则依次从 "
                             + " / ".join(KEY_SOURCES) + " 里找，都找不到就只测免鉴权的 liveliness")
    parser.add_argument("--client", default=None,
                        help="出问题的客户端，如 'Claude Code 2.1'、'Codex'；会记进报告")
    parser.add_argument("--report", metavar="PATH", default=None,
                        help="把报告写到文件（不给则打到 stdout）")
    args = parser.parse_args()

    base_url = (args.base_url or "").strip()
    parsed = urllib.parse.urlparse(base_url)
    if not parsed.hostname:
        print(f"--base-url 不是个完整地址：{base_url!r}"
              "（要带 scheme，如 https://.../llm/）", file=sys.stderr)
        return 2
    if parsed.scheme == "https" and ssl is None:
        print("本机 Python 缺少 ssl 模块，无法做 HTTPS 探测；"
              "换一个带 SSL 的 Python 运行。", file=sys.stderr)
        return 2

    api_key, key_source = _resolve_key(args.api_key)
    rows, fatal = run_probe(base_url, api_key)
    text = _report(base_url, args.client, rows, fatal, key_source)

    if args.report:
        report_path = os.path.expanduser(args.report)
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
        print()
        print(text)
        print(f"\n[✓] 报告已保存至: {report_path}")
    else:
        print()
        print(text)

    return 1 if any(not ok for _, ok, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
