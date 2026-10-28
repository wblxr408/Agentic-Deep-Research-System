# Spec Delta

## Purpose

允许用户将中国站Agnes保存在本人模型配置中，并将明确选取的简单开发任务交给它生成候选修改。模型凭据、当前研究配置与开发任务分开管理，返回结果须经过主执行者审阅，真实调用状态与验证范围可以追溯。

## ADDED Requirements

### Requirement: Agnes provider and personal saved configuration
系统 SHALL 提供Agnes中国站文本模型选项，并允许用户加密保存额外模型配置；保存额外配置 MUST 不改变当前主模型或正在执行研究的模型合同。

#### Scenario: Save Agnes alongside DeepSeek
- **WHEN** 已使用DeepSeek的用户保存Agnes配置
- **THEN** 本人已保存配置出现Agnes，当前主模型仍是DeepSeek，其他用户不能读取该密钥

#### Scenario: Activate a saved configuration
- **WHEN** 用户明确应用本人已保存的Agnes配置
- **THEN** 该配置成为后续任务的主模型，接口只返回掩码凭据

### Requirement: Bounded development delegation
开发委派 SHALL 只发送调用方显式选择的任务和源码，拒绝凭据、仓库之外文件、二进制和超额输入；模型 MUST 只返回候选修改，不能读取更多文件、执行命令、递归委派或直接修改仓库。

#### Scenario: Delegate a provider catalog change
- **WHEN** 主执行者选择端点目录文件和明确的小修改任务
- **THEN** Agnes返回限定文件的候选，保留请求、原响应和用量，只有主执行者审阅后才应用

#### Scenario: Incomplete or out-of-scope response
- **WHEN** 响应被截断、超时、格式错误或提出未选择文件
- **THEN** 保留实际失败及已知用量，不自动应用或无界重试

### Requirement: Secret ownership and endpoint boundaries
凭据 SHALL 保留在本人加密配置或主机受保护的凭据文件中；开发委派 MUST 使用已确认的官方区域端点，禁止跨区自动转发和在日志、仓库或候选产物中记录密钥。

#### Scenario: Windows credential use
- **WHEN** 当前Windows用户启动开发委派
- **THEN** 在本机解密当前用户DPAPI凭据，仅在授权的Agnes请求头中使用
