# 2026-10-19 评价来源证据

该目录保存开发阶段真实公开取证后进入生产适配函数的输入／输出。预览接口不联网，内置数据是固定且部分覆盖的快照。数值与版本应按这些原始材料解释，不据此宣布已取得所有评价数据。

| 来源 | 实际取得及身份依据 | 文件／状态 |
| --- | --- | --- |
| [CCF 2022 原始目录 PDF 镜像](https://scdm-shu.github.io/ccf/2022-CCF-Ranking.pdf) | 封面标 2022 年、中国计算机学会；第 13 页计算机网络 A 类包含 SIGCOMM、NSDI，带 DBLP 链接 | `public-catalogue-records.json` 中 2022 记录；镜像不能冒充官网实时返回。 |
| [CCF 2012 原始目录 PDF 镜像](https://risame.github.io/sun/ccf.pdf) | 封面实际为 2012，非检索结果可能暗示的 2019；第 15 页 SIGCOMM A、第 16 页 NSDI B | 保存 2012 记录，按实际封面纠正年份，不伪造 2019 数据。 |
| [ICORE 官方 CORE2023 查询](https://portal.core.edu.au/conf-ranks/?search=SIGCOMM&by=all&source=CORE2023&sort=atitle&page=1) | 返回 SIGCOMM、CORE2023、A*，FoR 4606 | 保存对应历史版。 |
| [ICORE 官方 2026 查询](https://portal.core.edu.au/conf-ranks/?search=SIGCOMM&by=all&source=ICORE2026&sort=atitle&page=1) | 返回 SIGCOMM、ICORE2026、A*，FoR 4606 | `icore-2026-preview.json`。 |
| [ABDC 官方工作簿](https://abdc.edu.au/wp-content/uploads/2026/09/ABDC-JQL-2025-v3-210926.xlsx) | 真实读取 2025、2022、2019、2016、2013、2010 工作表；JIBS 印刷 ISSN 0047-2506、在线 1478-6990 均关联 A* | 保存一所期刊的历史样本，FoR 旧版 1503、新版 3507；`abdc-2025-preview.json`。 |
| [OpenAlex 论文响应](https://api.openalex.org/works/W1951724000) | 原始响应保留模型外提供的数值、元数据及更新时间 | `openalex-work.json`、`openalex-normalized.json`、`openalex-2026-preview.json`。 |
| [AJG 官方入口](https://charteredabs.org/academic-journal-guide) | 显示 AJG2024 方法文件与登录／注册入口；本轮没有登录授权 | 没有取得真实目录等级；仅授权导入适配可用。 |
| [CCF 官网入口](https://www.ccf.org.cn/Academic_Evaluation/By_category/) | 本轮直接请求返回验证页，未取得目录 | 未将验证页当目录或自动绕过。 |

`ccf-historical-preview.json` 和 `ccf-2022-preview.json` 分别展示不同年份目录的实际匹配；其他体系的状态依来源可用性独立保留。为减少无关资料复制，只提交已消费的有限目录事实，不附整个工作簿或 PDF。

OpenAlex 引用窗口依据其 [引用／FWCI 一手说明](https://help.openalex.org/data/works/citations/)，并与原始响应更新时间分开记录。此处 FWCI 是 **OpenAlex 提供值**，不能当作 Elsevier SciVal FWCI。
