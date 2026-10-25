# Spec Delta

## Purpose

为跨对象、跨学科的研究任务提供一致、易读的前端界面，使用户能够配置研究、理解实际执行步骤、查看原文依据并阅读图文报告，同时通过独立技术文档理解系统的工作方式。

## ADDED Requirements

### Requirement: Theme and title hierarchy

系统 SHALL 提供纸白苔绿、暖灰赭石、雾白靛蓝、墨黑青绿四套配色及对应横幅背景，使用独立黑色蒙版。中文主标题为“知之为知之，不知则搜之。”，副标题为“搜而不思则罔，思而不搜则殆。”；英文主标题为“Research is all you need”，副标题为“In Sources We Trust”。主标题 SHALL 显著大于副标题，桌面基准为原首页字号的两倍。

#### Scenario: Theme and language persist
- **WHEN** 用户选择配色或标题语言并重新打开页面
- **THEN** 页面恢复其选择，横幅、控件、图表和技术文档使用相同主题。

### Requirement: Research configuration remains available

系统 SHALL 使用多行输入、简洁基本选项和分组高级配置，保留现有对象、多学科、评价权重、来源、预算、模板和绘图 Skill 配置及当前权限校验。

#### Scenario: User changes advanced configuration
- **WHEN** 用户打开配置主题、修改参数并提交
- **THEN** 请求沿用原理解预览与提交契约，页面不丢失其他分组的草稿。

### Requirement: Workflow is grounded in execution

系统 SHALL 将当前计划依赖、步骤状态和执行事件呈现为可缩放、平移、定位的流程图，节点可查看工具与输入输出摘要。终态和当前快照优先于旧事件；缺失信息不得推定为成功。刷新和连接恢复 SHALL 保留持久步骤。

#### Scenario: Reopen paused research
- **WHEN** 用户打开已有暂停任务并刷新
- **THEN** 显示已完成步骤及实际暂停阶段，节点不继续显示运行动画，不将旧事件标为当前执行。

### Requirement: Independent technical documentation

系统 SHALL 提供独立技术文档窗口及顶部主题导航，以分层卡片、数据方向连线和可控动画解释现有研究过程、ACI、证据与检索、Skill、模型路由、预算、恢复及图文交付。

#### Scenario: Explore a technical topic
- **WHEN** 用户打开技术文档、切换主题并点击图中节点
- **THEN** 显示该节点用途、输入输出和对应原理，动画可暂停或单步，减少动效偏好生效。

### Requirement: Reports prioritize readable findings

系统 SHALL 将正文、图表和引用作为默认阅读内容，将预算、审核、版本和执行详情置于独立研究记录。正文具备目录、可读行宽、来源预览及图表放大和数据下载；不在报告中添加防御性模板说明。

#### Scenario: Inspect supporting evidence
- **WHEN** 用户点击报告中的引用
- **THEN** 打开对应来源卡片，可查看摘录、保留原文及外部来源，遵守原任务访问权限。

### Requirement: Accessible responsive interactions

系统 SHALL 为窗口、标签、画布和表单提供键盘操作、可见焦点、明确标签、简短错误及响应式布局。配色及语言操作不得重置研究草稿；异步来源切换不得显示前一次请求的内容。

#### Scenario: Close an auxiliary window
- **WHEN** 用户用 Escape 或关闭按钮退出详情窗口
- **THEN** 焦点回到触发控件，研究页面和草稿保持。
