# 腾讯云IMS SDK Bug修复方案

## 🐛 问题描述

### 错误信息
```
code:UnknownParameter 
message:未定义参数 `Ontent` 。
requestId:xxx-xxx-xxx
```

### 根本原因

**腾讯云SDK 3.1.x版本存在严重Bug**：
- 当设置 `req.Content = "base64数据"` 时
- SDK内部序列化会错误地将字段名变成 `'Ontent'`（少了一个C）
- 导致API返回"未定义参数 Ontent"错误

---

## ✅ 解决方案

### 方案：降级到稳定的3.0.1076版本

#### 1. 更新requirements.txt

```txt
tencentcloud-sdk-python-common==3.0.1076  # ✅ 稳定版本
tencentcloud-sdk-python-ims==3.0.1076     # ✅ 稳定版本
```

#### 2. 代码实现（tencent_ims.py）

```python
try:
    import base64
    
    # 创建请求对象
    req = models.ImageModerationRequest()
    
    # 设置参数 - 使用Base64编码图片数据
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    # 重要：使用from_json_string只设置必要字段，避免null值
    params_dict = {
        "Content": image_base64,
        "BizType": biz_type or "default"
    }
    req.from_json_string(json.dumps(params_dict))
    
    # 验证序列化结果，确保没有Ontent错误
    json_check = req.to_json_string()
    if '"Ontent"' in json_check:
        logger.error(f"检测到SDK Bug: Content被序列化为Ontent")
        logger.error(f"JSON内容: {json_check[:200]}")
        raise RuntimeError("腾讯云SDK版本存在Bug，请降级到3.0.1076")
    
    # 调用API
    resp = self.client.ImageModeration(req)
    
except Exception as e:
    logger.error(f"❌ 腾讯云IMS扫描失败")
    logger.error(f"  - 错误类型: {type(e).__name__}")
    logger.error(f"  - 错误信息: {str(e)}")
    raise
```

---

## 🔧 部署步骤

### Docker环境

```bash
# 1. 停止容器
docker-compose down

# 2. 清理旧镜像
docker system prune -f

# 3. 重新构建（使用3.0.1076版本）
docker-compose build --no-cache scanner

# 4. 启动容器
docker-compose up -d scanner

# 5. 查看日志
docker-compose logs -f scanner
```

### 本地环境

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行测试
python test_ims_sdk.py

# 3. 运行扫描器
python scanner.py --limit 5
```

---

## 🧪 验证方法

### 方法1: 检查SDK版本

```bash
# 在容器中
docker-compose exec scanner python3 -c "import tencentcloud; print(tencentcloud.__version__)"

# 应该输出: 3.0.1076
```

### 方法2: 检查序列化结果

```bash
# 在容器中运行测试
docker-compose exec scanner python3 /app/test_ims_sdk.py
```

**期望输出**:
```
✓ Content字段存在
✓ 没有Ontent错误字段
⚠️  发现null字段 (可能有多个)
```

### 方法3: 实际扫描测试

```bash
# 扫描少量图片测试
docker-compose exec scanner python3 scanner.py --limit 5

# 查看日志，确认没有"Ontent"错误
docker-compose logs scanner | grep -i ontent
```

**期望结果**: 
- ✅ 没有"Ontent"相关错误
- ✅ 图片正常扫描
- ✅ API调用成功

---

## 📊 版本对比

| 版本 | Content序列化 | null字段 | 稳定性 |
|------|--------------|---------|--------|
| **3.0.1076** | ✅ 正确 | ⚠️ 有null | ✅ 稳定 |
| **3.1.96** | ❌ 变成Ontent | ⚠️ 有null | ❌ 有Bug |
| **3.1.98** | ❌ 变成Ontent | ⚠️ 有null | ❌ 有Bug |

---

## 🎯 最终配置

### requirements.txt
```txt
minio==7.2.0
Pillow==10.2.0
imagehash==4.3.1
numpy==1.26.4
tencentcloud-sdk-python-common==3.0.1076  # ✅ 稳定版本
tencentcloud-sdk-python-ims==3.0.1076     # ✅ 稳定版本
mysql-connector-python==8.3.0
python-dotenv==1.0.1
loguru==0.7.2
tqdm==4.66.1
```

### tencent_ims.py关键点
1. ✅ 使用 `from_json_string()` 设置参数
2. ✅ 只包含 `Content` 和 `BizType` 两个字段
3. ✅ 添加序列化结果验证
4. ✅ 详细的错误日志记录

---

## 📝 注意事项

1. **不要升级到3.1.x版本** - 直到腾讯云修复这个Bug
2. **每次修改代码后必须重新构建Docker镜像** - 使用 `--no-cache` 参数
3. **检查日志中的SDK版本** - 确保使用的是3.0.1076
4. **保留验证代码** - `if '"Ontent"' in json_check` 可以及时发现版本问题

---

## 🔗 相关资源

- [腾讯云IMS官方文档](https://cloud.tencent.com/document/product/1125/100989)
- [腾讯云Python SDK GitHub](https://github.com/TencentCloud/tencentcloud-sdk-python)
- [SDK版本发布说明](https://github.com/TencentCloud/tencentcloud-sdk-python/releases)
