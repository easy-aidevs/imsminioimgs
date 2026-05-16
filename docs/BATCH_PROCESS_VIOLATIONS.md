# 批量处理违规图片完整指南

## 🎯 核心问题解答

### 问：后续同特征的图片有 is_violation 和 violation_type 吗？

**答：✅ 有的！每条记录都包含完整的违规信息。**

---

## 📋 数据库记录结构

### 所有记录都包含以下字段

```python
# 第1张图片：poker1.jpg（首次扫描）
{
    'id': 1,
    'key': 'abc123-102400',
    'object_key': 'poker1.jpg',
    'is_violation': 1,              # ✅ 有
    'violation_type': 'gambling',   # ✅ 有
    'violation_label': 'Poker',     # ✅ 有
    'confidence': 0.95,             # ✅ 有
}

# 第2张图片：poker_copy.jpg（相同图片，不同路径）
{
    'id': 2,
    'key': 'abc123-102400',
    'object_key': 'poker_copy.jpg',
    'is_violation': 1,              # ✅ 从第1条复制
    'violation_type': 'gambling',   # ✅ 从第1条复制
    'violation_label': 'Poker',     # ✅ 从第1条复制
    'confidence': 0.95,             # ✅ 从第1条复制
}
```

**关键点**：
- ✅ `is_violation` - 每条都有
- ✅ `violation_type` - 每条都有
- ✅ `confidence` - 每条都有

---

## 🔍 查询所有违规图片

### 方法1: 查询所有违规图片

```python
from database import ImageDatabase

db = ImageDatabase(
    host='localhost',
    port=3306,
    user='root',
    password='your_password',
    database='image_security'
)

# 查询所有违规图片
violations = db.execute_query("""
    SELECT 
        id,
        bucket_name,
        object_key,
        is_violation,
        violation_type,
        violation_label,
        confidence
    FROM image_scan_records
    WHERE is_violation = 1
    ORDER BY violation_type, confidence DESC
""", fetch=True)

print(f"共找到 {len(violations)} 张违规图片\n")

for v in violations:
    print(f"ID: {v['id']}")
    print(f"  路径: {v['bucket_name']}/{v['object_key']}")
    print(f"  类型: {v['violation_type']}")
    print(f"  置信度: {v['confidence']}")
```

---

### 方法2: 按违规类型筛选

```python
# 只查询赌博类违规图片
gambling_images = db.execute_query("""
    SELECT bucket_name, object_key, violation_type, confidence
    FROM image_scan_records
    WHERE is_violation = 1 
      AND violation_type = 'gambling'
    ORDER BY confidence DESC
""", fetch=True)

print(f"赌博类违规图片: {len(gambling_images)} 张")

for img in gambling_images:
    print(f"{img['bucket_name']}/{img['object_key']}")
```

---

### 方法3: 统计各类型数量

```python
stats = db.execute_query("""
    SELECT 
        violation_type,
        COUNT(*) as count,
        AVG(confidence) as avg_confidence
    FROM image_scan_records
    WHERE is_violation = 1
    GROUP BY violation_type
    ORDER BY count DESC
""", fetch=True)

for s in stats:
    print(f"{s['violation_type']}: {s['count']}张 "
          f"(平均置信度: {s['avg_confidence']:.2f})")
```

---

## 🗑️ 批量删除违规图片

### 方案1: 删除特定类型的违规图片

```python
from minio_client import MinIOClient
from database import ImageDatabase

# 初始化
db = ImageDatabase(...)
minio = MinIOClient(...)

# 1. 查询所有赌博类违规图片
violations = db.execute_query("""
    SELECT id, bucket_name, object_key
    FROM image_scan_records
    WHERE is_violation = 1 
      AND violation_type = 'gambling'
""", fetch=True)

print(f"准备删除 {len(violations)} 张赌博类图片\n")

# 2. 逐个删除
deleted_count = 0
for v in violations:
    try:
        # 从MinIO删除文件
        minio.remove_object(v['bucket_name'], v['object_key'])
        
        # 从数据库删除记录
        db.execute_query(
            "DELETE FROM image_scan_records WHERE id = %s",
            (v['id'],)
        )
        
        deleted_count += 1
        print(f"✓ 已删除: {v['object_key']}")
        
    except Exception as e:
        print(f"✗ 删除失败: {v['object_key']} - {str(e)}")

# 3. 提交事务
db.connection.commit()
print(f"\n成功删除 {deleted_count} 张图片")
```

---

### 方案2: 删除所有违规图片

```python
# ⚠️ 警告：这将删除所有违规图片！

# 1. 先确认数量
count = db.execute_query("""
    SELECT COUNT(*) as total
    FROM image_scan_records
    WHERE is_violation = 1
""", fetch=True)[0]['total']

print(f"⚠️  警告：即将删除 {count} 张违规图片！")
confirm = input("确认删除？(yes/no): ")

if confirm.lower() != 'yes':
    print("已取消")
    exit()

# 2. 获取所有违规图片
violations = db.execute_query("""
    SELECT bucket_name, object_key, id
    FROM image_scan_records
    WHERE is_violation = 1
""", fetch=True)

# 3. 批量删除
for v in violations:
    minio.remove_object(v['bucket_name'], v['object_key'])
    db.execute_query("DELETE FROM image_scan_records WHERE id = %s", (v['id'],))

db.connection.commit()
print("删除完成！")
```

---

## 📊 高级查询示例

### 1. 查找同一违规图片的所有副本

```python
# 查找某张违规图片的所有路径
key = 'abc123-102400'

all_copies = db.execute_query("""
    SELECT id, bucket_name, object_key
    FROM image_scan_records
    WHERE `key` = %s AND is_violation = 1
""", (key,), fetch=True)

print(f"Key: {key}")
print(f"共找到 {len(all_copies)} 个副本:\n")

for copy in all_copies:
    print(f"  {copy['bucket_name']}/{copy['object_key']}")
```

---

### 2. 查找低置信度的违规图片（需人工复核）

```python
suspect_images = db.execute_query("""
    SELECT bucket_name, object_key, violation_type, confidence
    FROM image_scan_records
    WHERE is_violation = 1 
      AND confidence < 0.8
    ORDER BY confidence ASC
""", fetch=True)

print(f"需要人工复核的图片: {len(suspect_images)} 张\n")

for img in suspect_images:
    print(f"{img['object_key']} "
          f"(类型: {img['violation_type']}, "
          f"置信度: {img['confidence']})")
```

---

### 3. 导出违规图片列表到CSV

```python
import csv

violations = db.execute_query("""
    SELECT 
        bucket_name,
        object_key,
        violation_type,
        violation_label,
        confidence,
        created_at
    FROM image_scan_records
    WHERE is_violation = 1
    ORDER BY violation_type, created_at DESC
""", fetch=True)

# 导出到CSV
with open('violations_report.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'bucket_name', 'object_key', 'violation_type',
        'violation_label', 'confidence', 'created_at'
    ])
    writer.writeheader()
    writer.writerows(violations)

print(f"已导出 {len(violations)} 条记录到 violations_report.csv")
```

---

## 💡 实用脚本：一键清理所有违规图片

创建文件 `cleanup_violations.py`:

```python
#!/usr/bin/env python3
"""
批量清理违规图片脚本
"""

import os
import sys
from dotenv import load_dotenv
from database import ImageDatabase
from minio_client import MinIOClient
from loguru import logger

# 加载环境变量
load_dotenv()

def cleanup_violations(violation_type=None, confidence_threshold=0.0, dry_run=False):
    """
    清理违规图片
    
    Args:
        violation_type: 违规类型，None表示所有类型
        confidence_threshold: 置信度阈值，只删除高于此值的
        dry_run: 是否仅预览不实际删除
    """
    # 初始化
    db = ImageDatabase(
        host=os.getenv('MYSQL_HOST'),
        port=int(os.getenv('MYSQL_PORT', '3306')),
        user=os.getenv('MYSQL_USER'),
        password=os.getenv('MYSQL_PASSWORD'),
        database=os.getenv('MYSQL_DATABASE')
    )
    
    minio = MinIOClient(
        endpoint=os.getenv('MINIO_ENDPOINT'),
        access_key=os.getenv('MINIO_ACCESS_KEY'),
        secret_key=os.getenv('MINIO_SECRET_KEY'),
        secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true'
    )
    
    # 构建查询
    query = "SELECT id, bucket_name, object_key, violation_type, confidence FROM image_scan_records WHERE is_violation = 1"
    params = []
    
    if violation_type:
        query += " AND violation_type = %s"
        params.append(violation_type)
    
    if confidence_threshold > 0:
        query += " AND confidence >= %s"
        params.append(confidence_threshold)
    
    query += " ORDER BY confidence DESC"
    
    # 执行查询
    violations = db.execute_query(query, tuple(params), fetch=True)
    
    if not violations:
        print("没有找到符合条件的违规图片")
        return
    
    print(f"找到 {len(violations)} 张违规图片:\n")
    
    # 显示预览
    for i, v in enumerate(violations[:10], 1):
        print(f"{i}. {v['object_key']}")
        print(f"   类型: {v['violation_type']}, 置信度: {v['confidence']}")
    
    if len(violations) > 10:
        print(f"... 还有 {len(violations) - 10} 张")
    
    # 确认删除
    if dry_run:
        print("\n[DRY RUN] 未实际删除")
        return
    
    confirm = input(f"\n确认删除这 {len(violations)} 张图片？(yes/no): ")
    if confirm.lower() != 'yes':
        print("已取消")
        return
    
    # 执行删除
    deleted = 0
    failed = 0
    
    for v in violations:
        try:
            # 从MinIO删除
            minio.remove_object(v['bucket_name'], v['object_key'])
            
            # 从数据库删除
            db.execute_query(
                "DELETE FROM image_scan_records WHERE id = %s",
                (v['id'],)
            )
            
            deleted += 1
            
        except Exception as e:
            failed += 1
            logger.error(f"删除失败: {v['object_key']} - {e}")
    
    # 提交事务
    db.connection.commit()
    
    print(f"\n删除完成:")
    print(f"  成功: {deleted}")
    print(f"  失败: {failed}")


if __name__ == '__main__':
    # 示例用法
    import argparse
    
    parser = argparse.ArgumentParser(description='批量清理违规图片')
    parser.add_argument('--type', help='违规类型（如gambling）')
    parser.add_argument('--confidence', type=float, default=0.0, help='置信度阈值')
    parser.add_argument('--dry-run', action='store_true', help='仅预览不删除')
    
    args = parser.parse_args()
    
    cleanup_violations(
        violation_type=args.type,
        confidence_threshold=args.confidence,
        dry_run=args.dry_run
    )
```

**使用方法**：

```bash
# 预览所有违规图片
python cleanup_violations.py --dry-run

# 删除所有赌博类图片
python cleanup_violations.py --type gambling

# 删除置信度>0.9的违规图片
python cleanup_violations.py --confidence 0.9

# 删除所有违规图片（谨慎！）
python cleanup_violations.py
```

---

## 🎯 总结

### 关键要点

1. ✅ **每条记录都有完整的违规信息**
   - `is_violation`
   - `violation_type`
   - `violation_label`
   - `confidence`

2. ✅ **可以按类型查询所有违规图片**
   ```sql
   SELECT * FROM image_scan_records
   WHERE is_violation = 1 AND violation_type = 'gambling'
   ```

3. ✅ **可以批量删除违规图片及其所有副本**
   - 从MinIO删除文件
   - 从数据库删除记录

4. ✅ **支持灵活的筛选条件**
   - 按类型
   - 按置信度
   - 按时间范围

---

**现在您可以轻松批量处理所有违规图片了！** 🎉

