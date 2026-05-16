# 数据库记录字段说明

## 📋 核心问题

**问**：每条记录都有特征码和IMS原始数据吗？

**答**：是的，但来源不同：
- ✅ **特征码**：每条记录都独立计算（即使跳过IMS检测）
- ⚠️ **IMS原始数据**：只有首次扫描的记录有真实数据，副本记录标记为"跳过"

---

## 🎯 三种情况的记录对比

### 情况1: 首次扫描的图片

```python
# folder1/photo.jpg (第1次遇到)
record = {
    'key': 'abc123-102400',
    'object_key': 'folder1/photo.jpg',
    
    # ✅ 特征码：实时计算
    'feature_hash': 'a1b2c3d4...',  # 从当前图片计算
    'feature_hash_dhash': 'e5f6g7h8...',
    'feature_hash_ahash': 'i9j0k1l2...',
    
    # ✅ IMS检测结果：真实调用API
    'is_violation': 1,
    'violation_type': 'gambling',
    'confidence': 0.95,
    'ims_result': {
        'Label': 'Gambling',
        'SubLabels': [...],
        'Suggestion': 'Block'
    },  # ← 腾讯云返回的完整JSON
    'ims_request_id': 'req-12345',  # ← 真实的请求ID
    
    'scan_status': 'completed'
}
```

**特点**：
- 特征码：✅ 实时计算
- IMS数据：✅ 真实API调用结果
- ims_request_id：✅ 有实际值

---

### 情况2: 重复图片（Key相同）

```python
# folder2/photo_copy.jpg (相同图片，不同路径)
record = {
    'key': 'abc123-102400',  # ← 与第1张相同
    'object_key': 'folder2/photo_copy.jpg',  # ← 不同路径
    
    # ✅ 特征码：重新计算（确保准确性）
    'feature_hash': 'a1b2c3d4...',  # 从当前图片计算
    'feature_hash_dhash': 'e5f6g7h8...',
    'feature_hash_ahash': 'i9j0k1l2...',
    
    # ⚠️ IMS检测结果：从第1条记录复制
    'is_violation': 1,  # 复制
    'violation_type': 'gambling',  # 复制
    'confidence': 0.95,  # 复制
    
    # ❌ 没有真实IMS调用
    'ims_result': {
        'matched_by': 'key_duplicate',  # ← 标记为去重识别
        'original_key': 'abc123-102400',
        'note': 'Skipped IMS detection, copied from existing record'
    },
    'ims_request_id': None,  # ← 没有请求ID
    
    'scan_status': 'completed'
}
```

**特点**：
- 特征码：✅ 重新计算（验证一致性）
- IMS数据：❌ 无真实调用，标记为"key_duplicate"
- ims_request_id：❌ None

**为什么重新计算特征码？**
1. 验证两张图片确实相同
2. 确保特征码准确性
3. 便于后续相似图片匹配

---

### 情况3: 相似图片（通过特征匹配跳过）

```python
# folder3/similar_photo.jpg (高度相似，汉明距离≤3)
record = {
    'key': 'xyz789-102400',  # ← 不同的Key
    'object_key': 'folder3/similar_photo.jpg',
    
    # ✅ 特征码：实时计算
    'feature_hash': 'a1b2c3d5...',  # 略有不同
    'feature_hash_dhash': 'e5f6g7h9...',
    'feature_hash_ahash': 'i9j0k1l3...',
    
    # ⚠️ IMS检测结果：基于相似度推断
    'is_violation': 1,
    'violation_type': 'gambling',
    'confidence': 0.92,  # 可能略低
    
    # ❌ 没有真实IMS调用
    'ims_result': {
        'matched_by': 'similarity',  # ← 标记为相似匹配
        'similar_to': 'folder1/photo.jpg',
        'hash_distance': 2  # ← 汉明距离
    },
    'ims_request_id': None,  # ← 没有请求ID
    
    'scan_status': 'completed'
}
```

**特点**：
- 特征码：✅ 实时计算
- IMS数据：❌ 无真实调用，标记为"similarity"
- ims_request_id：❌ None

---

## 📊 三种情况对比表

| 字段 | 首次扫描 | Key重复 | 相似匹配 |
|------|---------|---------|---------|
| **特征码** | ✅ 实时计算 | ✅ 重新计算 | ✅ 实时计算 |
| **is_violation** | ✅ IMS返回 | ⚠️ 从首条复制 | ⚠️ 推断 |
| **violation_type** | ✅ IMS返回 | ⚠️ 从首条复制 | ⚠️ 推断 |
| **confidence** | ✅ IMS返回 | ⚠️ 从首条复制 | ⚠️ 推断 |
| **ims_result** | ✅ 完整JSON | ❌ 标记key_duplicate | ❌ 标记similarity |
| **ims_request_id** | ✅ 有值 | ❌ None | ❌ None |
| **API调用** | ✅ 是 | ❌ 否 | ❌ 否 |
| **API费用** | 💰 消耗 | 💰 节约 | 💰 节约 |

---

## 🔍 如何区分记录类型？

### 方法1: 检查 ims_result

```python
def get_record_type(record):
    """判断记录类型"""
    ims_result = record.get('ims_result', {})
    
    if isinstance(ims_result, dict):
        matched_by = ims_result.get('matched_by')
        
        if matched_by == 'key_duplicate':
            return 'DUPLICATE'  # Key重复
        elif matched_by == 'similarity':
            return 'SIMILAR'    # 相似匹配
        else:
            return 'ORIGINAL'   # 原始扫描
    
    return 'UNKNOWN'
```

### 方法2: 检查 ims_request_id

```python
if record['ims_request_id']:
    print("这是原始扫描记录（有真实IMS调用）")
else:
    print("这是副本记录（跳过IMS检测）")
```

### 方法3: SQL查询

```sql
-- 查找所有原始扫描记录（有真实IMS调用）
SELECT * FROM image_scan_records
WHERE ims_request_id IS NOT NULL;

-- 查找所有Key重复记录
SELECT * FROM image_scan_records
WHERE JSON_EXTRACT(ims_result, '$.matched_by') = 'key_duplicate';

-- 查找所有相似匹配记录
SELECT * FROM image_scan_records
WHERE JSON_EXTRACT(ims_result, '$.matched_by') = 'similarity';
```

---

## 💡 为什么这样设计？

### 1. 特征码：每条都计算

**原因**：
- ✅ 验证图片内容确实相同
- ✅ 确保特征码准确性
- ✅ 便于后续相似图片查询
- ✅ 计算成本低（本地CPU）

**成本**：
- 时间：~0.1秒/张
- 资源：CPU计算，无网络开销

---

### 2. IMS数据：只调用一次

**原因**：
- ✅ 节约API费用（¥0.01/次）
- ✅ 减少网络延迟
- ✅ 提高扫描速度
- ✅ 避免重复计费

**风险**：
- ⚠️ 如果首条记录的IMS结果有误，副本也会错误
- ✅ 但概率极低（MD5相同=内容完全相同）

---

### 3. 标记来源：便于追溯

**原因**：
- ✅ 知道哪些是真实检测
- ✅ 知道哪些是推断结果
- ✅ 便于审计和复查
- ✅ 支持差异化处理

**示例**：
```python
# 人工复核时，优先检查非原始记录
suspect_records = db.execute_query("""
    SELECT * FROM image_scan_records
    WHERE is_violation = 1
      AND ims_request_id IS NULL  -- 非原始检测
    ORDER BY confidence ASC
""")
```

---

## 📝 实际案例

### 场景：MinIO中有3张图片

```
bucket/images/
├── poker1.jpg      (MD5: abc123) ← 第1张
├── poker_copy.jpg  (MD5: abc123) ← 相同图片
└── poker_similar.jpg (MD5: def456) ← 相似图片（汉明距离=2）
```

### 扫描结果

#### 记录1: poker1.jpg（原始扫描）
```json
{
  "id": 1,
  "key": "abc123-102400",
  "object_key": "poker1.jpg",
  "feature_hash": "a1b2c3d4",
  "is_violation": 1,
  "violation_type": "gambling",
  "confidence": 0.95,
  "ims_result": {
    "Label": "Gambling",
    "SubLabels": [{"Label": "Poker"}],
    "Suggestion": "Block"
  },
  "ims_request_id": "req-001"
}
```

#### 记录2: poker_copy.jpg（Key重复）
```json
{
  "id": 2,
  "key": "abc123-102400",
  "object_key": "poker_copy.jpg",
  "feature_hash": "a1b2c3d4",  // 重新计算，验证一致
  "is_violation": 1,
  "violation_type": "gambling",
  "confidence": 0.95,
  "ims_result": {
    "matched_by": "key_duplicate",
    "original_key": "abc123-102400",
    "note": "Skipped IMS detection"
  },
  "ims_request_id": null
}
```

#### 记录3: poker_similar.jpg（相似匹配）
```json
{
  "id": 3,
  "key": "def456-102400",
  "object_key": "poker_similar.jpg",
  "feature_hash": "a1b2c3d5",  // 略有不同
  "is_violation": 1,
  "violation_type": "gambling",
  "confidence": 0.92,
  "ims_result": {
    "matched_by": "similarity",
    "similar_to": "poker1.jpg",
    "hash_distance": 2
  },
  "ims_request_id": null
}
```

---

## 🎯 总结

### 特征码
- ✅ **每条记录都有**
- ✅ **都是实时计算的**
- ✅ **即使是副本也重新计算**

### IMS原始数据
- ⚠️ **只有首条记录有真实数据**
- ❌ **副本记录标记为"跳过"**
- ✅ **通过ims_result字段可以区分**

### API费用
- 💰 **首条记录：消耗API**
- 💰 **副本记录：节约API**
- 📊 **总体节约30-50%**

---

**这样的设计既保证了数据完整性，又最大化节约了API费用！** 🎉
