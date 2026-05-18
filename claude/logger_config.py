"""
日志配置模块
提供双日志系统：运行日志和错误日志
"""

import os
import sys
from loguru import logger


def setup_logger(log_dir: str = "logs", scan_limit: int = None):
    """
    配置双日志系统
    
    Args:
        log_dir: 日志目录
        scan_limit: 扫描限制数量（用于日志文件名）
    
    Returns:
        logger: 配置好的logger实例
    """
    # 创建日志目录
    os.makedirs(log_dir, exist_ok=True)
    
    # 移除默认的handler
    logger.remove()
    
    # 1. 控制台输出 - INFO级别，彩色显示
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        colorize=True,
        enqueue=True
    )
    
    # 2. 运行日志文件 - DEBUG级别，记录所有详细信息
    scan_log_file = os.path.join(log_dir, "scan.log")
    logger.add(
        scan_log_file,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        rotation="100 MB",  # 每100MB轮转
        retention="30 days",  # 保留30天
        compression="zip",  # 压缩旧日志
        enqueue=True,  # 异步写入
        encoding="utf-8"
    )
    
    # 3. 错误日志文件 - ERROR级别，只记录错误
    error_log_file = os.path.join(log_dir, "error.log")
    logger.add(
        error_log_file,
        level="ERROR",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line}\n{exception}\n{message}\n{'='*80}\n",
        rotation="50 MB",
        retention="90 days",  # 错误日志保留更久
        compression="zip",
        enqueue=True,
        encoding="utf-8",
        backtrace=True,  # 记录完整的异常堆栈
        diagnose=True  # 显示变量值
    )
    
    # 4. 违规图片专用日志 - WARNING级别
    violation_log_file = os.path.join(log_dir, "violations.log")
    logger.add(
        violation_log_file,
        level="WARNING",
        filter=lambda record: record["level"].name == "WARNING" and "违规" in record["message"],
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}\n",
        rotation="50 MB",
        retention="90 days",
        compression="zip",
        enqueue=True,
        encoding="utf-8",
        mode="a"
    )
    
    logger.info(f"日志系统初始化完成")
    logger.info(f"  - 运行日志: {scan_log_file}")
    logger.info(f"  - 错误日志: {error_log_file}")
    logger.info(f"  - 违规日志: {violation_log_file}")
    
    return logger


def get_logger():
    """获取已配置的logger实例"""
    return logger
