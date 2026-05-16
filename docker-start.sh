#!/bin/bash

# Docker快速启动脚本 - 简化版

set -e

echo "=========================================="
echo "  图片内容安全扫描系统"
echo "=========================================="
echo ""

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "✗ 错误: Docker未安装"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "✗ 错误: Docker Compose未安装"
    exit 1
fi

echo "✓ Docker: $(docker --version)"
echo ""

# 检查.env文件
if [ ! -f .env ]; then
    echo "⚠ 创建配置文件..."
    cp .env.example .env
    echo "✓ 已创建 .env 文件"
    echo ""
    echo "⚠ 请编辑 .env 文件，填写："
    echo "  - MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY"
    echo "  - MYSQL_HOST, MYSQL_PASSWORD"
    echo "  - TENCENT_SECRET_ID, TENCENT_SECRET_KEY"
    echo ""
    read -p "按Enter键打开编辑器..."
    vim .env || nano .env || vi .env
fi

echo ""
echo "=========================================="
echo "  选择操作"
echo "=========================================="
echo "1. 启动扫描"
echo "2. 查看日志"
echo "3. 停止服务"
echo "4. 重新扫描（强制）"
echo "0. 退出"
echo ""

read -p "请选择 (0-4): " choice

case $choice in
    1)
        echo ""
        echo "启动扫描..."
        docker-compose up
        ;;
    2)
        echo ""
        docker-compose logs -f scanner
        ;;
    3)
        echo ""
        echo "停止服务..."
        docker-compose down
        echo "✓ 已停止"
        ;;
    4)
        echo ""
        echo "强制重新扫描..."
        FORCE_RESCAN=true docker-compose up
        ;;
    0)
        exit 0
        ;;
    *)
        echo "无效选择"
        exit 1
        ;;
esac
