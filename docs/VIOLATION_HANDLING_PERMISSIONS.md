# 违规图片处理 - 基于MinIO权限控制

## 🎯 核心改进

**原方案**：通过重命名文件（添加`.__del__`后缀）来标记违规图片  
**新方案**：通过MinIO对象标签（Object Tags）来控制访问权限

### 优势对比

| 特性 | 重命名方案 | 权限控制方案 |
|------|-----------|------------|
| **文件路径保持** | ❌ 路径改变 | ✅ 路径不变 |
| **访问控制** | ❌ 需要应用层判断 | ✅ MinIO原生支持 |
| **恢复难度** | ⚠️ 需要重命名回来 | ✅ 只需移除标签 |
| **性能影响** | ⚠️ 需要复制+删除 | ✅ 仅设置标签 |
| **URL兼容性** | ❌ URL会失效 | ✅ URL保持不变 |
| **CDN友好** | ❌ CDN缓存失效 | ✅ CDN可继续工作 |

---

## 📋 工作原理

### 1. Block操作（标记为违规）

```python
# 设置MinIO对象标签
tags = {
    "status": "violation",
    "blocked": "true"
}
minio.set_object_tags(bucket, object_key, tags)

# 更新数据库
UPDATE image_scan_records SET blocked = 1 WHERE id = ?
```

**效果**：
- ✅ 文件仍然存在于MinIO中
- ✅ 文件路径保持不变
- ✅ 通过标签标记为blocked状态
- ✅ 可以通过策略禁止公开访问

### 2. Restore操作（恢复误判）

```python
# 移除MinIO对象标签
minio.delete_object_tags(bucket, object_key)

# 更新数据库
UPDATE image_scan_records SET blocked = 0, is_violation = 0 WHERE id = ?
```

**效果**：
- ✅ 文件立即恢复正常访问
- ✅ 无需移动或重命名
- ✅ URL完全不受影响

### 3. Delete操作（彻底删除）

```python
# 从MinIO删除文件
minio.remove_object(bucket, object_key)

# 从数据库删除记录
DELETE FROM image_scan_records WHERE id = ?
```

**效果**：
- ⚠️ 不可恢复
- 仅在确认无误后执行

---

## 🔧 MinIO Bucket Policy配置

为了让blocked标签生效，需要配置Bucket Policy：

### 方案1: 基于标签的Policy（推荐）

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::your-bucket-name/*",
            "Condition": {
                "StringEquals": {
                    "s3:ExistingObjectTag/blocked": "true"
                }
            }
        }
    ]
}
```

**说明**：
- 所有带有 `blocked=true` 标签的对象将被拒绝访问
- 未标记的对象正常访问
- 适用于public-read bucket

### 方案2: 应用层控制

如果无法修改Bucket Policy，可以在应用层检查：

```python
def can_access_image(bucket, object_key):
    """检查图片是否可访问"""
    acl_info = minio_client.get_object_acl(bucket, object_key)
    return not acl_info.get('is_blocked', False)
```

---

## 🚀 使用示例

### 1. 标记违规图片为blocked

```bash
# 预览（不实际执行）
python handle_violations.py block --type gambling --dry-run

# 执行标记
python handle_violations.py block --type gambling
```

**执行过程**：
1. 查询所有gambling类型的违规图片
2. 对每个图片设置MinIO标签 `blocked=true`
3. 更新数据库中 `blocked=1`
4. 图片立即变为不可访问（如果配置了Policy）

### 2. 查看被blocked的文件

```bash
python handle_violations.py list-blocked
```

### 3. 恢复误判的图片

```bash
# 恢复指定的被blocked文件
python handle_violations.py restore --ids 1,2
```

**执行过程**：
1. 移除MinIO对象标签
2. 更新数据库 `blocked=0, is_violation=0`
3. 图片立即恢复访问

### 4. 彻底删除blocked文件

```bash
# 警告：此操作不可恢复！
python handle_violations.py delete-blocked --ids 1,2,3
```

---

## 💡 最佳实践

### 1. 配置Bucket Policy

在MinIO控制台或通过mc命令行工具配置Policy，确保blocked标签生效。

### 2. 三步走策略

```
第1步: block（标记） → 让图片无法访问，但保留文件
第2步: review（审核） → 人工确认是否有误判
第3步: delete（删除） → 确认无误后彻底删除
```

### 3. 定期清理

建议每周或每月清理一次blocked文件：

```bash
# 查看所有blocked文件
python handle_violations.py list-blocked

# 确认无误后删除
python handle_violations.py delete-blocked
```

### 4. 备份重要数据

在执行delete操作前，建议先备份：

```bash
# 导出blocked文件列表
python handle_violations.py list-blocked > blocked_backup.txt
```

---

## 📊 数据库字段说明

### blocked字段

```sql
blocked TINYINT(1) DEFAULT 0 COMMENT '是否被block: 0-正常, 1-已block'
```

**取值**：
- `0`: 正常状态，可以访问
- `1`: 已block，MinIO对象带有blocked标签

**索引**：
- 已添加 `idx_blocked` 索引，查询性能优化

---

## 🔄 升级指南

如果你之前使用的是重命名方案，需要迁移：

### 1. 执行数据库迁移

```bash
mysql -u root -p < migration_add_blocked_field.sql
```

### 2. 恢复所有.__del__文件

```bash
# 如果有旧版本的.__del__文件，先恢复它们
python handle_violations_old.py restore
```

### 3. 重新标记违规图片

```bash
# 使用新版本重新标记
python handle_violations.py block --type gambling
```

---

## ⚠️ 注意事项

1. **MinIO版本要求**: 需要MinIO支持Object Tags（RELEASE.2020-06-14及以上）
2. **Policy配置**: 如果不配置Bucket Policy，blocked标签只作为标记，不会自动阻止访问
3. **CDN缓存**: 如果使用CDN，blocked后可能需要清除CDN缓存
4. **权限要求**: MinIO用户需要有 `s3:PutObjectTagging` 和 `s3:GetObjectTagging` 权限

---

## 🎉 总结

新的权限控制方案相比重命名方案有以下优势：

✅ **文件路径不变** - URL和引用不需要更新  
✅ **即时生效** - 设置标签后立即生效  
✅ **易于恢复** - 移除标签即可恢复  
✅ **性能更好** - 不需要复制和删除文件  
✅ **CDN友好** - 不影响CDN缓存  
✅ **标准兼容** - 使用S3标准标签功能  

**推荐使用新的权限控制方案来处理违规图片！**
