# 数据库设计

## 概述

系统使用 **MySQL** 作为数据存储，核心表是 `image_scan_records`，记录每张图片的扫描和处置状态。

## 数据库和表结构

### 创建数据库

```bash
# 方法 1：直接执行 SQL 脚本
mysql -u root -p < schema.sql

# 方法 2：手动创建
mysql -u root -p
CREATE DATABASE image_security CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE image_security;
SOURCE schema.sql;
```

### image_scan_records 表

**字段说明**：

| 字段 | 类型 | NULL | 默认值 | 说明 |
|------|------|------|--------|------|
| `id` | BIGINT | NO | 自增 | 主键，自增 ID |
| `key` | VARCHAR(128) | NO | - | 内容唯一标识：MD5(内容) - 文件大小，用于去重 |
| `bucket_name` | VARCHAR(255) | NO | - | MinIO 桶名 |
| `object_key` | VARCHAR(512) | NO | - | MinIO 对象键（路径） |
| `content_type` | VARCHAR(128) | YES | NULL | MIME 类型（如 image/jpeg） |
| `file_size` | BIGINT | YES | NULL | 文件大小（字节） |
| `feature_hash` | VARCHAR(64) | YES | NULL | 感知哈希（phash），用于相似检测 |
| `is_violation` | TINYINT | NO | 0 | 是否违规：0=否，1=是 |
| `violation_type` | VARCHAR(50) | YES | NULL | 违规类型：gambling/porn/violence/politics/terrorism/ads/contraband/vulgar/qrcode |
| `violation_label` | VARCHAR(100) | YES | NULL | 违规细分标签 |
| `confidence` | DECIMAL(5,4) | YES | 0.0000 | 置信度：0.0000-1.0000（由腾讯云 IMS 返回） |
| `suggestion` | VARCHAR(20) | YES | NULL | IMS 建议：review/block 等 |
| `blocked` | TINYINT | NO | 0 | **处置状态**：0=public，1=private，2=quarantined |
| `scan_status` | VARCHAR(20) | NO | pending | 扫描状态：pending/scanning/completed/failed |
| `ims_result` | JSON | YES | NULL | 腾讯云 IMS 原始返回结果（完整 JSON） |
| `error_message` | TEXT | YES | NULL | 扫描失败时的错误信息 |
| `error_retry_count` | INT | NO | 0 | 失败重试次数 |
| `first_seen_at` | DATETIME | YES | 当前时间 | 图片首次发现时间 |
| `last_scanned_at` | DATETIME | YES | NULL | 最后一次扫描时间 |
| `created_at` | DATETIME | NO | 当前时间 | 记录创建时间 |
| `updated_at` | DATETIME | NO | 当前时间 on update | 记录最后更新时间 |

### 关键索引

```sql
-- 同一路径唯一
UNIQUE KEY uk_bucket_object (bucket_name, object_key(255))

-- 快速查询违规图片
INDEX idx_is_violation (is_violation)

-- 快速查询处置状态
INDEX idx_blocked (blocked)

-- 相似图片检测
INDEX idx_feature_hash (feature_hash)

-- 按违规类型查询
INDEX idx_violation_type (violation_type)

-- 按扫描状态查询
INDEX idx_scan_status (scan_status)

-- 按创建时间查询（常用于日志分析）
INDEX idx_created_at (created_at)
```

## 关键字段解释

### key 字段（内容标识）

**构成**：`md5(file_content) + '-' + file_size`

**用途**：
- 同一内容不同路径时的复用判断（第 2 层去重）
- 确保相同内容在扫描后只需调用一次 IMS

**示例**：
```
原图：file_a.jpg (1MB)  → key = "abc123def456-1048576"
副本：file_b.jpg (1MB，内容相同）→ 同一个 key，直接复用扫描结果
```

### feature_hash 字段（感知哈希）

**类型**：phash（知觉哈希）

**用途**：
- 相似图片检测（第 3 层去重）
- 根据汉明距离找相似图片，距离 ≤ 3 认为相似

**示例**：
```
原图：photo_1.jpg → phash = "8f4a5e2c1b9d7f3a"
类似：photo_2.jpg → phash = "8f4a5e2c1b9d7f3c"（仅1位不同）
距离 = 1，认为相似，复用原图的扫描结果
```

### blocked 字段（处置状态）

**三个状态**：

| 值 | 状态 | 说明 | 可逆性 |
|----|------|------|--------|
| 0 | public（未处理） | 图片正常或已恢复 | - |
| 1 | private（隐藏观察） | 标记为私密，无法公开访问 | 可恢复为 0（restore-public） |
| 2 | quarantined（已隔离） | 已移到隔离桶 | **不可逆**，仅能删除 |

**状态转移图**：
```
扫描发现违规 (is_violation=1, blocked=0)
            ↓
[mark-private] → blocked=1 (观察期)
            ↓
    ┌─────┴─────┐
    ↓           ↓
[confirm-quarantine] [restore-public]
    ↓                ↓
 blocked=2        blocked=0
(已隔离)          (已恢复)
    ↓
[delete]
    ↓
记录删除
```

### scan_status 字段

**状态值**：
- `pending`：待扫描
- `scanning`：正在扫描
- `completed`：扫描完成
- `failed`：扫描失败

用于跟踪每次扫描的进度。

### ims_result 字段

**内容**：腾讯云 IMS API 的完整返回结果（JSON 格式）

**示例**：
```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "suggestion": "block",
    "label": 10,
    "confidence": 95,
    "details": {
      "porn": { "confidence": 5 },
      "gambling": { "confidence": 95 },
      "violence": { "confidence": 10 }
    }
  }
}
```

## 查询示例

### 查看新增违规

```sql
SELECT id, object_key, violation_type, confidence, created_at
FROM image_scan_records
WHERE is_violation = 1 AND blocked = 0
ORDER BY created_at DESC;
```

### 查看观察中的图片

```sql
SELECT id, object_key, violation_type, created_at
FROM image_scan_records
WHERE blocked = 1
ORDER BY created_at ASC;
```

### 查看已隔离的图片

```sql
SELECT id, object_key, violation_type, created_at
FROM image_scan_records
WHERE blocked = 2
ORDER BY created_at DESC;
```

### 查找相似的图片

```sql
-- 找距离不超过 3 的所有相似图片
SELECT id, object_key, feature_hash,
       BIT_COUNT(CONV(feature_hash, 16, 2) ^ CONV('8f4a5e2c1b9d7f3a', 16, 2)) as distance
FROM image_scan_records
HAVING distance <= 3
ORDER BY distance;
```

### 统计违规类型

```sql
SELECT violation_type, COUNT(*) as count, AVG(confidence) as avg_confidence
FROM image_scan_records
WHERE is_violation = 1 AND blocked IN (0, 1)
GROUP BY violation_type
ORDER BY count DESC;
```

## 性能优化建议

### 1. 索引优化

对于大规模数据，建议额外添加：

```sql
-- 复合索引：快速查询违规+处置状态
CREATE INDEX idx_violation_blocked ON image_scan_records(is_violation, blocked);

-- 复合索引：快速查询特定类型的违规
CREATE INDEX idx_type_blocked ON image_scan_records(violation_type, blocked);

-- 分区索引（如果超过 1 亿条记录）
ALTER TABLE image_scan_records PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);
```

### 2. 字段优化

- `key` 字段由于经常用于查询，确保有索引
- `feature_hash` 用于相似检测，建议加索引
- 考虑给 `created_at` 加索引用于日志查询

### 3. 数据清理

```sql
-- 清理 90 天前删除的隔离数据
DELETE FROM image_scan_records
WHERE blocked = 2 AND updated_at < DATE_SUB(NOW(), INTERVAL 90 DAY);
```

## 备份和恢复

### 备份数据库

```bash
mysqldump -u root -p image_security > backup.sql
```

### 恢复数据库

```bash
mysql -u root -p image_security < backup.sql
```

---

← [INDEX](./INDEX.md) | [ARCHITECTURE](./ARCHITECTURE.md) →
