# 扫描器详解（scanner.py）

## 概述

`scanner.py` 是系统的扫描入口，负责遍历 MinIO 桶中的所有图片，提取特征，调用腾讯云 IMS 进行内容检测，并将结果存入数据库。

**核心特性**：三层去重机制，最小化 API 调用，节省费用。

## 工作流程

```
遍历 MinIO 桶
    ↓
┌─────────────────────────────────────────────┐
│ 第 1 层：路径去重                            │
│ 同一路径已扫描？→ 跳过                      │
└─────────────────────────────────────────────┘
    ↓ (否)
┌─────────────────────────────────────────────┐
│ 下载图片 & 提取特征                          │
│ - 计算内容 Key (md5-size)                   │
│ - 计算 phash 特征                           │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 第 2 层：内容去重                            │
│ 相同内容已扫描？→ 复用结果                   │
└─────────────────────────────────────────────┘
    ↓ (否)
┌─────────────────────────────────────────────┐
│ 第 3 层：特征相似                            │
│ 有高度相似的已扫描图片？→ 复用结果           │
│ (phash 距离 ≤ 3)                            │
└─────────────────────────────────────────────┘
    ↓ (否)
┌─────────────────────────────────────────────┐
│ 调用腾讯云 IMS API                          │
│ 获取：is_violation, type, confidence        │
└─────────────────────────────────────────────┘
    ↓
写入数据库
```

## 基本用法

### 命令行

```bash
python scanner.py [选项]
```

### 选项

| 选项 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `--bucket` | str | 指定要扫描的桶（可多个） | `--bucket images --bucket photos` |
| `--force-rescan` | flag | 强制重新扫描所有图片 | `--force-rescan` |
| `--skip-ims` | flag | 跳过 IMS 扫描，只做去重 | `--skip-ims` |
| `--limit` | int | 限制扫描数量 | `--limit 100` |
| `--dry-run` | flag | 预演，不写数据库 | `--dry-run` |

## 使用场景

### 场景 1：首次全量扫描

```bash
python scanner.py
```

**特点**：
- 扫描所有配置的桶中的所有图片
- 第一次遇到每张图片，调用 IMS API
- 统计第 1、2、3 层去重

**输出**：
```
[INFO] 扫描器初始化完成
[INFO] 遍历完成，共 1000 张图片
[INFO] 扫描完成
  - 总数：1000
  - 已扫描：1000
  - 复用结果：0
  - 检出违规：12 张
```

### 场景 2：增量扫描（新增图片）

```bash
python scanner.py
```

**特点**：
- 自动跳过已扫描的图片（第 1 层去重）
- 只扫描新增或修改的图片
- 复用已有结果

**输出**：
```
[INFO] 扫描完成
  - 总数：1050
  - 已扫描：50     (新增)
  - 复用结果：1000 (已存在)
  - 检出违规：2 张 (新增)
```

### 场景 3：强制重新扫描

```bash
python scanner.py --force-rescan
```

**用途**：
- 更新违规判断（IMS 模型升级）
- 调整置信度阈值
- 验证扫描结果

**特点**：
- 忽略所有已有扫描记录
- 重新对所有图片调用 IMS API
- 统计结果覆盖旧数据

### 场景 4：跳过 IMS（测试去重）

```bash
python scanner.py --skip-ims
```

**用途**：
- 测试特征提取和去重逻辑
- 验证数据库查询
- 不消耗 IMS API 配额

**特点**：
- 仍然完整执行去重逻辑
- 不调用腾讯云 IMS
- 快速验证系统功能

### 场景 5：有限数量扫描

```bash
python scanner.py --limit 100
```

**用途**：
- 测试和演示
- 控制单次 API 费用

## 三层去重详解

### 第 1 层：路径去重

**原理**：同一 MinIO 路径（bucket + object_key）已扫描过，直接跳过。

**实现**：
```python
existing = db.find_by_bucket_object(bucket, object_key)
if existing:
    stats['skipped'] += 1
    return
```

**优势**：
- 最快速，无需下载和计算
- 处理重复上传的同一文件

**示例**：
```
首次：bucket=images, key=photo.jpg → 下载、扫描
再次：bucket=images, key=photo.jpg → 直接跳过（路径相同）
```

### 第 2 层：内容去重

**原理**：相同内容（md5 + 文件大小）已扫描过，复用结果。

**实现**：
```python
key = calculate_key(image_data)  # md5-size
same_content = db.find_by_key(key)
if same_content:
    write_reused_record(same_content)
    stats['reused'] += 1
    return
```

**优势**：
- 处理同一内容不同路径的情况
- 避免重复 API 调用

**示例**：
```
图片 A (100KB): /upload/photo.jpg     → 第一次，调用 IMS，结果: 违规
图片 B (100KB): /archive/photo.jpg    → 内容相同，复用 A 的结果（不调用 IMS）
```

### 第 3 层：特征相似

**原理**：phash 特征相似度高（汉明距离 ≤ 3）的已扫描图片，复用其结果。

**实现**：
```python
phash = features['phash']
similar = db.find_similar_scanned(phash, max_distance=3)
if similar:
    write_reused_record(similar[0])
    stats['reused'] += 1
    return
```

**汉明距离**：
- 距离 = 两个 phash 字符串中不同的位数
- 距离 ≤ 3 认为相似（经验值）
- 可调整 `SIMILAR_DISTANCE_REUSE` 参数

**优势**：
- 处理裁剪、压缩、轻微编辑的同一图片
- 显著减少 API 调用

**示例**：
```
原图: photo_original.jpg  → phash = "8f4a5e2c1b9d7f3a" → 扫描 → 违规
编辑: photo_cropped.jpg   → phash = "8f4a5e2c1b9d7f3c" → 汉明距离 = 1 → 复用结果
```

## 特征提取

### phash（知觉哈希）

**定义**：将图片缩小到 8×8，转换为灰度，计算 64 位哈希值。

**特点**：
- 对裁剪、缩放、压缩变化鲁棒
- 快速计算
- 固定长度（64 位）

**代码**：
```python
from imagehash import phash
from PIL import Image

image = Image.open(image_data)
phash_value = phash(image, hash_size=8)
```

### 内容 Key（唯一标识）

**构成**：`md5(内容) + '-' + 文件大小`

**用途**：
- 确保相同内容可被识别
- 检测完全重复的图片

**计算**：
```python
import hashlib
md5 = hashlib.md5(image_data).hexdigest()
key = f"{md5}-{len(image_data)}"
```

## 缓存策略

### 内存缓存

扫描器在内存中维护一个相似图片缓存，加速查询：

**特点**：
- 只缓存相似的图片（第 3 层）
- 大小可配置
- 扫描完成后自动清理

**配置**：
```python
CACHE_MAX_SIZE = 10000  # 最大缓存条目
```

### 缓存查询

```python
cache_similar = scanner._find_similar_in_cache(phash)
db_similar = scanner.db.find_similar_scanned(phash)
# 合并并返回最相似的
```

## 错误处理

### 错误类型

| 错误 | 原因 | 处理 |
|------|------|------|
| `MinIOError` | MinIO 连接失败 | 记录错误，跳过该对象 |
| `IMS API Error` | 腾讯云 API 限流或错误 | 重试（最多 3 次），记录 |
| `ImageProcessError` | 图片无法识别 | 跳过，记录为错误 |
| `DatabaseError` | 数据库写入失败 | 记录错误，继续扫描 |

### 错误重试

```python
# 自动重试 3 次
for retry in range(3):
    try:
        result = ims.scan_image(image_data)
        break
    except Exception as e:
        if retry < 2:
            logger.warning(f"重试 {retry + 1}")
            continue
        else:
            logger.error(f"最终失败：{e}")
            record_error(e)
```

## 统计信息

扫描完成后输出统计：

```python
{
    'total': 1000,          # 遇到的总对象数
    'scanned': 50,          # 实际调用 IMS 扫描数
    'reused': 900,          # 复用已有结果数
    'skipped': 50,          # 跳过（重复）数
    'violations': 5,        # 检出违规数
    'api_saved': 900,       # 节省的 API 调用数
    'errors': 50            # 错误数
}
```

**计算公式**：
```
total = scanned + reused + errors
api_saved = reused + skipped (第 2、3 层去重)
节省费用 ≈ api_saved × (IMS 单价)
```

## 性能优化建议

### 1. 调整批大小

```python
# 扫描器一次处理的对象数
BATCH_SIZE = 50  # 减少可降低内存使用，增加可提速
```

### 2. 并发控制

```python
# 并发下载和处理
MAX_CONCURRENT = 5  # 根据 MinIO 和数据库容量调整
```

### 3. 特征哈希参数

```python
# phash 大小（8 = 64 位，4 = 16 位）
hash_size = 8  # 越小越快，但准确度降低
```

### 4. 数据库索引

```sql
-- 确保有这些索引以加快查询
INDEX idx_key (key)
INDEX idx_feature_hash (feature_hash)
INDEX idx_bucket_object (bucket_name, object_key)
```

## 日志查看

### 扫描日志

```bash
tail -f logs/scan.log

# 输出示例
[2026-05-19 10:00:00] | DEBUG | 开始扫描桶: images
[2026-05-19 10:00:01] | DEBUG | 遍历: uploads/photo_1.jpg
[2026-05-19 10:00:02] | WARNING | 违规(IMS): uploads/photo_1.jpg | 类型=gambling | 置信度=0.95
[2026-05-19 10:00:50] | INFO | 扫描完成
```

### 违规日志

```bash
tail -f logs/violations.log

# 只显示检出的违规
[2026-05-19 10:00:02] | WARNING | 违规(IMS): uploads/photo_1.jpg | 类型=gambling | 置信度=0.95
```

### 错误日志

```bash
tail -f logs/error.log

# 只显示错误
[2026-05-19 10:05:30] | ERROR | MinIO连接失败: Connection refused
```

## 高级用法

### 自定义扫描逻辑

继承 `ImageScanner` 类：

```python
class CustomScanner(ImageScanner):
    def _process_one(self, bucket, object_name):
        # 自定义处理逻辑
        super()._process_one(bucket, object_name)
```

### 钩子函数（Hook）

在扫描过程中插入自定义逻辑：

```python
scanner.on_violation(lambda record: send_alert(record))
scanner.on_error(lambda error: log_to_external_system(error))
```

## 故障排查

### 问题：扫描速度慢

**原因**：
- IMS API 限流
- MinIO 网络延迟
- 数据库写入慢

**解决**：
```python
# 1. 增加 IMS 配额
# 2. 优化数据库索引
# 3. 调整并发数
MAX_CONCURRENT = 10
```

### 问题：内存占用过高

**原因**：缓存太大

**解决**：
```python
CACHE_MAX_SIZE = 1000  # 减少缓存大小
```

### 问题：出现 "phash is NULL"

**原因**：图片无法识别（损坏或格式不支持）

**解决**：
```python
# 检查图片格式支持
supported_formats = ['JPEG', 'PNG', 'GIF', 'BMP']
```

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [HANDLER](./HANDLER.md) →
