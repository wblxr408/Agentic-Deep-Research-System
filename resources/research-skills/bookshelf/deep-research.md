---
name: 研究入口分流版
slug: bookshelf-deep-research
description: 从现有请求选择主题调研、简报、综述、事实核查或 WHY/HOW/WHAT 模式，冻结对象、问题及时间。
version: 1
enabled: true
priority: 90
stages:
- planner
- analyst
- reflection
- report
keywords:
- 深度调研
- 深入研究
- deep research
- 事实核查
- deep-research
trigger_patterns:
- 深度调研
- 深入研究
- deep\ research
- 事实核查
tags:
- bo-bookshelf
- method:bookshelf-deep-research
allowed_tools: []
required_tools: []
---

# Overview

研究入口分流版 · deep-research

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。从现有请求选择主题调研、简报、综述、事实核查或 WHY/HOW/WHAT 模式，冻结对象、问题及时间。按子问题设计原始来源优先的证据计划；对独立子题使用既有调度，综合时交叉核查支持与冲突。把检索覆盖、原文阅读程度、数据口径和分析推断区分；输出针对本问题的发现与具体结论。仅用户要求监测时才另建计划。

交接内容：问题树、来源证据、综合发现、冲突和具体后续问题。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:planner

把方法落实为当前问题的范围、来源与计划交接。

# Stage:analyst

从已取得材料执行方法分析，保留实体、条件、关系和来源身份。

# Stage:reflection

逐项核对当前结论、数字和条件，输出有位置的问题与最小修订。

# Stage:report

根据已核实研究结果组织自然报告，保留主文、技术条件、图表和引用。

# Reference:bookshelf-provenance

书架条目：deep-research--local

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/fused-skills/deep-research

收录版本：fusion-2026-10-05；发布：2026-10-22.5

署名：Imbad0202 / Academic Research Skills

许可说明：各模块分别适用其原许可。保留模块内 LICENSE / NOTICE；不得用王博的署名替代原作者。 ARS 当前公开许可为 CC BY-NC 4.0（原作者 Cheng-I Wu）；其完整文本随包保留。

原运行依赖：支持联网检索的 AI 客户端；论文链接、数据库或模型服务需用户自己的连接。不会随包分发 API 密钥。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
