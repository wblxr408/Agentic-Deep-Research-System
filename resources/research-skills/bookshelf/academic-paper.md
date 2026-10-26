---
name: 统一学术写作
slug: bookshelf-academic-paper
description: 依据研究目标、已有证据、语言和目标读者选择提纲、摘要、综述、全文或修订路径。
version: 1
enabled: true
priority: 120
stages:
- report
keywords:
- 学术写作
- 论文写作
- academic writing
- manuscript
- 论文修订
- academic-paper
trigger_patterns:
- 学术写作
- 论文写作
- academic\ writing
- manuscript
- 论文修订
tags:
- bo-bookshelf
- method:bookshelf-academic-paper
allowed_tools: []
required_tools: []
---

# Overview

统一学术写作 · academic-paper

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。依据研究目标、已有证据、语言和目标读者选择提纲、摘要、综述、全文或修订路径。保持论点—证据—推理链，沿用真实结果、公式和引用标识。修改时保留范围外原稿，评审意见逐条回应并指出改动位置。按用户要求组织格式，源码、格式转换与编译仅走已接入工具。

交接内容：清晰章节、连续论证、来源引用及修订说明。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:report

根据已核实研究结果组织自然报告，保留主文、技术条件、图表和引用。

# Reference:bookshelf-provenance

书架条目：academic-paper--local

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/fused-skills/academic-paper

收录版本：fusion-2026-10-05；发布：2026-10-22.5

署名：Imbad0202 / Academic Research Skills / bahayonghang

许可说明：各模块分别适用其原许可。保留模块内 LICENSE / NOTICE；不得用王博的署名替代原作者。 ARS 当前公开许可为 CC BY-NC 4.0（原作者 Cheng-I Wu）；其完整文本随包保留。 academic-writing-skills 根目录未找到统一 LICENSE；保留作者的安装/自行修改说明及原文件，不另宣称 MIT 或商业许可。

原运行依赖：Python 3.10+；TeX / Typst / Pandoc 仅在对应格式任务需要；编译也可使用客户端自带编译工具。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
