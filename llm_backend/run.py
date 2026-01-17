import os

# 【关键修复步骤 1】设置环境变量，允许 OpenMP 库重复加载
# 这通常是解决 Windows 下 torch 报错 "DLL initialization routine failed" 的核心
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# 【关键修复步骤 2】在导入任何其他库（特别是 uvicorn）之前，先导入 torch
# 这样可以确保 torch 的核心 DLL (c10.dll) 最先被正确加载
import torch

import uvicorn
from app.core.logger import get_logger
from pathlib import Path

logger = get_logger(service="server")


def start_server():
    # 确保工作目录正确
    os.chdir(Path(__file__).parent)

    logger.info("Starting server...")
    logger.info(f"Working directory: {os.getcwd()}")

    # 注意：在 reload=True 模式下，uvicorn 会创建子进程。
    # 我们在上面设置的 os.environ 会被传递给子进程，这很重要。
    uvicorn.run(
        "main:app",  # 使用模块路径
        host="0.0.0.0",
        port=8000,
        access_log=False,
        log_level="error",
        reload=True  # 开发模式下启用热重载
    )


if __name__ == "__main__":
    start_server()