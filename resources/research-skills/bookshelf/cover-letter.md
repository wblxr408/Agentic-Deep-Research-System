---
name: 投稿附信
slug: bookshelf-cover-letter
description: 依据已提供稿件、目标期刊、研究贡献与适配理由撰写附信。
version: 1
enabled: true
priority: 120
stages:
- report
keywords:
- 投稿附信
- cover letter
- submission letter
- cover-letter
trigger_patterns:
- 投稿附信
- cover\ letter
- submission\ letter
tags:
- bo-bookshelf
- method:bookshelf-cover-letter
allowed_tools: []
required_tools: []
---

# Overview

投稿附信 · cover-letter

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。依据已提供稿件、目标期刊、研究贡献与适配理由撰写附信。每个贡献点对应实际证据，保留作者及稿件身份；原创性、利益冲突或独占投稿声明只能使用用户已确认信息。引用具体研究价值，采用自然简洁语气；只生成草稿，不发送或提交。

交接内容：附信草稿、贡献依据及需由作者补充的信息。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:report

根据已核实研究结果组织自然报告，保留主文、技术条件、图表和引用。

# Reference:bookshelf-provenance

书架条目：cover-letter

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/local-skills/cover-letter

收录版本：5.1.0；发布：2026-10-22.5

署名：bahayonghang

许可说明：见源项目说明，本站不另授许可

原运行依赖：以原包及源文件为准

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
