---
name: 公司与行业研究
slug: bookshelf-company-intel
description: 按明确企业、行业或竞对集合确定范围；仅在任务要求时发现候选竞对。
version: 1
enabled: true
priority: 120
stages:
- planner
- analyst
keywords:
- 公司研究
- 企业布局
- company intel
- industry research
- 战略信号
- company-intel
trigger_patterns:
- 公司研究
- 企业布局
- company\ intel
- industry\ research
- 战略信号
tags:
- bo-bookshelf
- method:bookshelf-company-intel
allowed_tools: []
required_tools: []
---

# Overview

公司与行业研究 · company-intel

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。按明确企业、行业或竞对集合确定范围；仅在任务要求时发现候选竞对。以财务、市场供给、产品、竞争、趋势、决策含义及专利／招聘／管理公告七个视角组织来源，优先原始公告与官方文档。将科研成果和业务关联以具体证据连接，分别标注事实、解释及待验证假设。

交接内容：对象卡、分视角证据、变化与含义、合作或研究切入点。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:planner

把方法落实为当前问题的范围、来源与计划交接。

# Stage:analyst

从已取得材料执行方法分析，保留实体、条件、关系和来源身份。

# Reference:bookshelf-provenance

书架条目：company-intel

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/local-skills/company-intel

收录版本：本机保存版；发布：2026-10-22.5

署名：原作者待核实

许可说明：原许可与署名保留于源文件；本站未另授统一许可

原运行依赖：按源文件中的运行依赖说明配置 Python、Node 或相应专用工具。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
