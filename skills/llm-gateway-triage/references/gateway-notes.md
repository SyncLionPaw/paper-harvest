# 网关实测快照

**入口：`https://chenglab.xmu.edu.cn/llm/`** —— 这是唯一以它为准的地址。
旧域名 `chenggroup.xmu.edu.cn` 指向同一台网关（同一 IP、同一证书），但**会逐步下线**，
不要再用，也不要配进客户端。

以下全部是 **2026-09-10 对 chenglab 实探**的结果。网关会升级、配置会改，
**以现场探测为准**，发现不符就更新本文。

## 端点行为

| 请求 | 结果 | 说明 |
|------|------|------|
| `GET https://chenglab.xmu.edu.cn/llm` | `301` → `http://chenglab.xmu.edu.cn/llm/` | 缺尾斜杠，**且降级到明文 http**，容易让客户端直接失败 |
| `GET https://chenglab.xmu.edu.cn/llm/` | `200 text/html` | 网关首页 / UI |
| `GET .../llm/ui/` | `200 text/html` | LiteLLM 管理界面，可用于查在线请求日志 |
| `GET .../llm/health/liveliness` | `200`，body `"I'm alive!"` | **免鉴权**，最适合当存活探针 |
| `GET .../llm/health` | `401`（无 key） | 需要 key，用来验 key 是否有效 |
| `GET .../llm/v1/models` | `401`（无 key / 无效 key） | OpenAI 兼容列表接口 |
| `GET http://.../llm/health/liveliness` | `302` → https | 明文入口会跳回 https；不要配明文地址 |

裸路径那次重定向的状态码在旧域名上是 `307`、在 chenglab 上是 `301`——
判断时按"是 3xx 且 Location 指向明文 http"来认，别死记某个码。

## 两种 401 的报文区别（重要）

无 key：

```json
{"error":{"message":"Authentication Error, No api key passed in.","type":"auth_error","param":"None","code":"401"}}
```

无效 key：

```json
{"error":{"message":"Authentication Error, Invalid proxy server token passed. Received API Key = sk-...robe, Key Hash (Token) =5ae9...c3a. Unable ...","type":"token_not_found_in_db","param":"key","code":"401"}}
```

前者是客户端**没把 key 发出去**（环境变量没读到 / header 名写错），后者是**key 本身不对**
（吊销、抄错、不是这个网关签发的）。报文里带 Key Hash，报给管理员时这个值最有用——
能直接定位是哪一把 key，而且它不是密钥本身，可以安全转发（脚本产出的报告里
`sk-` 开头的明文会被自动打码，Key Hash 保留）。

## 可用模型

`GET /llm/v1/models`（带 key）返回网关支持的模型清单，2026-09-10 实探有 22 个，
含 `claude-opus-5` / `claude-sonnet-5` / `deepseek-v4-pro` / `glm-5.3` / `gpt-6-astra` /
`kimi-k3` / `gemini-3.8-flash` 等，另有一个 `auto_router` 路由项。

**清单会随网关调整变化，不要写死**——需要时现查。用户报"模型名不对"时，
先确认他用的名字在不在这个清单里。

## 网络与证书

- DNS：`chenglab.xmu.edu.cn` → `219.229.81.240`（厦大应用网关 applg219；
  旧域名 `chenggroup` 也解析到这里）
- TLS：TrustAsia Technologies, Inc. 签发，`notAfter = Jan 24 07:59:59 2027 GMT`
  （实探时剩余 135 天）
- 备用链路：拨校园网 VPN 后直连内网 `http://10.26.14.77/llm/`

## 请求级排查去哪看

接入层全绿、但某个请求本身报错时，本 skill 到此为止。网关自己带管理界面：

- `https://chenglab.xmu.edu.cn/llm/ui/` —— LiteLLM Admin UI，可按 user / model /
  时间筛在线请求记录，看每次请求的 status、耗时、token、报错详情。

查这些需要管理员权限。让用户去找网关管理员，不要试图绕过鉴权。

## 关于这份文档

- `topology.html` 是从 `~/llm_logs/` 拷来的架构图副本，主机名已同步成 `chenglab`，
  因此与上游原图有差异；架构本身（LiteLLM → nonlinear / DeepSeek）未变。
- 本文件里的数值只在标注的实测日期有效。改网关配置后请重跑脚本并更新此文件。
