# 研究上游渠道与维护

DeepIntel 提供 16 个只读渠道，参考 Agent-Reach 的渠道覆盖、首选与备选策略，直接调用公开接口或固定的上游工具。内容继续进入现有搜索/浏览、证据、分析与引用链。

## 在界面中使用

在研究工作台的选项区域打开“联网渠道”，最多选择 8 个支持搜索的渠道，然后开始研究。没有选择时使用网页搜索；`github: LangGraph`、`bilibili: Agent 教程` 等平台前缀和已知平台的 HTTPS 链接会指定对应渠道。渠道选择随会话保存，并在恢复时继续使用。公开研究默认联网；开启“补充检索内部资料”后，两类证据共同参与分析，内部命中不会跳过所选渠道。

每个渠道都有“维护”入口，可以启用/停用、选择首选后端、开启默认顺序的备选、设置总超时和最多后端尝试。RSS 可配置最多 10 个公开 HTTPS 源。“采集内容”接受关键词或链接，返回实际内容、来源链接和各后端尝试；保存配置后再采集即可验证改动效果。只支持读取的小宇宙也可在这里使用。

渠道列表是被动读取：显示配置、设置方法和最近实际尝试。`not_checked` 表示没有记录，`content_attempt_recorded` 表示已有尝试，成功与否以 `last_attempt` 为准。记录不代表平台永远可用。

## 覆盖与依赖

表内是本次实现的操作范围。关键词搜索通常返回摘要或元数据，链接读取才尝试取得正文、回复或字幕。默认后端按顺序有限回退；具体启用顺序可按用户修改。

| 渠道 ID | 搜索 | 链接读取 | 默认后端 / 配置要求 |
|---|---|---|---|
| `web` | DuckDuckGo / Bing RSS / Exa 结果 | Jina Reader 正文 | `duckduckgo`、`bing-rss`、`exa-mcp`、`jina`；搜索挑战不作为内容，经独立引擎备选 |
| `exa` | 全网语义搜索 | — | `exa-mcp`；安装 mcporter，配置名为 exa 的服务 |
| `github` | 仓库 | 仓库说明与 README | `gh`、`github-api`；公开 API 无需私人登录；读取使用仓库根 URL |
| `youtube` | 视频 | 字幕与视频信息 | `yt-dlp`、`opencli`；可手动选择 `transcribe` |
| `bilibili` | 视频 | 字幕或明确标识的视频元数据 | 搜索：`bili`、`opencli`、`bilibili-api`；默认读取优先 OpenCLI 字幕；链接需包含 BV 号 |
| `rss` | 在配置源的条目中筛选 | RSS / Atom 条目 | `feed`；读取直接传 feed URL，搜索先配置 feeds；条目可能只含摘要 |
| `v2ex` | 公开最新主题内筛选 | `/t/数字` 主题与回复 | `v2ex-api`；搜索范围是最新主题 |
| `twitter` | 推文 | 推文 / 长文 | `twitter`、`opencli`；twitter 需显式 Token，OpenCLI 需已有会话 |
| `reddit` | 帖子 | 帖子与评论 | `opencli`；可手动选择兼容 `rdt`，其工具可能自动读取浏览器 Cookie |
| `xiaohongshu` | 笔记 | 笔记内容 | `opencli`、`xhs-mcp`；MCP 详情 URL 需 xsec_token；`xhs` 仅手动选择 |
| `facebook` | 搜索结果 | 用户名主页信息 | `opencli`；已有浏览器会话；暂不支持 profile.php 形式 |
| `instagram` | 用户 | 用户最近帖子与 caption | `opencli`；读取用户名主页 URL |
| `linkedin` | 职位 | `/in/用户`、`/company/公司` 信息 | `linkedin-mcp`、`jina`；MCP 需已有登录态，公开页面可走 Jina |
| `boss` | 岗位与 JD | — | `boss`；已有专用 Chrome，existing-browser / 本地 CDP 9222 |
| `xueqiu` | 股票 / 搜索结果 | `/S/股票代码` 行情 | `opencli`；已有浏览器会话 |
| `xiaoyuzhou` | — | 公开节目介绍、单集 shownotes | `xiaoyuzhou-page`、`jina`；原站读取公开页面数据；音频转录单独配置 |

第三方 CLI、MCP 服务和登录态由操作员按所需渠道配置。DeepIntel 的请求处理不会安装或升级这些工具，也不提供平台登录流程。OpenCLI 复用操作员控制的已有 Chrome 会话；手动选择的存量 rdt/xhs 工具可能自行读取或刷新凭据，配置前应确认其当前版本行为。平台协议、输出和限制变化时，集中修改 `app/channels/backends.py` 中的对应适配器与行为样例。

## 本地工具安装与平台登录态

Windows PowerShell 7 在仓库根运行以下安装器；它安装固定版本，并生成可信的原生启动映射 `config/channel-tools.local.json` 和独立 MCP 配置 `config/mcporter.local.json`。这两个机器配置不提交。API 默认读取原生映射文件，重启后继续生效；`CHANNELS_TOOL_PREFIXES` 仍可显式覆盖。映射只由操作员维护，网页请求不能修改可执行路径。

```powershell
./scripts/setup_channel_tools.ps1 -NodePath 'D:/New Folder/node.exe' -PythonPath 'D:/Agentic-Deep-Research-System/.venv/Scripts/python.exe'
```

本次已安装 bili 0.6.2、yt-dlp 2026.8.19（含匹配的 EJS 0.8.0）、mcporter 0.9.0、OpenCLI 1.8.8、Twitter CLI 0.8.5、Boss CLI 3.0.0、LinkedIn MCP 4.27.0。后三者使用 `.channel-tools/python` 的独立 Python 3.13 环境；不会更改主应用的 MCP/Pydantic 版本。Node 工具的 undici 固定到 7.29.1，安装后的 npm audit 为 0 漏洞。工具更新应先核对命令/输出契约，再重跑实际内容案例。

`config/mcporter.json` 提供 Exa 官方免 Key 的限流服务，关闭编辑器 MCP 自动导入，限定 search/fetch。本次公开搜索已经使用该服务；生产用量可能需要 Exa 自己的 Key/OAuth。GitHub 公开 API 已能工作，gh 是可选备选；rdt、xhs、独立小红书 MCP 和音频转录工具为手动可选后端，本次没有启用或安装它们。

本轮曾触及 Exa 免费 MCP 限额，返回 rate_limited；最后一轮额度恢复后取得 5 条结果。持续使用时可等待恢复或配置 Exa 专用 API Key。网页搜索已加入 Bing 公开搜索 RSS 摘要备选，当前顺序为 DuckDuckGo → Bing RSS → Exa；只有公共 HTTPS 来源才进入证据。Bing feed 声明限个人非商业 RSS 聚合使用，商业部署应选择合适授权的搜索后端。该 RSS 来源不是稳定 API 合约，结果排名与全文读取分别验证。

| 渠道 / 操作 | 平台登录要求 | 本次配置与验证边界 |
|---|---|---|
| 网页搜索/读取、Exa、RSS、V2EX、公开 GitHub | 不需要平台登录 | 公开后端；Exa 免 Key 有服务限流 |
| YouTube 公开视频搜索 | 通常不需要 | yt-dlp + 显式 Node 运行时；年龄/私人内容另需授权账号 |
| B站公开视频搜索/详情 | 通常不需要 | 固定 bili search/video 命令不触发其浏览器 Cookie 扫描；本轮搜索成功，详情额外复验遇 account_risk 并停止回退；取得元数据但缺字幕时标 partial |
| B站字幕 | 可能需要 B站登录态及可用字幕 | OpenCLI 使用专用浏览器；没有字幕不能声称取得转录 |
| 小宇宙公开节目/单集页 | 不需要 | 取得介绍、shownotes、单集链接；明确标注音频转录未获取 |
| Twitter / X | 需要 | 显式 `TWITTER_AUTH_TOKEN` + `TWITTER_CT0`；缺失停止，或手动选已有 OpenCLI 平台会话 |
| Reddit、小红书、Facebook、Instagram、雪球 | 目标环境需要对应平台会话验证 | OpenCLI 已安装；专用测试浏览器当前无平台登录态。Reddit/FB/IG/雪球本轮仍有网络/页面限制，登录后仍需实际验证 |
| LinkedIn 原生搜索/资料 | 需要 | MCP 已安装及配置，但采集前必须由操作员完成专用 profile 登录，并导出 `CHANNELS_LINKEDIN_SESSION_READY=true`；当前未启用，返回 auth_required |
| Boss直聘 | 需要 | Boss CLI 已安装；专用浏览器必须登录，并在其隔离 data-dir 保存会话。严格 existing-browser，不自动转存个人 Cookie |
| 音频转录 | 需要提供商密钥，区别于平台登录 | Groq/OpenAI 专用转录配置；当前未验证，也不继承研究 LLM Key |

本轮 OpenCLI 使用空的独立 Edge profile，经 `OPENCLI_CDP_ENDPOINT=http://127.0.0.1:9223` 连接。**CDP 直连不需要 Browser Bridge 扩展**；如采用默认 Bridge 模式，则需要手动安装扩展并将专用 profile 命名为 deepintel-test。浏览器连接配置与平台登录是两件事。API 进程应显式导出 `OPENCLI_CDP_ENDPOINT` 或使用该命名 profile，不借用其他已登录浏览器。

LinkedIn 手动登录命令（由操作员运行；安装器不会执行）：

```powershell
& .channel-tools/python/Scripts/mcp-server-linkedin.exe --login --no-auto-import --user-data-dir 'D:/Agentic-Deep-Research-System/.channel-tools/linkedin/profile'
$env:CHANNELS_LINKEDIN_SESSION_READY = 'true'
```

会话失效时撤销 ready 标记并手动处理；上游 MCP 自己包含登录恢复逻辑，ready 标记是操作员准入，不是平台认证证明。共享部署中工具平台身份仍属于操作员，DeepIntel 测试账号只负责应用认证。

## 运行配置

`CHANNELS_STATE_ROOT` 默认是工作目录下的 `./data/channels`，保存可信用户 UUID 对应的 JSON 配置及最近 100 条尝试记录。文件通过原子写入和跨进程锁更新；历史只含渠道、后端、状态、结果数量、错误类别、调用数与时间，不保存查询、Token 和上游原始错误。Docker Compose 已配置独立的 `channeldata` 卷。

本机运行时将下列值放入启动 API 的进程环境；Docker Compose 会将 `.env` 载入容器。普通 Python 中 Pydantic 的 `.env` 读取不会自动变成子进程环境。Windows PowerShell 示例：

```powershell
$env:CHANNELS_STATE_ROOT = 'D:/Agentic-Deep-Research-System/data/channels'
$env:CHANNELS_TOOL_PREFIXES_FILE = 'D:/Agentic-Deep-Research-System/config/channel-tools.local.json'
$env:OPENCLI_CDP_ENDPOINT = 'http://127.0.0.1:9223'
```

安装器按实际路径生成原生可执行文件和 CLI 入口。CDP 地址须对应操作员已经运行的专用浏览器。npm 的 `.cmd` / `.bat` 启动器会被拒绝，使用原生 Node + 工具的已安装 JS 入口。内联 `CHANNELS_TOOL_PREFIXES` 会覆盖整个文件映射；沿用安装器配置时不要仅用一条 opencli 映射覆盖其他工具。该映射属于受信的服务端部署配置，用户 API 不能修改。

GitHub CLI 只接收 `GH_TOKEN` / `GITHUB_TOKEN`；twitter 后端要求同时显式设置 `TWITTER_AUTH_TOKEN` 和 `TWITTER_CT0`，缺少即返回 `auth_required`。OpenCLI 可接收 `OPENCLI_PROFILE` / `OPENCLI_CDP_ENDPOINT`。渠道 JSON 和网页表单不保存这些秘密。外部工具仍能访问其本机配置文件与浏览器会话：当前部署的 CLI 凭据属于 API 进程的操作员身份，用户隔离的是配置和历史，不能将此视为每个用户独立的平台账号。

音频转录只在显式选择 `transcribe` 且设置 `transcription_provider=groq|openai` 后执行 `agent-reach transcribe`。需事先在 Agent-Reach 配置该提供商的专用凭据，研究系统的 LLM/OpenAI/Groq 环境密钥不转发；不会跨提供商自动重试。转录会将音频交给所选提供商处理，来源支持范围取决于上游工具。

## API

所有接口沿用现有会话认证，用户归属从服务端 Principal 获得。请求不能传 owner，也不能传命令或自定义工具名。

| 方法 / 路径 | 用途 |
|---|---|
| `GET /api/v1/channels` | 16 渠道、操作、默认/可选后端、当前用户配置及最近尝试 |
| `GET /api/v1/channels/history` | 当前用户最近的有界尝试记录 |
| `PUT /api/v1/channels/{channel}/config` | 保存启用状态、顺序、期限、尝试上限、RSS 源和转录提供商 |
| `POST /api/v1/channels/collect` | 实际搜索或读取内容 |

例如将公开 GitHub API 设为首选：

```json
{
  "enabled": true,
  "backends": ["github-api", "gh"],
  "timeout_seconds": 20,
  "max_attempts": 2,
  "feeds": [],
  "transcription_provider": null
}
```

实际内容请求：

```json
{
  "channel": "github",
  "operation": "read",
  "query": "https://github.com/Panniantong/Agent-Reach",
  "limit": 5,
  "max_chars": 8000
}
```

响应包含 `items`、`attempts`、`status` 和 `call_count`。每条内容提供 `url/title/content/channel/backend/collected_at`；每次尝试提供 `backend/status/result_count/error_category/duration_ms/call_count`。`success` 有实际结果，`partial` 表示只获得明确标识的视频元数据等部分内容，`empty` 表示没有内容，`failed` 表示执行或配置失败。上游采集失败以结构化结果返回；非法请求/配置为 HTTP 422，配置存储不可读为 503。

研究接口 `POST /api/v1/research` 新增可选的 `channels` 数组，例如 `{"query":"Agent 框架对比","channels":["web","github","exa"]}`，最多 8 个不重复的已注册渠道。原请求保持兼容。

## 维护与回退

| 错误类别 | 处理方式 |
|---|---|
| `dependency_missing` / `dependency_unavailable` | 配置所选工具，或将可用备选设为首选 |
| `native_launcher_required` / `configuration_error` | 修正原生启动器映射；不把用户输入拼入 shell |
| `auth_required` | 更新所选工具的明确登录态后再采集；该次停止回退 |
| `account_risk` | 在平台端处理账号/验证问题；该次停止回退 |
| `not_found` | 来源链接已失效；停止回退，不将 404 页面作为证据 |
| `configuration_required` | 完成 MCP 服务或专用浏览器连接配置 |
| `rate_limited` | 同用户、同渠道记录 60 秒冷却；不会换后端连续请求 |
| `no_transcript` | 尝试已配置的字幕备选；最终可返回标为 partial 的元数据 |
| `empty_content` / `invalid_output` / `network` | 在同一总期限内尝试有限备选；保留失败记录 |
| `configuration_required` | RSS 搜索配置 feeds；转录选择提供商并事先配置凭据 |
| `domain_blocked` / `unsupported_input` | 使用受支持的公开 HTTPS 来源和 URL 形式 |
| `budget_exceeded` / `timeout` / `output_limit` | 缩小请求或调整有界配置；查看完整尝试轨迹 |

默认单次采集最多 8 次外部调用、20 秒总期限、3 个后端尝试；用户期限范围 1–90 秒、最多尝试 1–5，结果范围 1–20 条，每条最多 20000 字符。HTTP 响应和命令合并输出各限制 1 MiB。多渠道搜索共享调用与时间预算，并轮流取各渠道结果；并行研究节点预先分配互不重叠的调用额度，尝试中的实际 CLI/HTTP 调用计入工具预算。

应用内 HTTP 读取验证公开地址、DNS 与逐跳重定向，并固定已验证地址建立 TLS；DNS 查询由系统解析器管理，第三方 CLI 和远端 Reader 的内部网络请求由其自身实现。Windows 子进程用 JobObject、POSIX 用进程组回收超时和退出后的子进程。

## 依据与验证

参考 [Agent-Reach 1.5.0 源码](https://github.com/Panniantong/Agent-Reach/tree/94f06c1969dfc1834001269d79d3ad0972d9dee6) 的渠道与 `agent_reach/skill/references/` 命令契约，以及 [OpenCLI 源码](https://github.com/jackwener/opencli/tree/b06ab7780e73d3021e12e0f170086c2d55675776) 的平台适配器。此处借鉴渠道能力和维护方式，不假定 Agent-Reach 提供统一 Python 搜索 SDK。

实际检查范围和结果见 [验证记录](research-channels-verification.md)。独立 DeepIntel 测试账号已通过真实 PostgreSQL 认证、API 与浏览器操作。网页搜索、B站和小宇宙的修复后记录与旧失败基线分别保留；需要平台登录态的渠道按上表配置后再验收。
