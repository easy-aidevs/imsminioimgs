# 腾讯云IMS SDK FileContent属性修复

## 🎯 问题根源

### 错误信息
```
code:UnknownParameter 
message:未定义参数 `Ontent` 。
```

### 根本原因

**属性名错误**：代码中使用了 `req.Content`，但SDK中的正确属性名是 `req.FileContent`！

当设置错误的属性名 `Content` 时，SDK序列化会将其变成 `'Ontent'`（少了一个C），导致API拒绝请求。

---

## ✅ 正确解决方案

### 正确的属性名

```python
# ❌ 错误 - 会导致 Ontent Bug
req.Content = image_base64

# ✅ 正确 - 使用 FileContent
req.FileContent = image_base64
```

### 完整代码示例

```python
from tencentcloud.ims.v20201229 import ims_client, models
import base64
import json

def scan_image(image_data, biz_type="default"):
    """扫描图片"""
    
    # 创建客户端
    client = ims_client.ImsClient(cred, region, clientProfile)
    
    # 创建请求对象
    req = models.ImageModerationRequest()
    
    # Base64编码图片数据
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    # ✅ 正确：使用 FileContent 属性
    req.FileContent = image_base64
    req.BizType = biz_type or "default"
    
    # 调用API
    resp = client.ImageModeration(req)
    
    return resp
```

---

## 🧪 验证结果

### 测试环境
- tencentcloud-sdk-python-common==3.1.98
- tencentcloud-sdk-python-ims==3.1.96

### 测试结果

```python
# 使用 FileContent 属性
req.FileContent = image_base64
req.BizType = "default"

json_str = req.to_json_string()
json_obj = json.loads(json_str)

print('JSON字段:', list(json_obj.keys()))
# 输出: ['BizType', 'DataId', 'FileContent', 'FileUrl', 'Interval', 'MaxFrames', 'User', 'Device']

print('FileContent存在:', 'FileContent' in json_obj)
# 输出: True ✅

print('Ontent存在:', 'Ontent' in json_obj)
# 输出: False ✅
```

---

## 📊 属性名对比

| 属性名 | 是否正确 | 序列化结果 | API调用 |
|--------|---------|-----------|---------|
| **FileContent** | ✅ 正确 | `"FileContent": "base64..."` | ✅ 成功 |
| Content | ❌ 错误 | `"Ontent": "base64..."` | ❌ 失败 |
| FileUrl | ✅ 正确（URL方式） | `"FileUrl": "https://..."` | ✅ 成功 |

---

## 🔍 如何发现正确的属性名

### 方法1: 检查SDK源码

```python
from tencentcloud.ims.v20201229 import models

req = models.ImageModerationRequest()
print([attr for attr in dir(req) if not attr.startswith('_') and 'content' in attr.lower()])
# 输出: ['FileContent']
```

### 方法2: 查看官方文档

[腾讯云IMS API文档](https://cloud.tencent.com/document/product/1125/100989)

请求参数：
- **FileContent**: 图片文件的Base64编码
- **FileUrl**: 图片文件的URL地址
- **BizType**: 业务类型

---

## 📝 最终配置

### requirements.txt
```txt
tencentcloud-sdk-python-common==3.1.98  # ✅ 最新版本
tencentcloud-sdk-python-ims==3.1.96     # ✅ 最新版本
```

### tencent_ims.py
```python
try:
    import base64
    
    # 创建请求对象
    req = models.ImageModerationRequest()
    
    # 设置参数 - 使用Base64编码图片数据
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    # ✅ 重要：使用 FileContent 属性（不是 Content）
    req.FileContent = image_base64
    req.BizType = biz_type or "default"
    
    logger.debug(f"准备调用IMS API - 图片大小: {len(image_data)} bytes")
    
    # 调用API
    resp = self.client.ImageModeration(req)
    
    # 解析结果
    result = self._parse_response(resp)
    
    return result
    
except Exception as e:
    logger.error(f"❌ 腾讯云IMS扫描失败")
    logger.error(f"  - 错误类型: {type(e).__name__}")
    logger.error(f"  - 错误信息: {str(e)}")
    raise
```

---

## 🚀 部署步骤

### Docker环境

```bash
# 1. 停止容器
docker-compose down

# 2. 重新构建镜像
docker-compose build --no-cache scanner

# 3. 启动容器
docker-compose up -d scanner

# 4. 查看日志
docker-compose logs -f scanner
```

### 验证修复

```bash
# 在容器中测试
docker-compose run --rm scanner python3 -c "
from tencentcloud.ims.v20201229 import models
import base64
import json

req = models.ImageModerationRequest()
image_base64 = base64.b64encode(b'test').decode('utf-8')
req.FileContent = image_base64
req.BizType = 'default'

json_obj = json.loads(req.to_json_string())
print('FileContent存在:', 'FileContent' in json_obj)
print('Ontent存在:', 'Ontent' in json_obj)
"
```

**期望输出**:
```
FileContent存在: True ✅
Ontent存在: False ✅
```

---

## 💡 关键要点

1. **属性名必须是 `FileContent`**，不是 `Content`
2. **直接赋值属性**即可，不需要使用 `from_json_string()`
3. **SDK版本可以使用最新的 3.1.x**，只要属性名正确就不会有问题
4. **会有null字段**，这是SDK的正常行为，不影响API调用

---

## 🔗 相关资源

- [腾讯云IMS API文档](https://cloud.tencent.com/document/product/1125/100989)
- [腾讯云Python SDK GitHub](https://github.com/TencentCloud/tencentcloud-sdk-python)
- [ImageModerationRequest API参考](https://cloud.tencent.com/document/api/1125/53271)
