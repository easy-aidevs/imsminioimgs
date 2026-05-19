# 数据库和代码比对审计报告

## 概述
比对 `schema.sql`、`scanner.py`、`database.py` 和 `minio_client.py`，发现了 **6个字段/逻辑问题**。

---

## 问题清单

### 🔴 **问题1：缺少 content_type 字段填充**
**严重性**：高  
**位置**：`scanner.py:_build_record_base()` 和 `_process_one()`

**现象**：
```python
# scanner.py:_build_record_base() - 第279-291行
def _build_record_base(self, bucket, object_name, image_data, key, feats):
    return {
        'key': key,
        'feature_hash': feats['phash'],
        # ...
        'file_size': len(image_data),
        # ❌ 缺少 'content_type': ???
    }
```

**数据库定义**：
```sql
content_type VARCHAR(128) DEFAULT NULL COMMENT 'MIME类型'
```

**影响**：
- 所有扫描记录的 `content_type` 都是 NULL
- 无法根据文件类型分析（如只扫描JPG，跳过PNG）
- 存储、带宽优化无法进行

**修复方案**：
- 改进 `minio_client.py:get_object_data()` 返回 content_type
- 在 `_process_one()` 中获取并传递 content_type

---

### 🟡 **问题2：whash特征被计算但未存储（浪费）**
**严重性**：中  
**位置**：`image_feature.py` vs `scanner.py`

**现象**：
```python
# image_feature.py:extract_features() - 第81-86行
try:
    whash = imagehash.whash(image, hash_size=self.hash_size)
    features['whash'] = str(whash)  # ✅ 计算了
except Exception as e:
    features['whash'] = features['phash']
```

但数据库没有 `feature_hash_whash` 列，代码也没有存储。

**影响**：
- whash 计算浪费 CPU 资源（whash 比 phash 慢）
- 未来想用 whash 时，需要重新扫描所有图片
- 可以用多种算法的组合提高准确度

**修复方案**：
1. **删除**：如果不需要 whash，注释掉计算代码
2. **存储**：如果需要，在数据库添加 `feature_hash_whash` 列并存储

**推荐**：删除，phash + dhash + ahash 已足够，whash 加不了太多价值。

---

### 🔴 **问题3：第3层统计逻辑不一致**
**严重性**：高  
**位置**：`scanner.py:_process_one()` 第239-262行

**现象**：
```python
# 第1层：路径去重
if existing:
    self.stats['skipped'] += 1  # ✅ 计入跳过
    return

# 第2层：内容去重
if same_content:
    self._write_reused(...)
    self.stats['skipped'] += 1  # ✅ 计入跳过
    return

# 第3层：特征相似
if similar and similar[0]['hash_distance'] <= SIMILAR_DISTANCE_REUSE:
    self._write_reused(...)
    self.stats['api_saved'] += 1
    self.stats['reused'] += 1
    # ❌ 没有计入 'skipped'！
    return
```

**问题**：
- 第1层和第2层计入 `stats['skipped']`
- 第3层没有计入
- 导致统计值不一致：`total ≠ skipped + scanned + errors`

**修复方案**：
第3层也应该计入 skipped 或定义新的统计类别：
```python
# 选项1：和第1、2层保持一致
self.stats['skipped'] += 1

# 选项2：用新的统计
self.stats['feature_matched'] += 1
```

推荐**选项1**（保持语义一致）。

---

### 🟡 **问题4：缓存加载缺少字段完整性检查**
**严重性**：中  
**位置**：`scanner.py:_load_scanned_to_cache()` 第84-107行

**现象**：
```python
def _load_scanned_to_cache(self):
    scanned_images = self.db.get_all_scanned_images(limit=...)
    for record in scanned_images:
        feature_hash = record.get('feature_hash')
        if feature_hash:
            # ❌ 只检查了 feature_hash，没检查其他必需字段
            self.feature_cache[feature_hash].append(record)
```

**问题**：
- 缓存中的记录可能缺少 `is_violation`、`violation_type` 等字段
- 在 `_write_reused()` 中使用缓存记录时可能报错
- 没有验证缓存记录的完整性

**修复方案**：
```python
def _is_complete_record(self, record):
    """检查记录是否包含必需的字段"""
    required = ['key', 'bucket_name', 'object_key', 'feature_hash', 
                'is_violation', 'violation_type', 'violation_label']
    return all(k in record for k in required)

# 在 _load_scanned_to_cache 中使用
if feature_hash and self._is_complete_record(record):
    self.feature_cache[feature_hash].append(record)
```

---

### 🔴 **问题5：minio_client.get_object_data() 没有返回 content_type**
**严重性**：高  
**位置**：`minio_client.py:get_object_data()` 第53-60行

**现象**：
```python
def get_object_data(self, bucket_name: str, object_name: str) -> bytes:
    """下载对象内容到内存。"""
    response = self.client.get_object(bucket_name, object_name)
    # ❌ 只返回了data，没有返回metadata（包含content_type）
    return response.read()
```

但在 `list_objects()` 中有 `object_info` 对象包含 content_type。

**影响**：
- 无法获取文件的 MIME 类型
- scanner 无法填充 content_type 字段
- 数据库记录不完整

**修复方案**：
改进 `minio_client.py`：
```python
def get_object_data(self, bucket_name: str, object_name: str) -> Tuple[bytes, Dict]:
    """下载对象内容和元数据到内存。返回 (data, metadata)"""
    response = self.client.get_object(bucket_name, object_name)
    try:
        data = response.read()
        metadata = {
            'content_type': response.content_type,
            'last_modified': response.last_modified,
            'size': response.size,
        }
        return data, metadata
    finally:
        response.close()
        response.release_conn()
```

然后在 `scanner.py` 中改为：
```python
image_data, metadata = self.minio.get_object_data(bucket, object_name)
feats = self.features.extract_features(image_data)
content_type = metadata.get('content_type', 'application/octet-stream')
```

---

### 🟡 **问题6：_record_error 中缺少某些字段**
**严重性**：低  
**位置**：`scanner.py:_record_error()` 第316-332行

**现象**：
```python
def _record_error(self, bucket, object_name, err):
    try:
        self.db.upsert_record({
            'key': f"error-{path_hash}",
            'feature_hash': '',
            'bucket_name': bucket,
            'object_key': object_name,
            'file_size': 0,
            'scan_status': 'failed',
            'error_message': error_msg,
            'last_scanned_at': datetime.now(),
            # ❌ 缺少 content_type、blocked 等可选字段
        })
```

**问题**：
- 错误记录缺少 `content_type`、`is_violation` 等字段
- 虽然这些字段都有默认值，但不够完整

**修复方案**：
```python
self.db.upsert_record({
    'key': f"error-{path_hash}",
    'feature_hash': '',
    'feature_hash_dhash': '',
    'feature_hash_ahash': '',
    'feature_hash_phash': '',
    'bucket_name': bucket,
    'object_key': object_name,
    'file_size': 0,
    'content_type': None,  # ✅
    'is_violation': 0,  # ✅
    'blocked': 0,  # ✅
    'scan_status': 'failed',
    'error_message': error_msg,
    'last_scanned_at': datetime.now(),
})
```

---

## 优先级修复计划

| 优先级 | 问题 | 修复工作量 | 业务影响 |
|-------|------|---------|--------|
| 🔴 P1 | 缺少 content_type | 中 | 数据不完整，无法按类型筛选 |
| 🔴 P1 | 第3层统计逻辑 | 低 | 统计数据错误，难以定位问题 |
| 🔴 P1 | content_type 获取困难 | 中 | 无法填充数据库字段 |
| 🟡 P2 | whash 浪费 | 低 | 性能浪费，但非关键 |
| 🟡 P2 | 缓存完整性检查 | 低 | 低概率导致bug |
| 🟡 P3 | 错误记录字段 | 低 | 可选，有默认值 |

---

## 字段完整性对比表

```
字段名              | DB | scanner | database | 状态
─────────────────────────────────────────────
key                 | ✅ | ✅     | ✅      | ✅
feature_hash        | ✅ | ✅     | ✅      | ✅
feature_hash_dhash  | ✅ | ✅     | ✅      | ✅
feature_hash_ahash  | ✅ | ✅     | ✅      | ✅
feature_hash_phash  | ✅ | ✅     | ✅      | ✅
feature_hash_whash  | ❌ | ✅(浪费)| -       | ❌
bucket_name         | ✅ | ✅     | ✅      | ✅
object_key          | ✅ | ✅     | ✅      | ✅
file_size           | ✅ | ✅     | ✅      | ✅
content_type        | ✅ | ❌     | ✅      | ❌ 未填充
is_violation        | ✅ | ✅     | ✅      | ✅
violation_type      | ✅ | ✅     | ✅      | ✅
violation_label     | ✅ | ✅     | ✅      | ✅
violation_description| ✅ | ✅     | ✅      | ✅
confidence          | ✅ | ✅     | ✅      | ✅
suggestion          | ✅ | ✅     | ✅      | ✅
ims_result          | ✅ | ✅     | ✅      | ✅
ims_request_id      | ✅ | ✅     | ✅      | ✅
scan_status         | ✅ | ✅     | ✅      | ✅
error_message       | ✅ | ✅     | ✅      | ✅
blocked             | ✅ | ✅     | ✅      | ✅
first_seen_at       | ✅ | ✅(正确)| ✅      | ✅
last_scanned_at     | ✅ | ✅     | ✅      | ✅
created_at          | ✅ | 默认   | ✅      | ✅ (自动)
updated_at          | ✅ | 默认   | ✅      | ✅ (自动)
```

---

## 建议修复顺序

1. **即刻修复（本次）**：
   - P1: 第3层统计逻辑（1行代码）
   - P1: 改进 minio_client.get_object_data() 返回 metadata
   - P1: scanner._build_record_base() 填充 content_type

2. **后续修复**：
   - P2: 删除或存储 whash
   - P2: 缓存完整性检查
   - P3: 错误记录字段完整化
