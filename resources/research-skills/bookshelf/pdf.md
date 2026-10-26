---
name: 统一 PDF 工作流
slug: bookshelf-pdf
description: 从任务已允许来源取得 PDF，检查阅读范围、文本／扫描性质、页码与栏序。
version: 1
enabled: true
priority: 120
stages:
- browser
- analyst
keywords:
- pdf
- 论文全文
- 扫描文档
- pdf提取
trigger_patterns:
- pdf
- 论文全文
- 扫描文档
- pdf提取
tags:
- bo-bookshelf
- method:bookshelf-pdf
allowed_tools: []
required_tools: []
---

# Overview

统一 PDF 工作流 · pdf

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。从任务已允许来源取得 PDF，检查阅读范围、文本／扫描性质、页码与栏序。提取论文正文、图表及公式时保留页码、图表号与原文位置；OCR 按本任务已有授权和解析能力处理。区分摘要、部分页和全文覆盖，分析前回到具体段落。仅进行研究所需的读取与定位，编辑／表单等操作需明确任务范围。

交接内容：原文片段、页码／图表位置、覆盖范围和阅读结果。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:browser

通过现有网页／PDF读取适配器取得可定位原文与覆盖记录。

# Stage:analyst

从已取得材料执行方法分析，保留实体、条件、关系和来源身份。

# Reference:bookshelf-provenance

书架条目：pdf--local

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/fused-skills/pdf

收录版本：fusion-2026-10-05；发布：2026-10-22.5

署名：OpenAI

许可说明：各模块分别适用其原许可。保留模块内 LICENSE / NOTICE；不得用王博的署名替代原作者。

原运行依赖：Python 3.10+；按操作安装 pypdf、pdfplumber、reportlab、PyMuPDF。Poppler / pdftoppm 为可选渲染工具；Node.js 仅供宿主需要的文档标记脚本。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
