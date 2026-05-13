#!/usr/bin/env python3
"""
下载所有模型并打包，用于离线部署。

此脚本会：
1. 下载所有 HuggingFace 模型
2. 安装 Playwright 浏览器
3. 打包模型缓存
"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ModelDownloader:
    """模型下载器"""
    
    def __init__(self, output_dir: str = "model_cache"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 模型配置
        self.models = {
            "embedding": {
                "name": "BAAI/bge-zh-qwen2-int8",
                "type": "sentence-transformers",
                "description": "中文优化的嵌入模型 (INT8 量化)"
            },
            "reranker": {
                "name": "BAAI/bge-reranker-v2-m3",
                "type": "transformers",
                "description": "跨编码器重排序模型"
            }
        }
    
    async def download_huggingface_model(self, model_name: str, model_type: str):
        """下载 HuggingFace 模型"""
        logger.info(f"下载模型: {model_name} ({model_type})")
        
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        try:
            if model_type == "sentence-transformers":
                # SentenceTransformer 模型
                model = SentenceTransformer(model_name, device=device)
                # 测试编码
                test_embedding = model.encode("测试文本", normalize_embeddings=True)
                logger.info(f"  ✓ 下载成功，维度: {test_embedding.shape}")
                
            elif model_type == "transformers":
                # Transformers 模型
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                model = AutoModelForSequenceClassification.from_pretrained(
                    model_name,
                    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                )
                model.to(device)
                model.eval()
                
                # 测试推理
                with torch.no_grad():
                    inputs = tokenizer(
                        ["测试查询"],
                        ["测试文档"],
                        padding=True,
                        truncation=True,
                        max_length=512,
                        return_tensors="pt",
                    )
                    inputs = {k: v.to(device) for k, v in inputs.items()}
                    outputs = model(**inputs)
                    logger.info(f"  ✓ 下载成功，输出形状: {outputs.logits.shape}")
            
            return True
            
        except Exception as e:
            logger.error(f"  ✗ 下载失败: {e}")
            return False
    
    async def install_playwright(self):
        """安装 Playwright 浏览器"""
        logger.info("安装 Playwright 浏览器...")
        
        try:
            # 安装 Playwright Python 包
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info("  ✓ Playwright Python 包安装成功")
            
            # 安装 Chromium 浏览器
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                logger.info("  ✓ Chromium 浏览器安装成功")
                return True
            else:
                logger.error(f"  ✗ Chromium 安装失败: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"  ✗ Playwright 安装失败: {e}")
            return False
    
    def get_cache_paths(self):
        """获取缓存路径"""
        cache_paths = []
        
        # HuggingFace 缓存
        hf_home = os.environ.get("HF_HOME")
        if hf_home:
            hf_cache = Path(hf_home)
        else:
            hf_cache = Path.home() / ".cache" / "huggingface"
        
        if hf_cache.exists():
            cache_paths.append(("huggingface", hf_cache))
        
        # Playwright 缓存
        playwright_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        if playwright_path:
            pw_cache = Path(playwright_path)
        else:
            # 不同平台的默认路径
            if sys.platform == "win32":
                pw_cache = Path.home() / "AppData" / "Local" / "ms-playwright"
            elif sys.platform == "darwin":
                pw_cache = Path.home() / "Library" / "Caches" / "ms-playwright"
            else:
                pw_cache = Path.home() / ".cache" / "ms-playwright"
        
        if pw_cache.exists():
            cache_paths.append(("playwright", pw_cache))
        
        return cache_paths
    
    def create_tarball(self):
        """创建压缩包"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        tarball_name = f"deepintel_models_{timestamp}.tar.gz"
        tarball_path = self.output_dir / tarball_name
        
        cache_paths = self.get_cache_paths()
        
        if not cache_paths:
            logger.warning("未找到模型缓存，请先运行下载")
            return None
        
        logger.info(f"创建压缩包: {tarball_path}")
        
        with tarfile.open(tarball_path, "w:gz") as tar:
            for name, path in cache_paths:
                if path.exists():
                    logger.info(f"  添加: {name} -> {path}")
                    tar.add(path, arcname=f"models/{name}")
        
        # 计算大小
        size_mb = tarball_path.stat().st_size / (1024 * 1024)
        logger.info(f"压缩包大小: {size_mb:.1f} MB")
        
        return tarball_path
    
    def create_deployment_script(self, tarball_path: Path):
        """创建部署脚本"""
        script_content = f'''#!/bin/bash
# DeepIntel 模型部署脚本
# 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
# 压缩包: {tarball_path.name}

set -e

echo "DeepIntel 模型部署开始..."

# 解压目录
EXTRACT_DIR="${{1:-./deepintel_models}}"

# 创建目录
mkdir -p "$EXTRACT_DIR"

# 解压
echo "解压模型文件..."
tar -xzf "{tarball_path.name}" -C "$EXTRACT_DIR"

# 设置环境变量
echo "设置环境变量..."
echo ""
echo "请将以下内容添加到你的环境配置中:"
echo ""
echo "export HF_HOME=\"$EXTRACT_DIR/models/huggingface\""
echo "export PLAYWRIGHT_BROWSERS_PATH=\"$EXTRACT_DIR/models/playwright\""
echo ""
echo "或者添加到 .env 文件:"
echo "HF_HOME=$EXTRACT_DIR/models/huggingface"
echo "PLAYWRIGHT_BROWSERS_PATH=$EXTRACT_DIR/models/playwright"
echo ""
echo "部署完成！"

# 验证
if [ -d "$EXTRACT_DIR/models/huggingface" ]; then
    echo "✓ HuggingFace 模型已部署"
fi

if [ -d "$EXTRACT_DIR/models/playwright" ]; then
    echo "✓ Playwright 浏览器已部署"
fi
'''
        
        script_path = self.output_dir / "deploy_models.sh"
        script_path.write_text(script_content)
        script_path.chmod(0o755)
        
        logger.info(f"部署脚本已创建: {script_path}")
        
        return script_path
    
    async def run(self):
        """运行下载和打包"""
        logger.info("="*60)
        logger.info("DeepIntel 模型下载和打包工具")
        logger.info("="*60)
        
        # 下载 HuggingFace 模型
        logger.info("\n1. 下载 HuggingFace 模型")
        for model_id, config in self.models.items():
            success = await self.download_huggingface_model(
                config["name"],
                config["type"]
            )
            if not success:
                logger.warning(f"模型 {model_id} 下载失败，继续...")
        
        # 安装 Playwright
        logger.info("\n2. 安装 Playwright 浏览器")
        await self.install_playwright()
        
        # 创建压缩包
        logger.info("\n3. 打包模型缓存")
        tarball_path = self.create_tarball()
        
        if tarball_path:
            # 创建部署脚本
            logger.info("\n4. 创建部署脚本")
            script_path = self.create_deployment_script(tarball_path)
            
            logger.info("\n" + "="*60)
            logger.info("✅ 完成！")
            logger.info(f"压缩包: {tarball_path}")
            logger.info(f"部署脚本: {script_path}")
            logger.info("")
            logger.info("使用方法:")
            logger.info(f"  1. 复制 {tarball_path.name} 和 {script_path.name} 到目标服务器")
            logger.info(f"  2. 运行: bash {script_path.name}")
            logger.info("  3. 按照提示设置环境变量")
            logger.info("="*60)
        else:
            logger.error("❌ 打包失败")
            return 1
        
        return 0


async def main():
    """主函数"""
    downloader = ModelDownloader()
    return await downloader.run()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
