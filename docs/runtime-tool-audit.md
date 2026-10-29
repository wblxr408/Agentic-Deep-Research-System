# 运行审计的调用标识契约

2026-10-29。真实根1ac44639在取证阶段因tool_call_audit写入失败终止，6080 Token、根记账16次工具请求、0在途；两份原始PDF合计1,548,088字节保留，没有成果分析或报告。日志显示StringDataRightTruncationError，字段上限64字符；本人SSE完整历史进一步保留了本次未提交快照中的unknown-完整operation_id，实际72字符。不是根据异常文字推测全部列需要扩展。

`tool_handoff.accept_results`对超过结果租约或绑定不符的已开始操作，拒收证据并生成unknown-加完整operation_id；`db.execution_control`用相同身份保存保守收据。该操作标识是服务端绑定的完整身份，不能裁成UUID长度、截前64位或把错误记录删除。未知预留不是已验证网络账单，也不能当作免费请求。

**改动**：`app/db/connection.py`的启动建库和`app/db/migrate.py`的显式迁移都将tool_call_audit.call_id定义为TEXT；已有表以ALTER COLUMN无损扩展。原主键、调用字符串、owner／session关联、状态和用量保持。固定摘要字段仍按既有64字符格式存储，不为本次故障改动其他列。

**ACI**：这是原运行快照持久化的内部存储修订，不新增用户参数或接口。输入是可信执行器形成的工具调用历史与结果交接记录；输出仍是同一审计主键下的原记录。行锁、当前owner／execution、根收据、事务和过期结果拒收沿原控制点；原记录重放仍是同一call_id的upsert，不产生第二份调用身份。数据库异常仍按原失败路径处理，不静默跳过审计。部署使用原启动迁移，不手工改旧研究或删除其失败。

**设计引用**：复用既有全部11项适用性评估，当前采用A2ABreak基线v1.0的[A2AB-10《委派环路检测与全链预算》](</C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-10 委派环路检测与全链预算.md>)“工程解决方案”1／3，以及[A2AB-11《中断任务租约与有界资源回收》](</C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-11 中断任务租约与有界资源回收.md>)“工程解决方案”1／4。执行点为accept_results、tool_receipt、RuntimePersistence和两条建库路径：保留未知消费、原期限、完整关联身份及原子结果接纳。03／06的原归属与并发控制保持；01／02／04／05／07／08／09没有新增技能信任、身份、SSE出口、产物、Webhook、授权或委派面，沿原评估。这些是待项目验证的工程建议。

**证据边界**：本次故障来自完整真实研究；诊断读取了该根的日志、SSE历史、已存状态和故障表定义，没有将旧材料送入新函数重放。源码和调用链审阅后，下一次完整原问题研究观察未知记录的实际保存及后续完整交付，不另运行局部、回归、构建、类型、schema或探针。新库路径与并发边界未由源码或单条成功记录证明。
