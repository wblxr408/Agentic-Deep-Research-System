# 研究来源范围专项交付

用户希望将导航限定为论文出版商／会议论文集、Google Scholar、DBLP、arXiv，以及企业、高校、机构官网。本轮在本地OpenMinion入口实现source_scope单选／多选、官网显式域名、出版商可配置清单与快照；网页面板尚未接入。实际配置见examples/organization-research.json，使用与错误边界见docs/openminion-research.md。

## 执行点

- app/research_sources.py：固定来源组和用途、域名精确／子域匹配、范围内查询与结果过滤。Scholar仅发现，不能读取或变成引用；DBLP标元数据，arXiv标预印本，机构官网不自动认定归属真实性。
- app/openminion_research.py：范围固定在请求中，核对种子、读取前及读取终点，保存source_policy、source_uses、effective_query及rejected_sources。默认只开放四组学术来源，官网需显式域名；旧任意站点请求需要补配。
- app/channels/execution.py::HttpReader：可选URL准入回调在每跳DNS解析／连接前执行，原有公共地址与锁定传输继续执行；其他调用者未设置此回调。

采用现有A2ABreak v1.0增量评估：**A2AB-07／Webhook归属验证与受控出站／工程解决方案、验收办法**，控制点为读取器逐跳连接前准入；**A2AB-08／结构化授权请求与权限不放大／工程解决方案、验收办法**，控制点为请求中的固定域名范围和可信工具闭包。其余9项沿用OpenSpec设计中的适用性判定。知识库索引为main/engineering/security/a2abreak/a2-abreak-多-agent-安全基线与-11-项方案索引；这是本地方案验证，不是官方修复认证。

## 实际验证

当前变更新增用例tests/current_change/test_research_source_scope.py：先在旧读取器观察2项断言失败，实际结果为accepted而期望source_out_of_scope；实现后这2项通过。新增范围配置与工具消费用例随后通过，涵盖单选／多选、域名冒充后缀、非法配置、Scholar只发现、过滤线索、原文调用拒绝和配置快照。

最终11项通过（5.90秒），三个修改模块py_compile成功，OpenSpec严格校验通过，apply任务为5/7。未运行已有回归或安全套件；这组用例用替代连接／搜索／模型调度验证来源边界，不能作为外部Google Scholar可用性、出版商完整覆盖或真实模型研究成功的证据。此次未重新进行外网完整研究，先前DeepSeek研究仍为partial。当前正文读取不支持PDF，这一缺口没有因来源准入而消失。
