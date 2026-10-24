# 5.4 报告预览与导出端到端记录

2026-10-21。范围为新组织研究的对象、统计口径、冻结权重、来源和缺失说明，贯通 PostgreSQL、工作台、原报告及下载文件；不包括后续图像模板、绘图和整篇科学主张核验。

## 实际失败与实现

消费者 `scripts/organization_report_export_e2e.py` 首先通过真实 Edge 登录及研究 API 创建新研究 `ae40fc8d-3f06-4fe0-845c-66ae41998a5d`，实际模型／工具生成报告后，在“完成报告必须携带冻结导出摘要”的业务断言失败。没有使用旧报告或替代模型输出制造失败。

新增 `app/organization_report.py`，Report 节点在模型调用后构造摘要，保存到原组织结果并追加 Markdown。前端新增摘要与下载组件；Markdown、JSON、HTML 使用同一结果，HTML 克隆实际安全渲染 DOM，原生折叠在断网后仍可操作。仅新增表格解析依赖 `remark-gfm`，未增加模型／Agent／存储服务或导出 API。

## 最终实际研究

同一消费者在实现后创建新研究 **`2c8d4301-4cba-4adc-b692-c4da7e6add04`**，未把失败前的报告回填成新结果：

- 对象为 Peking University，高校单选；学科标签 computer science，时间 2024-01-01 至 2024-12-31，主题 DistServe。
- 原始主题／证据权重 6／4，生效为 **60%／40%**，其他维度为零；配置 `report-export-e2e-v1`。
- 实际取得出版商[论文页面](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin)及会议日程两条证据，2 条引用；结构化纳入 1 条发表、1 个未关联版本的独立家族。
- 12,845 字符报告，摘要保留 8 条解释边界；目录未自动应用到本次成果，未知指标／关系不补造。对象消歧仍为 pending，原文定位验证不代表独立语义复核。

本场景没有宣称来源被限制为仅一个页面：工具实际又取得会议日程，纳入范围在保存的来源列表中如实显示。取得内容及预算沿用原取证机制。

## 消费结果

最终执行退出 0，真实消费者完成：

1. 查询保存的完成结果，摘要范围、完整权重与当次配置相同；60%／40% 可从保存比例复算。
2. 使用真实 PostgreSQL 驱动读取原 `final_report`、`review_status`，正文和摘要与 API 完整相同。
3. 在工作台展开“研究口径”，读取权重表中的 60.00%／40.00%，查看对象来源与缺口，刷新后仍可回访。
4. 三次实际点击下载并等待浏览器下载完成；Markdown 与原保存正文完全相同，JSON 的正文、配置、完整摘要与保存结果相同。
5. 在断网的真实 Edge 页面打开下载 HTML，展开原生折叠，读取同一 60.00% 权重、实际出版商链接和缺口。下载文件不依赖 React hydration 或远程样式才能阅读。

没有新增研究请求来完成下载；报告正文、配置和待核信息不由下载动作重算。实际报告科学主张的最终审计仍含未核内容，因此本项不被当成 OPT-15 全部审核通过，亦不代表 ORG 整体完成。

## 产物与剩余范围

[Markdown](organization-report-export-20261021/report.md)、[完整研究 JSON](organization-report-export-20261021/report.json)、[离线 HTML](organization-report-export-20261021/report.html)、[界面截图](organization-report-export-20261021/summary.png)、[离线截图](organization-report-export-20261021/offline-report.png)。界面截图受报告卡内部滚动裁剪；完整离线截图及真实表格消费补充其可见范围。

用户活动目标明确只允许端到端能力场景，所以没有执行原任务末尾列出的类型、构建或 lint 门禁，未运行单元、回归、冒烟、健康及其他探针。该限制优先于任务原文。更广学科、业务交付、分析深度、图像报告及整体统一端到端验证继续按 TODO 推进。
