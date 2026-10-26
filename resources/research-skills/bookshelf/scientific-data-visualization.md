---
name: 统一科研绘图
slug: bookshelf-scientific-data-visualization
description: 先明确图要回答的问题，检查数据类型、单位、分组、实验单位、配对、缺失与样本量，再选择图型。
version: 1
enabled: true
priority: 120
stages:
- analyst
- render
keywords:
- 科研绘图
- 数据可视化
- scientific visualization
- 统计图
- 图表设计
- scientific-data-visualization
trigger_patterns:
- 科研绘图
- 数据可视化
- scientific\ visualization
- 统计图
- 图表设计
tags:
- bo-bookshelf
- method:bookshelf-scientific-data-visualization
allowed_tools: []
required_tools: []
---

# Overview

统一科研绘图 · scientific-data-visualization

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。先明确图要回答的问题，检查数据类型、单位、分组、实验单位、配对、缺失与样本量，再选择图型。区分数值 ID 与测量值，保留数据范围和分母；误差条、显著性和拟合来自真实计算。渲染阶段按当前适配器的 bar、line、network、matrix 提交来源绑定数据和样式；其他图型形成绘图需求，不冒充已生成图。保留可读中文字体、单位、图例和导出格式。

交接内容：数据剖析、图型理由、来源数据与可复现绘图参数。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:analyst

从已取得材料执行方法分析，保留实体、条件、关系和来源身份。

# Stage:render

基于已有来源绑定的数据生成受控绘图方案，沿用当前渲染器支持的 bar/line/network/matrix；不运行外部代码。

# Reference:bookshelf-provenance

书架条目：scientific-data-visualization--local

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/fused-skills/scientific-data-visualization

收录版本：fusion-2026-10-05；发布：2026-10-22.5

署名：王博 / wblxr408 / Haojae

许可说明：各模块分别适用其原许可。保留模块内 LICENSE / NOTICE；不得用王博的署名替代原作者。

原运行依赖：Python 3.10+。按任务使用 numpy、pandas、matplotlib、scipy、PyYAML、openpyxl；期刊方案按需用 seaborn、SciencePlots、plotly。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
