# 组织类型与对象选择端到端记录

2026-10-20 完成 OpenSpec 5.1，当前 20/34。工作台控件及请求构造已经在 4.1 中接入，本项核对当前实现并完成独立高校、独立实验室的真实用户路径，不为已有行为虚构 RED 或重复实现控件。

使用隔离的真实 Edge、现有认证、主 API、真实模型与取证工具、PostgreSQL。未拦截网络、替换模型／数据库或伪造报告，也未运行单元、回归、冒烟、健康、启动探针或其他门禁。

## 用户路径

消费程序 `scripts/organization_selection_e2e.py` 在两条独立浏览器页面中登录并进入研究工作台：

1. 开启组织模式，清空三个类型，提交后显示“请至少选择一种研究对象类型”，没有创建研究请求。
2. 仅选高校或仅选实验室，加入一个具体对象；故意将对象类型设为未选择类型，提交显示对应错误，没有创建研究请求。
3. 设定倒置日期，提交显示有效起止日期提示，没有创建研究请求。
4. 改成合法日期并提交，分别完成取证、分析、报告与页面显示。渠道选中状态在对象类型切换前后相同，请求和数据库保留同一渠道配置。
5. 核对用户选择的类型、名称、来源、学科、主题和时间进入生效结果及数据库。服务器补充默认字段可以存在，但不改变用户输入。等待实际报告标题和本次组织范围显示后截图。

两条真实研究：

- 独立高校：`749cc8a8-7a1d-4b31-b7af-62d62d0b603a`，Peking University，2024 年，DistServe 出版商来源。[选择页](organization-selection-20261020/university/selection.png)、[报告页](organization-selection-20261020/university/report.png)、[请求](organization-selection-20261020/university/request.json)、[实际结果](organization-selection-20261020/university/result.json)。
- 独立实验室：`fa689ff6-3ac9-46a7-b05a-5d6ff477ded7`，CSAIL，2020–2026 年，实验室官网。[选择页](organization-selection-20261020/laboratory/selection.png)、[报告页](organization-selection-20261020/laboratory/report.png)、[请求](organization-selection-20261020/laboratory/request.json)、[实际结果](organization-selection-20261020/laboratory/result.json)。

消费程序退出 0，两页没有捕获到浏览器运行错误。初次自动化因登录后未导航到“研究”而超时，未创建研究；修正浏览器操作后执行以上真实路径。未将自动化定位错误当成产品缺陷或接口失败。

混合选择复用 4.1 已保存的真实 MIT＋CSAIL 页面提交、报告与刷新证据，见[原始记录](organization-runtime-20261020.md)。这不是新建的第三条研究；4.4 另有高校＋企业的 API 共同署名案例。

## 证明范围

本项证明类型、具体对象、学科和时间控件的提交、拒绝、保存和报告消费；用户可以独立研究高校或实验室。实验室运行只取得一条官网导航片段，后续工具出现预算限制，报告明确没有可核实的研究主题；不能据此宣称实验室研究方向分析已经充分。完整分析深度、权重面板、评价适用性及导出分别保留后续任务。

程序支持 `--resume` 继续读取这两条已记录任务，不另建研究。该参数本轮没有额外执行，不把其存在当成恢复行为已验证。
