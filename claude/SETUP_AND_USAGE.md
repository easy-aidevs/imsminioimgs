# 违规图片处置工具：完整使用和配置说明

## 📋 目录

1. [系统要求](#系统要求)
2. [安装与配置](#安装与配置)
3. [使用流程](#使用流程)
4. [命令参考](#命令参考)
5. [配置详解](#配置详解)
6. [常见问题](#常见问题)
7. [故障排查](#故障排查)

---

## 系统要求

### 软件依赖

- **Python 3.8+**
- **MySQL 5.7+** 或 **MySQL 8.0+**
- **MinIO** 服务（任何兼容 S3 的对象存储）
- **腾讯云 IMS** 账户（用于图片扫描，可选。仅 `scanner.py` 需要）

### Python 包依赖

详见 `requirements.txt`：

```
minio==7.2.0              # MinIO 对象存储客户端
mysql-connector-python==8.3.0  # MySQL 驱动
tencentcloud-sdk-python-ims==3.1.96  # 腾讯云 IMS（内容安全扫描）
tencentcloud-sdk-python-common==3.1.98
python-dotenv==1.0.1     # 环境变量加载
loguru==0.7.2            # 日志库
Pillow==10.2.0           # 图片处理（扫描器）
imagehash==4.3.1         # 哈希去重（扫描器）
numpy==1.26.4            # 数值计算（扫描器）
requests==2.31.0         # HTTP 请求
tqdm==4.66.2             # 进度条（扫描器）
```

**仅使用 `handle_violations.py` 的最小依赖：**
```
minio>=7.2.0
mysql-connector-python>=8.3.0
python-dotenv>=1.0.1
loguru>=0.7.2
```

---

## 安装与配置

### 1. 克隆/准备项目

```bash
cd /path/to/imsminioimgs/claude
```

### 2. 创建虚拟环境（推荐）

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

```bash
cp .env.example .env
vim .env  # 编辑配置
```

详见 [配置详解](#配置详解) 部分。

### 5. 初始化数据库（仅首次）

```bash
# 登录 MySQL
mysql -u root -p

# 创建数据库
CREATE DATABASE IF NOT EXISTS image_security CHARACTER SET utf8mb4;

# 创建表（如果 schema.sql 存在）
USE image_security;
SOURCE schema.sql;
```

如果没有 `schema.sql`，参考以下 SQL：

```sql
CREATE TABLE image_scan_records (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  bucket_name VARCHAR(255) NOT NULL,
  object_key VARCHAR(1024) NOT NULL,
  is_violation INT DEFAULT 0,           -- 0=正常, 1=违规
  violation_type VARCHAR(100),           -- 违规类型（如 gambling, porn）
  violation_label VARCHAR(255),          -- 违规标签详细描述
  confidence FLOAT,                      -- 置信度 0-100
  blocked INT DEFAULT 0,                 -- 处置状态：0=public, 1=private, 2=quarantined
  feature_hash VARCHAR(64),              -- 感知哈希（用于去重）
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_location (bucket_name, object_key),
  KEY idx_violation (is_violation),
  KEY idx_blocked (blocked),
  KEY idx_type (violation_type)
);
```

---

## 使用流程

### 整体工作流

```
┌────────────────────────────────────────────────────────────────┐
│ 第一阶段：发现 & 标记为私密（隐藏观察）                          │
├────────────────────────────────────────────────────────────────┤
│ 1. python handle_violations.py list           查看新增违规      │
│ 2. python handle_violations.py mark-private   标记为私密        │
│ 3. python handle_violations.py list-private   查看观察中的      │
│                                                                │
│ [此时图片在原桶，但无法公开访问，应用层过滤不显示]              │
│ [观察期：监控业务日志，确认无异常]                              │
└────────────────────────────────────────────────────────────────┘
        │
        ├─── 观察正常 ───────────────────────────────────────┐
        │                                                     │
        ↓                                                     ↓
┌──────────────────────────┐               ┌──────────────────────────┐
│ 第二阶段-A：确认隔离      │               │ 第二阶段-B：改回公开    │
├──────────────────────────┤               ├──────────────────────────┤
│ 观察正常，真正违规        │               │ 观察异常，误判          │
│                          │               │                          │
│ confirm-quarantine       │               │ restore-public           │
│ 移到隔离桶（不可恢复）   │               │ 改为公开（重新分析）    │
└──────────────────────────┘               └──────────────────────────┘
        │                                          │
        └──────────────────────┬───────────────────┘
                               │
                               ↓
                  ┌─────────────────────┐
                  │ 第三阶段：彻底删除  │
                  ├─────────────────────┤
                  │ delete --ids x,y,z  │
                  │ 从隔离桶删除        │
                  │ 清除数据库记录      │
                  └─────────────────────┘
```

### 典型流程示例

#### 场景 1：发现违规并处置

```bash
# 1. 查看新增违规图片
$ python handle_violations.py list
未处理的违规图片（blocked=0）（共 15 条）
ID     类型         置信度    路径
--
1      gambling     0.95      images/pic_001.jpg
2      porn         0.87      images/pic_002.jpg
...

# 2. 标记赌博类为私密（进入观察期）
$ python handle_violations.py mark-private --type gambling
...
完成 - 成功: 5 失败: 0 跳过: 0

# 3. 查看当前观察中的
$ python handle_violations.py list-private
私密观察中的图片（blocked=1）（共 5 条）
ID     类型         置信度    路径
--
1      gambling     0.95      images/pic_001.jpg
...

# [等待 24-48 小时，监控业务日志确认无异常]

# 4. 观察正常，确认隔离
$ python handle_violations.py confirm-quarantine --ids 1,2,3,4,5
...
完成 - 成功: 5 失败: 0 跳过: 0

# 5. 查看已隔离的
$ python handle_violations.py list-quarantined
隔离中的图片（blocked=2）（共 5 条）
...

# 6. 一段时间后，彻底删除
$ python handle_violations.py delete --ids 1,2,3,4,5
...
完成 - 成功: 5 失败: 0
```

#### 场景 2：发现误判，立即恢复

```bash
# 发现某些私密图片不应该被拦截
$ python handle_violations.py restore-public --ids 10,11

# 图片改回公开，标记为误判，不再参与违规处理
完成 - 成功: 2 失败: 0 跳过: 0

# 查看该记录
$ mysql image_security -e "SELECT id, blocked, is_violation FROM image_scan_records WHERE id=10"
+----+---------+----------+
| id | blocked | is_violation |
+----+---------+----------+
| 10 |       0 |        0 |  ← 改回公开，不再是违规
+----+---------+----------+
```

---

## 命令参考

### 1. 列表查询命令

#### `list` - 查看未处理的违规

```bash
python handle_violations.py list [OPTIONS]

选项：
  --type TEXT           按违规类型过滤（如 gambling, porn）
  --confidence FLOAT    最低置信度阈值（如 0.8）

示例：
  python handle_violations.py list
  python handle_violations.py list --type gambling --confidence 0.9
```

#### `list-private` - 查看观察期的图片

```bash
python handle_violations.py list-private [OPTIONS]

选项：
  --type TEXT           按违规类型过滤
  --confidence FLOAT    最低置信度阈值

示例：
  python handle_violations.py list-private
  python handle_violations.py list-private --type porn
```

#### `list-quarantined` - 查看已隔离的图片

```bash
python handle_violations.py list-quarantined

示例：
  python handle_violations.py list-quarantined
```

---

### 2. 第一阶段：标记私密

#### `mark-private` - 标记违规图片为私密

```bash
python handle_violations.py mark-private [OPTIONS]

选项（选择一种）：
  --type TEXT                按违规类型过滤
  --confidence FLOAT         最低置信度阈值
  --ids ID1,ID2,...         指定图片 ID（逗号分隔）

可选：
  --dry-run                 预检查，不实际执行

示例：
  # 标记所有赌博类
  python handle_violations.py mark-private --type gambling
  
  # 标记指定 ID
  python handle_violations.py mark-private --ids 1,5,10,15
  
  # 预检查
  python handle_violations.py mark-private --type porn --dry-run
```

**操作内容：**
- 设置 MinIO 对象权限为私密（无法公开访问）
- 更新 DB: `blocked = 1`
- 记录日志

---

### 3. 第二阶段-A：确认隔离

#### `confirm-quarantine` - 观察正常，移到隔离桶

```bash
python handle_violations.py confirm-quarantine [OPTIONS]

选项：
  --ids ID1,ID2,...        指定要隔离的图片 ID（可选，省略则全部隔离）

可选：
  --dry-run               预检查，不实际执行

示例：
  # 隔离指定 ID
  python handle_violations.py confirm-quarantine --ids 1,2,3
  
  # 隔离全部观察中的（谨慎使用）
  python handle_violations.py confirm-quarantine
  
  # 预检查
  python handle_violations.py confirm-quarantine --ids 1,2,3 --dry-run
```

**操作内容：**
- 从原桶移动到隔离桶
- 打违规标签（用于标记）
- 更新 DB: `blocked = 2`
- **不可逆**：隔离后只能删除

---

### 4. 第二阶段-B：改回公开

#### `restore-public` - 观察异常，改回公开

```bash
python handle_violations.py restore-public [OPTIONS]

选项：
  --ids ID1,ID2,...       指定要恢复的图片 ID

可选：
  --dry-run              预检查，不实际执行

示例：
  python handle_violations.py restore-public --ids 5,8
  python handle_violations.py restore-public --ids 5,8 --dry-run
```

**操作内容：**
- 设置 MinIO 对象权限为公开
- 更新 DB: `blocked = 0, is_violation = 0`
- 标记为误判，不再参与违规处理
- 图片恢复正常访问

---

### 5. 第三阶段：彻底删除

#### `delete` - 从隔离桶彻底删除

```bash
python handle_violations.py delete [OPTIONS]

选项：
  --ids ID1,ID2,...       指定要删除的图片 ID（可选，省略则删除全部隔离的）

可选：
  --dry-run              预检查，不实际执行

示例：
  # 删除指定 ID
  python handle_violations.py delete --ids 1,2,3
  
  # 删除全部隔离的（谨慎使用，需确认 DELETE）
  python handle_violations.py delete
  
  # 预检查
  python handle_violations.py delete --ids 1,2,3 --dry-run
```

**操作内容：**
- 从隔离桶删除对象文件
- 清除数据库记录
- **不可恢复**

**确认提示：**
```
确认彻底删除 3 张？ (输入 DELETE 确认): DELETE
```

---

## 配置详解

### MinIO 配置

```ini
MINIO_ENDPOINT=localhost:9000
```
- MinIO 服务地址和端口
- 格式：`host:port`
- 示例：`minio.example.com:9000`

```ini
MINIO_ACCESS_KEY=your_minio_access_key
MINIO_SECRET_KEY=your_minio_secret_key
```
- MinIO 访问密钥
- 从 MinIO 管理界面获取

```ini
MINIO_SECURE=false
```
- 是否使用 HTTPS
- `false` = HTTP, `true` = HTTPS

```ini
MINIO_BUCKET_NAME=images
```
- 业务图片所在的桶
- `scanner.py` 扫描此桶中的图片
- `handle_violations.py` 在此桶标记私密

```ini
QUARANTINE_BUCKET_NAME=quarantine
```
- 隔离桶名称
- 不存在时自动创建
- **建议配置为不公开访问**
- 仅在 `confirm-quarantine` 时使用

---

### MySQL 配置

```ini
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_DATABASE=image_security
```
- MySQL 连接信息
- `MYSQL_DATABASE` 必须提前创建

---

### 腾讯云 IMS 配置

```ini
TENCENT_SECRET_ID=your_tencent_secret_id_here
TENCENT_SECRET_KEY=your_tencent_secret_key_here
TENCENT_REGION=ap-guangzhou
```
- **仅 `scanner.py` 需要**
- `handle_violations.py` 不需要腾讯云凭证
- 从腾讯云控制台获取（[详见腾讯云文档](https://cloud.tencent.com/doc/product/598)）
- 可选地域：`ap-beijing`, `ap-shanghai`, `ap-guangzhou`, 等

---

### 扫描参数

```ini
HASH_SIZE=8
```
- 感知哈希大小（仅 `scanner.py` 使用）
- 用于检测相似图片，节省 API 费用
- 不影响 `handle_violations.py`

```ini
SCAN_PREFIX=
```
- 扫描路径前缀（仅 `scanner.py` 使用）
- 为空表示扫描整个桶
- 示例：`photos/` 只扫描此前缀下的图片

```ini
FORCE_RESCAN=false
```
- 是否强制重新扫描已扫过的图片（仅 `scanner.py` 使用）

```ini
SCAN_LIMIT=100
```
- 仅扫描前 N 张图片，用于测试（仅 `scanner.py` 使用）

---

### Docker 配置

```ini
DOCKER_NETWORK_MODE=host
```
- Docker 网络模式（仅 `docker-compose` 使用）
- `host`：容器共享宿主机网络，可访问 `localhost`
- `bridge`：需用宿主机 IP 访问外部服务

---

### 无效项检查

✅ **所有配置项都有效，未发现过时项。**

- 腾讯云配置（TENCENT_*）：仅 `scanner.py` 需要，`handle_violations.py` 可忽略
- 扫描参数（HASH_SIZE, SCAN_PREFIX, etc.）：仅 `scanner.py` 需要
- 其他配置：所有工具都需要

---

## 常见问题

### Q1: 私密图片用户怎么无法访问？

**回答：** 使用 MinIO 的权限控制（`set_object_private()` 设置）。

```python
# 代码中的实现
self.minio.set_object_private(bucket, key)
```

同时，应用层应在数据库查询时过滤：
```sql
SELECT * FROM images WHERE blocked = 0  -- 只显示 public 的
```

---

### Q2: 能回到隔离前的状态吗？

**回答：** 

- ❌ **隔离后（blocked=2）**：无法恢复，只能删除
- ✅ **观察期（blocked=1）**：可改回公开 `restore-public`

建议在观察期充分验证后再确认隔离。

---

### Q3: 观察期需要多长时间？

**回答：** 根据业务需要自行决定，无硬性要求。建议：

- 高置信度违规（>0.95）：24小时
- 中等置信度（0.8-0.95）：48-72小时
- 低置信度（<0.8）：建议先 `restore-public`，重新审视

---

### Q4: 如何查询单个图片的状态？

**回答：**

```bash
# 使用 MySQL
mysql image_security -e "SELECT id, bucket_name, object_key, blocked, is_violation FROM image_scan_records WHERE id=123"

# 或用命令行
python handle_violations.py list-private
python handle_violations.py list-quarantined
```

---

### Q5: 误删了怎么办？

**回答：** 

- 如果只是删了 MinIO 对象（隔离桶）：数据库记录仍在，可重新上传文件
- 如果执行了 `delete` 命令：数据库记录已删除，**不可恢复**

**建议：** 定期备份数据库 `image_scan_records` 表。

```bash
mysqldump image_security image_scan_records > backup_$(date +%Y%m%d).sql
```

---

### Q6: 如何只处理某个类型的违规？

**回答：** 使用 `--type` 过滤：

```bash
# 列出所有赌博类
python handle_violations.py list --type gambling

# 标记所有赌博类为私密
python handle_violations.py mark-private --type gambling

# 隔离所有赌博类（仅限观察中的）
# 先查看
python handle_violations.py list-private --type gambling
# 根据 ID 隔离
python handle_violations.py confirm-quarantine --ids 1,2,3,4,5
```

---

### Q7: 置信度阈值怎么设置？

**回答：** 根据违规类型和业务容忍度：

```bash
# 严格模式：0.9 以上的赌博才处理
python handle_violations.py mark-private --type gambling --confidence 0.9

# 宽松模式：0.7 以上就标记
python handle_violations.py mark-private --type gambling --confidence 0.7
```

推荐：
- 明显违规（赌博、暴力）：≥0.8
- 边界情况（色情、广告）：≥0.85
- 不确定的：先观察，再决定

---

### Q8: 如何批量处理指定 ID？

**回答：** 使用 `--ids` 参数，逗号分隔：

```bash
# 标记 ID 为 1,5,10,15 的图片为私密
python handle_violations.py mark-private --ids 1,5,10,15

# 隔离 ID 为 20,21,22 的图片
python handle_violations.py confirm-quarantine --ids 20,21,22

# 删除 ID 为 30,31,32 的图片
python handle_violations.py delete --ids 30,31,32
```

---

## 故障排查

### 1. 数据库连接失败

**错误信息：**
```
mysql.connector.errors.DatabaseError: Access denied for user 'root'@'localhost'
```

**排查步骤：**
1. 检查 MySQL 是否运行
2. 检查 `.env` 中的 `MYSQL_PASSWORD` 是否正确
3. 检查数据库是否存在：
   ```bash
   mysql -u root -p -e "SHOW DATABASES;"
   ```
4. 重新创建数据库（如果丢失）：
   ```bash
   mysql -u root -p < schema.sql
   ```

---

### 2. MinIO 连接失败

**错误信息：**
```
minio.error.S3Error: Access Denied. User: ...
```

**排查步骤：**
1. 检查 MinIO 是否运行
2. 检查 `.env` 中的 `MINIO_ENDPOINT` 是否正确
3. 检查 `MINIO_ACCESS_KEY` 和 `MINIO_SECRET_KEY` 是否正确
4. 检查网络连接：
   ```bash
   curl http://localhost:9000 -v
   ```

---

### 3. 权限不足

**错误信息：**
```
S3Error: Access Denied when trying to set object private
```

**排查步骤：**
1. 确保 MinIO 用户有足够权限
2. 检查隔离桶是否存在且有写权限
3. 重新创建隔离桶：
   ```bash
   # 在 MinIO console 或 CLI 中
   mc rm -r --dangerous minio/quarantine
   mc mb minio/quarantine
   ```

---

### 4. 日志位置

所有日志都在 `logs/` 目录：

- `logs/scan.log` - 扫描日志
- `logs/error.log` - 错误日志
- `logs/violations.log` - 违规处置日志

**查看最新日志：**
```bash
tail -f logs/violations.log
```

---

### 5. 干运行验证

所有命令都支持 `--dry-run`，不实际执行，仅显示预期效果：

```bash
# 验证会标记哪些图片
python handle_violations.py mark-private --type gambling --dry-run

# 验证会隔离哪些图片
python handle_violations.py confirm-quarantine --ids 1,2,3 --dry-run

# 验证会删除哪些图片
python handle_violations.py delete --ids 10,11,12 --dry-run
```

**务必先 dry-run，再实际执行。**

---

## 最佳实践总结

1. **始终先 dry-run**
   ```bash
   python handle_violations.py mark-private --type xxx --dry-run
   ```

2. **观察期充分验证**（建议 24-48 小时）
   - 监控应用日志
   - 检查用户反馈
   - 确认无业务影响

3. **分类处理**
   ```bash
   # 先处理高置信度的
   python handle_violations.py mark-private --type gambling --confidence 0.95
   ```

4. **定期备份数据库**
   ```bash
   mysqldump image_security image_scan_records > backup_$(date +%Y%m%d).sql
   ```

5. **监控隔离桶大小**
   ```bash
   # MinIO CLI
   mc du minio/quarantine
   ```

6. **定期清理过期隔离**
   - 建议隔离 30 天后执行 delete
   - 或基于业务规定的保留期

---

## 相关文档

- [`VIOLATIONS_WORKFLOW.md`](VIOLATIONS_WORKFLOW.md) - 三阶段工作流详解
- [`README.md`](README.md) - 项目概述
- [MinIO 文档](https://min.io/docs/minio/linux/index.html)
- [MySQL 文档](https://dev.mysql.com/doc/)
- [腾讯云 IMS 文档](https://cloud.tencent.com/document/product/1125)

---

**最后更新：2026-05-19**
