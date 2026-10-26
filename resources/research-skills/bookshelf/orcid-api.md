---
name: 研究者身份检索
slug: bookshelf-orcid-api
description: 用公开 ORCID 记录、机构主页及发表署名交叉核查候选研究者。
version: 1
enabled: true
priority: 120
stages:
- search
- analyst
keywords:
- orcid
- 研究者身份
- 作者消歧
- 研究人员身份
- orcid-api
trigger_patterns:
- orcid
- 研究者身份
- 作者消歧
- 研究人员身份
tags:
- bo-bookshelf
- method:bookshelf-orcid-api
allowed_tools: []
required_tools: []
---

# Overview

研究者身份检索 · orcid-api

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。用公开 ORCID 记录、机构主页及发表署名交叉核查候选研究者。保留 ORCID ID、姓名变体、作品标识和隶属的起止日期，区分自报字段、来源字段和当前官网信息。同名、共同机构或共著不直接证明当前任职或可联系性；只取得已授权公开记录，凭据需求作为工具配置条件。

交接内容：身份候选、规范 ORCID、历史隶属和核实依据。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:search

通过现有搜索渠道取得候选及规范来源信息，交回原文入口。

# Stage:analyst

从已取得材料执行方法分析，保留实体、条件、关系和来源身份。

# Reference:bookshelf-provenance

书架条目：orcid-api

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/local-skills/orcid-api

收录版本：本机保存版；发布：2026-10-22.5

署名：原作者待核实

许可说明：原许可与署名保留于源文件；本站未另授统一许可

原运行依赖：Python 3.10+；按包内 references/research-runtime.md 和原项目依赖说明配置，文献计量等分支可能需要 R / bibliometrix 或 Graphviz。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
