# 组织范围任务 1.1–1.3 交付记录

日期：2026-10-19。用户明确选择 `add-organization-research-matching` 的 OpenSpec 任务 1.1–1.3。交付为登录研究路由中的范围预览 API 和纯数据契约，接口使用与限制见 [使用说明](../organization-research-scope.md)。

## 实际变更

| 任务 | 交付与行为证据 |
| --- | --- |
| 1.1 | 三类机构的七种非空组合、默认全选、显式空选择拒绝、类型冲突、非法日期／主题／学科拒绝。 |
| 1.2 | 具体对象精确保留、多个同名实验室不同 ID 不合并、单多实体契约、候选发现条件及来源／待消歧状态保留、无来源或非法 URL 拒绝。 |
| 1.3 | 有来源和有效期的高校—院系—实验室关系、发表时原始署名、当前任职分别保留；父子视图独立、汇总成果只计一次、关系过期后停止继承、研究时间外成果排除、非法引用／循环／冲突 ID 拒绝。 |

新增 `app/research_scope.py`，在既有 `app/api/research.py` 注册 `POST /api/v1/research/scope/preview`。消费用例在 `tests/current_change/test_organization_scope_preview.py`，先写用例后实现。

## 实际验证

命令：

```powershell
.venv/Scripts/python.exe -m pytest tests/current_change/test_organization_scope_preview.py -q --tb=short
.venv/Scripts/python.exe -m ruff check app/research_scope.py app/api/research.py tests/current_change/test_organization_scope_preview.py
```

首次运行：29 个用例全部按预期失败，接口尚不存在，HTTP 404，9.38 秒。实现后：同一组 **29 passed**，8.91 秒。Ruff 返回 **All checks passed**。现有 LangChain 依赖产生 1 条 `allowed_objects` 未来默认值变化警告，不影响本组结果。

用例通过真实 FastAPI 路由消费请求和响应，替换登录主体依赖；不能据此声称认证机制已重新验证。机构、论文和来源是明确的替代输入，没有访问外网、模型或数据库。只验证本次新增行为，没有运行既有回归、smoke、启动／导入探针或文件／文字断言。

## 交付边界

任务 1.1–1.3 的基础契约与预览可调用。它们尚未进入正式研究创建／执行／恢复链路，前端也未接入；对应任务 4、5 保持未完成。候选发现目前交付的是输入与查询契约，接口不开展真实候选采集，也不验证输入 URL。统计按成果 ID 去重，研究家族／扩展版合并仍是任务 1.4。待消歧实体的条件预览与外部事实核验分别呈现。

`openspec.cmd instructions apply --change add-organization-research-matching --json` 在逐项勾选后分别报告 1/34、2/34、3/34；最终余 31 项。`openspec.cmd validate add-organization-research-matching --strict` 返回 `Change 'add-organization-research-matching' is valid`。

完成范围内做了一次自审，核对输入边界、历史归属、计数及文档完成口径；修正设计和实现计划中沿用的“仅规划”描述。没有新增 Agent、委派、协议或授权边界，沿用流程设计中的既有架构评估，本次不声称完成新的 A2ABreak 控制验证。
