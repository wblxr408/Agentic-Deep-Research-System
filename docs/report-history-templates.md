# 报告历史、图文模板与回答形式

2026-10-23源码交付，未运行、未建表。沿用Python／React和现有PostgreSQL，未增加Agent、服务或模型轮次；全部ORG／OPT／FLOW实现后才统一端到端。

## 按读者任务写作

DeliveryRequest.output_kind可选auto、answer、summary、comparison、report、data_analysis。auto为fact选直接回答、comparison选比较、aggregate选数据分析，其余选报告；深度沿冻结depth。`report_planning.py`在预览中生成版本化writing_plan，进入解释身份，Report实际消费前再核对输入。

显式自定义页面、选中组织模块拥有结构优先权，回答形式调整核心判断与模块写法。直接回答不强塞企业全景或统计章节；比较保留统一口径／条件；数据分析引用已有确定性统计，不让语言模型重算分母／比例。生成结构有效不等于正常交付：后者仍需完整支持审核和所需绘图完成。版本、预算与审核标签留工作区。

当前报告交付为Markdown／HTML／JSON及PDF打印，绘图另有SVG／PNG／图表PDF；未配置PPTX原生适配时预览拒绝请求，避免研究后把缺失格式记为完成。未将候选适配器冒充已实现。

## 不可变报告文本版本

现有数据库新增research_report_versions。原运行持久化及最终保存事务先检查实际owner／session／execution，再保存正文或中断响应、审核、引用、原文版本映射、计划／解释身份、交付配置和写作计划。report_binding含execution、plan及保留材料版本，旧正文不能无声配上新材料归档。

相同内容／审核／绑定得到同report_id，事务重放不新增版本。supported_report、saved_draft、incomplete_response分别呈现；中断JSON响应不冒充Markdown报告。每任务最多64版、单版8MB，容量不足明确失败，不删除旧记录以伪造保存成功。历史文本不复制大图像文件，不声称旧版均保有完整图像下载。

| 本人接口 | 行为 |
| --- | --- |
| GET /api/v1/research/{session_id}/reports | 版本编号、日期、状态、审核计数。 |
| GET /api/v1/research/{session_id}/reports/{report_id} | 原正文／响应、审核、引用、原文版本关联及读者投影。 |

工作区“报告版本历史”显式读取独立文本视图，不覆盖主稿；审核完成稿可下载该版Markdown。原文入口沿owner任务保留版本接口；不重绘、不重置预算、不将生成结论回灌成独立事实。历史保留沿原source_purge不删除历史任务、任务删除联动删除报告版本的语义，不新增共享权限。阶段恢复另沿原输入／期限／额度，不因读取历史自动续作。

普通研究的analyst_context现在亦由RuntimePersistence保存，修复此前仅组织研究同步到结果记录的缺口。运行快照及最终保存沿原execution检查额外拒绝当前已取消任务的迟到覆盖。

## 图文模板保存与复制

research_delivery_templates保存完整声明式DeliveryRequest的不可变修订，包括页面／问题／顺序、图型、主题、回答形式、格式、绘图选择及单图覆盖，独立于组织权重预设。记录owner、template_id、version、request_id、配置身份、名称及项目标签；项目标签仅用于本人分类，不能作为跨用户项目ACL。

接口为`/api/v1/research/delivery-templates`的GET／POST、`/{template_id}`的GET／PUT及`/{template_id}/versions`的GET。PUT在owner事务锁内检查expected_version再追加；同owner/request_id同参数重放，换参数或目标冲突。每人最多50模板、每模板100版，不自动删除。只存原声明式类型，不增加模板脚本、网络或文件权限。

查询面板可选版本并复制、另存或保存新修订。copied_from_template保留来源template_id／version，服务端确认归本人；允许编辑副本，不声称编辑后仍与原配置相同。当前研究冻结实际配置，重新预览对象／学科／数据与当前Skill；旧模板不能恢复禁用Skill。客户端保留同次请求ID、防同时发送；保存成功和随后列表刷新失败分别呈现。

## 部署与验证状态

两表DDL加入现有connection初始化及migrate入口，尚未执行；没有回填、历史重审、自动模板或后台迁移。资料／报告关联均由可信事务产生，未让模型编辑原owner或预算。

复用A2ABreak **v1.0**全11评估：**03《上下文归属与跨租户隔离》工程1—3**用于owner SQL／原文；**05《产物分块校验与断流恢复》工程1—4**用于完整稿／中断响应及不可变版本，非新签名传输；**06《并发状态版本与审批绑定》工程1—4**用于expected_version／request_id／execution／plan／证据绑定；**08《结构化授权请求与权限不放大》工程1—4**用于模板数据与当前Skill准入；**10《委派环路检测与全链预算》工程1／3及T3**用于无额外模型、原根预算及有界版本；**11《中断任务租约与有界资源回收》工程1／2／4**用于原期限／取消及迟到拒绝，无新租约系统。01沿原注册表，02／07／09无新Card／Webhook／跨组织凭据，04沿原API／事件许可。完整ID为A2AB-03等，对应原文在Basic Memory main/engineering/security/a2abreak/solutions；均待项目验证。

统一端到端覆盖真实稿／草稿／中断版、双owner、重放、取消／执行替换、原文／审核绑定、历史不回灌、模板并发／旧版复制／禁用Skill，以及不同回答类型和真实图文阅读／下载。当前SQL、类型、页面与功能都未执行，不据源码宣称质量或安全通过。
