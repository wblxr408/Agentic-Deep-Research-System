# Spec Delta

## Purpose

在保持必要研究覆盖和当前质量判断的前提下，减少重复模型输入、无效审核与恢复空转。统一记录主决策、分析、写作、审核及格式修复的真实消费和未知项，使成本改进能够由当前任务的实际请求及可观察结果解释。

## ADDED Requirements

### Requirement: All model operations share the original root ledger

系统 SHALL 将主决策、分析、写作、事实／读者／图文审核、格式修复及授权备用请求纳入同一根准入和累计限额，保留调用身份、用途、实际 usage、未知消费及在途预占。预留调整和恢复不能增加总额、重复计量聚合行或把未知价格显示为免费。

#### Scenario: A controller call consumes the remaining allowance
- **WHEN** 主 Agent 决策请求已使用额度，下一写作请求不足以准入
- **THEN** 系统保留本次消费和研究成果，拒绝超额派发，不将控制器用量排除后继续写作

#### Scenario: An interrupted request has unknown usage
- **WHEN** 请求已尝试派发但未收到可核的供应商用量
- **THEN** 系统按既有规则保留未知消费并与已知用量分列，不退款、不伪造零消费或盲目重发

### Requirement: Context is bounded by the active research operation

系统 SHALL 为当前操作提供必要问题、结论依赖、Skill 和原文位置，记录未选材料及容量缺口，不默认附带完整历史、前章全文或无关技术卡。同批审核可共享重叠原文，但每条主张只能使用其实际绑定的来源范围；输入和输出空间均受真实请求准入。

#### Scenario: Multiple claims cite overlapping passages
- **WHEN** 当前批次多条主张的合法来源片段重叠
- **THEN** 系统可只传一次共享文字，保留每条可用范围，不能使用仅属于另一条主张的证据取得支持

#### Scenario: A necessary source window does not fit
- **WHEN** 当前消息无法容纳支撑结论所需的完整条件
- **THEN** 系统分解操作或保留具体缺口，不静默截掉条件或用生成概要冒充原文

### Requirement: Valid review reuse follows complete dependencies

系统 SHALL 仅在当前主体和任务、主张含义、必要上下文、类型和前提、来源版本／位置、访问许可、统计口径、政策及审核模型／合同均匹配时复用判定，并记录原依据和新位置。文本相似、稳定 ID 或旧正判不能单独授权复用；无法确定影响范围时须扩大到适当局部或全局审阅。

#### Scenario: Formatting changes preserve all factual dependencies
- **WHEN** 当前修改只改变位置或排版，主张及全部必要依赖不变
- **THEN** 事实判定可复用并更新定位，未产生新事实判断请求，当前交付仍依据完整有效的审核组合

#### Scenario: A source version or a decisive premise changes
- **WHEN** 主张文字不变但原文、权限、必要条件或审核合同发生变化
- **THEN** 相关判定和依赖结论失效，系统审核受影响范围，不以文字相同直接通过

### Requirement: Remaining work determines reservations

系统 SHALL 按未完成问题、未完成内容单元、失效审核项及剩余交付工作估算预留，明确估算不是质量批准。有效已完成工作不能被恢复重复预测为整套待办，新内容和失效依赖必须恢复相应需求；预留总量与当前请求始终受原根限额约束。

#### Scenario: Facts and reading are complete before media delivery
- **WHEN** 同一有效输入下事实和读者审核已完成，仅图文及导出待办
- **THEN** 系统预测并保留剩余图文／交付需求，不重新为全部分析、写作及已完成审核占用份额

### Requirement: Iteration opportunities persist at root scope

系统 SHALL 沿原根持久化实际发生的重规划、共享内容修订、格式再生成和无进展机会，复用已有上限并仅补未覆盖差量。恢复或合同重审不能重置机会；预算消耗、文字变化或模型自评分不等于进展。新控制器未采用时不新增其决策次数或武断使用24／2等草案数值；达到生效上限须停止自动循环并保留成果。

#### Scenario: The same reading gap returns after repeated edits
- **WHEN** 连续轮次没有补足关键问题，或同一缺口在不同审核阶段往返达到原根上限
- **THEN** 系统停止自动修订并说明未决项，不以切换阶段、恢复执行或更改合同重新领取机会

#### Scenario: A saved response has a lossless format projection
- **WHEN** 完整响应只需已定义且无歧义的字段投影即可满足消费者格式
- **THEN** 系统复用原付费响应并记录投影，不改语义判定或重新调用模型；真正截断或含义不明仍保留失败并遵守原重试机会

### Requirement: Cost reporting explains improvement without hiding quality loss

系统 SHALL 按操作用途展示原生输入／输出、未知消费、在途预占、请求数、审核复用和缺口，并区分应用复用与供应商提示缓存。沿原收据保存供应商原始usage，在支持的实际端点与模型下归一缓存读、按有效期区分的写及普通输入，兼容供应商包含或单列缓存输入的差异，不漏计、不重复相加。费用区分普通输入、缓存读写、输出及适用存储，缺失分项不推断为零；缓存折扣不能擅自减少原根逻辑Token额度。成本改进应与相同当前任务内容及质量目标一起解释，不能用历史故障累计、配置报价或字符估算冒充实测节省。

#### Scenario: An optimization reduces tokens by omitting a required answer
- **WHEN** 请求用量下降但内容计划中的必答问题或必要证据丢失
- **THEN** 系统仍记录质量缺口，不将其报告为满足目标的成本改善

#### Scenario: Provider prices are incomplete
- **WHEN** 部分请求缺少可核的价格或缓存计费信息
- **THEN** 显示已知用量与已知费用小计，完整费用保持未知，不推断免费、缓存折扣或确定的节省金额

#### Scenario: A provider serves a cached prefix and generates a new response
- **WHEN** 实际支持的端点返回缓存读取分项及本次新增输出
- **THEN** 系统保留本次请求和输出消费，按该供应商语义计算不重叠的输入类别；记录供应商命中，不将其冒充应用结果复用、零Token调用或根额度退款

#### Scenario: A compatible endpoint does not declare cache support
- **WHEN** 当前供应方仅提供兼容协议，未确认支持所选模型的缓存参数及usage
- **THEN** 沿普通请求与已有应用结果复用继续研究，不发送不支持的专有参数、不默默更换供应方、不虚构缓存折扣

### Requirement: Corpus growth preserves valid completed work and attributable cost

系统 SHALL 沿原根按未完成论文／字段、主题、内容和审核项预测剩余工作，逐批保存有效产物，失败只作用于对应操作；新增或变更论文按依赖传播失效。首次语料处理、有效复用、开发修复及异常返工分别计量，不以缓存折扣推断已减少逻辑用量，不重置原限额。

#### Scenario: One paper is added to a retained corpus
- **WHEN** 同一获准任务内原99篇的输入、版本、权限和字段合同仍有效，又增加一篇相关论文
- **THEN** 系统处理新增材料及受影响主题／结论／图与审核，保留其余有效产物，不默认重读99篇或重写全部章节；原总预算不足时保留明确缺口

#### Scenario: A large corpus is interrupted after partial completion
- **WHEN** 100篇任务中部分论文与主题已经完成，当前一项派发结果未知
- **THEN** 系统保留已完成项与原消费，对未知项先对账，并按实际剩余状态继续或结束，不整包重放或将未知消费记零
