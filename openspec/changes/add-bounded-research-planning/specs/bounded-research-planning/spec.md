# Spec Delta

## Purpose
使用户能够理解研究步骤、依赖和调整原因，并使执行器在同一任务状态、权限、预算和恢复边界内完成有界取证；拒绝不可执行依赖、旧结果及无收益循环，保留真实缺口。

## ADDED Requirements

### Requirement: Bounded external acquisition and task reuse
系统 SHALL 将普通HTTP跳转、页面资源和可选渲染纳入原调用份额及期限；任务浏览入口 MUST NOT 运行独立未计量页面分析。新根 SHALL 冻结读取模式、任务缓存及实时抓取年龄，URL请求身份不得丢弃文档版本或query语义。

#### Scenario: Static source followed by bounded rendering
- **WHEN** auto模式取得空页面或有界JavaScript占位，且未限定来源／种子模式并仍有原份额
- **THEN** 最多追加一次受控浏览，合并原HTTP与浏览实际计数；预算或渲染不足保留缺口，不重置预算或虚构全文

#### Scenario: Reuse a retained page
- **WHEN** 当前任务存在相同请求／最终URL的受控取得文字
- **THEN** 重新检查来源范围及获取年龄、服务器缓存限制，并优先最新合法版本；复用不改写原文、evidence_id或旧时间

#### Scenario: Realtime evidence expired
- **WHEN** 实时任务的新综合发现来源超出抓取年龄或当前来源范围
- **THEN** 保留原历史资料但不再交给当前综合，记录缺口并使其依赖的旧综合失效

### Requirement: Explicit retained source archival
系统 SHALL 允许本人明确将取得的受控公开原文版本保存到本人资料，保存原任务／来源／版本关联，默认direct且不自动编码或进入检索。归档 MUST NOT 把线索、生成报告或未确认公开传输的内容冒充公开原文。

#### Scenario: Archive request replay
- **WHEN** 同owner/request_id与相同版本／参数重放
- **THEN** 同一事务操作返回原归档结果，改变参数冲突，不重新读取网络、调用模型或改写原研究

### Requirement: Bounded query variants
系统 SHALL 冻结用户明确的术语别名和查询变体上限，保留原始查询，按当前对象和时间补全；显式平台命令及URL MUST NOT 被普通词汇改写。每个变体 SHALL 独立经过既有来源范围准入，别名不能扩大工具、渠道或资料许可。

#### Scenario: Multiple variants under one root allowance
- **WHEN** 当前步骤需要多个词面查询或多个已选渠道
- **THEN** 分配的实际调用和超时总量 SHALL 不超过原根剩余份额；保存变体、渠道选择、裁剪原因与实际尝试，未执行不得声称覆盖

#### Scenario: Unavailable representation channel
- **WHEN** 未配置学习稀疏模型、行为数据或稠密许可
- **THEN** 标明未启用原因，保留独立词汇路径，不将普通关键词冒充向量或行为召回

### Requirement: Bounded stage model routing
系统 SHALL 对新根任务冻结已配置服务、候选策略、资料类别和阶段要求。确定性工作 MUST 保持直接执行；需要模型时 SHALL 先过滤阶段、能力、配置质量档位、资料许可及上下文容量，再比较有来源的配置报价。未知报价 MUST NOT 作为免费价格，配置档位 MUST NOT 冒称实际任务质量认证。

#### Scenario: No eligible candidate
- **WHEN** 启用路由但没有候选同时满足当前阶段与资料许可
- **THEN** 在派发请求和预算预占前停止该模型阶段，保留原因，不选择未配置服务、不跳过研究核对

#### Scenario: Changed live configuration
- **WHEN** 服务端端点、主备身份或路由策略与原根快照不再匹配
- **THEN** 下一次模型请求 SHALL 在派发前拒绝；恢复不得静默切换端点或重置额度

#### Scenario: Authorized service failure fallback
- **WHEN** 主服务尚未返回有效输出即失败，且备用独立密钥、资料许可及启用策略所需候选条件均满足
- **THEN** 备用请求复用原计量器并记录自己的provider/model及价格依据；已输出的流式报告不得拼接另一个模型的响应，服务故障回退不得冒称内容能力升级

### Requirement: Bounded capability escalation
系统 SHALL 以原根累计名额限制能力升级，先保存已付用量、失败输出和升级决定，再派发满足原许可的更高能力候选。证据缺失与实体身份歧义 MUST NOT 通过更换模型猜测事实；升级 MUST NOT 重置阶段尝试、预算或期限。

#### Scenario: Evidence conflict with an eligible higher tier
- **WHEN** 完整审核定位到有原文摘录的矛盾，且仍有原根名额、修订机会和预算
- **THEN** 先保存修订前稿与审核再选择更高配置档位的不同型号，按原固定引用修订并重新审核整稿

#### Scenario: Missing evidence or exhausted root allowance
- **WHEN** 原文未取得、身份歧义未澄清、根额度成为限制或没有合格更高候选
- **THEN** 记录补证／澄清或拒绝原因，不凭置信度添加调用，不创建新根额度

### Requirement: Validated visible plans
系统 SHALL 对固定、动态和混合计划使用一致的有界结构/权限校验，拒绝重复ID、未知依赖和环；条件只使用明确支持的结果状态，MUST NOT执行模型表达式。用户 SHALL 看到计划版本、步骤、依赖、来源用途、执行/调整/受阻原因。

#### Scenario: Revise configuration after a stopped run
- **WHEN** 用户编辑本人原请求并要求按修改配置研究
- **THEN** 先重新预览并核对当前本人可用配置，创建独立任务；旧根状态和已用预算保留，旧审批／预览不继承，不能冒称原任务已恢复完成
#### Scenario: Invalid model plan
- **WHEN** 模型给出循环或缺失节点的依赖
- **THEN** 未校验计划不分发；保留具体拒绝和有界修正/受限回退说明，不宣称已覆盖原目标。
#### Scenario: Conditional and parallel work
- **WHEN** 多个步骤满足依赖和各自权限/预算且允许并行
- **THEN** 只按并发上限分发；依赖未完成或条件不成立的步骤等待或明确跳过，不提前执行。

### Requirement: Bound handoff and root ownership
系统 SHALL 给子任务传明确目标、所需证据引用、操作/计划版本、期限和预算份额；返回结果必须匹配当前执行及节点请求，重复结果幂等、旧结果不得进入综合。一个运行 MUST 保持一个状态和预算所有者，工具及SDK适配器不能创建另一套主调度。

#### Scenario: Tool consumes the frozen query configuration
- **WHEN** 根分发搜索、内部资料或浏览工具
- **THEN** 只传该阶段必需的冻结变体／对象时间、过滤／召回模式或时效字段；投影身份参与操作绑定并在执行前及接纳时核对，不能因最小化上下文丢弃实际约束
#### Scenario: Late or duplicate result
- **WHEN** 同一子任务重复返回或旧计划结果迟到
- **THEN** 已接受结果不重复结算，旧版本被标为过期并拒绝，其他合法步骤可继续。

### Requirement: Evidence driven bounded iteration
系统 SHALL 仅根据具体证据缺口/冲突和可用预算进行有界重规划，保存已有证据和失败记忆；证据满足当前问题、预算耗尽、持续无新增信息、需要人工授权或达到轮次上限时明确结束或暂停。模型置信度 MUST NOT 单独触发新的自主循环。
#### Scenario: Repeated empty search
- **WHEN** 有限修正轮次没有产生新证据版本或可执行的新方向
- **THEN** 结束重复取证并报告未解决问题及原因，不将空结果或模型自评分变成充分性证明。
### Requirement: Question evidence context preserves original anchors
The system SHALL organize literal retained excerpts by the current question and explicit work references while retaining original citation numbers and the same retained-source/version identity used by the task ledger. Relevance, source coverage and semantic support SHALL remain distinct.

#### Scenario: Context omits sources or experimental conditions
- **WHEN** the current allowance cannot retain a source or requested experimental window
- **THEN** the stage records the selected excerpts, omitted IDs and selection gaps
- **AND** lexical gaps alone do not automatically authorize additional external collection or a truth verdict

#### Scenario: A stopped analysis uses a different selector contract
- **WHEN** a resume request no longer matches the retained context-selection input binding
- **THEN** continuation is rejected without changing the previous evidence, budget or deadline
- **AND** historical reading remains available under the original access policy

#### Scenario: The reader inspects research evidence
- **WHEN** an owner opens the report research record
- **THEN** question-level selected excerpts, retained versions and actual positions are available
- **AND** engineering diagnostics are not injected as report-body writing material

### Requirement: Data egress and reader disclosure remain distinct
系统 SHALL 冻结资料声明、可外传模型类别和可公开查询，并按实际源提高限制；MCP工具的出站类别 MUST 同时满足注册表和逐工具声明。展示脱敏 MUST NOT 修改原始授权参数、审批绑定或证据位置。

#### Scenario: OAuth credentials in a URL fragment
- **WHEN** 来源或任务文字的URL在fragment或SPA hash路由参数中携带访问／身份／会话token
- **THEN** 系统 SHALL 沿与查询参数相同的访问凭据分级、搜索／代理拒绝及模型／展示脱敏规则处理，不因HTTP不发送fragment而视为公开文本
- **AND** 普通论文页码及章节锚点不被当作访问凭据，本人原始输入仍由原权限入口保留

#### Scenario: A report exposes access credentials
- **WHEN** 生成正文在完整输出检查中包含已识别访问凭据或需要脱敏的访问URL
- **THEN** 正文不作为流式完成报告发布，任务保留脱敏草稿并要求重新审核
- **AND** 新历史、SSE、日志、引用及导出使用披露投影，不能沿用原稿支持结论作为脱敏新稿的审核结论

#### Scenario: The owner reuses a protected original source
- **WHEN** 已鉴权本人打开原文或编辑原研究配置
- **THEN** 沿原权限保留真实材料身份与访问URL，复制新任务重新预览当前许可
- **AND** 报告JSON仅使用独立export_view，排除原材料和重开参数，不宣称原始存储已全面加密

### Requirement: Quality observations and human judgments retain scope
系统 SHALL 使用实际候选返回顺序和明确人工标注计算有界池内排名指标；没有标签、标准答案或有效分母时MUST保留未知。反馈 SHALL 绑定本人当前报告／证据／计划／执行及实际目标，以请求身份幂等保存，不自动改变事实库、索引或模型配置。

#### Scenario: Only some candidates are judged
- **WHEN** 用户没有标完整个返回候选池或池中没有已知正例
- **THEN** 不能生成该池Recall／MRR／NDCG的完整质量结论，更不能声称全库召回
- **AND** 已标数量、可定义的局部指标及真实通道成员仍可见

#### Scenario: A feedback request is retried or stale
- **WHEN** 相同请求身份重放、复用为不同参数或当前报告快照已经改变
- **THEN** 相同参数只形成一个反馈事件，异参或旧快照拒绝新增
- **AND** 纠错与采纳不覆盖原报告或自动授权新研究

### Requirement: Runtime receipts preserve unknown monetary cost
系统 SHALL 沿原根预占／结算记录真实模型请求身份及耗时，将模型、工具和本地资源观察分开。未定价项目 MUST 保持未知，不能把已有数值计数冒充完整账单，也不能把绘图模型费用再计入本地渲染项。

#### Scenario: Local resources and unpriced requests are present
- **WHEN** 本机Embedding／重排／绘图产生耗时记录，或模型／工具缺少可靠价格与用量
- **THEN** 已知参考费用只作为小计，完整金额保持未知
- **AND** 性能分位数带实际样本数量及缺失量，不宣称总体SLA或虚构节省比例

### Requirement: Cancellation stops new work and preserves dispatched usage
系统 SHALL 由本人携带当前execution_id及幂等request_id取消未完成任务，保留canceled独立终态。模型和工具准入 SHALL 与取消复用原任务事务锁，计入当前已用及在途份额；取消后MUST NOT恢复额度、旧审批或接受迟到正文。

#### Scenario: Cancel races a model or tool dispatch
- **WHEN** 本人取消与供应商／工具准入并发
- **THEN** 事务确定是否已准入，未准入不派发，已准入保持实际或未知计量及原期限
- **AND** 迟到结算只合并原归属收据，不把当前取消／新执行改成完成或失败，不回灌证据

#### Scenario: A stale page or a retried command attempts cancellation
- **WHEN** execution_id已变化，或同request_id重放／异参复用
- **THEN** 旧执行命令和异参拒绝，相同命令只产生一个业务结果
- **AND** 用户可查看已取消状态、未结算收据及原配置，复制新任务重新预览当前许可

#### Scenario: Several readers reconnect across an execution change
- **WHEN** 多个页面订阅同任务，或携带保留窗口外的事件ID重连
- **THEN** 各订阅独立有界接收，发事件前复核原凭据与执行；旧执行不能关闭新连接
- **AND** 保留窗口缺口明确回到持久化结果，不能把流式事件当永久完整研究成果

