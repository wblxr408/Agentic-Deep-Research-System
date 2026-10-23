# Spec Delta

## Purpose

为研究系统提供可维护的跨平台只读信息采集能力，使用户可以选择信息渠道，并将真实采集内容及其来源送入现有分析、校验和引用流程，同时清楚区分配置完成、内容采集成功和不可用状态。

## ADDED Requirements

### Requirement: Platform coverage
系统 SHALL 注册 web、exa、github、youtube、bilibili、rss、v2ex、twitter、reddit、xiaohongshu、facebook、instagram、linkedin、boss、xueqiu、xiaoyuzhou 渠道，并对每个渠道声明真实支持的搜索或读取操作、后端顺序及配置要求。

#### Scenario: Explicit platform query
- **WHEN** 用户指定 GitHub 渠道或使用 github: 查询
- **THEN** 系统使用 GitHub 后端并返回具有原始链接的仓库结果，而不把通用网页结果冒充 GitHub 原生结果。

### Requirement: Bounded fallback and truthful results
系统 SHALL 按用户配置的后端顺序进行有限采集，保留每次尝试的后端、错误类别与结果数量；空内容不得记录为成功，认证或风控错误不得触发自动登录或继续尝试同渠道后端。

#### Scenario: Backend unavailable
- **WHEN** 首选后端缺失而备选返回有效内容
- **THEN** 系统返回备选内容并记录首选失败与实际使用后端。

#### Scenario: Authentication required
- **WHEN** 平台返回认证失败
- **THEN** 返回需要用户配置的状态，停止该渠道降级，不将错误文本作为证据。

### Requirement: Research evidence integration
系统 SHALL 将渠道采集结果转换为现有研究证据，并保存渠道、后端、来源链接及采集时间；用户选择的渠道 SHALL 在研究提交、后台工作和检查点恢复中保持一致。

#### Scenario: Multi-source research
- **WHEN** 一次研究选择多个可用渠道
- **THEN** 分析节点收到有来源的合并证据，工具轨迹包含各渠道尝试结果，失败渠道不产生伪造引用。

### Requirement: Public collection recovery
系统 SHALL 为网页搜索提供独立 Bing RSS / Exa 引擎备选，支持 bili 公开搜索/详情返回和小宇宙公开原站页面数据；保留实际来源、内容类型与失败分类。

#### Scenario: Search engine challenge
- **WHEN** DuckDuckGo 返回挑战页面而独立搜索后端可用
- **THEN** 不解挑战或再次访问受限引擎；由备选返回查询结果，并记录首选 access_denied；Exa 免费额度耗尽准确归类 rate_limited。

#### Scenario: Public podcast page
- **WHEN** 用户读取有效小宇宙节目或单集链接
- **THEN** 返回原站介绍/shownotes/单集链接，明确音频转录未获取。

#### Scenario: Missing source or blocked platform
- **WHEN** 原站返回 HTTP 404 或 B站返回 HTTP 412
- **THEN** 分别记录 not_found 或 account_risk 并停止降级，错误页面不成为引用。

### Requirement: Owner-scoped maintenance
系统 SHALL 为已认证用户提供渠道配置和实际采集历史，按可信主体隔离数据；配置只允许注册后端和有界参数，列表查询不得发起探测、搜索或自动安装。

#### Scenario: Independent configuration
- **WHEN** 两个用户设置不同的后端顺序
- **THEN** 各自的采集使用自己的配置，另一用户无法读取其采集历史。

### Requirement: Constrained execution
系统 MUST 只执行服务端定义的只读命令，并限制执行期限、结果数量和输出字节；用户内容不得成为 shell、可执行路径、写命令或上游配置。HTTP 读取 MUST 拒绝私网、凭据 URL 和危险跳转。

#### Scenario: Untrusted command-shaped query
- **WHEN** 查询包含 shell 元字符或以选项开头
- **THEN** 查询作为普通数据处理或明确拒绝，不执行额外命令。
