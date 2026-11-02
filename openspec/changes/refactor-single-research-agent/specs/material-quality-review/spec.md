# Spec Delta

## Purpose

使研究审核以用户问题和错误的实际后果为依据，分别表达事实支持状态与交付影响。既阻止核心结论、归属和决定性比较中的错误，也避免边缘细节、合理复现或格式问题造成无止境修改，同时保留可追溯的判定和范围变化。

## ADDED Requirements

### Requirement: Essential claims include their decisive premises

系统 SHALL 将必答问题、核心结论、成果归属、决定性比较及建议所依赖的事实前提纳入必要核验，连同其数字、单位、条件、时间及外推范围。模型自报的低重要性标签不能免除这些依赖；重要性不明确时按必要项处理。

#### Scenario: A secondary number justifies the recommendation
- **WHEN** 写作把原先标为次要的实验数字用于支撑主要建议
- **THEN** 系统将该数字及所需条件提升到必要范围，在取得有效来源判定前不批准依赖它的结论

### Requirement: Factual status and delivery impact remain distinct

系统 SHALL 分别保存主张事实状态、审核范围及理由、问题实质影响和修复建议。免核项 MUST NOT 计为 supported；低影响项可以不阻塞交付，发现明确反证则须处理。核心错误不能由其他高分抵消，缺少足够证据时允许保持 unknown 或未核。

#### Scenario: An incidental detail is outside the essential scope
- **WHEN** 该细节不影响答案、选择或必要解释，并有当前范围下的明确免核理由
- **THEN** 系统保留其原判定或未核状态，单列免核，不因它未获来源判断而阻塞报告

#### Scenario: A central attribution contradicts the source
- **WHEN** 报告将决定性成果归属到错误机构，其他章节均已通过
- **THEN** 系统仍阻塞合格交付，给出定位及修复范围，不以总体评分放行

### Requirement: Proposed research is assessed against its factual premises

系统 SHALL 区分来源报告的事实、基于前提的推断、本报告提出的建议及任务方法。新课题和复现协议不要求来源预先提出同一建议，但其事实前提、实际资源和收益保证仍受必要范围核验，不能通过“建议”标签免除核心错误。

#### Scenario: The report proposes an unperformed combination experiment
- **WHEN** 报告明确提出检验两种有据方法的组合效果，未宣告成功
- **THEN** 审核核对方法和资源前提及建议身份，不要求论文已经证明该新实验有效

### Requirement: Repetition blocks only for material reading harm

系统 SHALL 结合命题、读者功能和实际后果判断重复。摘要预告、导航、不同对象的边界及结果旁必要条件不能仅因相同术语被判阻塞。阻塞判断须定位相关内容并解释其导致的误解、矛盾、论证缺失或实质阅读负担。

#### Scenario: Similar wording serves distinct reader purposes
- **WHEN** 摘要概述资源可用性而行动章说明具体资源入口，或两段分别限定硬件迁移与负载迁移
- **THEN** 审核按各自命题和用途判断，不将相似措辞直接认定为必须删除的重复

#### Scenario: A chapter only restates an earlier conclusion
- **WHEN** 后一章重复同一命题及论证，没有自身回答并挤占所需解释
- **THEN** 系统提出有具体位置和保留去向的实质问题，定向合并或修改而非仅搬入附录

### Requirement: Review scope changes by purpose rather than exhaustion

系统 SHALL 对实际问题、用途及重要依赖变化进行版本化范围调整，保存依据、差异和影响。预算不足、反复失败及模型自评分 MUST NOT 自动降低核心标准。正文、附录、图表和解说应使用同一当前核心范围；用户明确调整范围不重写历史判定。

#### Scenario: The remaining budget becomes insufficient
- **WHEN** 当前必要审核无法在原余额内完成
- **THEN** 系统保留稿件和未核清单，报告实际不足，不把必要项降为建议或标为支持

#### Scenario: A figure explanation uses an excluded incidental inventory
- **WHEN** 图文复核仍基于同一问题和主张范围且该枚举未成为决定性前提
- **THEN** 系统保留相同免核范围，不因进入图注或解释阶段重新要求逐项核验

#### Scenario: A theoretical paper is read for its formal contribution
- **WHEN** 同一次初读提供合法原文定位的理论导读合同，且用户没有另行要求实验字段
- **THEN** 系统围绕机制、假设／适用条件及来源结果计算缺口，不机械追加实验设计和经验对照；未要求字段保持未知而非认定不适用，事实及核心结论的必要条件继续核验

#### Scenario: A follow-up attempts to reduce its required reading fields
- **WHEN** 补读候选将已有来源定位合同的必需字段缩小，或省略用户明确要求的字段
- **THEN** 系统保留原要求和冲突，允许有原文依据的需求扩大，不借换profile使未完成项变成完成；报告和读者审核仍按冻结政策及实际核心结论判断

### Requirement: Reader review remains current and bounded

系统 SHALL 对初稿完成当前整稿的读者审核，修订后根据实际影响使相关维度失效并复核；核心结论或结构变化触发相应全局复核。有效未变维度可以组合复用，最终结果须绑定当前稿。争议重复组最多进行一次有界实质影响复核，不以不断更换合同取得新尝试。

#### Scenario: A local deletion preserves all claims and coverage
- **WHEN** 删除仅去除无新用途的复述，必要主张、前提和其他章节职责均未变化
- **THEN** 系统复核受影响阅读范围并组合有效旧维度，不强制重做全部事实审核，也不原样沿用旧整稿通过标记

#### Scenario: A reader edit removes a required answer
- **WHEN** 编辑移除了唯一回答必答问题的内容
- **THEN** 覆盖及依赖的读者维度失效，问题补足前不批准合格交付

### Requirement: Visual delivery covers the declared research needs

系统 SHALL 按用户要求、所选模块和当前判断明确适用的模块／机制图、事件时间轴及数据图需求，分别记录覆盖与事实审核状态。仅已有图通过、图数量或文字表格 MUST NOT 证明所需可视化完成；无适用证据或数据时保留具体缺口，不静默省略或编造。

#### Scenario: Required visuals were never generated
- **WHEN** 当前稿的已生成图均通过审核，但用户所需机制图或时间轴尚未生成
- **THEN** 系统保留可视化覆盖缺口，不将该稿标记为满足全部图文需求

#### Scenario: A publication count is offered as an event timeline
- **WHEN** 演进任务需要有来源日期的成果／机制事件，但当前只生成年度发表数量折线
- **THEN** 系统不以该折线抵充事件时间轴，按原证据补足或说明日期／事件缺口，时间先后不标成已证实继承

### Requirement: Source figures are complete identifiable regions of the actual source

系统 SHALL 在要求论文原图时交付绑定实际原件、版本、页码和区域的目标架构／实验图块，并保留必要图号、图注、坐标、图例及子图关系。整页预览 SHALL 作为追溯材料与独立图块分记，定位不确定或仅取得整页时不得宣称图块已提取。

#### Scenario: Only a full paper page is available
- **WHEN** 实际资产只有包含目标图的整页缩略图
- **THEN** 系统保留原页入口并将独立图块记为未完成，不将整页计为满足目标架构／实验图要求

### Requirement: Requested visuals survive each actual report export

系统 SHALL 让界面及请求的导出格式消费同版有效图资产，明确记录未装配、渲染失败和缺失。图事实支持与最终图块、图说、标签和阅读效果分开判断；所需图被导出筛选丢弃时不能沿用网页已有图的结果宣称交付完整。

#### Scenario: PDF export omits a required chart
- **WHEN** 已有有效数据图或事件时间轴未被当前PDF装配
- **THEN** 系统将该格式记为可视化未完成，复用有效正文和图资产仅修复对应装配，不自动重写整稿或重采论文
