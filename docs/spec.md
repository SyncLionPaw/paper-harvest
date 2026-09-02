# paper-harvest 产品规格

## 1. 项目概述

`paper-harvest` 是一个面向用户和 agent 的论文资料收集工具。

用户给出一条论文链接或一个本地 PDF，工具负责把论文资料整理成统一目录，尽量产出：

- 原始 PDF
- LaTeX 源码
- Markdown
- 结构化结果清单

工具的核心目标是“一条命令拿到可继续使用的文章资料包”，适合：

- 用户自己在终端里直接运行
- agent 通过 `uvx` 直接调用
- 后续自动化流程继续消费产出目录

命令用法、安装方式和运行示例见仓库根目录 `README.md`。Agent 按需参考见 `skills/paper-harvest/references/`。

## 2. 目标用户

### 2.1 直接用户

- 需要快速整理论文资料的研究者
- 需要把论文转换成可编辑 Markdown 的读者
- 希望统一保存 PDF、源码和解析结果的用户

### 2.2 Agent 用户

- 需要通过命令行稳定抓取论文资料的 agent
- 需要结构化输出结果，继续执行摘要、翻译、索引或知识库写入的自动化流程

## 3. 核心目标

### 3.1 必须满足

1. 用户可以直接通过 `uvx` 运行工具。
2. 输入一条链接或一个本地 PDF 后，工具可以创建统一文章目录。
3. 工具优先产出 PDF。
4. 工具在来源支持时尝试产出 LaTeX 源码。
5. 工具在配置了 MinerU token 时产出 Markdown。
6. 工具输出结构化结果，便于 agent 判断每一步状态。
7. 某一步失败时，工具尽量保留已成功的结果，并给出清晰状态。

### 3.2 体验目标

1. 默认命令足够短，适合复制粘贴。
2. 默认输出目录明确、可预测。
3. 出错信息可读，用户能知道下一步怎么补齐。
4. 对 agent 来说，输出格式稳定，避免依赖脆弱的终端文本解析。

## 4. 输入范围

工具支持以下输入：

- arXiv 论文链接，例如 `https://arxiv.org/abs/2403.18074`
- 本地 PDF 文件

后续可扩展输入：

- 其他学术站点链接
- 普通网页文章链接
- 公众号文章链接

## 5. 标准输出

每篇文章对应一个独立目录，默认直接创建在目标目录下：

```text
<article_id>/
  pdf/
  tex/
  md/
  harvest_result.json
```

### 5.1 `pdf/`

保存原始 PDF。

建议文件命名：

```text
pdf/<article_id>.pdf
```

### 5.2 `tex/`

保存论文源码资料。

对于 arXiv，至少包括：

```text
tex/<archive-file>
tex/source/
```

### 5.3 `md/`

保存 Markdown 解析结果。

建议包括：

```text
md/<article_id>.md
md/assets/
md/mineru.zip
md/mineru_result.json
```

### 5.4 `harvest_result.json`

保存结构化执行结果，至少包含：

- 工具名
- 文章标识
- 文章目录
- `pdf` 步骤状态
- `tex` 步骤状态
- `md` 步骤状态
- 结果文件路径

步骤状态取值建议：

- `success`
- `skipped`
- `failed`

## 6. 标准行为

### 6.1 默认执行流程

用户执行：

```bash
uvx paper-harvest '<source>'
```

工具按顺序执行：

1. 识别文章标识
2. 创建文章目录
3. 获取 PDF
4. 如果来源支持，获取 LaTeX 源码
5. 如果具备 MinerU token，生成 Markdown
6. 写出 `harvest_result.json`
7. 在终端打印简洁结果

### 6.2 PDF 行为

- 对 arXiv `abs` 链接，工具应自动转换为 PDF 下载地址
- 对本地 PDF，工具应复制到文章目录

### 6.3 TEX 行为

- 对 arXiv 链接，工具应尝试下载源码包并解压
- 对非 arXiv 来源，可以直接标记为 `skipped`

### 6.4 Markdown 行为

- Markdown 由 MinerU 负责生成
- 输入应优先使用本地 PDF
- 图片资源应放到 `md/assets/`
- 工具应生成适合继续阅读和继续加工的 Markdown 目录
- 默认优先使用 MinerU 精准解析 API
- 当未配置 token，且输入满足轻量接口限制时，工具应尝试回退到 MinerU Agent 轻量解析 API

## 7. 优雅失败要求

这是一个面向 agent 的工具，失败策略必须稳定。

### 7.1 总体原则

1. 单个步骤失败，不应直接破坏整个文章目录。
2. 已经成功的步骤结果应保留。
3. 失败信息应收口到结构化结果里。
4. 可恢复的缺失条件优先标记为 `skipped`。

### 7.2 典型场景

#### MinerU token 缺失

预期行为：

- `pdf` 正常完成
- `tex` 正常完成或按条件跳过
- 如果输入满足轻量接口限制，先尝试 Agent 轻量解析 API
- 轻量接口成功时，`md` 正常完成
- 轻量接口不适用或调用失败时，`md` 标记为 `skipped` 或 `failed`
- 返回清晰消息，提示如何配置 token，或说明轻量接口限制

#### 非 arXiv 链接

预期行为：

- 直接作为输入非法处理
- 返回清晰错误信息，说明当前版本只接受 arXiv 链接和本地 PDF

#### TEX 下载失败

预期行为：

- `pdf` 保留
- `md` 继续执行
- `tex` 标记为 `failed`

#### Markdown 生成失败

预期行为：

- `pdf` 与 `tex` 保留
- `md` 标记为 `failed`
- 返回可读错误信息

## 8. 终端输出要求

工具在普通模式下应输出简洁摘要，至少包括：

- 文章目录
- PDF 结果
- TEX 结果
- Markdown 结果
- `harvest_result.json` 路径

工具在 `--json` 模式下应输出稳定 JSON，适合 agent 直接消费。

## 9. 命令行要求

### 9.1 基本命令

```bash
uvx paper-harvest '<source>'
```

### 9.2 必要参数

- `--target-dir`：指定文章目录生成的目标目录
- `--name`：指定文章目录名
- `--skip-tex`：跳过源码下载
- `--skip-md`：跳过 Markdown 生成
- `--force`：覆盖已有 Markdown 目录
- `--json`：输出结构化 JSON

### 9.3 分发要求

工具需要支持以下运行方式：

1. 仓库内调试：

```bash
uv run main.py '<source>'
```

2. 仓库路径分发：

```bash
uvx --from /path/to/repo paper-harvest '<source>'
```

3. Git 仓库分发：

```bash
uvx --from git+https://<repo-url> paper-harvest '<source>'
```

4. 包源分发：

```bash
uvx paper-harvest '<source>'
```

## 10. 对 agent 的接口约束

为了方便 agent 使用，这个工具需要满足以下要求：

1. 命令退出码语义稳定。
2. `--json` 输出字段尽量向后兼容。
3. 步骤状态要显式，不让上层猜测。
4. 默认目标目录固定为当前工作目录。
5. 结果路径全部写入 manifest，避免上层自行拼接路径。

## 11. 非功能要求

### 11.1 可维护性

- 各步骤职责分开：`pdf`、`tex`、`md`
- 目录布局逻辑集中管理
- 对外命令入口单一

### 11.2 可发布性

- 项目应支持标准 Python 打包
- 可构建 wheel 和 sdist
- 可通过 `uvx` 直接执行

### 11.3 可扩展性

- 后续可以接更多站点解析逻辑
- 后续可以增加元数据抓取
- 后续可以增加引用信息、摘要、标签等产物

## 12. 当前范围之外

以下内容不属于本期必须范围：

- 学术元数据深度抽取
- 自动摘要与翻译
- 引文网络分析
- 大规模批量调度平台
- 站点登录态管理

这些能力可以在后续规格中继续扩展。

## 13. 技术选型

这一部分描述工程实现所采用的技术方案，算法规则或第三方服务内部能力见各自文档。

### 13.1 语言与运行时

- 语言：Python
- 版本要求：Python `>= 3.9`
- 执行方式：优先支持 `uv run` 与 `uvx`

选择原因：

- Python 适合快速组织命令行工具和文件处理流程
- 标准库已经覆盖 HTTP、压缩包解压、路径管理、JSON 输出等核心需求
- 与 `uv` 配合后，分发和运行路径更短，适合直接给用户和 agent 使用

### 13.2 打包与分发

- 打包配置：`pyproject.toml`
- 构建后端：`setuptools.build_meta`
- 分发产物：`wheel` 与 `sdist`
- 对外命令：`paper-harvest`

选择原因：

- 兼容标准 Python 包发布流程
- 直接支持 `uv build`
- 能满足 `uvx --from <repo>` 和后续包源发布

### 13.3 CLI 技术方案

- CLI 采用标准库 `argparse`
- 主命令入口放在 `paper_harvest/cli.py`
- 仓库兼容入口保留 `main.py`

选择原因：

- 依赖最少，减少分发故障面
- 参数结构简单，当前不需要引入更重的 CLI 框架
- 对 agent 来说，行为更稳定，启动依赖更少

### 13.4 网络请求

- 优先使用 Python 标准库 `urllib.request`
- 不额外引入 `requests`

选择原因：

- 避免增加三方依赖
- 满足 PDF 下载、arXiv 源码下载、MinerU API 调用场景
- 对 uvx 场景更轻，冷启动更直接

### 13.5 目录与文件组织

- 文章目录布局由统一模块负责
- 标准目录结构固定为 `pdf`、`tex`、`md`
- 每篇文章输出一份 `harvest_result.json`

选择原因：

- 避免每个子模块各自拼路径
- 降低上层 agent 对目录规则的记忆成本
- 让后续扩展元数据、标签、摘要时保持一致目录语义

### 13.6 Markdown 生成

- Markdown 生成能力使用 MinerU
- 优先使用精准解析 API
- 在没有 token 的场景下，支持 Agent 轻量解析 API 作为回退
- 本工具只负责调用、落盘和整理结果

选择原因：

- 当前需求重点是“一键收集整理论文资料”
- PDF 转 Markdown 属于外部能力接入，工程侧重点是稳定接入和结果组织
- 轻量接口更适合 `uvx` 和 agent 的即开即用场景

轻量接口约束需要明确写入实现：

- 无需 token，但会按 IP 限频
- 单文件，不支持批量
- 文件大小限制较小
- 页数限制较小
- 输出为 Markdown 链接，不提供精准解析 API 那样的完整 zip 结果

### 13.7 结构化输出

- 终端输出提供人类可读摘要
- `--json` 提供结构化 JSON
- `harvest_result.json` 提供文件级清单

选择原因：

- 同时覆盖用户终端使用和 agent 自动化使用
- 降低上层解析自然语言输出的脆弱性

## 14. 实现方案

### 14.1 包结构

建议按以下结构组织：

```text
paper_harvest/
  cli.py

core/
  article_layout.py
  url/
    parse.py
  pdf/
    download.py
  md/
    mineru.py
  tex/
    arxiv.py
```

职责划分：

- `paper_harvest/cli.py`
  - 命令行参数解析
  - 执行编排
  - 顶层错误收口
  - 普通输出和 JSON 输出

- `core/article_layout.py`
  - 统一文章目录模型
  - 负责 `pdf`、`tex`、`md` 目录创建
  - 负责 `article_id` 规范化

- `core/url/parse.py`
  - 统一处理输入源解析
  - 识别链接类型和来源类型
  - 提取 arXiv id、文件名候选、标准化 URL
  - 为后续 `pdf`、`tex`、`md` 步骤提供统一输入语义

- `core/pdf/download.py`
  - 下载或保存 PDF
  - 支持 arXiv `abs` 链接到 PDF 链接的转换

- `core/md/mineru.py`
  - 调用 MinerU
  - 下载解析结果
  - 规范化 Markdown 与图片资源
  - 把结果写到 `md/`
  - 负责精准解析 API 与轻量解析 API 的策略切换

- `core/tex/arxiv.py`
  - 识别 arXiv id
  - 下载 arXiv 源码包
  - 解压源码到 `tex/source/`

### 14.2 主流程实现

主命令接收到输入后，建议按以下顺序执行：

1. 解析输入源
2. 标准化 URL 或本地文件路径
3. 推断或接收 `article_id`
4. 创建文章目录
5. 先完成 PDF 步骤
6. 再尝试 TEX 步骤
7. 再尝试 Markdown 步骤
8. 汇总步骤状态
9. 输出 `harvest_result.json`
10. 根据参数输出普通摘要或 JSON

这样设计的原因：

- URL 解析逻辑集中后，来源识别和后续步骤可以解耦
- PDF 是整个流程的公共基础
- TEX 和 Markdown 都可以围绕 PDF/文章目录继续工作
- 即便后续步骤失败，也能保留前面已经完成的结果

### 14.3 article_id 生成规则

建议规则：

- 用户显式传 `--name` 时，以 `--name` 为准
- arXiv 链接优先使用 arXiv id
- 直接 PDF 链接优先使用文件名
- 本地 PDF 优先使用文件名
- 最终统一做语义化清洗，转换为目录安全格式

目标：

- 保证目录名稳定
- 避免特殊字符导致路径问题
- 尽量保留用户可识别的文章标识

### 14.4 统一数据结构定义

为了让 CLI、各步骤模块和上层 agent 使用一致的数据语义，建议定义统一的数据结构。

这里描述工程侧对象设计，字段规则以可扩展、可序列化、可直接写入 JSON 为目标。

#### 14.4.1 ParsedSource

`ParsedSource` 表示输入源解析结果，是 `url` 层输出给后续模块的标准对象。

建议字段：

- `raw_input`
  - 用户原始输入
- `normalized_input`
  - 标准化后的输入
- `input_kind`
  - 输入类型，例如 `url`、`local_pdf`
- `source_kind`
  - 来源类型，例如 `arxiv`、`direct_pdf`、`generic_html`、`local_pdf`
- `article_id_candidate`
  - 推断出的文章标识候选
- `pdf_url`
  - PDF 下载候选地址，没有时为 `null`
- `tex_url`
  - TEX 下载候选地址，没有时为 `null`
- `local_path`
  - 本地文件路径，没有时为 `null`
- `metadata`
  - 预留扩展字段，用于保存额外来源信息

建议示例：

```json
{
  "raw_input": "https://arxiv.org/abs/2403.18074",
  "normalized_input": "https://arxiv.org/abs/2403.18074",
  "input_kind": "url",
  "source_kind": "arxiv",
  "article_id_candidate": "2403_18074",
  "pdf_url": "https://arxiv.org/pdf/2403.18074.pdf",
  "tex_url": "https://arxiv.org/src/2403.18074",
  "local_path": null,
  "metadata": {
    "arxiv_id": "2403.18074"
  }
}
```

#### 14.4.2 StepResult

`StepResult` 表示单个步骤的执行结果，适用于 `pdf`、`tex`、`md`。

建议字段：

- `status`
  - `success`、`skipped`、`failed`
- `message`
  - 面向用户和 agent 的简短说明
- `path`
  - 该步骤最重要的结果路径，没有时为 `null`
- `artifacts`
  - 该步骤产生的附加文件列表
- `error_code`
  - 预留的错误码，没有时为 `null`

建议示例：

```json
{
  "status": "success",
  "message": "pdf collected",
  "path": "2403_18074/pdf/2403_18074.pdf",
  "artifacts": [
    "2403_18074/pdf/2403_18074.pdf"
  ],
  "error_code": null
}
```

#### 14.4.3 HarvestResult

`HarvestResult` 表示一次完整抓取任务的汇总结果。

建议字段：

- `tool_name`
  - 工具名，例如 `paper-harvest`
- `article_id`
  - 文章目录标识
- `article_dir`
  - 文章根目录
- `source`
  - `ParsedSource`
- `pdf`
  - PDF 步骤结果
- `tex`
  - TEX 步骤结果
- `md`
  - Markdown 步骤结果
- `manifest_path`
  - 最终 manifest 路径

建议示例：

```json
{
  "tool_name": "paper-harvest",
  "article_id": "2403_18074",
  "article_dir": "2403_18074",
  "source": {
    "raw_input": "https://arxiv.org/abs/2403.18074",
    "normalized_input": "https://arxiv.org/abs/2403.18074",
    "input_kind": "url",
    "source_kind": "arxiv",
    "article_id_candidate": "2403_18074",
    "pdf_url": "https://arxiv.org/pdf/2403.18074.pdf",
    "tex_url": "https://arxiv.org/src/2403.18074",
    "local_path": null,
    "metadata": {
      "arxiv_id": "2403.18074"
    }
  },
  "pdf": {
    "status": "success",
    "message": "pdf collected",
    "path": "2403_18074/pdf/2403_18074.pdf",
    "artifacts": [
      "2403_18074/pdf/2403_18074.pdf"
    ],
    "error_code": null
  },
  "tex": {
    "status": "success",
    "message": "tex collected",
    "path": "2403_18074/tex/source",
    "artifacts": [
      "2403_18074/tex/arXiv-2403.18074v2.tar.gz",
      "2403_18074/tex/source"
    ],
    "error_code": null
  },
  "md": {
    "status": "skipped",
    "message": "md skipped because MinerU token is not configured",
    "path": null,
    "artifacts": [],
    "error_code": null
  },
  "manifest_path": "2403_18074/harvest_result.json"
}
```

#### 14.4.4 ArticleLayout

`ArticleLayout` 表示目录布局对象，供内部模块共享，不一定直接暴露给最终用户。

建议字段：

- `article_id`
- `article_dir`
- `pdf_dir`
- `tex_dir`
- `md_dir`

这个对象主要负责：

- 统一目录创建
- 避免不同模块各自拼接路径
- 保证 `pdf`、`tex`、`md` 的输出位置一致

#### 14.4.5 设计约束

这些对象建议满足以下约束：

1. 字段命名语义稳定
2. 可以直接序列化为 JSON
3. 路径字段使用字符串对外输出
4. 允许后续新增字段，但已有字段含义保持不变
5. `HarvestResult` 是对外主结果对象

这样做的价值：

- CLI 输出和 manifest 可以共享同一套结果模型
- agent 不需要解析终端自然语言
- 后续新增步骤时可以沿用同一个结果结构

#### 14.4.6 TargetDir

`TargetDir` 表示文章目录的上一级目标目录。

约束：

- CLI 参数名使用 `--target-dir`
- 默认值为命令执行时的当前工作目录
- 最终文章目录为：

```text
<target-dir>/<article_id>/
```

这样设计的原因：

- 用户直接 `uvx paper-harvest '<source>'` 时，结果就地可见
- 不强制额外包一层 `store/`
- 如果用户需要集中管理，可以自行传入一个专门目录

### 14.5 PDF 步骤实现

PDF 步骤需要覆盖三类输入：

#### arXiv 链接

- 识别 `abs` / `pdf` / 其他 arXiv 形式
- 统一转换成 PDF 下载地址
- 下载到 `pdf/<article_id>.pdf`

#### 本地 PDF

- 复制到 `pdf/<article_id>.pdf`

### 14.6 TEX 步骤实现

当前 TEX 只覆盖 arXiv。

实现步骤：

1. 从输入中识别 arXiv id
2. 生成源码地址 `https://arxiv.org/src/<id>`
3. 下载源码包到 `tex/`
4. 解压到 `tex/source/`
5. 做基本的安全解压校验，避免压缩包路径穿越

对非 arXiv 输入：

- 直接返回 `skipped`

### 14.7 Markdown 步骤实现

Markdown 步骤依赖 MinerU。

实现路径：

1. 优先用本地 PDF 作为输入
2. 先判断是否存在 MinerU token
3. 有 token 时，优先调用精准解析 API
4. 无 token 时，判断输入是否满足 Agent 轻量解析 API 限制
5. 满足轻量接口限制时，调用轻量解析 API
6. 精准接口场景下，下载解析结果 zip
7. 轻量接口场景下，下载 Markdown 结果
8. 统一归档图片到 `md/assets/`
9. 统一输出 `md/<article_id>.md`
10. 输出 `md/mineru_result.json`

#### 精准解析 API

适用场景：

- 已配置 token
- 文档较大
- 需要更高精度
- 需要 zip、JSON、docx、html、latex 等附加结果

#### Agent 轻量解析 API

适用场景：

- 未配置 token
- 用户通过 `uvx` 直接运行，希望尽量零配置
- 文档大小和页数满足轻量接口限制
- 只需要 Markdown 结果

规格约束：

- 使用无 token 接口
- 接口按 IP 限频
- 仅支持单文件
- 文件大小上限和页数上限低于精准解析 API
- 输出只保证 Markdown 结果，不保证完整 zip 产物

回退规则建议：

1. 精准解析 API 为首选
2. 缺少 token 时，不直接放弃，先尝试轻量解析 API
3. 轻量解析 API 因限制不适用时，再把 `md` 标记为 `skipped`
4. 轻量解析 API 请求失败时，记录失败原因并保留其他产物

### 14.8 URL 解析步骤实现

URL 解析层建议独立成单独模块，不和 `pdf`、`md`、`tex` 任一步骤耦合。

实现目标：

1. 识别输入是远程链接还是本地文件
2. 对远程链接做标准化
3. 当前版本只接受 arXiv 链接；其他远程链接直接报错
4. 输出统一的解析结果对象

建议解析结果至少包含：

- 原始输入
- 规范化后的输入
- 输入类型
- 来源类型
- 文章标识候选
- PDF 下载候选地址
- TEX 下载候选地址

这样做的价值：

- 后续新增站点支持时，只需要扩展 URL 解析层
- `pdf`、`md`、`tex` 三步可以保持更对称的职责
- 顶层 CLI 不需要散落站点判断逻辑

### 14.9 错误处理实现

面向 agent 的要求是“可恢复优先于直接中断”。

建议分层处理：

#### 顶层 fatal

这些情况直接返回失败退出码：

- 输入非法
- 本地 PDF 不存在
- PDF 主步骤失败
- 目标目录无法写入

#### 步骤级失败

这些情况不直接中断整条流程：

- TEX 下载失败
- MinerU token 缺失
- Markdown 生成失败

处理方式：

- 记录步骤状态
- 返回明确消息
- 保留其他成功产物

### 14.10 输出实现

建议双通道输出：

#### 普通模式

输出简洁摘要，适合人直接阅读。

#### `--json`

输出结构化对象，适合 agent 直接解析。

同时，每次运行都应写入：

```text
harvest_result.json
```

这个文件应作为最终权威结果，而不是让上层重新拼接路径或从日志猜测状态。

### 14.11 uvx 场景实现要求

因为目标场景是“用户直接 `uvx` 运行”，实现上需要遵守这些原则：

1. 默认目标目录使用当前工作目录
2. 不依赖仓库内部绝对路径
3. token 查找支持当前工作目录
4. 尽量减少第三方依赖
5. 打包后可直接作为控制台命令运行

### 14.12 发布实现要求

发布前需要满足：

1. `uv build` 成功
2. 产出 wheel 和 sdist
3. `uvx --from . paper-harvest --help` 可运行
4. `uvx --from . paper-harvest '<source>'` 可运行
5. 发布到包源后支持：

```bash
uvx paper-harvest '<source>'
```

## 15. 实施建议

建议按以下顺序推进：

1. 先把 PDF、TEX、Markdown 三步能力拆成独立模块
2. 再收口统一 CLI
3. 再补结构化结果文件
4. 再验证 `uv run`、`uvx --from .`、`uvx <package>`
5. 最后补用户文档和 skill 文档

这样可以先保证功能正确，再收口为稳定的可分发工具。
