# Design

## Context

参见 proposal.md。当前 search_node 直接执行 DuckDuckGo，browser_node 使用通用 Playwright；McpPolicyProxy 没有生产 executor。本改动使用薄适配器直接调用已选定的上游只读工具，避免把 Agent-Reach 的安装/诊断类误当统一搜索 SDK。依据上游提交 94f06c1969dfc1834001269d79d3ad0972d9dee6 的公开命令契约。

## Goals / Non-Goals

Goals：统一请求、结果、后端顺序、错误分类、用户配置、实际运行记录及证据接入。
Non-Goals：平台登录自动化、写操作、任意 MCP 工具执行、自动更新外部工具、把适配器测试称为全部平台在线。

## Decisions

- 固定渠道注册表与服务端 argv 模板；HTTP 与进程执行共享有界内容验收。命令参数不使用 shell；拒绝查询选项注入。
- 结构化结果包含 url/title/content/channel/backend/collected_at。没有有效公开来源链接的上游记录明确拒绝，不自动猜文章链接；已知平台 ID 按其公开规范生成链接。
- 每用户 JSON 配置复用 atomic_write_json，路径由可信 owner UUID 决定；运行历史仅保存渠道/状态/时间，不保存查询和原始异常或秘密，最近 100 条有界记录。配置持久化使用文件锁保护并发读改写。
- 网络出口拒绝私网和非 HTTPS；重定向逐跳验证，连接固定已核验地址。第三方 CLI 的网络行为由工具自身负责，项目不宣称完全控制其内部网络出口。
- 只传平台对应的环境凭据，公开信息工具不继承研究 LLM/API 秘密。Twitter 缺显式 tokens 时停止；OpenCLI 使用操作员控制的已有会话。rdt/xhs 存量工具可能自行读取浏览器 Cookie，因此仅作手动选择的兼容后端，维护界面明示要求。项目不宣称隔离第三方工具对本机配置文件的访问；当前凭据为 API 操作员身份，owner 隔离配置与历史。
- 后端失败最多尝试注册表内的有限列表；认证/风控直接停止，限流记录冷却期。请求共享期限、调用数与结果上限，成功依据实质内容。
- search/browser 主路径转换为原有模型；Evidence 增加可选渠道元数据，旧客户端兼容。通用查询保留 DuckDuckGo。
- 平台 canonical URL 优先于 API 地址/媒体 CDN/帖子外链；读取时合并同一来源下的字幕和评论。缺字幕可回退，最终只有元数据时返回 partial 并说明缺失。
- 实际 CLI/HTTP 调用共享全链额度与期限，并行节点预分配互不重叠的调用额度；多个选择渠道轮流取结果。Windows JobObject / POSIX 进程组负责根进程退出后和超时的后代回收。

## Risks / Trade-offs

追加真实失败修复：网页结果用 HTMLParser 保留链接/摘要，DuckDuckGo 挑战返回 access_denied 并切换独立 Bing RSS / Exa 搜索引擎，不解验证码或再次访问被拦引擎。Exa 已取得真实内容，随后免费额度耗尽，纯文本提示归类 rate_limited；RSS 备选的个人非商业使用声明见渠道说明，商业部署选择授权后端。B站使用已安装 bili 的公开 search/video 契约，HTTP 412 标为 account_risk 并停止。小宇宙优先解析公开原站 __NEXT_DATA__ 中介绍/shownotes，404 标为 not_found 停止；这些内容明确不是音频转录。Windows 可信本地启动映射支持原生 Node/Python 入口；MCP 关闭编辑器自动导入并限定只读工具。LinkedIn 工具需操作员 session-ready 准入，专用 profile 关闭 auto-import；当前账号测试未提供平台登录。沿用下述 A2ABreak v1.0 适用边界，配置安装不扩展用户可调用能力或证据信任。

- 上游输出/命令换代 → 集中契约适配、代表性固定返回样例、实际错误可追踪；未配置渠道不伪称可用。
- 音视频转录调用外部提供商 → 作为单独配置的可选读取后端，不自动转发内部文档或跨提供商重试。
- 本次无平台私人账号 → 行为回归证明适配和隔离；真实内容验收范围单独记载。

## Baseline application

依据 A2ABreak 安全基线 v1.0，引用以下条目的“工程解决方案”“验收办法”；本地方案为来源核对提案，本次按实际边界验证，不宣称官方修复。

| ID / title / version / sections | 本次控制点及验证 |
|---|---|
| A2AB-01 / 技能声明验证与委派准入 / v1.0 / 工程解决方案、验收办法 | 渠道/后端注册表；非注册能力拒绝；错误输出和无来源结果不进入 Evidence |
| A2AB-03 / 上下文归属与跨租户隔离 / v1.0 / 工程解决方案、验收办法 | owner 配置与历史隔离；会话可信 owner 流转；双主体行为测试 |
| A2AB-08 / 结构化授权请求与权限不放大 / v1.0 / 工程解决方案、验收办法 | 请求操作枚举、后端枚举、只读 argv；禁任意执行/自动登录；边界测试 |
| A2AB-10 / 委派环路检测与全链预算 / v1.0 / 工程解决方案、验收办法 | 请求调用数/期限与有界后端降级；预算耗尽测试；没有 Agent 再委派 |
| A2AB-11 / 中断任务租约与有界资源回收 / v1.0 / 工程解决方案、验收办法 | 不等待登录占用工作线程；子进程期限/输出超限清理；真实子进程测试，仅借鉴资源回收部分 |
| A2AB-07 / Webhook归属验证与受控出站 / v1.0 / 工程解决方案第2项、验收办法 | 没有 Webhook；仅借鉴 HTTP 读取出口、DNS/跳转约束；拒绝私网测试，不实施回调归属证明 |

精确来源：[基线索引 v1.0](memory://main/engineering/security/a2abreak/a2-abreak-多-agent-安全基线与-11-项方案索引)、[A2AB-01 技能声明验证与委派准入](memory://main/engineering/security/a2abreak/solutions/a2-ab-01-技能声明验证与委派准入)、[A2AB-03 上下文归属与跨租户隔离](memory://main/engineering/security/a2abreak/solutions/a2-ab-03-上下文归属与跨租户隔离)、[A2AB-07 Webhook归属验证与受控出站](memory://main/engineering/security/a2abreak/solutions/a2-ab-07-webhook-归属验证与受控出站)、[A2AB-08 结构化授权请求与权限不放大](memory://main/engineering/security/a2abreak/solutions/a2-ab-08-结构化授权请求与权限不放大)、[A2AB-10 委派环路检测与全链预算](memory://main/engineering/security/a2abreak/solutions/a2-ab-10-委派环路检测与全链预算)、[A2AB-11 中断任务租约与有界资源回收](memory://main/engineering/security/a2abreak/solutions/a2-ab-11-中断任务租约与有界资源回收)。

其余适用性：A2AB-02「Agent Card可信密钥与身份绑定」、A2AB-09「多跳主体溯源与凭据防转用」无对应跨组织协议；A2AB-04「长连接撤权与事件出口鉴权」、A2AB-05「产物分块校验与断流恢复」本次不改变既有流出口与报告分块；A2AB-06「并发状态版本与审批绑定」没有新增写工具或审批，渠道配置并发通过本地文件锁串行化，不声称实现完整审批版本保护。A2AB-11 不涉及新中断恢复状态。全部 11 项按基线 v1.0 评估，验证范围见 [功能与内容验证记录](../../../docs/research-channels-verification.md)。

## Migration Plan

新增配置默认为 web；明确平台前缀或渠道选择后执行对应适配。已有研究请求兼容。删除 channels API 注册及主路径接入可回退通用采集，原研究库无需迁移。
