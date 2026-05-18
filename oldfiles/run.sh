#!/bin/bash

# 图片内容安全扫描系统 - 快速启动脚本

echo "=========================================="
echo "  图片内容安全扫描系统"
echo "=========================================="
echo ""

# 检查Python版本
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到Python3，请先安装Python 3.7+"
    exit 1
fi

echo "✓ Python版本: $(python3 --version)"

# 检查依赖
echo ""
echo "检查依赖包..."
pip3 install -r requirements.txt -q

if [ $? -eq 0 ]; then
    echo "✓ 依赖包安装成功"
else
    echo "✗ 依赖包安装失败"
    exit 1
fi

# 检查配置文件
echo ""
if [ ! -f .env ]; then
    echo "⚠ 警告: 未找到.env配置文件"
    echo "请复制.env.example为.env并填写配置信息:"
    echo "  cp .env.example .env"
    echo ""
    read -p "是否现在创建配置文件? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cp .env.example .env
        echo "✓ 已创建.env文件，请编辑该文件填写您的配置信息"
        exit 0
    else
        exit 1
    fi
else
    echo "✓ 配置文件存在"
fi

# 检查数据库
echo ""
echo "提示: 请确保已执行以下操作:"
echo "  1. MySQL服务正在运行"
echo "  2. 已创建数据库: image_security"
echo "  3. 已执行schema.sql初始化表结构"
echo ""
read -p "是否已完成数据库初始化? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "请先完成数据库初始化，然后重新运行此脚本"
    exit 1
fi

# 获取扫描选项
echo ""
echo "扫描选项:"
read -p "存储桶名称 (留空使用默认): " BUCKET_NAME
read -p "对象前缀 (留空扫描全部): " PREFIX
read -p "限制数量 (留空不限制): " LIMIT
read -p "强制重扫? (y/n): " FORCE_RESCAN

# 设置环境变量
[ -n "$BUCKET_NAME" ] && export SCAN_BUCKET_NAME="$BUCKET_NAME"
[ -n "$PREFIX" ] && export SCAN_PREFIX="$PREFIX"
[ -n "$LIMIT" ] && export SCAN_LIMIT="$LIMIT"
[[ "$FORCE_RESCAN" =~ ^[Yy]$ ]] && export FORCE_RESCAN="true"

# 开始扫描
echo ""
echo "=========================================="
echo "  开始扫描..."
echo "=========================================="
echo ""

python3 scanner.py

# 显示结果
echo ""
echo "=========================================="
echo "  扫描完成!"
echo "=========================================="
echo ""

if [ -f violations.txt ]; then
    echo "违规报告已生成: violations.txt"
    echo ""
    read -p "是否查看违规报告? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cat violations.txt | head -100
    fi
fi

echo ""
echo "详细日志请查看: scanner.log"
