# 腾讯云IMS参数错误修复

## 🐛 问题描述

**错误信息**:
```
[TencentCloudSDKException] code:InvalidParameterValue.InvalidParameter 
message:参数错误 
requestId:b6fa436c-d0f5-4bd8-8ab7-4a885bdc6877
```

**受影响文件**: `test-img/100gsoft.cn/6/6c/6c1/6c1f5dc1dd1294bfcbc157da30d5e971_28985.jpg`

---

## 🔍 问题分析

### 根本原因

在 `tencent_ims.py` 的 `scan_image()` 方法中，图片数据编码方式错误：

**错误代码** (第81行):
```python
params = {
    "Content": image_data.hex(),  # ❌ 使用十六进制编码
    "DataEndpoint": "",
    "BizType": biz_type or "default"
}
```

**问题**:
- `image_data.hex()` 将二进制数据转换为十六进制字符串
- 但腾讯云IMS API要求的是 **Base64编码**
- 导致API无法解析图片数据，返回"参数错误"

---

## ✅ 修复方案

### 修改内容

**文件**: `tencent_ims.py`

**修复后的代码**:
```python
import base64

# 创建请求对象
req = models.ImageModerationRequest()

# 设置参数 - 使用Base64编码图片数据
image_base64 = base64.b64encode(image_data).decode('utf-8')
params = {
    "Content": image_base64,  # ✅ 使用Base64编码
    "BizType": biz_type or "default"
}
req.from_json_string(json.dumps(params))

logger.debug(f"准备调用IMS API - 图片大小: {len(image_data)} bytes, Base64长度: {len(image_base64)}")
```

### 关键改动

1. **添加base64导入**: `import base64`
2. **Base64编码**: `base64.b64encode(image_data).decode('utf-8')`
3. **移除无效参数**: 删除 `"DataEndpoint": ""`（不需要）
4. **增强日志**: 记录图片大小和Base64长度，便于调试

---

## 📊 对比说明

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| 编码方式 | hex() 十六进制 | base64.b64encode() Base64 |
| 示例输出 | `ffd8ffe0...` (hex) | `/9j/4AAQSkZJRg...` (base64) |
| API兼容性 | ❌ 不兼容 | ✅ 符合API要求 |
| 数据大小 | 原始大小×2 | 原始大小×1.33 |

### 编码示例

假设图片数据为 `b'\xff\xd8\xff'` (JPEG文件头):

**Hex编码** (错误):
```
"ffd8ff"
```

**Base64编码** (正确):
```
"/9j/"
```

---

## 🧪 验证方法

### 1. 本地测试

```bash
# 重新运行扫描器
python scanner.py --limit 5

# 查看日志
tail -f logs/scan.log
tail -f logs/error.log
```

### 2. 检查成功日志

**成功的日志应该显示**:
```
2024-01-15 10:30:15 | DEBUG | tencent_ims:scan_image:88 | 准备调用IMS API - 图片大小: 123456 bytes, Base64长度: 164608
2024-01-15 10:30:16 | DEBUG | tencent_ims:scan_image:95 | 图片扫描完成 - 违规: False, 类型: None, 置信度: 0.0
```

### 3. 检查错误日志

如果仍有错误，会显示详细信息:
```
❌ 腾讯云IMS扫描失败
  - 错误类型: TencentCloudSDKException
  - 错误信息: [TencentCloudSDKException] code:xxx message:xxx
  - 图片数据大小: 123456 bytes
  - API错误码: InvalidParameterValue
  - API错误消息: 参数错误
  - RequestID: xxx-xxx-xxx
详细堆栈信息:
...
```

---

## 💡 相关知识

### 腾讯云IMS API要求

根据[腾讯云IMS文档](https://cloud.tencent.com/document/api/1125/53271)，`Content` 参数要求：

> 图片文件的 Base64 编码。仅支持 JPG、PNG、BMP 格式，大小不超过 10MB。

### Base64 vs Hex

| 特性 | Base64 | Hex |
|------|--------|-----|
| 编码效率 | 3字节→4字符 (1.33倍) | 1字节→2字符 (2倍) |
| API支持 | ✅ 广泛支持 | ❌ 较少支持 |
| 可读性 | 中等 | 低 |
| 用途 | 二进制数据传输 | 调试、哈希值 |

### Python中的编码方式

```python
import base64

data = b'\xff\xd8\xff\xe0'  # JPEG文件头

# Base64编码 (正确)
base64_str = base64.b64encode(data).decode('utf-8')
print(base64_str)  # "/9j/4A=="

# Hex编码 (错误)
hex_str = data.hex()
print(hex_str)  # "ffd8ffe0"

# Base64解码
decoded = base64.b64decode(base64_str)
print(decoded == data)  # True
```

---

## 🔧 其他可能的参数错误

### 1. 图片太大

**错误**: `Image size exceeds limit`

**解决**: 
```python
# 检查图片大小
if len(image_data) > 10 * 1024 * 1024:  # 10MB
    logger.warning(f"图片过大 ({len(image_data)} bytes)，跳过扫描")
    return {'is_violation': False, ...}
```

### 2. 不支持的格式

**错误**: `Unsupported image format`

**解决**:
```python
# 验证图片格式
from PIL import Image
from io import BytesIO

try:
    img = Image.open(BytesIO(image_data))
    if img.format not in ['JPEG', 'PNG', 'BMP']:
        logger.warning(f"不支持的图片格式: {img.format}")
        return {'is_violation': False, ...}
except Exception as e:
    logger.error(f"无效的图片文件: {e}")
    return {'is_violation': False, ...}
```

### 3. BizType配置错误

**错误**: `Invalid BizType`

**解决**:
```python
# 确保BizType已在腾讯云控制台配置
biz_type = os.getenv('TENCENT_IMS_BIZTYPE', 'default')
```

---

## 📝 总结

### 修复内容

- ✅ 将图片编码从hex改为base64
- ✅ 移除不必要的DataEndpoint参数
- ✅ 增强错误日志，便于调试
- ✅ 添加详细的调试信息

### 预期效果

- ✅ IMS API调用成功
- ✅ 图片正常扫描
- ✅ 违规检测正常工作
- ✅ 错误信息清晰明了

### 下一步

1. **重新构建Docker镜像** (如果使用Docker)
   ```bash
   docker-compose build scanner
   docker-compose up -d scanner
   ```

2. **重新运行扫描**
   ```bash
   python scanner.py
   ```

3. **监控日志**
   ```bash
   tail -f logs/scan.log
   tail -f logs/error.log
   ```

4. **验证结果**
   - 检查是否还有"参数错误"
   - 确认违规图片被正确识别
   - 统计API调用成功率

---

**修复完成！现在应该可以正常调用腾讯云IMS API了。** 🎉
