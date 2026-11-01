# Spec Delta

## Purpose

将研究过程的规划、执行内容和独立审计组织为同一研究根下的三个逻辑角色，使用户能够理解计划、证据、修改原因和交付结果。通过明确的产物交接、必要复核和可信运行边界支持自动流转，同时保留原有功能、授权、预算和恢复合同。

## ADDED Requirements

### Requirement: Three roles collaborate within one research root

系统 SHALL 在同一研究根内明确编排、任务和审计职责：编排决定计划与下一步，任务负责证据处理、分析、写作和局部修订，审计返回来源／阅读／图文问题及最小修复范围。角色交接 MUST 保留任务、产物版本、依赖和实际操作归属，不因角色切换重置预算或期限。

#### Scenario: Audit identifies a material issue
- **WHEN** 当前候选稿有影响核心结论的来源缺口
- **THEN** 审计返回问题、依据及修复范围，编排决定合法补证或修订，任务执行修改；各步骤共享原根额度和修订机会

### Requirement: Delivery is decided by trusted execution

系统 MUST 依据当前版本的问题覆盖、必要事实、读者和图文审核组合及实际交付状态裁决最终报告。角色的完成声明、概率和自评分 SHALL NOT 直接批准发布、扩大权限或改变运行上限；未完成时保留产物和明确原因。

#### Scenario: A role requests delivery with a decisive unresolved premise
- **WHEN** 任务或编排请求结束但当前建议仍依赖未核的决定性前提
- **THEN** 系统保留候选和缺口，按原范围继续必要处理或结束为未完成，不发布为合格最终报告

### Requirement: Preliminary judgement has an optional configured backend

系统 SHALL 在配置并获准使用Jev时将适用初判交给Jev，未配置时交给现有获准LLM完成同一判断。两条路径 MUST 共用判据与规范化输出，记录实际后端和模型版本；同次初判不默认重复调用两者，判断不能代替授权或事实证据。

#### Scenario: No Jev API is configured
- **WHEN** 研究需要一个适用语义初判且未配置Jev API
- **THEN** 系统由现有获准LLM承接该初判，保留相同输出合同与根计量，研究不因缺少Jev停止或跳过判断

#### Scenario: Jev API is configured
- **WHEN** 当前任务已配置并获准使用Jev API且需要适用初判
- **THEN** 系统选择Jev并记录实际版本，不同时强制执行一次相同LLM判断，不将Jev概率视为来源支持或发布许可

### Requirement: Roles use only necessary authorized context and valid reuse

系统 SHALL 以当前任务必要材料和版本化产物引用交接，按主体、任务、主张含义、条件、来源范围／版本、权限和模型／合同判断有效复用。相同已完成操作或同根并发重复请求 MUST NOT 默认产生第二份付费请求；未知派发沿原收据对账处理。

#### Scenario: A local revision changes a decisive condition
- **WHEN** 只修改一个段落但其中实验条件支持了其他结论
- **THEN** 系统使受影响依赖失效并复核，其余有效结果保留；最终组合覆盖当前稿，不按改动段落数直接放行

### Requirement: Tool work is bounded without compulsory role round trips

系统 SHALL 按计划依赖和当前准入执行工具批次，并按需使用搜索、原文获取、内部检索、注册能力和冻结技能。已明确且获准的独立步骤不要求每个工具前后新增编排与审计模型请求；没有内部资料需要时不强制RAG。

#### Scenario: Independent source reads are ready
- **WHEN** 当前计划有多个获准且互不依赖的原文读取任务
- **THEN** 系统在原份额内派发有界批次并保留各自收据，结果足以继续时直接推进，出现真实缺口才重规划

### Requirement: Role migration preserves the existing roadmap

系统 MUST 保留原功能、已实现待验收状态、冻结和外部条件，并为迁移差量指定唯一实现归属。角色名称变化不能取消研究内容要求、重复开发已交付共用能力或用旧架构证据宣称三角色已通过；正常自动流转不新增阶段人工确认门。

#### Scenario: A shared cache capability already has an implementation
- **WHEN** 原架构精简分支已交付当前所需的依赖复用能力
- **THEN** 三角色接合该实现和实际覆盖证据，仅实现角色适配差量，保留未覆盖验收及冻结范围
