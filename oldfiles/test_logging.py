#!/usr/bin/env python3
"""
日志系统测试脚本
用于验证日志配置是否正常工作
"""

from logger_config import setup_logger

# 初始化日志系统
logger = setup_logger(log_dir="logs")

print("="*80)
print("日志系统测试")
print("="*80)
print()

# 测试不同级别的日志
logger.debug("这是一条DEBUG日志 - 应该出现在scan.log中")
logger.info("这是一条INFO日志 - 应该出现在控制台和scan.log中")
logger.warning("这是一条WARNING日志 - 包含违规关键字会出现在violations.log中")
logger.error("这是一条ERROR日志 - 应该出现在error.log和scan.log中")

print()
print("✅ 日志测试完成！")
print()
print("请检查以下文件：")
print("  1. logs/scan.log - 应包含所有4条日志")
print("  2. logs/error.log - 应包含ERROR日志")
print("  3. logs/violations.log - 应包含WARNING日志（如果有'违规'关键字）")
print()
print("查看日志内容：")
print("  cat logs/scan.log")
print("  cat logs/error.log")
print("  cat logs/violations.log")
