# OPT-04：同源特征视图与编码成本

2026-10-21，代码／契约已接入，尚未运行。实施任务和最后验收见[OpenSpec](../openspec/changes/add-versioned-retrieval-features/tasks.md)。按用户要求，全部ORG／OPT／跨模块实现之后统一端到端，不先行安装模型、调用新接口或执行测试／门禁。

## 目标、现状与选择

此前上传总是生成嵌入，RAG在全文查询前依赖嵌入器；没有实际表示版本。新增`app/retrieval_features.py`普通函数，以同一解析／分块版本生成词汇、实体／时间、模态覆盖及稠密表示记录。来源保留完整计划，小块只带自己的特征。任务内网上证据仍不自动向量化。特征表示属于OPT-04，实际索引算法／发布属于OPT-05，查询排序／融合属于OPT-11–13。

| 子项 | 当前实现／决定 | 候选、成本及重新考虑条件 |
| --- | --- | --- |
| 04.1 词汇 | Unicode NFKC／casefold规范词项与原始位置分别保存；英文／技术标识、中文单字／相邻二元组可选；复用03实体词典；可选派生PostgreSQL英文词形 | 默认关闭派生视图，原文词项始终单独保留。实际跨来源词形检索接到OPT-05／11；实体词典不声称NER消歧质量 |
| 04.2 相关性 | 小块TF、源内DF、平滑IDF及归一TF-IDF，保留N、平均长度、覆盖及重叠口径 | 当前PostgreSQL `ts_rank`不是BM25；跨源BM25必须用当前授权查询范围统计，不能直接比较各来源局部IDF |
| 04.3 学习稀疏 | 本人可选固定版本本地SPLADE模型，保存实际词表token权重与输入覆盖 | 默认关闭；Top-K截断明确记录；稀疏索引／召回由OPT-05／11继续接入，不把TF-IDF改名为SPLADE |
| 04.4 稠密 | 新接入默认关闭，可选现有单向量或显式配对的查询／文档编码器；保存实际归一整体向量与模型身份 | 不新建双塔训练；共享空间由部署者声明，维度相同不证明兼容。后续接入实际查询、索引和质量验收 |
| 04.5 细粒度 | 可选保存实际token矩阵、有效位置和来源偏移，另存整体向量 | 不把通用token向量宣称为经过ColBERT训练；MaxSim和候选索引在后续OPT-05／11接续 |
| 04.6 行为 | 当前缺少适当授权曝光／点击／用户历史及训练目标，未采用协同过滤、Item2Vec、序列模型／行为双塔 | 不自动收集新行为。已有工具轨迹是执行记录，不能当兴趣标签；跨任务不同主题不预设稳定偏好 |
| 04.7 BSR | 用户确认Beam Search Retrieval；选择以授权资料结构和有来源的提及为图边 | 有界束搜索属于召回而非表示，实际执行、路径及资源上限在11.16实现；提及不等于已确认实体关系 |
| 04.8 实体 | 复用字典提及、来源／偏移、分类及已知字段；身份消歧和确认关系保持独立 | 模型NER／关系抽取没有收益证据，不默认调用。机构／人员／地点共现不产生合作／任职事实；已有组织关系模块继续按来源审核 |
| 04.9 模态 | 文字／结构独立视图；用户可提供同一版PDF或DOCX原件，选真实页面或内嵌图片生成本地图文表示 | 独立保存图片及有原文位置的文本窗口；没有文本则只编码图像，不跟随资源URL。图文索引和跨模态召回在OPT-05／11接续 |
| 04.10 时序 | 显式来源日期、as_of、窗口及半衰期，保存推导依据；未来／未知日期不产生虚假新鲜度 | 来源日期为用户声明而非自动核实，不从正文日期猜发表时间；研究趋势仍用组织趋势模块的跨年同口径证据 |

上述候选取舍遵循主TODO开头的“候选不代表全部选用”。未采用不是运行成功；后续若选择这些模型，需要新的数据／模型／索引及真实场景证据。

## 显式学习稀疏编码（2026-10-27，源码已接入）

资料接入可选择“生成学习稀疏特征”。部署者预先设置 `RAG_SPARSE_MODEL` 为经过SPLADE训练的模型仓库标识、`RAG_SPARSE_REVISION` 为完整40位提交；模型与tokenizer必须已存在本机缓存，不自动下载，且权重必须有 `safetensors`。`RAG_SPARSE_MAX_INPUT_TOKENS` 默认256、`RAG_SPARSE_TOP_K` 默认128，均可在服务端配置。调用不执行仓库远程代码，实际权重由本机受信任管理员准备；声明模型经过SPLADE训练是部署者责任，不从普通Masked-LM结构推断训练质量。

每份来源最多200个小块、120秒，逐块检查实际token长度；任何片段超出或模型不可用时不提交不完整表示。使用模型logits、注意力掩码及max池化的 `log1p(relu())` 产生真实非负词表权重，按Top-K保留并标注是否省略了非零项，模型、提交、实际词表身份和池化进入feature profile。实现参考 [SPLADE作者实现](https://github.com/naver/splade/blob/main/splade/models/transformer_rep.py)，没有将TF-IDF或词面标记改称学习稀疏。来源中的这份表示当前供特征详情读取；其加权倒排、查询编码与检索仍须OPT-05／11接续，最终质量和资源占用待完整真实端到端。重复提交可能在版本去重前再次发生本地编码；不会自动调用外部模型API。

## 可选英文词形（2026-10-27，源码已接入）

资料接入可选择派生英文词形，使用当前数据库 `pg_catalog.english` 全文检索配置对每个小块生成lexeme集合，记录配置、数据库版本及每块最多1024项后的覆盖；只新增视图，不改变精确词项和原文偏移。该配置可能包含停用词和其他字典规则，不把它描述成逐词一一映射或适用于所有学科语言的万能词干器；技术标识仍使用保留的原始词项。数据库通常采用英文词干字典，具体处理取决于实际配置，参见 [PostgreSQL文本检索配置](https://www.postgresql.org/docs/current/textsearch-configuration.html)。词形视图的查询及索引交接后续完成，是否改善真实查询需完整端到端。

## 显式配对及细粒度向量（2026-10-27，源码已接入）

用户可在接入资料时选择细粒度语义。部署者设置 `RAG_MULTIVECTOR_DOCUMENT_MODEL`、`RAG_MULTIVECTOR_DOCUMENT_REVISION`、`RAG_MULTIVECTOR_QUERY_MODEL`、`RAG_MULTIVECTOR_QUERY_REVISION`、`RAG_MULTIVECTOR_SPACE`；两端仓库须使用本机缓存的完整40位提交及safetensors权重，可选的 `RAG_MULTIVECTOR_DOCUMENT_PREFIX`／`RAG_MULTIVECTOR_QUERY_PREFIX` 明确配对模型的输入前缀。空间名称是部署者声明，不凭相同维度认定模型可比较。默认不运行、不下载模型。

编码使用 [Sentence Transformers v3 的实际token输出](https://github.com/huggingface/sentence-transformers/blob/v3.0.0/sentence_transformers/SentenceTransformer.py)；一次模型前向同时得到每个token和整体向量，再逐向量L2归一，使用fast tokenizer的原文偏移，并将token id与模型输入实际比较。特殊token／前缀位置标记为空、不会当作原文位置；不支持可靠对齐或模型输入超长则拒绝整次接入。每次最多200块、默认256 token／块、180秒和12 MiB向量；二进制float32矩阵与位置按owner、资料版本和实际片段存在数据库，原文及历史报告不回写。数据库外键要求资料、片段、账号一致；源删除时向量随片段清理。对应A2ABreak v1.0 A2AB-03《上下文归属与跨租户隔离》与A2AB-11《中断任务租约与有界资源回收》的工程约束，完整双账号、版本和超限验证仍待统一端到端。

查询侧编码函数和两端配对身份已准备，尚未调用或提供多向量检索。后续要在授权索引内排除非原文token、校验模型配对及维度，才能执行实际MaxSim；模型本身是否经过该目标训练、是否带来质量收益也需另行验证。同步来源不会私自重新运行该模型，需本人手动更新。

## 原件图文表示（2026-10-27，源码已接入）

在资料的页面／图片理解区域，选择同版本原始PDF页面或DOCX内嵌图片后，可单独生成本地图文特征。服务端配置 `RAG_MULTIMODAL_MODEL` 与 `RAG_MULTIMODAL_REVISION`，要求本地缓存的完整40位提交、可信safetensors权重和可提供原文位置的fast tokenizer；默认不自动下载或编码。图像通过既有有界渲染器从本人原件取得，PDF页面使用该页解析原文，DOCX图片使用其已关联结构块；没有关联文字就只编码图像。

使用同一CLIP模型的 [图像和文本投影接口](https://huggingface.co/docs/transformers/v4.40.2/en/model_doc/clip)，分别保存真实L2归一向量。文字最多取该来源区间前16000字符、最多8个模型文本窗口，记录所有窗口数、实际编码数量和原文绝对偏移；图像记录渲染尺寸和输入身份，避免将缩略图称为原图字节。输出随操作、来源版本和账号存入独立表，来源或账号删除时级联清理，原始图片及历史报告不改写。详情显示实际已编码项目；索引和文本查图／图查文尚未发布。

操作遵循A2ABreak v1.0 A2AB-03《上下文归属与跨租户隔离》、A2AB-06《并发状态版本与审批绑定》与A2AB-11《中断任务租约与有界资源回收》：先核验原件与版本、限制本人并发和期限，写入前重核当前权限／生命周期／模型，取消或失效不发布结果。取消后本地子进程最多运行至自身时限；并发、多账号、超限及召回效果均留待最终真实端到端。

## 行为数据与BSR口径（2026-10-27）

当前源码中的 `research_quality_feedback` 是任务质量反馈，并非授权的用户—文献曝光／点击序列。再次在线查阅指定仓库当前 [YouTubeDNN 数据构造](https://github.com/zhongqiangwu960812/AI-RecommenderSystem/blob/master/Recall/YoutubeDNN/utils.py) 和 [UserCF 实现](https://github.com/zhongqiangwu960812/AI-RecommenderSystem/blob/master/Recall/CollaborativeFiltering/CF_For_NewsRec/CFModel.py)：前者使用按时间排序的用户／文章历史，后者使用用户、文章及观看时长；当前资料不足以把它们当成已有训练数据或直接引入推荐器。确有明确推荐目标及授权数据后再选模型，当前不新增行为采集。

用户已确认BSR是Beam Search Retrieval：每轮只保留评分最高的一定数量候选、有限轮扩展，避免所有路径组合无限增长；可参考原论文的 [BSR方法](https://opus.lib.uts.edu.au/bitstream/10453/183299/2/Towards%20Linguistic%20Neural%20Representation%20Learning%20and%20Sentence%20Retrieval%20from%20Electroencephalogram%20Recordings.pdf)。本项目拟以当前用户、任务、有效期可访问的来源片段为种子，沿真实的父子结构与字典提及关系扩展，以查询相关性排序，并输出真实路径、截断与预算；不推断合作或任职关系，不把其他用户资料纳入搜索。其输入、状态及回退在召回模块实现；当前尚无已完成的BSR召回。

后续OPT-05的[真实Posting与范围BM25](versioned-retrieval-indexes.md)现已接入代码、未迁移；FTS `ts_rank`仍是单独回退，不能把它计作BM25。新增direct选择不物化关键词小块，之后显式发布才建立检索代际。

## 生成契约、统计与位置

`FeaturePolicy`版本为`adrs-retrieval-features-v1`，词项策略为`adrs-mixed-literal-v1`：

| 字段 | 默认及边界 |
| --- | --- |
| `dense` | false；仅在用户选择后生成嵌入 |
| `cjk_mode` | both；可选characters／bigrams。单字符／二元组为规则词项，不宣称语言学分词 |
| `max_token_events` | 1024／块，可选128–2048；达到上限显示截断，不代表词项在后文不存在 |
| `source_date`／`as_of` | 默认null；声明来源日期时必须同时声明计算时点 |
| `half_life_days` | 730，可选30–3650；`2^(-age_days/half_life_days)`为产品规则 |
| `window_start`／`window_end` | 可空，拒绝倒置；仅对明确日期判断in_window |

每个规范词项保留TF和最多两个实际原文字面位置；词项最长128字符，超长值省略有计数。位置为Python Unicode字符，起点含、终点不含；NFKC及casefold可能改变词项长度，不能用规范词项长度重建原位置。中文与英文连续出现时分别切分，技术字面如C++／C#后缀保留。

源内IDF为`log((N+1)/(df+1))+1`，TF为`1+log(count)`，最后L2归一。N是本来源实际保留特征的小块数量，重叠小块分别计数；不是全文全集、跨库文档数或论文数量。该局部权重用于解释该表示，后续全库排序需要重新取得相应授权范围统计。没有词项时权重为空而非造分。

源特征计划上限8MiB；包括词项位置／TF-IDF和统计的最终表示超限时，保留逻辑块、版本、范围及明确的省略状态。中间预算变化会使旧IDF cohort失效，因此省略旧权重，不保留陈旧权重。若整体预算必须省略全部词汇增强，token_count／平均长度为未知，document_count指可用特征数为0，total_chunk_count仍保留，不能解释为资料没有内容。来源正文和03原位置计划继续保留。

## 稠密编码与独立词汇检索

上传选择dense时先检查服务端`RAG_EMBED_REVISION`是40位模型提交ID；不自动填写未知提交。沿用配置模型的`SentenceTransformer.encode`、L2归一，禁止远程自定义代码。实际编码后保存模型引用、请求revision、维度、SentenceTransformers／Transformers／Torch库版本、序列token上限、默认prompt名／摘要及编码profile_id。不从仓库名中的`int8`推断量化已生效，也不把未观测的运行commit另造为已核值。

每块记录含默认prompt的输入token数、模型上限及截断／未知。该覆盖是编码器输入边界，不是PDF页码或原文的精确截断重映射。向量数量、维度、finite及L2范数不成立则502且不提交来源；不补零／截断向量。相同owner／组／原资料、解析／分块／特征策略与声明编码配置复用已提交表示；修改词项／时间／编码配置形成独立表示，旧任务不改写。

默认检索只用当前owner／组／active来源的全文和已存词项；不加载嵌入或重排模型。服务端可分别设置`RAG_ENABLE_DENSE_RETRIEVAL=true`及`RAG_ENABLE_RERANKER=true`。稠密查询只取实际encoding_profile_id相同的向量，模型或向量查询不可用保留词汇路径。词汇、稠密和重排的实际通道状态附结果及节点记录；空结果不能用来推断模型已可用。最终空结果／错误的产品展示继续由后续查询执行模块完善。

复核现有可选重排调用时发现旧实现先排序分数再与原文顺序配对，会把分数分给另一段文字。现已改为输入顺序的一文一分，消费方绑定ID后排序；单logit经sigmoid，形状／finite／数量异常保留融合顺序。该修复没有新模型调用证据，质量和预算归集仍待OPT-13／18及最后统一端到端。

## ACI与交互

资料管理为三种接入方式共用特征设置：稠密选择、中文词项、上限和可选日期／窗口。批次固定开始时的配置。来源详情可看词项／位置、统计口径、编码／时间／模态、未采用原因和完整JSON；只读展示不触发模型。

| 操作 | 输入／输出及边界 |
| --- | --- |
| POST `/api/v1/documents/sources` | 既有请求加`feature_policy`；未知字段／非法日期或窗口422，缺少固定模型revision时409。默认不编码 |
| POST `/api/v1/documents/upload` | 表单加`feature_policy_json`（最多4000字符），同一FeaturePolicy；无效JSON422，编码失败502且事务不提交；取消稠密或配置模型后可显式重试 |
| GET `/api/v1/documents/sources/{id}/features` | 按实际认证owner读既有计划，页面最多20个块，`include_chunks=true`完整下载；旧无计划legacy_gap，不自动追认。来源版本冲突409，非本人／缺失404 |
| RAG／`knowledge_base_search` | 保留原参数与有限父级，增加实际通道状态、特征profile／实际编码／时间依据；主流程Evidence acquisition沿用这些引用。没有自动训练、图像出站或跨任务搜索 |

`feature_plan`、`feature_profile`和`dense_profile`为服务器管理字段，普通metadata编辑不能改写；和接入事务／幂等绑定。来源及向量查询当前owner、组、状态继续是权威；特征不构成授权。

资料列表显式使用`GET /sources?summary=true`，只取编辑需要的普通metadata和版本信息，省略正文及完整解析／分块／特征计划，避免每次列出所有资料就传输多份大对象。原API未指定summary时保留既有完整读取；各详情API按owner读取对应计划。

## 参考与选型依据

- [SentenceTransformer API](https://sbert.net/docs/package_reference/sentence_transformer/model.html)：当前文档支持revision、一般encode和查询／文档专用接口。项目继续用已有版本通用encode并记录身份，不假定依赖下限版本已经具有全部新API。
- [SPLADE作者仓库](https://github.com/naver/splade)：学习稀疏与词面TF-IDF分别表达；这里仅用于候选方法核对。
- [ColBERT作者仓库](https://github.com/stanford-futuredata/ColBERT)：token矩阵和MaxSim与当前单向量、词项位置的区别。
- 用户指定[AI-RecommenderSystem的YoutubeDNN实际输入代码](https://github.com/zhongqiangwu960812/AI-RecommenderSystem/blob/master/Recall/YoutubeDNN/utils.py)已按需在线读取：依赖user_id、article_id、expo_time、历史序列及负采样，不能直接用于当前任务证据；[协同过滤实现定位](https://github.com/zhongqiangwu960812/AI-RecommenderSystem/blob/9b64f48f14076ad8e84d8472379dbff54ac2c220/Recall/CollaborativeFiltering/CF_For_NewsRec/CFModel.py)同样以历史点击为输入。未克隆、下载训练集、复制实现或运行推荐模型。前两次浏览器获取仓库目录失败，随后通过GitHub连接器实际读代码；不是凭目录名作数据适配结论。

这些资料说明方法与API，不构成项目效果证据。

## 安全引用与实施状态

复用A2ABreak v1.0 [11项适用性](OPTIMIZATION_TODO.md#安全方案引用与规划状态)，本次采用以下条目的“工程解决方案／验收办法”，均待项目统一端到端：

| 方案 | 执行点及需验行为 |
| --- | --- |
| [A2AB-03 上下文归属与跨租户隔离](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-03%20上下文归属与跨租户隔离.md) | 特征API和检索绑定数据库owner；B知道A来源ID不能读取词项／编码信息 |
| [A2AB-06 并发状态版本与审批绑定](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-06%20并发状态版本与审批绑定.md) | 特征配置进入接入幂等／事务，重试不重复编码提交；版本变化生成独立表示 |
| [A2AB-08 结构化授权请求与权限不放大](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-08%20结构化授权请求与权限不放大.md) | 请求策略不能扩大来源／owner／模型执行权限；图像指针不自动出站 |
| [A2AB-10 委派环路检测与全链预算](C:/Users/wblxr/basic-memory/engineering/security/a2abreak/solutions/A2AB-10%20委派环路检测与全链预算.md) | 无新增Agent／训练循环，词项及元数据有界，模型编码需显式选择；研究总预算沿用，完整辅助调用成本归集继续OPT-18 |

没有新增Card、Webhook、远程凭据／委派、独立分块协议或流；其余编号沿原评估。本轮仅源码与契约审阅，无解析／编码／上传／查询实跑或非端到端检查。下一OPT-05，全部实现后统一检查真实词项、成本选择、实际编码／不兼容拒绝、独立词汇路径、权限和日期／模态未知。
