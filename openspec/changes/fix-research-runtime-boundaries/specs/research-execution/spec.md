# Spec Delta

## Purpose

定义研究链路对公开网络、授权恢复、会话执行和事件输出的行为约束，使用户能够可靠暂停和恢复任务，并保证权限变化及时作用于已建立的连接和后续动作。

## ADDED Requirements

### Requirement: Public browser boundary
系统 SHALL 仅允许通用浏览器读取公共 HTTPS 目标，并对重定向、子资源和动态连接执行同等边界。

#### Scenario: Private target or redirect
- **WHEN** 页面请求解析到内网、回环或保留地址
- **THEN** 系统拒绝访问，私有内容不会进入研究证据

### Requirement: Bound approval resume
系统 SHALL 从完整已保存状态恢复具体已批准动作，保留查询、资料选项、工具权限、历史及已使用预算；批准 MUST 不放大其他动作权限。

#### Scenario: Resume paused action
- **WHEN** 所有待审批动作已得到决定
- **THEN** 系统从暂停的 DAG 继续，批准动作只执行一次，拒绝动作跳过，规划与预算不会重置

### Requirement: Session execution ownership
系统 SHALL 原子接受新会话或合法确认，拒绝重复执行和其他用户覆盖；审批决定 MUST 只能生效一次。

#### Scenario: Concurrent duplicate request
- **WHEN** 并发请求使用相同会话标识
- **THEN** 最多启动一个工作流，其他请求不会覆盖查询和结果

### Requirement: Stream revocation
系统 SHALL 在每个研究事件输出前及空闲等待期间重新检查原始凭据和会话归属。

#### Scenario: Revoke established stream credential
- **WHEN** 用户退出、撤销令牌或凭据版本失效
- **THEN** 已建立连接关闭，不再交付历史或后续研究事件

### Requirement: Empty batch completion
系统 SHALL 在所有工具被策略禁用时生成可读的受限结果与终态。

#### Scenario: All planned tools denied
- **WHEN** DAG 无可调用工具
- **THEN** 系统完成汇总与拒绝报告，不会以空结果提前结束
