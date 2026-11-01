# 原架构精简实施记录

## 2026-11-01：原生用量与分项费用（部分实现，待实际接受）

工作分支为`codex/simplify-existing-architecture`，沿原变更`refactor-single-research-agent`的5.1／5.5实施。当前在本机修改；已找到可用云环境，但现有接口不能迁移调用中的聊天，未另开云端聊天。权威范围仍由[总计划](../IMPLEMENTATION_PLAN.md)和[原任务](../../openspec/changes/refactor-single-research-agent/tasks.md)维护，本记录只保存实际差量与证据边界。

### 当前源码差量

| 原任务 | 修改及消费者 | 状态与剩余范围 |
|---|---|---|
| 5.1原生usage | `llm_usage.py`统一解析原生usage；Anthropic非流式与完整流式结果保留全部usage，累计流事件替换而非相加；`llm_budget.py`和`llm_client.py`共用归一结果 | 源码已接。Chat／Responses输入包含缓存，Anthropic单列缓存后再合计，DeepSeek命中／未命中分区；缺失明细保留未知 |
| 5.1根限额与报价 | 沿原call_id、准入、settle和JSON收据保存明细；逻辑Token全额计量，取消／未知沿原保守预占；缓存报价按读、写和有效期分项；有报价的缓存写入溢价进入原费用预占 | 源码已接；不改旧收据、不退款或新增账本。实际端点能力声明、请求缓存参数及稳定前缀适配仍未完成，兼容网关不会因此收到新专有参数 |
| 5.1用途 | 原BudgetedClient可给现有调用标注operation与content_unit_id，规划／分析／研究缺口审核沿阶段归因；事实范围选择、事实判断、读者／材料／重复影响、读者修订及章节格式修复分别归因 | 已接上述调用，元数据不进入供应商请求。其余细粒度修订、图文及特殊回退用途仍需继续核对 |
| 5.5成本投影 | `runtime_accounting.py`仅投影原唯一收据，输出分项、已知费用小计、未知请求、用途和供应商缓存读写；保留旧汇总字段，schema升v2 | 源码已接。应用免调用复用、失效原因、逐篇／主题的正常研究与开发返工归因仍待实施；不宣称已经节省Token |

普通输入、缓存读、缓存写和输出是互斥计费类别；缓存写不在普通输入价格之上重复加收。DeepSeek的miss沿其普通输入价，不再另加一次写入费。Anthropic有5m／1h原生明细时分别用所配置报价；不能确定有效期或缺某项报价时只显示已知小计，完整费用保持未知。缺字段、未知价格与真实零消费分别表达。现有静态模型价格只作明确标注的参考，不能充当当前端点账单。当前计价范围是Token报价估计，供应商存储／其他计费项目尚无完整合同与收据。

原生语义依据：[DeepSeek缓存字段](https://api-docs.deepseek.com/guides/kv_cache/)、[Anthropic缓存usage与有效期](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)、[OpenAI缓存usage与模型差异](https://developers.openai.com/api/docs/guides/prompt-caching)。未套用官方折扣给兼容网关，也未新增预热请求或真实模型调用。

### 审阅与验证边界

仅完成源码及调用链审阅：供应方响应→适配／归一→原预算settle→原执行控制model_receipt→按call_id替换的数据库收据→runtime_ledger投影。已核对原`merge_receipt_budget`整条替换收据，新增明细随原JSON保存，不需第二张消费表或重新加总阶段摘要。流式Anthropic未观察到message_stop时不发布完整usage，沿原未知消费处理。

未执行局部／TDD／回归、构建／类型／lint／schema或任何探针，未启动真实研究／付费比较。没有运行输出证明本次语义、费用或百篇效果已经通过。因此5.1／5.5仍未勾选，其余任务不因共用文件被标完成；后续按用户明确的模块级真实旅程取证。

### 安全沿用与执行点

应用A2ABreak基线v1.0，[design.md D11](../../openspec/changes/refactor-single-research-agent/design.md#d11-安全基线与本次适用性)已有全部11项适用结论，本次增量复用该评估。相关项均为工程1—4、验收T1—T3：A2AB-03《上下文归属与跨租户隔离》沿原owner／任务收据读取；A2AB-06《并发状态版本与审批绑定》沿原execution围栏和call_id替换；A2AB-08《结构化授权请求与权限不放大》只接服务端报价，usage不授予端点权限；A2AB-10《委派环路检测与全链预算》在原reserve／settle全额扣逻辑Token；A2AB-11《中断任务租约与有界资源回收》保留未知派发、deadline与原取消回收。上述仅审阅既有控制点和本次接线，未运行功能或安全接受。

其余沿D11逐项保留：A2AB-01《技能声明验证与委派准入》未改Skill准入；A2AB-04《长连接撤权与事件出口鉴权》未改SSE；A2AB-05《产物分块校验与断流恢复》未把部分报告或断流改记完整；A2AB-07《Webhook归属验证与受控出站》未改Webhook或出站授权。A2AB-02《Agent Card可信密钥与身份绑定》和A2AB-09《多跳主体溯源与凭据防转用》因没有远端Agent发现／跨组织多跳，具体机制仍结构性不适用。这些是来源核对的工程建议，非供应商官方修复或项目已验证保证。

### 后续接续

继续完成5.1／5.5实际端点与复用归因差量，然后按原顺序接3.1—3.4／2.1—2.4及后续依赖：RAG资料库中的论文成员、筛选／阅读层级、缺字段队列→主题证据→有界章节→增量审核→原R8图型／独立论文图块与多格式交付。目录／分级／补证当前仍按[复用适配表](../CORPUS_RAG_INTEGRATION_PLAN.md)待接，已有解析／检索不重新开发。
