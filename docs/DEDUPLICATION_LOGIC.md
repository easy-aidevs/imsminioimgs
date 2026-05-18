# 图片扫描去重逻辑完整说明

## 🎯 Key的核心意义

### Key是什么？
```python
key = md5(文件内容) + "-" + 文件大小
```

**Key = 图片内容哈希**，用于唯一标识图片的**内容**（不是路径）

### Key的作用
1. **识别相同内容的图片** - 即使在不同路径
2. **避免重复调用IMS API** - 节约成本
3. **保留所有路径信息** - 便于追踪和管理

---

## 📋 正确的去重逻辑

### 场景1: bucket + object_key 相同 → 完全跳过 ✅

**含义**: 同一个MinIO路径的文件

**处理**:
- ❌ 不插入数据库
- ❌ 不调用API
- ❌ 不提取特征
- ✅ 直接返回

**代码**:
```python
existing_path = db.find_by_bucket_object(bucket_name, object_name)

if existing_path and not force_rescan:
    # 完全跳过
    return
```

**示例**:
```
第一次: bucket='test', path='a.jpg' → 扫描并插入
第二次: bucket='test', path='a.jpg' → 完全跳过（同一路径）
```

---

### 场景2: key相同但路径不同 → 插入记录，复用结果 ✅

**含义**: 相同内容的图片在不同路径

**处理**:
- ✅ 提取特征
- ✅ 插入新路径记录
- ❌ 不调用API（复用原有结果）
- ✅ 标记为`matched_by: 'key_duplicate'`

**代码**:
```python
existing_same_content = db.find_by_key(key)

if existing_same_content and not force_rescan:
    # 复用扫描结果，插入新路径
    record = {
        'key': key,
        'bucket_name': bucket_name,
        'object_key': object_name,  # 新路径
        'is_violation': existing_same_content.get('is_violation'),
        'violation_type': existing_same_content.get('violation_type'),
        'ims_result': {
            'matched_by': 'key_duplicate',
            'original_path': existing_same_content.get('object_key'),
        },
        ...
    }
    db.insert_record(record)  # 插入新路径
    return  # 跳过API
```

**示例**:
```
第一次: path='folder1/a.jpg', key='abc123' → 扫描、调用API、插入
第二次: path='folder2/a.jpg', key='abc123' → 插入新路径，复用结果
第三次: path='folder3/a.jpg', key='abc123' → 插入新路径，复用结果

结果: 数据库有3条记录，只调用了1次API
```

---

### 场景3: key不同 → 正常流程 ✅

**含义**: 新的图片或内容有变化

**处理**:
- ✅ 提取特征
- ✅ 查询相似违规图片
- ✅ 调用腾讯云IMS API
- ✅ 插入/更新记录

**代码**:
```python
# 正常流程
features = extract_features(image_data)
similar = find_similar_violations(features['phash'])

if similar and distance <= 3:
    # 高度相似，直接标记
    insert_record({...})
else:
    # 调用API
    ims_result = scan_image(image_data)
    upsert_record({...})
```

---

## 🔄 完整处理流程

```
开始处理图片
    ↓
步骤1: 下载图片数据
    ↓
步骤2: 计算Key（内容哈希）
    ↓
步骤3: 检查 bucket + object_key 是否存在？
    ├─ 是 → ✅ 完全跳过（不插入、不扫描）
    └─ 否 → 继续
    ↓
步骤4: 提取图片特征（pHash/dHash/aHash）
    ↓
步骤5: 检查 key 是否存在？
    ├─ 是 → ✅ 插入新路径记录，复用扫描结果（跳过API）
    └─ 否 → 继续
    ↓
步骤6: 查询相似违规图片（基于特征哈希）
    ├─ 找到高度相似（距离≤3）→ ✅ 标记违规，跳过API
    └─ 未找到或中度相似 → 继续
    ↓
步骤7: 调用腾讯云IMS API
    ↓
步骤8: 构建记录
    ↓
步骤9: 插入/更新数据库（upsert）
```

---

## 💡 关键改进点

### 1. database.py 新增方法

```python
def find_by_bucket_object(self, bucket_name: str, object_key: str):
    """根据MinIO路径查找记录（用于去重）"""
    query = """
        SELECT * FROM image_scan_records 
        WHERE bucket_name = %s AND object_key = %s 
        LIMIT 1
    """
    results = self.execute_query(query, (bucket_name, object_key), fetch=True)
    return results[0] if results else None
```

### 2. scanner.py 改进逻辑

**之前的问题**:
- ❌ 只检查key，导致同一路径重复插入
- ❌ 重复调用insert_record（代码bug）

**现在的改进**:
- ✅ 先检查 bucket + object_key（路径去重）
- ✅ 再检查 key（内容去重）
- ✅ 删除重复的insert_record调用
- ✅ 清晰的日志提示

---

## 📊 统计说明

### skipped计数

```python
self.stats['skipped'] += 1
```

**包含两种情况**:
1. **路径重复** → 完全跳过（最理想）
2. **内容重复** → 插入记录但跳过API（节约成本）

**都表示节约了API调用**。

---

## 🎯 数据库设计配合

### schema.sql 唯一约束

```sql
UNIQUE KEY uk_bucket_object (bucket_name, object_key(255))
```

**作用**:
- 防止同一路径重复插入
- 即使代码逻辑出错，数据库也能保证唯一性
- `upsert_record()` 会触发UPDATE而不是INSERT

---

## 📝 总结对比表

| 场景 | bucket+object_key | key | 操作 | API调用 | 插入数据库 | 统计 |
|------|-------------------|-----|------|---------|-----------|------|
| 首次扫描 | ❌ 不存在 | ❌ 不存在 | 完整流程 | ✅ 调用 | ✅ 插入 | scanned++ |
| 同一路径重复 | ✅ 存在 | - | 完全跳过 | ❌ 不调用 | ❌ 不插入 | skipped++ |
| 相同内容不同路径 | ❌ 不存在 | ✅ 存在 | 插入记录+复用结果 | ❌ 不调用 | ✅ 插入 | skipped++ |
| 相似违规图片 | ❌ 不存在 | ❌ 不存在 | 插入记录+推测结果 | ❌ 不调用 | ✅ 插入 | scanned++, api_saved++ |
| 全新图片 | ❌ 不存在 | ❌ 不存在 | 完整流程 | ✅ 调用 | ✅ 插入 | scanned++ |

---

## 🔍 实际案例

### 案例1: 批量上传相同图片

```
用户上传同一张图片到不同文件夹：
- /user1/photo.jpg
- /user2/photo.jpg
- /user3/photo.jpg

处理结果:
- 第1张: 扫描、调用API、插入记录
- 第2张: 检测到key相同，插入新路径，复用结果（节约API）
- 第3张: 检测到key相同，插入新路径，复用结果（节约API）

数据库: 3条记录
API调用: 1次
节约: 2次API调用
```

### 案例2: 重新扫描

```
第一次扫描:
- /images/a.jpg → 扫描并插入

第二次扫描（不强制重扫）:
- /images/a.jpg → 检测到路径重复，完全跳过

数据库: 1条记录（没有重复）
API调用: 0次（完全跳过）
```

### 案例3: 强制重扫

```
设置 force_rescan=true

/images/a.jpg → 即使路径存在，也重新扫描和更新

用途: 
- 更新扫描结果
- 修复错误数据
- 重新检测违规内容
```

---

## ✅ 最终效果

1. **避免重复插入** - 同一路径只有一条记录
2. **节约API成本** - 相同内容只调用一次API
3. **保留所有路径** - 便于追踪和管理
4. **支持强制重扫** - 灵活控制扫描行为
5. **数据库保护** - 唯一约束防止数据异常
