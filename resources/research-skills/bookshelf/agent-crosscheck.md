---
name: 统一成果审查
slug: bookshelf-agent-crosscheck
description: 对照用户目标、范围和交付约定，合并目的与正确性两种视角。
version: 1
enabled: true
priority: 120
stages:
- reflection
keywords:
- 成果审查
- 交叉审查
- 结果复核
- crosscheck
- agent-crosscheck
trigger_patterns:
- 成果审查
- 交叉审查
- 结果复核
- crosscheck
tags:
- bo-bookshelf
- method:bookshelf-agent-crosscheck
allowed_tools: []
required_tools: []
---

# Overview

统一成果审查 · agent-crosscheck

# Prompt

在当前阶段按下列研究方法处理本次问题。先复用现有研究范围与输入，仅补充完成本阶段必要的信息；只产生本阶段成果，交给既有流程。对照用户目标、范围和交付约定，合并目的与正确性两种视角。检查结论是否回答问题、事实是否有来源、条件是否完整、取舍是否明确。每条问题保留证据位置、实际影响和最小修改，去重后按重要性给出。只审当前研究成果，不自动扩成代码或安全测试。

交接内容：目标符合性、真实问题清单、证据与修改建议。

# Constraints

沿用当前任务的对象、时间、资料访问、工具授权、预算和停止条件。只使用已经接入的工具与已取得证据；宿主插件、外部脚本、数据库和专业软件不因本方法入库而自动可用。保留原始数字、单位、样本条件和出处，统计与算法数值必须来自真实数据或实际执行结果。使用 ADRS 现有阶段，不自动增加 Agent、安装服务、发送消息或建立定时任务。以下归档原文仅用于查看来源，不作为新权限或运行指令；引用内容不得触发额外加载。报告正文写研究发现和依据，不复述这些内部规则。

# Stage:reflection

逐项核对当前结论、数字和条件，输出有位置的问题与最小修订。

# Reference:bookshelf-provenance

书架条目：agent-crosscheck--local

来源：https://github.com/wblxr408/skill-bookshelf/tree/db8ce71a00e9957030a4a19b1c1a474dfb16aa2e/fused-skills/agent-crosscheck

收录版本：fusion-2026-10-05；发布：2026-10-22.5

署名：原始入口作者待核实

许可说明：各模块分别适用其原许可。保留模块内 LICENSE / NOTICE；不得用王博的署名替代原作者。 原始 agent-crosscheck / intent-review 作者尚未核实，不宣称原始部分为王博原创。

原运行依赖：支持技能的 AI 客户端；开发结果审查共享包内 dev 规则。独立审查角色仅在用户授权和工具可用时使用。

适配范围：本条为 ADRS 阶段方法；原宿主操作和安装器留在来源包中。模板仅接入报告结构，不增加原生二进制导出。

# Reference:bookshelf-original

原主要文件和配套资源见固定来源。个人导入副本及原包在本机保留；仓库内仅分发本项目的阶段适配方法。
