# 安装指南

## 环境要求

### 软件依赖

- **Python 3.8+**
- **MySQL 5.7+** 或 **MySQL 8.0+**
- **MinIO** 存储服务（任何 S3 兼容的对象存储）
- **网络连接**：能访问腾讯云 API（仅 scanner.py 需要）

### 可选：Docker

如果使用 Docker 部署，需要：
- **Docker 20.10+**
- **Docker Compose 1.29+**

## 步骤 1：克隆项目

```bash
git clone <repo-url> imsminioimgs
cd imsminioimgs/claude
```

## 步骤 2：创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
# Linux/Mac:
source .venv/bin/activate

# Windows:
.venv\Scripts\activate
```

## 步骤 3：安装 Python 依赖

```bash
pip install -r requirements.txt
```

**依赖清单**：
```
minio==7.2.0                          # MinIO 客户端
mysql-connector-python==8.3.0         # MySQL 驱动
tencentcloud-sdk-python-ims==3.1.96   # 腾讯云 IMS
python-dotenv==1.0.1                  # 环境变量加载
loguru==0.7.2                         # 日志库
Pillow==10.2.0                        # 图片处理
imagehash==4.3.1                      # 哈希特征提取
numpy==1.26.4                         # 数值计算
requests==2.31.0                      # HTTP 请求
tqdm==4.66.2                          # 进度条
```

**最小依赖**（仅运行 handle_violations.py）：
```bash
pip install minio mysql-connector-python python-dotenv loguru
```

## 步骤 4：配置环境

### 4.1 复制配置模板

```bash
cp .env.example .env
```

### 4.2 编辑配置文件

```bash
vim .env  # 或使用你的编辑器
```

### 4.3 关键配置项

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `MINIO_ENDPOINT` | MinIO 服务地址 | `localhost:9000` 或 `minio.example.com:9000` |
| `MINIO_ACCESS_KEY` | MinIO 访问密钥 | `minioadmin` |
| `MINIO_SECRET_KEY` | MinIO 秘密密钥 | `minioadmin` |
| `MINIO_BUCKET_NAME` | 业务图片存储桶 | `images` |
| `QUARANTINE_BUCKET_NAME` | 隔离桶 | `quarantine` |
| `MYSQL_HOST` | MySQL 服务器地址 | `localhost` 或 `mysql.example.com` |
| `MYSQL_USER` | MySQL 用户名 | `root` |
| `MYSQL_PASSWORD` | MySQL 密码 | - |
| `MYSQL_DATABASE` | 数据库名 | `image_security` |
| `TENCENT_SECRET_ID` | 腾讯云 Secret ID（仅 scanner.py） | - |
| `TENCENT_SECRET_KEY` | 腾讯云 Secret Key（仅 scanner.py） | - |
| `TENCENT_REGION` | 腾讯云地域 | `ap-beijing` |

### 4.4 配置示例

```ini
# .env

# ====== MinIO 配置 ======
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=images
QUARANTINE_BUCKET_NAME=quarantine
MINIO_USE_SSL=false

# ====== MySQL 配置 ======
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=image_security
MYSQL_CHARSET=utf8mb4

# ====== 腾讯云配置（仅 scanner.py 需要）======
TENCENT_SECRET_ID=your_secret_id
TENCENT_SECRET_KEY=your_secret_key
TENCENT_REGION=ap-beijing

# ====== 日志配置（可选）======
LOG_LEVEL=INFO
ENABLE_CONSOLE_LOG=true
```

## 步骤 5：初始化数据库

### 5.1 创建数据库

```bash
# 方法 1：使用 schema.sql（推荐）
mysql -u root -p < schema.sql

# 方法 2：手动创建
mysql -u root -p
mysql> CREATE DATABASE image_security CHARACTER SET utf8mb4;
mysql> USE image_security;
mysql> SOURCE schema.sql;
mysql> EXIT;
```

### 5.2 验证数据库

```bash
# 查看创建的表
mysql -u root -p image_security -e "SHOW TABLES;"

# 查看 image_scan_records 表结构
mysql -u root -p image_security -e "DESCRIBE image_scan_records;"
```

输出应该包含 `image_scan_records` 表。

## 步骤 6：创建 MinIO 桶

```bash
# 使用 minio 命令行工具或 Web UI

# 命令行方式（需要安装 mc）
mc mb localhost:9000/images
mc mb localhost:9000/quarantine

# 或通过 MinIO Web UI (http://localhost:9000)
# 创建两个桶：images 和 quarantine
```

## 步骤 7：验证安装

### 7.1 测试 Python 环境

```bash
python -c "import minio, mysql.connector, loguru; print('✓ 所有依赖安装成功')"
```

### 7.2 测试配置

```bash
# 查看配置是否正确加载
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(f'MySQL: {os.getenv(\"MYSQL_HOST\")}'); print(f'MinIO: {os.getenv(\"MINIO_ENDPOINT\")}')"
```

### 7.3 测试 MinIO 连接

```bash
python -c "
from minio import Minio
from dotenv import load_dotenv
import os

load_dotenv()
client = Minio(
    os.getenv('MINIO_ENDPOINT'),
    access_key=os.getenv('MINIO_ACCESS_KEY'),
    secret_key=os.getenv('MINIO_SECRET_KEY'),
    secure=False
)
buckets = client.list_buckets()
print('✓ MinIO 连接成功')
for b in buckets.buckets:
    print(f'  - {b.name}')
"
```

### 7.4 测试 MySQL 连接

```bash
python -c "
import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()
conn = mysql.connector.connect(
    host=os.getenv('MYSQL_HOST'),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DATABASE')
)
print('✓ MySQL 连接成功')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM image_scan_records')
result = cursor.fetchone()
print(f'  - 表中现有记录数: {result[0]}')
conn.close()
"
```

## 步骤 8：运行系统

### 选项 A：扫描图片（仅使用 scanner.py）

```bash
# 首次全量扫描
python scanner.py

# 强制重新扫描
python scanner.py --force-rescan
```

### 选项 B：处置违规（仅使用 handle_violations.py）

```bash
# 查看新增违规
python handle_violations.py list

# 标记为私密
python handle_violations.py mark-private --type gambling
```

### 选项 C：完整工作流

```bash
# 1. 扫描
python scanner.py

# 2. 查看违规
python handle_violations.py list

# 3. 标记私密
python handle_violations.py mark-private --type gambling

# 4. 观察 24 小时...

# 5. 确认隔离
python handle_violations.py confirm-quarantine --ids 1
```

## 故障排查

### 问题：`ModuleNotFoundError: No module named 'minio'`

**解决**：
```bash
pip install -r requirements.txt
```

### 问题：`MySQL 连接失败`

**检查清单**：
```bash
# 1. MySQL 是否运行
mysql -u root -p -e "SELECT 1"

# 2. 凭据是否正确
# 检查 .env 中的 MYSQL_PASSWORD

# 3. 数据库是否存在
mysql -u root -p -e "SHOW DATABASES" | grep image_security
```

### 问题：`MinIO 连接失败`

**检查清单**：
```bash
# 1. MinIO 是否运行
curl http://localhost:9000

# 2. 凭据是否正确
# 检查 .env 中的 MINIO_ACCESS_KEY 和 SECRET_KEY

# 3. 桶是否存在
mc ls localhost:9000
```

### 问题：`权限被拒绝 (Permission denied)`

**解决**：
```bash
# 创建 logs 目录
mkdir -p logs

# 设置权限
chmod 755 logs
```

## 下一步

- ✓ 安装完成
- → 快速开始：[QUICK_START.md](./QUICK_START.md)
- → 使用指南：[USAGE.md](./USAGE.md)
- → 三阶段工作流：[WORKFLOW.md](./WORKFLOW.md)

---

← [INDEX](./INDEX.md) | [QUICK_START](./QUICK_START.md) →
