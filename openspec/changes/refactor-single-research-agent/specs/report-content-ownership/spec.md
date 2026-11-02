# Spec Delta

## Purpose

在研究报告生成前明确问题、结论、证据和章节的内容归属，使主文推进判断、附录保留完整技术说明。通过稳定内容单元支持可追溯的局部编辑、覆盖判断和受影响审核，减少同一成果在各章节被反复介绍与整稿返工。

## ADDED Requirements

### Requirement: Content ownership precedes chapter generation

系统 SHALL 在章节生成前保存内容计划，为必答问题和关键结论指定完整论证所属章节、前提及证据、主附录去向和其他章节允许的简述用途。所有已采纳成果须有与问题相关的去向或排除理由；章节名称和段落数量不能代替内容职责。

#### Scenario: Several chapters use the same representative work
- **WHEN** 全景、演进及行动章都需要援引同一成果
- **THEN** 系统分配不同的章节判断，保留一处完整机制解释，并让其他章节按各自问题使用必要简述及来源

#### Scenario: A mandatory question has no owner
- **WHEN** 内容计划未分配某个必答问题，或采纳成果没有明确去向
- **THEN** 系统保留具体计划缺口，不能仅凭章节齐全进入合格交付

### Requirement: Chapter inputs contain assigned substance and necessary dependencies

系统 SHALL 向写作提供当前章的问题、归属结论、必要依赖和实际来源，保留原引用及条件，记录未装入的必要材料。其他章节全文和无关技术卡不应默认累计进入每一章；材料不足须拆分或补取，不能以概要替代必要原文或生成缺失事实。

#### Scenario: A later chapter needs one earlier conclusion
- **WHEN** 当前章只依赖前章的一条判断及其条件
- **THEN** 写作取得该结论和必要原文／依赖，既不默认收到此前全部正文，也不丢失影响含义的条件

### Requirement: Reuse of a conclusion preserves its reader function

系统 SHALL 区分完整论证、摘要、导航、就地条件和行动前提等读者功能。同一命题可按必要用途简述，但不同段落 ID 不构成语义去重证明。技术附录应保留每项代表工作的整合说明，移动重复内容不能单独作为去重完成。

#### Scenario: A summary previews a supported main conclusion
- **WHEN** 摘要简述主文将展开的判断且没有添加新事实
- **THEN** 系统允许该用途，保留对应结论及引用关系，不强制删除预告

#### Scenario: Duplicate prose is moved to the appendix
- **WHEN** 编辑只将同用途重复段落搬到附录，重复命题仍完整存在
- **THEN** 系统继续按实质影响判断冗余，不以位置变化或 ID 唯一性声称去重成功

### Requirement: Edits target versioned content units

系统 SHALL 允许对稳定内容单元进行移动、删句或定向替换，保存原稿、预期版本、实际范围、理由及修改记录。默认保留引用；确需新来源时须经过授权取证、绑定及审核。版本冲突、范围不唯一或不可定位的补丁不得静默应用。

#### Scenario: A paragraph mixes a unique mechanism and a redundant caveat
- **WHEN** 一段包含必须保留的机制说明及已有充分表达的重复范围句
- **THEN** 编辑可仅删除对应重复句并保留机制、必要条件和来源，不必整段删除、搬移或重写整稿

#### Scenario: The target changed before patch submission
- **WHEN** 另一合法操作已修改目标内容版本
- **THEN** 系统拒绝旧补丁写入，保留冲突信息和已付费候选，不覆盖新内容

### Requirement: Changed premises invalidate dependent conclusions

系统 SHALL 保存主张、条件、推断和出现位置的依赖关系。修改实体、数字、否定、时间、引用、指代或必要条件时，使相应事实和依赖结论的审核失效；单纯位置变化不应自动更换主张身份。覆盖及当前读者任务须随修改更新。

#### Scenario: The workload condition changes
- **WHEN** 修改了用于支持主要性能比较的负载条件
- **THEN** 系统重新核验该条件和依赖的性能／行动判断，不能仅凭比较句文字未变复用旧正判

#### Scenario: An unchanged claim moves to its owning chapter
- **WHEN** 主张文字、必要上下文、来源及全部审核依赖未变化，仅章节位置改变
- **THEN** 系统保留主张身份及有效事实判定，更新出现位置并检查受影响阅读职责

### Requirement: Corpus coverage preserves the requested reading depth

系统 SHALL 保存所需论文及其阅读层级、来源版本、全文可用性、字段完成状态、报告去向和缺口，区分全语料覆盖与全部精读。用户明确要求逐篇或全部精读时，系统 MUST NOT 静默以默认代表集、检索top-k或篇目清单代替；容量不足应分批或报告未完成范围。

#### Scenario: Every paper in a hundred-paper corpus requires close reading
- **WHEN** 用户要求指定100篇全部精读
- **THEN** 系统逐篇记录约定字段及证据覆盖，未完成论文继续保留缺口，不以已完成20篇代表分析宣称100篇已完成

#### Scenario: A selected paper has no accessible full text
- **WHEN** 其中一篇只有摘要，其他论文已完成全文处理
- **THEN** 系统明确该篇实际层级和缺口，保留其他有效产物，不把摘要标为全文精读或重做其余论文

### Requirement: Assembly preserves complete bounded writing batches

系统 SHALL 分开单次写作响应与整份报告的资源边界。版本化的新任务可汇总多批已写段落，归属选择及后续修订须使用同一装配合同，不得为单批段落数静默删减完整批次或独有技术内容。整份产物仍有明确资源上限；超出时保留未完成状态及付费候选，不能以裁剪取得通过。旧任务保持其冻结合同，最终来源／读者／图文审核仍须完成。

#### Scenario: A technical appendix spans more than one writing packet
- **WHEN** 同一模块的完整已写附录合计超过20段，且仍在新任务装配资源上限内
- **THEN** 汇总、格式投影、编辑选择及修订读取完整段落；编辑可基于知识归属去重，不将单批20段误作完整附录的目标或删减依据

#### Scenario: An assembled artifact exceeds its resource boundary
- **WHEN** 完整汇总超出冻结版本支持的装配资源边界或当前下游上下文容量
- **THEN** 保留真实容量缺口和已付费候选，不截断尾部、减少全部阅读成员或据此宣称百篇已交付

### Requirement: Synthesis uses bounded topic evidence and retains original provenance

系统 SHALL 复用逐篇证据产物按当前问题形成主题比较、条件及反例，再向章节提供必要输入和原文引用。综合摘要只能作为导航／候选，关键事实仍须回到来源；章节不默认接收全部论文全文或此前章节，必要条件和未覆盖范围不得静默丢失。

#### Scenario: A topic claim depends on a paper outside the current excerpt window
- **WHEN** 主题结论需要当前材料包未包含的实验条件或反例
- **THEN** 系统按来源位置补足必要窗口或保留缺口，不以主题摘要替代原文支持，也不默认重新装入全部100篇

### Requirement: Screening decisions and reading depth have traceable independent states

系统 SHALL 为论文保存问题／筛选政策版本、纳入／排除／待定理由及依据，并分列材料可用层级、实际阅读层级、所需字段及支持判定。会刊等级、关键词、原件可用或已索引不能直接证明相关性、全文精读或事实支持；历史规则按本次对象与问题适配。

#### Scenario: A paper has an abstract reading and an available PDF
- **WHEN** 原稿已经入库，但当前任务只完成摘要导读
- **THEN** 系统保留原稿可用与摘要已读两个状态，按当前必读字段调度必要补读，不将其直接标为全文精读完成

### Requirement: Evidence supplementation follows the missing fields into later delivery

系统 SHALL 沿当前论文／来源版本记录缺全文、缺条件、缺来源位置、缺数据或图块等具体缺口，并把必要补证结果接回分析、主题、内容及图需求依赖。已有材料和字段仅在失效时重做；补证不能以卡片摘要或不同论文代替所需原文。

#### Scenario: Two chapters require the same missing experiment condition
- **WHEN** 两个章节或图表依赖同一论文的同一未取得条件
- **THEN** 系统合并对应补证操作，取得有效原文后更新相关依赖，不为每章重新读取整篇，也不自动重写无关内容
