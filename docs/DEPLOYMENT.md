# Agentic Deep Research System 部署文档

> 版本：v1.0 | 日期：2026-05-12

## 目录

1. [系统要求](#1-系统要求)
2. [环境变量配置](#2-环境变量配置)
3. [本地开发部署](#3-本地开发部署)
4. [Docker 部署](#4-docker-部署)
5. [生产环境部署](#5-生产环境部署)
6. [数据库配置](#6-数据库配置)
7. [监控与日志](#7-监控与日志)
8. [故障排查](#8-故障排查)

---

## 1. 系统要求

### 1.1 硬件要求

| 组件 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核+ |
| 内存 | 4 GB | 8 GB+ |
| 存储 | 20 GB SSD | 50 GB SSD |
| 网络 | 10 Mbps | 100 Mbps |

### 1.2 软件要求

| 软件 | 版本要求 |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 15+ (with pgvector extension) |
| Redis | 7+ |
| Docker | 24+ |
| Docker Compose | 2.20+ |

### 1.3 外部依赖

| 服务 | 用途 | 备注 |
|------|------|------|
| LLM API | Qwen / DeepSeek / OpenAI | 需要 API Key，无需本地下载 |
| HuggingFace | 可选内部资料模型 | 显式选择稠密／重排时才需要模型；默认词汇接入与检索不下载模型 |
| DuckDuckGo | 搜索服务 | 免费，无需 API Key |

### 1.4 模型下载需求

| 模型类型 | 模型名称 | 大小 | 下载方式 | 是否必需 |
|----------|----------|------|----------|----------|
| 内部资料嵌入模型 | 配置的SentenceTransformer模型 | 随模型／精度而定，未实测 | 显式启用后加载，新的稠密表示需固定模型提交 | 可选；默认词汇接入／检索无需模型 |
| 内部资料重排序模型 | 配置的交叉编码器 | 随模型／精度而定，未实测 | 服务器显式启用后加载 | 可选，不可用时保留融合顺序 |
| Playwright 浏览器 | Chromium | 150MB-200MB | `playwright install chromium` | ✅ 必需 |

总磁盘需求需按实际模型／容器／浏览器测量，不从模型名称中的int8推断精度或容量。公开研究默认联网且不启用内部检索；词汇资料接入和检索不要求加载模型。PostgreSQL仍承担会话、引用与配置。OPT-04新代码的选择与配置见[特征契约](versioned-retrieval-features.md)，尚未安装／实跑，全部TODO实施后统一端到端。

---

## 2. 环境变量配置

### 2.1 创建环境变量文件

```bash
cp .env.example .env
```

### 2.2 必需配置项

```bash
# ===== LLM 配置 =====
LLM_PROVIDER=qwen                    # qwen | deepseek | openai
LLM_MODEL=qwen-plus                  # 模型名称
LLM_API_KEY=your-api-key-here        # API Key
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1  # API Base URL

# ===== 数据库配置 =====
DATABASE_URL=postgresql://user:password@localhost:5432/deepintel
REDIS_URL=redis://localhost:6379/0

# ===== 安全配置 =====
SECRET_KEY=your-secret-key-here      # 用于 session 加密
```

### 2.3 可选配置项

```bash
# ===== 浏览器配置 =====
BROWSER_HEADLESS=true                # 生产环境必须为 true
BROWSER_POOL_SIZE=3                  # 浏览器池大小
BROWSER_NAVIGATION_TIMEOUT=30000     # 导航超时(ms)

# ===== RAG 配置 =====
RAG_EMBED_MODEL=BAAI/bge-zh-qwen2-int8 # 按实际选定模型配置，不保证此名称已可用
# RAG_EMBED_REVISION=<实际40位模型提交ID>  # 选择稠密编码时必填，不填猜测值
RAG_ENABLE_DENSE_RETRIEVAL=false      # 默认只用独立词汇路径
RAG_ENABLE_RERANKER=false            # 与稠密分别选择
RAG_RERANK_MODEL=BAAI/bge-reranker-v2-m3
RAG_RETRIEVAL_TOP_K=20

# ===== 工作流配置 =====
MAX_REVISIONS=3                      # 最大重规划次数
SESSION_TTL=3600                     # 会话超时(秒)

# ===== 日志配置 =====
LOG_LEVEL=INFO                       # DEBUG | INFO | WARNING | ERROR
```

---

## 3. 本地开发部署

### 3.1 克隆项目

```bash
git clone https://github.com/your-org/deepintel.git
cd deepintel
```

### 3.2 后端设置

```bash
# 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements-local.txt

# 安装 Playwright 浏览器
playwright install chromium

# 预下载本地模型（可选，避免首次运行时延迟）
python scripts/preload_models.py

# 初始化数据库
python -m app.db.migrate

# 启动后端
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3.3 前端设置

```bash
cd frontend

# 安装依赖
npm install

# 开发模式启动
npm run dev

# 生产构建
npm run build
```

### 3.4 验证部署

```bash
# 健康检查
curl http://localhost:8000/health

# 预期响应
{"status": "healthy", "version": "1.0.0"}
```

---

## 4. Docker 部署

### 4.1 使用 Docker Compose（推荐）

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### 4.2 Windows 本机启动

```powershell
.\start-deepintel.ps1 -Mode local

脚本会优先使用项目内 `.venv`，不存在时自动创建并安装依赖。
```

可选参数：

```powershell
.\start-deepintel.ps1 -Mode local -SkipFrontend
.\start-deepintel.ps1 -Mode local -SkipDbChecks
```

### 4.3 服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose 架构                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐  │
│   │   Nginx     │────▶│   Frontend  │     │   Backend   │  │
│   │   :80/443   │     │   React     │     │   FastAPI   │  │
│   └─────────────┘     └─────────────┘     └──────┬──────┘  │
│                                                   │         │
│                              ┌────────────────────┼──────┐  │
│                              │                    │      │  │
│                         ┌────▼────┐         ┌────▼────┐ │  │
│                         │  Redis  │         │ PostgreSQL│ │  │
│                         │  :6379  │         │  :5432   │ │  │
│                         └─────────┘         └──────────┘ │  │
│                                                         │  │
└─────────────────────────────────────────────────────────────┘
```

### 4.4 单独构建镜像

```bash
# 后端镜像
docker build -t deepintel-backend:latest .

# 前端镜像
docker build -t deepintel-frontend:latest ./frontend
```

---

## 5. 生产环境部署

### 5.1 部署检查清单

- [ ] 环境变量已正确配置
- [ ] 数据库已创建并启用 pgvector 扩展
- [ ] Redis 已启动并配置密码
- [ ] SSL 证书已配置（HTTPS）
- [ ] LLM API Key 已配置且有效
- [ ] 日志目录已创建
- [ ] 防火墙规则已配置

### 5.2 数据库初始化

```sql
-- 创建数据库
CREATE DATABASE deepintel;

-- 连接数据库
\c deepintel

-- 启用 pgvector 扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 启用全文搜索
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 创建表（由 migrate.py 自动执行）
```

### 5.3 Nginx 配置示例

```nginx
upstream backend {
    server backend:8000;
}

upstream frontend {
    server frontend:3000;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # 前端
    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # 后端 API
    location /api/ {
        proxy_pass http://backend/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;  # 长时间运行的请求
    }

    # SSE 流式输出
    location /api/research/stream {
        proxy_pass http://backend/api/research/stream;
        proxy_http_version 1.1;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        proxy_read_timeout 86400s;
    }
}
```

### 5.4 Systemd 服务配置

```ini
# /etc/systemd/system/deepintel-backend.service
[Unit]
Description=DeepIntel Backend API
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=deepintel
WorkingDirectory=/opt/deepintel
Environment="PATH=/opt/deepintel/venv/bin"
ExecStart=/opt/deepintel/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# 启用服务
sudo systemctl enable deepintel-backend
sudo systemctl start deepintel-backend
```

---

## 6. 数据库配置

### 6.1 PostgreSQL 优化

```sql
-- postgresql.conf 优化参数
shared_buffers = 256MB
work_mem = 64MB
maintenance_work_mem = 128MB
effective_cache_size = 768MB

-- 索引DDL由app/db/retrieval_indexes.py和既有初始化统一维护。
-- 当前不默认新建IVF；词项Posting、FTS/JSONB GIN与owner/来源B-Tree分别承担查询。
-- FTS使用实际支持配置，不能假定已有名为chinese的配置。
```

OPT-05的[代际／重建／回滚](versioned-retrieval-indexes.md)已接入代码，尚未迁移。仅直接定位的新资料不物化关键词小块；显式建立才发布代际。已有索引／向量和旧资料不自动清理或重建；向量默认在过滤后的兼容范围精确计算。全部TODO实现后才统一端到端，当前不运行部署或索引效果检查。

OPT-06的[生命周期](evidence-lifecycle.md)同样尚未迁移：初始化增加版本族／访问策略、幂等事件和owner epoch表；原DELETE改为Tombstone，显式purge才清理非当前来源。新上传默认task范围，未绑定任务仅本人定位；要供研究复用，需绑定实际本人任务或明确选择group／owner。旧无生命周期来源仅保留本人显式分组路径，不自动认领旧owner。没有自动资料回填、后台清理、重训或服务重启；全部实施后统一通过实际业务确认。

### 6.2 连接池配置

```python
# app/db/connection.py
DATABASE_POOL_CONFIG = {
    "min_size": 2,
    "max_size": 10,
    "command_timeout": 60,
}
```

---

## 7. 监控与日志

### 7.1 日志配置

```python
# 日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 日志文件轮转
# /var/log/deepintel/
# ├── app.log          # 应用日志
# ├── access.log       # 访问日志
# └── error.log        # 错误日志
```

### 7.2 健康检查端点

```bash
# 基础健康检查
GET /health
Response: {"status": "healthy", "version": "1.0.0"}

# 详细健康检查
GET /health/detailed
Response: {
    "status": "healthy",
    "components": {
        "database": "healthy",
        "redis": "healthy",
        "llm": "healthy"
    }
}
```

### 7.3 Prometheus 指标

```
# 端点: /metrics
# 主要指标:
- deepintel_requests_total
- deepintel_request_duration_seconds
- deepintel_active_sessions
- deepintel_llm_tokens_total
- deepintel_llm_cost_usd
- deepintel_dag_nodes_executed
- deepintel_reflection_revisions
```

---

## 8. 故障排查

### Windows Docker Desktop 反复启动报错

若后台日志中的首个错误为 `initializing Inference manager` 或 `initializing Secrets Engine`，并包含 `dockerInference`／`engine.sock` 和 `The file cannot be accessed by the system`，参见 [Docker 启动修复与实际数据库验证](acceptance/docker-startup-20261020.md)。这是本机残留通信端点阻塞后台初始化；客户端提示找不到 Linux engine 管道是后续结果。

本机桌面、开始菜单及既有任务栏固定图标的 **Docker Desktop** 已统一接入安全启动脚本。Docker 已退出时，它将两个已知、仅含临时 socket 的目录保存为带唯一后缀的旧目录，再启动 Docker；运行中仅打开界面。可复用启动脚本为 [`scripts/start_docker_desktop.ps1`](../scripts/start_docker_desktop.ps1)，入口安装脚本为 [`scripts/install_docker_safe_start.ps1`](../scripts/install_docker_safe_start.ps1)：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/install_docker_safe_start.ps1
```

安装器读取 Docker 的 `AutoStart` 偏好：关闭时移除遗留的 Docker 登录启动项，开启时使该项也走修复入口；不改变用户的自动启动偏好。原快捷方式、启动脚本和注册表原值备份至 `%LOCALAPPDATA%/DockerSafeStart/entrypoints-before-*`。没有现有任务栏图标时不新增固定项。

2026-10-21 已实际复现“任务栏仍直接调用原程序”的遗漏，并通过修复后连续两次任务栏启动、原报告／证据读取及新事务提交；见[本次记录](acceptance/docker-startup-entrypoints-20261021.md)。Docker 更新或重新固定图标后若恢复了原程序入口，可重新执行安装器。直接运行安装目录原程序或 `docker desktop start` 仍会绕过本机恢复；该处理不是 Docker／Windows 底层缺陷的永久修复承诺。

### 8.1 常见问题

**问题 0: 模型下载失败**

```bash
# 检查网络连接
curl -I https://huggingface.co

# 设置 HuggingFace 镜像
export HF_ENDPOINT=https://hf-mirror.com

# 手动下载模型
python scripts/preload_models.py

# 离线部署：使用预下载的模型包
bash deploy_models.sh
```

**问题 1: 数据库连接失败**

```bash
# 检查 PostgreSQL 是否运行
pg_isready -h localhost -p 5432

# 检查 pgvector 扩展
psql -d deepintel -c "SELECT * FROM pg_extension WHERE extname='vector';"
```

**问题 2: Playwright 浏览器启动失败**

```bash
# 安装系统依赖
playwright install-deps chromium

# 检查是否可以启动
playwright open https://example.com
```

**问题 3: LLM API 调用失败**

```bash
# 测试 API 连接
curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen-plus", "messages": [{"role": "user", "content": "Hello"}]}'
```

**问题 4: SSE 连接中断**

```bash
# 检查 Nginx 配置
nginx -t

# 检查超时设置
grep -E "proxy_read_timeout|proxy_send_timeout" /etc/nginx/nginx.conf
```

### 8.2 性能调优

```bash
# 检查资源使用
docker stats

# 检查数据库连接数
psql -d deepintel -c "SELECT count(*) FROM pg_stat_activity;"

# 检查 Redis 内存
redis-cli info memory
```

---

## 附录：快速启动命令

```bash
# 完整启动流程
git clone https://github.com/your-org/deepintel.git
cd deepintel
cp .env.example .env
# 编辑 .env 填入配置

docker-compose up -d

# 等待服务就绪
sleep 10

# 验证
curl http://localhost:8000/health
```
