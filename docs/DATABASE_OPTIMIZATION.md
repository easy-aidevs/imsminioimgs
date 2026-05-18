# 数据库优化说明

## 🎯 优化目标

1. **避免重复扫描** - 同一MinIO路径只保存一条记录
2. **简化数据库结构** - 删除无用的表

---

## ✅ 已完成的优化

### 1. 添加唯一约束（防止重复）

**修改**: `schema.sql` - `image_scan_records` 表

```sql
-- 之前：只有普通索引
INDEX idx_bucket_object (bucket_name, object_key(255))

-- 现在：唯一约束
UNIQUE KEY uk_bucket_object (bucket_name, object_key(255))
```

**效果**:
- ✅ 同一 `(bucket_name, object_key)` 只能有一条记录
- ✅ 重复扫描时会自动更新，不会创建新记录
- ✅ 使用 `upsert_record()` 方法实现"存在则更新，不存在则插入"

---

### 2. 删除无用的表

#### ❌ 删除 `similar_images` 表

**原因**:
- 当前实现在内存中动态计算相似度
- 不需要持久化相似关系
- 减少数据库复杂度

**替代方案**:
- 使用 `database.find_similar_violations()` 方法实时计算
- 基于特征哈希的汉明距离判断

---

#### ❌ 删除 `scan_statistics` 表

**原因**:
- 统计数据可以实时从 `image_scan_records` 查询
- 不需要预计算和存储
- 避免数据不一致问题

**替代方案**:
- 使用 `database.get_statistics()` 方法实时统计
- 通过SQL聚合查询获取最新数据

---

## 📊 最终数据库结构

### image_scan_records（唯一的表）

**用途**: 存储所有图片扫描记录

**关键字段**:
- `key` - 图片内容哈希（用于识别相同图片的不同路径）
- `bucket_name` + `object_key` - MinIO路径（唯一约束）
- `feature_hash` - 感知哈希（用于相似图片检测）
- `is_violation` - 是否违规
- `blocked` - 是否被阻止访问

**唯一约束**:
```sql
UNIQUE KEY uk_bucket_object (bucket_name, object_key(255))
```

**重要索引**:
- `idx_key` - 查找相同图片的其他路径
- `idx_feature_hash` - 相似图片搜索
- `idx_is_violation` - 快速筛选违规图片
- `idx_blocked` - 查询被阻止的文件

---

## 🔄 去重逻辑

### 场景1: 同一路径重复扫描

```python
# 第一次扫描
record = {
    'bucket_name': 'my-bucket',
    'object_key': 'images/photo1.jpg',
    'is_violation': 0,
    ...
}
db.upsert_record(record)  # INSERT

# 第二次扫描（同一路径）
record = {
    'bucket_name': 'my-bucket',
    'object_key': 'images/photo1.jpg',
    'is_violation': 1,  # 状态变化
    ...
}
db.upsert_record(record)  # UPDATE（因为唯一约束）
```

### 场景2: 相同图片不同路径

```python
# 图片A在路径1
record1 = {
    'key': 'abc123-md5hash',  # 相同的内容哈希
    'bucket_name': 'my-bucket',
    'object_key': 'path1/photo.jpg',
}
db.insert_record(record1)  # INSERT

# 图片A在路径2（相同内容）
record2 = {
    'key': 'abc123-md5hash',  # 相同的内容哈希
    'bucket_name': 'my-bucket',
    'object_key': 'path2/photo.jpg',  # 不同的路径
}
db.insert_record(record2)  # INSERT（不同路径，允许）
```

---

## 💡 upsert_record 工作原理

```python
def upsert_record(self, record: Dict) -> int:
    """
    插入或更新记录
    
    - 如果 (bucket_name, object_key) 已存在 → UPDATE
    - 如果不存在 → INSERT
    """
    query = """
        INSERT INTO image_scan_records (...) VALUES (...)
        ON DUPLICATE KEY UPDATE
            is_violation = VALUES(is_violation),
            violation_type = VALUES(violation_type),
            last_scanned_at = NOW(),
            updated_at = NOW()
    """
```

---

## 🚀 部署步骤

### 全新安装

```bash
# 直接执行最新的schema.sql
mysql -u root -p < schema.sql
```

### 已有数据库（需要迁移）

```sql
-- 1. 备份数据
mysqldump -u root -p image_security > backup.sql

-- 2. 删除旧表
DROP TABLE IF EXISTS similar_images;
DROP TABLE IF EXISTS scan_statistics;

-- 3. 修改主表，添加唯一约束
ALTER TABLE image_scan_records 
    DROP INDEX idx_bucket_object,
    ADD UNIQUE KEY uk_bucket_object (bucket_name, object_key(255));

-- 4. 验证
SHOW INDEX FROM image_scan_records;
```

---

## 📝 总结

| 优化项 | 之前 | 现在 | 好处 |
|--------|------|------|------|
| **去重方式** | 无唯一约束 | `UNIQUE KEY (bucket, object_key)` | 避免重复记录 |
| **similar_images表** | 定义但未使用 | 已删除 | 简化结构 |
| **scan_statistics表** | 定义但未使用 | 已删除 | 实时查询更准确 |
| **数据库表数量** | 3个表 | 1个表 | 更易维护 |

---

## 🔗 相关代码

- **Schema定义**: [schema.sql](file:///Users/macbook/imsminioimgs/schema.sql)
- **Upsert实现**: [database.py#L301](file:///Users/macbook/imsminioimgs/database.py#L301)
- **实时统计**: [database.py#L357](file:///Users/macbook/imsminioimgs/database.py#L357)
- **相似检测**: [database.py#L145](file:///Users/macbook/imsminioimgs/database.py#L145)
