# Windows Docker Desktop 反复启动失败修复

2026-10-20，本机 Docker Desktop 4.84.0.234817、Docker CLI 29.6.2、WSL2 后端。用户要求优先修复多次出现的启动 error。本项为主机运行环境修复，不表示组织研究 TODO 或 MATCH.5 已完成。

## 原因与证据

本次 `com.docker.backend.exe.log` 在 13:32:21 UTC 的首个致命错误为：

```text
starting services: initializing Inference manager:
listening on unix://.../Docker/run/dockerInference:
remove .../Docker/run/dockerInference: The file cannot be accessed by the system.
```

后台随后退出，Linux 引擎管道未创建。`Docker/run` 中存在零字节的 `dockerInference`、`dockerEthernetVfkit`、`userAnalyticsOtlpHttp.sock` 重解析点；`docker-secrets-engine` 中存在同类 `engine.sock`。直接查询第一个端点返回 Windows error 1920。本次不存在后台进程；WSL 服务、虚拟机计算服务和 hns 正在运行。没有证据支持将手动启动类型的 `com.docker.service` 停止状态判定为原因。

Basic Memory 保存的 2026-10-12 恢复记录已记载相同端点错误和目录隔离方案。此次说明单次手动隔离没有消除复发条件。Docker 官方仓库的[同类问题讨论](https://github.com/docker/desktop-feedback/issues/460)还记录了正常关闭后复发、仅禁用模型功能无效，以及固定 `.stale` 名称冲突；这些是外部用户报告，本机修复判断以实际日志与操作为依据。

## 本次修改

在确认 Docker Desktop／后台进程不存在后，将两个临时运行目录改名保存，重建原目录并启动 Docker。使用精确路径的 `.NET Directory.Move`；本次 PowerShell provider 的 `Rename-Item` 对 secrets 目录出现改名后原路径仍存在的情况，因此没有继续依赖该调用。未改动镜像、卷、WSL 发行版、VHDX、WSL 资源设置或服务启动类型。日志中较早的界面 factory reset 操作不是本次代理执行的恢复动作，不能推断此前数据完整性。

新增 [`scripts/start_docker_desktop.ps1`](../../scripts/start_docker_desktop.ps1)，并安装至：

```text
C:/Users/wblxr/AppData/Local/DockerSafeStart/Start-DockerDesktop.ps1
```

桌面原有 `Docker Desktop.lnk` 已备份到该支持目录，并替换为调用此脚本；用户开始菜单也新增同名入口，图标沿用 Docker 图标。

脚本通过当前会话互斥锁合并同时点击。已有 Docker 进程时仅调用原程序打开界面。冷启动时仅接受两个明确目录中的已知、零字节 socket 重解析点；意外内容、目录重定向或并发启动会中止并给出错误，保存日志供人工检查。所有待处理目录先完成范围检查，再逐个改名；后缀包含时间与随机值，避免固定旧文件名冲突。旧目录保留、不递归删除。启动记录位于 `DockerSafeStart/launcher.log`。

## 实际端到端验证

使用本机已有 `pgvector/pgvector:pg16` 镜像，新建本任务独立 PostgreSQL 容器 `adrs-docker-recovery-20261020` 和同名命名卷，发布到 `127.0.0.1:15433`，禁用容器健康探针。既有业务容器未启动或修改。

从 Windows 上的真实 asyncpg 驱动通过发布端口连接数据库，创建 pgvector 扩展与证据表，事务提交 JSONB 证据和三维向量，再检索并核对提交状态及向量距离。之后正常停止整个 Docker Desktop，通过用户桌面的真实快捷方式启动，再启动同一数据库容器，从同一卷读取重启前提交的证据，并提交新的更新。场景同时覆盖运行中的重复启动入口和连续冷启动后的数据恢复。

第一轮真实快捷方式冷启动于 21:40:16 完成目录隔离，随后数据库证据读取与新事务提交通过。第二轮于 21:41:56 使用新的唯一目录名再次隔离，随后从同一卷读取原证据、第一轮更新和向量，提交并读回 `consecutive_restart_count=2`，通过。两个时间均为本机 UTC+8。专用容器和卷在场景完成后删除，Docker Desktop 保持运行。

未运行单元、回归、冒烟、健康或 lint/schema 门禁。数据库往返并不等于完整研究产品端到端已通过；MATCH.5 仍需真实业务迁移、归属与重排链路验证。

## 后续使用与限制

继续使用桌面或开始菜单中的 **Docker Desktop**。项目自动化可显式调用本机安装的脚本；直接运行 Docker 原程序或 `docker desktop start` 会绕过目录隔离。当前 Docker 的 `AutoStart` 为 false，本次未改变该偏好，也未新增登录任务或驻留服务。

这是经过本机实际重启与数据库操作验证的恢复入口，不能承诺未来升级、所有异常退出或机器重启场景。新增未知端点需要重新看首个致命日志再调整；不自动扩大处理范围。旧运行目录会累积少量目录项，当前保留备查；不要对 Docker 数据目录执行清理或恢复出厂设置。

移除本机绕行入口时，将支持目录中保存的原快捷方式复制回桌面，并删除本次新增的用户开始菜单快捷方式即可；无需修改 Docker 数据。
