# 固定证据重排端到端交付

2026-10-21 完成 OpenSpec 5.3，当前 22/34；同时补齐 TODO MATCH.5 的真实 PostgreSQL 业务验证。ACI 见[固定证据重排](../research-reranking.md)。没有运行单元、回归、冒烟、健康、启动／导入／存在性／hash 探针或 build／类型／lint／schema 门禁。

## 完整场景与失败过程

使用实际登录、模型、出版商网页、浏览／搜索、PostgreSQL 和 Edge，先完成两篇论文的组织研究，再从界面冻结同一证据、改变偏好并重排，最后显式创建独立新研究。没有生成替代论文、伪造特征或切换到 SQLite。来源为 USENIX 的 [Orca](https://www.usenix.org/conference/osdi22/presentation/yu) 与 [DistServe](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin)，所选对象为 Seoul National University 与 Peking University。

环境恢复时实际 Docker／API／前端均停止，首次登录连接失败，未创建任务。通过既有 Docker 恢复入口重启原容器与应用后创建研究 **`871eae63-4ece-4832-a8e5-6885bc32593f`**，真实取证完成，两条发表记录及原文位置进入结果。完整消费场景先因缺少重排入口失败。

接入后，真实 PostgreSQL 插入又暴露 `AmbiguousParameterError: could not determine data type of parameter $3`，对应可空会话参数。为共享 SQL 补充 UUID、JSONB 与时间类型，再继续读取同一已完成研究，没有为修复重复取证。首轮完整流程通过后，补充版本要求发现修改前后配置标签相同；修复为每次显式预览／新研究独立版本后重新验证。

## 最终实际结果

最终消费程序 `scripts/organization_rerank_e2e.py --phase verify --existing 871eae63-4ece-4832-a8e5-6885bc32593f` 退出 0，无浏览器运行错误。原来源研究沿用，未假称又做一遍取证。快照 **`f994b0c0-a866-490e-939d-3945b4b5b853`** 在两次重排中相同，证据封存日、候选与来源均相同。

| 对象 | 主题 60／时效 20／成果表现未知 20 | 主题 20／时效 80 |
| --- | --- | --- |
| Peking University | 13.33–40.00，覆盖率 80% | 53.33–80.00，覆盖率 100% |
| Seoul National University | 60.00–86.65，覆盖率 80% | 20.00–46.59，覆盖率 100% |

前一偏好下首尔大学下界高于北京大学上界；后一偏好下北京大学下界高于首尔大学上界。这里比较声明词面／时间偏好，不是机构科研质量。原结构记录只保留出版年份，因此整个年份进入时效区间；即使覆盖率达到 100%，也不生成精确总分。成果表现缺失保留其 20 分预算的可能区间，没有按零分或重分配预算处理。

界面实际显示了区间、80%→100% 覆盖率、分项贡献及反转的确定优先关系，计算规则为 `adrs-matching-v2`。配置版本分别为 `user-config-v1:preview:f83fb594-de12-4f6e-b60f-731ed629ecd6` 与 `user-config-v1:preview:98b507a1-f72e-4e09-8caa-74b535eb6f24`；原会话配置不变。

重排前后原报告、review 快照、token／费用、取证审计行数和研究数量一致。重复准备复用同一快照，绑定原会话的行数为 1；所有来源仍为 `unreviewed`，没有把原文位置检查升级为人工／语义确认。

点击“重新取证并研究”才创建新任务 **`25e4c1ff-0a3f-426f-a509-74a9e6b8ed5f`**，新研究实际调用工具、完成报告，主题比例为 20%，并保留独立 `research` 配置版本。报告 14,416 字符、22 条引用。旧报告、配置和审计仍不变；该次验证研究数只增加 1。先前通过但随后发现版本缺口的任务 `2ac971c3-06c9-47ec-83c0-128bf8d980a2` 是历史运行，不当成最终版本验证。

## PostgreSQL、归属与迁移证据

本场景在既有独立 PostgreSQL 实例执行与初始化／迁移入口共用的 `MATCHING_SCHEMA_SQL`，随后真实插入、读取、重复准备及重排，保留既有记录；没有只检查表存在就宣称完成。独立通用迁移 CLI 未运行，也未构建新应用镜像，本项不扩充为生产云部署证明。

两个预置验收身份实际登录。B 不能从 A 会话准备快照，也不能预览 A 快照，均 404；B 用显式公开记录绑定 A 会话仍为 404。B 不绑定会话时可创建并预览自己的真实 PostgreSQL 快照，覆盖 NULL 会话与 UUID 参数；A 不能读取该 B 快照。调用方复制内容并自报 `saved_research` 标记为 422，不能伪装服务端来源。所用记录均出自本次真实公开研究，没有伪造评分输入。

这些是 MATCH.5 的真实驱动、会话绑定、owner 及重排业务证据；并发压力、故障注入与整套安全回归未执行。

## 产物与边界

[原研究](organization-rerank-20261021/source-result.json)、[源快照](organization-rerank-20261021/snapshot.json)、[首次偏好](organization-rerank-20261021/before.json)、[修改后偏好](organization-rerank-20261021/after.json)、[首次界面](organization-rerank-20261021/before-rerank.png)、[修改后界面](organization-rerank-20261021/after-rerank.png)、[独立新研究结果](organization-rerank-20261021/fresh-result.json)均保留实际输出。

当前只自动计算标题词面与有界时效；路线契合、完整度、合作互补和未取得指标保持未知。学科组沿用请求标签，尚未逐篇自动分类；家族未链接、正文引用审核不足等限制仍保留。完整自动评价、更多学科案例、深读／行动与导出继续按后续任务推进，不将本项当作 ORG 整体或全部报告事实验证完成。
