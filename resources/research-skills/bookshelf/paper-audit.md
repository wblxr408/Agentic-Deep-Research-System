---
name: 统一论文审查
slug: bookshelf-paper-audit
description: 先确定审阅对象和目标，再检查研究问题、方法、实验／统计、证据、创新及表述。
version: 1
enabled: true
priority: 120
stages:
- reflection
keywords:
- 论文审查
- 审稿
- paper audit
- peer review
- 稿件评估
- paper-audit
trigger_patterns:
- 论文审查
- 审稿
- paper\ audit
- peer\ review
- 稿件评估
tags:
- bo-bookshelf
- method:bookshelf-paper-audit
allowed_tools: []
required_tools: []
---

# Overview

统一论文审查 · paper-audit

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。先确定审阅对象和目标，再检查研究问题、方法、实验／统计、证据、创新及表述。对问题给出具体段落或原文、影响和最小改法；将真实矛盾、证据不足和表达问题分开。需要多视角时在既有核对阶段组织视角，去重问题，不另设固定人数。完整核对引用与数字，不以自评分数替代证据。

交接内容：按重要性排序的问题、位置、依据和可执行修改。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:reflection

逐项核对当前结论、数字和条件，输出有位置的问题与最小修订。

# Reference:bookshelf-provenance

书架条目：paper-audit--local

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/fused-skills/paper-audit

收录版本：fusion-2026-10-05；发布：2026-10-22.5

署名：bahayonghang / Imbad0202 / Academic Research Skills

许可说明：各模块分别适用其原许可。保留模块内 LICENSE / NOTICE；不得用王博的署名替代原作者。 ARS 当前公开许可为 CC BY-NC 4.0（原作者 Cheng-I Wu）；其完整文本随包保留。 academic-writing-skills 根目录未找到统一 LICENSE；保留作者的安装/自行修改说明及原文件，不另宣称 MIT 或商业许可。

原运行依赖：Python 3.10+；PDF 输入按需安装 pypdf 或 PyMuPDF；稿件相关编译依赖由稿件项目提供。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
