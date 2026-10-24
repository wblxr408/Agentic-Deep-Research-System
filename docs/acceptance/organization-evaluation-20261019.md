# OpenSpec 1.4–3.1 交付记录

2026-10-19。用户要求从已完成的 1.1–1.3 继续做到 3.1，本轮范围为 1.4、2.1–2.6、3.1 共八项。交付可调用的基础模块和预览／归一化 API，不包含 3.2 之后的评分与研究链路、界面。

## 实施与证据

| 任务 | 实际交付 | 验证及数据边界 |
| --- | --- | --- |
| 1.4 | 发表与家族双口径、显式家族证据、共著／资助／引用独立关系、对象全计数与汇总并集 | 会议＋扩展版为两条发表／一个家族，双方共同成果汇总不重计；同标题无证据不合并，资助和引用不产生署名。7 个新增 HTTP 行为用例。 |
| 2.1 | 20 项体系的学科／成果类型／指标层级、版本与可用性清单 | 计算机会议、材料期刊、商科期刊的分派与拒绝原因；来源接入状态见 [ACI 文档](../research-evaluation-and-weights.md)。 |
| 2.2 | CCF、ICORE 精确身份／轨道和指定历史版适配 | 新增消费用例覆盖历史变化与附属轨道不继承。真实 CCF PDF 镜像样本和 ICORE 官方历史记录各自保留来源；不是全目录。 |
| 2.3 | 四类 WoS／Scopus 收录及 JCR、期刊分区表、CiteScore／百分位、SJR、SNIP 的独立记录与授权导入适配 | 用明确替代输入验证多类别、多年份与来源不可用；未取得真实商业指标，不能据此宣称连通数据服务。 |
| 2.4 | ABDC、AJG 独立等级、版本、缺失／未收录状态适配 | 官方 ABDC 工作簿真实读取历史工作表，保存一家期刊样本；AJG 需登录，实际仅完成授权导入路径，等级／历史用例采用替代输入。 |
| 2.5 | 提供方限定的论文引用百分位、CNCI、FWCI 记录；OpenAlex 原始响应归一化 | 真实取得 OpenAlex W1951724000 并生成预览；CNCI 无真实授权数据，保持缺口，授权导入用例不冒充真实采集。 |
| 2.6 | 每项来源状态与统一 ACI：输入输出、权限、批次、错误、预算、运行边界和后续动作 | 内容与实际接口／数据一致性审阅；三个新增接口运行时均不出站。 |
| 3.1 | 两种分层预设、自定义／覆盖、启停、稳定归一化、版本化有序映射 | 6:4→60%:40%、零权重停用、恢复预设、分层权重、大有限数、非法配置和关闭父层的消费用例。尚不输出匹配分。 |

## TDD 实际结果

仅新增并运行本轮行为文件，没有运行上一轮的范围用例、既有回归或 smoke／启动／导入／存在性／hash／文字断言。

| 新增行为文件 | 实现前 RED | 实现后 GREEN |
| --- | --- | --- |
| `test_research_families.py` | 3 failed／4 passed，8.49 秒；家族／关系字段尚不存在，计数键缺失 | 7 passed，7.07 秒 |
| `test_evaluation_adapters.py` | 15 failed，9.75 秒；新路由 404 | 15 passed，13.19 秒；公开快照加入后的同组结果为 15 passed，9.76 秒 |
| `test_openalex_evaluation.py` | 3 failed，10.98 秒；新路由 404 | 与权重组共同运行：17 passed，13.77 秒，其中本文件 3 项 |
| `test_weight_configuration.py` | 先修正 pytest 保留参数名的收集问题（不计 RED）；随后 14 failed，13.71 秒，新路由 404 | 初始 14 项通过；补充两项边界后观察 2 failed／14 passed（9.33 秒），再修复至 16 passed，8.21 秒 |

用例使用真实 FastAPI 路由，登录主体依赖用固定测试主体替换，未重新验证认证本身。替代输入的来源与授权声明不代表取得真实商业许可证。现有 LangChain 依赖产生一条未来默认值警告。

本轮四个文件共 **41 个新增行为用例通过**。受影响的生产文件与这四个新增用例文件执行 Ruff，返回 `All checks passed`。OpenSpec 八项逐项勾选并刷新，进度从 3/34 增至 **11/34，余 23 项**；`openspec.cmd validate add-organization-research-matching --strict` 返回 `Change 'add-organization-research-matching' is valid`。

实际命令按上述新增行为组分别执行（未包含其他测试文件）：

```powershell
.venv/Scripts/python.exe -m pytest tests/current_change/test_research_families.py -q --tb=short
.venv/Scripts/python.exe -m pytest tests/current_change/test_evaluation_adapters.py -q --tb=short
.venv/Scripts/python.exe -m pytest tests/current_change/test_weight_configuration.py tests/current_change/test_openalex_evaluation.py -q --tb=short
.venv/Scripts/python.exe -m pytest tests/current_change/test_weight_configuration.py -q --tb=short
.venv/Scripts/python.exe -m ruff check app/research_scope.py app/research_evaluation.py app/research_matching.py app/api/research.py tests/current_change/test_research_families.py tests/current_change/test_evaluation_adapters.py tests/current_change/test_weight_configuration.py tests/current_change/test_openalex_evaluation.py
openspec.cmd validate add-organization-research-matching --strict
```

完成前做了一次聚焦自审：输入及来源边界、时间／身份精确匹配、家族口径、权重层级和文档进度相互核对；关闭父层和布尔权重的问题按新增失败用例修复。没有委派独立评审 Agent，也未将自审当作外部真实性核验。

## 真实数据消费

公开取证发生在本轮开发阶段，保留于 [来源证据目录](evaluation-sources-20261019/)，不是由预览 API 自动联网。实际输入进入生产适配函数并保存了以下业务结果：

- CCF NSDI：2012 版 B、2022 版 A；来源为 CCF 发布 PDF 的公开镜像，未将旧版当现版。
- ICORE SIGCOMM：CORE2023 与 ICORE2026 均 A*，分别保留官方查询 URL。
- ABDC JIBS：2025 及五个历史工作表均保留原始 A*；样本按印刷／在线 ISSN 分别表达。
- OpenAlex 原始 W1951724000：本次返回 FWCI `3266.5958`、引用百分位 `1.0`；归一化保留提供方、2015 发表年、文献类型、子领域、2018-12-31 引用窗口截止、2026-10-19 快照及提供方更新时间。数值会随数据库更新而变化，本次仅代表保存的响应。

未读取 `.env`，未运行模型或创建付费服务，没有提交、发布或对外发送消息。现有多 Agent 拓扑／委派边界未变；本次是本地数据契约与计算，不新增 A2A，也不声称完成新的安全基线控制验证。
