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
