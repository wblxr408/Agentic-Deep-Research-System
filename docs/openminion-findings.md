# OpenMinion Building Blocks Tested / What We Learned

核对日期：2026-10-18。环境：Windows、Python3.11.7、PyPI OpenMinion0.1.7。SDK为可选依赖；[运行说明](openminion-research.md)给出任务、工具及复现命令。此文记录本项目实测，不代表SDK的全部功能或官方问题确认。

## 使用的构件与实际作用

| 构件 | 本项目实际使用 | 证据边界 |
| --- | --- | --- |
| `Agent` / `APIRuntime` | 模型自主选择公开搜索／读取，生成组织研究结果；已有片段再送SDK模型核验 | 新行为用例使用真实SDK和替代HTTP模型，真实DeepSeek运行另存产物 |
| `@tool` | 注册两个只读函数，明确`min_scope=READ_ONLY`，闭包绑定本次预算和证据 | 不允许模型登记新工具；工具列表显式限定 |
| Provider | 日常模型走OpenAI兼容适配；Cortensor使用SDK原生provider | Cortensor替代HTTP用例通过，不是Cortensor网络运行证明 |
| Session | 每次研究和核验使用新session，整个runtime的home/data按运行隔离 | 不提供长期记忆或跨运行恢复；未测试相关能力 |
| Typed output | 综合的findings/questions/gaps/missing_requirements，核验的verdicts；程序生成最终报告 | 逐事实来源编号及必需维度检查，终审有未支持事实不能completed |
| Permissions / limits | 显式工具、SDK步数／工具次数、应用截止及字节预算 | 有限新行为用例，不是所有攻击路径的安全保证 |
| Diagnostics | 保存run ID、SDK状态／统计、实际工具轨迹和来源 | 模型自述不替代轨迹，秘密与原始provider异常不导出 |

没有为了展示构件而加入技能、A2A委派、定时任务或长期记忆。组织研究一次性公开取证已经能检验工具执行、provider、权限、session、结构化结果和诊断。

## 发现1：canonical正文附带Agent名称

复现：最小配置提供一个名为`organization-research`、`default_channel=console`的Agent；替代HTTP模型返回Markdown或JSON正文；调用`Agent(...).run()`。预期可直接消费模型正文，实际0.1.7的`result.text`形如`organization-research: # Example Lab`，JSON也有相同前缀。该行为在安装源码`services/brain/post_execution/postprocess_response.py::_agent_response_from_postprocess`中可定位。

影响：直接`json.loads(result.text)`失败，Markdown标题也不在行首，导致保守主张提取把标题当作无引用主张。

本地解决：保留采集正文为draft，由独立、无工具权限的SDK综合阶段消费真实证据并返回typed output；核验也使用`output_type`指定Pydantic模型并消费`result.output`。保留采集与综合各自的SDK标识和统计，不把第二阶段统计当成采集统计。

建议：将传输展示前缀与canonical内容分开，或给出稳定的`content`字段；文档明确`text`是否带展示封套。已有`output_type`的使用说明值得放到入门示例中。

## 发现2：最小Agent配置需要显式本地channel

复现：只设置provider而不设置profile的`default_channel`，直接通过本地SDK调用。实际在`enforce_inbound_authenticity`拒绝，尚未进入模型和工具执行。

本地解决：为这个不对外开放的CLI明确`default_channel=console`，保留SDK权限检查。没有设置全局安全关闭开关，也没有把公网入口标记为本地可信。

建议：SDK入口校验缺失channel时返回面向调用者的配置提示；在最小配置示例标注信任边界。该项属于配置可用性反馈，不声称鉴权拒绝本身是漏洞。

## 发现3：Windows上重叠home/data可能掩盖原始错误

本项目首次真实运行将临时home和data指向同一路径，provider配置错误发生后，退出临时目录时得到`NotADirectoryError`，覆盖了有用的原始异常。产物：`docs/acceptance/openminion-msr-20261018/result.json`。改为独立home/data及分离identity数据库／bundle路径后，下一次能准确保留`ProviderError`：`openminion-msr-20261018-attempt2/result.json`。

建议：bootstrap拒绝或明确支持重叠根目录；清理异常作为附加错误保留，不覆盖业务异常。当前本地解决使用独立临时根；临时目录清理失败不覆盖研究结果。不能据此宣称所有Windows目录布局都已验证。

## 发现4：截断、网页导航和空搜索会制造“运行成功”的假象

最初DeepSeek真实任务确实调用了搜索和读取，但web预算仅1次底层调用，未走有效备选；网页开头导航挤占工具上下文，报告只能说明证据不足。该产物曾被旧的完成条件标为completed；其报告和原始轨迹保留在`docs/acceptance/openminion-msr-20261018-deepseek/`，应按**研究未完成**理解，不能作为成功业务结果。

本地解决：搜索允许有界的3次底层尝试并保存attempts；HTML优先main/article并过滤导航；模型可用focus读取保留原文中的相关窗口。研究结果有独立task_status/gaps；SDK completed不直接等于研究completed。最终报告还须具有实际来源支持的主张。修正后的真实运行另存新目录，不覆盖旧失败证据。

建议SDK工具结果提供结构化截断元信息及原文片段偏移；诊断明确模型执行结束和业务目标完成的区别。发现此问题依赖读取实际产物，单纯HTTP200或SDK结束状态无法证明研究成功。

## 发现5：论文任务需要正文级读取与可复用取证

先前r4实际研究拿到论文摘要，但PDF受1MiB上限及文件格式限制无法读取，报告仍推断了机构角色及未经核实的技术条件。该次结果为partial，不能作为完整研究交付。r5已读到Reverie全文，但InvisiFlow正式版约26MB，仍超初始4MiB预算。当前有界调整至32MiB／文件、64MiB／轮；页面工具至多补读首个合规论文PDF，pypdf解析在既有受控子进程内完成。正文保留160000字符及页码偏移，相同URL的不同focus复用正文。新增消费用例已验证后部实验限制、稳定引用和不重复下载；真实外网结果仍单独评估。

## 发现6：工具采集草稿不能替代证据综合

r5返回长篇无引文草稿，仅做格式修复只能保留缺引文，最终0/39支持；r6在重复检索后得到SDK上下文预算终止消息，不能当作报告。采集和格式有效均不足以证明业务任务完成。

当前做法：工具阶段保留真实证据和草稿，随后同一SDK执行一次无工具的证据综合，再核验最终文本。综合从来源建立引文，可以修正草稿；不能仅凭草稿补出事实。采集、综合、核验使用新session，沿用同一根截止时间与来源边界。工具响应缩短链接／页码元信息，并将论文正文按focus返回，完整原文不塞入每一步上下文。

这不是已证实的SDK缺陷归因：安装源码followup.py从默认profile读取system_prompt，因此本地同时配置profile提示与Agent.instructions，并保留真实失败产物供进一步复现。SDK建议明确区分工具采集结果、草稿和最终可校验交付，并说明run.stats对后处理模型／工具调用的覆盖范围。

SDK建议：结构化工具结果允许明确表示“发现链接”“保留原文”“上下文窗口”和“截断范围”，使模型能决定下一步补正文，而不是把索引摘要当成已读全文。任务完成状态应同时考虑实际目标覆盖和未解决的证据缺口。

## 发现7：typed output会校验结果，但不会自动修复格式

r12已采集6来源及两份全文PDF，却在综合时因7个后续问题超过1–4的契约而抛出AgentOutputValidationError。安装版本的api/agent.py将output_type用于返回正文的本地Pydantic校验；没有因此自动向模型附加JSON Schema或重试。不能把“使用typed output”当作模型必然遵守全部字段边界的保证。

本地解决：综合消息明确包含本阶段契约；仅当该异常发生且根预算足够时，使用新session、无工具执行一次格式修复，附上schema及失败原文，要求保留研究事实和引用。原文与恢复状态保存在format_recoveries中。再次失败直接终止，不重新采集、不无限重试；成功也须接受原有范围检查和最终来源核验。两个新增恢复消费用例先RED再GREEN，2passed4.39秒；真实业务效果另看完整实跑。

建议：公开说明output_type的校验范围、是否向provider传schema、错误如何携带原始结果及使用统计，并提供有界修复示例。失败调用的统计目前未能从该异常取得，不把恢复调用统计冒充该阶段总成本。

整篇复核又暴露契约传递问题：仅依赖Agent.instructions时，本案例返回results/verdict，缺少verdicts/status/quote，A／B均0/14且保留失败原文。任务契约同时显式放入调用消息后，C恢复有效输出12/14；这只说明本地规避有效，不据此断言SDK所有入口都忽略instructions。窗口增加不同条件覆盖及有界后文后，D对同一篇报告达到14/14，原采集状态不改写。复核与新采集分开保存，详见[交付证据](acceptance/openminion-delivery-20261018.md)。

r15又出现一次散文输出和PDF引语转写失败，当前改为选择已有excerpt_id并由程序附原文；未知／跨来源编号拒绝，语义判断与人工状态不变。SDK格式失败至多重试一次无工具JSON。2026-10-19新采集r16完整成功：6来源、两份全文、11次工具、193.797秒，13/13自动支持，研究／核验错误为空。它证明本次有界案例可运行，不证明所有任务稳定或所有模型判定正确。

修订输入也须独立预算：r14重复传整篇报告、原文包及审计片段造成SDK决策上下文超限；只传prior_findings、来源元数据、最多12000字符问题（每项最多3片段，披露遗漏）后，冻结失败输入的真实SDK目标返回有效简报，5957输入tokens／1117输出tokens，范围检查无缺项。原文仍在evidence，不随上下文压缩删除。

## Cortensor生态结合评估

研发团队需要按公开证据追踪组织研究方向，Cortensor可承担可替换的推理与独立文字复核；工具输出和主张来源表也可作为builder验证模型遵循工具契约、处理证据冲突和限定条件的可复用材料。

[Portal官方文档](https://docs-v2.cortensor.network/products/portal-and-api-gateway/)目前声明托管兼容接口以文字输入输出为主，未开放tool/function calling。因此首选结合是主模型取证、Cortensor对固定公开材料综合／核验；SDK原生Cortensor的hybrid文本工具路径需获配端点后单独实测。直接Router与Portal的session归属和模型别名不同，不应复制同一份配置假定等价。

[Hackathon说明](https://docs-v2.cortensor.network/ecosystem/hackathon-5/)强调实际SDK运行、可重复工作流、真实模型演示及建设性反馈；Portal访问可选且受容量限制。本项目没有发送访问申请、创建付费账户或伪造Cortensor网络运行。

## 当前新增行为验证

只执行`tests/current_change/`中本变更新增行为用例，先观察缺失行为的预期断言失败，再达到通过。包括：后部证据、第16条来源、最终报告矛盾主张、错误引用／伪引语／漏检、预算耗尽不调用审计、真实SDK两provider适配、工具超限不多读、预取消及私网入口拒绝。外部HTTP模型和页面读取有替代实现；真实研究产物另核对，不把替代响应当作外部服务证明。未运行回归或旧安全套件。
