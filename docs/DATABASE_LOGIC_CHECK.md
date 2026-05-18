# 数据库结构与程序逻辑对比检查报告

## 📅 检查时间
**2026-05-16**

---

## ❌ 发现的严重问题

### 问题1: upsert_record 逻辑错误 ⚠️⚠️⚠️

#### 问题描述

**数据库约束**:
```sql
UNIQUE KEY uk_bucket_object (bucket_name, object_key(255))
```

**当前代码逻辑** (database.py 第338-373行):
```python
def upsert_record(self, record: Dict) -> int:
    existing = self.find_by_key(record['key'])  # ❌ 错误：按 key 查找
    
    if existing:
        # 更新现有记录
        updates = {...}
        self.update_record(record['key'], updates)  # ❌ 按 key 更新
        return existing['id']
    else:
        # 插入新记录
        return self.insert_record(record)  # ❌ 可能触发唯一约束冲突
```

#### 问题分析

**场景1: 同一路径重复扫描**
```
第一次: bucket='test', path='a.jpg', key='abc123' → INSERT 成功
第二次: bucket='test', path='a.jpg', key='abc123' 
  → find_by_key('abc123') 找到记录
  → update_record('abc123', ...) 更新成功 ✅
  
结果: 正常（巧合）
```

**场景2: 相同内容不同路径**
```
第一次: bucket='test', path='folder1/a.jpg', key='abc123' → INSERT 成功
第二次: bucket='test', path='folder2/b.jpg', key='abc123'
  → find_by_key('abc123') 找到第一条记录
  → update_record('abc123', ...) 更新第一条记录 ❌
  → folder2/b.jpg 的记录丢失！
  
结果: **数据错误** ❌
```

**场景3: 并发插入**
```
线程1: INSERT INTO ... (bucket='test', object_key='a.jpg')
线程2: INSERT INTO ... (bucket='test', object_key='a.jpg')

如果两个线程同时执行 find_by_key，都返回 None
→ 两个线程都执行 INSERT
→ 第二个 INSERT 触发唯一约束冲突 ❌

结果: **程序崩溃** ❌
```

---

#### 正确的实现

应该使用 MySQL 的 `INSERT ... ON DUPLICATE KEY UPDATE` 语法：

```python
def upsert_record(self, record: Dict) -> int:
    """
    插入或更新记录（基于 bucket_name + object_key 唯一约束）
    """
    query = """
        INSERT INTO image_scan_records (
            `key`, feature_hash, feature_hash_dhash, feature_hash_ahash,
            feature_hash_phash, bucket_name, object_key, file_size,
            content_type, is_violation, violation_type, violation_label,
            violation_description, confidence, suggestion, ims_result,
            ims_request_id, scan_status, error_message, last_scanned_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            `key` = VALUES(`key`),
            feature_hash = VALUES(feature_hash),
            feature_hash_dhash = VALUES(feature_hash_dhash),
            feature_hash_ahash = VALUES(feature_hash_ahash),
            feature_hash_phash = VALUES(feature_hash_phash),
            is_violation = VALUES(is_violation),
            violation_type = VALUES(violation_type),
            violation_label = VALUES(violation_label),
            violation_description = VALUES(violation_description),
            confidence = VALUES(confidence),
            suggestion = VALUES(suggestion),
            ims_result = VALUES(ims_result),
            ims_request_id = VALUES(ims_request_id),
            scan_status = VALUES(scan_status),
            error_message = VALUES(error_message),
            last_scanned_at = NOW(),
            updated_at = NOW()
    """
    
    params = (
        record.get('key'),
        record.get('feature_hash'),
        record.get('feature_hash_dhash'),
        record.get('feature_hash_ahash'),
        record.get('feature_hash_phash'),
        record.get('bucket_name'),
        record.get('object_key'),
        record.get('file_size'),
        record.get('content_type'),
        record.get('is_violation', 0),
        record.get('violation_type'),
        record.get('violation_label'),
        record.get('violation_description'),
        record.get('confidence'),
        record.get('suggestion'),
        json.dumps(record.get('ims_result')) if record.get('ims_result') else None,
        record.get('ims_request_id'),
        record.get('scan_status', 'completed'),
        record.get('error_message'),
        record.get('last_scanned_at', datetime.now())
    )
    
    record_id = self.execute_query(query, params)
    return record_id
```

---

### 问题2: 缺少 first_seen_at 字段处理 ⚠️

#### 问题描述

**数据库定义**:
```sql
first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '首次发现时间',
```

**程序代码**:
- ❌ scanner.py 中从未设置 `first_seen_at`
- ❌ database.py 的 insert_record 和 upsert_record 都不包含此字段

#### 影响

- `first_seen_at` 会使用默认值 `CURRENT_TIMESTAMP`
- 对于新插入的记录没问题
- 但对于 upsert 操作，无法区分"首次发现"和"最后扫描"

#### 建议修复

在 insert_record 中添加：
```python
query = """
    INSERT INTO image_scan_records (
        ..., first_seen_at, last_scanned_at
    ) VALUES (
        ..., %s, %s
    )
"""

params = (
    ...,
    record.get('first_seen_at', datetime.now()),  # 首次发现时间
    record.get('last_scanned_at', datetime.now())  # 最后扫描时间
)
```

在 upsert_record 中：
```sql
ON DUPLICATE KEY UPDATE
    ...
    first_seen_at = COALESCE(first_seen_at, VALUES(first_seen_at)),  -- 保持原值
    last_scanned_at = NOW()  -- 更新时间
```

---

### 问题3: update_record 方法设计缺陷 ⚠️

#### 问题描述

**当前实现** (database.py 第300-336行):
```python
def update_record(self, key: str, updates: Dict) -> bool:
    query = f"UPDATE image_scan_records SET ... WHERE `key` = %s"
```

**问题**:
1. ❌ 按 `key` 更新，但唯一约束是 `(bucket_name, object_key)`
2. ❌ 如果同一个 key 有多个路径，会更新所有路径的记录
3. ❌ 这个方法在 upsert_record 中使用，但逻辑不匹配

#### 建议

**方案A**: 删除此方法，统一使用 upsert_record

**方案B**: 修改为按 `(bucket_name, object_key)` 更新
```python
def update_record_by_path(self, bucket_name: str, object_key: str, updates: Dict) -> bool:
    query = f"UPDATE image_scan_records SET ... WHERE bucket_name = %s AND object_key = %s"
    params = [..., bucket_name, object_key]
```

---

## ✅ 正确的部分

### 1. 三层去重逻辑 ✅

**步骤3: 路径去重**
```python
existing_path = db.find_by_bucket_object(bucket_name, object_name)
if existing_path and not force_rescan:
    return  # ✅ 完全跳过
```
- ✅ 正确使用 `bucket + object_key` 查询
- ✅ 同一路径完全跳过

**步骤5: 内容去重**
```python
existing_same_content = db.find_by_key(key)
if existing_same_content and not force_rescan:
    # ✅ 复用结果，插入新路径
    db.upsert_record(record)
```
- ✅ 正确使用 `key` 查找相同内容
- ✅ 保留所有路径信息

**步骤6: 相似去重**
```python
similar_scanned = db.find_similar_scanned(features['phash'], max_distance=5)
if similar_scanned and distance <= 3:
    # ✅ 复用相似图片的结果
    record = {
        'is_violation': 1 if most_similar.get('is_violation') else 0,
        ...
    }
```
- ✅ 查找所有已扫描图片（不只是违规）
- ✅ 正确复用违规状态

---

### 2. 特征缓存策略 ✅

**缓存加载**:
```python
scanned_images = self.db.get_all_scanned_images(limit=...)
for record in scanned_images:
    self.feature_cache[feature_hash].append(record)
```
- ✅ 加载所有已扫描图片
- ✅ 支持 LRU 策略限制大小

**缓存更新**:
```python
def _add_to_feature_cache(self, record: Dict):
    # ✅ 所有扫描过的图片都加入缓存
    self.feature_cache[feature_hash].append(record)
```
- ✅ 移除了"只缓存违规"的限制

---

### 3. 数据库索引 ✅

```sql
UNIQUE KEY uk_bucket_object (bucket_name, object_key(255))  -- ✅ 路径去重
INDEX idx_key (`key`)  -- ✅ 内容去重
INDEX idx_feature_hash (feature_hash)  -- ✅ 相似检测
INDEX idx_is_violation (is_violation)  -- ✅ 违规查询
INDEX idx_blocked (blocked)  -- ✅ Block状态查询
```

所有必要的索引都已创建。

---

## 🔧 需要修复的代码

### 修复1: database.py - upsert_record 方法

**文件**: `/Users/macbook/imsminioimgs/database.py`  
**位置**: 第338-373行

**当前代码**:
```python
def upsert_record(self, record: Dict) -> int:
    existing = self.find_by_key(record['key'])
    
    if existing:
        updates = {...}
        self.update_record(record['key'], updates)
        return existing['id']
    else:
        return self.insert_record(record)
```

**修复后**:
```python
def upsert_record(self, record: Dict) -> int:
    """
    插入或更新记录（基于 bucket_name + object_key 唯一约束）
    使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE 语法
    """
    query = """
        INSERT INTO image_scan_records (
            `key`, feature_hash, feature_hash_dhash, feature_hash_ahash,
            feature_hash_phash, bucket_name, object_key, file_size,
            content_type, is_violation, violation_type, violation_label,
            violation_description, confidence, suggestion, ims_result,
            ims_request_id, scan_status, error_message, last_scanned_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            `key` = VALUES(`key`),
            feature_hash = VALUES(feature_hash),
            feature_hash_dhash = VALUES(feature_hash_dhash),
            feature_hash_ahash = VALUES(feature_hash_ahash),
            feature_hash_phash = VALUES(feature_hash_phash),
            is_violation = VALUES(is_violation),
            violation_type = VALUES(violation_type),
            violation_label = VALUES(violation_label),
            violation_description = VALUES(violation_description),
            confidence = VALUES(confidence),
            suggestion = VALUES(suggestion),
            ims_result = VALUES(ims_result),
            ims_request_id = VALUES(ims_request_id),
            scan_status = VALUES(scan_status),
            error_message = VALUES(error_message),
            last_scanned_at = NOW(),
            updated_at = NOW()
    """
    
    params = (
        record.get('key'),
        record.get('feature_hash'),
        record.get('feature_hash_dhash'),
        record.get('feature_hash_ahash'),
        record.get('feature_hash_phash'),
        record.get('bucket_name'),
        record.get('object_key'),
        record.get('file_size'),
        record.get('content_type'),
        record.get('is_violation', 0),
        record.get('violation_type'),
        record.get('violation_label'),
        record.get('violation_description'),
        record.get('confidence'),
        record.get('suggestion'),
        json.dumps(record.get('ims_result')) if record.get('ims_result') else None,
        record.get('ims_request_id'),
        record.get('scan_status', 'completed'),
        record.get('error_message'),
        record.get('last_scanned_at', datetime.now())
    )
    
    record_id = self.execute_query(query, params)
    logger.debug(f"Upsert记录成功，ID: {record_id}")
    return record_id
```

---

### 修复2: database.py - 添加 first_seen_at 处理

**文件**: `/Users/macbook/imsminioimgs/database.py`  
**位置**: insert_record 和 upsert_record 方法

在 INSERT 语句中添加 `first_seen_at` 字段，在 UPDATE 中保持原值。

---

### 修复3: database.py - 考虑删除或重构 update_record

**选项A**: 删除 `update_record` 方法，统一使用 `upsert_record`

**选项B**: 重命名为 `update_record_by_key`，明确其用途

---

## 📊 总结

### 严重问题（必须修复）

| 问题 | 严重程度 | 影响 | 修复优先级 |
|------|---------|------|-----------|
| upsert_record 逻辑错误 | 🔴 严重 | 数据丢失、程序崩溃 | **立即修复** |
| 缺少 first_seen_at 处理 | 🟡 中等 | 时间戳不准确 | 尽快修复 |
| update_record 设计缺陷 | 🟡 中等 | 可能更新错误记录 | 建议修复 |

### 正确的部分

- ✅ 三层去重逻辑完整且正确
- ✅ 特征缓存策略优化到位
- ✅ 数据库索引设计合理
- ✅ 相似图片复用逻辑正确

---

## 🎯 建议的修复顺序

1. **立即修复**: upsert_record 方法（使用 ON DUPLICATE KEY UPDATE）
2. **尽快修复**: 添加 first_seen_at 字段处理
3. **可选优化**: 重构或删除 update_record 方法

---

**检查完成时间**: 2026-05-16  
**检查人**: AI Assistant  
**状态**: ⚠️ 发现严重问题，需要立即修复
