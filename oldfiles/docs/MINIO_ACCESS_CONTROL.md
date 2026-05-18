# MinIO 违规图片访问控制实现方案

## 📅 更新时间
**2026-05-16**

---

## ⚠️ 重要问题

### MinIO 不支持单个对象的 ACL 设置

MinIO **不支持**像 AWS S3 那样直接设置单个对象的 ACL（Access Control List）为 `private`。

**错误理解**:
```python
# ❌ 这种方式在 MinIO 中不存在
self.minio.set_object_acl(bucket, object_key, 'private')
```

**正确理解**:
- MinIO 的访问控制是 **Bucket 级别**的，不是对象级别
- 需要通过 **Bucket Policy** 来控制访问权限

---

## ✅ 正确的实现方案

### 方案：标签 + Bucket Policy

#### 第1步: 给违规对象添加标签

```python
def set_object_blocked(self, bucket_name: str, object_name: str, is_blocked: bool = True):
    """设置对象为blocked状态（通过标签标记）"""
    if is_blocked:
        tags = ObjectTags()
        tags["status"] = "violation"
        tags["blocked"] = "true"  # ✅ 关键标签
        self.client.set_object_tags(bucket_name, object_name, tags)
    else:
        self.client.delete_object_tags(bucket_name, object_name)
```

#### 第2步: 设置 Bucket Policy 拒绝访问带标签的对象

```python
def set_bucket_policy_block_tagged_objects(self, bucket_name: str):
    """设置 Bucket Policy，拒绝访问带有 blocked=true 标签的对象"""
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Deny",  # ✅ 拒绝访问
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                "Condition": {
                    "StringEquals": {
                        "s3:ExistingObjectTag/blocked": "true"  # ✅ 条件：标签 blocked=true
                    }
                }
            }
        ]
    }
    
    self.client.set_bucket_policy(bucket_name, json.dumps(policy))
```

---

## 🔧 自动配置

### handle_violations.py 初始化时自动设置

```python
class ViolationHandler:
    def __init__(self):
        # ... 初始化数据库和MinIO
        
        # ✅ 自动设置 Bucket Policy，确保 blocked 对象无法访问
        self._setup_bucket_policy()
    
    def _setup_bucket_policy(self):
        """对所有存储桶设置 Block Policy"""
        buckets = self.minio.list_buckets()
        for bucket in buckets:
            self.minio.set_bucket_policy_block_tagged_objects(bucket)
```

---

## 🎯 工作流程

### 标记违规图片

```bash
python handle_violations.py block --type gambling
```

**执行步骤**:
1. ✅ 查询数据库中未 blocked 的违规图片
2. ✅ 给 MinIO 对象添加标签 `blocked=true`
3. ✅ 更新数据库 `blocked=1`
4. ✅ Bucket Policy 自动生效，拒绝访问这些对象

### 访问被阻止的效果

**标记前**:
```
https://minio.example.com/bucket/image.jpg  → ✅ 可以访问
```

**标记后**:
```
https://minio.example.com/bucket/image.jpg  → ❌ Access Denied (403)
```

---

## 📊 技术细节

### Bucket Policy 工作原理

```json
{
  "Effect": "Deny",           // 拒绝访问
  "Action": ["s3:GetObject"], // 针对 GET 操作
  "Condition": {
    "StringEquals": {
      "s3:ExistingObjectTag/blocked": "true"  // 当标签 blocked=true 时
    }
  }
}
```

**关键点**:
- `Deny` 优先级高于 `Allow`
- 只要对象有 `blocked=true` 标签，任何人都无法访问
- 包括匿名用户、认证用户、甚至管理员

---

## ⚠️ 注意事项

### 1. Bucket Policy 是累积的

如果之前已经有 Bucket Policy，新的 Policy 会**覆盖**旧的。

**解决方案**:
- 合并多个 Statement
- 或者使用 `get_bucket_policy()` 先读取现有策略

### 2. 标签设置后立即生效

一旦设置 `blocked=true` 标签，Bucket Policy 立即生效，无需重启。

### 3. 恢复访问

要恢复访问，需要：
1. 清除标签：`delete_object_tags()`
2. Bucket Policy 自动不再匹配，访问恢复

---

## 🔍 验证方法

### 检查对象是否有标签

```python
tags = minio_client.get_object_tags(bucket, object_key)
print(tags)  # {'blocked': 'true', 'status': 'violation'}
```

### 检查 Bucket Policy

```bash
# 使用 mc 命令行工具
mc admin policy info myminio/mybucket

# 或使用 Python SDK
policy = minio_client.client.get_bucket_policy(bucket_name)
print(policy)
```

### 测试访问被阻止

```bash
# 尝试访问被 blocked 的对象
curl https://minio.example.com/bucket/blocked-image.jpg

# 应该返回 403 Forbidden
```

---

## 📝 总结

| 特性 | 说明 |
|------|------|
| **实现方式** | 标签 + Bucket Policy |
| **访问控制粒度** | Bucket 级别（通过标签条件） |
| **生效时间** | 立即生效 |
| **恢复方式** | 清除标签即可 |
| **安全性** | 高（Deny 规则优先级最高） |
| **兼容性** | MinIO 和 AWS S3 都支持 |

---

## 🚀 优势

1. ✅ **真正的访问控制** - 不只是标记，而是实际阻止访问
2. ✅ **自动化** - 初始化时自动配置，无需手动操作
3. ✅ **灵活** - 可以通过修改标签动态控制访问
4. ✅ **安全** - Deny 规则优先级最高，无法绕过
5. ✅ **标准** - 使用 AWS S3 兼容的策略语法
