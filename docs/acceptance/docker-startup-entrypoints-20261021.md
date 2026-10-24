# Docker 启动入口遗漏修复与实际数据恢复

2026-10-21，Windows 上 Docker Desktop 4.84.0、WSL2 后端。用户再次要求优先修复反复启动 error。本项修复本机启动路径，不推进组织研究功能编号；原有 OpenSpec 进度仍为 22/34。

## 原因和本次复现

此前修复了桌面和开始菜单入口，遗漏了两个路径：任务栏固定的 `Docker Desktop.lnk` 仍指向 `C:/Program Files/Docker/Docker/Docker Desktop.exe`；HKCU `Software/Microsoft/Windows/CurrentVersion/Run` 的 `Docker Desktop` 也仍指向原程序，而 Docker `settings-store.json` 的 `AutoStart` 是 false。

本次先在实际研究数据库提交一笔独立恢复证据，保存原报告及不可变匹配快照，然后正常关闭 Desktop，经真实任务栏快捷方式启动。12:14:03 本机时间的后台日志再次出现：

```text
backend crashed ... starting services: initializing Inference manager:
listening on unix://.../Docker/run/dockerInference:
remove .../Docker/run/dockerInference: The file cannot be accessed by the system.
```

数据库容器无法恢复，实际数据读取路径中断。缺失引擎连接是这个后台退出的结果。反复出现的事件流 EOF 并不单独证明同一故障；此次判断有上述新的致命日志和实际容器操作失败作为依据。

初次消费者脚本另遇到 Windows 默认 GBK 解码和容器恢复命令超时，随后明确 UTF-8 解码并处理单次命令超时。故障状态下的普通 `docker desktop stop` 也等待超时；仅对已经崩溃、尚未恢复工作负载的实例执行一次 `docker desktop stop --force --timeout 30` 关闭错误报告进程。没有将强制退出加入自动启动器，正常重启场景仍使用正常停止。

## 修改及本机应用

新增 [`install_docker_safe_start.ps1`](../../scripts/install_docker_safe_start.ps1)，复用原 [`start_docker_desktop.ps1`](../../scripts/start_docker_desktop.ps1)，没有增加常驻任务或另一套恢复器。

- 将桌面实际已知目录（含 OneDrive 重定向）、用户开始菜单及现有任务栏固定图标统一到本地修复脚本；沿用 Docker 图标。不存在固定图标时不新增。
- 根据 Docker 当前 `AutoStart=false` 移除冲突的遗留登录启动项，保持该偏好。安装器也实现 `true` 时使用修复入口，未额外切换用户设置验证该分支。
- 备份原快捷方式、启动脚本和注册表原值。无法识别登录命令或自动启动偏好时中止，不猜测设置。
- 继续只在 Docker 进程全部退出后保存两个已知 socket 运行目录；原有目录校验、范围限制和唯一后缀保持。镜像、卷、WSL 发行版和数据盘未清理。

本机备份目录：`C:/Users/wblxr/AppData/Local/DockerSafeStart/entrypoints-before-20261021-121456-777-ef06bc21`。这是机器本地备份，不能当成其他机器可用的仓库产物。

## 实际端到端结果

消费者 [`docker_recovery_e2e.py`](../../scripts/docker_recovery_e2e.py) 通过真实任务栏 `.lnk` 启动 Desktop，恢复本来运行中的两个 ADRS 验收容器；未启动其他项目的已停止容器。随后从 Windows asyncpg 驱动通过 `127.0.0.1:15434` 读取 PostgreSQL 中的原始研究报告和匹配 JSONB，完整比较业务内容，并提交、再次读取恢复记录的更新。

修复后命令：

```powershell
.venv/Scripts/python.exe scripts/docker_recovery_e2e.py --phase verify --cycles 2
```

命令退出 0。两次真实启动分别在 12:16:39、12:17:03 由启动日志记录了已知 socket 目录保存，均读取到重启前的原报告与原匹配证据，成功提交并读回 `restart_count=1`、`2`。

随后通过实际应用登录，读取原研究结果，状态仍为 `completed`，11,197 字符报告与重启前完整相同。机器本地产物 `application-result.json` 保存该次消费结果；没有用健康接口代替应用访问。

- 原研究：`871eae63-4ece-4832-a8e5-6885bc32593f`。
- 原证据快照：`f994b0c0-a866-490e-939d-3945b4b5b853`。
- 本次恢复事务：`3d64cea9-7ddb-4e0c-81bb-37c9e7bb6390`。
- 本地原始消费者产物：`.codex-homework/docker-startup-20261021/`；其中 `before.json` 是机器本地保存的业务内容，验证结果见该目录 `verify-result.json`。

未运行回归、冒烟、健康或构建门禁。未验证 Windows 整机重启、Docker 升级、自动启动开启分支或新未知端点；不将本机入口修复宣称为上游底层缺陷永久消失。重新固定图标或更新后可再次执行入口安装器。故障来源的既有外部讨论见[上一阶段记录](docker-startup-20261020.md)，此次结论依据本机实际复现与数据恢复。

## 16:01 再次核查与实际重启

用户再次要求优先处理启动 error 后，直接核对本机三个快捷方式：桌面实际路径、用户开始菜单和现有任务栏图标均指向 `DockerSafeStart/Start-DockerDesktop.ps1`，`AutoStart=false` 且 HKCU Run 的 Docker 项为空。版本仍为 4.84.0.234817。查到同类致命日志发生在 12:14 的入口修复之前；本次没有复现修复后同一启动崩溃，不能将历史日志当成新故障。

本次先确认没有 running／pending 研究，保存原报告与匹配快照，提交独立恢复记录；一条旧 paused／awaiting_approval 任务保持暂停。正常停止 Desktop 后，从真实任务栏快捷方式启动。15:59:57 启动器保存两个已知 socket 目录并启动后台。通过发布端口读回原报告和 JSONB，完整业务内容一致；恢复记录提交并读回 `restart_count=1`，暂停任务的状态和 review_status 比较一致。随后真实应用登录和原研究读取均返回 200，原报告仍为 completed、11,197 字符。

恢复事务：`235599a4-6b77-47bb-afa8-fab773e2738f`；本地产物：`.codex-homework/docker-followup-20261021T075939Z/before.json` 和 `result.json`。首轮消费者在成功重启及数据库比较后误用 API 的 `final_report` 字段而报 KeyError，API 实际字段是 `report`；修正消费字段后对同一次重启重新读取并完成验证，没有再重启或重复提交恢复事务。较早一次消费者因将 paused 视为运行任务而在重启之前退出，未改变该任务。

这次确认已安装的入口修复仍然生效，没有额外修改生产启动器或启动偏好。当前 OpenSpec 功能进度为 28/34；上文 22/34 为首次入口修复时的历史状态。整机重启后的自动启动、上游缺陷永久消除仍未验证。

## 19:59 优先恢复 Docker

用户再次要求先处理反复启动 error。本轮检查时 Docker Desktop 与后台进程已停止，后台最后日志时间为 18:22；现有材料不能确定停止原因，也没有显示此次新发生的同类 socket 致命错误。桌面、开始菜单与任务栏的实际快捷方式仍使用修复脚本，`AutoStart=false`，遗留登录启动项为空。没有把旧错误日志或事件流 `EOF` 当成新的启动崩溃。

19:59:36 通过实际任务栏快捷方式启动。启动器保留两个已知 socket 目录后启动 Desktop；随后 `docker start` 成功恢复原来的 PostgreSQL、Redis 两个 ADRS 容器。通过 PostgreSQL 发布端口读取原研究 `871eae63-4ece-4832-a8e5-6885bc32593f` 的完整报告和原匹配快照 `f994b0c0-a866-490e-939d-3945b4b5b853`，与此前保存的业务内容逐项比较一致，报告仍为 11,197 字符。独立恢复记录 `85d0c701-6ef0-49ac-9c83-543be7752252` 已提交并再次读回；本地产物为 `.codex-homework/docker-recovery-20261021T115936Z/result.json`。

本轮未修改启动器、快捷方式或自动启动偏好，也没有额外执行一次停机重启。结果证明现有修复入口此次可以启动 Docker 并恢复项目数据库使用，不能证明未知停止原因已经解决或上游缺陷永久消失。没有运行研究功能的新代码、回归、冒烟或门禁；这次启动与恢复操作仅对应用户明确提出的 Docker 修复范围。

## 21:43 启动入口和当前日志复核

本次读取当前进程、快捷方式、配置和日志，Docker Desktop 及后台进程的启动时间仍为 19:59:36—19:59:40；没有为核查而再次重启。桌面（实际 OneDrive 重定向目录）、开始菜单和任务栏三个既有快捷方式均指向 `DockerSafeStart/Start-DockerDesktop.ps1`。配置仍为 `AutoStart=false`，HKCU Run 中没有 Docker Desktop 项。

当前后台日志包含客户端取消事件订阅后产生的 `EOF`，这些日志不能单独作为启动失败的依据。本次所读日志未发现新的同类 socket 初始化致命错误；进程存在也不等于已经重新验证应用可用性。最近一次实际数据库恢复证据仍是上节 19:59 的结果，不将其计为本轮新执行。本轮没有更改启动脚本、清理数据、停止容器或运行项目功能检查。

## 23:49 当前启动状态与报错区分

用户再次要求优先处理启动 error，随后表示不清楚报错文字或发生时间。本轮直接读取当前进程、三个快捷方式、启动器日志、当前后台及两份本次运行的滚动日志、Electron 日志和容器清单。Desktop／后台仍为 19:59 启动的同一实例；ADRS PostgreSQL（15434）及 Redis（16380）均为 `Up 4 hours`。三个快捷方式继续使用已安装修复脚本；这些是当前运行状态与入口证据，不替代研究功能验收。

所读本次后台日志未发现新的 `backend crashed` 或已知 socket 初始化致命错误；最新 `event streamer: error: EOF` 紧跟 `request cancelled by client`。Electron 日志在 19:59 启动后有 `/store` 的 HTTP 403，这属于界面商店请求记录，现有材料不能把它等同于引擎启动失败，也不能确认用户看到的就是它。没有为推测原因修改账户、网络或商店设置。

已有修复当前仍生效，本轮没有新增启动器改动、重启、容器启停或数据清理。最近实际业务内容恢复证据仍为 19:59 的记录；没有把本轮状态读取写成新的端到端通过，也不声称未知历史退出原因已解决。
