---
name: 地理空间数据分析
slug: bookshelf-geopandas
description: 确认数据中的坐标、几何、行政区、时间和 CRS；对面积、距离或连接选择适用投影与单位。
version: 1
enabled: true
priority: 120
stages:
- analyst
keywords:
- geopandas
- 地理空间
- 空间分布
- crs
- 地理合作格局
trigger_patterns:
- geopandas
- 地理空间
- 空间分布
- crs
- 地理合作格局
tags:
- bo-bookshelf
- method:bookshelf-geopandas
allowed_tools: []
required_tools: []
---

# Overview

地理空间数据分析 · geopandas

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。确认数据中的坐标、几何、行政区、时间和 CRS；对面积、距离或连接选择适用投影与单位。区分空间包含、相交、最近邻和地理共现，说明边界与缺失记录。仅解释已有数据与真实计算结果；GeoPandas、投影或数据读取能力不在现有工具中时保留所需操作和输入，不能以文字推算替代。

交接内容：数据与坐标口径、空间关系、可复核结果及图示需求。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:analyst

从已取得材料执行方法分析，保留实体、条件、关系和来源身份。

# Reference:bookshelf-provenance

书架条目：geopandas

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/local-skills/geopandas

收录版本：1.4；发布：2026-10-22.5

署名：原作者待核实

许可说明：MIT

原运行依赖：Python 3.10+；按包内 references/research-runtime.md 和原项目依赖说明配置，文献计量等分支可能需要 R / bibliometrix 或 Graphviz。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
