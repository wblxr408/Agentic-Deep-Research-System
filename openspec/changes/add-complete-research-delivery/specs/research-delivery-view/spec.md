# Spec Delta

## Purpose

为不同对象和学科的研究提供同一任务结果驱动的交付视图，将正文、计算统计、来源引用、审核缺口和后续行动连接起来，并通过声明式页面支持预设、自定义和可移植下载，避免呈现层重新编造研究数据。

## ADDED Requirements

### Requirement: Verified source locations survive unaccepted technical summaries
系统 SHALL 将本根已保存技术提案中能在当前已授权原文重新定位的引文作为检索线索，即使其字段摘要因数值／覆盖不足未采纳；不得因此提升该摘要。未知来源ID、发现片段、不支持字段、无可核原文的提案 MUST NOT 成为线索。系统 SHALL 保存阶段字段拒收原因，正文不展示内部状态。

#### Scenario: Literal hardware proof and broader unsupported field summary
- **WHEN** 字段摘要列出模型或负载等未被所列引用覆盖的细节，但其中硬件引文在本根当前原文中可核
- **THEN** 原字段接纳限制保留，引用在当前来源中重新定位、用实际字符范围供写作与审核查找，不复制提案摘要作事实；同规范源URL的其他当前保留版本也必须逐一原文定位

### Requirement: Research questions and source attribution retain their proper scope
v6审核 SHALL 区分拟议研究问题、原稿件的作者报告归因与实测或效果保证。数值、科学条件、真实资源及结果仍 MUST 从所引用原文得到支持；不得凭未见片段推断整个作品没有研究。系统 SHALL 保留所有原引用来源、双窗口／原预算和字符锚点约束，不复用旧v5正判。

#### Scenario: Asking about a proposed combination experiment
- **WHEN** 主张提出检验两种已描述方法能否结合及其代价的开放问题，没有宣告可行或保证收益
- **THEN** 审核按明确建议核其事实前提，不要求原文先声明这一新问题需要实验；宣称不存在组合研究或承诺成功仍分别需要依据

### Requirement: Literal complete analysis objects survive a single redundant final close
系统 SHALL 在标准JSON解码报Extra data且剩余文字恰为单个右括号、前缀全部文字解码为完整对象时，保留该原对象及原响应、记录内部格式恢复。系统 MUST 保持全部字段值与原组织字段／正文／proof校验，长度截断先停止；不能补内部结构、提取后续对象、接受尾随文字或以此重置尝试／预算。

#### Scenario: One redundant final object delimiter
- **WHEN** 正常结束的分析响应是完整对象后多单个右括号
- **THEN** 保留原完整数据和原始响应，继续原阶段校验，格式恢复独立于控制字符修复计数

#### Scenario: Interrupted or ambiguous malformed response
- **WHEN** 模型长度截断、内部JSON损坏、第二对象、尾随文字或多个多余符号
- **THEN** 原停止／拒绝行为生效，不通过删改数据或新增额度恢复

### Requirement: Publication identity preserves explicitly linked source versions
新corpus-v3声明 SHALL 在已取得PDF的主标题区明确链接到本根已授权且已取得的出版页、完整标题及出版日期边界一致且目标唯一时，将其作为同一发表的来源别名。系统 MUST 保存来源URL、各自证明和署名，不因来源增加重复累计发表；类型／日期冲突、仅相似题名、参考文献链接及歧义不能建立别名，研究家族仍需原关系证明。旧声明和历史结果 SHALL 保留原规则。

#### Scenario: Author copy and matching publication page
- **WHEN** 已取得作者PDF封面明确包含同标题同月份的已取得出版页URL
- **THEN** 来源记录分别保留，发表按同一output_id计一次；任一关联来源取得全文即可为该发表建立全文覆盖，引用与证据审核仍使用各自原文

#### Scenario: Unproved relationship or changed publication identity
- **WHEN** 没有明确主标题区链接，或目标未取得、题名／日期不一致、目标不唯一、类型冲突
- **THEN** 不合并该来源身份，不追抓URL或扩权，不把相似线索当作已证实版本关系；旧根的冻结声明／额度／阶段不改

### Requirement: Assigned deep-reading works remain in the question input
系统 SHALL 保留每个深读分组指定的全部采纳成果ID及其题名、日期、来源和证据映射，不为局部种子字节上限删除对象。完整署名证明可保留在根而不重复加入不负责归属抽取的深读阶段；实际完整请求仍 MUST 经过原预算、容量、期限及资料权限准入。

#### Scenario: Large accepted affiliation records
- **WHEN** 深读组的完整署名记录使旧种子上限超限
- **THEN** 系统使用原采纳身份投影，不删除指定成果；实际完整请求仍装不下时保留阶段并暂停，不派发缺对象请求冒充完成

#### Scenario: Old question-seed contract resumes
- **WHEN** 工作流使用旧问题种子契约，或阶段输入绑定不同
- **THEN** 不跨版本复用阶段，不清空旧尝试后重新派发；旧结果可按原权限读取，根用量／期限不重置

### Requirement: Located technical conditions reach writing source context
系统 SHALL 将本次深读卡的合格原文proof在当前保留证据中重新核对，将仍有效的位置作为同源相邻条件选段线索，不以摘要代替来源、不扩展权限或预算。系统 SHALL 在研究记录中保留实际选中与遗漏，选段命中 MUST NOT 被当作科学支持或整篇已读证明。

#### Scenario: A proof is stale or cannot fit
- **WHEN** 深读卡原文位置／引语与当前证据不一致，或原来源配额无法装入该位置窗口
- **THEN** 不把旧摘要当原文补入写作；失效proof不作线索，有效但未装入的proof保留未选状态，完整条件语义继续由最终审核及真实旅程判断

### Requirement: Frozen per-chart Skill overrides
系统 SHALL 提供内置、手选及显式允许的自动绘图，并允许在非内置方案中按稳定数据图ID指定已注册Skill覆盖。默认及覆盖 SHALL 分别冻结当前适用版本，在同一原预算声明式计划中按图加载，不能执行Skill脚本或扩大权限。

#### Scenario: Reopen an explicitly styled chart
- **WHEN** 用户保存了某图的Skill覆盖并重新打开或下载该图
- **THEN** 产物 SHALL 同时匹配来源图、呈现、覆盖Skill及原数据身份，不能返回另一种呈现或默认Skill的文件

#### Scenario: Requested override has no retained chart data
- **WHEN** 该图未取得有据数据或本次页面没有使用对应图
- **THEN** 保留具体缺口并暂停正常交付，不静默切换Skill或构造替代数值

### Requirement: Question-first reader report and technical appendix
系统 SHALL 围绕读者的研究问题组织核心判断、机制比较、演进及可执行建议，保留依据与适用条件。逐篇完整实验说明及详细课题表 SHALL 可进入附录，支持主文与附录的独立阅读和导出。研究深度 SHALL 由问题覆盖和实质分析决定，不由固定页数或每模块固定段数代替。

#### Scenario: Resource-dependent cooperation choices
- **WHEN** 用户要求研究团队与合作资源且尚未声明具体设备和业务条件
- **THEN** 报告提供需要何种日志、系统控制权、设备及首个成果的条件化路径，不虚构用户资源或团队合作意愿

#### Scenario: Research edition after a failed automatic run
- **WHEN** 自动任务失败后以保留材料和有界续作人工整编报告
- **THEN** 研究记录分别保存自动任务状态与整编产物的来源/用量，不将历史任务改为completed，也不以样例宣称通用自动模板已实现

#### Scenario: Read the general main report and appendix
- **WHEN** 模块草稿同时提供核心判断、主体段落和详细实验附录
- **THEN** 系统共用来源编号、统计绑定和转义校验；预设先呈现核心判断，附录可展开并分别下载或打印，不生成额外未选模块

#### Scenario: Retained text and bounded layout extraction
- **WHEN** PDF全部正文已保留，但图表候选达到结构上限
- **THEN** 系统分别记录正文完整性和结构缺口，保留文字原位置，不把结构上限误报为正文缺失，也不把全文文字当全部图表已取得

#### Scenario: Bound model context and share audit excerpts
- **WHEN** 分析、写作或审核接收多篇全文与重复主张来源
- **THEN** 按问题选取有实质内容的完整记录、保存未选范围，保持原引用编号；审核共享引文仍逐主张限制可用摘录，所有调用受同一根派生额度与原文校验约束

### Requirement: Truncated analysis cannot become finished report evidence
分析模型在输出长度上限停止时 SHALL 保留用量与原始片段，进入现有可恢复暂停边界；截断JSON MUST NOT 被当作完整分析继续生成正常报告。最终结果持久化 SHALL 正确保存paused及完成时间为空，不因重复使用SQL参数的类型推断冲突改写为failed。

#### Scenario: Analysis reaches output limit
- **WHEN** 分析模型以finish_reason=length结束
- **THEN** 保存原始片段和实际用量，报告输入不接收截断JSON，根任务按既有暂停边界处理

#### Scenario: Persist a budget pause
- **WHEN** 最终状态为paused且已经保留部分报告和用量
- **THEN** PostgreSQL写入状态、原稿和用量，completed_at为空，不产生重复参数类型推断异常

### Requirement: Frozen delivery view
系统 SHALL 从已授权任务的冻结查询、报告、引用、统计及审核结果产生带版本身份的交付视图，保留原始正文和证据。历史任务缺少新契约时 SHALL 使用明确标识的兼容视图。

#### Scenario: Build a reading artifact from a stored result
- **WHEN** 用户读取已授权的历史研究结果
- **THEN** 交付视图使用该任务保存的正文、引用和统计，保留数据身份及原稿，不用当前默认配置替换研究依据

### Requirement: Reader-facing report and separate research records
系统 SHALL 用正常研究报告语言呈现研究发现、分析、图表及参考资料。段落类型、审核状态、产物/数据/指标标识、错误码和运行配置 SHALL 保留在独立研究记录或数据导出中，不自动拼入阅读正文、HTML或打印版。系统 SHALL 在方法说明中简洁交代来源、时间和样本范围，并在具体结论处保留影响解释的必要条件；不逐段重复免责或自我辩护，不把删除审核标识当作审核通过。

#### Scenario: Read and export an illustrated report
- **WHEN** 用户阅读或导出图文报告
- **THEN** 正文和图表呈现研究内容、单位、适用范围及引用，应用提供独立研究记录入口，JSON保留完整追溯资料

#### Scenario: Historical machine-generated appendices
- **WHEN** 历史正文包含旧程序添加的审核清单、冻结配置或依据偏移表
- **THEN** 阅读视图移除明确的系统段落而保留正常研究限制和参考资料，原始正文仍可在研究记录/数据中取得

#### Scenario: Reopen an existing report
- **WHEN** 用户重新打开本人历史研究
- **THEN** 页面使用原任务配置和数据，不使用今日默认值重算研究范围，不重新调用模型

### Requirement: Declarative report pages
系统 SHALL 提供标准、图像简报、研究脉络和自定义页面。页面 SHALL 显示标题、研究问题、适用模块、正文片段、图表或明确的数据缺口。自定义内容 MUST 作为数据处理，不执行HTML或脚本。

#### Scenario: Missing custom page answer
- **WHEN** 页面问题没有对应生成段落或结构化数据
- **THEN** 页面明确显示未单独回答的缺口，并保留完整报告入口，不生成无来源答案

### Requirement: Evidence-bound charts
系统 SHALL 使用实际统计快照或关系观察生成图表及可展开数据表，保留单位、样本口径、metric_id、来源与未知值。证据计数 MUST 标为证据而非成果数量。

#### Scenario: Unknown annual sample
- **WHEN** 年度样本为null
- **THEN** 图表显示未覆盖或断点，不补零、不据此推算增长

### Requirement: Explicit renderer capabilities
系统 SHALL 区分内置渲染、手选Skill和自动Skill。没有受信执行适配器的Skill或未支持的输出格式 SHALL 显示原因和可操作替代选择，不静默换图或假称执行成功。

#### Scenario: Unavailable drawing adapter
- **WHEN** 用户手选了尚无执行适配器的绘图Skill
- **THEN** 交付视图保留Skill选择与版本，显示待适配状态；用户可明确切换到内置绘图

#### Scenario: Registered Skill with trusted file rendering
- **WHEN** 手选或自动匹配的注册Skill适用render阶段，任务预算与期限仍允许执行
- **THEN** 系统冻结实际Skill身份及指令，模型仅生成允许图型和样式的声明式计划，由固定程序渲染已有数据为SVG／PNG／图表PDF；模型与Skill不得指定脚本、文件路径、新测量或权限

#### Scenario: Changed figure inputs or incomplete assets
- **WHEN** 保存产物的任务／execution／数据／交付描述／Skill身份不匹配，或计划及文件集合未完整
- **THEN** 结果读取不得重绘、静默回退或把旧产物标成功，正常完成交付暂停并保留原因；单图PDF不得冒称完整报告原生PDF

### Requirement: Portable delivery
系统 SHALL 允许完成的研究导出Markdown、含完整数据的JSON、无需CDN的离线HTML，并提供打印入口。导出 SHALL 使用相同交付身份，完整保留正文和引用，交互内容 SHALL 有静态替代。

#### Scenario: Offline HTML
- **WHEN** 用户下载HTML
- **THEN** 文件内包含页面、内联图表、数据表和完整正文；没有依赖React事件的失效按钮或外部脚本

### Requirement: Visible bounded iteration
系统 SHALL 展示实际计划、步骤状态、重规划原因和停止原因；仅在具体缺口及根任务预算允许时有限修订，用户可选择单轮或有限修订。

#### Scenario: Repeated evidence
- **WHEN** 连续修订没有保留新版本材料达到所选上限
- **THEN** 停止自动补证并报告未解决缺口，不把停止当作事实审核通过
### Requirement: Immutable owner-bound report text history
The system SHALL preserve report text or interrupted responses with their original audit, execution, plan and retained source-version references. Repeated persistence of the same snapshot SHALL NOT create another version. Historical generated conclusions SHALL NOT become independent evidence.

#### Scenario: A different owner requests a report version
- **WHEN** another owner requests the task or report version
- **THEN** no historical content is returned

#### Scenario: A draft precedes final source support
- **WHEN** generation or the final audit is incomplete or needs revision
- **THEN** the version remains a draft or interrupted response
- **AND** it is not offered as a supported report or a completed requested file

### Requirement: Versioned declarative delivery templates
The system SHALL save owner-scoped delivery configurations independently of evaluation weights, append revisions under an expected version and replay identical owner/request IDs. Copied configurations SHALL undergo current research preview and Skill admission.

#### Scenario: A stale writer saves a template
- **WHEN** expected_version differs from the latest owned revision
- **THEN** no new revision is created and the conflict is reported

#### Scenario: A copied template contains an unavailable Skill
- **WHEN** current research is previewed
- **THEN** current Skill and capability constraints apply without restoring old privileges

### Requirement: Reader task controls generated structure
The system SHALL freeze answer, summary, comparison, report or data-analysis intent and depth without another model planning round. Explicit pages and selected modules SHALL retain structure priority. Unsupported requested file adapters SHALL NOT be described as delivered.

### Requirement: 保留并继续原稿的审核
系统 SHALL 在审核结果格式损坏或截断时保留调用用量与已完成判断，并在原权限、额度、期限内对失败批次有限拆分重试；仍未完成时只允许对本人未变更的原稿及来源继续审核，不得将未核或不支持事实发布为已完成报告。

#### Scenario: 审核批次格式错误
- **WHEN** 一批审核返回不可解析或被截断的结构且原预算允许
- **THEN** 系统记录失败并将该批缩小后有限重试；成功批次不因这一错误重跑

#### Scenario: 已保存的审核未完成
- **WHEN** 拥有者继续本人原稿的审核且原稿、来源、审核合同及额度满足续作条件
- **THEN** 系统保留原判断及用量，只处理未完成的判断；来源改变、权限丧失或额度用尽时不得继续

### Requirement: 深读成果的实际全文上下文
系统 SHALL 在既有预算内为当前深读成果优先选入其已取得全文的正文窗口；不以元数据或摘要冒充全文。窗口必须为带可复查位置的真实来源片段，已定位 proof 不得被截断后冒充完整证据。

#### Scenario: 多篇成果包含已取得全文
- **WHEN** 深读批次中多个成果各自具有已关联的全文来源
- **THEN** 模型调用前检查每个成果至少一个关联全文的正文片段实际进入上下文；无法装入时记录缺口并按原预算和恢复规则处理

#### Scenario: 恢复原有深读任务
- **WHEN** 旧检查点没有新装配合同版本
- **THEN** 保留其原有输入绑定与选段规则，不重置预算、期限和已完成阶段

### Requirement: 对象调查支持研究判断
系统 SHALL 保留原始问题与实际来源限制，优先调查目标对象的真实研究；在已选模块内把前阶段材料有界交给后续分析。关键判断 SHALL 关联当前原文、推导、决策含义及必要的替代解释或取舍；不得将模型分析、同词命中或背景资料自动当作目标对象事实。

#### Scenario: 短问题开展开放研究
- **WHEN** 用户提交机构或团队研究问题且未显式限定只读种子
- **THEN** 系统沿原许可范围发现主要工作与团队，不预塞代表论文或以样例替代搜索；实际来源和未解决覆盖单独保存

#### Scenario: 深读结果用于综合判断
- **WHEN** 研究同时选择深读、演进或行动
- **THEN** 后续问题收到实际前阶段材料及原文引用，记录装入与遗漏，候选判断仍需原文审核，原预算和用户页面顺序保持

### Requirement: 原问题与成果读取的有界交接
新发现v2 SHALL 在开放机构研究计划中保留原问题检索及成果发现入口，不把机构名命中视为主题命中。已调度的补读未结束时 SHALL 先消费其结果，再选择后续链接；成果／全文的相关线索优先于泛目录和新闻。来源仍 MUST 通过当前权限、范围和出站准入，共享原调用／深度／节点上限。

#### Scenario: 机构新闻淹没论文线索
- **WHEN** 原问题包含具体技术主题且发现结果同时包含机构新闻、人员目录、成果页和全文链接
- **THEN** 选择分别记录主题命中、来源角色和选择理由；相同机构名不能提高主题相关性，纯背景入口数量受限，已取得页面的明确全文链接可进入下一轮读取，不推测不存在于来源的URL

#### Scenario: 原任务冻结了旧发现策略
- **WHEN** 恢复v1或无发现策略的旧任务
- **THEN** 保持其原规则、原输入绑定和用量期限，不静默升级或清除已有读取尝试

#### Scenario: 原文链接没有题目文字
- **WHEN** 新v3任务的已读相关页面明确给出数字编号PDF或原始出版入口，但锚文本只有阅读PDF或原文
- **THEN** 在词面门禁前识别实际href，并使用该父页的主题判断读取资格；相关全文优先于推荐文章，不构造URL，不将父页声明当成成果归属证明

#### Scenario: 等待一次工具失败的退避
- **WHEN** 同一node／operation／attempt重复保存或调度，没有新的失败
- **THEN** 保留首次next_retry_at；只有新失败产生新的退避期限，不增加原尝试数、不把网页上游错误默认为数据库故障

#### Scenario: 仅机构命中的搜索结果
- **WHEN** 新根冻结字面主题验收且当前查询包含具体技术词，但后端仅返回命中机构名的结果
- **THEN** 整批记录irrelevant_results，沿原后端、剩余次数和期限回退；部分结果不绕过同一主题筛选，未取得相关正文不消耗成果抽取模型调用


### Requirement: 原文支持的机构名称与发表身份
跨语言机构署名 MUST 通过当前已取得的显式官网入口或其实际同域语言入口建立名称依据；模型翻译不能替代原文。别名 SHALL 保留原entity_id、来源proof和冲突处理，最终成果重核当前证据。

#### Scenario: 中文对象与英文论文署名
- **WHEN** 机构入口实际链接另一语言主页，已取得主页标题和名称，并取得英文论文作者／机构原文
- **THEN** 在原读取限额内解析主页的原文别名并交接后续抽取；搜索片段、任意同域文章、外域跳转或无证明的译名不能建立该别名

#### Scenario: 日期内部重叠与署名拼接
- **WHEN** 一个完整日期含有较短月年子串，或模型把多作者／省略拼接写进署名
- **THEN** 日期内部重叠不构成两个独立日期，其他不同日期仍保持歧义；每条署名保留一位作者及连续原文，只有年份不补月份，版本日期不当作首次发表
