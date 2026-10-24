# OpenSpec 3.2–3.5 交付记录

日期：2026-10-19。用户明确要求完成 3.2–3.5 并同步 TODO 和文档。代码交付为确定性匹配、不可覆盖的 owner 证据快照、创建／重排 API，使用说明见[匹配预览 ACI](../research-matching-preview.md)。

## 新增行为与实际证据

| 任务 | 新行为 | 观察到的结果 |
| --- | --- | --- |
| 3.2 | 对象类型／具体选择、学科／时间、确认关系与明确指标先硬筛选，再按共同口径和研究家族等权聚合；保留来源与特征规则 | 高分企业仍被高校单选排除，未知资助或未确认依据不能通过；JIF 硬阈值先排除观察；词项覆盖实际产生主题特征，家族平均有可复核分项依据。 |
| 3.3 | 指标贡献经组权重及成果表现父维度预算分配，显示来源、映射与贡献 | 根层 80%／20% 时，分别启用单项 JIF、三项 JIF／分区／JCI，成果表现贡献均为 20 分；不突破父级上限。 |
| 3.4 | 缺失区间、权重覆盖率、待补证、跨组不可比及严格区间优势 | 甲 54–94／60% 覆盖、乙 76，重叠时无确定优劣；已知零值覆盖率不丢失；家族局部缺失保留分母；无适用维度返回空区间。 |
| 3.5 | 认证 owner 绑定的不可覆盖快照、可选会话归属、同证据修改权重只读重算 | 9:1 和 1:9 权重使 A/B 顺序反转；同一快照载荷与事实未变；他人快照 404、候选覆盖字段 422、绑定他人会话拒绝、会话归属变化后访问重新拒绝。 |

新增 `app/db/matching.py` 及普通初始化／迁移 DDL 接入，扩展 `app/research_matching.py`，研究路由增加两项 API；新增行为用例仅在 `tests/current_change/test_matching_preview.py`。

## TDD 与检查

- 初次 14 项全部预期失败（404，16.28 秒），两个新入口尚不存在；实现后 14 passed，23.58 秒。
- 聚焦自审新增 5 项边界，观察 3 failed／16 passed，7.69 秒：无适用维度的提示缺失、过滤后全零指标报错、非法原始分区被接受。修复后 19 passed，7.74 秒。
- 补充适用性、明确指标硬条件和家族缺失口径，观察 1 failed／21 passed，6.64 秒：材料组错误接受 CCF 配置。复用已有适用性判断修复，最终 **22 passed**，7.92 秒。
- 受影响生产文件与本轮新增用例 Ruff 返回 `All checks passed`。

仅运行本轮新增行为文件，没有运行上一轮权重／评价测试、既有回归或 smoke、启动／导入、存在性、hash／文字探针。现有 LangChain 依赖产生 1 条未来默认值警告。

实际命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/current_change/test_matching_preview.py -q --tb=short
.venv/Scripts/python.exe -m ruff check app/research_matching.py app/db/matching.py app/db/connection.py app/db/migrate.py app/api/research.py tests/current_change/test_matching_preview.py
```

## 数据、权限及验证范围

用例通过真实 FastAPI 路由、Pydantic 契约、生产评分函数和生产快照 SQL 消费请求，数据库采用临时 SQLite 执行实际 DDL／SQL，适配器只转换 asyncpg 调用形状和日期参数。归属条件由生产 SQL 执行，没有复制到测试替身里。主体依赖用两个固定测试 owner 替换，未声称验证凭据流程。

新权重预览用例阻断实际 HTTPX 同步／异步网络传输；没有新的外部请求。不可覆盖性检查比较数据库中的实际业务载荷，而非文件摘要或实现代码文字。所有机构、家族和量表为明确的替代输入，没有用其宣称真实合作关系或业务准确率。

Docker 清单读取显示本机 PostgreSQL 容器引擎不可用，因此未运行真实 PostgreSQL 实例迁移，也没有用健康检查代替功能证据。SQL 的 PostgreSQL 类型／驱动集成仍是部署验证缺口；SQLite 行为不能扩大为该实例验证已通过。

本轮是数据契约、计算和已有认证下的资源隔离，没有新增 Agent、A2A 或委派边界。确认状态代表 owner 对证据的声明，预览不独立核实来源；主研究链路、恢复快照和报告集成仍属第 4 组。一次聚焦自审按新增输入边界、区间、权限及完成口径审阅，未委派其他 Agent。

3.2、3.3、3.4、3.5 逐项勾选后，每次刷新 OpenSpec apply 分别确认 12/34、13/34、14/34、**15/34**，余 19 项。`openspec.cmd validate add-organization-research-matching --strict` 返回 `Change 'add-organization-research-matching' is valid`。
