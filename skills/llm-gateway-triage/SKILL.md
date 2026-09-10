---
name: llm-gateway-triage
version: "0.1.0"
description: 排查厦大 chenglab LLM 网关（LiteLLM）的客户端接入故障：连不上、404/401/超时、证书告警、key 不生效。在用户机器上只读地跑一遍 DNS → TLS → 网关存活 → 鉴权，产出可直接转给网关管理员的上报报告。当用户说"LLM 网关连不上/报错/超时"、"API key 不管用"、"claude code 连不上模型"、"请求发不出去"时使用。
---

# LLM 网关接入排查

组里的 LLM 流量走厦大公网入口 `https://chenglab.xmu.edu.cn/llm`，反向代理到校园网内的
LiteLLM 节点（`10.26.14.77`），再由它转发给 nonlinear 后端或直连 DeepSeek。
完整拓扑见 [references/topology.html](references/topology.html)，实测快照见
[references/gateway-notes.md](references/gateway-notes.md)。

**范围**：只管"请求有没有到网关、为什么被挡在门外"，也就是客户端侧。它的产物是
**一份报告，不是修好的客户端**——在用户机器上只读地探一遍，把证据收集起来，
交给能改网关的人。请求进了网关之后的报错（模型返回不对、上游 5xx、计费异常），
本 skill 只能确认接入层没问题，然后指向网关 UI `/llm/ui/` 看在线请求记录。

**关键做法**：沿着链路一跳一跳走，别一上来就猜 key 或模型名。脚本把
DNS → TLS → 网关存活 → 鉴权 四跳依次探一遍，先看它说断在哪一跳，再谈修。

## 铁律（先读这个）

1. **先体检，再下结论**。跑脚本拿到证据再说话；不要凭用户一句"连不上"就断言是
   key 问题，或让用户重装客户端。
2. **只诊断，不改用户的配置**。脚本是只读的（几个 GET）。发现问题就写进报告，
   改不改由用户和管理员决定。
3. **忠实报告**。某项没检测（比如没给 key）就说"未检测"，不要脑补成"正常"。
   报告里的原始报文照实带，不要替网关"美化"错误信息。
4. **别把密钥传出去**。报告会外发，只带 Key Hash，不带 Key 明文——脚本已自动打码，
   不要为了"方便排查"手工把 key 贴进报告或对话里。
5. **内网地址只在 VPN 内可达**。`10.26.14.77` 连不上是正常的，不要反复重试或找
   别的入口；先问用户是否已拨 VPN。
6. **不碰网关日志数据**。查在线请求记录是网关管理员的事，本 skill 只读探活接口。

## 1. 跑体检，产出报告

```bash
python3 "$SKILL_DIR/scripts/diagnose.py"
python3 "$SKILL_DIR/scripts/diagnose.py" --client "Claude Code 2.1"
python3 "$SKILL_DIR/scripts/diagnose.py" --base-url <用户配的地址>    # 用户配的不是默认地址时
python3 "$SKILL_DIR/scripts/diagnose.py" --api-key sk-xxx           # 环境变量里没有 key 时手动指定
```

**产物是一份可直接转发的报告**，包含：本机环境变量实际取值、逐跳探测结果、
每一次请求的**原始报文**、以及结论。整段复制给网关管理员即可，不需要用户自己总结。

- `--client`：记下出问题的是哪个客户端，管理员常需要这个。
- `--report PATH`：写到文件；不给就打到 stdout。
- 报告**不含 API Key 明文**（报文里的 `sk-` 已打码），但保留 Key Hash——管理员靠它
  定位是哪把 key，且 Key Hash 不是密钥本身，可以安全转发。

**key 从哪来**：不传 `--api-key` 时脚本按 `LLM_API_KEY` → `ANTHROPIC_AUTH_TOKEN` →
`ANTHROPIC_API_KEY` → `OPENAI_API_KEY` 的顺序自动找（就是客户端自己在用的那把），
并在报告里注明来源——管理员据此能判断"客户端到底读没读到 key"。都找不到就跳过鉴权探测。
拿到 key 才会打 `/health`，这是**唯一能区分"没带 key"和"key 无效"**的办法。
地址可用 `--base-url` 或 `LLM_BASE_URL` 覆盖。

退出码：`0` 全绿，`1` 有异常项，`2` 环境问题（解释器或参数不对）——脚本里可直接判。

## 2. 读结果：每个 ✗ 对应什么

| ✗ 的项 | 含义 | 给用户的建议 |
|--------|------|-------------|
| DNS 解析失败 | 域名没解析出来 | 确认本机联网 / DNS；仍不行走 VPN 备用链路 |
| TLS 证书 | 证书过期或握手失败 | 证书过期会**所有客户端一起挂**，找网关管理员 |
| 网关存活 | 请求没落到 LiteLLM | 看返回码：404 = 路径前缀写错；3xx = 路径前缀不对被重定向；连不上 = 公网入口断 |
| base_url 结尾斜杠 | 少了 `/`，裸路径被 3xx 降级到**明文 http** | 改成带结尾斜杠的地址，见下 |
| API Key 鉴权 | 401 | 按报文区分：`No api key passed in` = 没带 key（客户端没读到环境变量）；`Invalid proxy server token` = key 本身无效 |

**尾斜杠这个坑值得单独说**：`https://chenglab.xmu.edu.cn/llm`（无斜杠）会被厦大应用网关
3xx 跳到 `http://` 明文的 `/llm/`，明文再 302 回 https（实测 chenglab 返回 301，
旧域名返回 307，别死记某个码）。部分客户端不接受明文降级、或干脆不跟随重定向，
表现就是"莫名连不上"。统一写成 **`https://chenglab.xmu.edu.cn/llm/`**。

**入口域名换过**：唯一有效的是 `chenglab.xmu.edu.cn`；旧域名 `chenggroup.xmu.edu.cn`
指向同一台网关但**正在下线**。用户机器上残留的旧配置是典型的"只有我连不上"。
脚本会把本机 `ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL` 等的实际取值打进报告，
先比对是不是还指着旧域名。

## 3. 公网入口断了时：VPN 备用链路

脚本判定为致命故障时会自动打出这段建议，转述给用户即可：

1. 先连接校园网 VPN
2. 把 base_url 改成直连内网 `http://10.26.14.77/llm/`

不要在用户没连 VPN 时去探内网地址——一定超时，得不到任何结论。

## 备注

- 脚本里的探测目标、判断分支和错误文案都是**实测**来的（见 references/gateway-notes.md），
  但网关会升级、配置会改；如果脚本的判断和实际现象对不上，以实测为准，并把新发现
  补进 `references/gateway-notes.md`。
- 需要网关管理员权限的操作（查在线日志、看 key 的 hash、重启服务）脚本做不到，
  让用户去找管理员，不要试图绕过。
