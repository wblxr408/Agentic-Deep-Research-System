# 模型下载指南

## 概述

Agentic Deep Research System 使用两种类型的模型：

1. **云端 API 模型** - 通过 API 调用，无需本地下载
2. **本地模型** - 需要从 HuggingFace 下载到本地

## 云端 API 模型（无需下载）

### 支持的 LLM 提供商

| 提供商 | 模型示例 | API 类型 | 是否需要下载 |
|--------|----------|----------|--------------|
| **通义千问 (Qwen)** | `qwen-plus`, `qwen-turbo`, `qwen-max` | 云端 API | ❌ 无需 |
| **DeepSeek** | `deepseek-chat`, `deepseek-coder` | 云端 API | ❌ 无需 |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini` | 云端 API | ❌ 无需 |

### 配置方式
- 通过前端界面配置 API Key
- 模型通过 API 调用，不占用本地存储
- 支持运行时切换模型

## 本地模型（需要下载）

### 1. RAG 嵌入模型

**模型名称**: `BAAI/bge-zh-qwen2-int8`
- **用途**: 将文本转换为向量嵌入
- **大小**: 约 400MB-1GB
- **语言**: 中文优化
- **量化**: INT8 量化，内存效率高

**首次运行自动下载**:
```bash
# 首次运行时会自动从 HuggingFace 下载
python -c "from sentence_transformers import SentenceTransformer; model = SentenceTransformer('BAAI/bge-zh-qwen2-int8')"
```

### 2. RAG 重排序模型

**模型名称**: `BAAI/bge-reranker-v2-m3`
- **用途**: 对检索结果进行重排序
- **大小**: 约 300MB-500MB
- **类型**: Cross-encoder 模型

**首次运行自动下载**:
```bash
# 首次运行时会自动从 HuggingFace 下载
python -c "from transformers import AutoModelForSequenceClassification; model = AutoModelForSequenceClassification.from_pretrained('BAAI/bge-reranker-v2-m3')"
```

### 3. Playwright 浏览器

**组件**: Chromium 浏览器
- **用途**: Browser Agent 网页自动化
- **大小**: 约 150MB-200MB

**安装命令**:
```bash
# 安装 Playwright 和 Chromium
playwright install chromium
```

## 下载位置

### HuggingFace 模型缓存
- **默认路径**: `~/.cache/huggingface/hub/`
- **环境变量**: `HF_HOME` 可自定义路径
- **清理**: 可手动删除不需要的模型

### Playwright 浏览器
- **默认路径**: `~/.cache/ms-playwright/`
- **平台特定**: Windows/Linux/macOS 不同

## 首次部署步骤

### 1. 环境准备
```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 安装 Playwright 浏览器
playwright install chromium
```

### 2. 模型预下载（可选）
```bash
# 预下载 RAG 模型（避免首次运行时延迟）
python scripts/preload_models.py
```

### 3. 启动服务
```bash
# 首次启动时会自动下载缺失的模型
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 离线部署

### 方案 A：预下载所有模型
```bash
# 在有网络的环境中下载所有模型
python scripts/download_all_models.py

# 将模型缓存打包
tar -czf models.tar.gz ~/.cache/huggingface/hub/ ~/.cache/ms-playwright/

# 在离线环境中解压
tar -xzf models.tar.gz -C ~/
```

### 方案 B：使用本地模型路径
```bash
# 设置环境变量指向本地模型目录
export HF_HOME=/path/to/local/huggingface
export PLAYWRIGHT_BROWSERS_PATH=/path/to/local/playwright

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 模型更新

### 更新本地模型
```bash
# 删除旧模型缓存
rm -rf ~/.cache/huggingface/hub/models--BAAI--bge-zh-qwen2-int8/
rm -rf ~/.cache/huggingface/hub/models--BAAI--bge-reranker-v2-m3/

# 重启服务会自动下载最新版本
```

### 更新 Playwright
```bash
# 更新 Playwright 和浏览器
pip install --upgrade playwright
playwright install --force chromium
```

## 磁盘空间需求

| 组件 | 估计大小 | 备注 |
|------|----------|------|
| RAG 嵌入模型 | 400MB-1GB | 可配置为更小的模型 |
| RAG 重排序模型 | 300MB-500MB | 可选，可禁用 |
| Playwright Chromium | 150MB-200MB | 必需 |
| **总计** | **850MB-1.7GB** | 首次部署所需 |

## 优化建议

### 1. 使用更小的模型
```env
# .env 配置
RAG_EMBED_MODEL=BAAI/bge-small-zh-v1.5  # 更小的模型
RAG_RERANK_MODEL=BAAI/bge-reranker-base # 基础版
```

### 2. 禁用 RAG 重排序
```env
# 如果不需高质量排序，可禁用
RAG_RERANK_TOP_N=0
```

### 3. 共享模型缓存
```env
# 多实例共享同一模型缓存
HF_HOME=/shared/huggingface
PLAYWRIGHT_BROWSERS_PATH=/shared/playwright
```

## 故障排除

### 模型下载失败
```bash
# 检查网络连接
curl -I https://huggingface.co

# 设置代理
export HF_ENDPOINT=https://hf-mirror.com
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port
```

### 磁盘空间不足
```bash
# 清理旧模型
huggingface-cli delete-cache

# 使用符号链接到更大磁盘
ln -s /big-disk/.cache/huggingface ~/.cache/huggingface
```

### 内存不足
```env
# 使用 CPU 模式
RAG_RERANK_DEVICE=cpu

# 使用量化模型
RAG_EMBED_MODEL=BAAI/bge-zh-qwen2-int8  # 已量化
```

## 总结

- **LLM 模型**：无需下载，通过 API 使用
- **RAG 模型**：首次运行自动下载，可预下载
- **浏览器**：需要安装 Chromium
- **总大小**：约 1GB，可根据需求调整

建议在首次部署前预下载所有模型，避免运行时延迟。
