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
| `key` | VARCHAR(128) | NO | - | 内容唯一标识：MD5(内容)-文件大小，用于内容去重 |
| `feature_hash` | VARCHAR(64) | YES | NULL | 主感知哈希（pHash），用于相似检测 |
| `feature_hash_dhash` | VARCHAR(64) | YES | NULL | dHash |
| `feature_hash_ahash` | VARCHAR(64) | YES | NULL | aHash |
| `feature_hash_phash` | VARCHAR(64) | YES | NULL | pHash（冗余存储） |
| `bucket_name` | VARCHAR(255) | NO | - | MinIO 桶名 |
| `object_key` | VARCHAR(512) | NO | - | MinIO 对象键（路径） |
| `file_size` | BIGINT | YES | NULL | 文件大小（字节） |
| `content_type` | VARCHAR(128) | YES | NULL | MIME 类型（如 image/jpeg） |
| `is_violation` | TINYINT | NO | 0 | 是否违规：0=否，1=是 |
| `violation_type` | VARCHAR(50) | YES | NULL | 直接取 IMS SubLabel（如 Gambling/SexyBehavior），无 SubLabel 时取 Label（如 Porn/Terror） |
| `violation_label` | VARCHAR(50) | YES | NULL | IMS 一级 Label：Polity/Porn/Sexy/Terror/Illegal/Religion/Ad/Teenager/Abuse |
| `violation_label_cn` | VARCHAR(50) | YES | NULL | 一级 Label 中文名（政治/色情/性感/暴恐/违法/宗教识别/广告/未成年识别/谩骂） |
| `sub_label` | VARCHAR(100) | YES | NULL | IMS 二级 SubLabel：Gambling/SexyBehavior/NationalOfficial/Drug/Blood/QrCode/… |
| `sub_label_cn` | VARCHAR(100) | YES | NULL | 二级 SubLabel 中文名 |
| `confidence` | DECIMAL(5,4) | YES | 0.0000 | 置信度：0.0000–1.0000（由腾讯云 IMS Score/100 换算） |
| `suggestion` | VARCHAR(20) | YES | NULL | IMS 建议：Block/Review/Pass |
| `ims_result` | JSON | YES | NULL | 完整扫描结果（含 raw_result 和 request_id） |
| `ims_request_id` | VARCHAR(128) | YES | NULL | 腾讯云 IMS 请求 ID |
| `scan_status` | VARCHAR(20) | NO | pending | 扫描状态：pending/scanning/completed/failed |
| `error_message` | TEXT | YES | NULL | 扫描失败时的错误信息 |
| `blocked` | TINYINT | NO | 0 | **处置状态**：0=public，1=private，2=quarantined |
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

**类型**：pHash（知觉哈希，主字段）

**用途**：
- 相似图片检测（第 3 层去重）
- 根据汉明距离找相似图片，距离 ≤ 3 认为相似

**示例**：
```
原图：photo_1.jpg → phash = "8f4a5e2c1b9d7f3a"
类似：photo_2.jpg → phash = "8f4a5e2c1b9d7f3c"（仅1位不同）
距离 = 1，认为相似，复用原图的扫描结果
```

### violation_type / violation_label / sub_label 字段

这三个字段共同描述 IMS 的检测结果：

| 字段 | 来源 | 示例值 |
|------|------|-------|
| `violation_label` | IMS 一级 Label | `Illegal` |
| `violation_label_cn` | 中文名 | `违法` |
| `sub_label` | IMS 二级 SubLabel | `Gambling` |
| `sub_label_cn` | 中文名 | `赌博` |
| `violation_type` | sub_label（有则取），否则取 violation_label | `Gambling` |

**过滤查询示例**：
```sql
-- 按一级 Label 查（查所有"违法"内容，含赌博/毒品等）
SELECT * FROM image_scan_records WHERE violation_label = 'Illegal';

-- 按二级 SubLabel 查（精确到赌博）
SELECT * FROM image_scan_records WHERE sub_label = 'Gambling';

-- 按 violation_type 查（等同于 sub_label 有值时）
SELECT * FROM image_scan_records WHERE violation_type = 'Gambling';
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

**内容**：扫描完整结果（JSON 格式）

**示例**：
```json
{
  "matched_by": "ims_api",
  "raw_result": {
    "Suggestion": "Block",
    "Label": "Illegal",
    "SubLabel": "Gambling",
    "Score": 95,
    "LabelResults": [...],
    "ObjectResults": [...],
    "OcrResults": [...]
  },
  "request_id": "abc123xyz"
}
```

## 查询示例

### 查看新增违规

```sql
SELECT id, object_key, violation_type, violation_label, sub_label, confidence, created_at
FROM image_scan_records
WHERE is_violation = 1 AND blocked = 0
ORDER BY created_at DESC;
```

### 查看观察中的图片

```sql
SELECT id, object_key, violation_type, violation_label, sub_label_cn, created_at
FROM image_scan_records
WHERE blocked = 1
ORDER BY created_at ASC;
```

### 查看已隔离的图片

```sql
SELECT id, object_key, violation_type, violation_label, sub_label, created_at
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
SELECT violation_label, sub_label, COUNT(*) as count, AVG(confidence) as avg_confidence
FROM image_scan_records
WHERE is_violation = 1 AND blocked IN (0, 1)
GROUP BY violation_label, sub_label
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
