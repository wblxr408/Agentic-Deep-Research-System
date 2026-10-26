---
name: 模板 · 年度影响力报告
slug: bookshelf-artifact-template-annual-impact-report
description: 报告结构：年度范围与目标→主要研究成果→团队及合作→可核实影响→后续重点
version: 1
enabled: true
priority: 120
stages:
- report
keywords:
- 年度影响力
- annual impact
- artifact-template-annual-impact-report
trigger_patterns:
- 年度影响力
- annual\ impact
tags:
- bo-bookshelf
- method:bookshelf-artifact-template-annual-impact-report
allowed_tools: []
required_tools: []
---

# Overview

模板 · 年度影响力报告 · artifact-template-annual-impact-report

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。把论文、项目、产出及应用成效放在各自口径内，用实际资料解释年度变化，区分机构自报和独立来源。 按以下结构组织本次报告：年度范围与目标→主要研究成果→团队及合作→可核实影响→后续重点。保持来源与图表位置，合并空章节，不为模板补造数字。

交接内容：章节结构、当前证据支持的正文、图表位置与来源。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:report

根据已核实研究结果组织自然报告，保留主文、技术条件、图表和引用。

# Reference:bookshelf-provenance

书架条目：artifact-template-annual-impact-report

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/local-skills/artifact-template-annual-impact-report

收录版本：本机保存版；发布：2026-10-22.5

署名：OpenAI 插件分发 · 原作者以文件署名为准

许可说明：原许可与署名保留于源文件；本站未另授统一许可

原运行依赖：需对应宿主插件及其实际可用工具。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
