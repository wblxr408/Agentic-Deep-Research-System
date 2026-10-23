# Proposal

## Why

当前审查确认六个高危缺陷：浏览器可访问内网，真实 RAG 命中因引用类型不匹配丢失，审批恢复失败并重置状态，同一会话可重复执行覆盖，长连接撤权不生效，工具全被策略禁用时图提前结束。用户要求逐一修复。

## What Changes

- 通用浏览器所有网络请求通过公共 HTTPS 地址校验和固定地址传输，包含重定向和页面子资源。
- 保留 RAG 结果中的结构化引用。
- 保存完整工作流状态，恢复已批准的具体动作并保留预算和策略。
- 原子创建会话和解决审批，避免同一会话并发执行与覆盖。
- SSE 在事件出口和空闲等待时重新鉴权。
- 空工具批次继续汇总并生成明确的拒绝结果。

## Capabilities

### New Capabilities

- `research-execution`: 研究执行的公共网络边界、状态恢复、唯一执行及事件访问控制。
- `internal-retrieval-results`: 内部资料真实命中及结构化引用传递。

### Modified Capabilities

无现有主规格。

## Impact

涉及 browser、rag、graph、research API、鉴权、SSE、运行时持久化及对应文档。仅为当前六项缺陷编写最小行为用例并观察 RED/GREEN；遵守用户禁止回归测试的明确要求，不运行既有套件。
