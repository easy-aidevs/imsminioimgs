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
| `quarantine_batch_id` | VARCHAR(64) | YES | NULL | **隔离批次ID**：quarantine 命令写入，手动指定或自动生成时间戳；同一批次ID可跨多次操作累积 |
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

-- 按批次查询/还原隔离图片
INDEX idx_quarantine_batch_id (quarantine_batch_id)

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
| 1 | private（隐藏观察） | 历史遗留，仍在原桶 | 可 quarantine 或忽略 |
| 2 | quarantined（已隔离） | 已物理移到隔离桶 | 可 restore 或 delete |

**状态转移图**：
```
扫描发现违规 (is_violation=1, blocked=0)
            ↓
[quarantine] → blocked=2（移入隔离桶）
            ↓
    ┌─────┴─────┐
    ↓           ↓
[restore]    [delete]
blocked=0    记录删除
（误判恢复）  （不可恢复）
```

### quarantine_batch_id 字段（隔离批次）

**类型**：`VARCHAR(64)`, 可为 NULL（历史记录或未指定批次的隔离）

**用途**：将多次 quarantine 操作归为同一批次，便于后续整批还原。

**两种来源**：

| 来源 | 格式示例 | 使用场景 |
|------|---------|---------|
| 自动生成（时间戳） | `20260520_143022` | 日常快速隔离，不需要语义标识 |
| 手动指定 | `gamble_wave1`、`ticket_0520_001` | 按类型/工单分批，需要整批还原 |

**跨操作累积**：同一批次ID可在多次 quarantine 中重复使用，所有使用该 ID 的记录构成同一批次：

```bash
# 第一次操作：隔离赌博图片
python handle_violations.py quarantine --sub-label Gamble --batch gamble_0520

# 第二次操作：再追加几张（同一批次ID）
python handle_violations.py quarantine --ids 10,11,12 --batch gamble_0520

# 两次操作的记录都属于 gamble_0520，可一次整批还原
python handle_violations.py restore --batch gamble_0520
```

**查询示例**：
```sql
-- 查看某批次的所有记录
SELECT id, bucket_name, object_key, violation_type, quarantine_batch_id
FROM image_scan_records
WHERE quarantine_batch_id = 'gamble_0520';

-- 查看所有批次及其数量
SELECT quarantine_batch_id, COUNT(*) AS cnt, MIN(updated_at) AS first_quarantined
FROM image_scan_records
WHERE blocked = 2 AND quarantine_batch_id IS NOT NULL
GROUP BY quarantine_batch_id
ORDER BY first_quarantined DESC;
```

### 新增列 SQL（运维执行）

> 此列在旧版表中不存在，**无需重建表，无需数据迁移**，直接在现有表上执行：

```sql
-- 新增 quarantine_batch_id 列及索引
ALTER TABLE image_scan_records
  ADD COLUMN quarantine_batch_id VARCHAR(64) NULL DEFAULT NULL
    COMMENT '隔离批次ID：quarantine 命令写入，支持手动指定（如 gamble_wave1）或自动生成（YYYYMMDD_HHMMSS）；同一批次ID可跨多次 quarantine 操作累积，便于整批还原'
    AFTER blocked,
  ADD INDEX idx_quarantine_batch_id (quarantine_batch_id);
```

> 已有的 blocked=2 记录 `quarantine_batch_id` 默认为 NULL，不影响正常使用（`restore --ids` 仍可处理这些历史记录）。

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
-- 全部已隔离
SELECT id, object_key, violation_type, violation_label, sub_label, quarantine_batch_id, updated_at
FROM image_scan_records
WHERE blocked = 2
ORDER BY updated_at DESC;

-- 按批次查看
SELECT id, object_key, violation_type, quarantine_batch_id
FROM image_scan_records
WHERE blocked = 2 AND quarantine_batch_id = 'gamble_0520';

-- 批次汇总（各批次数量和时间）
SELECT quarantine_batch_id, COUNT(*) AS cnt,
       MIN(updated_at) AS first_quarantined, MAX(updated_at) AS last_quarantined
FROM image_scan_records
WHERE blocked = 2 AND quarantine_batch_id IS NOT NULL
GROUP BY quarantine_batch_id
ORDER BY first_quarantined DESC;
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
