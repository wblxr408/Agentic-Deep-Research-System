# OPT-05：索引选择、代际发布与范围统计

## 已编码稀疏／英文词形的代际发布（2026-10-27）

来源显式选择了本地学习稀疏或英文词形时，首次建索引与重建会分别建立实际模型token权重倒排和PostgreSQL词形倒排；原词面BM25倒排继续单独保存。稀疏Posting绑定owner、来源、片段、代际、模型profile及词表身份；查询端只有同一实际模型／词表表示才可比较。词形Posting绑定真实数据库配置身份，不与技术标识原词项混用。两者与词项代际在同一事务发布，关闭检索时当前head不再引用，切换回旧代前检查各类Posting数量；原文和旧报告不改写。

稀疏Top-K可能省略非零项，词形可能超过每片段或来源Posting上限，代际分别记录截断／省略；词形最多20万Posting，稀疏最多12万，不把缺失当作完整。索引操作只使用已保存真实特征，不运行模型。账号、来源和片段通过复合外键绑定，读取须再限制当前head、生命周期和实际查询范围；各倒排的查询交接、真实重建／回滚和隔离效果统一端到端验收。

## 多向量与图文的来源代际（2026-10-27）

配对模型的整体和token矩阵在首次发布来源索引之前，与来源和片段处于同一事务；每个代际确认全部片段、来源版本、特征profile及声明的模型配对身份，并记录实际尺寸和总字节。向量实体不随每次重建复制，而是通过当前owner、来源、片段和代际manifest定位。回滚前重新核对配对向量的范围和数量；关闭索引不使其参与检索。后续召回必须过滤当前生命周期及head，再执行配对查询和MaxSim，当前不声称ANN或Late Interaction搜索已接通。

本人完成实际原件图文编码后，当前来源若已启用检索，在同一事务生成新索引代际并纳入本版本有效图文特征；若为仅定位用途，特征保留但不自动打开检索。显式重建会纳入当前来源、模型及生命周期一致的图文向量；保留代际通过成员表引用具体图像操作，回滚前核对数量。编码结果保存时就记录当时的发布状态；详情另外显示它是否属于当前head。实际文本／图像查询和质量留到OPT-11及统一端到端。

HNSW、IVF、量化和磁盘图均是候选：当前没有经统一真实运行验证的目标规模、权限过滤后的召回和资源数据，也不具备训练聚类索引的代表性语料，因此继续采用有界范围精确筛选与原始float32，保留这些替代接口。官方[pgvector说明](https://github.com/pgvector/pgvector#hnsw)显示HNSW无需训练但构建及内存成本较高，IVFFlat依赖聚类，并列出维度和过滤行为；本项目配对模型token向量允许高达4096维且使用独立矩阵表，不能直接假定单向量HNSW覆盖该表示。后续依据实际规模、同权限范围的召回／耗时／内存与发布回滚结果决定，现不声称这些候选已运行或比较通过。

2026-10-21，代码／契约已接入，尚未执行迁移、索引构建、接口或查询。六项实施和最终验收在[OpenSpec](../openspec/changes/add-versioned-retrieval-indexes/tasks.md)分开记录；全部ORG／OPT／跨模块实现后统一端到端。本文不表示性能、召回或安全已经通过。

## 目标、职责与选型

`app/db/retrieval_indexes.py`复用现有PostgreSQL，提供普通索引数据函数和生命周期操作。04决定生成什么特征，05决定怎样保存和发布可查结构；11–13继续完善召回与融合／排序。当前已有规模不足以证明默认ANN／量化或另加服务的收益，因此采用明确范围的词项索引和可选精确向量。

| 子项 | 当前采用的结构／行为 | 未采用候选与重选条件 |
| --- | --- | --- |
| 05.1 精确 | UUID主键、owner／来源／分组／状态／版本B-Tree，直接原位定位 | 无需独立Hash索引；目前没有证明其收益的等值瓶颈 |
| 05.2 关键词 | 按owner＋term＋generation的真实Posting List及每代文档长度；保留FTS GIN／词项JSONB GIN回退 | 词项位置和正文仍在原来源，不在Posting中复制全文 |
| 05.3 加权稀疏 | TF倒排、当前授权范围DF／平均长度及BM25 | 这是词汇稀疏，不是学习稀疏；没有固定LSR模型／词表，不构建伪SPLADE索引 |
| 05.4 图型ANN | 默认未采用HNSW／Vamana，可选向量按过滤范围精确距离 | 当前未有真实规模、召回／延迟收益依据；达到实际场景目标瓶颈后重选，需考虑owner过滤和内存 |
| 05.5 聚类ANN | 停止新建默认固定lists的IVFFlat，保留既有物理索引 | IVF训练／lists／probes需数据和召回证据；IVF-PQ同样未选，不在空资料阶段默认训练 |
| 05.6 压缩量化 | 保存原向量及实际编码身份，没有额外PQ／OPQ／SQ | 没有证实容量瓶颈和可接受误差，不因模型名推断量化生效；以后同时比较误差和空间 |
| 05.7 磁盘ANN | 未采用DiskANN服务／磁盘图 | 当前没有超过内存／存储能力的已知规模，不增加部署与一致性成本 |
| 05.8 多向量 | 实际词项倒排可定位细粒度字面；未建立语义token／Late Interaction索引 | 04未选专用多向量编码，因此不把单向量或词面位置冒充该索引 |
| 05.9 属性 | JSONB GIN和当前owner／group／status／来源／版本B-Tree | Bitmap／Roaring Bitmap为候选，尚无需要独立表示和维护的测量依据 |
| 05.10 关系 | 原位父子和词典提及的有界邻接映射，按来源显式读取 | 不是已确认实体图；当前不建全局图数据库，真实关系多跳有需要时再选 |
| 05.11 时间 | owner＋创建时间、代际创建时间、来源解析版本和明确用户声明日期B-Tree | 不把正文日期当发表时间；分区需规模与保留策略依据，当前未采用 |
| 05.12 生命周期 | 同事务准备／发布、代际保留、预期版本与幂等操作、重建／关闭／回滚 | 已选词汇／精确方法无需模型训练；不自动重编码、压缩或删除旧代际。后台维护继续06／18 |
| 05.13 启用决定 | 用户主动资料接入可选direct／lexical；网上任务证据默认不建索引；稠密另有显式选择及服务器许可 | 不以改稿次数作为索引理由，不在查看原文时自动建索引；规模和召回缺口出现后再选更复杂结构 |

近似索引和其过滤语义参见[pgvector官方说明](https://github.com/pgvector/pgvector#filtering)：近似检索可在扫描之后过滤，可能影响受限范围的召回。当前精确路径先物化已授权且编码一致的ID／向量范围，再算距离，最后只读取top候选的正文／metadata；即使旧部署已有全局ANN，也不依赖该索引取得本次精确范围结果。这里没有实测性能比较。

## 存储及实际发布

沿用同一数据库，新增五张表，各自有直接用途：

| 表 | 责任 |
| --- | --- |
| `retrieval_index_generations` | 来源／特征／词项版本、实际覆盖、构建准备及指针切换前耗时；保留已发布／已退役代际 |
| `retrieval_index_documents` | 每代每小块长度和完整／截断状态，含零词项小块，用于N及平均长度 |
| `retrieval_index_terms` | 每代文档的规范词项和TF，唯一键约束每词每块只存一次 |
| `source_index_heads` | 每来源当前direct／lexical、可空generation_id和递增revision，决定后续检索 |
| `source_index_operations` | owner＋request_id绑定请求参数及该次结果，处理超时重试／重放 |

新来源选择lexical时，原文、计划、检索小块、所选嵌入及词项代际在原接入事务提交；不暴露半个来源。direct新来源保留原文／解析／分块／特征计划和直接定位head，不物化documents小块或Posting，也不编码。详情仍可按03原位读片段；之后显式建立词汇索引时才从冻结原位物化小块，继续不调用模型。direct与dense=true同时请求422，不为不参与检索的资料做编码。

关闭一个已有词汇来源时，切换head到direct，后续FTS／Posting／向量都排除它；既有小块／旧代际继续保留供回滚，关闭不等于物理清除。后续06负责完整生命周期及清理语义。源内原文和旧任务依据不会因关闭／重建而被替换。

构建核对实际parse／chunk／feature／tokenizer版本、逻辑块成员、原位及正文切片一致；词频必须为正整数且合计等于该块长度。最多4000块／20万Posting；限额按完整块省略并标partial，不能把缺口计为内容不存在。没有词项或不可用特征的情况与完整覆盖分别表达。

新代际和当前head同事务发布；旧代际标retired但不自动删除。重建失败回滚；旧head仍为这次失败操作之前的已提交状态。并发的其他合法操作仍可能改变状态，因此客户端不能只凭自己一次失败推断当前head。回滚目标必须仍保留、同owner／来源／解析／特征／tokenizer版本，并核对该代文档仍完整。

## 查询口径

Posting查询在一个SQL快照内，以当前owner、当前group、active来源、lexical head及其兼容代际建立候选全集，然后计算N、平均长度、查询词DF和BM25。该范围是已发布且有可用特征的小块，重叠小块分别计数；不是论文数量，也不把旧无代际资料算成已知完整词项语料。

项目的`owned_postings_bm25_v1`使用`k1=1.2`、`b=0.75`，每个规范查询词只计一次：

```text
IDF = ln(1 + (N - DF + 0.5) / (DF + 0.5))
score = Σ IDF × TF × (k1+1) / (TF + k1 × (1-b+b×length/max(avg_length,1)))
```

参数和IDF形式核对了[Apache Lucene BM25Similarity源码](https://github.com/apache/lucene/blob/main/lucene/core/src/java/org/apache/lucene/search/similarities/BM25Similarity.java)，项目使用自己的混合字面词项和范围定义，不声称与Lucene分词、位置折扣或整体分值完全一致。没有运行对拍或分数门禁。

旧来源缺代际时保留已有FTS／有词项metadata的回退，不追认已发布BM25。FTS／字面回退、Posting BM25及可选精确向量分别排名，再以RRF融合，缺少某通道不给该通道补分；原始FTS与BM25分值不直接相加。结果保留代际ID、实际范围N／平均长度／部分覆盖数量、各通道状态及分数作用于原命中块的说明，传入任务Evidence acquisition。父级扩展发生在排序之后，不把原块分数当作整段父级的相关性分。

向量只有在用户已生成、服务器启用、实际encoding_profile_id一致且当前head允许检索时参与。未知旧编码不猜，模型／向量查询不可用时保留词汇路径。默认无新增ANN／量化操作，也不删除已有物理索引。

## ACI与恢复

沿用已认证`/api/v1/documents`，owner来自认证主体，客户端不能指定owner。

| 操作 | 输入／输出与边界 |
| --- | --- |
| POST `/sources` | 既有请求加`index_policy={mode:direct或lexical,reason:...}`，默认lexical；配置进入接入幂等。返回实际`chunk_count`、`planned_chunk_count`和index选择／代际。direct实际检索块数为0 |
| POST `/upload` | 表单加`index_policy_json`（最多2000字符），同一契约；批次固定开始时的选择；来源和首次代际同事务提交 |
| GET `/sources/{id}/index` | 本人当前模式／head／revision、解析及特征版本、最近20代、更多标记和选型原因；`include_adjacency=true`显式附结构邻接（最多10000边）；只读不建索引 |
| POST `/sources/{id}/index/actions` | `action=rebuild|disable|activate`，request_id、expected_source_version、expected_feature_profile_id、expected_generation_id、expected_revision及activate的target_generation_id；变更当前本人来源索引，原文／模型不变 |

客户端先读取index状态，把返回的解析／特征／head／revision原样作为预期值提交，新旧来源的null／revision=0分别保留。activate必须有目标，其他动作不能传目标。版本或head冲突409并刷新；同request_id改变参数409；非本人／缺失404。旧来源没有兼容特征时rebuild返回409并说明显式重新接入，仍可disable旧检索。归档来源不能重建／启用，但可关闭。

服务端行锁最长等待3秒、单SQL最长30秒、显式生命周期操作总期限45秒；超时／数据库错误返回503，事务不发布该次操作。网络丢失或503后客户端保留同一个请求和预期参数，通过“用同一请求重试上一操作”确认结果；已有提交则返回原结果`replayed=true`，不会再建一代。不能因重试自身超时就换key重复操作，原请求可能仍在执行。没有后台恢复循环或新的常驻任务。

资料详情展示当前模式、覆盖、代际／时间和可回滚项，提供重建／启用、关闭、读当前状态及同源保留代际激活。loading、版本冲突、结果未确认及请求重放各自可见。结构邻接只表示章节／块和字典提及，不自动创建已确认合作／任职边，也不跟随引用URL。

## 初始化与旧资料

新表和精确／词项／属性／时间索引同时进入`app/db/connection.py`和`app/db/migrate.py`的可重复DDL。迁移为documents／document_sources补可空owner列，不猜测或绑定原无owner数据。新库向量列维度取已验证范围内的配置，已有列不隐式改维度。停止新建旧的固定IVF，已有索引和向量继续保留；默认精确查询不受其近似扫描影响。

没有自动回填旧来源／生成词项／重编码；旧视图显示无代际，历史模型结果和已完成报告不是本次新索引验证证据。普通metadata编辑保护index_policy；实际生效head以服务端表为准，初始选择和后续显式切换分别表达。

后续OPT-06的[当前版本与使用范围](evidence-lifecycle.md)现已接入代码、未迁移。除05条件，所有召回及BM25统计还检查任务／明确复用、有效期、当前版本与Tombstone；旧无记录资料只保留本人明确分组路径。head变化同步增加访问epoch，显式清理旧代际只处理retired、截止前且无head引用者，最多20个，清理后不可回滚到该代际。

重复接入除了匹配原配置，还核对当前生效的direct／lexical用途。已被关闭的旧索引不能被误报为此次请求的可检索表示；用途已变化时产生独立表示，不悄悄修改原来源head。接入结果根级representation记录本次实际编码调用／片段数和未知成本；index.effects只描述索引构建阶段，不能把其中embedding_calls=0理解为整个稠密接入没有编码。

迁移脚本去掉了仅列出表名的检查步骤；最后统一端到端将以真实来源接入、查询、事务／重放、回滚和旧报告访问效果判断，不能用表存在代替能力结果。本文列出的命令／API均未运行。

## 安全引用及剩余验证

依据A2ABreak基线v1.0，复用[全部11项适用性](OPTIMIZATION_TODO.md#安全方案引用与规划状态)，对应“工程解决方案／验收办法”的本次增量如下，均未验收：

| 方案 | 控制点及最终需覆盖场景 |
| --- | --- |
| [A2AB-03 上下文归属与跨租户隔离](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-03%20上下文归属与跨租户隔离.md) | 状态、代际、Posting、N／DF、邻接及动作先限定实际owner；跨owner知道ID不能读写或影响统计 |
| [A2AB-06 并发状态版本与审批绑定](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-06%20并发状态版本与审批绑定.md) | 来源行锁、预期parse／feature／generation／revision、原子head、owner＋request_id参数绑定；迟到、ABA、重复与失败不能多发布或覆盖新状态 |
| [A2AB-08 结构化授权请求与权限不放大](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-08%20结构化授权请求与权限不放大.md) | 直接定位／关闭来源不被其他通道召回，当前组／active继续复核，模型或索引选择不扩大权限 |
| [A2AB-10 委派环路检测与全链预算](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-10%20委派环路检测与全链预算.md) | 无模型或新委派调用，块数／Posting／邻接及请求期限有界；最终检查实际消耗与范围 |
| [A2AB-11 中断任务租约与有界资源回收](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-11%20中断任务租约与有界资源回收.md) | 本增量仅借鉴有限deadline与事务取消回收；没有等待输入／授权的索引任务或新后台worker，因此不新增中断租约调度器。检查超时回滚与结果未知后的同请求重试 |

其余编号沿既有无新Card、Webhook、远程凭据／委派或独立产物流的结构性判断。上述是来源核对后的本地工程方案，不是官方修复保证。当前只做源码和一致性审阅；未执行模型、API、迁移、索引、SQL查询、性能比较、构建／lint／schema门禁或任何测试。下一OPT-06生命周期与范围传播，全部TODO实现后统一端到端。
