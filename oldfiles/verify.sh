#!/bin/bash

# 快速验证脚本

echo "=========================================="
echo "  系统验证"
echo "=========================================="
echo ""

# 检查Python
if command -v python3 &> /dev/null; then
    echo "✓ Python3 已安装: $(python3 --version)"
else
    echo "✗ Python3 未安装"
    exit 1
fi

# 检查文件完整性
echo ""
echo "检查项目文件..."

files=(
    "scanner.py"
    "minio_client.py"
    "image_feature.py"
    "tencent_ims.py"
    "database.py"
    "schema.sql"
    "requirements.txt"
    ".env.example"
    "README.md"
)

missing=0
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (缺失)"
        missing=$((missing + 1))
    fi
done

if [ $missing -eq 0 ]; then
    echo ""
    echo "✓ 所有必要文件都存在"
else
    echo ""
    echo "✗ 缺少 $missing 个文件"
    exit 1
fi

# 检查依赖
echo ""
echo "检查Python依赖包..."
pip3 list 2>/dev/null | grep -E "minio|Pillow|imagehash|mysql-connector|tencentcloud|loguru|tqdm" || echo "  (未安装或部分缺失)"

echo ""
echo "=========================================="
echo "  验证完成"
echo "=========================================="
echo ""
echo "下一步操作:"
echo "1. 安装依赖: pip install -r requirements.txt"
echo "2. 配置环境: cp .env.example .env 并编辑"
echo "3. 初始化数据库: mysql -u root -p < schema.sql"
echo "4. 运行扫描: python scanner.py 或 ./run.sh"
echo ""
