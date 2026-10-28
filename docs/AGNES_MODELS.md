# Agnes模型与开发委派

2026-10-28。用户授权将Agnes加入研究平台，并用于独立、简单的代码工作。当前默认选择`agnes-3.0-flash`，复杂设计、关键边界和最终审阅继续由主执行者负责；按实际任务选择，不因有第二模型就增加一次无用途调用。

## 平台设置

在“我的模型”中可选择Agnes 3.0 Flash、2.5 Flash及2.5 Pro，默认中国站`https://api.agnes-ai.cn/v1`。官方依据：[中国站说明](https://agnes-ai.cn/en/docs/overview)、[3.0 Flash接口](https://wiki.agnes-ai.com/en/docs/agnes-30-flash)。2026-10-28本人中国站实时模型目录包含上述模型；可用性、额度和价格随账号而变，本次费用未独立确认。

“保存为可选配置”将提供方、模型和密钥加密保存在当前账号中，页面仅返回配置元数据。“已保存的模型”中的“应用此配置”才会切换当前主模型；已有DeepSeek可以继续保留。每个账号独立保存，其他账号不继承凭据。正在运行或恢复的研究仍核对冻结的原模型配置，新增可选配置不会替研究补额或改写合同。

接口：`GET /api/v1/config/llm/profiles`列本人配置；`POST /llm/profiles/{provider}`保存；`POST /llm/profiles/{provider}/activate`明确应用。后两个路径同属`/api/v1/config`。已有配置表复用短名称`mp:{owner}:{provider}`，不需要迁移；部署须配置`SECURITY_ENCRYPTION_KEY`，已有加密数据必须保留原密钥。

## 本机开发委派

`scripts/agnes_delegate.py`复用现有OpenAI SDK。当前Windows用户的Key存放在仓库之外的DPAPI文件，默认`~/.codex/secrets/agnes-adrs.dpapi`；其他主机可由进程环境提供`AGNES_API_KEY`，不把Key写在命令里。官方区域端点由`AGNES_API_BASE`选择，不自动跨区。

```powershell
& .venv/Scripts/python.exe scripts/agnes_delegate.py --task-file path/to/task.md --file app/example.py
```

其他已明确授权的代码仓库可通过`--repo-root`指定；文件和产物均归该仓库。默认单次6,000输出Token，上限12,000，最多8个文件、单文件48KB、总输入96KB；一次请求、无自动重试、有限连接／读取超时。按任务需要并行独立调用，避免对同一待修改文件并行写入。

发送前拒绝仓库外路径、依赖、资料目录、`.env`、二进制及明显凭据。接口无工具、shell或递归委派，返回的文件路径必须属于显式选择。合法结果写入`outputs/agnes-delegations/<job>/candidate.json`，同时保存请求、原响应和用量回执；不会自动修改源文件。主执行者阅读建议、核对当前差异后应用必要部分，按用户当前检查限制处理。格式合格不代表代码正确，第二模型也不能声称没有实际运行的检查。

适合委派：一个目录条目、局部文案、清楚限定的小函数修改、有限源码审阅。涉及权限、预算、数据流或多模块取舍时先由主执行者拆清任务；返回内容扩大范围、断流、截断或格式错误时保留失败。所有预期之外的检查仍受现有用户禁止项约束。

## 实际状态

专用Key已获当次创建确认并完成中国站调用。首项端点目录修改报用量1,609 Token，主执行者审阅后只采纳两项目录新增；第二项报告结构审阅报用量7,046 Token，未返回修改，主执行者只保留有用边界建议并独立处理明确的格式问题。两项共8,655 Token，服务端费用未知；未衡量总体提速或宣称质量保证。

模型已保存到当前浏览器使用的工作区账号`acceptance_owner_222b60f6`，当前主模型仍为DeepSeek；其他账号仍需本人保存。详情见[实际记录](acceptance/agnes-models-20261028.md)。A2ABreak v1.0的11项适用性、控制点及未验证边界见[设计](../openspec/changes/add-agnes-model-integration/design.md)。
