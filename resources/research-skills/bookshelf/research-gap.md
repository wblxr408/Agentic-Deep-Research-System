---
name: 研究空白分析
slug: bookshelf-research-gap
description: 从已收集研究全景和代表全文检查时间、方法、主题、应用及研究对象五类缺口。
version: 1
enabled: true
priority: 120
stages:
- analyst
- report
keywords:
- 研究空白
- 研究缺口
- research gap
- 未来研究方向
- research-gap
trigger_patterns:
- 研究空白
- 研究缺口
- research\ gap
- 未来研究方向
tags:
- bo-bookshelf
- method:bookshelf-research-gap
allowed_tools: []
required_tools: []
---

# Overview

研究空白分析 · research-gap

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。从已收集研究全景和代表全文检查时间、方法、主题、应用及研究对象五类缺口。比较旧／新研究路线，指出矛盾、未解决的条件和可验证的问题。少量检索结果或低论文数只能说明本次覆盖，不足以证明领域空白。按影响、可检验性、数据／资源可得性排序机会，保留反例与替代解释。

交接内容：证据支持的缺口候选、反例、研究问题及验证路线。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:analyst

从已取得材料执行方法分析，保留实体、条件、关系和来源身份。

# Stage:report

根据已核实研究结果组织自然报告，保留主文、技术条件、图表和引用。

# Reference:bookshelf-provenance

书架条目：research-gap

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/local-skills/research-gap

收录版本：本机保存版；发布：2026-10-22.5

署名：原作者待核实

许可说明：原许可与署名保留于源文件；本站未另授统一许可

原运行依赖：Python 3.10+；按包内 references/research-runtime.md 和原项目依赖说明配置，文献计量等分支可能需要 R / bibliometrix 或 Graphviz。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
