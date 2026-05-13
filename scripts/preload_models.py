#!/usr/bin/env python3
"""
预下载所有本地模型脚本。

在首次部署前运行此脚本，避免服务启动时的模型下载延迟。
"""

import asyncio
import logging
import sys
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


async def download_embedding_model():
    """下载 RAG 嵌入模型"""
    model_name = "BAAI/bge-zh-qwen2-int8"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    logger.info(f"开始下载嵌入模型: {model_name} (device: {device})")
    try:
        model = SentenceTransformer(model_name, device=device)
        # 测试编码
        test_text = "测试文本"
        embedding = model.encode(test_text, normalize_embeddings=True)
        logger.info(f"嵌入模型下载成功，维度: {embedding.shape}")
        return True
    except Exception as e:
        logger.error(f"嵌入模型下载失败: {e}")
        return False


async def download_reranker_model():
    """下载 RAG 重排序模型"""
    model_name = "BAAI/bge-reranker-v2-m3"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    logger.info(f"开始下载重排序模型: {model_name} (device: {device})")
    try:
        # 下载 tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        logger.info(f"Tokenizer 下载成功: {tokenizer.__class__.__name__}")
        
        # 下载模型
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
            logger.info(f"重排序模型下载成功，输出形状: {outputs.logits.shape}")
        
        return True
    except Exception as e:
        logger.error(f"重排序模型下载失败: {e}")
        return False


async def check_playwright():
    """检查 Playwright 浏览器"""
    try:
        import playwright
        from playwright.async_api import async_playwright
        
        logger.info("检查 Playwright 浏览器...")
        playwright_instance = await async_playwright().start()
        try:
            # 尝试启动浏览器
            browser = await playwright_instance.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("about:blank")
            await page.close()
            await browser.close()
            logger.info("Playwright 浏览器检查通过")
            return True
        finally:
            await playwright_instance.stop()
    except Exception as e:
        logger.warning(f"Playwright 检查失败: {e}")
        logger.info("请运行: playwright install chromium")
        return False


async def main():
    """主函数"""
    logger.info("开始预下载所有本地模型...")
    
    results = []
    
    # 下载嵌入模型
    embed_result = await download_embedding_model()
    results.append(("嵌入模型", embed_result))
    
    # 下载重排序模型
    rerank_result = await download_reranker_model()
    results.append(("重排序模型", rerank_result))
    
    # 检查 Playwright
    playwright_result = await check_playwright()
    results.append(("Playwright 浏览器", playwright_result))
    
    # 打印结果
    logger.info("\n" + "="*50)
    logger.info("预下载结果:")
    for name, success in results:
        status = "✓ 成功" if success else "✗ 失败"
        logger.info(f"  {name}: {status}")
    
    # 统计
    total = len(results)
    success_count = sum(1 for _, s in results if s)
    
    logger.info(f"\n总计: {success_count}/{total} 项成功")
    
    if success_count == total:
        logger.info("✅ 所有模型预下载完成，可以启动服务")
        return 0
    else:
        logger.warning("⚠️  部分模型下载失败，请检查网络连接")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
