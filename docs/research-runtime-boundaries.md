# 研究执行边界修复

本变更对应 `openspec/changes/fix-research-runtime-boundaries/`，修复当前审查的六项 P1。

| 问题 | 当前行为与控制点 |
| --- | --- |
| 通用浏览器 SSRF | BrowserAgent 和浏览器工具共享 PublicBrowserGateway。仅公共 HTTPS GET/HEAD；固定 DNS 校验得到的地址并验证 TLS 主机名，每个重定向重新校验。子资源、fetch、弹窗经过同一传输。关闭 service worker 与 WebSocket；无法拦截的浏览器流量由专用、被占用但不监听的本地代理端口拒绝。保留 JavaScript 渲染；每次浏览限 64 个请求、8 MiB、45 秒出站窗口。 |
| RAG 命中丢失 | RAGResult 引用同时支持 Citation 对象和旧字符串，真实检索构造的结构化来源可以序列化并交付。 |
| 审批恢复失效 | 保存 LangGraph 完整 values 状态到 PostgreSQL，使用有效恢复入口并继续原 DAG。决定绑定原节点、工具和参数、规划轮次；保留 owner、渠道、资料选项、skill_context、历史和消耗预算。全部待审批决定完成后恢复；拒绝节点跳过。MCP 同时验证服务指纹及实际参数，批准人使用认证身份。 |
| 重复会话执行覆盖 | 原子 INSERT 不覆盖；已有会话仅允许 owner 相符、pending 且完整原请求相符的确认，其他同 owner 请求返回 409，其他 owner 返回 404。审批在会话行锁下只能决定一次。新的 execution_id 隔离恢复段，旧执行段不能覆盖持久状态或发布关闭新流的终止事件。 |
| SSE 撤权失效 | 绑定建立连接时的凭据摘要，每个历史/新事件前重新读取有效性、版本、到期和 owner；空闲最长约 1 秒再次检查。鉴权后端异常关闭连接。恢复清除上一执行段的缓冲终止事件。 |
| 全部工具被禁用时提前结束 | 空批次显式进入汇总、分析和受限报告；无证据时跳过模型反思，返回可读报告、blocked 标记和一致完成状态。 |

## 数据升级

数据库初始化和迁移脚本新增 `research_sessions.request_payload`、`research_sessions.execution_id` 和 `session_runtime_state.state_snapshot_json`，允许 `paused` 状态。按现有部署流程执行初始化/迁移后运行新服务。旧的已保存数据保留；旧版不完整暂停快照无法安全恢复，审批接口返回 409。运行时在写入审计和审批时间前规范化 ISO 时间为数据库日期值。

## 验证范围

遵守用户禁止回归测试的明确要求。只创建并执行 `tests/fixes/test_research_boundaries.py` 的当前缺陷最小行为用例，包含私有页面/重定向/DNS 子资源、真实 RAG 构造、编译图受限终态、重复会话、已建立连接撤权、完整暂停持久化和绑定恢复、MCP 批准参数约束。旧套件、smoke、启动探针、文件存在性和文字匹配检查均未执行。

结果：本次 10 个缺陷行为用例通过；Ruff 的 E9/F63/F7/F82 检查通过；`openspec validate fix-research-runtime-boundaries --strict` 通过。

图、检索结果模型、事件管理器和运行时持久化使用真实代码；外部 HTTP、数据库、embedding/reranker、模型调用用适配器替代。数据库适配器模拟原子插入、行锁及时间参数约束。未在真实 PostgreSQL 或 Chromium 页面环境执行本变更，因此不把这些用例声称为生产端到端证明。

## 安全方案引用

应用 A2AB v1.0 的“工程解决方案 / 验收办法”：A2AB-03《上下文归属与跨租户隔离》（恢复 owner）；A2AB-04《长连接撤权与事件出口鉴权》（SSE 原凭据重查）；A2AB-06《并发状态版本与审批绑定》（会话行锁、执行段、动作绑定）；A2AB-07《Webhook归属验证与受控出站》的受控出站部分（固定地址传输）；A2AB-08《结构化授权请求与权限不放大》（具体参数与服务指纹）；A2AB-10《委派环路检测与全链预算》的预算部分（恢复消耗连续）。这些是已核实的本地方案，当前验证边界见上文，并非官方修复声明；其余方案适用性见 design.md。
