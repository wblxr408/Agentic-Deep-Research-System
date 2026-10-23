# Spec Delta

## Purpose

为企业、高校和科研实验室提供可以本地重复执行的有界研究任务，使 SDK 真正驱动模型和采集工具交互，并交付研究范围、执行轨迹、来源、报告及未解决问题作为可核查结果。

## ADDED Requirements

### Requirement: Run bounded organization research
系统 SHALL 接受一个或多个带类型的组织、研究主题和时间范围，由 SDK 实际执行模型与搜索／读取工具交互，交付各对象的研究发展分析及范围限制。模型自述不得替代真实工具轨迹。

#### Scenario: Research university and company
- **WHEN** 用户指定高校和企业及主题并执行命令
- **THEN** 产物保存原始范围、计划、工具结果、证据和报告，并区分事实、推断和缺口

SDK综合 SHALL 返回逐条研究事实及显式来源编号，由程序生成报告；每项代表性工作须包含发表归属、研究问题、技术方法与成果条件，另含后续验证建议。缺必要组织或维度、引用无效、或任一研究事实终审未通过时不得completed。范围说明依据请求及采集记录生成；后续建议与取证缺口不计作已验证事实，并明确显示核验覆盖范围。

模型自行提出的missing_requirements SHALL 作为建议保留，不能扩张原请求的验收范围；coverage_missing由请求组织、必需事实维度、后续问题和引用范围的检查生成。

### Requirement: Constrain execution and isolate state
系统 SHALL 将每次运行的状态隔离，只开放显式登记的公开只读工具，限制总时长、工具次数、读取字节和模型步数；超限或取消时停止新调用并清理临时资源。禁止公开资料工具读取内部地址或本地文件。

#### Scenario: Exhausted collection budget
- **WHEN** 任务耗尽工具或时间预算
- **THEN** 后续工具不发起外部读取，运行输出明确的受限或失败状态而非宣称完成

### Requirement: Reproduce and identify provider evidence
系统 SHALL 提供固定 SDK 版本和复现命令，记录模型、提供方、实际工具调用和运行结果；Cortensor 的配置能力、实际访问及真实运行证据分开陈述。

#### Scenario: Cortensor access unavailable
- **WHEN** 未提供 Cortensor 访问配置
- **THEN** 仍可用已配置模型执行流程，但不声称完成 Cortensor 网络推理

### Requirement: Read bounded paper text and reuse retained sources
系统 SHALL 从合规HTML提供范围内论文链接，并在有界子进程中提取公开PDF文字；保存页码、正文偏移、页数和截断状态。解析超时、损坏、加密或无可提取文字 SHALL 显式失败，不伪造原文。同次运行的重复focus读取 SHALL 复用已保留原文、保持证据标识稳定，并继续消耗工具次数。

一次页面读取 MAY 同时提取其首个范围内非slides论文PDF，保留分别的引用标识，最多额外读取一份文档并计入原有总预算。SDK工具采集后 SHALL 从实际保留来源执行无工具综合，草稿本身不能作为新证据；最终核验必须对应综合后的报告，采集与综合统计分开保存。

#### Scenario: Verify experiment conditions late in a PDF
- **WHEN** 相关数字和限制位于论文后部且仍在公布的保留预算内
- **THEN** 原文工具能返回对应内容及偏移，来源元数据能定位PDF页码，同URL再次读取不同focus不重新下载

### Requirement: Select and enforce research source scope
系统 SHALL 接受出版商／会议论文集、DBLP、arXiv、Google Scholar、企业／高校／研究机构官网来源组的单选或多选，拒绝空选择及无域名的官网选择。出版商清单允许显式配置，保存清单版本和实际域名快照，不把起始清单宣称为全部学科的完整覆盖。搜索结果、种子、正文读取及每跳重定向 SHALL 在可信代码执行范围限制；Google Scholar仅用于发现，DBLP正文标为元数据用途，arXiv标为预印本，站点准入不等于结论真实或论文已通过同行评审。

#### Scenario: Select official and scholarly sources together
- **WHEN** 用户选择论文集和官网并指定机构域名
- **THEN** 搜索仅交付范围内线索，原文及合法范围内跳转可读取，结果保存实际生效的范围

#### Scenario: Allowed source redirects outside selected scope
- **WHEN** 范围内页面跳转到未选域名
- **THEN** 系统在连接该跳转目标前拒绝，不为该页面分配引用

#### Scenario: Use Scholar to discover papers
- **WHEN** 用户选择Google Scholar
- **THEN** 仅返回发现线索；读取Scholar正文被拒绝，论文正文需要所在来源组也已被选中
