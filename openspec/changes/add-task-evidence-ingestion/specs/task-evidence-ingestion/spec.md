# Spec Delta

## Purpose

把用户主动接入的资料和任务中实际取得的网上证据记录为有归属、有版本、可追溯和可恢复的数据。接入方式及失败状态对用户可见，搜索线索与已读原文分别表达，默认只在当前任务范围内复用。

## ADDED Requirements

### Requirement: Explicit owner-scoped scheduled source synchronization
系统 SHALL 允许用户为本人选择的公开 HTTPS 来源建立手动或定时同步；源范围、目标分组与执行状态由用户控制，同步 SHALL 沿用当前资料版本、owner、网络限制和有界执行。创建订阅不得自动触发读取，周期只有启用后生效。

#### Scenario: A remote source has not changed
- **WHEN** 来源按其真实 ETag 或 Last-Modified 返回 304，或取得的正文与当前版本一致
- **THEN** 保留现有版本并记录未变，不产生重复资料或改写历史报告

#### Scenario: A pending synchronization is revoked or replaced
- **WHEN** 用户暂停、删除或修改订阅，或原账号／资料权限在写入前失效
- **THEN** 已派发读取的迟到结果不得写入资料，运行状态如实保留

#### Scenario: A source changes
- **WHEN** 有界读取取得新的可解析内容且目标版本仍有效
- **THEN** 以同一来源家族追加新版本，保留原文、来源时间、原版本和引用，并记录真实取得结果

### Requirement: Explicit source discovery and batch intake
系统 SHALL 复用手动登记、启用渠道、种子与检索发现，并允许用户显式选择文件集合或目录后有界批量上传；逐项显示采纳、复用、失败和未处理状态。目录选择不得授予服务端任意本地目录读取权限。

#### Scenario: Selected directory contains unsupported files
- **WHEN** 用户选择含支持与不支持类型的目录
- **THEN** 系统列出逐项原因，上传仅在显式动作后发生，不静默忽略不支持项或遍历其他目录

### Requirement: Owner and group scoped idempotent intake
系统 SHALL 将上传幂等绑定实际 owner、目标分组及内容版本。同一分组并发重复上传不能产生多个相同来源记录，另一分组的同一文件不能误报该分组已接入。

#### Scenario: Repeat after partial batch failure
- **WHEN** 用户重试失败批次且部分文件已经提交
- **THEN** 已提交同组文件复用来源记录，失败项可单独重试，保留状态且不会重复嵌入已成功文件

#### Scenario: Destination or intake configuration changes after partial completion
- **WHEN** 当前页面批次已派发过请求，继续或失败重试时的分组、OCR、分块、特征／索引或保存范围／有效期与首次提交不同
- **THEN** 系统 SHALL 在发送下一项前拒绝沿用旧批次状态，允许恢复原设置或显式重列整批
- **AND** 重列整批只重置支持文件的页面状态，保留旧来源且不自动发送请求，不能把旧目标成功项当作新目标已接入

#### Scenario: Repeated start before the button rerenders
- **WHEN** 用户连续点击开始／继续导致React尚未更新按钮状态
- **THEN** 同步派发闸口 SHALL 只允许当前批次的一条提交循环，服务端仍执行真实owner与完整配置的幂等写入

### Requirement: Immutable task evidence versions
系统 SHALL 在任务归属内保存证据来源、获取时间、内容版本、原始证据标识及保留文字；重复事件不增加版本，变化原文建立新版本，不覆盖被引用版本。保留的归一文本不能冒称原始网络字节。

#### Scenario: Same source changes during research
- **WHEN** 同一来源被重新读取且保留正文变化
- **THEN** 账本保存新旧版本及各自证据事件，原引用仍可定位旧内容

### Requirement: Discovery and retained content remain distinct
系统 SHALL 分开记录仅搜索发现、取得部分正文、全文和内部资料片段的状态，保留来源类型及解析元数据；缺少获取时间或正文时说明未知，不把证据数当论文全集。

#### Scenario: Search then read source
- **WHEN** 搜索摘要之后取得同 URL 原文
- **THEN** 两种取得事件和内容状态分别保存，后一次读取不将原摘要追认为全文

### Requirement: Bounded recovery with durable outcomes
系统 SHALL 复用现有预算、工具重试和执行版本隔离，展示待重试、终止待人工处理、等待审批和后续已恢复的接入结果。恢复不自行放宽来源、权限或预算，旧执行者不能覆盖新执行状态。

#### Scenario: Late worker persistence
- **WHEN** 恢复已产生新执行标识而旧执行者提交快照
- **THEN** 系统拒绝旧提交，当前账本与恢复状态不被覆盖

### Requirement: Read only owner scoped ledger
系统 SHALL 仅向当前授权主体展示其任务账本；历史无账本任务可显式投影并标明非持久。读取不发生网络、模型调用、同步或知识库索引。

#### Scenario: Another owner requests ledger
- **WHEN** 非拥有者查询或下载该研究的接入账本
- **THEN** 系统返回不可访问，不泄露源文字或版本

### Requirement: Declare acquisition and coverage choices
系统 SHALL 说明实际采用的请求驱动／事件式接入、全量或时间戳增量，以及未启用定时、CDC、Webhook的原因和重评条件；组织研究样本继续保留已有范围、流转与全文缺口。

#### Scenario: No scheduled subscription
- **WHEN** 用户仅发起普通研究或批量上传
- **THEN** 系统不创建周期任务、消息订阅或跨任务复用，返回实际执行与覆盖范围
