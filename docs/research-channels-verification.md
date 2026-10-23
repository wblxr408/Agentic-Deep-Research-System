# 上游渠道验证记录

日期：2026-10-12。变更：`openspec/changes/add-research-channels/`。实现及维护方法见 [渠道说明](research-channels.md)。本次验证针对上游内容接入、配置隔离、预算和研究证据传播。

## 功能回归

先写消费行为断言并观察预期失败，再实现对应功能。已观察到的 RED 包括平台前缀未返回原生结果、API 尚未注册、选择未传入工作流、共享预算超出、字幕/评论被截为首条、第四个 RSS 源未访问、GitHub API 地址被用作来源、Reddit 外链覆盖帖子来源、默认存量凭据工具仍执行，以及根进程结束后子进程继续存活。

最终后端功能命令，在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/channels tests/graph/test_graph.py tests/agents/test_agents.py::TestSearchAgent tests/agents/test_agents.py::TestBrowserAgent tests/agents/test_agents.py::TestAnalystAgent::test_evidence_formatting tests/agents/test_agents.py::TestReportAgent::test_generate_stream_emits_chunks_and_citations tests/integration/test_workflow.py::TestResearchResultNormalization -k 'not import and not compile_research_graph and not graph_has_required_nodes and not research_state_has_required_keys and not plan_step_defaults and not plan_step_serialization and not create_initial_state' -q
```

最新结果：**134 passed，8 deselected**，17.88 秒。首次接入时 118 项通过，本轮追加 16 项真实失败对应的消费行为案例。按用户规则排除现有导入、浅层结构、默认构造等测试；未执行启动、smoke、文件存在、checksum 或浅层健康检查。一个既有 LangGraph 弃用警告仍存在。

| 验证对象 | 实际断言 |
|---|---|
| 16 渠道适配 | 代表性 JSON/JSONL/MCP/YAML/字幕返回转换为原始链接与内容，字幕/评论多行保留 |
| 后端回退 | 缺依赖或空内容使用有限备选；认证、风控、限流停止；限流冷却期间不再外部请求 |
| owner 与持久状态 | 两个主体配置/历史独立；请求不能替换 owner；两个真实 OS 进程写入保留 40 条历史 |
| 研究路径 | 真实 LangGraph 工具批处理执行搜索与 V2EX 读取，产生 2 条有来源证据；主题及回复进入内容，实际运输调用总数 4 |
| 预算 | 渠道内多 HTTP、多个后端、多个选择渠道共享期限/调用额度；并行节点预分配额度 |
| 命令与凭据 | 固定 argv，查询作为数据；选项注入拒绝；实际子进程只收到所选 GitHub Token，未收到研究 LLM/OpenAI/Twitter 秘密 |
| 资源清理 | 真实子进程超时、输出超限以及父进程先退出的后代回收；Windows JobObject 修复后全部通过 |
| HTTP 与来源 | 拒绝私网 URL、私网 DNS、危险重定向；保留 GitHub/YT 网页地址和 Reddit 帖子 permalink |
| 会话与引用 | 用户渠道选择/owner 进入后台及检查点输入，证据保留 channel/backend/time，消费分析和报告引用行为兼容 |

前端在 `frontend/` 执行 `npm.cmd test`：**4 passed**。Testing Library 用户交互覆盖选择渠道、保存优先级、采集实际响应内容、提交研究选择；保存失败可见且不伪称成功；轨迹呈现首选失败和备选成功。追加登录回归先复现 `Rendered more hooks than during the previous render` 和认证后页面无法呈现，再将 App 的所有 Hook 移到条件返回之前，验证登录后能进入研究工作台。

## 构建与规范

| 检查 | 结果 |
|---|---|
| `.venv\Scripts\python.exe -m ruff check app/channels app/api/channels.py tests/channels scripts/channel_acceptance.py` | 通过 |
| `frontend/` 的 `npm.cmd run build`（tsc + Vite） | 通过；现有大 bundle 警告仍存在 |
| `openspec.cmd validate add-research-channels --strict` | 通过，遥测关闭 |
| `frontend/` 的 `npm.cmd run lint` | 通过，0 错误、0 警告；新增 ESLint/TypeScript/React Hooks 推荐配置，并启用 `--max-warnings=0` |

本机 Python 3.11 测试环境使用 LangGraph 0.2.60、langchain 0.3.30、langchain-core 0.3.86；为运行受影响功能修正了本地依赖兼容性，仓库 requirements 未改。继承的 system site packages 仍有其他 pip 依赖冲突提示，这些结果不证明完整环境无冲突。

## 真实公开内容

直接使用实际 ChannelService/HTTP 读取，配置独立的测试 owner 状态，时间窗口为 2026-10-12 09:41 UTC。GitHub 显式选用 `github-api`，避免依赖本机 gh 登录态。

| 来源 | 实际结果 | 外部调用 / 用时 |
|---|---|---|
| [Agent-Reach 仓库](https://github.com/Panniantong/Agent-Reach) | 1 条，含 README，8000 字符；来源是仓库网页 URL | 2 HTTP / 3264 ms |
| [V2EX 主题 1000000](https://www.v2ex.com/t/1000000) | 1 条，主题及回复，截到 8000 字符 | 2 HTTP / 3844 ms |
| [HN RSS 最新源](https://hnrss.org/newest?count=5) | 5 条文章记录，合计 664 字符 | 1 HTTP / 1202 ms |

RSS 此次取得 feed 提供的条目和元数据，没有据此宣称读取所有文章外链全文。原始本机采集记录在聊天目录 `work/public-channel-content.json`，不将其全部内容纳入仓库。

上述首次公开读取阶段尚未验证私人平台、OpenCLI、mcporter 或音视频转录。后续工具安装与真实验证见追加修复章节；私人平台登录后的采集、音视频提供商转录和真实 LLM 生成报告的完整生产研究任务仍未验收。

## 独立测试账号的首次真实 API / 浏览器验收

用户在后续请求中选择新建独立本地 DeepIntel 测试账号。账号 `channel_test` 通过完整应用的 `/auth/initialize` 创建，再通过 `/auth/login` 密码登录；没有替换认证依赖或伪造 Principal。数据库使用独立 `pgvector/pgvector:pg16` 容器 `deepintel-channel-acceptance-20261012`，本机端口 55432；API 在 8021，前端构建产物通过本地 5175 端口代理 API。测试账号密码仅在聊天工作目录的 `work/deepintel-channel-test-account.json`，不纳入仓库或分享报告。

执行脚本为 `scripts/channel_acceptance.py`，真实 HTTP 请求覆盖账号初始化/登录、匿名采集拒绝、错误密码拒绝、配置持久化、19 次采集的来源内容、全部 23 条尝试历史和退出后的会话失效。**49 项断言通过**，必需的公开内容案例全部成功。没有调用健康接口，也没有 mock 上游内容或数据库。记录时间为 2026-10-12 10:13:16–10:13:51 UTC。

| 实际内容案例 | 结果 |
|---|---|
| GitHub 仓库读取 | README 1 条 / 8000 字符 |
| GitHub 仓库搜索 | 5 条 / 401 字符 |
| V2EX 主题与回复读取 | 1 条 / 8000 字符 |
| RSS 源读取 | 5 条 / 801 字符 |
| RSS 配置源搜索 | 5 条 / 801 字符 |
| 网页读取（Jina / example.com） | 1 条 / 958 字符 |

共 18 条结果，涉及 4 个成功取得内容的渠道；6 个采集案例成功，1 个空结果，12 个失败案例。GitHub 搜索是仓库摘要，RSS 是 feed 条目，不把摘要计为外链全文。完整结构化记录见 [API 采集报告](acceptance/channels-2026-10-12.json)。

| 未取得内容的渠道 / 操作 | 实际结果 |
|---|---|
| web 搜索 | `empty_content`；关键词 LangGraph 本次没有结果 |
| B站搜索 | 首选/备选工具缺失，公开 API 返回 `upstream_error` |
| 小宇宙节目页读取 | Jina 返回 `upstream_error` |
| Twitter 搜索 | `auth_required`；缺少显式平台 Token，停止回退 |
| YouTube、Exa、Reddit、小红书、Facebook、Instagram、LinkedIn、Boss、雪球 | `dependency_missing`；本机尚未安装对应 CLI / 配置服务 |

独立 Edge 浏览器使用同一账号和真实后端完成登录、导航研究工作台、选择 GitHub、保存首选后端、读取仓库 README、核对链接与内容显示。**6 个操作结果通过，页面脚本异常 0**，取得 8000 字符 README。记录见 [浏览器报告](acceptance/channels-browser-2026-10-12.json) 和 [实际页面截图](acceptance/channels-browser-2026-10-12.png)。

本机原生 PostgreSQL 没有 vector 扩展，第一次完整 API 运行失败后改用上述独立容器；应用的数据库初始化成功，并按既有策略将缺失的 chinese 全文配置回退到 simple。未修改现有数据库管理员、密码或平台账号。

重跑应指向已运行的独立测试 API 和该测试账号文件：

```powershell
.\.venv\Scripts\python.exe scripts/channel_acceptance.py --base-url http://127.0.0.1:8021 --account-file '<本地测试账号文件路径>' --report docs/acceptance/channels-rerun.json
```

`--initialize` 只用于明确准备好的空测试数据库。DeepIntel 账号提供应用认证，平台读取仍需自己的工具/登录态，不能因此宣称 16 平台全部通过在线验收。

## 工具补齐与真实失败修复复验

使用相同独立数据库和 `channel_test`，时间窗口 2026-10-12 **11:26:23–11:28:19 UTC**。API 保持真实密码认证、配置持久化和上游网络调用。完整报告 [修复后 API 记录](acceptance/channels-verified-2026-10-12.json) 含 **71 项通过断言、16 渠道、21 个采集案例、11 个成功案例、8 个取得内容的渠道、33 条内容**。脚本因 `rss/read` 网络失败退出 1，不能把这份报告称为全量通过。

| 修复对象 | 原因与修复 | 实际内容结果 |
|---|---|---|
| 网页搜索 | 原 HTML 正则丢失嵌套文本/链接，改用 HTMLParser；真实 DuckDuckGo 响应是挑战页，标 access_denied，使用独立 Bing RSS / Exa 备选 | Bing RSS 4 条 HTTPS 来源与摘要；实际 Edge 显示来源和内容。结果属于搜索摘要，排名质量另行评估 |
| B站搜索 | 安装 bili，适配实际 data.video 封装与原始 BV 来源 | bili 4 条公开视频结果；实际 Edge 显示链接和内容 |
| 小宇宙读取 | 旧节目 URL 原站已 404，Jina 失败；新增公开页面 __NEXT_DATA__ 解析与有效节目/单集 URL | 商业就是这样节目页 1 条、单集 shownotes 1 条；实际 Edge 显示单集 1731 字符。旧 URL 返回 not_found，负例不产生证据 |
| YouTube 搜索 | 全量 dump-json 超过 1MiB；只请求消费所需字段，补 EJS 和显式 Node 运行时 | yt-dlp 5 条来源/标题/描述，最后一轮无需 OpenCLI 回退 |
| Exa 搜索 | 补原生 mcporter 和受限 Exa 服务；将退出码 0 的免费额度提示正确分类为 rate_limited | 中间轮确实限流，最后一轮恢复并返回 5 条；限流记录保留，不把提示当内容 |

新增 16 项消费行为测试先观察预期失败再修复，通过网页嵌套文本、小宇宙节目/单集介绍、404 不入证据、B站元数据 partial、HTTP 412 风控、原生配置持久映射、专用 CDP、LinkedIn 未准入拒绝、工具错误分类、搜索挑战独立备选、Bing RSS 与 Exa 限额断言。最终受影响回归 134 项通过；前端代码本轮未改，沿用上一轮 4 项功能测试、零警告 lint 和构建结果。

真实 Edge 使用同一账号再完成网页搜索、B站搜索、小宇宙单集读取，三个操作的 HTTP 结果、DOM 来源链接和内容均通过，**页面脚本异常 0**。记录见 [修复后浏览器报告](acceptance/channels-repaired-browser-2026-10-12.json)；[截图](acceptance/channels-repaired-browser-2026-10-12.png) 是维护页面的现场记录，内容核验以 DOM 断言和报告为准。

已实际运行 `scripts/setup_channel_tools.ps1`：bili 0.6.2、yt-dlp 2026.8.19 + EJS 0.8.0、mcporter 0.9.0、OpenCLI 1.8.8；独立 Python 3.13 环境包含 Twitter 0.8.5、Boss 3.0.0、LinkedIn MCP 4.27.0。Node 依赖 undici 固定 7.29.1，安装后 npm audit 为 0 漏洞。原生映射和本地 MCP 配置被忽略；仓库保存可重建的版本清单、安装器与公开 Exa 配置。默认公开 GitHub API 无需 gh；rdt、xhs、独立小红书 MCP 和音频转录是未配置的手动可选后端。

### 额外复验与剩余限制

完整轮 RSS read 与紧接的重试均发生 network；同轮 RSS search 成功 5 条。随后核对原站实际 RSS 内容成功，并于 **11:37:11 UTC** 通过同账号认证 API 再次读取成功 **5 条**，见 [RSS 恢复记录](acceptance/channels-rss-recovery-2026-10-12.json)。未修改适配器，也未伪称找到了网络根因；原始失败保留，结果说明存在外部网络波动。

额外 B站视频详情读取返回 **account_risk**，仅一次 bili 尝试便停止回退，见 [额外复验记录](acceptance/channels-followup-2026-10-12.json)。本轮公开搜索成功不证明视频详情或字幕可用。消费测试验证取得元数据但无字幕时正确标 partial，尚未用真实平台登录取得字幕。小宇宙只取得公开介绍和 shownotes，未取得音频转录。

| 需要平台登录态的渠道 | 当前真实结果 / 还需配置 |
|---|---|
| Twitter / X | auth_required；需显式 TWITTER_AUTH_TOKEN + TWITTER_CT0 或专用 OpenCLI 会话 |
| LinkedIn | auth_required；需手动完成专用 profile 登录并启用 CHANNELS_LINKEDIN_SESSION_READY；上游自动导入关闭 |
| Boss直聘 | auth_required；需独立已登录浏览器及隔离 data-dir 会话，existing-browser / CDP 9222 |
| Reddit、小红书、Facebook、Instagram、雪球 | 空测试浏览器没有相应平台登录态；本轮为 upstream_error / network，小红书另有未配置的可选 MCP。登录后仍须验证页面及网络限制，不能将这些错误全称为缺登录 |
| B站字幕 | 可能需 B站专用登录态及平台可用字幕；本轮未验证 |

网页、Exa、RSS、V2EX、公开 GitHub、公开视频搜索和小宇宙公开介绍通常无需平台登录。Exa 专用 Key 和音频转录提供商密钥属于服务配置。DeepIntel 测试账号提供应用认证；平台身份仍由操作员的工具/浏览器提供，不等于每位 DeepIntel 用户有独立平台身份。专用空 Edge CDP 9223 已配置，CDP 直连不依赖 Bridge 扩展；默认 Bridge 模式需另行安装扩展。详细操作见 [登录与配置表](research-channels.md#本地工具安装与平台登录态)。

## A2ABreak 基线应用

本次应用 **A2ABreak v1.0** 中与能力准入、主体归属、受控出站、授权不放大、全链预算和资源回收相关的方案。ID、标题、章节、执行点及全部 11 项适用性见 [设计中的基线评估](../openspec/changes/add-research-channels/design.md#baseline-application)。对应验证是上表的能力拒绝、owner、命令/HTTP、预算和真实进程行为测试。这些方案是来源核对提案，验证仅覆盖本项目实施部分，不是完整 A2A 协议修复声明。
