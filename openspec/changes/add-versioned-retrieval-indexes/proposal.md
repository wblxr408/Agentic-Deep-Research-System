# Proposal

## Why

OPT-05需要可发布和回滚的实际检索索引。当前默认在启动时建立固定IVF索引，没有样本／表示选择依据；词汇只用FTS分数，缺少真实倒排、查询范围统计和索引代际，重建及旧引用边界不清。

## What Changes

- 在现有PostgreSQL加入按来源／特征版本的词项倒排和文档统计，生成完整后原子发布head；重建／回滚请求幂等且受owner与预期版本约束。
- 以当前owner、分组、active来源和已发布代际计算BM25，缺特征旧资料保留FTS路径并显示口径；不把候选局部IDF当全库统计。
- 复用主键／B-Tree、FTS／JSONB GIN及时间／属性索引；父子关系采用已有原位邻接映射。向量按实际编码profile、owner和分组过滤后精确距离；当前未有规模／召回收益证据，停止新建默认IVF。
- 显式记录HNSW／Vamana／IVF／压缩／DiskANN／多向量的未采用原因和重选条件，无额外服务；既有物理索引和旧任务原文不删除。
- 新增本人索引状态、重建／回滚交互及ACI。全部TODO实现后统一端到端验收。

## Capabilities

### New Capabilities

- `versioned-retrieval-indexes`：原子发布的词项代际、授权范围统计、索引选择和本人生命周期操作。

### Modified Capabilities

无主规范修改，沿用当前来源、分块与特征契约。

## Impact

新增可增量初始化的PostgreSQL代际／倒排表和索引、普通索引管理函数；上传事务、RAG、本人管理API和资料详情。无后台训练／重编码、ANN服务、全库自动重建或新Agent，不执行迁移／验证。
