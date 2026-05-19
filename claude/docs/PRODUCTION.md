# 生产部署指南

## 概述

本文档提供生产环境部署的最佳实践，确保系统的稳定性、安全性和可观测性。

## 架构规划

### 推荐架构

```
应用服务器
    ↓
MySQL (主从复制)
MinIO 集群
    ↑
扫描器 (定时任务)
处置工具 (人工触发)
```

### 关键组件

| 组件 | 推荐配置 | 说明 |
|------|---------|------|
| MySQL | 主从或集群 | 数据持久化和高可用 |
| MinIO | 分布式集群 | 对象存储高可用 |
| 扫描器 | 定时任务 | 每日或按需运行 |
| 处置工具 | 手动操作 | 人工审核后执行 |

## 环境配置

### 1. 环境变量管理

**生产环境专用配置文件**：

```bash
# .env.production
MYSQL_HOST=mysql-prod.internal.com
MYSQL_USER=app_user
MYSQL_PASSWORD=${MYSQL_PASSWORD}  # 从密钥管理系统读取
MYSQL_DATABASE=image_security_prod

MINIO_ENDPOINT=minio-cluster.internal.com:9000
MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY}
MINIO_SECRET_KEY=${MINIO_SECRET_KEY}
MINIO_BUCKET_NAME=images-prod
QUARANTINE_BUCKET_NAME=quarantine-prod

TENCENT_SECRET_ID=${TENCENT_SECRET_ID}
TENCENT_SECRET_KEY=${TENCENT_SECRET_KEY}

LOG_LEVEL=WARNING  # 生产环境使用 WARNING 或 ERROR
ENABLE_CONSOLE_LOG=false
```

**使用方式**：

```bash
export ENV_FILE=.env.production
python scanner.py
```

### 2. 数据库配置

#### 主从复制

```sql
-- 主数据库：创建复制用户
CREATE USER 'repl'@'slave-host' IDENTIFIED BY 'password';
GRANT REPLICATION SLAVE ON *.* TO 'repl'@'slave-host';

-- 从数据库：配置复制
CHANGE MASTER TO
  MASTER_HOST='master-host',
  MASTER_USER='repl',
  MASTER_PASSWORD='password',
  MASTER_LOG_FILE='mysql-bin.000001',
  MASTER_LOG_POS=123;
START SLAVE;
```

#### 连接池配置

在代码中配置 MySQL 连接池：

```python
# database.py
pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name='image_security',
    pool_size=10,
    pool_reset_session=True,
    host=os.getenv('MYSQL_HOST'),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DATABASE'),
)
```

### 3. MinIO 配置

#### TLS/SSL

启用 HTTPS：

```bash
MINIO_ENDPOINT=minio-prod.com:9000
MINIO_USE_SSL=true
MINIO_CERT_FILE=/path/to/cert.crt
MINIO_KEY_FILE=/path/to/key.key
```

#### 访问控制

```bash
# 创建专用访问密钥（IAM）
mc admin user add localhost app_user app_password
mc admin policy attach localhost readwrite --user=app_user
```

## 数据备份

### 1. MySQL 备份

**每日备份脚本**（`backup.sh`）：

```bash
#!/bin/bash
BACKUP_DIR="/backups/mysql"
DATE=$(date +%Y%m%d)

mysqldump -u root -p${MYSQL_PASSWORD} image_security \
  | gzip > ${BACKUP_DIR}/image_security_${DATE}.sql.gz

# 保留 30 天备份
find ${BACKUP_DIR} -name "*.sql.gz" -mtime +30 -delete
```

**Cron 任务**：

```bash
0 2 * * * /path/to/backup.sh
```

### 2. MinIO 备份

```bash
# 定期备份 MinIO 数据
mc mirror --watch minio/images /backup/images
```

## 监控和告警

### 1. 日志监控

**关键指标**：
- 扫描完成率
- 违规检出数
- API 调用失败率
- 处置操作成功率

**日志聚合**（使用 ELK Stack）：

```bash
# Filebeat 配置
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /app/logs/scan.log
    - /app/logs/violations.log
    - /app/logs/error.log
```

### 2. 健康检查

**Prometheus 监控**：

```python
# 在应用中暴露指标
from prometheus_client import Counter, Histogram

scan_total = Counter('scan_total', 'Total scans')
violations_total = Counter('violations_total', 'Total violations found')
scan_duration = Histogram('scan_duration_seconds', 'Scan duration')
```

### 3. 告警规则

**关键告警**：

| 告警 | 条件 | 行动 |
|------|------|------|
| 扫描失败 | `scan_status = failed` | 立即通知运维 |
| 数据库连接错误 | 连接失败次数 > 5 | 检查数据库状态 |
| API 配额不足 | IMS API 限流 | 等待恢复或增加配额 |
| 磁盘满 | 可用空间 < 10% | 清理旧日志和备份 |

## 性能优化

### 1. 数据库优化

```sql
-- 定期分析表
ANALYZE TABLE image_scan_records;

-- 定期整理碎片
OPTIMIZE TABLE image_scan_records;

-- 添加复合索引
CREATE INDEX idx_violation_blocked 
  ON image_scan_records(is_violation, blocked);
```

### 2. 扫描器优化

- **增量扫描**：只扫描新增对象（第 1 层去重）
- **缓存优化**：调整内存缓存大小
- **并发控制**：根据 IMS 配额调整并发数

### 3. 查询优化

```sql
-- 使用 LIMIT 分页查询违规图片，避免一次加载全部
SELECT * FROM image_scan_records 
WHERE is_violation = 1 AND blocked = 0
ORDER BY created_at DESC
LIMIT 0, 100;
```

## 安全最佳实践

### 1. 凭据管理

**不要**在代码中硬编码凭据：

```python
# ❌ 错误
MYSQL_PASSWORD = "password123"

# ✅ 正确
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
```

**使用密钥管理系统**（如 HashiCorp Vault）：

```python
import hvac

client = hvac.Client(url='https://vault.internal.com')
secret = client.secrets.kv.read_secret_version(path='image-security/prod')
MYSQL_PASSWORD = secret['data']['data']['mysql_password']
```

### 2. 网络隔离

```
互联网
  │
  ↓
[防火墙]
  │
  ├─→ 应用服务器 (VPC)
  │   ├─→ MySQL (内网)
  │   └─→ MinIO (内网)
  │
  └─→ 仅允许特定端口和 IP
```

### 3. 访问控制

```bash
# MinIO 策略：仅允许读写特定桶
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:GetObject", "s3:PutObject"],
      "Resource": ["arn:aws:s3:::images-prod", "arn:aws:s3:::images-prod/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::quarantine-prod", "arn:aws:s3:::quarantine-prod/*"]
    }
  ]
}
```

### 4. 日志安全

```bash
# 不要记录敏感信息
logger.info(f"API call successful")  # ✓
logger.info(f"API call with key: {secret_key}")  # ✗

# 定期归档和加密日志
tar -czf logs_encrypted.tar.gz logs/
gpg --encrypt logs_encrypted.tar.gz
```

## 运维流程

### 1. 每日检查清单

```bash
#!/bin/bash
# 每日检查脚本

# 检查 MySQL
mysql -u root -p${MYSQL_PASSWORD} -e "SELECT COUNT(*) FROM image_scan_records"

# 检查 MinIO
mc ls minio/images | head -5

# 检查日志错误
tail -10 logs/error.log

# 检查磁盘使用
df -h | grep -E "logs|data"
```

### 2. 定期维护任务

| 任务 | 频率 | 说明 |
|------|------|------|
| 数据备份 | 每日 | MySQL 完整备份 |
| 日志归档 | 每周 | 归档 30 天前的日志 |
| 数据库优化 | 每月 | ANALYZE 和 OPTIMIZE |
| 安全审计 | 每月 | 检查访问日志和权限 |
| 容量规划 | 每季度 | 评估存储和处理能力 |

### 3. 升级流程

```bash
# 1. 在测试环境验证
cd /opt/imsminioimgs/test
git pull origin main
python -m pytest tests/

# 2. 生成更新日志
git log --oneline <old-tag>..<new-tag> > CHANGELOG.txt

# 3. 在生产环境更新
cd /opt/imsminioimgs/prod
git pull origin main
python -m pytest tests/

# 4. 重启服务
systemctl restart imsminioimgs

# 5. 验证
curl http://localhost:9000/health
```

## 故障恢复

### 1. 数据库故障

```bash
# 使用从库切换
# 修改 MYSQL_HOST 指向从库
nano .env.production
export MYSQL_HOST=mysql-slave.internal.com

# 重启服务
systemctl restart imsminioimgs
```

### 2. MinIO 故障

```bash
# 检查集群状态
mc admin info minio-prod

# 恢复操作
# (根据 MinIO 故障排查文档)
```

### 3. 数据恢复

```bash
# 从备份恢复
mysql -u root -p < /backups/mysql/image_security_20260519.sql.gz
```

## 成本优化

### 1. 腾讯云 IMS 成本

- 利用三层去重机制最小化 API 调用
- 购买 IMS 月度套餐而不是按量计费
- 定期审计调用日志，优化检测策略

### 2. 存储成本

- 定期清理已删除的隔离图片
- 按照数据生命周期设置自动清理策略
- 考虑使用冷存储（如 S3 Glacier）存档历史数据

## 总结检查清单

部署到生产前，确保：

- [ ] 所有敏感信息使用环境变量或密钥管理系统
- [ ] MySQL 配置了主从复制或集群
- [ ] MinIO 启用了 TLS/SSL
- [ ] 设置了每日备份
- [ ] 配置了日志聚合和监控告警
- [ ] 配置了定时任务（scanner）
- [ ] 测试了故障转移和恢复流程
- [ ] 文档化了运维流程和紧急联系方式

---

← [INDEX](./INDEX.md) | [DOCKER](./DOCKER.md) →
