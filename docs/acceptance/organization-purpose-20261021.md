# 研究目的与模块的真实端到端交付

2026-10-21，OpenSpec 7.1。新增行为为三种目的、推荐模块和自定义非空子集进入同一真实研究，报告按所选内容组装；目的、模板与匹配权重分别表达。运行使用本机实际 API、PostgreSQL、Edge、DeepSeek 和公开网页，无替代模型或伪造页面。契约与安全引用见[模块 ACI](../organization-analysis-modules.md)。

## 原始失败与修复

消费者 [`organization_purpose_e2e.py`](../../scripts/organization_purpose_e2e.py) 首先登录真实应用后提交独立高校、研究发展目的、仅 `evolution` 模块、合作发现权重的合法请求。原 API 因不支持 `purpose`、`modules` 返回 422，未创建研究；机器本地 `baseline-response.txt` 保存原响应。

接入后真实页面又发现：清空模块的错误提示被权重面板同值刷新清除；冻结请求模型不能用普通赋值设置推荐模块。分别改为只在权重实际变化时清除旧错误、在模型构建验证时解析并冻结模块。再次实际提交后已进入研究。

合作首轮 `c9431779-0a9b-4ef8-a4fd-c8de78702df9` 因一段无来源编号的 `observation` 被可信组装器拒绝，`issues` 非空，消费者失败；[原失败数据](organization-purpose-20261021/failed-cooperation.json)保留。没有自动补造引用或降低通过条件。补充模型指令：缺材料、不能确认和缺少独立验证应标为 `gap`，来源摘述必须带编号；无效段落另保留在 `rejected_paragraphs`。随后发起新的实际合作研究。该补充只约束现有写作调用，没有增加修稿轮次。

合作结果在 PostgreSQL 中保存后，页面摘要又暴露对象字段顺序与所选数组顺序不同。改为按冻结 `modules` 数组渲染；通过 `--session` 回访同一完成研究验证，没有因页面观察超时而重新研究。

## 实际结果

三条场景均只选 Peking University、计算机学科、2024 年，以 [USENIX DistServe 页面](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin)为种子；都使用合作发现权重预设，其中合作互补性保持 **15%**。页面切换三种目的时该比例不变，实际请求、运行配置和结果均保留独立字段。

| 实际新研究 | 内容选择和结果 | 原始证据包 |
| --- | --- | --- |
| `6a9d417e-effa-4916-8612-279808f99959` | 布局与演进，自定义仅 `evolution`。空模块先在 UI 拒绝且无研究 POST；实际正文只生成研究演进，另外保留方法／来源／审核附录，没有企业产品或合作分析页。单篇单年度不能确立多年趋势。 | [数据](organization-purpose-20261021/evolution.json)、[页面](organization-purpose-20261021/evolution.png) |
| `6369a49d-6fd3-4890-bc88-20270a0855bc` | 合作发现，默认研究全景、关系分析、交叉验证、后续行动。区分共著与协议／部署；缺合作需求时呈现待补条件和验证问题，没有发起联系。模块问题清单为空。 | [数据](organization-purpose-20261021/cooperation.json)、[页面](organization-purpose-20261021/cooperation.png) |
| `d71ca313-b5cc-4348-9d85-1191346c7764` | 综合研究，默认六模块。各模块都取得可消费段落和合法编号，界面、保存结果和导出采用同一冻结配置。 | [数据](organization-purpose-20261021/comprehensive.json)、[页面](organization-purpose-20261021/comprehensive.png) |

三条消费者均退出 0：真实新请求→模型／工具→结果→PostgreSQL 原正文／模块对照→页面刷新→实际 JSON 下载。综合场景额外下载 [Markdown](organization-purpose-20261021/report.md)和 [HTML](organization-purpose-20261021/report.html)，前者完整等于保存正文；在新建离线浏览器上下文打开 HTML，实际目的和六个章节可见，见[离线页面](organization-purpose-20261021/offline.png)。不是用类型、存在性或启动检查代替消费结果。

```powershell
.venv/Scripts/python.exe scripts/organization_purpose_e2e.py
.venv/Scripts/python.exe scripts/organization_purpose_e2e.py --purpose cooperation_discovery
.venv/Scripts/python.exe scripts/organization_purpose_e2e.py --purpose cooperation_discovery --session 6369a49d-6fd3-4890-bc88-20270a0855bc
.venv/Scripts/python.exe scripts/organization_purpose_e2e.py --purpose comprehensive
```

上列合作命令前一次创建完成研究、后一次回访完成页面验证；不是四条全部重新取证。运行期间只在对应研究已终态后重启所属 API 以加载修改，没有重启 Docker。未运行回归、冒烟、健康、导入／启动／文件存在性／文字探针或类型／构建／lint 等门禁。

## 证据边界与未完成项

本项通过的是内容选择和结构化交付。三条各只纳入 1 项发表、1 个研究家族；引用清单却分别有 **52、42、12** 条证据，含额外搜索噪声。对象种子网址仍不是导航白名单，本项不证明检索精准或仅访问单源；限定来源和样本流转继续由后续任务接入。补证中仍发生真实 `budget_exceeded`，尤其综合场景 11 条工具记录中 8 条被预算拒绝，均保留在证据包。

最终主张审计分别为：演进 7 项检查／5 项支持，合作 11／7，综合 17／9；全部 `needs_review=true`、人工未审核。模块 `issues=[]` 只表示选中 ID、段落契约和来源编号合法，不等于主张全部成立；模型计数、解释和未知仍需复核。低置信或缺全文不补造结果，不能把当前基础段落当作后续机制深读、关系核实或行动卡完成。

本次未重跑旧 v2、并发、所有跨 owner 或所有网关安全场景；安全评估复用 A2AB-03／06／08 v1.0 的既有控制点说明，不宣称完整部署安全验证。图像模板、绘图 Skill、7.2–7.8 和最终统一端到端交付仍未完成。
