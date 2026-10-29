# M2 真实全链旅程

2026-10-29，本机Windows，ADRS任务分支`codex/adrs-todo-20261023`。11.1—11.4原件、原图页、界面与资料包源码整体完成后才启动本次研究；未执行局部、回归、探针、构建／类型／schema检查或旧数据重放。源码完成不等同运行、读者价值或所有边界通过。

## 环境与任务

实际启动API时PostgreSQL连接被拒绝；Docker引擎未运行。使用既有`docker desktop start`原生桥恢复引擎。读取已有容器归属和卷后，仅恢复`deepintel-db`／`deepintel-redis`，沿用`deepintel_pgdata`／`deepintel_redisdata`，没有新建空研究库。任务级Compose覆盖关闭数据库自动健康探针，没有调用健康测试。随后启动本机API8015、Vite5185并执行实际业务创建；没有启动容器内旧API／前端。

新根`4a1af3c1-b358-4dea-8679-937616e2957a`，execution`2ebb1041-0af2-46c0-9f59-67bff305f079`，原短问题“北京大学 LLM 服务研究”。仍从机构官网入口发现成果，没有预置论文／作者或复用旧任务全文。范围2020-01-01至2026-10-28、计算机、综合六模块、深入研究、公开网络、图文简报、内置图表、Markdown／JSON／HTML，原新任务建议630,000 Token／56工具／4,320秒。根冻结实际账号`agnes / agnes-3.0-flash`，已发生Planner收据确认；不改旧30daffcc的DeepSeek绑定、236,848 Token或续作次数1。

本次冻结`source_media_policy=adrs-source-media-v1`。原件保存表随实际应用部署接入；最终未取得原件／图片／报告交付。不以读取表、创建成功、实时界面或初始模型收据宣称模块通过。

原始记录位于`outputs/m2-source-media-20261029/`的request、preview、budget-advice、run、latest-task、observations、runtime-state、source-assets；其中本机原文／运行记录不随源码提交。

## 实际停止与源代码修正

05:58UTC观察到本根`paused / research_discovery_incomplete`，23,501 Token／23工具请求，0在途，原时长489秒；完成两批成果抽取，但没有获准成果，没有报告、反思、完整审核或图文交付。取得10份正文／页面版本，其中一份无关的Qualcomm产品简报被原读取器解析为完整PDF；原件表为0。这不是图像渲染失败，渲染阶段尚未到达。

实际媒体交接缺口：新策略只在根`delivery`内，而工具投影有意排除展示配置；读取器因此从未拿到保存原件的标志，取得的PDF也没有`source_asset`。修正为新根媒体v2把原件采集策略放进已有`external_evidence`工具契约；该字段本就随有界browser交接，不把整份报告配置发给工具。旧v1根及其账本不升级，不重新抓原件冒充原采集版本。

实际发现缺口：已取得arXiv HTML明确包含相同论文的PDF／abs链接，但它们位于页头，被`navigation`标志降级；正文参考文献中的Qualcomm PDF先占名额。另一个Reddit分享URL的query含`/abs/`，对整个URL扫描把它误归原始论文入口，并重读同一论文多个版本。修正为仅新发现v4按实际path识别PDF／abs／html，排除分享提交动作；同标识的实际arXiv表示链接与明确页头下载／citation_pdf_url入口可优先于引用文献。只作读取排序，不推导署名、版本等价、全文或事实支持；原准入、12来源／3层／每批3项、工具次数和重试界限保留。

这两项修正只做源码和调用链审阅，没有重放旧响应或执行局部检查。完整新根旅程尚未启动；旧4a1af3c1费用、失败和原输入保留。OpenSpec11.5、M1.E2E、M2、M3均未完成。
