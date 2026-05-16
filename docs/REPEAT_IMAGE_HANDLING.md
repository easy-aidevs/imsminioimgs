# 重复图片处理逻辑说明

## 🎯 核心需求

**问题场景**：
MinIO中可能存在同一张图片存储在多个不同路径的情况，例如：
```
bucket/images/
├── folder1/photo.jpg      (MD5: abc123, Size: 100KB)
├── folder2/photo_copy.jpg (MD5: abc123, Size: 100KB) ← 同一张图片
└── folder3/another.jpg    (MD5: def456, Size: 200KB)
```

**业务需求**：
- 需要记录**所有路径**到数据库
- 后续批量删除违规图片时，能够找到并删除所有相同图片的所有路径
- 避免遗漏任何副本

---

## ✅ 当前实现逻辑

### 1. Key的计算（与路径无关）

```python
def calculate_key(self, image_data: bytes) -> str:
    """
    key = MD5(文件内容) + "-" + 文件大小
    
    注意：Key只依赖图片内容和大小，与存储路径无关！
    """
    md5_hash = hashlib.md5(image_data).hexdigest()
    file_size = len(image_data)
    return f"{md5_hash}-{file_size}"
```

**示例**：
- `folder1/photo.jpg` → Key: `"abc123-102400"`
- `folder2/photo_copy.jpg` → Key: `"abc123-102400"` ← **完全相同**

---

### 2. 数据库表结构（允许重复Key）

```sql
CREATE TABLE image_scan_records (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- ⚠️ 关键：key字段没有UNIQUE约束
    `key` VARCHAR(128) NOT NULL COMMENT '图片唯一标识',
    
    -- 每条记录保存不同的路径
    bucket_name VARCHAR(255) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,  -- ← 不同路径
    
    -- 其他字段...
    
    INDEX idx_key (`key`)  -- 用于快速查找相同图片的所有路径
);
```

**关键点**：
- ❌ **移除了** `key` 字段的 UNIQUE 约束
- ✅ **允许** 同一个Key对应多条记录（不同路径）
- ✅ **添加** `idx_key` 索引优化查询

---

### 3. 扫描流程

#### 第1张图片：`folder1/photo.jpg`

```
1. 读取图片数据
2. 计算Key: "abc123-102400"
3. 查询数据库: SELECT * WHERE key = "abc123-102400" LIMIT 1
   → 结果: 不存在
4. 提取特征: pHash=xxx
5. 调用腾讯云IMS检测 → 发现违规（gambling）
6. 插入数据库:
   INSERT INTO image_scan_records VALUES (
       key: "abc123-102400",
       object_key: "folder1/photo.jpg",  ← 路径1
       is_violation: 1,
       violation_type: "gambling",
       ...
   )
```

**数据库状态**：
```
id | key            | object_key           | is_violation | violation_type
1  | abc123-102400  | folder1/photo.jpg    | 1            | gambling
```

---

#### 第2张图片：`folder2/photo_copy.jpg`（相同图片）

```
1. 读取图片数据
2. 计算Key: "abc123-102400"  ← 与第1张相同
3. 查询数据库: SELECT * WHERE key = "abc123-102400" LIMIT 1
   → 结果: 找到第1条记录
4. ⚡ 跳过IMS检测（已知道是违规图片）
5. 但仍然插入新记录（保存当前路径）:
   INSERT INTO image_scan_records VALUES (
       key: "abc123-102400",
       object_key: "folder2/photo_copy.jpg",  ← 路径2（新记录）
       is_violation: 1,  ← 从第1条记录复制
       violation_type: "gambling",
       ...
   )
```

**数据库状态**：
```
id | key            | object_key              | is_violation | violation_type
1  | abc123-102400  | folder1/photo.jpg       | 1            | gambling
2  | abc123-102400  | folder2/photo_copy.jpg  | 1            | gambling  ← 新增
```

---

#### 第3张图片：`folder3/another.jpg`（不同图片）

```
1. 读取图片数据
2. 计算Key: "def456-204800"  ← 不同
3. 查询数据库: 不存在
4. 正常流程：提取特征 → 调用IMS → 保存结果
```

---

## 🔍 查询所有相同图片的路径

### 方法1: 使用 find_all_by_key()

```python
# 查找同一张图片的所有路径
all_paths = db.find_all_by_key("abc123-102400")

for record in all_paths:
    print(f"路径: {record['bucket_name']}/{record['object_key']}")
    print(f"违规: {record['is_violation']}")
    print(f"类型: {record['violation_type']}")
```

**输出**：
```
路径: images/folder1/photo.jpg
违规: True
类型: gambling

路径: images/folder2/photo_copy.jpg
违规: True
类型: gambling
```

---

### 方法2: SQL直接查询

```sql
-- 查找某张图片的所有路径
SELECT 
    id,
    bucket_name,
    object_key,
    is_violation,
    violation_type,
    created_at
FROM image_scan_records
WHERE `key` = 'abc123-102400'
ORDER BY created_at DESC;
```

---

## 💡 批量删除违规图片

### 场景：删除所有棋牌类违规图片及其副本

```python
# 1. 查询所有gambling类型的记录
violations = db.execute_query("""
    SELECT DISTINCT `key`, object_key, bucket_name, violation_type
    FROM image_scan_records
    WHERE is_violation = 1 
      AND violation_type = 'gambling'
""", fetch=True)

# 2. 对每个违规图片，找到所有副本
for violation in violations:
    key = violation['key']
    
    # 查找所有相同图片的路径
    all_copies = db.find_all_by_key(key)
    
    print(f"\n违规图片Key: {key}")
    print(f"共找到 {len(all_copies)} 个副本:")
    
    for copy in all_copies:
        path = f"{copy['bucket_name']}/{copy['object_key']}"
        print(f"  - {path}")
        
        # 3. 从MinIO删除
        minio_client.remove_object(copy['bucket_name'], copy['object_key'])
        print(f"    ✓ 已删除")
    
    # 4. 从数据库删除所有记录
    db.execute_query("DELETE FROM image_scan_records WHERE `key` = %s", (key,))
    print(f"  ✓ 数据库记录已清理")
```

**输出示例**：
```
违规图片Key: abc123-102400
共找到 2 个副本:
  - images/folder1/photo.jpg
    ✓ 已删除
  - images/folder2/photo_copy.jpg
    ✓ 已删除
  ✓ 数据库记录已清理
```

---

## 📊 优势对比

### 旧逻辑（跳过不记录）

| 方面 | 表现 |
|------|------|
| API节约 | ✅ 好（跳过检测） |
| 路径完整性 | ❌ 差（只记录第1个路径） |
| 批量删除 | ❌ 困难（找不到其他副本） |
| 数据一致性 | ❌ 差（丢失信息） |

### 新逻辑（全部记录）

| 方面 | 表现 |
|------|------|
| API节约 | ✅ 好（跳过检测） |
| 路径完整性 | ✅ 完美（记录所有路径） |
| 批量删除 | ✅ 简单（能找到所有副本） |
| 数据一致性 | ✅ 完美（信息完整） |

---

## 🎯 关键改进点

### 1. 数据库表结构

**之前**：
```sql
`key` VARCHAR(128) NOT NULL UNIQUE  -- ❌ 不允许重复
```

**现在**：
```sql
`key` VARCHAR(128) NOT NULL         -- ✅ 允许重复
INDEX idx_key (`key`)               -- ✅ 添加索引
```

### 2. 扫描逻辑

**之前**：
```python
if existing_record:
    return  # ❌ 直接返回，不记录路径
```

**现在**：
```python
if existing_record:
    # ✅ 仍然插入新记录，保存当前路径
    record = {..., 'object_key': object_name}
    db.insert_record(record)
    return  # 但跳过IMS检测
```

### 3. 查询方法

**新增**：
```python
def find_all_by_key(self, key: str) -> List[Dict]:
    """查找同一张图片的所有路径"""
```

---

## 📝 使用建议

### 1. 定期清理重复记录

如果确认某些副本已删除，可以清理数据库：

```sql
-- 查找孤立记录（MinIO中已不存在的路径）
SELECT * FROM image_scan_records
WHERE object_key NOT IN (
    SELECT object_key FROM minio_objects  -- 假设有个同步表
);
```

### 2. 统计重复图片数量

```sql
-- 查看有多少图片有重复路径
SELECT 
    `key`,
    COUNT(*) as copy_count,
    GROUP_CONCAT(object_key) as paths
FROM image_scan_records
GROUP BY `key`
HAVING copy_count > 1
ORDER BY copy_count DESC;
```

### 3. 监控存储空间浪费

```sql
-- 计算重复图片占用的额外空间
SELECT 
    SUM(file_size * (copy_count - 1)) as wasted_bytes
FROM (
    SELECT 
        `key`,
        file_size,
        COUNT(*) as copy_count
    FROM image_scan_records
    GROUP BY `key`
    HAVING copy_count > 1
) AS duplicates;
```

---

## ✨ 总结

**核心原则**：
1. ✅ **Key相同** = 图片内容相同（MD5+大小）
2. ✅ **每条记录** = 一个具体的存储路径
3. ✅ **同Key多记录** = 同一张图片的多个副本
4. ✅ **跳过IMS** = 节约API费用
5. ✅ **保留路径** = 便于批量删除

**业务价值**：
- 💰 节约API费用（重复图片不检测）
- 🗂️ 完整路径信息（所有副本都可追溯）
- 🧹 批量删除方便（一键清理所有副本）
- 📊 数据统计准确（真实反映存储情况）

---

**这样设计既节约了API费用，又保证了数据的完整性！** 🎉
